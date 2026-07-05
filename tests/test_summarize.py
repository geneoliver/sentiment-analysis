import pandas as pd

from src.summarize import summary_by_category, summary_by_payee, summary_essential_vs_discretionary


def _sample_df():
    return pd.DataFrame([
        {"date": "2026-06-02", "source": "amex", "description": "TRADER JOE S #123", "amount": 84.32,
         "category": "Essentials", "subcategory": "Groceries", "is_transfer": False},
        {"date": "2026-06-18", "source": "amex", "description": "TRADER JOE S #456", "amount": 58.21,
         "category": "Essentials", "subcategory": "Groceries", "is_transfer": False},
        {"date": "2026-06-03", "source": "amex", "description": "NETFLIX.COM", "amount": 15.49,
         "category": "Discretionary", "subcategory": "Entertainment", "is_transfer": False},
        {"date": "2026-06-06", "source": "checking", "description": "AMEX EPAYMENT ACH PMT", "amount": 1200.0,
         "category": "Internal Transfer", "subcategory": "Credit Card Payment", "is_transfer": True},
    ])


def test_summary_by_payee_groups_and_excludes_transfers():
    result = summary_by_payee(_sample_df())
    assert "AMEX EPAYMENT ACH PMT" not in result["payee"].apply(lambda p: "AMEX" in p and "EPAYMENT" in p).values

    trader_joes = result[result["payee"].str.contains("TRADER JOE")]
    assert len(trader_joes) == 1
    assert trader_joes.iloc[0]["total_amount"] == 142.53
    assert trader_joes.iloc[0]["transaction_count"] == 2


def test_summary_by_category_excludes_transfers():
    result = summary_by_category(_sample_df())
    assert "Internal Transfer" not in result["category"].values
    groceries_row = result[result["subcategory"] == "Groceries"].iloc[0]
    assert groceries_row["total_amount"] == 142.53


def test_summary_essential_vs_discretionary_splits_by_top_level():
    result = summary_essential_vs_discretionary(_sample_df())
    assert set(result["category"].unique()) == {"Essentials", "Discretionary"}
    essentials_total = result[result["category"] == "Essentials"]["total_amount"].sum()
    assert essentials_total == 142.53
