"""Dashboard E2E (M8): prepare data and dev tokens on the running stack, then run Playwright.

Usage: uv run python scripts/web_e2e.py   (requires `docker compose up`, `npm ci` in
apps/web and `npx playwright install chromium`). Used by the smoke step M8-T07.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
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

WEB = ROOT / "apps" / "web"
BATCH = "b-prov-alfa-merchant-03-USD"


def prepare(api: Api) -> dict[str, Any]:
    tokens = {
        "analyst": dev_auth.token("ana-web", ["analyst"]),
        "dual": dev_auth.token("ana-web", ["analyst", "supervisor"]),
        "supervisor": dev_auth.token("sofia-web", ["supervisor"]),
        "auditor": dev_auth.token("aud-web", ["auditor"]),
    }
    integration = dev_auth.token("svc-web-ingest", ["integration"])
    root = ROOT / "datasets" / "synthetic" / "transactions-v2"
    files = {p.name: p.read_text(encoding="utf-8") for p in root.glob("*.csv")}
    for name, source in (("internal_ledger.csv", "internal_ledger"),
                         ("provider_report.csv", "provider_report")):  # fmt: skip
        reader = csv.DictReader(io.StringIO(files[name]))
        rows = [r for r in reader if r["provider_id"] == "prov-alfa"]
        body = {
            "source": source,
            "provider_id": "prov-alfa",
            "idempotency_key": f"smoke-v2-{name}-prov-alfa",
            "content": to_csv(rows),
        }
        resp = api.get("/v1/artifacts", method="POST", body=body, token=integration)
        expect(resp.status in (200, 201), resp.text)
    labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
    batch = next(b for b in batches_for(labels) if b.batch_id == BATCH)
    batch_id = f"web-{uuid.uuid4().hex[:8]}-{BATCH}"
    body = {
        "batch_id": batch_id,
        "provider_id": batch.provider_id,
        "merchant_account": batch.merchant_account,
        "currency": batch.currency,
        "window_start": batch.window_start.isoformat(),
        "window_end": batch.window_end.isoformat(),
        "business_timezone": batch.business_timezone,
        "cutoff_at": batch.cutoff_at.isoformat(),
    }
    expect(api.get("/v1/batches", method="POST", body=body, token=tokens["analyst"]).status == 201)
    for source in ("internal_ledger", "provider_report"):
        done = api.get(f"/v1/batches/{batch_id}/sources/{source}/complete", method="POST",
                       token=integration)  # fmt: skip
        expect(done.status == 200, done.text)
    run = api.get(f"/v1/batches/{batch_id}/runs", method="POST", token=tokens["analyst"])
    expect(run.status == 202, run.text)
    run_id = run.body["run_id"]
    deadline = time.monotonic() + 60
    while api.get(f"/v1/runs/{run_id}", token=tokens["auditor"]).body.get("status") != "completed":
        expect(time.monotonic() < deadline, "run did not complete")
        time.sleep(0.5)
    items = api.get(f"/v1/runs/{run_id}/results?limit=500", token=tokens["auditor"]).body["items"]
    mismatch = next(i for i in items if "AMOUNT_MISMATCH" in i["discrepancy_types"])
    return tokens | {"run_id": run_id, "payment_ref": mismatch["payment_ref"]}


def run_e2e(env: dict[str, str]) -> dict[str, Any]:
    api = Api(int(env.get("API_HOST_PORT", "18180")))
    context = prepare(api)
    npm = shutil.which("npm") or "npm"
    npx = shutil.which("npx") or "npx"
    child = dict(os.environ) | {"E2E_CONTEXT": json.dumps(context)}
    build = subprocess.run([npm, "run", "build"], cwd=WEB, capture_output=True, text=True,
                           check=False, env=child)  # fmt: skip
    expect(build.returncode == 0, build.stdout[-1500:] + build.stderr[-800:])
    test = subprocess.run([npx, "playwright", "test"], cwd=WEB, capture_output=True, text=True,
                          check=False, env=child, timeout=600)  # fmt: skip
    report_path = WEB / "test-results" / "e2e-report.json"
    stats: dict[str, Any] = {}
    if report_path.exists():
        stats = json.loads(report_path.read_text("utf-8")).get("stats", {})
    expect(test.returncode == 0, test.stdout[-3000:] + test.stderr[-800:])
    return {"run_id": context["run_id"], "payment_ref": context["payment_ref"], "stats": stats,
            "output": test.stdout.strip().splitlines()[-6:]}  # fmt: skip


def main() -> int:
    try:
        print(json.dumps(run_e2e(load_env()), indent=2))
    except SmokeFailure as exc:
        print(f"[FAIL] web e2e: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
