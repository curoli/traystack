import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from traystack.models import Artifact, PageText, ProcessingJob, RevisionText
from traystack.services.normalization import NORMALIZATION_VERSION
from traystack.services.storage import LocalStorage
from traystack.services.text_extraction import ProcessingError, extract_source

logger = logging.getLogger(__name__)


def claim_next_job(sessions: sessionmaker) -> UUID | None:
    with sessions.begin() as session:
        job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.status == "queued")
            .order_by(ProcessingJob.created_at, ProcessingJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.attempts += 1
        return job.id


def execute_job(job_id: UUID, sessions: sessionmaker, storage: LocalStorage) -> None:
    """Execute only a claimed run; publish artifacts, text and completion in one DB transaction."""
    try:
        with sessions() as session:
            job = session.get(ProcessingJob, job_id)
            if job is None or job.status != "running":
                return
            source = session.get(Artifact, job.source_artifact_id)
            if job.normalization_version != NORMALIZATION_VERSION:
                raise ProcessingError("unsupported_normalization_version")
            path = storage.path_for(source.storage_key)
            with path.open("rb") as stream:
                if (
                    path.stat().st_size != source.size_bytes
                    or hashlib.file_digest(stream, "sha256").hexdigest() != source.sha256
                ):
                    raise ProcessingError("source_integrity_check_failed")
            parameters, mime_type = dict(job.parameters), source.mime_type
            source_id, revision_id = source.id, job.revision_id
        # No transaction/row lock remains open during CPU-intensive extraction.
        result = extract_source(path, mime_type, parameters)
        structured = {
            "schema_version": 1,
            "revision_id": str(revision_id),
            "source_artifact_id": str(source_id),
            "processing_job_id": str(job_id),
            "normalization_version": NORMALIZATION_VERSION,
            "parameters": parameters,
            **result.as_dict(),
        }
        markdown = (
            "\n\n".join(f"## Page {page.page_number}\n\n{page.text}" for page in result.pages)
            + "\n"
        )
        outputs = [
            (
                "structured_json",
                "application/json",
                "json",
                json.dumps(structured, ensure_ascii=False, indent=2).encode("utf-8"),
            ),
            ("extracted_markdown", "text/markdown", "md", markdown.encode("utf-8")),
        ]
        stored = [
            (kind, mime, extension, storage.put_bytes(data, mime))
            for kind, mime, extension, data in outputs
        ]
        with sessions.begin() as session:
            job = session.scalar(
                select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
            )
            # Operator recovery may have failed this run; never publish its stale result.
            if job.status != "running":
                return
            job.processor_versions = result.processor_versions
            derived = []
            for kind, mime, extension, blob in stored:
                artifact = Artifact(
                    revision_id=revision_id,
                    source_artifact_id=source_id,
                    kind=kind,
                    mime_type=mime,
                    original_filename=f"{kind}-{job_id}.{extension}",
                    storage_key=blob.storage_key,
                    sha256=blob.sha256,
                    size_bytes=blob.size_bytes,
                    processor="traystack-extraction",
                    processor_version="0.2.0",
                    parameters={
                        **parameters,
                        "processing_job_id": str(job_id),
                        "normalization_version": NORMALIZATION_VERSION,
                        "processor_versions": result.processor_versions,
                    },
                )
                session.add(artifact)
                derived.append(artifact)
            current = session.get(RevisionText, revision_id)
            if current is None:
                current = RevisionText(revision_id=revision_id)
                session.add(current)
            current.source_artifact_id = source_id
            current.processing_job_id = job_id
            current.normalization_version = NORMALIZATION_VERSION
            current.plain_text = result.plain_text
            current.normalized_text = result.normalized_text
            current.status = result.status
            current.quality_status = result.quality_status
            current.quality_warnings = result.quality_warnings
            current.pages_total = len(result.pages)
            current.pages_processed = result.pages_processed
            current.pages_failed = len(result.pages) - result.pages_processed
            session.execute(delete(PageText).where(PageText.revision_id == revision_id))
            session.flush()
            session.add_all(
                PageText(
                    revision_id=revision_id,
                    page_number=page.page_number,
                    text=page.text,
                    normalized_text=page.normalized_text,
                    start_offset=page.start_offset,
                    end_offset=page.end_offset,
                    extraction_method=page.extraction_method,
                    status=page.status,
                    quality_status=page.quality_status,
                    quality_warnings=page.quality_warnings,
                    confidence=page.confidence,
                    layout_metadata=page.layout_metadata,
                )
                for page in result.pages
            )
            session.flush()
            job.result_artifact_ids = [str(artifact.id) for artifact in derived]
            job.status = "completed"
            job.finished_at = datetime.now(UTC)
        logger.info("Processing completed job_id=%s", job_id)
    except Exception as error:
        reason = str(error) if isinstance(error, ProcessingError) else "processing_failed"
        logger.error("Processing failed job_id=%s error_type=%s", job_id, type(error).__name__)
        with sessions.begin() as session:
            job = session.scalar(
                select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
            )
            if job is not None and job.status == "running":
                job.status, job.error_message = "failed", reason
                job.finished_at = datetime.now(UTC)


def run_once(sessions: sessionmaker, storage: LocalStorage) -> bool:
    job_id = claim_next_job(sessions)
    if job_id is None:
        return False
    execute_job(job_id, sessions, storage)
    return True
