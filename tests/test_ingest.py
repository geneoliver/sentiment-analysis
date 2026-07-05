from pathlib import Path

from src.config import ROOT, load_settings
from src.ingest.csv_source import load_source

SAMPLES = ROOT / "samples"


def test_amex_ingest_normalizes_sign_and_skips_malformed_rows():
    settings = load_settings()
    result = load_source(SAMPLES / "amex_sample.csv", "amex", settings.source_config("amex"))

    assert len(result.skipped) == 1  # the row with a blank description
    assert len(result.transactions) == 10

    trader_joes = next(t for t in result.transactions if "TRADER JOE" in t.description)
    assert trader_joes.amount == 84.32  # charge_positive: charge stays positive (spend)

    payment = next(t for t in result.transactions if "AUTOPAY PAYMENT RECEIVED" in t.description)
    assert payment.amount == -1200.00  # a payment received is a credit, not spend


def test_checking_ingest_flips_debit_negative_sign():
    settings = load_settings()
    result = load_source(SAMPLES / "checking_sample.csv", "checking", settings.source_config("checking"))

    assert len(result.transactions) == 7

    paycheck = next(t for t in result.transactions if "PAYCHECK" in t.description)
    assert paycheck.amount == -3200.00  # deposit (raw positive) becomes negative: money received, not spend

    mortgage = next(t for t in result.transactions if "MORTGAGE" in t.description)
    assert mortgage.amount == 2100.00  # debit (raw negative) becomes positive: spend
