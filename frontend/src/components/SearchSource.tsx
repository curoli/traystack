import { useEffect, useRef, useState } from "react";
import {
  artifactUrl,
  getText,
  type SearchResult,
  type TextContent,
} from "../api";

export default function SearchSource({
  source,
  onClose,
}: {
  source: SearchResult;
  onClose: () => void;
}) {
  const [text, setText] = useState<TextContent | null>(null);
  const [page, setPage] = useState(source.page_number ?? 1);
  const [error, setError] = useState("");
  const viewer = useRef<HTMLElement>(null);
  useEffect(() => {
    let active = true;
    setText(null);
    setError("");
    viewer.current?.focus();
    if (!source.revision_id) return;
    getText(source.revision_id)
      .then((result) => {
        if (!active) return;
        if (result.processing_job_id !== source.processing_job_id)
          throw Error(
            "The document has changed. Run the search again to view its current text.",
          );
        setText(result);
        setPage(source.page_number ?? 1);
        viewer.current?.focus();
        viewer.current?.scrollIntoView({ block: "start" });
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error
              ? error.message
              : "Document text unavailable.",
          );
      });
    return () => {
      active = false;
    };
  }, [source]);
  return (
    <section
      className="page-viewer"
      aria-label="Extracted page text"
      ref={viewer}
      tabIndex={-1}
    >
      <h3>{source.title}</h3>
      <button className="secondary" onClick={onClose}>
        Close document text
      </button>
      {error && <p role="alert">{error}</p>}
      {!text && !error && <p role="status">Loading document text …</p>}
      {text && (
        <>
          <label htmlFor="search-source-page">Page</label>
          <select
            id="search-source-page"
            value={page}
            onChange={(event) => setPage(Number(event.target.value))}
          >
            {text.pages.map((item) => (
              <option key={item.page_number} value={item.page_number}>
                Page {item.page_number}
              </option>
            ))}
          </select>
          <pre className="text-preview">
            {text.pages.find((item) => item.page_number === page)?.text}
          </pre>
          {source.artifact_id && (
            <a href={artifactUrl(source.artifact_id)} className="download">
              Download original ↓
            </a>
          )}
        </>
      )}
    </section>
  );
}
