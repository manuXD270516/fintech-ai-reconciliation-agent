"""Heading-aware chunking (`chunking/v1`).

Each `##` section is a chunk; text before the first `##` is the `intro` chunk. A section
longer than MAX_TOKENS is split on block boundaries (blank lines) with a token overlap,
never inside a numbered list or a table. Chunk IDs derive from document, version,
locator and content hash, so a change of strategy yields a new index version.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from recon_knowledge.corpus import SourceDocument, has_instructions, slugify

CHUNKING_VERSION = "chunking/v1"
MAX_TOKENS = 700
OVERLAP_TOKENS = 80
_CODE = re.compile(r"\b[A-Z]\d{2}\b")


@dataclass(frozen=True, slots=True)
class Chunk:
    document_key: str
    chunk_id: str
    section_slug: str
    section_path: str
    ordinal: int
    start_line: int
    end_line: int
    content: str
    error_codes: tuple[str, ...]
    flagged_instructions: bool

    @property
    def token_count(self) -> int:
        return len(self.content.split())

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def evidence_unit(self) -> str:
        """Canonical evidence unit: overlapping parts of one section count once."""
        return f"{self.document_key}#{self.section_slug}"


@dataclass
class _Section:
    heading: str
    start: int
    lines: list[str]


def _blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            blocks[-1].append(line)
        elif blocks[-1]:
            blocks.append([])
    return [b for b in blocks if b]


def _split(text_lines: list[str]) -> list[str]:
    text = "\n".join(text_lines).strip()
    if len(text.split()) <= MAX_TOKENS:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    for block in _blocks(text_lines):
        block_text = "\n".join(block)
        if current and len(" ".join(current).split()) + len(block_text.split()) > MAX_TOKENS:
            parts.append("\n\n".join(current))
            tail = " ".join(parts[-1].split()[-OVERLAP_TOKENS:])
            current = [tail]
        current.append(block_text)
    if current:
        parts.append("\n\n".join(current))
    return parts


def chunk_document(doc: SourceDocument) -> list[Chunk]:
    title = doc.title
    sections: list[_Section] = [_Section("intro", doc.body_start_line, [])]
    for offset, line in enumerate(doc.body.rstrip("\n").split("\n")):
        number = doc.body_start_line + offset
        if line.startswith("# "):
            title = line[2:].strip()
            sections[0].start = number + 1
            continue
        if line.startswith("## "):
            sections.append(_Section(line[3:].strip(), number, []))
            continue
        sections[-1].lines.append(line)

    chunks: list[Chunk] = []
    for section in sections:
        if not "\n".join(section.lines).strip():
            continue
        slug = "intro" if section.heading == "intro" else slugify(section.heading)
        path = title if section.heading == "intro" else f"{title} > {section.heading}"
        end = section.start + len(section.lines)
        for part, content in enumerate(_split(section.lines)):
            full = content if section.heading == "intro" else f"{section.heading}\n{content}"
            digest = hashlib.sha256(full.encode("utf-8")).hexdigest()
            chunk_id = hashlib.sha256(
                f"{doc.key}#{slug}#{part}#{digest}#{CHUNKING_VERSION}".encode()
            ).hexdigest()[:32]
            chunks.append(
                Chunk(
                    document_key=doc.key,
                    chunk_id=chunk_id,
                    section_slug=slug,
                    section_path=path[:400],
                    ordinal=len(chunks),
                    start_line=section.start,
                    end_line=end,
                    content=full,
                    error_codes=tuple(sorted(set(_CODE.findall(full)))),
                    flagged_instructions=has_instructions(full),
                )
            )
    return chunks
