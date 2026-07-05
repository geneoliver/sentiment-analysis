"""Parses Amex and checking-account CSV exports into the common Transaction schema.

Bank CSV exports are inconsistent (extra columns, blank trailer rows, stray
commas in descriptions, occasional malformed rows). This module is
deliberately defensive: a bad row is skipped and recorded rather than
crashing the whole ingest run.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any

from dateutil import parser as dateutil_parser

from src.models import Transaction

VALID_SIGN_MODES = {"charge_positive", "debit_positive", "debit_negative"}


@dataclass
class SkippedRow:
    line_number: int
    reason: str
    raw: dict[str, Any]


@dataclass
class IngestResult:
    transactions: list[Transaction]
    skipped: list[SkippedRow] = field(default_factory=list)


def _parse_date(raw: str, date_format: str | None) -> Date:
    raw = raw.strip()
    if date_format:
        return Date.fromisoformat(_strftime_to_isoformat(raw, date_format))
    return dateutil_parser.parse(raw).date()


def _strftime_to_isoformat(raw: str, date_format: str) -> str:
    import datetime
    return datetime.datetime.strptime(raw, date_format).date().isoformat()


def _parse_amount(raw: str, sign_mode: str) -> float:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    value = float(cleaned)
    if negative:
        value = -value

    if sign_mode in ("charge_positive", "debit_positive"):
        return value
    if sign_mode == "debit_negative":
        return -value
    raise ValueError(f"Unknown amount_sign mode: {sign_mode}")


def load_source(path: Path, source_name: str, source_cfg: dict[str, Any]) -> IngestResult:
    """Load one CSV export into normalized Transactions.

    `source_cfg` is the `sources.<name>` block from config/settings.yaml —
    it tells us which columns to read and how to interpret the amount sign.
    """
    sign_mode = source_cfg["amount_sign"]
    if sign_mode not in VALID_SIGN_MODES:
        raise ValueError(f"Invalid amount_sign '{sign_mode}' for source '{source_name}'")

    date_col = source_cfg["date_column"]
    desc_col = source_cfg["description_column"]
    amount_col = source_cfg["amount_column"]
    category_col = source_cfg.get("category_column")
    date_format = source_cfg.get("date_format")

    transactions: list[Transaction] = []
    skipped: list[SkippedRow] = []

    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):  # header is line 1
            if row is None or all((v is None or str(v).strip() == "") for v in row.values()):
                continue  # blank trailer row, common in bank exports
            try:
                if date_col not in row or amount_col not in row or desc_col not in row:
                    raise ValueError("missing expected column(s)")

                tx_date = _parse_date(row[date_col], date_format)
                amount = _parse_amount(row[amount_col], sign_mode)
                description = (row[desc_col] or "").strip()
                if not description:
                    raise ValueError("empty description")
                raw_category = (row.get(category_col) or "").strip() or None if category_col else None

                transactions.append(Transaction(
                    date=tx_date,
                    source=source_name,
                    description=description,
                    amount=amount,
                    raw_category=raw_category,
                ))
            except Exception as exc:  # noqa: BLE001 - intentionally broad, this is a per-row skip
                skipped.append(SkippedRow(line_number=line_number, reason=str(exc), raw=dict(row)))

    return IngestResult(transactions=transactions, skipped=skipped)
