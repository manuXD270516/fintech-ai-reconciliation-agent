"""Versioned mappings from source-specific vocabularies to the canonical model.

Unknown values are rejected (quarantine), never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from recon_domain.observation import DomainError, ObservationStatus, OperationType, SourceKind

MAPPING_VERSION = "mappings/v1"


class UnknownMappingError(DomainError):
    """A source value has no mapping in the current version."""


@dataclass(frozen=True, slots=True)
class SourceVocabulary:
    source: SourceKind
    provider_id: str
    statuses: MappingProxyType[str, ObservationStatus]
    operations: MappingProxyType[str, OperationType]

    def status(self, raw: str) -> ObservationStatus:
        try:
            return self.statuses[raw.strip().upper()]
        except KeyError:
            raise UnknownMappingError(
                f"unknown status {raw!r} for {self.source}/{self.provider_id} ({MAPPING_VERSION})"
            ) from None

    def operation(self, raw: str) -> OperationType:
        try:
            return self.operations[raw.strip().upper()]
        except KeyError:
            raise UnknownMappingError(
                f"unknown operation {raw!r} for {self.source}/{self.provider_id} "
                f"({MAPPING_VERSION})"
            ) from None


def _vocab(
    source: SourceKind,
    provider_id: str,
    statuses: dict[str, ObservationStatus],
    operations: dict[str, OperationType],
) -> SourceVocabulary:
    return SourceVocabulary(
        source, provider_id, MappingProxyType(statuses), MappingProxyType(operations)
    )


St, Op = ObservationStatus, OperationType
_LEDGER_STATUSES = {
    "PENDING": St.PENDING,
    "POSTED": St.SUCCEEDED,
    "FAILED": St.FAILED,
    "REVERSED": St.REVERSED,
}
_LEDGER_OPS = {
    "AUTH": Op.AUTHORIZATION,
    "CAPTURE": Op.CAPTURE,
    "REFUND": Op.REFUND,
    "CHARGEBACK": Op.CHARGEBACK,
}

VOCABULARIES: MappingProxyType[tuple[SourceKind, str], SourceVocabulary] = MappingProxyType(
    {
        (SourceKind.INTERNAL_LEDGER, "prov-alfa"): _vocab(
            SourceKind.INTERNAL_LEDGER, "prov-alfa", _LEDGER_STATUSES, _LEDGER_OPS
        ),
        (SourceKind.INTERNAL_LEDGER, "prov-beta"): _vocab(
            SourceKind.INTERNAL_LEDGER, "prov-beta", _LEDGER_STATUSES, _LEDGER_OPS
        ),
        (SourceKind.PROVIDER_REPORT, "prov-alfa"): _vocab(
            SourceKind.PROVIDER_REPORT,
            "prov-alfa",
            {
                "SETTLED": St.SUCCEEDED,
                "PENDING": St.PENDING,
                "DECLINED": St.FAILED,
                "REVERSED": St.REVERSED,
            },
            {
                "AUTHORIZE": Op.AUTHORIZATION,
                "CAPTURE": Op.CAPTURE,
                "REFUND": Op.REFUND,
                "DISPUTE": Op.CHARGEBACK,
            },
        ),
        (SourceKind.PROVIDER_REPORT, "prov-beta"): _vocab(
            SourceKind.PROVIDER_REPORT,
            "prov-beta",
            {"OK": St.SUCCEEDED, "WAIT": St.PENDING, "KO": St.FAILED, "VOID": St.REVERSED},
            {"AUT": Op.AUTHORIZATION, "CAP": Op.CAPTURE, "REF": Op.REFUND, "CBK": Op.CHARGEBACK},
        ),
    }
)


def vocabulary(source: SourceKind, provider_id: str) -> SourceVocabulary:
    try:
        return VOCABULARIES[(source, provider_id)]
    except KeyError:
        raise UnknownMappingError(
            f"no vocabulary for {source}/{provider_id} ({MAPPING_VERSION})"
        ) from None
