from datetime import date

from src.categorize.rules import apply_rules
from src.config import load_settings, load_taxonomy
from src.models import Transaction


def test_apply_rules_matches_known_merchants_and_leaves_unknown_uncategorized(tmp_path):
    settings = load_settings()
    settings.raw["paths"]["corrections_dir"] = str(tmp_path)
    taxonomy = load_taxonomy()

    groceries = Transaction(date=date(2026, 6, 2), source="amex", description="TRADER JOE S #123 BERKELEY CA", amount=84.32)
    streaming = Transaction(date=date(2026, 6, 3), source="amex", description="NETFLIX.COM", amount=15.49)
    unknown = Transaction(date=date(2026, 6, 10), source="amex", description="SQ *LOCAL COFFEE ROASTERS", amount=6.75)

    apply_rules([groceries, streaming, unknown], settings, taxonomy)

    assert groceries.category == "Essentials"
    assert groceries.subcategory == "Groceries"
    assert groceries.method == "rule"
    assert groceries.confidence == 1.0

    assert streaming.category == "Discretionary"
    assert streaming.subcategory == "Entertainment"

    assert unknown.category is None  # left for tier 2 (Claude API)


def test_apply_rules_longest_keyword_wins(tmp_path):
    settings = load_settings()
    settings.raw["paths"]["corrections_dir"] = str(tmp_path)
    settings.raw["paths"]["merchant_rules_file"] = "tests/fixtures/overlap_rules.yaml"
    taxonomy = load_taxonomy()

    tx = Transaction(date=date(2026, 6, 1), source="amex", description="AMAZON PRIME VIDEO", amount=9.99)
    apply_rules([tx], settings, taxonomy)

    assert tx.subcategory == "Entertainment"  # "AMAZON PRIME" is more specific than "AMAZON"
