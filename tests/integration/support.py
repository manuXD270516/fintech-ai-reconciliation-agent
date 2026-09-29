"""Helpers for tests that run inside the Compose `smoke` container (internal network)."""

from __future__ import annotations

import os
import uuid

import nats
import psycopg
from nats.aio.client import Client as NatsClient

from recon_api.config import Settings, load_settings


def new_run_id() -> str:
    return uuid.uuid4().hex[:10]


def settings() -> Settings:
    return load_settings()


def admin_connect(dbname: str | None = None) -> psycopg.Connection[tuple[object, ...]]:
    s = settings()
    return psycopg.connect(
        host=s.db_host,
        port=s.db_port,
        dbname=dbname or s.db_name,
        user=os.environ["SMOKE_PG_ADMIN_USER"],
        password=os.environ["SMOKE_PG_ADMIN_PASSWORD"],
        autocommit=True,
        connect_timeout=5,
    )


def app_connect(s: Settings | None = None) -> psycopg.Connection[tuple[object, ...]]:
    s = s or settings()
    return psycopg.connect(
        host=s.db_host,
        port=s.db_port,
        dbname=s.db_name,
        user=s.db_user,
        password=s.db_password.get_secret_value(),
        autocommit=True,
        connect_timeout=5,
    )


async def nats_connect(url: str | None = None) -> NatsClient:
    s = settings()
    return await nats.connect(
        servers=[url or s.nats_url],
        user=s.nats_user,
        password=s.nats_password.get_secret_value(),
        connect_timeout=5,
        allow_reconnect=False,
        max_reconnect_attempts=0,
    )
