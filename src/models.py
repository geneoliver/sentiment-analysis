"""Common normalized transaction schema shared by every pipeline step.

Sign convention: `amount` is positive for money spent (a charge/debit) and
negative for money received (a credit, refund, or payment). Ingest is
responsible for normalizing raw CSV values into this convention.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date as Date
from typing import Any, Optional

SOURCE_AMEX = "amex"
SOURCE_CHECKING = "checking"

METHOD_RULE = "rule"
METHOD_LEARNED_RULE = "learned_rule"
METHOD_CORRECTION = "correction"
METHOD_CLAUDE = "claude"
METHOD_MANUAL = "manual"
METHOD_ERROR = "error"
METHOD_PENDING = "pending"


@dataclass
class Transaction:
    date: Date
    source: str
    description: str
    amount: float
    raw_category: Optional[str] = None

    row_id: str = ""

    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: Optional[float] = None
    method: Optional[str] = None

    is_transfer: bool = False
    possible_duplicate: bool = False

    notes: str = ""

    def __post_init__(self) -> None:
        if not self.row_id:
            key = f"{self.date}|{self.source}|{self.description}|{self.amount}"
            self.row_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transaction":
        d = dict(d)
        if isinstance(d.get("date"), str):
            d["date"] = Date.fromisoformat(d["date"])
        return cls(**d)
