"""Flags money movement between the two accounts so it isn't double-counted as spend.

Two mechanisms, matching the spec:

1. Keyword match (config: dedupe.internal_transfer_keywords) — the primary,
   transparent mechanism. Anything matching is marked `is_transfer=True`
   with category/subcategory set to Internal Transfer / Credit Card Payment.
   These rows stay in every tab for the audit trail but are excluded from
   spend summaries.

2. Cross-source amount/date heuristic — catches transfers the keyword list
   doesn't know about yet. It never auto-excludes anything; it just sets
   `possible_duplicate=True` so it surfaces in manual review.
"""
from __future__ import annotations

from datetime import timedelta

from src.config import Settings, Taxonomy
from src.models import Transaction

TRANSFER_SUBCATEGORY = "Credit Card Payment"


def flag_transfers(transactions: list[Transaction], settings: Settings, taxonomy: Taxonomy) -> None:
    keywords = [k.upper() for k in settings.internal_transfer_keywords]
    top_level = taxonomy.top_level_for(TRANSFER_SUBCATEGORY) or "Internal Transfer"

    for tx in transactions:
        upper_desc = tx.description.upper()
        if any(kw in upper_desc for kw in keywords):
            tx.is_transfer = True
            tx.category = top_level
            tx.subcategory = TRANSFER_SUBCATEGORY
            tx.method = "transfer_keyword"
            tx.confidence = 1.0


def flag_possible_duplicates(transactions: list[Transaction], settings: Settings) -> None:
    """Cross-source amount/date match for transactions not already flagged as transfers."""
    tolerance = settings.amount_match_tolerance
    window = timedelta(days=settings.date_window_days)

    candidates = [tx for tx in transactions if not tx.is_transfer]
    by_source: dict[str, list[Transaction]] = {}
    for tx in candidates:
        by_source.setdefault(tx.source, []).append(tx)

    sources = list(by_source.keys())
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            for tx_a in by_source[sources[i]]:
                for tx_b in by_source[sources[j]]:
                    if abs(abs(tx_a.amount) - abs(tx_b.amount)) <= tolerance and abs((tx_a.date - tx_b.date).days) <= window.days:
                        tx_a.possible_duplicate = True
                        tx_b.possible_duplicate = True
