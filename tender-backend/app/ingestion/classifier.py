"""Keyword-based classification of tender titles.

Ported from the production n8n workflow, which deliberately replaced an
LLM-based classifier with local keyword scoring: no API cost, no rate limits,
and reproducible results.

How the scoring works:

  * A title is matched against every category's keyword list.
  * Each match adds the keyword's length to that category's score, so longer
    and more specific terms weigh more. "cyber security training" therefore
    lands in Cyber Security (14 characters) rather than Training & Consultancy
    (8 characters).
  * Short ASCII abbreviations (4 characters or fewer) must match on word
    boundaries, otherwise "erp" would match "interpret" and "ai" would match
    "maintenance".
  * The highest-scoring category wins, but only if the evidence is strong
    enough: either two separate keyword hits, or a single hit of at least
    eight characters. This is what stops a lone generic word from
    miscategorising a notice.
  * Confidence is the score over 22, capped at 1.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

# A single keyword hit only counts if it is at least this long.
MIN_SINGLE_KEYWORD_LENGTH = 8
# Otherwise we need at least this many separate hits.
MIN_HITS = 2
# Score at which confidence reaches 1.0.
CONFIDENCE_DIVISOR = 22
# Keywords this short must match whole words, not substrings.
SHORT_KEYWORD_LENGTH = 4

_ASCII_KEYWORD = re.compile(r"^[a-z0-9-]+$")


@dataclass(frozen=True)
class Classification:
    category_id: int
    category_name: str
    confidence: Decimal
    score: int
    hits: tuple[str, ...]


class _PreparedCategory:
    """A category with its keywords compiled ahead of time.

    Compiling the word-boundary patterns once rather than per title matters:
    there are well over a thousand keywords, and a full scrape classifies
    thousands of notices.
    """

    __slots__ = ("id", "name", "plain", "patterns")

    def __init__(self, category_id: int, name: str, keywords: list[str]):
        self.id = category_id
        self.name = name
        self.plain: list[str] = []
        self.patterns: list[tuple[str, re.Pattern]] = []

        for raw in keywords:
            keyword = " ".join((raw or "").split()).lower()
            if not keyword:
                continue
            if len(keyword) <= SHORT_KEYWORD_LENGTH and _ASCII_KEYWORD.match(keyword):
                self.patterns.append(
                    (
                        keyword,
                        re.compile(
                            rf"(^|[^a-z0-9]){re.escape(keyword)}([^a-z0-9]|$)"
                        ),
                    )
                )
            else:
                self.plain.append(keyword)


class Classifier:
    """Build once from the categories table, then classify many titles."""

    def __init__(self, categories: list[tuple[int, str, list[str]]]):
        self._categories = [
            _PreparedCategory(cid, name, keywords) for cid, name, keywords in categories
        ]

    @property
    def keyword_count(self) -> int:
        return sum(len(c.plain) + len(c.patterns) for c in self._categories)

    def classify(self, title: str | None) -> Classification | None:
        """Return the best category, or None if nothing matched convincingly."""
        if not title:
            return None

        text = title.lower()
        best: _PreparedCategory | None = None
        best_score = 0
        best_hits: list[str] = []

        for category in self._categories:
            score = 0
            hits: list[str] = []

            for keyword in category.plain:
                if keyword in text:
                    score += len(keyword)
                    hits.append(keyword)

            for keyword, pattern in category.patterns:
                if pattern.search(text):
                    score += len(keyword)
                    hits.append(keyword)

            if score > best_score:
                best, best_score, best_hits = category, score, hits

        if best is None:
            return None

        # Require real evidence. A single short keyword is usually noise.
        if len(best_hits) < MIN_HITS:
            if max(len(h) for h in best_hits) < MIN_SINGLE_KEYWORD_LENGTH:
                return None

        confidence = min(Decimal(1), Decimal(best_score) / Decimal(CONFIDENCE_DIVISOR))
        return Classification(
            category_id=best.id,
            category_name=best.name,
            confidence=round(confidence, 3),
            score=best_score,
            hits=tuple(best_hits),
        )