"""Orchestrates the four independently re-runnable pipeline steps:
ingest -> categorize -> review -> summarize.

Each run is identified by a `run_id` (default: today's date) and keeps its
intermediate state under outputs/<run_id>/ so any step can be re-run on its
own without redoing the others:

  outputs/<run_id>/raw.csv           - normalized ingest output (Raw Data tab)
  outputs/<run_id>/skipped_rows.csv  - malformed rows skipped during ingest
  outputs/<run_id>/categorized.csv   - source of truth (Categorized Transactions tab)
  outputs/<run_id>/review.csv        - companion file for manual review
  outputs/<run_id>/expenses_<run_id>.xlsx - final workbook
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import Settings, Taxonomy, load_settings, load_taxonomy
from src.dedupe import flag_possible_duplicates, flag_transfers
from src.categorize.claude_classifier import categorize_with_claude
from src.categorize.rules import apply_rules
from src.ingest.csv_source import load_source
from src.models import Transaction
from src import review as review_step
from src import summarize as summarize_step
from src import workbook as workbook_step

RAW_FILENAME = "raw.csv"
SKIPPED_FILENAME = "skipped_rows.csv"
CATEGORIZED_FILENAME = "categorized.csv"
REVIEW_FILENAME = "review.csv"


def default_run_id() -> str:
    return date.today().isoformat()


def run_dir(settings: Settings, run_id: str) -> Path:
    d = settings.outputs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


RAW_COLUMNS = ["row_id", "date", "source", "description", "amount", "raw_category"]


def _transactions_to_df(transactions: list[Transaction]) -> pd.DataFrame:
    return pd.DataFrame([tx.to_dict() for tx in transactions])


def _transactions_to_raw_df(transactions: list[Transaction]) -> pd.DataFrame:
    """Only the as-ingested columns — this is the audit-trail Raw Data tab,
    so it stays untouched by anything categorize/review/summarize do.
    """
    df = _transactions_to_df(transactions)
    return df[RAW_COLUMNS]


def _df_to_transactions(df: pd.DataFrame) -> list[Transaction]:
    return [Transaction.from_dict(row.dropna().to_dict()) for _, row in df.iterrows()]


def step_ingest(amex_path: Path, checking_path: Path, settings: Settings, run_id: str) -> Path:
    all_transactions: list[Transaction] = []
    all_skipped = []

    for name, path in (("amex", amex_path), ("checking", checking_path)):
        result = load_source(path, name, settings.source_config(name))
        all_transactions.extend(result.transactions)
        for skipped in result.skipped:
            all_skipped.append({"source": name, "line_number": skipped.line_number, "reason": skipped.reason, "raw": skipped.raw})
        print(f"[ingest] {name}: {len(result.transactions)} transactions, {len(result.skipped)} skipped", file=sys.stderr)

    out_dir = run_dir(settings, run_id)
    raw_path = out_dir / RAW_FILENAME
    _transactions_to_raw_df(all_transactions).to_csv(raw_path, index=False)

    if all_skipped:
        skipped_path = out_dir / SKIPPED_FILENAME
        pd.DataFrame(all_skipped).to_csv(skipped_path, index=False)
        print(f"[ingest] {len(all_skipped)} malformed rows logged to {skipped_path}", file=sys.stderr)

    return raw_path


def step_categorize(settings: Settings, taxonomy: Taxonomy, run_id: str) -> Path:
    out_dir = run_dir(settings, run_id)
    raw_path = out_dir / RAW_FILENAME
    if not raw_path.exists():
        raise FileNotFoundError(f"No raw data for run '{run_id}' — run 'ingest' first ({raw_path} not found)")

    df = pd.read_csv(raw_path)
    transactions = _df_to_transactions(df)

    flag_transfers(transactions, settings, taxonomy)
    flag_possible_duplicates(transactions, settings)
    apply_rules(transactions, settings, taxonomy)
    categorize_with_claude(transactions, settings, taxonomy)

    categorized_path = out_dir / CATEGORIZED_FILENAME
    _transactions_to_df(transactions).to_csv(categorized_path, index=False)

    uncategorized = sum(1 for tx in transactions if tx.method in ("error", "pending"))
    print(f"[categorize] {len(transactions)} transactions categorized, {uncategorized} need attention", file=sys.stderr)
    return categorized_path


def step_review_export(settings: Settings, run_id: str) -> Path:
    out_dir = run_dir(settings, run_id)
    categorized_path = out_dir / CATEGORIZED_FILENAME
    review_path = out_dir / REVIEW_FILENAME
    count = review_step.export_for_review(categorized_path, review_path, settings)
    print(f"[review] {count} transactions need review -> {review_path}", file=sys.stderr)
    return review_path


def step_review_apply(settings: Settings, taxonomy: Taxonomy, run_id: str) -> int:
    out_dir = run_dir(settings, run_id)
    categorized_path = out_dir / CATEGORIZED_FILENAME
    review_path = out_dir / REVIEW_FILENAME
    applied = review_step.apply_review(categorized_path, review_path, settings, taxonomy)
    print(f"[review] applied {applied} overrides and logged corrections", file=sys.stderr)
    return applied


def step_summarize(settings: Settings, run_id: str, output_path: Path | None = None) -> Path:
    out_dir = run_dir(settings, run_id)
    raw_path = out_dir / RAW_FILENAME
    categorized_path = out_dir / CATEGORIZED_FILENAME
    if not categorized_path.exists():
        raise FileNotFoundError(f"No categorized data for run '{run_id}' — run 'categorize' first")

    raw_df = pd.read_csv(raw_path)
    categorized_df = pd.read_csv(categorized_path)

    by_payee = summarize_step.summary_by_payee(categorized_df)
    by_category = summarize_step.summary_by_category(categorized_df)
    by_essential_discretionary = summarize_step.summary_essential_vs_discretionary(categorized_df)

    output_path = output_path or (out_dir / f"expenses_{run_id}.xlsx")
    workbook_step.build_workbook(output_path, raw_df, categorized_df, by_payee, by_category, by_essential_discretionary)
    print(f"[summarize] workbook written to {output_path}", file=sys.stderr)
    return output_path


def run_full_pipeline(amex_path: Path, checking_path: Path, settings: Settings, taxonomy: Taxonomy, run_id: str) -> Path:
    step_ingest(amex_path, checking_path, settings, run_id)
    step_categorize(settings, taxonomy, run_id)
    step_review_export(settings, run_id)
    return step_summarize(settings, run_id)
