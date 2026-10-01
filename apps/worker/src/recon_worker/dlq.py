"""Operator tool for dead letters (runbook docs/runbooks/dlq-replay.md).

    python -m recon_worker.dlq list
    python -m recon_worker.dlq triage --action replay  --operator ops-ana --reason "..." [--limit N]
    python -m recon_worker.dlq triage --action discard --operator ops-ana --reason "..." [--limit N]

Dead letters stay in RECON_DLQ (7 days) as history; triage acknowledges them on the
durable `dlq-triage` consumer, which is what clears the `DeadLetters` alert. Replay
republishes the original payload to its original subject with a deterministic
`Nats-Msg-Id`; consumers stay idempotent (inbox / artifact idempotency key), so replaying
twice never duplicates effects. Every triage action is audited.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import nats
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from sqlalchemy import Engine, insert

from recon_api.config import load_settings
from recon_store.engine import runtime_engine, runtime_url
from recon_store.tables import audit_entries
from recon_worker.runner import DLQ_STREAM, DLQ_TRIAGE, INGEST_PREFIX, SUBJECT_PREFIX

REPLAYABLE = (f"{SUBJECT_PREFIX}.", f"{INGEST_PREFIX}.")
SYSTEM_TENANT = "_system"


@dataclass(frozen=True, slots=True)
class DeadLetter:
    stream_seq: int
    subject: str
    reason: str
    data: str

    @classmethod
    def parse(cls, stream_seq: int, raw: bytes) -> DeadLetter:
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return cls(
            stream_seq,
            str(body.get("subject", "")),
            str(body.get("reason", "unparseable dead letter")),
            str(body.get("data", "")),
        )

    def tenant(self) -> str:
        """Tenant for the audit entry: from the ingest subject or the event envelope."""
        if self.subject.startswith(f"{INGEST_PREFIX}."):
            parts = self.subject.split(".")
            return parts[2] if len(parts) == 5 else SYSTEM_TENANT
        try:
            envelope = json.loads(self.data)
        except ValueError:
            return SYSTEM_TENANT
        value = envelope.get("tenant_id") if isinstance(envelope, dict) else None
        return str(value)[:128] if value else SYSTEM_TENANT

    @property
    def replayable(self) -> bool:
        """Only exhausted deliveries can succeed later; poison never will."""
        return self.subject.startswith(REPLAYABLE) and self.reason.startswith("exhausted:")

    def summary(self) -> dict[str, Any]:
        return {
            "stream_seq": self.stream_seq,
            "subject": self.subject,
            "reason": self.reason[:200],
            "replayable": self.replayable,
        }


def audit(engine: Engine, letter: DeadLetter, action: str, operator: str, reason: str,
          outcome: str, now: datetime) -> None:  # fmt: skip
    with engine.begin() as conn:
        conn.execute(
            insert(audit_entries).values(
                occurred_at=now,
                tenant_id=letter.tenant(),
                actor=operator[:128],
                action=f"dlq.{action}",
                resource_type="dead_letter",
                resource_id=f"{DLQ_STREAM}:{letter.stream_seq}",
                outcome=outcome,
                correlation_id=f"dlq-{letter.stream_seq}",
                details={
                    "operator_reason": reason[:500],
                    "dead_letter_reason": letter.reason[:300],
                    "original_subject_prefix": ".".join(letter.subject.split(".")[:2]),
                },
            )
        )


async def pending_letters(js: JetStreamContext) -> list[DeadLetter]:
    info = await js.consumer_info(DLQ_STREAM, DLQ_TRIAGE)
    stream = await js.stream_info(DLQ_STREAM)
    letters = []
    for seq in range(int(info.ack_floor.stream_seq) + 1, int(stream.state.last_seq) + 1):
        try:
            msg = await js.get_msg(DLQ_STREAM, seq)
        except nats.js.errors.NotFoundError:
            continue
        letters.append(DeadLetter.parse(seq, msg.data or b""))
    return letters


async def triage(
    js: JetStreamContext,
    engine: Engine,
    action: str,
    operator: str,
    reason: str,
    limit: int,
) -> list[dict[str, Any]]:
    sub = await js.pull_subscribe_bind(DLQ_TRIAGE, stream=DLQ_STREAM)
    results: list[dict[str, Any]] = []
    while len(results) < limit:
        try:
            # One at a time: a fetched-but-unhandled letter would stay ack-pending (hidden)
            # until ack_wait expires.
            msgs: list[Msg] = await sub.fetch(batch=1, timeout=2)
        except TimeoutError:
            break
        for msg in msgs:
            letter = DeadLetter.parse(msg.metadata.sequence.stream, msg.data)
            outcome = "discarded"
            if action == "replay":
                if not letter.replayable:
                    # Stop at the first letter that cannot be replayed: it needs a discard
                    # decision first (messages are triaged in order).
                    await msg.nak()
                    results.append(letter.summary() | {"outcome": "not_replayable"})
                    return results
                await js.publish(
                    letter.subject,
                    letter.data.encode(),
                    headers={"Nats-Msg-Id": f"dlq-replay-{letter.stream_seq}"},
                    timeout=5,
                )
                outcome = "replayed"
            await asyncio.to_thread(
                audit, engine, letter, action, operator, reason, outcome, datetime.now(UTC)
            )
            await msg.ack()
            results.append(letter.summary() | {"outcome": outcome})
    return results


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    tri = sub.add_parser("triage")
    tri.add_argument("--action", choices=["replay", "discard"], required=True)
    tri.add_argument("--operator", required=True)
    tri.add_argument("--reason", required=True)
    tri.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    settings = load_settings()
    nc = await nats.connect(
        servers=[settings.nats_url],
        user=settings.nats_user,
        password=settings.nats_password.get_secret_value(),
        connect_timeout=5,
    )
    try:
        js = nc.jetstream(timeout=5)
        if args.command == "list":
            letters = await pending_letters(js)
            print(json.dumps({"unhandled": [x.summary() for x in letters]}, indent=2))
            return 0
        engine = runtime_engine(
            runtime_url(
                settings.db_host,
                settings.db_port,
                settings.db_name,
                settings.db_user,
                settings.db_password.get_secret_value(),
            )
        )
        try:
            results = await triage(js, engine, args.action, args.operator, args.reason, args.limit)
        finally:
            engine.dispose()
        print(json.dumps({"triaged": results}, indent=2))
        return 0
    finally:
        await nc.close()


def main() -> int:
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
