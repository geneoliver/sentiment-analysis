"""Rolls up categorized transactions into the three summary tabs.

Internal transfers (`is_transfer=True`) are excluded from every summary
here — they're money moving between your own accounts, not spend — but
they remain visible in the Raw Data and Categorized Transactions tabs for
the audit trail.
"""
from __future__ import annotations

import pandas as pd

from src.corrections import normalize_pattern

PAYEE_SUMMARY_COLUMNS = ["payee", "category", "subcategory", "total_amount", "transaction_count", "first_date", "last_date"]
CATEGORY_SUMMARY_COLUMNS = ["category", "subcategory", "total_amount", "transaction_count", "first_date", "last_date"]
ESSENTIAL_DISCRETIONARY_COLUMNS = ["category", "payee", "total_amount", "transaction_count", "first_date", "last_date"]


def _spend_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["is_transfer"] != True].copy()  # noqa: E712 - pandas boolean mask


def _with_payee(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["payee"] = df["description"].apply(normalize_pattern)
    return df


def summary_by_payee(df: pd.DataFrame) -> pd.DataFrame:
    spend = _with_payee(_spend_only(df))
    if spend.empty:
        return pd.DataFrame(columns=PAYEE_SUMMARY_COLUMNS)

    rows = []
    for payee, group in spend.groupby("payee"):
        dominant = group["subcategory"].value_counts().idxmax()
        dominant_category = group.loc[group["subcategory"] == dominant, "category"].iloc[0]
        rows.append({
            "payee": payee,
            "category": dominant_category,
            "subcategory": dominant,
            "total_amount": round(group["amount"].sum(), 2),
            "transaction_count": len(group),
            "first_date": group["date"].min(),
            "last_date": group["date"].max(),
        })
    return pd.DataFrame(rows, columns=PAYEE_SUMMARY_COLUMNS).sort_values("total_amount", ascending=False).reset_index(drop=True)


def summary_by_category(df: pd.DataFrame) -> pd.DataFrame:
    spend = _spend_only(df)
    if spend.empty:
        return pd.DataFrame(columns=CATEGORY_SUMMARY_COLUMNS)

    grouped = spend.groupby(["category", "subcategory"]).agg(
        total_amount=("amount", "sum"),
        transaction_count=("amount", "count"),
        first_date=("date", "min"),
        last_date=("date", "max"),
    ).reset_index()
    grouped["total_amount"] = grouped["total_amount"].round(2)
    return grouped.sort_values(["category", "total_amount"], ascending=[True, False]).reset_index(drop=True)


def summary_essential_vs_discretionary(df: pd.DataFrame) -> pd.DataFrame:
    spend = _with_payee(_spend_only(df))
    if spend.empty:
        return pd.DataFrame(columns=ESSENTIAL_DISCRETIONARY_COLUMNS)

    grouped = spend.groupby(["category", "payee"]).agg(
        total_amount=("amount", "sum"),
        transaction_count=("amount", "count"),
        first_date=("date", "min"),
        last_date=("date", "max"),
    ).reset_index()
    grouped["total_amount"] = grouped["total_amount"].round(2)
    return grouped.sort_values(["category", "total_amount"], ascending=[True, False]).reset_index(drop=True)
