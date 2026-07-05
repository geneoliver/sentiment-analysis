from datetime import date

from src.config import load_settings, load_taxonomy
from src.dedupe import flag_possible_duplicates, flag_transfers
from src.models import Transaction


def test_flag_transfers_matches_keywords_on_both_sources():
    settings = load_settings()
    taxonomy = load_taxonomy()

    amex_credit = Transaction(date=date(2026, 6, 20), source="amex", description="AUTOPAY PAYMENT RECEIVED - THANK YOU", amount=-1200.0)
    checking_debit = Transaction(date=date(2026, 6, 6), source="checking", description="AMEX EPAYMENT ACH PMT", amount=1200.0)
    groceries = Transaction(date=date(2026, 6, 2), source="amex", description="TRADER JOE S #123", amount=84.32)

    transactions = [amex_credit, checking_debit, groceries]
    flag_transfers(transactions, settings, taxonomy)

    assert amex_credit.is_transfer is True
    assert amex_credit.subcategory == "Credit Card Payment"
    assert checking_debit.is_transfer is True
    assert groceries.is_transfer is False
    assert groceries.category is None  # untouched, left for tier 1/2 categorization


def test_possible_duplicate_flagged_across_sources_by_amount_and_date():
    settings = load_settings()

    a = Transaction(date=date(2026, 6, 10), source="amex", description="SOME CHARGE", amount=250.0)
    b = Transaction(date=date(2026, 6, 11), source="checking", description="UNRELATED DESC", amount=250.0)
    c = Transaction(date=date(2026, 6, 10), source="amex", description="DIFFERENT AMOUNT", amount=10.0)

    flag_possible_duplicates([a, b, c], settings)

    assert a.possible_duplicate is True
    assert b.possible_duplicate is True
    assert c.possible_duplicate is False
