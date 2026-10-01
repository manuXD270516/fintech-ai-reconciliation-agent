from __future__ import annotations

import asyncio
import json
import signal
import sys

import nats

from recon_api.config import ConfigurationError, load_settings
from recon_api.logs import configure_logging
from recon_store import telemetry
from recon_store.engine import runtime_engine, runtime_url
from recon_worker.runner import Worker

EXIT_INVALID_CONFIG = 2


async def _main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(
            json.dumps(
                {
                    "level": "ERROR",
                    "logger": "recon_worker.config",
                    "message": "invalid configuration; refusing to start",
                    "fields": [f for f, _ in exc.problems],
                }
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_CONFIG
    configure_logging(settings.log_level)
    telemetry.configure("recon-worker")
    engine = runtime_engine(
        runtime_url(
            settings.db_host,
            settings.db_port,
            settings.db_name,
            settings.db_user,
            settings.db_password.get_secret_value(),
        )
    )
    nc = await nats.connect(
        servers=[settings.nats_url],
        user=settings.nats_user,
        password=settings.nats_password.get_secret_value(),
        connect_timeout=5,
        max_reconnect_attempts=-1,
    )
    worker = Worker(engine, nc)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop.set)
        except NotImplementedError:
            pass
    try:
        await worker.run()
    finally:
        await nc.drain()
        engine.dispose()
        telemetry.shutdown()
    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
