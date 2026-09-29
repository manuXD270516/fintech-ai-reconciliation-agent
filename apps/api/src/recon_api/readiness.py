from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Sequence
from typing import Literal, Protocol

import nats
import psycopg
from nats.errors import Error as NatsError
from nats.js.errors import Error as JetStreamError

from recon_api.config import Settings

CheckStatus = Literal["ok", "fail", "timeout"]
CHECK_NAMES: tuple[str, ...] = ("database", "vector", "messaging")

logger = logging.getLogger("recon_api.readiness")


class Probe(Protocol):
    """Checks one dependency and reports every capability it covers."""

    name: str
    covers: tuple[str, ...]

    async def run(self) -> dict[str, CheckStatus]: ...


class PostgresProbe:
    """Lightweight query plus a vector distance on literals. Never writes."""

    name: str = "postgres"
    covers: tuple[str, ...] = ("database", "vector")

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self) -> dict[str, CheckStatus]:
        s = self._settings
        timeout_ms = int(s.ready_timeout_seconds * 1000)
        conn = await psycopg.AsyncConnection.connect(
            host=s.db_host,
            port=s.db_port,
            dbname=s.db_name,
            user=s.db_user,
            password=s.db_password.get_secret_value(),
            connect_timeout=max(2, math.ceil(s.ready_timeout_seconds)),
            application_name="recon-api-readiness",
            options=f"-c statement_timeout={timeout_ms}",
            autocommit=True,
        )
        async with conn:
            await conn.execute("SELECT 1")
            try:
                cur = await conn.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
                row = await cur.fetchone()
            except psycopg.Error as exc:
                logger.warning("vector capability unavailable", extra={"fields": _exc(exc)})
                return {"database": "ok", "vector": "fail"}
        vector: CheckStatus = "ok" if row is not None and float(row[0]) == 1.0 else "fail"
        return {"database": "ok", "vector": vector}


class NatsJetStreamProbe:
    """Connects and queries JetStream account info. Never publishes."""

    name: str = "nats"
    covers: tuple[str, ...] = ("messaging",)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self) -> dict[str, CheckStatus]:
        s = self._settings

        async def _silence(_: Exception) -> None:
            return None

        nc = await nats.connect(
            servers=[s.nats_url],
            user=s.nats_user,
            password=s.nats_password.get_secret_value(),
            name="recon-api-readiness",
            connect_timeout=s.ready_timeout_seconds,
            allow_reconnect=False,
            max_reconnect_attempts=0,
            error_cb=_silence,
        )
        try:
            await nc.jetstream(timeout=s.ready_timeout_seconds).account_info()
        except (NatsError, JetStreamError) as exc:
            logger.warning("jetstream capability unavailable", extra={"fields": _exc(exc)})
            return {"messaging": "fail"}
        finally:
            await nc.close()
        return {"messaging": "ok"}


def _exc(exc: BaseException) -> dict[str, str]:
    return {"exc_type": type(exc).__name__}


class ReadinessChecker:
    """Runs probes concurrently under one global deadline.

    The deadline is enforced with asyncio.wait, so a probe that ignores cancellation
    cannot delay the response; unfinished probes are cancelled in the background.
    """

    def __init__(self, probes: Sequence[Probe], deadline_seconds: float) -> None:
        self._probes = list(probes)
        self._deadline = deadline_seconds
        self._background: set[asyncio.Task[dict[str, CheckStatus]]] = set()

    @classmethod
    def from_settings(cls, settings: Settings) -> ReadinessChecker:
        return cls(
            [PostgresProbe(settings), NatsJetStreamProbe(settings)],
            settings.ready_timeout_seconds,
        )

    async def check(self) -> dict[str, CheckStatus]:
        results: dict[str, CheckStatus] = dict.fromkeys(CHECK_NAMES, "fail")
        tasks = {asyncio.create_task(probe.run()): probe for probe in self._probes}
        done, pending = await asyncio.wait(tasks, timeout=self._deadline)

        for task in done:
            probe = tasks[task]
            exc = task.exception()
            if exc is None:
                results.update({k: v for k, v in task.result().items() if k in probe.covers})
            else:
                logger.warning("probe failed", extra={"fields": {"probe": probe.name, **_exc(exc)}})
                results.update(dict.fromkeys(probe.covers, "fail"))

        for task in pending:
            probe = tasks[task]
            logger.warning("probe timed out", extra={"fields": {"probe": probe.name}})
            results.update(dict.fromkeys(probe.covers, "timeout"))
            task.cancel()
            self._background.add(task)
            task.add_done_callback(self._forget)

        return results

    def _forget(self, task: asyncio.Task[dict[str, CheckStatus]]) -> None:
        self._background.discard(task)
        if not task.cancelled():
            task.exception()
