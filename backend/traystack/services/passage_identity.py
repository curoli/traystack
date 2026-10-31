"""Stable identity of an explicit passage and effective search expression."""

import hashlib

from traystack.services.textual_matching import CANDIDATE_POLICY, SCORER_VERSION


def occurrence_identity(job_id, mode, phrase, start, end):
    return hashlib.sha256(
        f"{job_id}|{mode}|{SCORER_VERSION}|{CANDIDATE_POLICY}|{phrase}|{start}|{end}".encode()
    ).hexdigest()


def text_fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()
