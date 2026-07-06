"""Manual review step: surface low-confidence/new classifications, then take
your edits back in and log them as corrections.

This operates on the categorized-transactions CSV produced by the
categorize step (outputs/<run_id>/categorized.csv), which stays the running
source of truth. The review file is a companion export — edit the two
override columns and re-run `review-apply`.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import Settings, Taxonomy, add_subcategory_to_taxonomy
from src.corrections import promote_rules, record_correction
from src.models import METHOD_MANUAL, Transaction

REVIEW_METHODS_ALWAYS_SURFACED = {"claude", "error", "pending"}


def export_for_review(categorized_path: Path, review_path: Path, settings: Settings) -> int:
    df = pd.read_csv(categorized_path)
    threshold = settings.low_confidence_threshold

    needs_review = df[
        (df["confidence"].fillna(0) < threshold) | (df["method"].isin(REVIEW_METHODS_ALWAYS_SURFACED))
    ].copy()
    needs_review["override_category"] = ""
    needs_review["override_subcategory"] = ""

    columns = [
        "row_id", "date", "source", "description", "amount",
        "category", "subcategory", "confidence", "method", "notes",
        "override_category", "override_subcategory",
    ]
    needs_review = needs_review[columns]
    review_path.parent.mkdir(parents=True, exist_ok=True)
    needs_review.to_csv(review_path, index=False)
    return len(needs_review)


def apply_review(categorized_path: Path, review_path: Path, settings: Settings, taxonomy: Taxonomy) -> int:
    categorized_df = pd.read_csv(categorized_path)
    review_df = pd.read_csv(review_path)

    valid_subcategories = taxonomy.valid_subcategories()
    categorized_df = categorized_df.set_index("row_id", drop=False)

    def _clean(value: object) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip()

    applied = 0
    for _, row in review_df.iterrows():
        override_subcategory = _clean(row.get("override_subcategory"))
        if not override_subcategory:
            continue
        override_category = _clean(row.get("override_category")) or (
            taxonomy.top_level_for(override_subcategory) or ""
        )
        if not override_category:
            raise ValueError(
                f"Unknown subcategory '{override_subcategory}' for row_id={row['row_id']}. "
                f"Either add it to config/taxonomy.yaml or fill in override_category explicitly."
            )

        if override_subcategory not in valid_subcategories:
            add_subcategory_to_taxonomy(override_subcategory, override_category, settings.taxonomy_file)

        row_id = row["row_id"]
        if row_id not in categorized_df.index:
            continue

        categorized_df.loc[row_id, "category"] = override_category
        categorized_df.loc[row_id, "subcategory"] = override_subcategory
        categorized_df.loc[row_id, "method"] = METHOD_MANUAL
        categorized_df.loc[row_id, "confidence"] = 1.0

        tx = Transaction(
            date=pd.to_datetime(row["date"]).date(),
            source=row["source"],
            description=row["description"],
            amount=float(row["amount"]),
            row_id=row_id,
        )
        record_correction(settings, tx, override_category, override_subcategory)
        applied += 1

    categorized_df.to_csv(categorized_path, index=False)
    if applied:
        promote_rules(settings)
    return applied
