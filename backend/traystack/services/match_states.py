"""Three-state projection and per-search automatic confirmation policy."""


def project_review(review, occurrence, policy):
    current = dict(review)
    # Legacy deferred decisions remain stored, but are pending in the new UI.
    if current["decision"] == "later":
        current["decision"] = "unreviewed"
    textual = policy.get("auto_confirm_textual")
    semantic = policy.get("auto_confirm_semantic")
    automatic = (
        current["version"] == 0
        and textual is not None
        and semantic is not None
        and (
            occurrence.get("raw_textual_score")
            if occurrence.get("raw_textual_score") is not None
            else occurrence["score"]
        )
        >= textual
        and occurrence.get("semantic_score") is not None
        and (
            occurrence.get("raw_semantic_score")
            if occurrence.get("raw_semantic_score") is not None
            else occurrence["semantic_score"]
        )
        >= semantic
    )
    if automatic:
        current["decision"] = "keep"
    return current, automatic
