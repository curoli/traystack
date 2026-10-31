import { useEffect, useRef, useState } from "react";
import { getSavedSource, artifactUrl, type TextContent } from "../api";
import { coverageLabel, qualityLabel, warningLabel } from "./processingLabels";

export interface SavedSourceLocation {
  runId: string;
  jobId: string;
  page: number;
  requestId: number;
}
export default function SavedSource({
  location,
  onClose,
}: {
  location: SavedSourceLocation;
  onClose: () => void;
}) {
  const [text, setText] = useState<TextContent | null>(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(location.page);
  const [loaded, setLoaded] = useState<number | null>(null);
  const viewer = useRef<HTMLElement>(null);
  useEffect(() => {
    let active = true;
    setText(null);
    setError("");
    setLoaded(null);
    viewer.current?.focus({ preventScroll: true });
    viewer.current?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
    getSavedSource(location.runId, location.jobId)
      .then((result) => {
        if (active) {
          setText(result);
          setPage(location.page);
          setLoaded(location.requestId);
        }
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error ? error.message : "Saved text unavailable.",
          );
      });
    return () => {
      active = false;
    };
  }, [location]);
  useEffect(() => {
    if (loaded !== location.requestId || !text) return;
    viewer.current?.focus({ preventScroll: true });
    viewer.current?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [loaded, location.requestId, text]);
  const selected = text?.pages.find((item) => item.page_number === page);
  return (
    <section
      ref={viewer}
      tabIndex={-1}
      className="page-viewer saved-source"
      aria-label="Saved source text"
    >
      <h3>Saved source text</h3>
      <p className="message warning">
        This is the extraction preserved with the saved search. The current
        document may have been reprocessed since then.
      </p>
      <button className="secondary" onClick={onClose}>
        Close saved text
      </button>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {!text && !error && <p role="status">Loading saved text …</p>}
      {text && (
        <>
          <p>
            {coverageLabel[text.status]} · {qualityLabel[text.quality_status]}
          </p>
          {text.quality_warnings.map((reason) => (
            <p className="fineprint" key={reason}>
              {warningLabel(reason)}
            </p>
          ))}
          <p className="identifier">
            Processing run: {text.processing_job_id}
            <br />
            Source: {text.source_artifact_id}
            <br />
            Normalization: {text.normalization_version}
          </p>
          <a className="download" href={artifactUrl(text.source_artifact_id)}>
            Download original ↓
          </a>
          <label htmlFor="saved-source-page">Saved page</label>
          <select
            id="saved-source-page"
            value={page}
            onChange={(event) => setPage(Number(event.target.value))}
          >
            {text.pages.map((item) => (
              <option key={item.page_number} value={item.page_number}>
                Page {item.page_number}
              </option>
            ))}
          </select>
          {selected && (
            <>
              <p className="fineprint">
                {selected.extraction_method === "plain_text" ||
                selected.extraction_method === "html_text"
                  ? "Logical text page"
                  : selected.extraction_method === "ocr"
                    ? "Tesseract OCR"
                    : selected.extraction_method === "embedded_pdf_text"
                      ? "Embedded PDF text"
                      : "Extraction unavailable"}
                {selected.confidence !== null &&
                  ` · Mean OCR word score: ${selected.confidence.toFixed(1)}/100 (not a probability)`}
              </p>
              <p className="fineprint">
                {coverageLabel[selected.status as keyof typeof coverageLabel] ??
                  selected.status}{" "}
                ·{" "}
                {qualityLabel[
                  selected.quality_status as keyof typeof qualityLabel
                ] ?? selected.quality_status}
              </p>
              {selected.quality_warnings.map((reason) => (
                <p className="fineprint" key={reason}>
                  {warningLabel(reason)}
                </p>
              ))}
              <pre className="text-preview">
                {selected.text || "No text was detected on this page."}
              </pre>
            </>
          )}
        </>
      )}
    </section>
  );
}
