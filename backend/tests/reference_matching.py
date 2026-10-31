"""Frozen pre-optimization matcher from merged PR #11 (45d49f3).

Independent baseline for exact output and work-budget regression checks.
"""

import math
import re
from bisect import bisect_left

from rapidfuzz.distance import Levenshtein

from traystack.services.textual_matching import Candidate, PassageBudget, WorkBudget


def reference_find_passages(
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
