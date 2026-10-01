"""Idempotent artifact ingestion: one transaction per artifact (rows, rejections, audit, outbox)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, func, insert, select

from recon_domain.ingestion import PARSER_VERSION, parse_csv
from recon_domain.observation import SourceKind
from recon_domain.revisions import IngestOutcome
from recon_store.observations import ObservationStore
from recon_store.tables import artifacts, audit_entries, outbox, rejections

ARTIFACT_INGESTED = "ArtifactIngested"


class IdempotencyConflictError(Exception):
    """Same idempotency key reused with different content."""


@dataclass(frozen=True, slots=True)
class Receipt:
    artifact_id: int
    replayed: bool
    content_hash: str
    row_count: int
    accepted: int
    duplicates: int
    conflicts: int
    rejected: int
    rejections: tuple[tuple[int, str, str], ...]


class ArtifactService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.observations = ObservationStore(engine)

    def ingest(
        self,
        *,
        tenant_id: str,
        source: SourceKind,
        provider_id: str,
        idempotency_key: str,
        content: str,
        actor: str,
        correlation_id: str,
        now: datetime,
    ) -> Receipt:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self.engine.begin() as conn:
            token = f"artifact|{tenant_id}|{source.value}|{provider_id}|{idempotency_key}"
            conn.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(token, 0))))
            existing = (
                conn.execute(
                    select(artifacts).where(
                        artifacts.c.tenant_id == tenant_id,
                        artifacts.c.source == source.value,
                        artifacts.c.provider_id == provider_id,
                        artifacts.c.idempotency_key == idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if existing["content_hash"] != content_hash:
                    raise IdempotencyConflictError(idempotency_key)
                stored = conn.execute(
                    select(rejections.c.row_number, rejections.c.code, rejections.c.message)
                    .where(rejections.c.artifact_id == existing["id"])
                    .order_by(rejections.c.row_number)
                ).all()
                return Receipt(
                    existing["id"],
                    True,
                    content_hash,
                    existing["row_count"],
                    existing["accepted"],
                    existing["duplicates"],
                    existing["conflicts"],
                    existing["rejected"],
                    tuple((r[0], r[1], r[2]) for r in stored),
                )

            parsed = parse_csv(
                content,
                source=source,
                provider_id=provider_id,
                tenant_id=tenant_id,
                received_at=now,
            )
            counts = dict.fromkeys(IngestOutcome, 0)
            for _, obs in parsed.observations:
                result = self.observations.ingest_in(
                    conn, obs, actor=actor, correlation_id=correlation_id
                )
                counts[result.outcome] += 1
            accepted = sum(n for o, n in counts.items() if o.persists)
            artifact_id: int = conn.execute(
                insert(artifacts)
                .values(
                    tenant_id=tenant_id,
                    source=source.value,
                    provider_id=provider_id,
                    idempotency_key=idempotency_key,
                    content_hash=content_hash,
                    parser_version=PARSER_VERSION,
                    row_count=parsed.row_count,
                    accepted=accepted,
                    duplicates=counts[IngestOutcome.DUPLICATE],
                    conflicts=counts[IngestOutcome.CONFLICT],
                    rejected=len(parsed.rejections),
                    received_by=actor,
                    correlation_id=correlation_id,
                )
                .returning(artifacts.c.id)
            ).scalar_one()
            if parsed.rejections:
                conn.execute(
                    insert(rejections),
                    [
                        {
                            "artifact_id": artifact_id,
                            "tenant_id": tenant_id,
                            "source": source.value,
                            "provider_id": provider_id,
                            "row_number": r.row_number,
                            "code": r.code.value,
                            "message": r.message[:300],
                            "payment_ref": r.payment_ref,
                            "merchant_account": r.merchant_account,
                            "currency": r.currency,
                            "raw_hash": r.raw_hash,
                        }
                        for r in parsed.rejections
                    ],
                )
            summary = {
                "artifact_id": artifact_id,
                "rows": parsed.row_count,
                "accepted": accepted,
                "duplicates": counts[IngestOutcome.DUPLICATE],
                "conflicts": counts[IngestOutcome.CONFLICT],
                "rejected": len(parsed.rejections),
            }
            conn.execute(
                insert(audit_entries).values(
                    tenant_id=tenant_id,
                    actor=actor,
                    action="artifact.ingest",
                    resource_type="artifact",
                    resource_id=str(artifact_id),
                    resource_version=1,
                    outcome="accepted",
                    correlation_id=correlation_id,
                    details=summary | {"content_hash": content_hash},
                )
            )
            conn.execute(
                insert(outbox).values(
                    event_id=uuid.uuid4(),
                    event_type=ARTIFACT_INGESTED,
                    schema_version=1,
                    tenant_id=tenant_id,
                    aggregate_id=f"artifact/{artifact_id}",
                    aggregate_version=1,
                    correlation_id=correlation_id,
                    payload=summary,
                )
            )
            return Receipt(
                artifact_id,
                False,
                content_hash,
                parsed.row_count,
                accepted,
                counts[IngestOutcome.DUPLICATE],
                counts[IngestOutcome.CONFLICT],
                len(parsed.rejections),
                tuple((r.row_number, r.code.value, r.message) for r in parsed.rejections),
            )
