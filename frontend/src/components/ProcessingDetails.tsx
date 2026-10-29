import { useEffect, useState } from "react";
import {
  getText,
  retryJob,
  startProcessing,
  type Revision,
  type TextContent,
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
}: {
  revision: Revision;
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
  async function submit(retryId?: string) {
    setError("");
    setBusy(true);
    try {
      if (retryId) await retryJob(retryId);
      else await startProcessing(revision.id, sourceId, manual);
      await onUpdated();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Verarbeitung konnte nicht gestartet werden.",
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
      setError(
        error instanceof Error ? error.message : "Text nicht verfügbar.",
      );
    } finally {
      setTextBusy(false);
    }
  }
  return (
    <div className="processing">
      <div className="processing-controls">
        <div>
          <label htmlFor={`source-${revision.id}`}>
            Quelle für die Verarbeitung
          </label>
          <select
            id={`source-${revision.id}`}
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            disabled={pending || busy}
          >
            <option value="" disabled>
              Original auswählen
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
              ? "Wird angefordert …"
              : index
                ? "Erneut verarbeiten"
                : "Verarbeitung starten"}
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
          Diesen Lauf manuell prüfen
          <small>
            Eine bestehende Prüfvormerkung des Originals wird immer übernommen.
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
          {statusLabel[revision.processing_status]} – der Status wird
          automatisch aktualisiert.
        </p>
      )}
      {latest?.status === "failed" && (
        <div role="alert" className="message error">
          <strong>Neuester Lauf fehlgeschlagen.</strong> Fehlercode:{" "}
          {latest.error_message}.{" "}
          {index
            ? "Der bisher ausgewählte Text und seine Herkunft bleiben erhalten."
            : "Für diese Revision ist noch kein ausgewählter Text verfügbar."}
        </div>
      )}
      {index && (
        <div
          className={`quality-panel ${index.quality_status === "no_known_issue" ? "" : "review"}`}
        >
          <h3>{coverageLabel[index.status]}</h3>
          <p>
            {index.pages_processed} von {index.pages_total} Seiten verarbeitet ·{" "}
            {index.pages_failed} ohne vollständigen Text
          </p>
          <strong>{qualityLabel[index.quality_status]}</strong>
          <p className="fineprint">
            Vollständige Verarbeitung ist keine Garantie für korrekt erkannte
            Wörter. Die Bewertung betrifft den extrahierten Text.
          </p>
          {index.quality_warnings.length > 0 && (
            <ul>
              {index.quality_warnings.map((reason) => (
                <li key={reason}>{warningLabel(reason)}</li>
              ))}
            </ul>
          )}
          <p className="identifier">
            Ausgewählter Lauf: {index.processing_job_id}
            <br />
            Quelle: {index.source_artifact_id}
            <br />
            Normalisierung: {index.normalization_version}
          </p>
          <button className="secondary" disabled={textBusy} onClick={showText}>
            {textBusy ? "Text wird geladen …" : "Seitentext ansehen"}
          </button>
        </div>
      )}
      {text && (
        <section className="page-viewer" aria-label="Extrahierter Seitentext">
          <div className="section-heading">
            <label htmlFor={`page-${revision.id}`}>Seite</label>
            <select
              id={`page-${revision.id}`}
              value={pageNumber}
              onChange={(event) => setPageNumber(Number(event.target.value))}
            >
              {text.pages.map((page) => (
                <option value={page.page_number} key={page.page_number}>
                  Seite {page.page_number}
                </option>
              ))}
            </select>
            <button className="secondary" onClick={() => setText(null)}>
              Text schließen
            </button>
          </div>
          {page && (
            <>
              <p className="fineprint">
                {page.extraction_method === "ocr"
                  ? "Tesseract OCR"
                  : page.extraction_method === "embedded_pdf_text"
                    ? "PDF-Textschicht"
                    : "Extraktion nicht verfügbar"}
                {page.confidence !== null &&
                  ` · Mittlerer OCR-Wortscore: ${page.confidence.toFixed(1)}/100 (keine Wahrscheinlichkeit)`}
              </p>
              <pre className="text-preview">
                {page.text || "Für diese Seite wurde kein Text erkannt."}
              </pre>
            </>
          )}
        </section>
      )}
      {revision.jobs.length > 0 && (
        <details className="job-history">
          <summary>Verarbeitungsläufe ({revision.jobs.length})</summary>
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
                      Als neuen Lauf wiederholen
                    </button>
                  )}
                </div>
                <p className="identifier">
                  {job.id} · {new Date(job.created_at).toLocaleString("de-DE")}
                  {job.retry_of_job_id && (
                    <>
                      <br />
                      Wiederholung von {job.retry_of_job_id}
                    </>
                  )}
                </p>
                {job.error_message && (
                  <p className="job-error">Fehlercode: {job.error_message}</p>
                )}
                <details>
                  <summary>Verfahren und Parameter</summary>
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
