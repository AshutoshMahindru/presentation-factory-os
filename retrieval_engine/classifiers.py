from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Protocol


QueryClass = str


@dataclass(frozen=True)
class QueryClassification:
    query_classification: QueryClass
    confidence: float
    reason: str


class RetrievalQueryClassifier(Protocol):
    def classify(self, query: str) -> QueryClassification:
        """Return a deterministic routing class and confidence for a query."""


@dataclass(frozen=True)
class ClassifierProfile:
    query_classification: QueryClass
    examples: tuple[str, ...]


class DeterministicRoutingClassifier:
    """Small local classifier based on class exemplars and vector similarity."""

    DEFAULT_PROFILES: tuple[ClassifierProfile, ...] = (
        ClassifierProfile(
            query_classification="financial",
            examples=(
                "revenue margin irr payback unit economics forecast model",
                "cash runway burn rate sensitivity downside bookings",
                "enterprise bookings slip runway sensitivity",
                "valuation ebitda multiple forecast model scenario",
                "pricing gross margin contribution profit and loss",
            ),
        ),
        ClassifierProfile(
            query_classification="strategic",
            examples=(
                "market size tam competitive positioning evidence claim",
                "defensibility moat incumbent response risk thesis",
                "moat against incumbent retaliation",
                "go to market strategy buyer segment adoption",
                "contradiction between source claim and market evidence",
            ),
        ),
        ClassifierProfile(
            query_classification="narrative",
            examples=(
                "story arc opening hook proof points investor ask",
                "slide sequence narrative flow objection handling",
                "executive storyline decision framing closing",
                "messaging hierarchy tension resolution",
            ),
        ),
        ClassifierProfile(
            query_classification="visual",
            examples=(
                "slide layout chart legibility information density",
                "visual design page composition whitespace hierarchy",
                "diagram rendering screenshot visual qa",
                "reduce clutter on comparison page and make the slide easier to scan",
                "table formatting color contrast axis label",
            ),
        ),
    )

    STOPWORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "for",
            "from",
            "how",
            "if",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "our",
            "show",
            "the",
            "to",
            "use",
            "what",
            "with",
        }
    )

    TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

    def __init__(
        self,
        profiles: tuple[ClassifierProfile, ...] | None = None,
        min_similarity: float = 0.12,
        min_margin: float = 0.025,
    ) -> None:
        self.profiles = profiles or self.DEFAULT_PROFILES
        self.min_similarity = min_similarity
        self.min_margin = min_margin
        self._profile_vectors = {
            profile.query_classification: self._vectorize(" ".join(profile.examples))
            for profile in self.profiles
        }

    def classify(self, query: str) -> QueryClassification:
        query_vector = self._vectorize(query)
        if not query_vector:
            return self._unknown("No classifiable query content was provided.")

        scores = {
            query_class: self._cosine_similarity(query_vector, profile_vector)
            for query_class, profile_vector in self._profile_vectors.items()
        }
        ranked_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_class, best_score = ranked_scores[0]
        runner_up_score = ranked_scores[1][1] if len(ranked_scores) > 1 else 0.0
        margin = best_score - runner_up_score

        if best_score < self.min_similarity or (
            margin < self.min_margin and best_score < self.min_similarity * 1.5
        ):
            return self._unknown(
                "No routing profile cleared the deterministic similarity threshold."
            )

        confidence = min(0.95, 0.50 + best_score + min(0.20, margin))
        return QueryClassification(
            query_classification=best_class,
            confidence=round(confidence, 3),
            reason=(
                f"Best local profile was {best_class} "
                f"(similarity={best_score:.3f}, margin={margin:.3f})."
            ),
        )

    def _unknown(self, reason: str) -> QueryClassification:
        return QueryClassification(
            query_classification="unknown",
            confidence=0.35,
            reason=reason,
        )

    def _vectorize(self, text: str) -> Counter[str]:
        tokens = [
            self._stem(token)
            for token in self.TOKEN_PATTERN.findall(text.lower())
            if token not in self.STOPWORDS
        ]
        vector: Counter[str] = Counter()

        for token in tokens:
            vector[f"token:{token}"] += 1.0
            for ngram in self._char_ngrams(token):
                vector[f"char:{ngram}"] += 0.18

        for left, right in zip(tokens, tokens[1:]):
            vector[f"bigram:{left} {right}"] += 1.35

        return vector

    def _stem(self, token: str) -> str:
        for suffix in ("ization", "ations", "tion", "ing", "ed", "s"):
            if len(token) > len(suffix) + 3 and token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    def _char_ngrams(self, token: str) -> tuple[str, ...]:
        if len(token) < 5:
            return ()
        return tuple(token[index : index + 4] for index in range(len(token) - 3))

    def _cosine_similarity(
        self, left: Mapping[str, float], right: Mapping[str, float]
    ) -> float:
        numerator = sum(weight * right.get(feature, 0.0) for feature, weight in left.items())
        left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
        right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)


class QueryClassifier(DeterministicRoutingClassifier):
    """Backward-compatible default classifier used by RetrievalRouter."""
