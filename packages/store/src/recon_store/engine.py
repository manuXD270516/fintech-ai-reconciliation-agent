"""Engine factory for the restricted runtime role.

`public` follows `recon` only to resolve the pgvector type and operators; nobody can
create objects in `public` (db-init revokes CREATE), so it cannot shadow `recon`.
"""

from __future__ import annotations

from sqlalchemy import URL, Engine, create_engine


def runtime_url(host: str, port: int, database: str, user: str, password: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )


def runtime_engine(url: URL, pool_size: int = 5) -> Engine:
    return create_engine(
        url,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c search_path=recon,public"},
    )
