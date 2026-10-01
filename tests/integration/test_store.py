"""M1 T07/T08: real PostgreSQL persistence of observations (runs in the smoke container)."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from dataclasses import replace

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, Table, create_engine, func, select

from recon_domain.observation import SourceKind, canonical_hash
from recon_domain.revisions import IngestOutcome
from recon_store.engine import runtime_engine, runtime_url
from recon_store.migrate import database_url
from recon_store.observations import ObservationStore, to_row
from recon_store.tables import audit_entries, metadata, observations, outbox

from ..unit.domain_support import observation
from .support import app_connect, new_run_id, settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    s = settings()
    eng = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    yield eng
    eng.dispose()


@pytest.fixture
def tenant() -> str:
    return f"tenant-it-{new_run_id()}"


def _count(engine: Engine, table: Table, tenant: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(func.count()).select_from(table).where(table.c.tenant_id == tenant)
            ).scalar_one()
        )


def test_schema_matches_sqlalchemy_metadata() -> None:
    s = settings()
    env = {
        "MIGRATE_DB_USER": os.environ["SMOKE_PG_ADMIN_USER"],
        "MIGRATE_DB_PASSWORD": os.environ["SMOKE_PG_ADMIN_PASSWORD"],
        "MIGRATE_DB_HOST": s.db_host,
        "MIGRATE_DB_PORT": str(s.db_port),
        "MIGRATE_DB_NAME": s.db_name,
    }
    eng = create_engine(database_url(env, "MIGRATE_DB_"))
    try:
        with eng.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "include_schemas": True,
                    "version_table_schema": "recon",
                    "include_name": lambda name, kind, _parent: kind != "schema" or name == "recon",
                },
            )
            diff = compare_metadata(ctx, metadata)
    finally:
        eng.dispose()
    assert diff == []


def test_ingest_outcomes_and_effects(engine: Engine, tenant: str) -> None:
    store = ObservationStore(engine)
    obs = observation(tenant_id=tenant)
    first = store.ingest(obs, actor="it", correlation_id="corr-1")
    replay = store.ingest(obs, actor="it", correlation_id="corr-2")
    conflict = store.ingest(
        replace(obs, raw_hash=canonical_hash({"other": 1})), actor="it", correlation_id="corr-3"
    )
    revised = store.ingest(
        replace(obs, revision=3, raw_hash=canonical_hash({"r": 3})),
        actor="it",
        correlation_id="corr-4",
    )
    stale = store.ingest(
        replace(obs, revision=2, raw_hash=canonical_hash({"r": 2})),
        actor="it",
        correlation_id="corr-5",
    )
    assert first.outcome is IngestOutcome.CREATED
    assert (
        replay.outcome is IngestOutcome.DUPLICATE and replay.observation_id == first.observation_id
    )
    assert conflict.outcome is IngestOutcome.CONFLICT and conflict.observation_id is None
    assert revised.outcome is IngestOutcome.NEW_REVISION and revised.current_revision == 3
    assert stale.outcome is IngestOutcome.STALE_REVISION and stale.current_revision == 3

    history = store.history(obs.key)
    assert [o.revision for o in history] == [1, 2, 3]
    assert history[0] == obs
    assert _count(engine, observations, tenant) == 3
    # Replay adds nothing; conflict is audited but emits no event.
    assert _count(engine, outbox, tenant) == 3
    assert _count(engine, audit_entries, tenant) == 4


def test_failed_transaction_leaves_no_partial_effects(engine: Engine, tenant: str) -> None:
    store = ObservationStore(engine)

    class Boom(Exception):
        pass

    with pytest.raises(Boom), engine.begin() as conn:
        store.ingest_in(conn, observation(tenant_id=tenant), actor="it", correlation_id="c")
        raise Boom
    for table in (observations, audit_entries, outbox):
        assert _count(engine, table, tenant) == 0


def test_concurrent_ingest_of_same_key_creates_one_row(engine: Engine, tenant: str) -> None:
    store = ObservationStore(engine)
    obs = observation(tenant_id=tenant, source=SourceKind.PROVIDER_REPORT)
    outcomes: list[IngestOutcome] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        barrier.wait()
        outcomes.append(store.ingest(obs, actor="it", correlation_id="c").outcome)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == sorted([IngestOutcome.CREATED] + [IngestOutcome.DUPLICATE] * 3)
    assert _count(engine, observations, tenant) == 1


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE recon.transaction_observations SET amount_minor = 1 WHERE false",
        "DELETE FROM recon.transaction_observations WHERE false",
        "DELETE FROM recon.audit_entries WHERE false",
        "UPDATE recon.audit_entries SET outcome = 'x' WHERE false",
        "UPDATE recon.outbox SET payload = '{}' WHERE false",
        "CREATE TABLE recon.intruder (id int)",
        # M2 (0002): artifacts, quarantine, results and inbox are append-only for runtime.
        "UPDATE recon.source_artifacts SET accepted = 0 WHERE false",
        "DELETE FROM recon.ingestion_rejections WHERE false",
        "UPDATE recon.match_results SET match_status = 'EXACT' WHERE false",
        "DELETE FROM recon.match_results WHERE false",
        "UPDATE recon.reconciliation_runs SET ruleset_version = 'x' WHERE false",
        "DELETE FROM recon.reconciliation_runs WHERE false",
        "DELETE FROM recon.inbox WHERE false",
    ],
)
def test_runtime_role_cannot_rewrite_history(statement: str) -> None:
    with app_connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)


def test_database_rejects_invalid_rows(engine: Engine, tenant: str) -> None:
    row = to_row(observation(tenant_id=tenant)) | {"revision": 0}
    with pytest.raises(Exception, match="ck_observation_revision_positive"):
        with engine.begin() as conn:
            conn.execute(observations.insert().values(**row))
