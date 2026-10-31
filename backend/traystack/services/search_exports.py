"""Export frozen matches and current reviews from one read-only database snapshot."""

import csv
import io
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from traystack.review_schemas import ReviewFilter
from traystack.run_schemas import RunSummary
from traystack.services.search_runs import canonical, get_run, read_run

FORMULA_PREFIX = re.compile(r"^[\s\ufeff]*[=+\-@]")

CSV_FIELDS = [
    "row_type",
    "schema_version",
    "notice",
    "run_id",
    "run_name",
    "searched_at",
    "exported_at",
    "review_filter",
    "query",
    "effective_query",
    "mode",
    "minimum_textual_score",
    "minimum_semantic_score",
    "scope_documents",
    "exported_documents",
    "exported_passages",
    "unsearchable_documents",
    "document_id",
    "document_title",
    "revision_id",
    "revision_number",
    "processing_job_id",
    "source_artifact_id",
    "normalization_version",
    "coverage",
    "quality_status",
    "warnings",
    "occurrence_id",
    "page_reference",
    "page_numbers",
    "offset_basis",
    "start_offset",
    "end_offset",
    "matched_sha256",
    "matched_text",
    "context",
    "snippet_start_offset",
    "textual_score",
    "semantic_score",
    "semantic_cosine",
    "review_decision",
    "review_version",
    "review_updated_at",
    "review_at_capture",
    "review_version_at_capture",
    "review_updated_at_capture",
    "scorer_version",
    "scorer_library_version",
    "candidate_policy",
    "semantic_model",
    "semantic_pipeline",
    "semantic_score_version",
    "snapshot_sha256",
]


def export_run(session: Session, identity: UUID, review_filter: ReviewFilter) -> dict[str, Any]:
    # First operation on the fresh request session: names, matches and all review
    # decisions belong to one snapshot, even if another view saves while exporting.
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    session.execute(text("SET TRANSACTION READ ONLY"))
    exported_at = datetime.now(UTC)
    run = get_run(session, identity)
    result = read_run(session, identity, review_filter=review_filter, complete=True)
    body = result.model_dump(mode="json")
    for key in (
        "limit",
        "offset",
        "unsearchable_limit",
        "unsearchable_offset",
    ):
        body.pop(key)
    for group in body["results"]:
        group.pop("occurrence_limit")
        group.pop("occurrence_offset")
    return {
        "schema_version": 1,
        "exported_at": exported_at.isoformat(),
        "reviews": "Current shared decisions at export; review_at_capture is preserved separately.",
        "notice": "Positive matches are not proof of absence or legal equivalence. "
        "Unsearchable documents remain separate regardless of the review filter.",
        "run": {
            **RunSummary.model_validate(run).model_dump(mode="json"),
            "snapshot_version": run.snapshot_version,
            "snapshot_sha256": run.snapshot_sha256,
        },
        "request": run.request_json,
        "captured_scope": run.scope_json,
        "result": body,
    }


def spreadsheet_cell(value: Any) -> Any:
    """Preserve content in JSON; neutralize formula-like CSV text for spreadsheets."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        value = canonical(value).decode()
    if isinstance(value, str) and FORMULA_PREFIX.match(value):
        return "'" + value
    return value


def csv_export(payload: dict[str, Any]) -> bytes:
    result = payload["result"]
    semantic = result["semantic"] or {}
    common = {
        "schema_version": payload["schema_version"],
        "notice": payload["notice"],
        "run_id": result["run_id"],
        "run_name": result["run_name"],
        "searched_at": result["searched_at"],
        "exported_at": payload["exported_at"],
        "review_filter": result["review_filter"],
        "query": result["query"],
        "effective_query": result["effective_query"],
        "mode": result["mode"],
        "minimum_textual_score": result["minimum_score"],
        "minimum_semantic_score": result["minimum_semantic_score"],
        "scope_documents": result["summary"]["documents_total"],
        "exported_documents": result["total"],
        "exported_passages": result["summary"]["occurrences_total"],
        "unsearchable_documents": result["unsearchable_total"],
        "offset_basis": result["offset_basis"],
        "scorer_version": result["scorer_version"],
        "scorer_library_version": result["scorer_library_version"],
        "candidate_policy": result["candidate_policy"],
        "semantic_model": semantic.get("model"),
        "semantic_pipeline": semantic.get("pipeline"),
        "semantic_score_version": semantic.get("score_version"),
        "snapshot_sha256": payload["run"]["snapshot_sha256"],
    }
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
    writer.writeheader()

    def write(values):
        writer.writerow(
            {key: spreadsheet_cell(value) for key, value in {**common, **values}.items()}
        )

    def document_fields(document):
        return {
            "document_id": document["document_id"],
            "document_title": document["title"],
            **{
                key: document[key]
                for key in (
                    "revision_id",
                    "revision_number",
                    "processing_job_id",
                    "normalization_version",
                    "coverage",
                    "quality_status",
                    "warnings",
                )
            },
            "source_artifact_id": document["artifact_id"],
        }

    # A summary row retains provenance even when the selected filter has no matches.
    write({"row_type": "summary", "warnings": result["warnings"]})
    for group in result["results"]:
        for item in group["occurrences"]:
            write(
                {
                    "row_type": "passage",
                    **document_fields(group["document"]),
                    **{
                        key: item[key]
                        for key in (
                            "occurrence_id",
                            "page_reference",
                            "page_numbers",
                            "start_offset",
                            "end_offset",
                            "matched_sha256",
                            "matched_text",
                            "snippet_start_offset",
                            "semantic_score",
                            "semantic_cosine",
                        )
                    },
                    "context": item["snippet"],
                    "textual_score": item["score"],
                    "review_decision": item["review"]["decision"],
                    "review_version": item["review"]["version"],
                    "review_updated_at": item["review"]["updated_at"],
                    "review_at_capture": item["review_at_capture"]["decision"],
                    "review_version_at_capture": item["review_at_capture"]["version"],
                    "review_updated_at_capture": item["review_at_capture"]["updated_at"],
                }
            )
    for document in result["unsearchable"]:
        write({"row_type": "unsearchable", **document_fields(document)})
    return output.getvalue().encode("utf-8-sig")
