"""Loads the YAML config that drives the pipeline (taxonomy, settings, rules).

Nothing in this module should ever need to change when you edit a .yaml
file under config/ — that's the point of keeping config out of code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> Any:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


@dataclass
class MerchantRule:
    keyword: str
    category: str
    subcategory: str
    origin: str = "manual"  # "manual" | "learned"


@dataclass
class Taxonomy:
    essentials: dict[str, str]          # subcategory -> description
    discretionary: dict[str, str]
    internal_transfer: dict[str, str]
    fallback_category: str

    def valid_subcategories(self) -> set[str]:
        return (
            set(self.essentials)
            | set(self.discretionary)
            | set(self.internal_transfer)
            | {self.fallback_category}
        )

    def top_level_for(self, subcategory: str) -> str | None:
        if subcategory in self.essentials:
            return "Essentials"
        if subcategory in self.discretionary:
            return "Discretionary"
        if subcategory in self.internal_transfer:
            return "Internal Transfer"
        return None

    def prompt_description(self) -> str:
        """Plain-English taxonomy description for the Claude API prompt."""
        lines = []
        for top, bucket in (("Essentials", self.essentials), ("Discretionary", self.discretionary)):
            lines.append(f"{top}:")
            for name, desc in bucket.items():
                lines.append(f"  - {name}: {desc.strip()}")
        return "\n".join(lines)


@dataclass
class Settings:
    raw: dict[str, Any]

    @property
    def inputs_dir(self) -> Path:
        return ROOT / self.raw["paths"]["inputs_dir"]

    @property
    def outputs_dir(self) -> Path:
        return ROOT / self.raw["paths"]["outputs_dir"]

    @property
    def corrections_dir(self) -> Path:
        return ROOT / self.raw["paths"]["corrections_dir"]

    def source_config(self, source: str) -> dict[str, Any]:
        return self.raw["sources"][source]

    @property
    def claude_model(self) -> str:
        return self.raw["claude"]["model"]

    @property
    def max_recent_corrections(self) -> int:
        return self.raw["claude"]["max_recent_corrections"]

    @property
    def claude_batch_size(self) -> int:
        return self.raw["claude"]["batch_size"]

    @property
    def low_confidence_threshold(self) -> float:
        return self.raw["review"]["low_confidence_threshold"]

    @property
    def internal_transfer_keywords(self) -> list[str]:
        return self.raw["dedupe"]["internal_transfer_keywords"]

    @property
    def amount_match_tolerance(self) -> float:
        return self.raw["dedupe"]["amount_match_tolerance"]

    @property
    def date_window_days(self) -> int:
        return self.raw["dedupe"]["date_window_days"]

    @property
    def promote_after_n_corrections(self) -> int:
        return self.raw["corrections"]["promote_after_n_corrections"]


def load_settings(path: Path | None = None) -> Settings:
    path = path or (ROOT / "config" / "settings.yaml")
    return Settings(raw=_load_yaml(path))


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    path = path or (ROOT / "config" / "taxonomy.yaml")
    data = _load_yaml(path)
    return Taxonomy(
        essentials={k: v.get("description", "") for k, v in (data.get("essentials") or {}).items()},
        discretionary={k: v.get("description", "") for k, v in (data.get("discretionary") or {}).items()},
        internal_transfer={k: v.get("description", "") for k, v in (data.get("internal_transfer") or {}).items()},
        fallback_category=data.get("fallback_category", "Uncategorized"),
    )


def _load_rules_file(path: Path, origin: str) -> list[MerchantRule]:
    if not path.exists():
        return []
    data = _load_yaml(path)
    rules = []
    for entry in data.get("rules") or []:
        rules.append(MerchantRule(
            keyword=entry["keyword"],
            category=entry["category"],
            subcategory=entry["subcategory"],
            origin=origin,
        ))
    return rules


def load_merchant_rules(settings: Settings) -> list[MerchantRule]:
    """Hand-authored rules, then auto-learned rules. Order doesn't affect
    matching priority (longest keyword always wins) but keeps the two
    sources visually distinct when debugging.
    """
    manual = _load_rules_file(ROOT / settings.raw["paths"]["merchant_rules_file"], origin="manual")
    learned = _load_rules_file(ROOT / settings.raw["paths"]["learned_rules_file"], origin="learned")
    return manual + learned
