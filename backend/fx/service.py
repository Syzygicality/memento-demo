"""Cross-currency routing through conversion accounts.

A cross-currency transfer cannot be a single balanced transaction: a debit in USD
and a credit in EUR do not sum to zero in any one currency. Instead the movement
is split at a pair of **conversion accounts** — one per currency — that the
platform owns:

    source (USD) ── debit ──▶ conversion:USD          (USD transaction, balances)
    conversion:EUR ── credit ──▶ destination (EUR)    (EUR transaction, balances)

The two legs are posted in the *same* DB transaction at a resolved, provenance-
tagged rate. Each leg is single-currency and balances to zero on its own, so the
per-transaction balance trigger is never violated, while the conversion accounts
absorb the FX as an explicit, auditable position rather than burying it inside a
money movement (see DECISIONS.md → fx-conversion-accounts, which supersedes
currency-fixed-per-account's reject-cross-currency stance).

The rounding residual of the conversion lands in the conversion accounts by
construction — the debited and credited amounts are each rounded once, to their
own currency's minor units — so no value is invented or discarded silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.accounts import Account
from fx.rates import ResolvedRate, resolve_rate
from money.types import Currency, Minor, convert, negate
from postings.engine import PostingSpec, post_transaction

# Conversion accounts live under a fixed reserved path prefix, one per currency,
# so the router can find them without a per-transfer lookup table.
CONVERSION_PATH_PREFIX = "platform.fx.conversion"


class ConversionAccountMissingError(Exception):
    """The platform has no conversion account provisioned for a currency."""


@dataclass(frozen=True)
class ConversionResult:
    """The two posted legs of a conversion plus the rate that produced them."""

    debit_transaction_id: object
    credit_transaction_id: object
    source_amount: Minor
    target_amount: Minor
    rate: ResolvedRate


async def route_conversion(
    session: AsyncSession,
    tenant_id: str,
    source: Account,
    destination: Account,
    amount: Minor,
    effective_at: datetime,
    memo: str,
) -> ConversionResult:
    """Post the two single-currency legs of a cross-currency movement.

    Resolves the ``source``→``destination`` rate effective at ``effective_at``,
    converts the amount into the destination currency, and posts a debit leg in
    the source currency and a credit leg in the destination currency through the
    matching conversion accounts. Both legs commit in the caller's transaction.
    """
    rate = await resolve_rate(session, source.currency, destination.currency, effective_at)
    target_amount = convert(amount, source.currency, destination.currency, rate.rate)

    src_conv = await _conversion_account(session, tenant_id, source.currency)
    dst_conv = await _conversion_account(session, tenant_id, destination.currency)

    # Leg 1 — debit the source, credit the source-currency conversion account.
    debit_txn = await post_transaction(
        session,
        tenant_id,
        specs=[
            PostingSpec(source.id, negate(amount), effective_at),
            PostingSpec(src_conv.id, amount, effective_at),
        ],
        memo=_leg_memo(memo, "debit", rate),
    )

    # Leg 2 — debit the destination-currency conversion account, credit the dest.
    credit_txn = await post_transaction(
        session,
        tenant_id,
        specs=[
            PostingSpec(dst_conv.id, negate(target_amount), effective_at),
            PostingSpec(destination.id, target_amount, effective_at),
        ],
        memo=_leg_memo(memo, "credit", rate),
    )

    return ConversionResult(
        debit_transaction_id=debit_txn.id,
        credit_transaction_id=credit_txn.id,
        source_amount=amount,
        target_amount=target_amount,
        rate=rate,
    )


async def _conversion_account(
    session: AsyncSession, tenant_id: str, currency: Currency
) -> Account:
    """Resolve the platform conversion account for one currency."""
    path = f"{CONVERSION_PATH_PREFIX}.{currency.value.lower()}"
    stmt = select(Account).where(
        Account.tenant_id == tenant_id,
        Account.path == path,
        Account.is_open == True,  # noqa: E712 — SQL boolean, not Python identity
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()
    if account is None:
        raise ConversionAccountMissingError(
            f"no open conversion account at '{path}' for {currency}"
        )
    return account


def _leg_memo(memo: str, leg: str, rate: ResolvedRate) -> str:
    """Annotate each leg's memo with the rate provenance for the audit trail."""
    stamp = f"fx {leg} @ {rate.rate} [{rate.source}]"
    return f"{memo} — {stamp}" if memo else stamp
