"""M1 T02: observation invariants, scoped identifiers and dual timestamps."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from recon_domain.money import Money
from recon_domain.observation import (
    DomainError,
    DualTime,
    OperationType,
    ScopedRef,
    SourceKind,
    canonical_hash,
    comparable,
)

from .domain_support import observation

DOMAIN_SRC = Path(__file__).resolve().parents[2] / "packages" / "domain" / "src" / "recon_domain"


def test_valid_observation_is_immutable() -> None:
    obs = observation()
    with pytest.raises(FrozenInstanceError):
        obs.revision = 2  # type: ignore[misc]


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(DomainError, match="naive"):
        DualTime.from_aware(datetime(2026, 9, 1, 8, 0))
    with pytest.raises(DomainError, match="RFC 3339"):
        DualTime.parse("not-a-date")


def test_dual_time_keeps_original_offset_and_utc() -> None:
    value = DualTime.parse("2026-09-01T20:30:00-04:00")
    assert value.utc == datetime(2026, 9, 2, 0, 30, tzinfo=UTC)
    assert value.offset_minutes == -240
    assert DualTime.parse("2026-09-01T20:30:00+05:45").offset_minutes == 345


@pytest.mark.parametrize(
    "overrides",
    [
        {"revision": 0},
        {"revision": True},
        {"tenant_id": ""},
        {"payment_ref": "has space"},
        {"provider_id": "x" * 200},
        {"raw_hash": "ABC"},
        {"attempt_ref": "bad/ref"},
        {"source": "internal_ledger"},
    ],
)
def test_invalid_fields_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(DomainError):
        observation(**overrides)


def test_references_are_scoped_by_provider_and_account() -> None:
    a = observation()
    other_account = observation(merchant_account="merchant-02")
    assert a.reference == ScopedRef("prov-alfa", "merchant-01", "pay-0001")
    assert a.reference != other_account.reference


def test_comparison_never_crosses_scope_or_same_source() -> None:
    ledger = observation()
    provider = observation(source=SourceKind.PROVIDER_REPORT, source_record_id="alf-000001")
    assert comparable(ledger, provider)
    assert not comparable(ledger, ledger)
    for change in (
        {"tenant_id": "tenant-other"},
        {"merchant_account": "merchant-02"},
        {"provider_id": "prov-beta"},
        {"money": Money(10000, "BOB")},
        {"operation_type": OperationType.REFUND},
    ):
        assert not comparable(ledger, observation(**change, source=SourceKind.PROVIDER_REPORT))


def test_canonical_hash_is_order_independent_and_content_sensitive() -> None:
    assert canonical_hash({"a": 1, "b": "x"}) == canonical_hash({"b": "x", "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


def test_offset_bounds() -> None:
    with pytest.raises(DomainError):
        DualTime(datetime(2026, 9, 1, tzinfo=UTC), 2000)
    with pytest.raises(DomainError):
        DualTime(datetime(2026, 9, 1, tzinfo=timezone(timedelta(hours=1))), 60)


def test_domain_package_has_no_infrastructure_imports() -> None:
    forbidden = {
        "sqlalchemy",
        "psycopg",
        "fastapi",
        "nats",
        "httpx",
        "alembic",
        "recon_api",
        "recon_store",
        "starlette",
        "pydantic",
    }
    for path in DOMAIN_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in forbidden, f"{path.name} imports {name}"
