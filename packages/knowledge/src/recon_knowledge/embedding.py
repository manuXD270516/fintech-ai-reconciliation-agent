"""Deterministic local embeddings: signed feature hashing of words and character trigrams.

This is NOT a semantic model. It captures surface (lexical/morphological) similarity,
needs no download and is reproducible bit for bit. It exercises the pgvector plumbing
and gives a measurable vector baseline; any semantic-quality claim requires a real model
evaluated under docs/07-evals.md.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass

DIMENSIONS = 256
_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return plain.lower()


def _features(text: str) -> list[tuple[str, float]]:
    feats: list[tuple[str, float]] = []
    for word in _WORD.findall(normalize(text)):
        feats.append((f"w:{word}", 1.0))
        padded = f"#{word}#"
        feats += [(f"c:{padded[i : i + 3]}", 0.5) for i in range(len(padded) - 2)]
    return feats


@dataclass(frozen=True, slots=True)
class HashingEmbedder:
    model: str = "hashing-ngram"
    revision: str = "v1"
    dimensions: int = DIMENSIONS

    @property
    def manifest(self) -> dict[str, object]:
        return {
            "model": self.model,
            "revision": self.revision,
            "dimensions": self.dimensions,
            "tokenizer": "ascii-folded lowercase [a-z0-9]+ words + char trigrams",
            "normalization": "l2",
            "semantic": False,
        }

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, weight in _features(text):
            digest = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest())
            sign = 1.0 if digest >> 63 else -1.0
            vector[digest % self.dimensions] += sign * weight
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [round(v / norm, 6) for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
