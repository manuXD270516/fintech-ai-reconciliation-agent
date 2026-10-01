"""Local operations helper (M9). Only touches this repository's Compose project.

    uv run python scripts/ops.py alerts [--url URL] [--json] [--fail-on critical|warning]
    uv run python scripts/ops.py backup  --out .backups/recon.dump
    uv run python scripts/ops.py restore-check --dump .backups/recon.dump [--json]

`backup` runs pg_dump inside the `postgres` service (custom format, schema `recon`).
`restore-check` restores the dump into a scratch database `recon_restore_check` in the
same container, compares row counts and an audit-trail digest with the live database,
reports the elapsed restore time and drops the scratch database. The live database is
never modified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from recon_api.alerts import evaluate, firing, load_rules  # noqa: E402

RULES = ROOT / "infra/observability/alerts.toml"
DEFAULT_URL = "http://127.0.0.1:18180/metrics"
SCRATCH_DB = "recon_restore_check"
TABLES = (
    "transaction_observations",
    "audit_entries",
    "outbox",
    "inbox",
    "source_artifacts",
    "ingestion_rejections",
    "reconciliation_batches",
    "reconciliation_runs",
    "match_results",
    "knowledge_documents",
    "knowledge_chunks",
    "investigations",
    "cases",
    "recommendations",
    "decisions",
)
# Digest of the append-only audit trail: any lost or altered row changes it.
AUDIT_DIGEST_SQL = (
    "SELECT md5(coalesce(string_agg(md5(row(a.*)::text), '' ORDER BY a.id), '')) "
    "FROM recon.audit_entries a"
)


def compose(*args: str, stdin: bytes | None = None, check: bool = True) -> bytes:
    result = subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, input=stdin, capture_output=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace")[-2000:])
    return result.stdout


def psql(db: str, sql: str) -> str:
    out = compose(
        "exec", "-T", "postgres", "sh", "-c",
        f'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d {db} -c "{sql}"',
    )  # fmt: skip
    return out.decode().strip()


def live_db() -> str:
    return compose("exec", "-T", "postgres", "sh", "-c", 'printf %s "$POSTGRES_DB"').decode()


def counts(db: str) -> dict[str, int]:
    # Table names come from the fixed TABLES constant, never from input.
    union = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM recon.{t}" for t in TABLES)  # noqa: S608
    rows = psql(db, union).splitlines()
    return {name: int(n) for name, n in (r.split("|") for r in rows)}


def cmd_alerts(args: argparse.Namespace) -> int:
    with urllib.request.urlopen(args.url, timeout=10) as response:  # noqa: S310 - local URL
        exposition = response.read().decode()
    alerts = evaluate(exposition, load_rules(Path(args.rules)))
    active = firing(alerts)
    if args.json:
        print(json.dumps({"alerts": [a.as_dict() for a in alerts]}, indent=2))
    else:
        for alert in alerts:
            state = "FIRING" if alert.firing else "ok"
            print(f"{state:7} {alert.severity:8} {alert.rule:30} value={alert.value} "
                  f"{dict(alert.labels)}")  # fmt: skip
    levels = {"critical": ("critical",), "warning": ("critical", "warning")}
    if args.fail_on and any(a.severity in levels[args.fail_on] for a in active):
        return 1
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    dump = compose(
        "exec", "-T", "postgres", "sh", "-c",
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --schema=recon',
    )  # fmt: skip
    out.write_bytes(dump)
    report = {
        "dump": str(out),
        "bytes": len(dump),
        "seconds": round(time.perf_counter() - started, 2),
        "counts": counts(live_db()),
        "audit_digest": psql(live_db(), AUDIT_DIGEST_SQL),
    }
    out.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def cmd_restore_check(args: argparse.Namespace) -> int:
    dump = Path(args.dump)
    expected = json.loads(dump.with_suffix(".json").read_text(encoding="utf-8"))
    psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    psql("postgres", f"CREATE DATABASE {SCRATCH_DB}")
    try:
        started = time.perf_counter()
        psql(SCRATCH_DB, "CREATE EXTENSION IF NOT EXISTS vector")
        compose(
            "exec", "-T", "postgres", "sh", "-c",
            f'pg_restore -U "$POSTGRES_USER" -d {SCRATCH_DB} --no-owner --no-privileges '
            "--exit-on-error",
            stdin=dump.read_bytes(),
        )  # fmt: skip
        restore_seconds = round(time.perf_counter() - started, 2)
        restored = counts(SCRATCH_DB)
        digest = psql(SCRATCH_DB, AUDIT_DIGEST_SQL)
    finally:
        psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    live_now = counts(live_db())
    report = {
        "restore_seconds": restore_seconds,
        "counts_match_backup": restored == expected["counts"],
        "audit_digest_match_backup": digest == expected["audit_digest"],
        "restored_counts": restored,
        "rows_written_after_backup": {
            t: live_now[t] - expected["counts"][t]
            for t in TABLES
            if live_now[t] != expected["counts"][t]
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if report["counts_match_backup"] and report["audit_digest_match_backup"] else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    alerts = sub.add_parser("alerts")
    alerts.add_argument("--url", default=DEFAULT_URL)
    alerts.add_argument("--rules", default=str(RULES))
    alerts.add_argument("--json", action="store_true")
    alerts.add_argument("--fail-on", choices=["critical", "warning"])
    backup = sub.add_parser("backup")
    backup.add_argument("--out", default=".backups/recon.dump")
    restore = sub.add_parser("restore-check")
    restore.add_argument("--dump", default=".backups/recon.dump")
    args = parser.parse_args(argv)
    handler = {"alerts": cmd_alerts, "backup": cmd_backup, "restore-check": cmd_restore_check}
    return handler[args.command](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
