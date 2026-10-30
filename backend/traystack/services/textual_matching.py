"""Positive candidate search; no match here never establishes clause absence."""

import math
import re
from bisect import bisect_left
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from rapidfuzz.distance import Levenshtein

from traystack.textual_schemas import TextDifference

SCORER_VERSION = "levenshtein-max-length-v1"
CANDIDATE_POLICY = "literal-and-best-word-window-per-start-v1-nonoverlap"


class SearchTooBroad(ValueError):
    def __init__(self, message, *, reason, resource, limit, observed):
        super().__init__(message)
        self.reason, self.resource = reason, resource
        self.limit, self.observed = limit, observed
        self.documents_inspected = 0

    def detail(self):
        return {
            "code": "textual_search_aborted",
            "reason": self.reason,
            "message": str(self),
            "resource": self.resource,
            "limit": self.limit,
            "observed_at_least": self.observed,
            "documents_inspected": self.documents_inspected,
            "results_complete": False,
        }


@dataclass
class WorkBudget:
    # Reject the whole request instead of silently truncating candidates or documents.
    characters: int = 20_000_000
    windows: int = 2_000_000
    matches: int = 100_000
    _initial: dict = field(init=False, repr=False)

    def __post_init__(self):
        self._initial = {kind: getattr(self, kind) for kind in ("characters", "windows", "matches")}

    def consume(self, kind, amount=1):
        remaining = getattr(self, kind) - amount
        if remaining < 0:
            raise SearchTooBroad(
                "The search exceeded its processing limit. Increase textual similarity or "
                "narrow the document selection.",
                reason="work_limit",
                resource=kind,
                limit=self._initial[kind],
                observed=self._initial[kind] - remaining,
            )
        setattr(self, kind, remaining)


@dataclass
class PassageBudget:
    total_limit: int = 2500
    document_limit: int = 250
    density_minimum: int = 100
    density_limit: float = 20  # Retained passages per 1,000 source characters.
    total: int = 0
    peak_document_count: int = 0

    def check(self, count, text_length, minimum):
        if count > self.document_limit:
            raise SearchTooBroad(
                "Too many candidate passages in one document. Increase textual similarity or "
                "use a more specific expression.",
                reason="document_passage_limit",
                resource="retained_passages_in_document",
                limit=self.document_limit,
                observed=count,
            )
        if self.total + count > self.total_limit:
            raise SearchTooBroad(
                "Too many candidate passages across the selection. Increase textual "
                "similarity or narrow the document selection.",
                reason="total_passage_limit",
                resource="retained_passages_total",
                limit=self.total_limit,
                observed=self.total + count,
            )
        density = count * 1000 / max(1, text_length)
        if minimum < 100 and count >= self.density_minimum and density >= self.density_limit:
            raise SearchTooBroad(
                "Candidate passages are too dense to review meaningfully. Increase textual "
                "similarity or add more context to the expression.",
                reason="dense_passages",
                resource="passages_per_1000_characters",
                limit=self.density_limit,
                observed=density,
            )

    def finish(self, count):
        self.total += count
        self.peak_document_count = max(self.peak_document_count, count)


@dataclass(frozen=True, slots=True)
class Candidate:
    start: int
    end: int
    score: float


def find_passages(
    text: str,
    query: str,
    minimum: float,
    budget: WorkBudget,
    passage_budget: PassageBudget | None = None,
) -> list[Candidate]:
    if not query or not math.isfinite(minimum) or not 0 < minimum <= 100:
        raise ValueError(
            "Textual matching requires a nonempty query and a threshold greater than 0 "
            "and at most 100"
        )
    passage_budget = passage_budget if passage_budget is not None else PassageBudget()
    budget.consume("characters", len(text))
    candidates = {}
    position = 0
    # Literal occurrences anywhere, including within words and across page boundaries.
    while True:
        start = text.find(query, position)
        if start < 0:
            break
        end = start + len(query)
        budget.consume("matches")
        candidates[start, end] = Candidate(start, end, 100.0)
        # Non-overlapping literal hits cannot be removed by approximate windows:
        # they already establish a lower bound on the final passage count.
        passage_budget.check(len(candidates), len(text), minimum)
        position = end  # Explicitly return non-overlapping literal occurrences.
    if minimum < 100:
        words = list(re.finditer(r"\S+", text))
        query_words = max(1, len(query.split()))
        tolerance = max(2, (query_words + 1) // 2)
        shortest = min(len(words), max(1, query_words - tolerance))
        longest = query_words + tolerance
        for index, word in enumerate(words):
            best = None
            for length in range(shortest, min(longest, len(words) - index) + 1):
                budget.consume("windows")
                start, end = word.start(), words[index + length - 1].end()
                if (start, end) in candidates:
                    continue
                passage = text[start:end]
                # A cheap length bound avoids computing an impossible score.
                if 100 * min(len(query), len(passage)) / max(len(query), len(passage)) < minimum:
                    continue
                score = 100 * Levenshtein.normalized_similarity(query, passage)
                if score >= minimum and (best is None or score > best.score):
                    best = Candidate(start, end, score)
            if best is not None:
                budget.consume("matches")
                candidates[best.start, best.end] = best

    # Highest score wins among overlapping windows; then earliest, then shortest.
    # Literal hits have priority. This removes near-duplicate windows, not source text.
    ranked = sorted(candidates.values(), key=lambda item: (-item.score, item.start, item.end))
    starts, accepted = [], []
    for candidate in ranked:
        index = bisect_left(starts, candidate.start)
        if index and accepted[index - 1].end > candidate.start:
            continue
        if index < len(accepted) and accepted[index].start < candidate.end:
            continue
        starts.insert(index, candidate.start)
        accepted.insert(index, candidate)
        passage_budget.check(len(accepted), len(text), minimum)
    passage_budget.finish(len(accepted))
    return sorted(accepted, key=lambda item: (-item.score, item.start, item.end))


def text_differences(query: str, passage: str) -> list[TextDifference]:
    # Compare words, punctuation, numbers and whitespace without hiding negations.
    tokens = r"\s+|\w+|[^\w\s]"
    query_tokens, passage_tokens = re.findall(tokens, query), re.findall(tokens, passage)
    return [
        TextDifference(
            kind=kind,
            query_text="".join(query_tokens[start:end]),
            passage_text="".join(passage_tokens[other_start:other_end]),
        )
        for kind, start, end, other_start, other_end in SequenceMatcher(
            None, query_tokens, passage_tokens, autojunk=False
        ).get_opcodes()
    ]
