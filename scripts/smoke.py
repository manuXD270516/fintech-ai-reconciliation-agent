"""Real Compose smoke for M0 (T03, T04, T05, T06, T08, T09 at stack level).

Usage:  uv run python scripts/smoke.py [--down]

Requires Docker with Compose v2 and a `.env` (copy `.env.example`). Never mocks
infrastructure: if Docker is unavailable the smoke fails. Leaves the stack running
unless --down is given; volumes are never removed.
"""

from __future__ import annotations

import argparse
import csv
import functools
import io
import json
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from recon_domain.oracle import batches_for, to_csv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # executed as `python scripts/smoke.py`
    sys.path.insert(0, str(ROOT))

from scripts import dev_auth  # noqa: E402

EVIDENCE_DIR = ROOT / ".smoke"
READY_DEADLINE = 3.0
SECRET_KEYS = (
    "POSTGRES_ADMIN_PASSWORD",
    "APP_DB_PASSWORD",
    "NATS_APP_PASSWORD",
    "MCP_DB_PASSWORD",
)


@dataclass
class Result:
    test_id: str
    name: str
    ok: bool
    seconds: float
    details: dict[str, Any] = field(default_factory=dict)


class SmokeFailure(Exception):
    pass


def expect(condition: bool, message: object = "expectation failed") -> None:
    if not condition:
        raise SmokeFailure(str(message))


def load_env() -> dict[str, str]:
    env_file = ROOT / ".env"
    if not env_file.exists():
        raise SmokeFailure(".env missing: copy .env.example to .env (synthetic local values)")
    values: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def compose(
    *args: str, check: bool = True, timeout: float = 600
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise SmokeFailure(f"docker compose {' '.join(args)} failed: {proc.stderr.strip()[-800:]}")
    return proc


@dataclass
class Http:
    status: int
    body: dict[str, Any]
    headers: dict[str, str]
    elapsed: float
    text: str


class Api:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def get(
        self,
        path: str,
        request_id: str | None = None,
        timeout: float = 10,
        *,
        method: str = "GET",
        body: object = None,
        token: str | None = None,
    ) -> Http:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method)  # noqa: S310
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        if request_id:
            request.add_header("X-Request-ID", request_id)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
                status, raw, headers = resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as err:
            status, raw, headers = err.code, err.read(), dict(err.headers)
        elapsed = time.perf_counter() - started
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            parsed = {}
        return Http(status, parsed, {k.lower(): v for k, v in headers.items()}, elapsed, text)

    def wait_status(self, path: str, status: int, timeout: float = 120) -> float:
        started = time.perf_counter()
        while time.perf_counter() - started < timeout:
            try:
                if self.get(path, timeout=5).status == status:
                    return time.perf_counter() - started
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(1)
        raise SmokeFailure(f"{path} did not return {status} within {timeout}s")


class Smoke:
    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.api = Api(int(env.get("API_HOST_PORT", "18180")))
        self.results: list[Result] = []
        self.secrets = [env[k] for k in SECRET_KEYS if env.get(k)]
        self.runs: dict[str, str] = {}

    def check(self, test_id: str, name: str, fn: Callable[[], dict[str, Any]]) -> None:
        started = time.perf_counter()
        try:
            details = fn()
            ok = True
        except (SmokeFailure, KeyError, subprocess.TimeoutExpired) as exc:
            details = {"error": str(exc)[-1500:]}
            ok = False
        seconds = round(time.perf_counter() - started, 2)
        self.results.append(Result(test_id, name, ok, seconds, details))
        print(f"[{'PASS' if ok else 'FAIL'}] {test_id} {name} ({seconds}s)", flush=True)
        if not ok:
            print(f"       {details['error']}", flush=True)

    def assert_no_secrets(self, text: str, where: str) -> None:
        for secret in self.secrets:
            expect(secret not in text, f"secret value leaked in {where}")

    # --- checks -----------------------------------------------------------------

    def startup(self) -> dict[str, Any]:
        dev_auth.init()
        compose("up", "-d", "--build", timeout=900)
        waited = self.api.wait_status("/health/ready", 200)
        return {"seconds_until_ready": round(waited, 2)}

    def healthy_contract(self) -> dict[str, Any]:
        live = self.api.get("/health/live")
        ready = self.api.get("/health/ready")
        expect(live.status == 200, live.text)
        expect(ready.status == 200, ready.text)
        expect(set(live.body) == {"status", "request_id"})
        expect(set(ready.body) == {"status", "request_id", "checks"})
        expect(ready.body["checks"] == {"database": "ok", "vector": "ok", "messaging": "ok"})
        for resp in (live, ready):
            expect(resp.headers["x-request-id"] == resp.body["request_id"])
            expect("server" not in resp.headers)
            self.assert_no_secrets(resp.text, "health body")
            for marker in ("://", "Traceback", "5432", "4222", "postgres", "recon_app"):
                expect(marker not in resp.text, f"sensitive detail {marker!r} in body")
        expect(ready.elapsed <= READY_DEADLINE)
        return {"live": live.body, "ready": ready.body, "ready_seconds": round(ready.elapsed, 3)}

    def infra_tests(self) -> dict[str, Any]:
        proc = compose(
            "--profile",
            "smoke",
            "run",
            "--rm",
            "--build",
            "smoke",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-m",
            "integration",
            "-v",
            "tests/integration",
            check=False,
            timeout=900,
        )
        lines = [ln for ln in proc.stdout.splitlines() if "PASSED" in ln or "FAILED" in ln]
        expect(proc.returncode == 0, proc.stdout[-2500:])
        return {"pytest": lines}

    def db_init_idempotent(self) -> dict[str, Any]:
        outputs = []
        for _ in range(2):
            proc = compose("run", "--rm", "db-init", check=False, timeout=300)
            expect(proc.returncode == 0, proc.stderr[-800:])
            self.assert_no_secrets(proc.stdout + proc.stderr, "db-init output")
            outputs.append(proc.returncode)
        expect(self.api.get("/health/ready").status == 200)
        return {"db_init_exit_codes": outputs}

    def migrations_idempotent(self) -> dict[str, Any]:
        outputs = []
        for _ in range(2):
            proc = compose("run", "--rm", "migrate", check=False, timeout=300)
            expect(proc.returncode == 0, proc.stderr[-800:])
            self.assert_no_secrets(proc.stdout + proc.stderr, "migrate output")
            outputs.append(proc.stdout.strip().splitlines()[-1:])
        expect(all(o == outputs[0] for o in outputs), outputs)
        return {"migrate": outputs}

    def reconciliation_e2e(self) -> dict[str, Any]:
        """HTTP -> outbox -> JetStream -> worker -> results, compared with the v2 oracle."""
        integration = dev_auth.token("svc-smoke-ingest", ["integration"])
        analyst = dev_auth.token("ana-smoke", ["analyst"])
        auditor = dev_auth.token("aud-smoke", ["auditor"])
        root = ROOT / "datasets" / "synthetic" / "transactions-v2"
        files = {p.name: p.read_text(encoding="utf-8") for p in root.glob("*.csv")}
        receipts = []
        for name, source in (("internal_ledger.csv", "internal_ledger"),
                             ("provider_report.csv", "provider_report")):  # fmt: skip
            rows = list(csv.DictReader(io.StringIO(files[name])))
            for provider in ("prov-alfa", "prov-beta"):
                body = {
                    "source": source,
                    "provider_id": provider,
                    "idempotency_key": f"smoke-v2-{name}-{provider}",
                    "content": to_csv([r for r in rows if r["provider_id"] == provider]),
                }
                resp = self.api.get("/v1/artifacts", method="POST", body=body, token=integration)
                expect(resp.status in (200, 201), resp.text)
                receipts.append({k: resp.body[k] for k in ("accepted", "rejected", "replayed")})
        denied = self.api.get("/v1/artifacts", method="POST", body={}, token=analyst)
        expect(denied.status == 403, f"analyst must not ingest: {denied.status}")
        anonymous = self.api.get("/v1/batches/none")
        expect(anonymous.status == 401, f"anonymous read must be 401: {anonymous.status}")

        labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
        suffix = uuid.uuid4().hex[:8]
        runs: list[str] = []
        for batch in batches_for(labels):
            batch_id = f"smoke-{suffix}-{batch.batch_id}"
            body = {"batch_id": batch_id, "provider_id": batch.provider_id,
                    "merchant_account": batch.merchant_account, "currency": batch.currency,
                    "window_start": batch.window_start.isoformat(),
                    "window_end": batch.window_end.isoformat(),
                    "business_timezone": batch.business_timezone,
                    "cutoff_at": batch.cutoff_at.isoformat()}  # fmt: skip
            created = self.api.get("/v1/batches", method="POST", body=body, token=analyst)
            expect(created.status == 201, created.text)
            for source in ("internal_ledger", "provider_report"):
                done = self.api.get(f"/v1/batches/{batch_id}/sources/{source}/complete",
                                    method="POST", token=integration)  # fmt: skip
                expect(done.status == 200, done.text)
            run = self.api.get(f"/v1/batches/{batch_id}/runs", method="POST", token=analyst)
            expect(run.status == 202, run.text)
            runs.append(run.body["run_id"])
            self.runs[batch.batch_id] = run.body["run_id"]

        started = time.perf_counter()
        got: dict[str, tuple[str, str]] = {}
        for run_id in runs:
            while True:
                status = self.api.get(f"/v1/runs/{run_id}", token=auditor)
                expect(status.status == 200, status.text)
                if status.body["status"] == "completed":
                    break
                expect(status.body["status"] == "requested", status.text)
                expect(time.perf_counter() - started < 90, "runs not completed within 90s")
                time.sleep(0.5)
            page = self.api.get(f"/v1/runs/{run_id}/results?limit=500", token=auditor)
            for item in page.body["items"]:
                got[item["payment_ref"]] = (item["match_status"],
                                            ",".join(item["discrepancy_types"]))  # fmt: skip
        want = {r["payment_ref"]: (r["expected_match"], r["expected_discrepancies"])
                for r in labels}  # fmt: skip
        wrong = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
        expect(not wrong, f"oracle mismatches: {wrong}")
        return {
            "receipts": receipts,
            "runs": len(runs),
            "labelled_payments": len(want),
            "matching_oracle": len(want) - len(wrong),
            "seconds_until_all_runs_completed": round(time.perf_counter() - started, 2),
        }

    def investigation_e2e(self) -> dict[str, Any]:
        """HTTP request -> outbox -> JetStream -> investigator -> MCP (stdio) -> draft (M5)."""
        analyst = dev_auth.token("ana-smoke", ["analyst"])
        auditor = dev_auth.token("aud-smoke", ["auditor"])
        run_id = self.runs.get("b-prov-alfa-merchant-03-USD")
        expect(run_id is not None, "reconciliation_e2e must run first")
        page = self.api.get(f"/v1/runs/{run_id}/results?limit=500", token=auditor).body["items"]
        mismatch = next(i for i in page if "AMOUNT_MISMATCH" in i["discrepancy_types"])
        exact = next(i for i in page if i["match_status"] == "EXACT")
        started = time.perf_counter()
        outcomes: dict[str, Any] = {}
        for label, item in (("amount_mismatch", mismatch), ("exact", exact)):
            path = f"/v1/runs/{run_id}/results/{item['ordinal']}/investigations"
            first = self.api.get(path, method="POST", token=analyst)
            expect(first.status in (200, 202), first.text)
            again = self.api.get(path, method="POST", token=analyst)
            expect(again.status == 200 and not again.body["created"], again.text)
            expect(again.body["investigation_id"] == first.body["investigation_id"])
            inv = first.body["investigation_id"]
            while True:
                got = self.api.get(f"/v1/investigations/{inv}", token=auditor)
                expect(got.status == 200, got.text)
                if got.body["state"] in ("NOT_NEEDED", "DRAFTED", "ABSTAINED", "ESCALATED",
                                         "FAILED"):  # fmt: skip
                    break
                expect(time.perf_counter() - started < 120, "investigation did not finish")
                time.sleep(0.5)
            record = got.body["record"]
            outcomes[label] = {
                "state": got.body["state"],
                "tool_calls": record["budget"]["tool_calls"],
                "generative_calls": record["budget"]["generative_calls"],
                "tokens_estimated": record["budget"]["tokens"],
                "model": record["model"],
                "label": (record.get("draft") or {}).get("label"),
                "facts": len((record.get("draft") or {}).get("facts", [])),
                "hypotheses": len((record.get("draft") or {}).get("hypotheses", [])),
            }
        expect(outcomes["amount_mismatch"]["state"] == "DRAFTED", outcomes)
        expect(outcomes["amount_mismatch"]["label"] == "SIMULATED", outcomes)
        expect(outcomes["exact"]["state"] == "NOT_NEEDED", outcomes)
        expect(outcomes["exact"]["generative_calls"] == 0, outcomes)
        denied = self.api.get(
            f"/v1/runs/{run_id}/results/{mismatch['ordinal']}/investigations",
            method="POST",
            token=auditor,
        )
        expect(denied.status == 403, f"auditor must not request investigations: {denied.status}")
        outcomes["seconds"] = round(time.perf_counter() - started, 2)
        return outcomes

    def knowledge_ingest_idempotent(self) -> dict[str, Any]:
        outputs = []
        for _ in range(2):
            proc = compose("run", "--rm", "knowledge-ingest", check=False, timeout=300)
            expect(proc.returncode == 0, proc.stderr[-800:])
            outputs.append(json.loads(proc.stdout.strip().splitlines()[-1]))
        expect(outputs[-1]["published"] == 0, outputs)
        expect(outputs[-1]["unchanged"] == outputs[-1]["documents"], outputs)
        return {"runs": outputs}

    def retrieval_evaluation(self) -> dict[str, Any]:
        """MEASURED lexical/vector/hybrid baselines on the synthetic corpus (M3)."""
        proc = compose(
            "--profile", "smoke", "run", "--rm", "smoke", "python", "-m", "recon_knowledge",
            "evaluate", "--corpus", "datasets/synthetic/knowledge-v1",
            check=False, timeout=600,
        )  # fmt: skip
        expect(proc.returncode == 0, proc.stderr[-800:])
        report: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
        expect(report["split_leakage_families"] == [], report["split_leakage_families"])
        for mode, result in report["results"].items():
            expect(result["all"]["acl_violations"] == 0, f"{mode}: ACL violation")
        EVIDENCE_DIR.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        (EVIDENCE_DIR / f"retrieval-eval-{stamp}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {
            mode: {split: result[split] for split in ("dev", "holdout")}
            for mode, result in report["results"].items()
        } | {"config": report["config"], "report_file": f".smoke/retrieval-eval-{stamp}.json"}

    def isolation(self) -> dict[str, Any]:
        proc = compose("ps", "--format", "json")
        raw = proc.stdout.strip()
        items: list[dict[str, Any]] = (
            json.loads(raw) if raw.startswith("[") else [json.loads(x) for x in raw.splitlines()]
        )
        published: dict[str, list[str]] = {}
        for item in items:
            pubs = [p for p in item.get("Publishers") or [] if p.get("PublishedPort")]
            published[item["Service"]] = [f"{p['URL']}:{p['PublishedPort']}" for p in pubs]
        port = self.env.get("API_HOST_PORT", "18180")
        expect(published.get("api") == [f"127.0.0.1:{port}"], published)
        for service in ("postgres", "nats"):
            expect(published.get(service) == [], f"{service} publishes {published.get(service)}")

        net = subprocess.run(
            ["docker", "network", "inspect", f"{project()}_backend", "--format", "{{.Internal}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        expect(net == "true", "backend network must be internal")

        lan = _lan_ip()
        lan_reachable = None
        if lan:
            with socket.socket() as sock:
                sock.settimeout(2)
                lan_reachable = sock.connect_ex((lan, int(port))) == 0
            expect(not lan_reachable, f"API reachable on non-loopback address {lan}")
        return {"published": published, "backend_internal": True, "lan_ip_checked": bool(lan)}

    def correlation(self) -> dict[str, Any]:
        request_id = f"smoke-{uuid.uuid4().hex[:12]}"
        resp = self.api.get("/health/ready", request_id=request_id)
        expect(resp.headers["x-request-id"] == request_id)
        time.sleep(1)
        all_logs = compose("--profile", "smoke", "logs", "--no-log-prefix")
        self.assert_no_secrets(all_logs.stdout + all_logs.stderr, "service logs")
        logs = compose("logs", "api", "--no-log-prefix").stdout
        matches = []
        for line in logs.splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("request_id") == request_id:
                matches.append(entry)
        expect(len(matches) == 1, f"expected one access log for {request_id}, got {matches}")
        entry = matches[0]
        expect(entry["status"] == resp.status and entry["path"] == "/health/ready")
        expect(isinstance(entry["duration_ms"], (int, float)))
        return {"log_entry": entry}

    def degraded(self, service: str, action: str) -> dict[str, Any]:
        undo = {"stop": "start", "pause": "unpause"}[action]
        compose(action, service)
        try:
            samples = []
            for _ in range(3):
                ready = self.api.get("/health/ready", timeout=10)
                live = self.api.get("/health/live")
                samples.append(
                    (ready.status, round(ready.elapsed, 3), ready.body.get("checks"), live.status)
                )
                expect(ready.status == 503, ready.text)
                expect(ready.elapsed <= READY_DEADLINE, f"ready took {ready.elapsed:.2f}s")
                expect(live.status == 200)
                self.assert_no_secrets(ready.text, "degraded body")
                expect("Traceback" not in ready.text and "://" not in ready.text)
        finally:
            compose(undo, service)
        recovered = self.api.wait_status("/health/ready", 200, timeout=90)
        return {
            "samples": [
                {"ready": s, "seconds": t, "checks": c, "live": lv} for s, t, c, lv in samples
            ],
            "max_ready_seconds": max(t for _, t, _, _ in samples),
            "recovery_seconds": round(recovered, 2),
        }

    def persistence(self) -> dict[str, Any]:
        run_id = uuid.uuid4().hex[:12]
        module = "tests.integration.persistence"
        smoke_run = ("--profile", "smoke", "run", "--rm", "smoke", "python", "-m", module)
        volumes_before = _volumes()
        write = compose(*smoke_run, "write", run_id, check=False)
        if write.returncode != 0:
            compose(*smoke_run, "cleanup", run_id, check=False)
            raise SmokeFailure(write.stdout + write.stderr[-800:])
        try:
            compose("--profile", "smoke", "stop", timeout=300)
            expect(all(s != "running" for s in _states().values()), _states())
            compose("up", "-d", timeout=600)
            self.api.wait_status("/health/ready", 200)
            verify = compose(*smoke_run, "verify", run_id, check=False)
        except BaseException:
            compose(*smoke_run, "cleanup", run_id, check=False)
            raise
        expect(verify.returncode == 0, verify.stdout + verify.stderr[-800:])
        expect(_volumes() == volumes_before, "named volumes changed across stop/start")
        return {
            "write": json.loads(write.stdout.strip().splitlines()[-1]),
            "verify": json.loads(verify.stdout.strip().splitlines()[-1]),
            "volumes": volumes_before,
        }


@functools.cache
def project() -> str:
    """Effective Compose project name (COMPOSE_PROJECT_NAME overrides compose.yaml)."""
    name: str = json.loads(compose("config", "--format", "json").stdout)["name"]
    return name


def _states() -> dict[str, str]:
    proc = compose("--profile", "smoke", "ps", "-a", "--format", "{{.Service}}={{.State}}")
    return dict(line.split("=", 1) for line in proc.stdout.split() if "=" in line)


def _volumes() -> dict[str, str]:
    names = [f"{project()}_pgdata", f"{project()}_natsdata"]
    proc = subprocess.run(
        ["docker", "volume", "inspect", *names, "--format", "{{.Name}}={{.CreatedAt}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            ip: str = sock.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def _cmd(*args: str) -> str:
    proc = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, check=False)
    return proc.stdout.strip() or proc.stderr.strip()


@contextmanager
def evidence(results: list[Result]) -> Iterator[None]:
    started = datetime.now(UTC)
    try:
        yield
    finally:
        EVIDENCE_DIR.mkdir(exist_ok=True)
        report = {
            "kind": "MEASURED",
            "scope": "local Compose smoke of M0 infrastructure; not a performance benchmark",
            "started_utc": started.isoformat(timespec="seconds"),
            "commit": _cmd("git", "rev-parse", "--short", "HEAD"),
            "dirty": bool(_cmd("git", "status", "--porcelain")),
            "host": f"{platform.system()} {platform.release()} {platform.machine()}",
            "docker": _cmd(
                "docker",
                "version",
                "--format",
                "{{.Server.Os}}/{{.Server.Arch}} {{.Server.Version}}",
            ),
            "compose": _cmd("docker", "compose", "version", "--short"),
            "images": _cmd("docker", "compose", "--profile", "smoke", "config", "--images"),
            "results": [r.__dict__ for r in results],
        }
        path = EVIDENCE_DIR / f"smoke-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"evidence: {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--down", action="store_true", help="docker compose down at the end (keeps volumes)"
    )
    args = parser.parse_args()

    try:
        env = load_env()
    except SmokeFailure as exc:
        print(f"[FAIL] preflight: {exc}")
        return 1

    smoke = Smoke(env)
    with evidence(smoke.results):
        smoke.check("T03", "startup: compose up, API ready", smoke.startup)
        if not smoke.results[-1].ok:
            return 1
        smoke.check("T05", "healthy live/ready contract from host", smoke.healthy_contract)
        smoke.check("T03", "vector + JetStream + role + readiness integration", smoke.infra_tests)
        smoke.check("T03", "db-init idempotent re-run", smoke.db_init_idempotent)
        smoke.check("M1-T08", "alembic migrate idempotent re-run", smoke.migrations_idempotent)
        smoke.check(
            "M2-T07", "HTTP ingest + runs via outbox/NATS/worker match oracle",
            smoke.reconciliation_e2e,
        )  # fmt: skip
        smoke.check(
            "M3-T04", "knowledge-ingest idempotent re-run", smoke.knowledge_ingest_idempotent
        )
        smoke.check(
            "M5-T09", "HTTP investigation via outbox/NATS/investigator/MCP", smoke.investigation_e2e
        )
        smoke.check(
            "M3-T07", "retrieval evaluation (MEASURED, synthetic)", smoke.retrieval_evaluation
        )
        smoke.check("T08", "API loopback-only, dependencies private", smoke.isolation)
        smoke.check("T09", "request ID correlated in header and JSON log", smoke.correlation)
        for service in ("postgres", "nats"):
            for action in ("stop", "pause"):
                smoke.check(
                    "T06",
                    f"{service} {action}: ready 503 <= 3s, live 200, recovery",
                    functools.partial(smoke.degraded, service, action),
                )
        smoke.check("T04", "marker and pending message survive stop/start", smoke.persistence)
        compose("--profile", "smoke", "rm", "-sf", "nats-nojs", check=False)
        if args.down:
            compose("down", timeout=300)

    failed = [r for r in smoke.results if not r.ok]
    print(f"smoke: {len(smoke.results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
