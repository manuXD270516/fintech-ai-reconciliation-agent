"""Capture the static demo fixture for GitHub Pages from a real local run (synthetic data).

    uv run python scripts/capture_demo_fixtures.py   # needs `docker compose up` (AI enabled)

Creates a fresh demo session (scripts/demo.py seed), runs one investigation on the amount
mismatch, opens its case, proposes adopting the reviewed draft and records a supervisor
decision; also leaves a second case pending. It then records the JSON of every GET the
dashboard issues and writes apps/web/public/demo/fixtures.json. No token, host, path or
secret is stored: only API response bodies, which contain synthetic data and opaque IDs.
"""

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.demo import seed, tokens  # noqa: E402
from scripts.smoke import Api, expect, load_env  # noqa: E402

OUT = ROOT / "apps" / "web" / "public" / "demo" / "fixtures.json"
TERMINAL = {"NOT_NEEDED", "DRAFTED", "ABSTAINED", "ESCALATED", "FAILED"}
FORBIDDEN = re.compile(r"(?i)eyJ[a-z0-9_-]{10,}\.|[a-z]:\\\\users|/home/|127\.0\.0\.1|localhost")


def ok(resp: Any, *codes: int) -> dict[str, Any]:
    expect(resp.status in codes, f"{resp.status}: {resp.text[:300]}")
    body: dict[str, Any] = resp.body
    return body


def capture(api: Api) -> dict[str, Any]:
    session = seed(api)
    tenant, target = session["tenant"], session["try_this"]
    tok = tokens(tenant)
    run_id, ordinal = target["run_id"], target["ordinal"]
    base = f"/v1/runs/{run_id}/results/{ordinal}"

    inv = ok(api.get(f"{base}/investigations", method="POST", token=tok["analyst"]), 202, 200)
    inv_id = inv["investigation_id"]
    deadline = time.monotonic() + 120
    path = f"/v1/investigations/{inv_id}"
    while ok(api.get(path, token=tok["auditor"]), 200)["state"] not in TERMINAL:
        expect(time.monotonic() < deadline, "investigation did not finish")
        time.sleep(0.5)
    case = ok(api.get(f"{base}/cases", method="POST", token=tok["analyst"]), 201, 200)
    case_id = case["case_id"]
    rec = ok(api.get(f"/v1/cases/{case_id}/recommendations", method="POST", token=tok["analyst"],
                     body={"action": "REQUEST_PROVIDER_INFO", "expected_version": 1,
                           "investigation_id": inv_id,
                           "rationale": "adoptar el borrador revisado: pedir reporte corregido"}),
             201)  # fmt: skip
    ok(api.get(f"/v1/cases/{case_id}/decisions", method="POST", token=tok["supervisor"],
               body={"recommendation_id": rec["recommendation_id"], "decision": "APPROVE",
                     "reason": "aprobado: solicitar información al proveedor",
                     "expected_version": 2, "idempotency_key": f"demo-{uuid.uuid4().hex[:10]}"}),
       201)  # fmt: skip

    # A second case left pending so the queue view has something to review.
    items = ok(api.get(f"/v1/runs/{run_id}/results?limit=500", token=tok["auditor"]), 200)["items"]
    other = next(i for i in items if i["ordinal"] != ordinal and i["match_status"] != "EXACT")
    pending = ok(api.get(f"/v1/runs/{run_id}/results/{other['ordinal']}/cases", method="POST",
                         token=tok["analyst"]), 201)  # fmt: skip
    pending_rec = ok(api.get(f"/v1/cases/{pending['case_id']}/recommendations", method="POST",
               token=tok["analyst"],
               body={"action": "REQUEST_ADJUSTMENT_REVIEW", "expected_version": 1,
                     "rationale": "revisar el resultado sin par antes de cerrar"}),
       201)  # fmt: skip

    get: dict[str, Any] = {}
    reader = tok["auditor"]

    def grab(path: str) -> Any:
        body = ok(api.get(path, token=reader), 200)
        get[path.split("?", maxsplit=1)[0]] = body
        return body

    batches = grab("/v1/batches")
    for batch in batches:
        grab(f"/v1/batches/{batch['batch_id']}")
        for run in grab(f"/v1/batches/{batch['batch_id']}/runs"):
            grab(f"/v1/runs/{run['run_id']}")
            grab(f"/v1/runs/{run['run_id']}/results?limit=500")
    grab(f"/v1/investigations/{inv_id}")
    for summary in grab("/v1/cases"):
        grab(f"/v1/cases/{summary['case_id']}")
        grab(f"/v1/cases/{summary['case_id']}/audit")
    existing = {
        f"POST {base}/investigations": {"investigation_id": inv_id, "created": False,
                                        "status": "existing"},
        f"POST {base}/cases": {"case_id": case_id, "created": False},
        f"POST /v1/runs/{run_id}/results/{other['ordinal']}/cases":
            {"case_id": pending["case_id"], "created": False},
    }  # fmt: skip
    # The pending recommendation is captured as pending; locally it is then resolved so the
    # demo does not leave work in the human queue (HumanBacklog would fire after 24 h).
    from scripts.ops_drills import drill  # noqa: PLC0415

    drill("clear-backlog", pending_rec["recommendation_id"])
    return {
        "kind": "SYNTHETIC",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": "API responses captured from a local run; AI output is SIMULATED (scripted).",
        "tenant": tenant,
        "subjects": {"analyst": "ana-demo", "supervisor": "sofia-demo", "auditor": "aud-demo"},
        "entry": {
            "run_id": run_id,
            "ordinal": ordinal,
            "investigation_id": inv_id,
            "case_id": case_id,
        },
        "get": get,
        "existing": existing,
    }


def main() -> int:
    api = Api(int(load_env().get("API_HOST_PORT", "18180")))
    api.wait_status("/health/ready", 200, timeout=120)
    data = capture(api)
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True)
    leaked = FORBIDDEN.findall(text)
    expect(not leaked, f"fixture contains forbidden content: {leaked[:3]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({"written": OUT.relative_to(ROOT).as_posix(), "bytes": len(text),
                      "responses": len(data["get"])}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
