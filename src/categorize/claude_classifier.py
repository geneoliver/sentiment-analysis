"""Tier 2 categorization: ask the Claude API to classify whatever tier 1
(rules + corrections) couldn't resolve.

The taxonomy is passed in plain English (from config/taxonomy.yaml) along
with your most recent manual corrections as worked examples, so the model
benefits from your past overrides without any retraining. Classification is
requested via forced tool-use so the response is structured JSON, not
free-text to parse.

Designed to fail soft: a missing API key, a network error, or a malformed
response marks the affected transactions as "Uncategorized" with method
"error"/"pending" rather than crashing the run — they'll simply show up in
the review step for a manual look.
"""
from __future__ import annotations

import os
from typing import Any

from src.config import Settings, Taxonomy
from src.corrections import load_recent_corrections
from src.models import METHOD_CLAUDE, METHOD_ERROR, METHOD_PENDING, Transaction

CLASSIFY_TOOL_NAME = "classify_transactions"


def _classify_tool_schema(valid_subcategories: list[str]) -> dict[str, Any]:
    return {
        "name": CLASSIFY_TOOL_NAME,
        "description": "Classify each transaction into exactly one taxonomy subcategory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "classifications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row_id": {"type": "string"},
                            "subcategory": {"type": "string", "enum": valid_subcategories},
                            "confidence": {
                                "type": "number",
                                "description": "0.0-1.0 confidence this is the right subcategory",
                            },
                            "rationale": {"type": "string", "description": "One short sentence."},
                        },
                        "required": ["row_id", "subcategory", "confidence"],
                    },
                }
            },
            "required": ["classifications"],
        },
    }


def _build_prompt(batch: list[Transaction], taxonomy: Taxonomy, corrections: list) -> str:
    lines = [
        "You are classifying personal financial transactions into a fixed taxonomy.",
        "",
        "Taxonomy:",
        taxonomy.prompt_description(),
        "",
    ]
    if corrections:
        lines.append("Examples of how I've corrected past classifications (follow these patterns):")
        for record in corrections:
            lines.append(f'  - "{record.description}" -> {record.subcategory}')
        lines.append("")

    lines.append("Classify each of the following transactions. Use the classify_transactions tool.")
    for tx in batch:
        lines.append(f"  - row_id={tx.row_id} | description=\"{tx.description}\" | amount={tx.amount:.2f} | source={tx.source}")

    return "\n".join(lines)


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _mark(tx: Transaction, taxonomy: Taxonomy, method: str, note: str) -> None:
    tx.category = taxonomy.top_level_for(taxonomy.fallback_category) or "Uncategorized"
    tx.subcategory = taxonomy.fallback_category
    tx.method = method
    tx.confidence = 0.0
    tx.notes = note


def categorize_with_claude(
    transactions: list[Transaction],
    settings: Settings,
    taxonomy: Taxonomy,
    client: Any = None,
) -> None:
    pending = [tx for tx in transactions if tx.category is None]
    if not pending:
        return

    if client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            for tx in pending:
                _mark(tx, taxonomy, METHOD_PENDING, "ANTHROPIC_API_KEY not set; skipped Claude classification")
            return
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

    valid_subcategories = sorted(taxonomy.valid_subcategories())
    tool_schema = _classify_tool_schema(valid_subcategories)
    recent_corrections = load_recent_corrections(settings)

    by_row_id = {tx.row_id: tx for tx in pending}

    for batch in _chunk(pending, settings.claude_batch_size):
        prompt = _build_prompt(batch, taxonomy, recent_corrections)
        try:
            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=4096,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": CLASSIFY_TOOL_NAME},
                messages=[{"role": "user", "content": prompt}],
            )
            tool_use = next(b for b in response.content if getattr(b, "type", None) == "tool_use")
            classifications = tool_use.input["classifications"]
        except Exception as exc:  # noqa: BLE001 - API/network/parsing failures must not crash the run
            for tx in batch:
                _mark(tx, taxonomy, METHOD_ERROR, f"Claude classification failed: {exc}")
            continue

        seen_row_ids = set()
        for item in classifications:
            row_id = item.get("row_id")
            tx = by_row_id.get(row_id)
            if tx is None:
                continue
            seen_row_ids.add(row_id)
            subcategory = item.get("subcategory")
            if subcategory not in valid_subcategories:
                _mark(tx, taxonomy, METHOD_ERROR, f"Claude returned unknown subcategory: {subcategory!r}")
                continue
            tx.category = taxonomy.top_level_for(subcategory)
            tx.subcategory = subcategory
            tx.confidence = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
            tx.method = METHOD_CLAUDE
            tx.notes = item.get("rationale", "")

        for tx in batch:
            if tx.row_id not in seen_row_ids and tx.category is None:
                _mark(tx, taxonomy, METHOD_ERROR, "Claude response did not include this transaction")
