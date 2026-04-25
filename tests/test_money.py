"""Pure unit tests for money primitives — no database required."""

from __future__ import annotations

from decimal import Decimal

from money.types import Currency, Minor, add, negate, round_minor, to_decimal


def test_add_and_negate_stay_integer() -> None:
    assert add(Minor(150), Minor(50)) == 200
    assert negate(Minor(150)) == -150


def test_to_decimal_uses_currency_exponent() -> None:
    assert to_decimal(Minor(12345), Currency.USD) == Decimal("123.45")


def test_round_minor_is_bankers_rounding() -> None:
    # 1.005 -> 100 (round-half-to-even), 1.015 -> 102
    assert round_minor(Decimal("1.005"), Currency.USD) == 100
    assert round_minor(Decimal("1.015"), Currency.USD) == 102
