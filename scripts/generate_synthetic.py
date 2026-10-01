"""Write the versioned synthetic transaction datasets.

Usage: uv run python scripts/generate_synthetic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from recon_domain.synthetic import LABEL_VERSIONS, generate, manifest_json

DATASETS = Path(__file__).resolve().parent.parent / "datasets" / "synthetic"


def main() -> int:
    for version in LABEL_VERSIONS:
        ds = generate(version=version)
        out = DATASETS / f"transactions-{version}"
        out.mkdir(parents=True, exist_ok=True)
        for name, text in ds.files().items():
            (out / name).write_text(text, encoding="utf-8", newline="\n")
        (out / "manifest.json").write_text(manifest_json(ds), encoding="utf-8", newline="\n")
        print(f"wrote {out} ({ds.manifest()['content_hash']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
