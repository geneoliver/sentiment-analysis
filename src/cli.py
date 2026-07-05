"""Command-line entry point.

Usage:
    python -m src.cli run --amex inputs/amex_2026-06.csv --checking inputs/checking_2026-06.csv
    python -m src.cli ingest --amex ... --checking ...
    python -m src.cli categorize
    python -m src.cli review-export
    python -m src.cli review-apply
    python -m src.cli summarize

All subcommands accept --run-id (default: today's date, e.g. 2026-07-05) so
a given month's data has one working directory under outputs/<run-id>/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from src import pipeline
from src.config import load_settings, load_taxonomy


def _add_run_id_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", default=pipeline.default_run_id(), help="Identifies this run's working directory under outputs/ (default: today's date)")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Expense categorization pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ingest = subparsers.add_parser("ingest", help="Parse Amex + checking CSVs into the normalized schema")
    p_ingest.add_argument("--amex", required=True, type=Path)
    p_ingest.add_argument("--checking", required=True, type=Path)
    _add_run_id_arg(p_ingest)

    p_categorize = subparsers.add_parser("categorize", help="Run rule-based + Claude API categorization")
    _add_run_id_arg(p_categorize)

    p_review_export = subparsers.add_parser("review-export", help="Export low-confidence/new transactions for manual review")
    _add_run_id_arg(p_review_export)

    p_review_apply = subparsers.add_parser("review-apply", help="Apply your edits from the review file and log corrections")
    _add_run_id_arg(p_review_apply)

    p_summarize = subparsers.add_parser("summarize", help="Build the final .xlsx workbook")
    _add_run_id_arg(p_summarize)
    p_summarize.add_argument("--output", type=Path, default=None)

    p_run = subparsers.add_parser("run", help="Full pipeline: ingest -> categorize -> review-export -> summarize")
    p_run.add_argument("--amex", required=True, type=Path)
    p_run.add_argument("--checking", required=True, type=Path)
    _add_run_id_arg(p_run)

    args = parser.parse_args(argv)

    settings = load_settings()
    taxonomy = load_taxonomy()

    if args.command == "ingest":
        pipeline.step_ingest(args.amex, args.checking, settings, args.run_id)
    elif args.command == "categorize":
        pipeline.step_categorize(settings, taxonomy, args.run_id)
    elif args.command == "review-export":
        pipeline.step_review_export(settings, args.run_id)
    elif args.command == "review-apply":
        pipeline.step_review_apply(settings, taxonomy, args.run_id)
    elif args.command == "summarize":
        pipeline.step_summarize(settings, args.run_id, args.output)
    elif args.command == "run":
        pipeline.run_full_pipeline(args.amex, args.checking, settings, taxonomy, args.run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
