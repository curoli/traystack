"""Complete, immutable search snapshots; reads never run retrieval or embeddings."""

import copy
import hashlib
import json
from collections import Counter
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from traystack.models import ArchivedText, PassageReview, SearchRun, SearchRunSource
from traystack.review_schemas import ReviewCounts, ReviewOut
from traystack.schemas import PageOut, TextSummaryOut
from traystack.services.textual_matching import SearchTooBroad
from traystack.services.textual_search import textual_snapshot
from traystack.textual_schemas import TextualSearchRequest, TextualSearchResponse


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class RunCapture:
    def __init__(self, max_bytes=64_000_000, max_documents=10_000):
        self.scope = []
        self.sources = {}
        self.max_bytes, self.max_documents = max_bytes, max_documents
        self.bytes = 0

    def charge(self, value):
        self.bytes += len(canonical(value))
        if self.bytes > self.max_bytes:
            error = SearchTooBroad(
                "The complete saved search is too large. Narrow the document selection.",
                reason="snapshot_size_limit",
                resource="snapshot_bytes",
                limit=self.max_bytes,
                observed=self.bytes,
            )
            error.documents_inspected = len(self.scope)
            raise error

    def add_scope(self, document, searchable):
        value = {**document.model_dump(mode="json"), "searchable": searchable}
        self.scope.append(value)
        if len(self.scope) > self.max_documents:
            error = SearchTooBroad(
                "Too many documents for a saved search. Narrow the selection.",
                reason="snapshot_scope_limit",
                resource="snapshot_documents",
                limit=self.max_documents,
                observed=len(self.scope),
            )
            error.documents_inspected = len(self.scope)
            raise error
        self.charge(value)

    def add_source(self, index, pages):
        value = TextSummaryOut.model_validate(index).model_dump(mode="json")
        value.update(plain_text=index.plain_text, normalized_text=index.normalized_text, pages=[])
        for page in pages:
            # Preserve text/offsets/quality, not unused potentially huge word-bbox arrays.
            item = {
                key: getattr(page, key) for key in PageOut.model_fields if key != "layout_metadata"
            }
            item["layout_metadata"] = {}
            value["pages"].append(PageOut.model_validate(item).model_dump(mode="json"))
        self.charge(value)
        self.sources[index.processing_job_id] = value


def create_run(factory, payload, semantic_provider, max_bytes=64_000_000, max_documents=10_000):
    capture = RunCapture(max_bytes, max_documents)
    # The whole universe before the mutable review filter is frozen atomically.
    query = payload.search.model_copy(
        update={
            "review_filter": "all",
            "offset": 0,
            "occurrence_offset": 0,
            "unsearchable_offset": 0,
        }
    )
    with factory() as session:
        result = textual_snapshot(session, query, semantic_provider, capture=capture)
        body = result.model_dump(mode="json")
        capture.charge(body)
    request = payload.search.model_dump(mode="json")
    fingerprint = digest({"request": request, "scope": capture.scope, "result": body})
    with factory.begin() as session:
        if payload.parent_run_id and session.get(SearchRun, payload.parent_run_id) is None:
            raise HTTPException(404, "The original saved search does not exist")
        for job_id, source in capture.sources.items():
            fingerprint_source = digest(source)
            session.execute(
                insert(ArchivedText)
                .values(
                    processing_job_id=job_id,
                    revision_id=UUID(source["revision_id"]),
                    source_artifact_id=UUID(source["source_artifact_id"]),
                    payload=source,
                    sha256=fingerprint_source,
                )
                .on_conflict_do_nothing(index_elements=[ArchivedText.processing_job_id])
            )
            existing = session.get(ArchivedText, job_id)
            if existing.sha256 != fingerprint_source:
                raise HTTPException(
                    409, "A processing run changed without a new identity. Reprocess before saving."
                )
        run = SearchRun(
            name=(payload.name or "").strip() or " ".join(payload.search.query.split())[:160],
            query=payload.search.query,
            parent_run_id=payload.parent_run_id,
            request_json=request,
            result_json=body,
            scope_json=capture.scope,
            snapshot_sha256=fingerprint,
            searched_at=result.searched_at,
            result_documents=result.total,
            result_passages=result.summary.occurrences_total,
        )
        session.add(run)
        session.flush()
        session.add_all(
            SearchRunSource(run_id=run.id, processing_job_id=job) for job in capture.sources
        )
        identity = run.id
    # Return the requested first view, backed only by the committed snapshot.
    with factory() as session:
        return read_run(session, identity, payload.search)


def get_run(session, identity):
    run = session.get(SearchRun, identity)
    if run is None:
        raise HTTPException(404, "Saved search not found")
    if (
        run.snapshot_version != 1
        or digest({"request": run.request_json, "scope": run.scope_json, "result": run.result_json})
        != run.snapshot_sha256
    ):
        raise HTTPException(
            503, "Saved search integrity check failed; no new search was substituted"
        )
    return run


def read_run(session, identity, view=None, review_filter=None):
    run = get_run(session, identity)
    view = view or TextualSearchRequest.model_validate(run.request_json)
    state = review_filter or view.review_filter
    body = copy.deepcopy(run.result_json)
    document_id = str(view.document_id) if view.document_id else None
    if document_id and not any(item["document_id"] == document_id for item in run.scope_json):
        # A previously empty scoped search stays empty, too.
        if document_id != run.request_json.get("document_id"):
            raise HTTPException(422, "This document is outside the saved search scope")
    groups = [
        item
        for item in body["results"]
        if not document_id or item["document"]["document_id"] == document_id
    ]
    ids = [item["occurrence_id"] for group in groups for item in group["occurrences"]]
    reviews = (
        {
            row.occurrence_id: row
            for row in session.scalars(
                select(PassageReview).where(PassageReview.occurrence_id.in_(ids))
            )
        }
        if ids
        else {}
    )
    counts, retained = Counter(), []
    for group in groups:
        local, occurrences = Counter(), []
        for item in group["occurrences"]:
            item["review_at_capture"] = item["review"]
            row = reviews.get(item["occurrence_id"])
            item["review"] = (
                ReviewOut.model_validate(row).model_dump(mode="json")
                if row is not None and row.matched_sha256 == item["matched_sha256"]
                else ReviewOut().model_dump(mode="json")
            )
            decision = item["review"]["decision"]
            local[decision] += 1
            counts[decision] += 1
            if state == "all" or state == decision:
                occurrences.append(item)
        if occurrences:
            group.update(
                review_counts=ReviewCounts(**local).model_dump(),
                occurrence_total=len(occurrences),
                occurrence_limit=view.occurrence_limit,
                occurrence_offset=view.occurrence_offset,
                occurrences=occurrences[
                    view.occurrence_offset : view.occurrence_offset + view.occurrence_limit
                ],
            )
            retained.append(group)
    scope = [row for row in run.scope_json if not document_id or row["document_id"] == document_id]
    unknown = [
        row for row in body["unsearchable"] if not document_id or row["document_id"] == document_id
    ]
    body.update(
        captured_review_filter=run.request_json["review_filter"],
        run_id=str(run.id),
        run_name=run.name,
        parent_run_id=str(run.parent_run_id) if run.parent_run_id else None,
        scope_total=len(run.scope_json),
        review_filter=state,
        review_counts=ReviewCounts(**counts).model_dump(),
        document_id=document_id,
        total=len(retained),
        limit=view.limit,
        offset=view.offset,
        results=retained[view.offset : view.offset + view.limit],
        unsearchable=unknown[
            view.unsearchable_offset : view.unsearchable_offset + view.unsearchable_limit
        ],
        unsearchable_total=len(unknown),
        unsearchable_limit=view.unsearchable_limit,
        unsearchable_offset=view.unsearchable_offset,
        summary={
            "documents_total": len(scope),
            "documents_searched": sum(row["searchable"] for row in scope),
            "documents_with_matches": len(retained),
            "documents_without_matches": sum(row["searchable"] for row in scope) - len(retained),
            "documents_unsearchable": len(unknown),
            "occurrences_total": sum(row["occurrence_total"] for row in retained),
        },
    )
    return TextualSearchResponse.model_validate(body)


def archived_source(session, run_id, job_id):
    if session.get(SearchRunSource, (run_id, job_id)) is None:
        raise HTTPException(404, "Source is not part of this saved search")
    source = session.get(ArchivedText, job_id)
    if source is None or digest(source.payload) != source.sha256:
        raise HTTPException(
            503, "Saved source integrity check failed; current text was not substituted"
        )
    return source.payload
