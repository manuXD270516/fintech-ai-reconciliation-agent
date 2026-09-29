"""Idempotency and revision policy for incoming observations (invariant 2)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class IngestOutcome(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    NEW_REVISION = "new_revision"
    STALE_REVISION = "stale_revision"
    CONFLICT = "conflict"

    @property
    def persists(self) -> bool:
        return self in {
            IngestOutcome.CREATED,
            IngestOutcome.NEW_REVISION,
            IngestOutcome.STALE_REVISION,
        }


@dataclass(frozen=True, slots=True)
class StoredRevision:
    revision: int
    raw_hash: str


def decide(existing: Iterable[StoredRevision], revision: int, raw_hash: str) -> IngestOutcome:
    """Classify an incoming (revision, raw_hash) against the stored history of one key.

    Same revision and hash is a replay (no new effect). Same revision with another hash
    is a conflict and never overwrites. A higher revision becomes current; a lower,
    unseen revision arrived out of order and is kept as history without becoming current.
    """
    history = {item.revision: item.raw_hash for item in existing}
    if not history:
        return IngestOutcome.CREATED
    if revision in history:
        return IngestOutcome.DUPLICATE if history[revision] == raw_hash else IngestOutcome.CONFLICT
    return IngestOutcome.NEW_REVISION if revision > max(history) else IngestOutcome.STALE_REVISION
