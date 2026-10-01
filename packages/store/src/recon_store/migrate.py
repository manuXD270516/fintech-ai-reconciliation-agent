"""Run Alembic migrations with the bootstrap role; grant least privilege to the runtime role.

Usage (inside the Compose `migrate` job): python -m recon_store.migrate
Environment: MIGRATE_DB_HOST, MIGRATE_DB_PORT, MIGRATE_DB_NAME, MIGRATE_DB_USER,
MIGRATE_DB_PASSWORD and APP_DB_USER (runtime role that receives grants).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import URL, create_engine

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def database_url(env: dict[str, str], prefix: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=env[f"{prefix}USER"],
        password=env[f"{prefix}PASSWORD"],
        host=env[f"{prefix}HOST"],
        port=int(env.get(f"{prefix}PORT", "5432")),
        database=env[f"{prefix}NAME"],
    )


def alembic_config(url: URL, runtime_role: str, mcp_role: str = "recon_mcp") -> Config:
    for role in (runtime_role, mcp_role):
        if not _ROLE.fullmatch(role):
            raise ValueError("roles must be lowercase SQL identifiers")
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["url"] = url
    cfg.attributes["runtime_role"] = runtime_role
    cfg.attributes["mcp_role"] = mcp_role
    return cfg


def upgrade(
    url: URL, runtime_role: str, revision: str = "head", mcp_role: str = "recon_mcp"
) -> None:
    command.upgrade(alembic_config(url, runtime_role, mcp_role), revision)


def current_revision(url: URL) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(
                conn, opts={"version_table_schema": "recon"}
            ).get_current_revision()
    finally:
        engine.dispose()


def main() -> int:
    env = dict(os.environ)
    try:
        url = database_url(env, "MIGRATE_DB_")
        role = env["APP_DB_USER"]
        mcp_role = env["MCP_DB_USER"]
    except KeyError as exc:
        print(f"migrate: missing environment variable {exc.args[0]}", file=sys.stderr)
        return 2
    upgrade(url, role, mcp_role=mcp_role)
    print(f"migrate ok: revision {current_revision(url)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
