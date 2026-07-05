import pandas as pd

from src.config import load_settings, load_taxonomy
from src.review import apply_review, export_for_review


def _write_categorized(path):
    pd.DataFrame([
        {"row_id": "r1", "date": "2026-06-10", "source": "amex", "description": "SQ *LOCAL COFFEE ROASTERS",
         "amount": 6.75, "category": "Uncategorized", "subcategory": "Uncategorized", "confidence": 0.0,
         "method": "pending", "is_transfer": False, "possible_duplicate": False, "notes": "no API key"},
        {"row_id": "r2", "date": "2026-06-14", "source": "checking", "description": "ZELLE TO J SMITH",
         "amount": 75.0, "category": "Uncategorized", "subcategory": "Uncategorized", "confidence": 0.0,
         "method": "pending", "is_transfer": False, "possible_duplicate": False, "notes": "no API key"},
    ]).to_csv(path, index=False)


def test_apply_review_ignores_untouched_rows_with_blank_overrides(tmp_path):
    settings = load_settings()
    settings.raw["paths"]["corrections_dir"] = str(tmp_path / "corrections")
    taxonomy = load_taxonomy()

    categorized_path = tmp_path / "categorized.csv"
    review_path = tmp_path / "review.csv"
    _write_categorized(categorized_path)
    export_for_review(categorized_path, review_path, settings)

    # Simulate editing only one row in a spreadsheet/text editor and saving,
    # leaving the rest of the override columns blank (as a real CSV edit
    # would, not a pandas assignment that could mask dtype quirks).
    import csv
    rows = list(csv.DictReader(open(review_path)))
    for row in rows:
        if row["row_id"] == "r1":
            row["override_category"] = "Discretionary"
            row["override_subcategory"] = "Dining Out"
    with open(review_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    applied = apply_review(categorized_path, review_path, settings, taxonomy)
    assert applied == 1

    result = pd.read_csv(categorized_path).set_index("row_id")
    assert result.loc["r1", "subcategory"] == "Dining Out"
    assert result.loc["r1", "method"] == "manual"
    # r2 was left blank in the review file and must not be touched.
    assert result.loc["r2", "subcategory"] == "Uncategorized"
    assert result.loc["r2", "method"] == "pending"
