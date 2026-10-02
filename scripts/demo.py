"""Local demo helper (M10). Synthetic data only; nothing is published or deployed.

    uv run python scripts/demo.py seed                 # new isolated demo session (tenant)
    uv run python scripts/demo.py kill-switch off|on   # AI investigations off/on (API only)
    uv run python scripts/demo.py resources            # container memory/CPU and image sizes
    uv run python scripts/demo.py drill                # isolation + kill-switch check (smoke)

`seed` creates a tenant `demo-<id>`, ingests the transactions-v2 dataset into it over HTTP,
creates and runs every labelled batch, checks the results against the dataset labels and
writes dev tokens for that tenant to `.demo/<tenant>.json` (git-ignored). Sessions never
share data: every API call is scoped by the token's tenant.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recon_domain.oracle import batches_for, to_csv  # noqa: E402
from scripts import dev_auth  # noqa: E402
from scripts.smoke import Api, SmokeFailure, expect, load_env  # noqa: E402

DATASET = ROOT / "datasets" / "synthetic" / "transactions-v2"
SESSIONS = ROOT / ".demo"
WEB_URL = "http://127.0.0.1:18181"


def tokens(tenant: str) -> dict[str, str]:
    return {
        "analyst": dev_auth.token("ana-demo", ["analyst"], tenant),
        "supervisor": dev_auth.token("sofia-demo", ["supervisor"], tenant),
        "auditor": dev_auth.token("aud-demo", ["auditor"], tenant),
        "integration": dev_auth.token("svc-demo-ingest", ["integration"], tenant),
    }


def _wait_run(api: Api, run_id: str, token: str, timeout: float = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        body: dict[str, Any] = api.get(f"/v1/runs/{run_id}", token=token).body
        if body.get("status") == "completed":
            return body
        expect(time.monotonic() < deadline, f"run {run_id} did not complete")
        time.sleep(0.5)


def seed(api: Api) -> dict[str, Any]:
    tenant = f"demo-{uuid.uuid4().hex[:8]}"
    tok = tokens(tenant)
    files = {p.name: p.read_text(encoding="utf-8") for p in DATASET.glob("*.csv")}
    for name, source in (("internal_ledger.csv", "internal_ledger"),
                         ("provider_report.csv", "provider_report")):  # fmt: skip
        rows = [dict(r, tenant_id=tenant) for r in csv.DictReader(io.StringIO(files[name]))]
        for provider in sorted({r["provider_id"] for r in rows}):
            body = {
                "source": source,
                "provider_id": provider,
                "idempotency_key": f"{tenant}-{name}-{provider}",
                "content": to_csv([r for r in rows if r["provider_id"] == provider]),
            }
            resp = api.get("/v1/artifacts", method="POST", body=body, token=tok["integration"])
            expect(resp.status == 201, resp.text)
    labels = [dict(r, tenant_id=tenant) for r in csv.DictReader(io.StringIO(files["labels.csv"]))]
    runs: dict[str, str] = {}
    for batch in batches_for(labels):
        body = {"batch_id": batch.batch_id, "provider_id": batch.provider_id,
                "merchant_account": batch.merchant_account, "currency": batch.currency,
                "window_start": batch.window_start.isoformat(),
                "window_end": batch.window_end.isoformat(),
                "business_timezone": batch.business_timezone,
                "cutoff_at": batch.cutoff_at.isoformat()}  # fmt: skip
        created = api.get("/v1/batches", method="POST", body=body, token=tok["analyst"])
        expect(created.status == 201, created.text)
        for source in ("internal_ledger", "provider_report"):
            done = api.get(f"/v1/batches/{batch.batch_id}/sources/{source}/complete",
                           method="POST", token=tok["integration"])  # fmt: skip
            expect(done.status == 200, done.text)
        run = api.get(f"/v1/batches/{batch.batch_id}/runs", method="POST", token=tok["analyst"])
        expect(run.status == 202, run.text)
        runs[batch.batch_id] = run.body["run_id"]
    counts: dict[str, int] = {}
    got: dict[str, str] = {}
    mismatch: dict[str, Any] | None = None
    for batch_id, run_id in runs.items():
        for status, n in _wait_run(api, run_id, tok["auditor"])["counts"].items():
            counts[status] = counts.get(status, 0) + n
        items = api.get(f"/v1/runs/{run_id}/results?limit=500", token=tok["auditor"]).body["items"]
        for item in items:
            got[item["payment_ref"]] = item["match_status"]
            if mismatch is None and "AMOUNT_MISMATCH" in item["discrepancy_types"]:
                mismatch = {"batch_id": batch_id, "run_id": run_id, "ordinal": item["ordinal"],
                            "payment_ref": item["payment_ref"]}  # fmt: skip
    wrong = [r["payment_ref"] for r in labels if got.get(r["payment_ref"]) != r["expected_match"]]
    expect(not wrong, f"results differ from the dataset labels: {wrong}")
    expect(mismatch is not None, "no AMOUNT_MISMATCH result in the dataset")
    SESSIONS.mkdir(exist_ok=True)
    session_file = SESSIONS / f"{tenant}.json"
    session_file.write_text(json.dumps({"tenant": tenant, "tokens": tok}, indent=2), "utf-8")
    return {
        "tenant": tenant,
        "batches": len(runs),
        "payments": len(labels),
        "counts": counts,
        "matches_labels": True,
        "try_this": mismatch,
        "dashboard": f"{WEB_URL}/#/runs/{mismatch['run_id']}" if mismatch else WEB_URL,
        "tokens_file": session_file.relative_to(ROOT).as_posix(),
    }


def restart_api(api: Api, **settings: str) -> float:
    """Recreate this project's `api` container with APP_* overrides; returns seconds to ready."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("APP_AI_", "APP_RULESET"))}
    env |= settings
    proc = subprocess.run(["docker", "compose", "up", "-d", "api"], cwd=ROOT, env=env,
                          capture_output=True, text=True, check=False, timeout=300)  # fmt: skip
    expect(proc.returncode == 0, proc.stderr[-1500:])
    return api.wait_status("/health/ready", 200, timeout=120)


def kill_switch(enabled: bool, api: Api) -> dict[str, Any]:
    waited = restart_api(api, APP_AI_ENABLED="true" if enabled else "false")
    metrics = api.get("/metrics").text
    expect(f"recon_ai_enabled {int(enabled)}" in metrics, "switch state not reflected in /metrics")
    return {"ai_enabled": enabled, "seconds_until_ready": round(waited, 2)}


def drill(api: Api) -> dict[str, Any]:
    """Smoke M10-T03/T04: two isolated sessions, and the full human path with AI switched off."""
    first, second = seed(api), seed(api)
    a = tokens(first["tenant"])
    target = first["try_this"]
    foreign_run = api.get(f"/v1/runs/{second['try_this']['run_id']}", token=a["auditor"])
    expect(foreign_run.status == 404, f"cross-session run read: {foreign_run.status}")
    listed = api.get("/v1/batches", token=a["analyst"]).body
    expect(len(listed) == first["batches"], f"session sees foreign batches: {len(listed)}")
    isolation = {"foreign_run_status": foreign_run.status, "own_batches_listed": len(listed)}

    base = f"/v1/runs/{target['run_id']}/results/{target['ordinal']}"
    switched: dict[str, Any] = {}
    try:
        switched["switch_off"] = kill_switch(False, api)
        refused = api.get(f"{base}/investigations", method="POST", token=a["analyst"])
        expect(refused.status == 503 and refused.body["detail"] == {"code": "ai_disabled"},
               refused.text)  # fmt: skip
        case = api.get(f"{base}/cases", method="POST", token=a["analyst"])
        expect(case.status == 201, case.text)
        case_id = case.body["case_id"]
        proposal = {
            "action": "REQUEST_PROVIDER_INFO",
            "expected_version": 1,
            "rationale": "diferencia de monto: pedir reporte corregido (sin IA)",
        }
        rec = api.get(f"/v1/cases/{case_id}/recommendations", method="POST", body=proposal,
                      token=a["analyst"])  # fmt: skip
        expect(rec.status == 201, rec.text)
        decision = {"recommendation_id": rec.body["recommendation_id"], "decision": "APPROVE",
                    "reason": "aprobado con evidencia determinística",
                    "expected_version": 2,
                    "idempotency_key": f"demo-{uuid.uuid4().hex[:10]}"}  # fmt: skip
        decided = api.get(f"/v1/cases/{case_id}/decisions", method="POST", body=decision,
                          token=a["supervisor"])  # fmt: skip
        expect(decided.status == 201, decided.text)
        expect(decided.body["operational_effect"].startswith("none"), decided.body)
        rerun = api.get(f"/v1/batches/{target['batch_id']}/runs", method="POST",
                        token=a["analyst"])  # fmt: skip
        expect(rerun.status == 202, rerun.text)
        _wait_run(api, rerun.body["run_id"], a["auditor"])
        switched |= {"investigation_refused": refused.body["detail"],
                     "case_decided_without_ai": decided.body["decision"],
                     "deterministic_run_completed": True}  # fmt: skip
    finally:
        switched["switch_on"] = kill_switch(True, api)
    again = api.get(f"/v1/runs/{rerun.body['run_id']}/results/{target['ordinal']}/investigations",
                    method="POST", token=a["analyst"])  # fmt: skip
    expect(again.status == 202, f"investigations must work again: {again.text}")
    return {"sessions": [first, second], "isolation": isolation, "kill_switch": switched,
            "investigation_after_switch_on": again.status}  # fmt: skip


def resources() -> dict[str, Any]:
    def run(*args: str) -> list[str]:
        out = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, check=False)
        return [line for line in out.stdout.splitlines() if line.strip()]

    project = json.loads("".join(run("docker", "compose", "config", "--format", "json")))["name"]
    stats = run("docker", "stats", "--no-stream", "--format",
                "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}")  # fmt: skip
    images = run("docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}")
    wanted = [i.split("@")[0] for i in run("docker", "compose", "config", "--images")]
    return {
        "containers": [s.split("\t") for s in stats if s.startswith(f"{project}-")],
        "images": [i.split("\t") for i in images if i.split("\t")[0] in set(wanted)],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    switch = sub.add_parser("kill-switch")
    switch.add_argument("state", choices=["on", "off"])
    sub.add_parser("resources")
    sub.add_parser("drill")
    args = parser.parse_args(argv)
    api = Api(int(load_env().get("API_HOST_PORT", "18180")))
    try:
        api.wait_status("/health/ready", 200, timeout=120)
        if args.command == "seed":
            result = seed(api)
        elif args.command == "kill-switch":
            result = kill_switch(args.state == "on", api)
        elif args.command == "drill":
            result = drill(api)
        else:
            result = resources()
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
