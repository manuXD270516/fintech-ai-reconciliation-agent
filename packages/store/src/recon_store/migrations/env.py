from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, text

from recon_store.tables import SCHEMA, metadata

config = context.config


def run_migrations_online() -> None:
    engine = create_engine(config.attributes["url"])
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
            context.configure(
                connection=connection,
                target_metadata=metadata,
                version_table_schema=SCHEMA,
                include_schemas=True,
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not supported")
run_migrations_online()
