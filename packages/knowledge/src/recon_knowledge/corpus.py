"""Synthetic corpus loading and validation.

Each document is a Markdown file with a `key: value` front matter. Validation rejects
documents with missing metadata, invalid enums or windows, and anything that looks like
card data or key material. Instruction-like text is kept (it is real-world content) but
flagged so callers treat it as untrusted data.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DOCUMENT_TYPES = frozenset({"runbook", "provider_doc", "error_codes", "incident", "procedure"})
REVIEW_STATUSES = frozenset({"published", "draft", "revoked"})
LANGUAGES = {"es": "spanish", "en": "english"}
ROLES = frozenset({"analyst", "supervisor", "auditor"})
REQUIRED = (
    "document_id",
    "version",
    "tenant_scope",
    "acl",
    "document_type",
    "title",
    "language",
    "effective_from",
    "published_at",
    "review_status",
)
_IDENT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_PAN = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}\b")
_INSTRUCTION = re.compile(
    r"ignora (todas )?las instrucciones|ignore (all )?previous instructions|approve_resolution"
    r"|env[ií]a el token|send the token|eres administrador|you are (an )?admin",
    re.IGNORECASE,
)


class CorpusError(ValueError):
    """A document violates the corpus contract."""


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:160] or "section"


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def has_instructions(text: str) -> bool:
    return bool(_INSTRUCTION.search(text))


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: str
    version: int
    tenant_scope: str
    acl: tuple[str, ...]
    provider_id: str | None
    document_type: str
    title: str
    language: str
    effective_from: datetime
    effective_to: datetime | None
    published_at: datetime
    review_status: str
    supersedes: str | None
    body: str
    body_start_line: int

    @property
    def key(self) -> str:
        return f"{self.document_id}@{self.version}"

    @property
    def fts_config(self) -> str:
        return LANGUAGES[self.language]

    @property
    def source_uri(self) -> str:
        return f"synthetic://knowledge-v1/{self.key}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


def _time(meta: dict[str, str], name: str) -> datetime | None:
    raw = meta.get(name, "").strip()
    if not raw:
        return None
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        raise CorpusError(f"{name} must include an offset")
    return value


def parse_document(text: str, origin: str = "<memory>") -> SourceDocument:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise CorpusError(f"{origin}: missing front matter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise CorpusError(f"{origin}: unterminated front matter") from None
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            raise CorpusError(f"{origin}: invalid front matter line {line!r}")
        meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise CorpusError(f"{origin}: missing metadata {missing}")
    body = "\n".join(lines[end + 1 :]).strip("\n") + "\n"
    acl = tuple(sorted({r.strip() for r in meta["acl"].split(",") if r.strip()}))
    try:
        effective_from = _time(meta, "effective_from")
        published_at = _time(meta, "published_at")
        effective_to = _time(meta, "effective_to")
        version = int(meta["version"])
    except ValueError as exc:
        raise CorpusError(f"{origin}: {exc}") from None
    assert effective_from is not None and published_at is not None  # noqa: S101 - REQUIRED
    doc = SourceDocument(
        document_id=meta["document_id"],
        version=version,
        tenant_scope=meta["tenant_scope"],
        acl=acl,
        provider_id=meta.get("provider_id") or None,
        document_type=meta["document_type"],
        title=meta["title"],
        language=meta["language"],
        effective_from=effective_from,
        effective_to=effective_to,
        published_at=published_at,
        review_status=meta["review_status"],
        supersedes=meta.get("supersedes") or None,
        body=body,
        body_start_line=end + 2,
    )
    validate(doc, origin)
    return doc


def validate(doc: SourceDocument, origin: str) -> None:
    problems = []
    for name in ("document_id", "tenant_scope"):
        if not _IDENT.fullmatch(getattr(doc, name)):
            problems.append(f"{name} must match {_IDENT.pattern}")
    if doc.version < 1:
        problems.append("version must be >= 1")
    if not doc.acl or not set(doc.acl) <= ROLES:
        problems.append(f"acl must be a non-empty subset of {sorted(ROLES)}")
    if doc.document_type not in DOCUMENT_TYPES:
        problems.append(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")
    if doc.review_status not in REVIEW_STATUSES:
        problems.append(f"review_status must be one of {sorted(REVIEW_STATUSES)}")
    if doc.language not in LANGUAGES:
        problems.append(f"language must be one of {sorted(LANGUAGES)}")
    if doc.effective_to is not None and doc.effective_to <= doc.effective_from:
        problems.append("effective_to must be after effective_from")
    if _KEY.search(doc.body):
        problems.append("content contains key material")
    for match in _PAN.finditer(doc.body):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            problems.append("content contains a card-like number")
            break
    if problems:
        raise CorpusError(f"{origin}: " + "; ".join(problems))


def corpus_manifest(root: Path) -> dict[str, object]:
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted([*root.glob("docs/*.md"), root / "queries.jsonl"])
    }
    content_hash = hashlib.sha256(
        "".join(f"{n}:{d}\n" for n, d in sorted(files.items())).encode()
    ).hexdigest()
    return {
        "dataset_id": "knowledge",
        "version": "v1",
        "data_origin": "SYNTHETIC",
        "generator": "hand-written synthetic corpus (no real providers, people or data)",
        "files": files,
        "content_hash": content_hash,
        "counts": {
            "documents": len(list(root.glob("docs/*.md"))),
            "queries": sum(
                1 for ln in (root / "queries.jsonl").read_text("utf-8").splitlines() if ln.strip()
            ),
        },
    }


def load_corpus(root: Path) -> list[SourceDocument]:
    docs = [
        parse_document(path.read_text(encoding="utf-8"), path.name)
        for path in sorted((root / "docs").glob("*.md"))
    ]
    keys = [d.key for d in docs]
    if len(keys) != len(set(keys)):
        raise CorpusError("duplicated document_id@version in corpus")
    for doc in docs:
        expected = f"{doc.key}.md"
        if not (root / "docs" / expected).is_file():
            raise CorpusError(f"{doc.key}: file must be named {expected}")
    return docs
