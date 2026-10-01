from __future__ import annotations

import json
import sys

import uvicorn

from recon_api.app import create_app
from recon_api.config import ConfigurationError, load_settings
from recon_api.logs import configure_logging
from recon_store import telemetry

EXIT_INVALID_CONFIG = 2


def main() -> int:
    try:
        settings = load_settings()
        if not settings.auth_jwks_file.is_file():
            raise ConfigurationError(
                [("APP_AUTH_JWKS_FILE", "JWKS file not found; run scripts/dev_auth.py init")]
            )
    except ConfigurationError as exc:
        error = {
            "level": "ERROR",
            "logger": "recon_api.config",
            "message": "invalid configuration; refusing to start",
            "fields": [{"field": field, "problem": problem} for field, problem in exc.problems],
        }
        print(json.dumps(error, ensure_ascii=True), file=sys.stderr)
        return EXIT_INVALID_CONFIG

    configure_logging(settings.log_level)
    telemetry.configure("recon-api")
    uvicorn.run(
        create_app(settings),
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,
        access_log=False,
        server_header=False,
    )
    telemetry.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
