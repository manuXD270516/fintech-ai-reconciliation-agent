"""M1 T01: exact money, precision rejection and range validation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon_domain.money import MINOR_MAX, MINOR_MIN, Money, MoneyError

amounts = st.integers(min_value=MINOR_MIN, max_value=MINOR_MAX)
currencies = st.sampled_from(["USD", "BOB"])


@given(amounts, currencies)
def test_decimal_roundtrip_is_exact(minor: int, currency: str) -> None:
    money = Money(minor, currency)
    assert Money.from_decimal(money.to_decimal(), currency) == money
    assert Money.from_decimal(str(money.to_decimal()), currency) == money


@given(st.integers(-(10**12), 10**12), st.integers(-(10**12), 10**12), currencies)
def test_addition_and_subtraction_are_exact_inverses(a: int, b: int, currency: str) -> None:
    x, y = Money(a, currency), Money(b, currency)
    assert (x + y) - y == x


@pytest.mark.parametrize("value", ["10.005", "0.001", "1e-3", "-0.009"])
def test_excess_precision_is_rejected(value: str) -> None:
    with pytest.raises(MoneyError, match="precision"):
        Money.from_decimal(value, "USD")


@pytest.mark.parametrize("value", ["10.5", "10.50", "10.500", "1E+2", "-3.10"])
def test_equivalent_precision_is_accepted(value: str) -> None:
    assert Money.from_decimal(value, "USD").to_decimal() == Decimal(value)


def test_float_inputs_are_rejected() -> None:
    with pytest.raises(MoneyError):
        Money.from_decimal(10.5, "USD")  # type: ignore[arg-type]
    with pytest.raises(MoneyError):
        Money(10.0, "USD")  # type: ignore[arg-type]
    with pytest.raises(MoneyError):
        Money(True, "USD")


@pytest.mark.parametrize("value", ["abc", "NaN", "Infinity", ""])
def test_non_numeric_or_non_finite_are_rejected(value: str) -> None:
    with pytest.raises(MoneyError):
        Money.from_decimal(value, "USD")


def test_range_and_currency_are_validated() -> None:
    with pytest.raises(MoneyError, match="64-bit"):
        Money(MINOR_MAX + 1, "USD")
    with pytest.raises(MoneyError, match="64-bit"):
        Money(MINOR_MAX, "USD") + Money(1, "USD")
    with pytest.raises(MoneyError, match="unsupported currency"):
        Money(1, "EUR")


def test_cross_currency_operations_are_rejected() -> None:
    with pytest.raises(MoneyError, match="different currencies"):
        Money(1, "USD") + Money(1, "BOB")
    assert Money(100, "USD") != Money(100, "BOB")
