"""Tier 1 categorization: corrections, then merchant rules (manual + learned).

Priority order (highest first):
  1. An exact match on a previously-corrected pattern — you already told the
     pipeline what this is.
  2. The longest matching keyword from config/merchant_rules.yaml or
     config/learned_rules.yaml (longer = more specific, so it wins over a
     generic rule).

Anything left uncategorized after this pass is handed to tier 2 (Claude API).
"""
from __future__ import annotations

from src.config import Settings, Taxonomy, load_merchant_rules
from src.corrections import corrections_lookup, normalize_pattern
from src.models import METHOD_CORRECTION, METHOD_LEARNED_RULE, METHOD_RULE, Transaction


def apply_rules(transactions: list[Transaction], settings: Settings, taxonomy: Taxonomy) -> None:
    lookup = corrections_lookup(settings)
    rules = sorted(load_merchant_rules(settings), key=lambda r: len(r.keyword), reverse=True)

    for tx in transactions:
        if tx.category is not None:
            continue  # already resolved (e.g. flagged as a transfer)

        pattern = normalize_pattern(tx.description)
        correction = lookup.get(pattern)
        if correction is not None:
            tx.category = taxonomy.top_level_for(correction.subcategory) or correction.category
            tx.subcategory = correction.subcategory
            tx.method = METHOD_CORRECTION
            tx.confidence = 1.0
            continue

        upper_desc = tx.description.upper()
        for rule in rules:
            if rule.keyword.upper() in upper_desc:
                tx.category = taxonomy.top_level_for(rule.subcategory) or rule.category
                tx.subcategory = rule.subcategory
                tx.method = METHOD_RULE if rule.origin == "manual" else METHOD_LEARNED_RULE
                tx.confidence = 1.0
                break
