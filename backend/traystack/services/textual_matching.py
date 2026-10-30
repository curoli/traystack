"""Positive candidate search; no match here never establishes clause absence."""

import re
from bisect import bisect_left
from dataclasses import dataclass
from difflib import SequenceMatcher

from rapidfuzz.distance import Levenshtein

from traystack.textual_schemas import TextDifference

SCORER_VERSION = "levenshtein-max-length-v1"
CANDIDATE_POLICY = "literal-and-best-word-window-per-start-v1-nonoverlap"


class SearchTooBroad(ValueError):
    pass


@dataclass
class WorkBudget:
    # Reject the whole request instead of silently truncating candidates or documents.
    characters: int = 20_000_000
    windows: int = 2_000_000
    matches: int = 100_000

    def consume(self, kind, amount=1):
        remaining = getattr(self, kind) - amount
        if remaining < 0:
            raise SearchTooBroad(
                "Textual search is too broad. Use a higher threshold or a single document."
            )
        setattr(self, kind, remaining)


@dataclass(frozen=True, slots=True)
class Candidate:
    start: int
    end: int
    score: float


def find_passages(text: str, query: str, minimum: float, budget: WorkBudget) -> list[Candidate]:
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
