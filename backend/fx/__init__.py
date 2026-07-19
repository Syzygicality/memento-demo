"""FX — cross-currency conversion through explicit conversion accounts.

This package lifts the single-currency restriction on transfers. Instead of
rejecting a cross-currency movement outright, it resolves a provenance-tagged
rate and routes the value through a per-currency **conversion account** so that
every leg of the movement is still single-currency and every transaction still
balances to zero within one currency (see DECISIONS.md → fx-conversion-accounts,
which supersedes currency-fixed-per-account's reject-cross-currency stance).
"""
