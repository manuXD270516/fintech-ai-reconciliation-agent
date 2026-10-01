from __future__ import annotations

import asyncio
import json
import signal
import sys

import nats

from recon_api.config import ConfigurationError, load_settings
from recon_api.logs import configure_logging
from recon_investigator.runner import Runner
from recon_store.engine import runtime_engine, runtime_url


async def _main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        fields = [f for f, _ in exc.problems]
        print(json.dumps({"error": "invalid configuration", "fields": fields}), file=sys.stderr)
        return 2
    configure_logging(settings.log_level)
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
    runner = Runner(engine, nc)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, runner.stop.set)
        except NotImplementedError:
            pass
    try:
        await runner.run()
    finally:
        await nc.drain()
        engine.dispose()
    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
