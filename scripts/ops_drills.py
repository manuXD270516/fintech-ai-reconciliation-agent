"""M9 operational drills used by the smoke (`M9-T04`..`M9-T06`).

Every fault is injected only into this repository's Compose project and undone in a
`finally` block. Thresholds are the EXPECTED alert rules; the drills verify that each
fault fires its alert, that recovery clears it and that no effect is duplicated.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from recon_api.alerts import evaluate, firing, load_rules
from recon_api.metrics import parse
from scripts import dev_auth
from scripts.smoke import ROOT, Api, SmokeFailure, compose, expect

RULES = load_rules(ROOT / "infra" / "observability" / "alerts.toml")
FORBIDDEN_LABEL_PREFIXES = ("tenant", "subject", "transaction", "case_id", "run_id", "user")
STALL_SECONDS = 60  # EXPECTED threshold of OutboxStalled / WorkerHeartbeatMissing


def scrape(api: Api) -> str:
    resp = api.get("/metrics", timeout=15)
    expect(resp.status == 200, resp.text[-500:])
    return resp.text


def active(api: Api) -> list[str]:
    return sorted({a.rule for a in firing(evaluate(scrape(api), RULES))})


def wait_alert(api: Api, rule: str, *, present: bool, timeout: float) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if (rule in active(api)) == present:
            return round(time.monotonic() - started, 1)
        time.sleep(2)
    raise SmokeFailure(f"{rule} {'did not fire' if present else 'did not clear'} in {timeout}s")


def drill(*args: str) -> dict[str, Any]:
    proc = compose(
        "--profile", "smoke", "run", "--rm", "smoke", "python", "-m",
        "tests.integration.fault_injection", *args, timeout=300,
    )  # fmt: skip
    result: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    return result


def dlq(*args: str) -> dict[str, Any]:
    proc = compose("exec", "-T", "worker", "python", "-m", "recon_worker.dlq", *args, timeout=120)
    result: dict[str, Any] = json.loads(proc.stdout)
    return result


def triage(action: str, reason: str, limit: int) -> list[dict[str, Any]]:
    args = ("--action", action, "--operator", "ops-smoke", "--reason", reason)
    triaged: list[dict[str, Any]] = dlq("triage", *args, "--limit", str(limit))["triaged"]
    return triaged


# --- M9-T04 ---------------------------------------------------------------------


def metrics_and_alerts(api: Api, secrets: list[str]) -> dict[str, Any]:
    text = scrape(api)
    for secret in secrets:
        expect(secret not in text, "secret value in /metrics")
    labels = set(re.findall(r'[{,]([a-z_]+)="', text))
    expect(not [n for n in labels if n.startswith(FORBIDDEN_LABEL_PREFIXES)], labels)
    samples = parse(text)
    up = {lab["source"]: v for lab, v in samples["recon_metrics_source_up"]}
    expect(up == {"database": 1.0, "messaging": 1.0}, up)
    beats = {lab["service"]: v for lab, v in samples["recon_service_heartbeat_age_seconds"]}
    expect(beats.get("worker", 999) < STALL_SECONDS, beats)
    expect(beats.get("investigator", 999) < STALL_SECONDS, beats)
    routes = {lab["route"] for lab, _ in samples["recon_http_requests_total"]}
    expect(not [r for r in routes if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", r)], routes)
    critical = [a.rule for a in firing(evaluate(text, RULES)) if a.severity == "critical"]
    expect(critical == [], f"critical alerts on a healthy stack: {critical}")
    return {
        "series": len(samples),
        "label_names": sorted(labels),
        "heartbeat_age_seconds": beats,
        "outbox_pending": samples["recon_outbox_pending"][0][1],
        "firing_before_drills": active(api),
    }


# --- M9-T05 ---------------------------------------------------------------------


def _wait_run(api: Api, run_id: str, token: str, timeout: float = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        body: dict[str, Any] = api.get(f"/v1/runs/{run_id}", token=token).body
        if body.get("status") == "completed":
            return body
        expect(time.monotonic() < deadline, f"run {run_id} did not complete: {body}")
        time.sleep(1)


def broker_and_worker_outage(api: Api) -> dict[str, Any]:
    """Broker and relay down: commands land in the outbox, alerts fire, recovery is exact."""
    from scripts.web_e2e import new_batch  # noqa: PLC0415 - shared synthetic batch helper

    analyst = dev_auth.token("ana-drill", ["analyst"])
    integration = dev_auth.token("svc-drill-ingest", ["integration"])
    batch_id = new_batch(api, analyst, integration, "drill")
    compose("stop", "nats", "worker")
    try:
        run = api.get(f"/v1/batches/{batch_id}/runs", method="POST", token=analyst)
        expect(run.status == 202, f"run must be accepted into the outbox: {run.text}")
        run_id = run.body["run_id"]
        source_down = wait_alert(api, "MetricsSourceDown", present=True, timeout=30)
        stalled = wait_alert(api, "OutboxStalled", present=True, timeout=STALL_SECONDS + 40)
        heartbeat = wait_alert(api, "WorkerHeartbeatMissing", present=True, timeout=40)
        during = active(api)
        status = api.get(f"/v1/runs/{run_id}", token=analyst).body["status"]
        expect(status == "requested", f"run advanced without broker: {status}")
    finally:
        compose("start", "nats")
        compose("up", "-d", "worker")
    api.wait_status("/health/ready", 200, timeout=90)
    first = _wait_run(api, run_id, analyst)
    items = api.get(f"/v1/runs/{run_id}/results?limit=500", token=analyst).body["items"]
    expect(len(items) == sum(first["counts"].values()), "results duplicated or missing")
    runs = api.get(f"/v1/batches/{batch_id}/runs", token=analyst).body
    expect(len(runs) == 1, f"exactly one run expected after the outage: {runs}")
    cleared = {
        rule: wait_alert(api, rule, present=False, timeout=60)
        for rule in ("OutboxStalled", "WorkerHeartbeatMissing", "MetricsSourceDown")
    }
    # Determinism check: a fresh run over the same inputs gives the same snapshot and counts.
    again = api.get(f"/v1/batches/{batch_id}/runs", method="POST", token=analyst)
    expect(again.status == 202, again.text)
    second = _wait_run(api, again.body["run_id"], analyst)
    expect(second["snapshot_hash"] == first["snapshot_hash"], (first, second))
    expect(second["counts"] == first["counts"], (first["counts"], second["counts"]))
    return {
        "run_id": run_id,
        "alert_seconds": {
            "MetricsSourceDown": source_down,
            "OutboxStalled": stalled,
            "WorkerHeartbeatMissing": heartbeat,
        },
        "firing_during_outage": during,
        "status_during_outage": status,
        "counts_after_recovery": first["counts"],
        "result_rows": len(items),
        "runs_for_batch_after_recovery": len(runs),
        "clear_seconds": cleared,
        "rerun_same_snapshot_and_counts": True,
    }


def dead_letter_triage(api: Api) -> dict[str, Any]:
    tenant = f"tenant-drill-{uuid.uuid4().hex[:8]}"
    backlog = dlq("list")["unhandled"]
    if backlog:  # leftovers from integration tests: poison messages by construction
        triage("discard", "smoke: dead letters from integration tests", len(backlog) + 10)
    wait_alert(api, "DeadLetters", present=False, timeout=30)
    drill("poison", tenant)
    deadline = time.monotonic() + 30
    while not dlq("list")["unhandled"]:
        expect(time.monotonic() < deadline, "poison message did not reach the DLQ")
        time.sleep(1)
    fired = wait_alert(api, "DeadLetters", present=True, timeout=30)
    letter = drill("dead-letter", tenant)
    pending = dlq("list")["unhandled"]
    expect(len(pending) == 2, pending)
    expect(pending[0]["reason"].startswith("poison:") and not pending[0]["replayable"], pending)
    expect(pending[1]["replayable"], pending)
    blocked = triage("replay", "drill: replay attempt before discarding poison", 5)
    discarded = triage("discard", "drill: malformed event_id, fixed at the producer", 1)
    replayed = triage("replay", "drill: dependency recovered", 1)
    expect([r["outcome"] for r in blocked] == ["not_replayable"], blocked)
    expect([r["outcome"] for r in discarded] == ["discarded"], discarded)
    expect(discarded[0]["reason"].startswith("poison:"), discarded)
    expect([r["outcome"] for r in replayed] == ["replayed"], replayed)
    deadline = time.monotonic() + 30
    while drill("artifacts", tenant)["artifacts"] < 1:
        expect(time.monotonic() < deadline, "replayed event was not ingested")
        time.sleep(1)
    after_first = drill("artifacts", tenant)
    expect(after_first == {"artifacts": 1, "observations": 1}, after_first)
    # A second DLQ copy of the same event, replayed again, must not duplicate effects.
    drill("dead-letter", tenant, letter["event_id"], letter["source_record_id"])
    again = triage("replay", "drill: duplicate replay of the same event", 1)
    expect([r["outcome"] for r in again] == ["replayed"], again)
    time.sleep(3)  # let the ingest consumer process the duplicate
    after_second = drill("artifacts", tenant)
    expect(after_second == after_first, f"duplicate replay changed effects: {after_second}")
    cleared = wait_alert(api, "DeadLetters", present=False, timeout=30)
    audit = drill("dlq-audit", tenant)["entries"]
    expect([e["action"] for e in audit] == ["dlq.discard", "dlq.replay", "dlq.replay"], audit)
    return {
        "backlog_discarded": len(backlog),
        "alert_fire_seconds": fired,
        "replay_blocked_by_poison": blocked,
        "discarded": discarded,
        "replayed": replayed,
        "drill_event": letter,
        "effects_after_first_replay": after_first,
        "effects_after_duplicate_replay": after_second,
        "alert_clear_seconds": cleared,
        "audit": audit,
    }


# --- M9-T06 ---------------------------------------------------------------------


def backup_restore(out_dir: Path) -> dict[str, Any]:
    from scripts import ops  # noqa: PLC0415

    dump = out_dir / f"recon-{uuid.uuid4().hex[:8]}.dump"
    started = time.monotonic()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            expect(ops.main(["backup", "--out", str(dump)]) == 0, "backup failed")
        backup = json.loads(dump.with_suffix(".json").read_text(encoding="utf-8"))
        backup_seconds = round(time.monotonic() - started, 2)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = ops.main(["restore-check", "--dump", str(dump)])
        report = json.loads(buffer.getvalue())
    except RuntimeError as exc:
        raise SmokeFailure(str(exc)) from None
    finally:
        for path in (dump, dump.with_suffix(".json")):
            path.unlink(missing_ok=True)
    expect(code == 0 and report["counts_match_backup"] and report["audit_digest_match_backup"],
           report)  # fmt: skip
    return {
        "dump_bytes": backup["bytes"],
        "backup_seconds": backup_seconds,
        "restore_seconds": report["restore_seconds"],
        "counts_match_backup": report["counts_match_backup"],
        "audit_digest_match_backup": report["audit_digest_match_backup"],
        "rows_backed_up": sum(backup["counts"].values()),
        "rows_written_after_backup": report["rows_written_after_backup"],
    }
