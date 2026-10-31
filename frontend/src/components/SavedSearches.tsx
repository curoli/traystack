import { useEffect, useState } from "react";
import { listSearchRuns, getSavedScope, type SavedRunSummary } from "../api";
import { formatDate } from "../format";
import { qualityLabel, coverageLabel, warningLabel } from "./processingLabels";

export default function SavedSearches({
  generation,
  onOpen,
  disabled,
}: {
  generation: number;
  onOpen: (id: string) => void;
  disabled: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{
    items: SavedRunSummary[];
    total: number;
    limit: number;
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    listSearchRuns(offset)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error
              ? error.message
              : "Could not load saved searches.",
          );
      });
    return () => {
      active = false;
    };
  }, [generation, offset]);
  return (
    <details className="saved-searches">
      <summary>Saved searches{data ? ` (${data.total})` : ""}</summary>
      <p className="fineprint">
        Each successful search saves its complete result set and matching source
        text. Opening a saved run does not search the current library.
      </p>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {data?.items.map((run) => (
        <article className="saved-search-row" key={run.id}>
          <button
            className="secondary"
            disabled={disabled}
            onClick={() => onOpen(run.id)}
          >
            Open {run.name}
          </button>
          <p className="fineprint">
            {formatDate(run.searched_at)} · {run.result_documents} documents ·{" "}
            {run.result_passages} candidate passages
          </p>
        </article>
      ))}
      {data?.total === 0 && <p>No saved searches yet.</p>}
      <nav className="pagination" aria-label="Saved search pages">
        <button
          className="secondary"
          disabled={disabled || offset === 0}
          onClick={() => setOffset((value) => Math.max(0, value - 20))}
        >
          Previous saved searches
        </button>
        <button
          className="secondary"
          disabled={disabled || !data || offset + data.limit >= data.total}
          onClick={() => setOffset((value) => value + 20)}
        >
          Next saved searches
        </button>
      </nav>
    </details>
  );
}

export function SavedScope({ id }: { id: string }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Awaited<
    ReturnType<typeof getSavedScope>
  > | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    getSavedScope(id, offset)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error ? error.message : "Saved scope unavailable.",
          );
      });
    return () => {
      active = false;
    };
  }, [id, offset]);
  return (
    <details>
      <summary>Documents at capture{data ? ` (${data.total})` : ""}</summary>
      {error && <p role="alert">{error}</p>}
      {data?.items.map((doc) => (
        <article key={doc.document_id} className="saved-search-row">
          <strong>{doc.title}</strong>
          <p className="fineprint">
            Revision {doc.revision_number ?? "unavailable"} ·{" "}
            {doc.searchable ? "Searched" : "Unsearchable"} ·{" "}
            {doc.coverage ? coverageLabel[doc.coverage] : "Not processed"} ·{" "}
            {doc.quality_status
              ? qualityLabel[doc.quality_status]
              : "Quality not assessed"}
          </p>
          {doc.warnings.map((reason) => (
            <p className="fineprint" key={reason}>
              {warningLabel(reason)}
            </p>
          ))}
        </article>
      ))}
      <nav className="pagination" aria-label="Captured scope pages">
        <button
          className="secondary"
          disabled={offset === 0}
          onClick={() => setOffset((value) => Math.max(0, value - 25))}
        >
          Previous scope documents
        </button>
        <button
          className="secondary"
          disabled={!data || offset + data.limit >= data.total}
          onClick={() => setOffset((value) => value + 25)}
        >
          Next scope documents
        </button>
      </nav>
    </details>
  );
}
