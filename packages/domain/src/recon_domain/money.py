"""Exact money: integer minor units plus a currency with an explicit, versioned exponent."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

CURRENCY_POLICY_VERSION = "currency-policy/v1"
CURRENCY_EXPONENTS = MappingProxyType({"USD": 2, "BOB": 2})

MINOR_MIN = -(2**63)
MINOR_MAX = 2**63 - 1


class MoneyError(ValueError):
    """Invalid amount, currency, precision or cross-currency operation."""


def exponent_of(currency: str) -> int:
    try:
        return CURRENCY_EXPONENTS[currency]
    except KeyError:
        raise MoneyError(f"unsupported currency {currency!r} ({CURRENCY_POLICY_VERSION})") from None


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if type(self.amount_minor) is not int:
            raise MoneyError("amount_minor must be an int (floats and bools are rejected)")
        exponent_of(self.currency)
        if not MINOR_MIN <= self.amount_minor <= MINOR_MAX:
            raise MoneyError("amount_minor outside the signed 64-bit range")

    @classmethod
    def from_decimal(cls, value: str | Decimal, currency: str) -> Money:
        """Exact conversion; rejects floats and any precision beyond the currency exponent."""
        if not isinstance(value, (str, Decimal)):
            raise MoneyError("decimal amounts must be given as str or Decimal, never float")
        try:
            amount = Decimal(value.strip()) if isinstance(value, str) else value
        except InvalidOperation:
            raise MoneyError("amount is not a decimal number") from None
        if not amount.is_finite():
            raise MoneyError("amount must be finite")
        scaled = amount.scaleb(exponent_of(currency))
        if scaled != scaled.to_integral_value():
            raise MoneyError(f"precision exceeds the {currency} exponent")
        return cls(int(scaled), currency)

    def to_decimal(self) -> Decimal:
        return Decimal(self.amount_minor).scaleb(-exponent_of(self.currency))

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise MoneyError("cannot combine different currencies (no FX in scope)")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __str__(self) -> str:
        return f"{self.currency} {self.to_decimal()}"
