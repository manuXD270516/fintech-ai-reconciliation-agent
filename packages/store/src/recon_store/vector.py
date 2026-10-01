"""Minimal pgvector column type for SQLAlchemy Core (no extra dependency).

Values travel as pgvector text literals (`[0.1,0.2]`). The type is registered in the
PostgreSQL dialect so reflection (and the schema drift test) recognises `vector(n)`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.engine import Dialect
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})" if self.dimensions else "vector"

    def bind_processor(self, dialect: Dialect) -> Callable[[Any], str | None]:
        def process(value: Sequence[float] | str | None) -> str | None:
            if value is None or isinstance(value, str):
                return value
            return to_literal(value)

        return process

    def result_processor(
        self, dialect: Dialect, coltype: object
    ) -> Callable[[Any], list[float] | None]:
        def process(value: str | None) -> list[float] | None:
            if value is None:
                return None
            return [float(x) for x in value.strip("[]").split(",") if x]

        return process


def to_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


ischema_names["vector"] = Vector
