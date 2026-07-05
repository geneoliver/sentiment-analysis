from datetime import date

import yaml

from src.config import load_settings
from src.corrections import (
    corrections_lookup,
    normalize_pattern,
    promote_rules,
    record_correction,
)
from src.models import Transaction


def _settings_with_tmp_dirs(tmp_path):
    settings = load_settings()
    settings.raw["paths"]["corrections_dir"] = str(tmp_path / "corrections")
    settings.raw["paths"]["learned_rules_file"] = str(tmp_path / "learned_rules.yaml")
    return settings


def test_normalize_pattern_strips_digits_and_collapses_whitespace():
    assert normalize_pattern("SQ *LOCAL COFFEE ROASTERS 001") == normalize_pattern("SQ *LOCAL COFFEE ROASTERS 002")
    assert normalize_pattern("Trader Joe's #123") == "TRADER JOE'S #"


def test_record_and_lookup_correction(tmp_path):
    settings = _settings_with_tmp_dirs(tmp_path)
    tx = Transaction(date=date(2026, 6, 10), source="amex", description="SQ *LOCAL COFFEE ROASTERS", amount=6.75)

    record_correction(settings, tx, "Discretionary", "Dining Out")

    lookup = corrections_lookup(settings)
    pattern = normalize_pattern(tx.description)
    assert pattern in lookup
    assert lookup[pattern].subcategory == "Dining Out"


def test_promote_rules_after_threshold(tmp_path):
    settings = _settings_with_tmp_dirs(tmp_path)
    settings.raw["corrections"]["promote_after_n_corrections"] = 2

    tx1 = Transaction(date=date(2026, 6, 10), source="amex", description="SQ *LOCAL COFFEE ROASTERS 001", amount=6.75)
    tx2 = Transaction(date=date(2026, 7, 3), source="amex", description="SQ *LOCAL COFFEE ROASTERS 002", amount=5.25)

    record_correction(settings, tx1, "Discretionary", "Dining Out")
    assert promote_rules(settings) == []  # only corrected once so far

    record_correction(settings, tx2, "Discretionary", "Dining Out")
    promoted = promote_rules(settings)

    assert len(promoted) == 1
    assert promoted[0].subcategory == "Dining Out"

    learned_path = tmp_path / "learned_rules.yaml"
    data = yaml.safe_load(learned_path.read_text())
    assert len(data["rules"]) == 1
