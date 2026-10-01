"""M9: the history secret scanner recognises each pattern it claims (canaries built at
runtime so this file never contains a matching literal)."""

from __future__ import annotations

import pytest
from scripts.check_scope import TREE_ONLY_PATTERNS
from scripts.secret_scan import FORBIDDEN_PATHS, PATTERNS

A = "A" * 24
CANARIES = {
    "Anthropic key": "sk-" + "ant-" + A,
    "Google API key": "AI" + "za" + "B" * 35,
    "Stripe live key": "sk" + "_live_" + "C" * 20,
    "JSON Web Token": "ey" + "J" + "a" * 12 + ".ey" + "J" + "b" * 12 + ".sig",
    "credential in URL": "postgres" + "://user:" + "s3cr3tvalue" + "@db:5432/x",
    "AWS access key": "AK" + "IA" + "Q" * 16,
    "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
}


@pytest.mark.parametrize(("label", "canary"), sorted(CANARIES.items()))
def test_each_pattern_detects_its_canary(label: str, canary: str) -> None:
    assert PATTERNS[label].search(f"value = {canary!r}")


def test_placeholders_and_env_interpolation_are_not_findings() -> None:
    benign = [
        "APP_DB_PASSWORD=dev-only-app-password",
        "nats://nats:4222",
        "postgresql+psycopg://${USER}:${PASSWORD}@postgres/db",
        "Authorization: Bearer <JWT>",
    ]
    assert not [b for b in benign for p in PATTERNS.values() if p.search(b)]


@pytest.mark.parametrize(
    ("text", "found"),
    [("C:" + "\\Users\\" + "Jane Doe\\AppData", True),
     ("file:///C:" + "/Users/" + "Jane%20Doe/x", True),
     ("/ho" + "me/jane/repo", True), ("C:\\Users\\<user>\\AppData", False),
     ("/home/runner/work", False), ("D:\\projects\\repo", False)],
)  # fmt: skip
def test_local_home_paths_are_flagged_in_the_tree(text: str, found: bool) -> None:
    assert bool(TREE_ONLY_PATTERNS["local home path"].search(text)) is found


@pytest.mark.parametrize(
    ("path", "forbidden"),
    [(".env", True), (".env.local", True), (".env.example", False),
     (".dev-keys/private.pem", True), (".backups/recon.dump", True), ("docs/.env.md", False)],
)  # fmt: skip
def test_forbidden_paths(path: str, forbidden: bool) -> None:
    assert bool(FORBIDDEN_PATHS.match(path)) is forbidden
