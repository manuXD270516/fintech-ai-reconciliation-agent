"""Local development identity provider: RS256 key pair, JWKS and signed tokens.

Keys live in `.dev-keys/` (git-ignored) and are for loopback use only. Only
`.dev-keys/public/jwks.json` is mounted into the API container.

Usage:
    uv run python scripts/dev_auth.py init
    uv run python scripts/dev_auth.py token --sub ana --role analyst [--tenant tenant-demo]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent
KEY_DIR = ROOT / ".dev-keys"
ISSUER = "recon-dev-idp"
AUDIENCE = "recon-api"
ROLES = ("analyst", "supervisor", "auditor", "integration")


def init(key_dir: Path = KEY_DIR, force: bool = False) -> str:
    private_path, jwks_path = key_dir / "private.pem", key_dir / "public" / "jwks.json"
    if private_path.exists() and jwks_path.exists() and not force:
        return json.loads(jwks_path.read_text(encoding="utf-8"))["keys"][0]["kid"]  # type: ignore[no-any-return]
    jwks_path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = f"dev-{uuid.uuid4().hex[:12]}"
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    jwk: dict[str, Any] = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk |= {"kid": kid, "use": "sig", "alg": "RS256"}
    jwks_path.write_text(json.dumps({"keys": [jwk]}, indent=2), encoding="utf-8")
    return kid


def token(
    sub: str,
    roles: list[str],
    tenant: str = "tenant-demo",
    ttl: int = 3600,
    key_dir: Path = KEY_DIR,
) -> str:
    kid = init(key_dir)
    private = (key_dir / "private.pem").read_bytes()
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": sub, "tenant_id": tenant, "roles": roles,
              "iat": now, "nbf": now, "exp": now + ttl}  # fmt: skip
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": kid})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--force", action="store_true")
    p_tok = sub.add_parser("token")
    p_tok.add_argument("--sub", required=True)
    p_tok.add_argument("--role", action="append", choices=ROLES, required=True)
    p_tok.add_argument("--tenant", default="tenant-demo")
    p_tok.add_argument("--ttl", type=int, default=3600)
    args = parser.parse_args(argv)
    if args.cmd == "init":
        print(f"dev keys ready in {KEY_DIR.relative_to(ROOT)} (kid {init(force=args.force)})")
    else:
        print(token(args.sub, args.role, args.tenant, args.ttl))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
