import math
import random

from reference_matching import reference_find_passages

from traystack.services.textual_matching import (
    PassageBudget,
    SearchTooBroad,
    WorkBudget,
    find_passages,
)


def outcome(matcher, text, query, minimum, windows=2000, matches=100):
    budget = WorkBudget(characters=5000, windows=windows, matches=matches)
    passages = PassageBudget(document_limit=20, density_minimum=8)
    try:
        result = matcher(text, query, minimum, budget, passages)
        answer = [(item.start, item.end, item.score) for item in result]
    except SearchTooBroad as error:
        answer = error.detail()
    return answer, (budget.characters, budget.windows, budget.matches), passages.total


def test_frozen_baseline_matches_across_unicode_boundaries_overlaps_and_work_limits():
    rng = random.Random(20261031)
    words = [
        "shall",
        "not",
        "disclose",
        "confidential",
        "informatlon",
        "500",
        "5000",
        "Acme",
        "Beta",
        "Straße",
        "strasse",
        "café",
        "cafe\u0301",
        "😀",
        "𐐀",
        "---",
        "a",
        "x" * 300,
    ]
    cases = [
        ("abcde abcdZ", "abcde", score)
        for score in [80, math.nextafter(80, 0), math.nextafter(80, 100)]
    ]
    for _ in range(500):
        text = " ".join(rng.choices(words, k=rng.randint(1, 45)))
        query = " ".join(rng.choices(words[:-1], k=rng.randint(1, 8)))
        score = rng.choice([5e-324, 0.01, 1, 30, 60, 75, 80, 85, 92.3, 99.999, 100])
        cases.append((text, query, score))
    cases += [("target " * 30, "target", score) for score in [70, 85, 100]]
    cases += [("\tA\nB\fC 😀target-suffix", "A B C", 40), ("x", "long phrase", 1)]
    for text, query, minimum in cases:
        for windows, matches in [(2000, 100), (5, 100), (2000, 2)]:
            assert outcome(find_passages, text, query, minimum, windows, matches) == outcome(
                reference_find_passages, text, query, minimum, windows, matches
            )


def test_long_impossible_words_do_not_change_candidate_offsets_or_budget():
    text = ("x" * 1000 + " ") * 3 + "The buyer pays EUR 5000 within thirty days."
    query = "The buyer pays EUR 500 within thirty days."
    assert outcome(find_passages, text, query, 85) == outcome(
        reference_find_passages, text, query, 85
    )
