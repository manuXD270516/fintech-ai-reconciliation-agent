"""Export the API's OpenAPI document for the web client generator (M8).

Usage: uv run python scripts/export_openapi.py   (writes apps/web/openapi.json)

`tests/unit/test_openapi_contract.py` fails if the committed file drifts from the app, and
the web check regenerates `src/api/schema.d.ts` from it with `openapi-typescript --check`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from recon_api.app import create_app
from recon_api.readiness import ReadinessChecker

TARGET = Path(__file__).resolve().parent.parent / "apps" / "web" / "openapi.json"


def document() -> dict[str, Any]:
    spec: dict[str, Any] = create_app(checker=ReadinessChecker([], 1.0)).openapi()
    return spec


def render() -> str:
    return json.dumps(document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
