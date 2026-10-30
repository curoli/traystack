import { useEffect, useRef, useState } from "react";
import { formatDate } from "../format";
import {
  getText,
  retryJob,
  startProcessing,
  type Revision,
  type TextContent,
  type SearchPageLocation,
} from "../api";
import {
  coverageLabel,
  qualityLabel,
  statusLabel,
  warningLabel,
} from "./processingLabels";

export default function ProcessingDetails({
  revision,
  onUpdated,
  requestedPage,
}: {
  revision: Revision;
  requestedPage?: SearchPageLocation;
  onUpdated: () => Promise<void>;
}) {
  const originals = revision.artifacts.filter(
    (artifact) => artifact.kind === "original",
  );
  const [sourceId, setSourceId] = useState(
    originals.length === 1 ? originals[0].id : "",
  );
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState<TextContent | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [textBusy, setTextBusy] = useState(false);
  const [loadedPageRequest, setLoadedPageRequest] = useState<number | null>(
    null,
  );
  const viewerRef = useRef<HTMLElement>(null);
  const index = revision.text_index;
  const latest = revision.jobs[0];
  const pending = revision.jobs.some((job) =>
    ["queued", "running"].includes(job.status),
  );
  const page = text?.pages.find((page) => page.page_number === pageNumber);

  useEffect(() => {
    setText(null);
    setPageNumber(1);
  }, [index?.processing_job_id]);
  useEffect(() => {
    if (!requestedPage) {
      setTextBusy(false);
      return;
    }
    if (index?.processing_job_id !== requestedPage.processingJobId) {
      setTextBusy(false);
      setError(
        "The selected text has changed since the search. Please run the search again.",
      );
      return;
    }
    let active = true;
    setTextBusy(true);
    setError("");
    getText(revision.id)
      .then((content) => {
        if (!active) return;
        if (content.processing_job_id !== requestedPage.processingJobId) {
          setError(
            "The text has been reprocessed. Please run the search again.",
          );
        } else {
          setText(content);
          setPageNumber(requestedPage.pageNumber);
          setLoadedPageRequest(requestedPage.requestId);
        }
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error ? error.message : "Text unavailable.",
          );
      })
      .finally(() => {
        if (active) setTextBusy(false);
      });
    return () => {
      active = false;
    };
  }, [requestedPage, revision.id, index?.processing_job_id]);

  useEffect(() => {
    // App first navigates to the document heading. Only the completed page
    // request may move focus onward, including when the same run is reopened.
    if (
      !requestedPage ||
      loadedPageRequest !== requestedPage.requestId ||
      text?.processing_job_id !== requestedPage.processingJobId
    )
      return;
    viewerRef.current?.focus({ preventScroll: true });
    viewerRef.current?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [requestedPage, loadedPageRequest, text?.processing_job_id]);

  async function submit(retryId?: string) {
    setError("");
    setBusy(true);
    try {
      if (retryId) await retryJob(retryId);
      else await startProcessing(revision.id, sourceId, manual);
      await onUpdated();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not start processing.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function showText() {
    setTextBusy(true);
    setError("");
    try {
      setText(await getText(revision.id));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Text unavailable.");
    } finally {
      setTextBusy(false);
    }
  }
  return (
    <div className="processing">
      <div className="processing-controls">
        <div>
          <label htmlFor={`source-${revision.id}`}>Processing source</label>
          <select
            id={`source-${revision.id}`}
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            disabled={pending || busy}
          >
            <option value="" disabled>
              Select an original
            </option>
            {originals.map((artifact) => (
              <option key={artifact.id} value={artifact.id}>
                {artifact.original_filename}
              </option>
            ))}
          </select>
        </div>
        <button
          className="primary"
          disabled={pending || busy || !sourceId}
          onClick={() => submit()}
        >
          {pending
            ? statusLabel[revision.processing_status]
            : busy
              ? "Submitting …"
              : index
                ? "Reprocess"
                : "Start processing"}
        </button>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={manual}
          onChange={(event) => setManual(event.target.checked)}
          disabled={pending || busy}
        />
        <span>
          Flag this run for manual review
          <small>
            An existing review flag on the original is always retained.
          </small>
        </span>
      </label>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {pending && (
        <p role="status" className="job-progress">
          {statusLabel[revision.processing_status]} – status updates
          automatically.
        </p>
      )}
      {latest?.status === "failed" && (
        <div role="alert" className="message error">
          <strong>Latest run failed.</strong> Error code: {latest.error_message}
          .{" "}
          {index
            ? "The previously selected text and its source information are preserved."
            : "No selected text is available for this revision yet."}
        </div>
      )}
      {index && (
        <div
          className={`quality-panel ${index.quality_status === "no_known_issue" ? "" : "review"}`}
        >
          <h3>{coverageLabel[index.status]}</h3>
          <p>
            {index.pages_processed} of {index.pages_total} pages processed ·{" "}
            {index.pages_failed} without complete text
          </p>
          <strong>{qualityLabel[index.quality_status]}</strong>
          <p className="fineprint">
            Complete processing does not guarantee correctly recognized words.
            The assessment applies to the extracted text.
          </p>
          {index.quality_warnings.length > 0 && (
            <ul>
              {index.quality_warnings.map((reason) => (
                <li key={reason}>{warningLabel(reason)}</li>
              ))}
            </ul>
          )}
          <p className="identifier">
            Selected run: {index.processing_job_id}
            <br />
            Source: {index.source_artifact_id}
            <br />
            Normalization: {index.normalization_version}
          </p>
          <button className="secondary" disabled={textBusy} onClick={showText}>
            {textBusy ? "Loading text …" : "View page text"}
          </button>
        </div>
      )}
      {text && (
        <section
          ref={viewerRef}
          tabIndex={-1}
          className="page-viewer"
          aria-label="Extracted page text"
        >
          <div className="section-heading">
            <label htmlFor={`page-${revision.id}`}>Page</label>
            <select
              id={`page-${revision.id}`}
              value={pageNumber}
              onChange={(event) => setPageNumber(Number(event.target.value))}
            >
              {text.pages.map((page) => (
                <option value={page.page_number} key={page.page_number}>
                  Page {page.page_number}
                </option>
              ))}
            </select>
            <button className="secondary" onClick={() => setText(null)}>
              Close text
            </button>
          </div>
          {page && (
            <>
              <p className="fineprint">
                {page.extraction_method === "ocr"
                  ? "Tesseract OCR"
                  : page.extraction_method === "embedded_pdf_text"
                    ? "Embedded PDF text"
                    : "Extraction unavailable"}
                {page.confidence !== null &&
                  ` · Mean OCR word score: ${page.confidence.toFixed(1)}/100 (not a probability)`}
              </p>
              <pre className="text-preview">
                {page.text || "No text was detected on this page."}
              </pre>
            </>
          )}
        </section>
      )}
      {revision.jobs.length > 0 && (
        <details className="job-history">
          <summary>Processing runs ({revision.jobs.length})</summary>
          <ol>
            {revision.jobs.map((job) => (
              <li key={job.id}>
                <div className="section-heading">
                  <strong>{statusLabel[job.status]}</strong>
                  {job.status === "failed" && (
                    <button
                      className="secondary"
                      onClick={() => submit(job.id)}
                      disabled={busy || pending}
                    >
                      Retry as a new run
                    </button>
                  )}
                </div>
                <p className="identifier">
                  {job.id} · {formatDate(job.created_at)}
                  {job.retry_of_job_id && (
                    <>
                      <br />
                      Retry of {job.retry_of_job_id}
                    </>
                  )}
                </p>
                {job.error_message && (
                  <p className="job-error">Error code: {job.error_message}</p>
                )}
                <details>
                  <summary>Methods and parameters</summary>
                  <pre className="text-preview">
                    {JSON.stringify(
                      {
                        processor_versions: job.processor_versions,
                        normalization_version: job.normalization_version,
                        parameters: job.parameters,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
