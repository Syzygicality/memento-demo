"""Money primitives.

`Minor` is a ``NewType`` over ``int`` representing an amount in a currency's
minor units (cents for USD, pence for GBP). It exists so mypy strict rejects any
code that mixes a money amount with a plain count — the single most common way a
ledger grows a rounding or unit bug. There is no float anywhere in this module by
design: money is integer minor units end to end, and rounding is a presentation
concern applied only at the edge (see ``round_minor``).
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import NewType

# An amount in a currency's smallest indivisible unit. Never a float.
Minor = NewType("Minor", int)


class Currency(StrEnum):
    """Supported settlement currencies.

    Currency is fixed per account at creation and never converted implicitly;
    cross-currency movement must route through explicit conversion accounts (see
    DECISIONS.md → currency-fixed-per-account).
    """

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"


# Minor-unit exponent per currency (all 2 today; kept as a table so a
# 0- or 3-decimal currency can be added without touching call sites).
_EXPONENT: dict[Currency, int] = {
    Currency.USD: 2,
    Currency.EUR: 2,
    Currency.GBP: 2,
    Currency.CAD: 2,
}


def zero() -> Minor:
    """Return the additive identity as a ``Minor``."""
    return Minor(0)


def add(a: Minor, b: Minor) -> Minor:
    """Add two amounts of the (assumed) same currency."""
    return Minor(int(a) + int(b))


def negate(a: Minor) -> Minor:
    """Return the signed inverse — used to build the credit leg of a posting."""
    return Minor(-int(a))


def to_decimal(amount: Minor, currency: Currency) -> Decimal:
    """Convert minor units to a presentation ``Decimal`` (never for storage)."""
    exp = _EXPONENT[currency]
    return Decimal(int(amount)) / (Decimal(10) ** exp)


def round_minor(value: Decimal, currency: Currency) -> Minor:
    """Round a decimal to whole minor units using banker's rounding.

    Rounding is applied only when converting an externally supplied decimal into
    the ledger's integer representation — never on already-stored minor units.
    Banker's rounding (round-half-to-even) is used so aggregate reports do not
    accumulate a directional bias.
    """
    exp = _EXPONENT[currency]
    scaled = (value * (Decimal(10) ** exp)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    return Minor(int(scaled))
