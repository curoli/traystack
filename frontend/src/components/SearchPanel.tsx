import { useRef, useState, type FormEvent } from "react";
import { formatDate } from "../format";
import {
  artifactUrl,
  searchDocuments,
  type SearchRequest,
  type SearchResponse,
  type SearchResult,
} from "../api";
import SearchSource from "./SearchSource";

export const searchWarnings: Record<string, string> = {
  no_revision: "No revision available yet.",
  no_selected_text: "No selected text yet; processing is required.",
  processing_failed: "Processing failed; no selected text is available yet.",
  processing_pending:
    "Processing is not finished; no selected text is available yet.",
  incomplete_extraction: "At least one page was not fully extracted.",
  extraction_needs_review: "The extraction requires manual review.",
  quality_unassessed: "Recognition quality has not been assessed.",
  unsupported_normalization_version:
    "The stored normalization rules are not supported; reprocessing is required.",
  newer_run_failed:
    "A newer processing run failed. Search uses the previously selected text.",
  newer_run_pending:
    "A newer processing run is not finished. Search uses the previously selected text.",
  page_location_unavailable:
    "No reliable page location is available for this match.",
};

function ResultCard({
  result,
  onOpen,
}: {
  result: SearchResult;
  onOpen: (result: SearchResult) => void;
}) {
  const start =
    result.start_offset !== null && result.snippet_start_offset !== null
      ? result.start_offset - result.snippet_start_offset
      : 0;
  // API offsets count Unicode code points; JavaScript string.slice counts UTF-16 units.
  const characters = Array.from(result.snippet || "");
  const end = start + Array.from(result.matched_text || "").length;
  return (
    <article
      className={`search-result ${result.status === "unverifiable" ? "uncertain" : ""}`}
    >
      <div className="section-heading">
        <h4>{result.title}</h4>
        <span className="badge">
          {result.revision_number
            ? `Revision ${result.revision_number}`
            : "No revision"}
        </span>
      </div>
      {result.snippet !== null && (
        <p className="search-snippet">
          {result.snippet_start_offset !== 0 && "…"}
          {characters.slice(0, start).join("")}
          <mark>{characters.slice(start, end).join("")}</mark>
          {characters.slice(end).join("")}
        </p>
      )}
      {result.page_number !== null && (
        <p className="fineprint">
          Page {result.page_number}
          {result.end_page_number !== result.page_number &&
            `–${result.end_page_number}`}{" "}
          · First occurrence in{" "}
          {result.offset_basis === "normalized_text"
            ? "normalized"
            : "extracted"}{" "}
          text
        </p>
      )}
      <div className="artifact-actions">
        <button className="secondary" onClick={() => onOpen(result)}>
          {result.page_number !== null
            ? `View page ${result.page_number}`
            : "Open document"}
        </button>
        {result.artifact_id && (
          <a className="download" href={artifactUrl(result.artifact_id)}>
            Download original ↓
          </a>
        )}
      </div>
    </article>
  );
}

export default function SearchPanel() {
  const [source, setSource] = useState<SearchResult | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchRequest["mode"]>("normalized");
  const [relation, setRelation] =
    useState<SearchRequest["relation"]>("contains");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);

  async function run(payload: SearchRequest) {
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    try {
      const result = await searchDocuments({ ...payload, ready_only: true });
      if (id === requestId.current) setResponse(result);
    } catch (error) {
      if (id === requestId.current)
        setError(error instanceof Error ? error.message : "Search failed.");
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    setResponse(null);
    void run({
      query,
      mode,
      relation,
      scope: "latest",
      limit: 10,
      unverifiable_limit: 10,
    });
  }
  function paginate(group: "results" | "unverifiable", delta: number) {
    if (!response) return;
    void run({
      query: response.query,
      mode: response.mode,
      relation: response.relation,
      scope: response.scope,
      limit: response.limit,
      offset: group === "results" ? response.offset + delta : response.offset,
      unverifiable_limit: response.unverifiable_limit,
      unverifiable_offset:
        group === "unverifiable"
          ? response.unverifiable_offset + delta
          : response.unverifiable_offset,
    });
  }
  return (
    <section className="panel search-panel" aria-labelledby="search-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">FULL REVISION TEXT</p>
          <h2 id="search-heading">Find documents</h2>
        </div>
        <span className="scope-tag">Ready documents</span>
      </div>
      <form onSubmit={submit} className="search-form">
        <div className="search-query">
          <label htmlFor="search-query">Text passage</label>
          <textarea
            id="search-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            maxLength={2000}
            rows={2}
            placeholder="e.g. The receiving party shall not disclose confidential information"
          />
        </div>
        <div>
          <label htmlFor="search-mode">Search mode</label>
          <select
            id="search-mode"
            value={mode}
            onChange={(event) =>
              setMode(event.target.value as SearchRequest["mode"])
            }
          >
            <option value="normalized">Normalized</option>
            <option value="exact">Exact</option>
          </select>
        </div>
        <fieldset className="search-goal">
          <legend>Find documents that</legend>
          <label>
            <input
              type="radio"
              name="search-goal"
              checked={relation === "contains"}
              onChange={() => setRelation("contains")}
            />{" "}
            Contain this phrase
          </label>
          <label>
            <input
              type="radio"
              name="search-goal"
              checked={relation === "lacks"}
              onChange={() => setRelation("lacks")}
            />{" "}
            Do NOT contain this phrase
          </label>
        </fieldset>
        <button className="primary" disabled={busy || !query.trim()}>
          {busy ? "Searching …" : "Run search"}
        </button>
      </form>
      <p className="fineprint">
        {mode === "normalized"
          ? "Normalized search ignores case and whitespace differences, including line breaks. Numbers, negations, punctuation and hyphens are preserved."
          : "Exact search preserves case, spaces and line breaks in the extracted text."}
      </p>
      <p className="search-notice">
        Search covers ready documents only. “Do NOT contain” checks the full
        text for this wording; it does not decide whether an equivalent legal
        clause exists.
      </p>
      {busy && (
        <p role="status" className="job-progress">
          Checking the entire selected text …
        </p>
      )}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {source && (
        <SearchSource source={source} onClose={() => setSource(null)} />
      )}
      {response && (
        <div className="search-response" aria-busy={busy}>
          <p className="search-query-summary">
            Results for <strong>“{response.query}”</strong> ·{" "}
            {response.mode === "exact" ? "Exact" : "Normalized"} ·{" "}
            {response.relation === "contains"
              ? "Contains"
              : "Documents without this phrase"}
          </p>
          <p className="fineprint">
            {response.summary.documents_total} documents in scope ·{" "}
            {response.summary.found} found ·{" "}
            {response.summary.not_found_in_processed_text} without the phrase
          </p>
          <p className="fineprint">
            Results from {formatDate(response.searched_at)}. Run the search
            again to include changes.
          </p>
          <section aria-label="Search results">
            <h3>
              {response.relation === "contains"
                ? "Documents found"
                : "Documents without this phrase"}{" "}
              ({response.total})
            </h3>
            {response.results.length ? (
              response.results.map((result) => (
                <ResultCard
                  key={result.document_id}
                  result={result}
                  onOpen={(result) => setSource({ ...result })}
                />
              ))
            ) : (
              <p className="search-empty">
                {response.summary.documents_total === 0
                  ? "No documents yet. Upload a demo contract."
                  : response.total > 0
                    ? "This results page is empty after an update. Go back a page or run the search again."
                    : "No results for this selection."}
              </p>
            )}
            <nav className="pagination" aria-label="Search result pages">
              <button
                className="secondary"
                disabled={busy || response.offset === 0}
                onClick={() => paginate("results", -response.limit)}
              >
                Previous results
              </button>
              <span>
                {response.results.length ? response.offset + 1 : 0}–
                {response.results.length
                  ? response.offset + response.results.length
                  : 0}{" "}
                of {response.total}
              </span>
              <button
                className="secondary"
                disabled={
                  busy || response.offset + response.limit >= response.total
                }
                onClick={() => paginate("results", response.limit)}
              >
                Next results
              </button>
            </nav>
          </section>
        </div>
      )}
    </section>
  );
}
