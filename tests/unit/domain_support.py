from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from recon_domain.money import Money
from recon_domain.observation import (
    DualTime,
    ObservationStatus,
    OperationType,
    SourceKind,
    TransactionObservation,
    canonical_hash,
)

LA_PAZ = timezone(timedelta(hours=-4))


def observation(**overrides: Any) -> TransactionObservation:
    base = TransactionObservation(
        tenant_id="tenant-demo",
        source=SourceKind.INTERNAL_LEDGER,
        source_record_id="led-000001",
        revision=1,
        provider_id="prov-alfa",
        merchant_account="merchant-01",
        operation_type=OperationType.CAPTURE,
        payment_ref="pay-0001",
        attempt_ref="pay-0001-a1",
        money=Money(10000, "USD"),
        status=ObservationStatus.SUCCEEDED,
        occurred_at=DualTime.from_aware(datetime(2026, 9, 1, 8, 0, tzinfo=LA_PAZ)),
        received_at=DualTime.from_aware(datetime(2026, 9, 1, 8, 5, tzinfo=LA_PAZ)),
        effective_at=None,
        raw_hash=canonical_hash({"id": "led-000001"}),
    )
    return replace(base, **overrides)
