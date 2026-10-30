"""Explain query-dependent search risk without inventing a calibrated safe threshold."""

import re
from decimal import Decimal, localcontext

from traystack.services.normalization import normalize_for_search
from traystack.textual_schemas import QueryNotice, TextualAssessment, TextualAssessmentRequest

GUIDANCE_VERSION = "query-risk-v1"
COMMON_WORDS = set(
    "a an the and or of to in for is are be shall must may not with by on at as that this "
    "der die das ein eine und oder von zu im in ist sind mit fuer für nicht des dem den".split()
)


def assess_query(request: TextualAssessmentRequest) -> TextualAssessment:
    phrase = normalize_for_search(request.query) if request.mode == "normalized" else request.query
    words = re.findall(r"[^\W_]+", phrase.casefold())
    content = sum(char.isalnum() for char in phrase)
    # Exact decimal arithmetic avoids presenting 80% of ten characters as one edit.
    score = Decimal(str(request.minimum_score))
    with localcontext() as context:
        context.prec = max(28, -score.as_tuple().exponent + 8)
        edits = int(Decimal(len(phrase)) * (100 - score) / 100)
    notices = []

    def warn(code, message):
        notices.append(QueryNotice(code=code, message=message))

    if content < 8:
        warn(
            "short_query",
            "This expression has very few letters or digits and may occur in many contexts.",
        )
    permits_insertion = score * (len(phrase) + 1) <= 100 * len(phrase)
    if content < 12 and (edits >= 1 or permits_insertion):
        warn(
            "short_query_edits",
            "Allowing character changes in a short expression can change its identity. "
            "Consider a higher textual threshold.",
        )
    if words and all(word in COMMON_WORDS for word in words):
        warn(
            "common_words",
            "This expression contains only common English/German words. Many unrelated "
            "passages may qualify, even at a high score.",
        )
    if not content:
        warn(
            "punctuation_query",
            "Punctuation alone provides little context for identifying a passage.",
        )
    if content and sum(char.isdigit() for char in phrase) * 2 >= content:
        warn(
            "numeric_query",
            "This expression is mainly numeric and can occur inside longer amounts, dates "
            "or identifiers. Inspect context; approximate edits can change the value.",
        )
    if edits >= 3 and (request.minimum_score < 75 or edits >= 20):
        warn(
            "large_edit_budget",
            f"At this threshold, an equal-length passage may differ by up to {edits} "
            f"character edits. Many of those changes could be meaningful.",
        )
    if len(words) <= 2 and content >= 8 and request.minimum_score < 85:
        warn(
            "short_phrase_threshold",
            "A permissive threshold for a one- or two-word expression can match "
            "unrelated wording. Add context or raise the threshold.",
        )
    return TextualAssessment(
        policy_version=GUIDANCE_VERSION,
        effective_query=phrase,
        comparison_characters=len(phrase),
        content_characters=content,
        word_count=len(words),
        equal_length_edit_budget=edits,
        warnings=notices,
    )
