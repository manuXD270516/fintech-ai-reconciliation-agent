"""Investigation requests and checkpoints.

A request is idempotent per (tenant, case, input snapshot hash): repeating it without new
evidence returns the existing investigation instead of spending budget again. The request,
its audit entry and the `InvestigationRequested` outbox event commit together.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import Engine, func, insert, select, text, update

from recon_store.observations import transaction_uid
from recon_store.tables import (
    audit_entries,
    batches,
    investigations,
    observations,
    outbox,
    results,
    runs,
)

INVESTIGATION_REQUESTED = "InvestigationRequested"
TERMINAL = {"NOT_NEEDED", "DRAFTED", "ABSTAINED", "ESCALATED", "FAILED"}
_CLAIM = text("""
UPDATE recon.investigations
SET record = record || jsonb_build_object('claimed_by', CAST(:worker AS text),
                                          'claimed_at', now()::text),
    updated_at = now()
WHERE id = :id
  AND state NOT IN ('NOT_NEEDED', 'DRAFTED', 'ABSTAINED', 'ESCALATED', 'FAILED')
  AND ((state = 'REQUESTED' AND NOT (record ? 'claimed_at'))
       OR updated_at < now() - make_interval(secs => :lease))
RETURNING id
""")


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    blob = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def case_snapshot(
    engine: Engine, tenant_id: str, run_id: uuid.UUID, ordinal: int
) -> dict[str, Any]:
    """Factual snapshot of one result (same shape as recon_agents.models.CaseSnapshot)."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(results, runs.c.run_number, runs.c.batch_id)
                .join(runs, runs.c.id == results.c.run_id)
                .where(
                    runs.c.tenant_id == tenant_id,
                    results.c.run_id == run_id,
                    results.c.ordinal == ordinal,
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise LookupError("result not found")
        batch = (
            conn.execute(
                select(batches).where(
                    batches.c.tenant_id == tenant_id, batches.c.batch_id == row["batch_id"]
                )
            )
            .mappings()
            .one()
        )
        ids = [*row["left_ids"], *row["right_ids"], *row["alternatives"]]
        obs = {
            r["id"]: r
            for r in conn.execute(
                select(
                    observations.c.id,
                    observations.c.source,
                    observations.c.source_record_id,
                    observations.c.occurred_at,
                ).where(observations.c.tenant_id == tenant_id, observations.c.id.in_(ids or [-1]))
            ).mappings()
        }

    def uids(values: list[int]) -> list[str]:
        return [
            str(transaction_uid(tenant_id, obs[v]["source"], obs[v]["source_record_id"]))
            for v in values
            if v in obs
        ]

    occurred = min((o["occurred_at"] for o in obs.values()), default=batch["window_start"])
    return {
        "case_ref": f"{run_id}#{ordinal}",
        "case_version": int(row["run_number"]),
        "tenant_id": tenant_id,
        "batch_id": row["batch_id"],
        "run_id": str(run_id),
        "ordinal": ordinal,
        "payment_ref": row["payment_ref"],
        "operation_type": row["operation_type"],
        "match_status": row["match_status"],
        "rule": row["rule"],
        "discrepancy_types": list(row["discrepancy_types"]),
        "amount_difference_minor": row["amount_difference_minor"],
        "provider_id": batch["provider_id"],
        "merchant_account": batch["merchant_account"],
        "currency": batch["currency"],
        "occurred_at": occurred.isoformat(),
        "left_transaction_ids": uids(list(row["left_ids"])),
        "right_transaction_ids": uids(list(row["right_ids"])),
        "alternatives": uids(list(row["alternatives"])),
    }


class InvestigationRepository:
    """Requests, reads and checkpoints (implements recon_agents' InvestigationStore)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def request(
        self,
        tenant_id: str,
        run_id: uuid.UUID,
        ordinal: int,
        *,
        actor: str,
        correlation_id: str,
    ) -> tuple[str, bool]:
        snapshot = case_snapshot(self.engine, tenant_id, run_id, ordinal)
        digest = snapshot_hash(snapshot)
        with self.engine.begin() as conn:
            token = f"investigation|{tenant_id}|{snapshot['case_ref']}"
            conn.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(token, 0))))
            existing = conn.execute(
                select(investigations.c.id).where(
                    investigations.c.tenant_id == tenant_id,
                    investigations.c.case_ref == snapshot["case_ref"],
                    investigations.c.input_snapshot_hash == digest,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return str(existing), False
            investigation_id = uuid.uuid4()
            conn.execute(
                insert(investigations).values(
                    id=investigation_id,
                    tenant_id=tenant_id,
                    case_ref=snapshot["case_ref"],
                    run_id=run_id,
                    ordinal=ordinal,
                    case_version=snapshot["case_version"],
                    input_snapshot_hash=digest,
                    state="REQUESTED",
                    requested_by=actor,
                    correlation_id=correlation_id,
                    record={"snapshot": snapshot},
                )
            )
            conn.execute(
                insert(audit_entries).values(
                    tenant_id=tenant_id,
                    actor=actor,
                    action="investigation.request",
                    resource_type="investigation",
                    resource_id=str(investigation_id),
                    resource_version=snapshot["case_version"],
                    outcome="requested",
                    correlation_id=correlation_id,
                    details={"case_ref": snapshot["case_ref"], "input_snapshot_hash": digest},
                )
            )
            conn.execute(
                insert(outbox).values(
                    event_id=uuid.uuid4(),
                    event_type=INVESTIGATION_REQUESTED,
                    schema_version=1,
                    tenant_id=tenant_id,
                    aggregate_id=f"investigation/{investigation_id}",
                    aggregate_version=1,
                    correlation_id=correlation_id,
                    payload={"investigation_id": str(investigation_id)},
                )
            )
        return str(investigation_id), True

    def get(self, tenant_id: str, investigation_id: uuid.UUID) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(investigations).where(
                        investigations.c.tenant_id == tenant_id,
                        investigations.c.id == investigation_id,
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else dict(row)

    def load_for_execution(self, investigation_id: uuid.UUID) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(investigations).where(investigations.c.id == investigation_id))
                .mappings()
                .first()
            )
        return None if row is None else dict(row)

    def claim(self, investigation_id: uuid.UUID, worker: str, lease_seconds: int = 600) -> bool:
        """Atomically take an investigation; a stale lease (crashed worker) can be retaken."""
        with self.engine.begin() as conn:
            claimed = conn.execute(
                _CLAIM, {"id": investigation_id, "worker": worker[:64], "lease": lease_seconds}
            ).first()
        return claimed is not None

    def save(self, record: dict[str, Any]) -> None:
        """Checkpoint a state transition; terminal states are audited."""
        investigation_id = uuid.UUID(record["investigation_id"])
        with self.engine.begin() as conn:
            current: dict[str, Any] = conn.execute(
                select(investigations.c.record).where(investigations.c.id == investigation_id)
            ).scalar_one()
            payload = json.loads(json.dumps(record, default=str))
            for kept in ("snapshot", "claimed_by", "claimed_at"):
                payload[kept] = current.get(kept)
            conn.execute(
                update(investigations)
                .where(investigations.c.id == investigation_id)
                .values(state=record["state"], record=payload, updated_at=func.now())
            )
            if record["state"] in TERMINAL:
                conn.execute(
                    insert(audit_entries).values(
                        tenant_id=record["tenant_id"],
                        actor="svc-investigator",
                        action="investigation.finish",
                        resource_type="investigation",
                        resource_id=record["investigation_id"],
                        resource_version=record["case_version"],
                        outcome=record["state"].lower(),
                        correlation_id=record["investigation_id"][:64],
                        details={
                            "tool_calls": record["budget"]["tool_calls"],
                            "generative_calls": record["budget"]["generative_calls"],
                            "model": record["model"],
                        },
                    )
                )
