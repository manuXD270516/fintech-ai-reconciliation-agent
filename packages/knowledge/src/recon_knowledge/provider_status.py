"""Synthetic provider status snapshots (validity intervals), loaded idempotently."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, select

from recon_store.tables import provider_status

STATUSES = frozenset({"operational", "degraded", "outage"})


class StatusError(ValueError):
    """The status dataset violates its contract."""


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    provider_id: str
    status: str
    valid_from: datetime
    valid_to: datetime | None
    observed_at: datetime
    details: dict[str, Any]


def _time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise StatusError("timestamps need an offset")
    return parsed


def load_snapshots(path: Path) -> tuple[str, list[StatusSnapshot]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("data_origin") != "SYNTHETIC":
        raise StatusError("provider status data must be SYNTHETIC")
    snapshots = []
    for item in raw["snapshots"]:
        valid_from = _time(item["valid_from"])
        observed = _time(item["observed_at"])
        if valid_from is None or observed is None:
            raise StatusError("valid_from and observed_at are required")
        snap = StatusSnapshot(
            provider_id=item["provider_id"],
            status=item["status"],
            valid_from=valid_from,
            valid_to=_time(item.get("valid_to")),
            observed_at=observed,
            details=dict(item.get("details", {})),
        )
        if snap.status not in STATUSES:
            raise StatusError(f"unknown status {snap.status!r}")
        if snap.valid_to is not None and snap.valid_to <= snap.valid_from:
            raise StatusError("valid_to must be after valid_from")
        snapshots.append(snap)
    return f"{raw['dataset_id']}/{raw['version']}", snapshots


def publish_snapshots(engine: Engine, path: Path) -> dict[str, int]:
    version, snapshots = load_snapshots(path)
    inserted = 0
    with engine.begin() as conn:
        for snap in snapshots:
            exists = conn.execute(
                select(provider_status.c.id).where(
                    provider_status.c.provider_id == snap.provider_id,
                    provider_status.c.valid_from == snap.valid_from,
                )
            ).first()
            if exists is not None:
                continue
            conn.execute(
                insert(provider_status).values(
                    provider_id=snap.provider_id,
                    status=snap.status,
                    valid_from=snap.valid_from,
                    valid_to=snap.valid_to,
                    observed_at=snap.observed_at,
                    details=snap.details,
                    source_version=version,
                )
            )
            inserted += 1
    return {"snapshots": len(snapshots), "inserted": inserted}
