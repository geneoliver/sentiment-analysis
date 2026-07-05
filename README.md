# Expense Categorization Pipeline

A personal, single-user pipeline that ingests American Express and checking
account CSV exports, categorizes each transaction (rules first, Claude API
for the rest), and produces a single `.xlsx` workbook for tax review and as
input to a separate income-modeling tool.

## Setup

Clone this branch to the project's home on your Mac:

```bash
git clone https://github.com/geneoliver/sentiment-analysis.git "/Users/gene/Library/CloudStorage/OneDrive-Personal/AA - Claude Cowork/Expense Categorization"
cd "/Users/gene/Library/CloudStorage/OneDrive-Personal/AA - Claude Cowork/Expense Categorization"
git checkout claude/expense-categorization-pipeline-t6mk1o
```

(If you already have a local clone elsewhere, just move/re-clone it to this
path — nothing in the pipeline hardcodes a location, it's all relative to
wherever the repo lives.)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes pytest; use requirements.txt for a plain install

export ANTHROPIC_API_KEY=sk-...       # or put it in a .env file at the project root
```

> **Note on the OneDrive location:** `inputs/`, `outputs/`, and
> `corrections/` hold personal financial data and are gitignored, but they
> will still sync to OneDrive since this folder is cloud-synced — that's
> presumably the point (backup/access across devices). One thing to keep
> out of the sync, though: `.venv/` generates thousands of small files that
> OneDrive doesn't need to churn through. Either create the venv elsewhere
> and symlink it in, or mark `.venv/` "Always keep on this device only" /
> excluded in OneDrive settings if you notice sync lag. For a tool you run
> once a month this is a minor nuisance at worst, not a blocker.

Without `ANTHROPIC_API_KEY` set, tier-2 classification is skipped
gracefully — unmatched transactions are marked `Uncategorized` / `pending`
instead of crashing the run, and show up in the review step.

## Usage

Drop your monthly exports into `inputs/` (gitignored — this is personal
financial data), then run the full pipeline:

```bash
python -m src.cli run --amex inputs/amex_2026-06.csv --checking inputs/checking_2026-06.csv
```

This writes everything to `outputs/<run-id>/` (run-id defaults to today's
date, override with `--run-id`):

- `raw.csv` — untouched, as-ingested data (becomes the Raw Data tab)
- `skipped_rows.csv` — malformed rows that couldn't be parsed, if any
- `categorized.csv` — the source of truth: every transaction with category, subcategory, confidence, and method
- `review.csv` — transactions below the confidence threshold or newly classified by Claude, for you to check
- `expenses_<run-id>.xlsx` — the final 5-tab workbook

Or double-click `run.command`, which picks up the newest `inputs/amex_*.csv`
and `inputs/checking_*.csv` automatically (creates a venv on first run).

### Steps can be re-run independently

```bash
python -m src.cli ingest --amex ... --checking ...   # parse CSVs -> raw.csv
python -m src.cli categorize                          # rules + Claude -> categorized.csv
python -m src.cli review-export                        # categorized.csv -> review.csv
#   ...edit the override_category / override_subcategory columns in review.csv...
python -m src.cli review-apply                          # merges overrides back, logs corrections
python -m src.cli summarize                              # categorized.csv -> final .xlsx
```

Repeated corrections (same merchant corrected `corrections.promote_after_n_corrections`
times, default 2) are automatically promoted into `config/learned_rules.yaml`
as permanent rules, and your last 25 corrections are included as examples
in every Claude API prompt — accuracy compounds over time with no retraining.

## Configuration

Everything you're likely to tune lives in `config/`, not in code:

- `config/taxonomy.yaml` — the category list (Essentials/Discretionary +
  subcategories) and the plain-English description of each, shown to the
  Claude API. Add/rename/remove categories here.
- `config/merchant_rules.yaml` — your hand-authored keyword → category
  rules (tier 1). The starter set is illustrative — replace it with your
  own recurring merchants.
- `config/learned_rules.yaml` — auto-generated from repeated corrections;
  don't hand-edit the structure, but feel free to delete entries.
- `config/settings.yaml` — CSV column mapping/sign convention per source,
  the Claude model, confidence threshold, transfer-detection keywords, and
  the correction-promotion threshold.

### Matching your actual bank exports

`config/settings.yaml` → `sources.amex` / `sources.checking` define which
CSV columns to read and how to normalize the amount sign. The pipeline
normalizes everything to **positive = money spent, negative = money
received** — once you have real exports, check a known charge and a known
deposit/payment against the output and adjust `amount_sign` per source if
the sign comes out backwards.

## Internal transfers

Paying the Amex bill from checking shows up as a transaction in both
exports but isn't spend. `dedupe.internal_transfer_keywords` in
`settings.yaml` flags anything matching (on either source) as an internal
transfer — kept in every tab for the audit trail, excluded from all spend
summaries. Anything not caught by a keyword but with a suspiciously close
amount/date match across the two sources is flagged `possible_duplicate`
for a manual look rather than silently excluded.

## Output workbook

| Tab | Contents |
|---|---|
| Raw Data | Untouched, as-ingested transactions from both sources |
| Categorized Transactions | Source of truth — every transaction with category, subcategory, confidence, method |
| Summary by Payee | Rolled up by merchant: total, count, date range |
| Summary by Category | Rolled up by category/subcategory |
| Essential vs Discretionary | Payee-level rollup split by top-level bucket |

## Tests

```bash
pytest
```

Covers ingest normalization/error-handling, transfer/duplicate flagging,
rule matching, the corrections/promotion loop, review apply, and the
summary rollups. `samples/` has small synthetic CSVs used as test fixtures
and for a manual end-to-end dry run:

```bash
python -m src.cli run --amex samples/amex_sample.csv --checking samples/checking_sample.csv --run-id sample
```

## Project structure

```
inputs/        # raw CSV downloads (gitignored)
outputs/       # generated workbooks + intermediate state per run (gitignored)
corrections/   # corrections.csv, the learning feedback log (gitignored)
config/        # taxonomy, merchant rules, pipeline settings (versioned)
src/           # pipeline source (versioned)
samples/       # small synthetic fixture CSVs (versioned)
tests/         # pytest suite (versioned)
```

## Known gaps / next steps

- The starter `config/merchant_rules.yaml` and category list are
  illustrative — swap in your real recurring merchants and confirm the
  taxonomy matches how you actually want things split for tax prep.
- Column mapping in `config/settings.yaml` is a best guess until validated
  against your actual Amex/checking export format.
