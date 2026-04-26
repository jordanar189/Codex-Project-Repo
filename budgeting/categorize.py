"""Rule-based merchant categorization.

A rule is a (lowercase) substring pattern → category. Categorization picks the
longest matching pattern (most specific wins). Income transactions (amount > 0)
are auto-assigned to the Income category and not flagged for review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class Rule:
    pattern: str  # stored lowercase
    category_id: int
    category_name: str


@dataclass(frozen=True)
class CategorizationResult:
    category_id: Optional[int]
    category_name: Optional[str]
    needs_review: bool
    matched_pattern: Optional[str]


def categorize(
    merchant: str,
    amount: float,
    rules: Iterable[Rule],
    income_category_id: Optional[int] = None,
    income_category_name: str = "Income",
) -> CategorizationResult:
    """Apply rules to a (merchant, amount) pair.

    - Income (amount > 0) → Income category, no review needed.
    - Expense (amount < 0) → longest matching rule wins.
    - No match → uncategorized, needs review.
    """
    if amount > 0 and income_category_id is not None:
        return CategorizationResult(
            category_id=income_category_id,
            category_name=income_category_name,
            needs_review=False,
            matched_pattern=None,
        )

    haystack = (merchant or "").lower()
    best: Optional[Rule] = None
    for rule in rules:
        if rule.pattern and rule.pattern in haystack:
            if best is None or len(rule.pattern) > len(best.pattern):
                best = rule

    if best is None:
        return CategorizationResult(
            category_id=None,
            category_name=None,
            needs_review=True,
            matched_pattern=None,
        )

    return CategorizationResult(
        category_id=best.category_id,
        category_name=best.category_name,
        needs_review=False,
        matched_pattern=best.pattern,
    )
