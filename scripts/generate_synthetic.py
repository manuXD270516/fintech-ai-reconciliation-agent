"""Write the versioned synthetic transaction dataset (M1 fixtures).

Usage: uv run python scripts/generate_synthetic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from recon_domain.synthetic import generate, manifest_json

OUT = Path(__file__).resolve().parent.parent / "datasets" / "synthetic" / "transactions-v1"


def main() -> int:
    ds = generate()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in ds.files().items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    (OUT / "manifest.json").write_text(manifest_json(ds), encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({ds.manifest()['content_hash']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
