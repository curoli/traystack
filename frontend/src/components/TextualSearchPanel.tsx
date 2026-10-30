import { useRef, useState, type FormEvent } from "react";
import {
  artifactUrl,
  searchTextual,
  type SearchTarget,
  type TextualDocument,
  type TextualGroup,
  type TextualOccurrence,
  type TextualSearchResponse,
} from "../api";
import { formatDate } from "../format";
import { coverageLabel, qualityLabel, warningLabel } from "./processingLabels";
import { searchWarnings } from "./SearchPanel";

const riskWarnings: Record<string, string> = {
  text_filter_disabled:
    "The textual filter is off. Every document with searchable text qualifies; many passages may be irrelevant.",
  low_text_threshold:
    "A low textual threshold may return many unrelated passages. This is a caution, not a calibrated accuracy estimate.",
  short_query:
    "Short queries provide little context and may return many unrelated passages.",
};

const riskMessage = (score: number, query: string) =>
  score === 0
    ? riskWarnings.text_filter_disabled
    : score < 70
      ? riskWarnings.low_text_threshold
      : query.trim().length > 0 && query.trim().length < 8
        ? riskWarnings.short_query
        : "";

function Provenance({ document }: { document: TextualDocument }) {
  return (
    <>
      {document.warnings.length > 0 && (
        <ul className="search-warnings">
          {document.warnings.map((reason) => (
            <li key={reason}>
              {searchWarnings[reason] || warningLabel(reason)}
            </li>
          ))}
        </ul>
      )}
      <details className="search-provenance">
        <summary>Source and processing status</summary>
        <p>
          {document.coverage
            ? coverageLabel[document.coverage]
            : "Not processed"}{" "}
          ·{" "}
          {document.quality_status
            ? qualityLabel[document.quality_status]
            : "Quality not assessed"}
        </p>
        <p className="identifier">
          Selected run: {document.processing_job_id || "None"}
          <br />
          Source: {document.artifact_id || "None"}
          <br />
          Normalization: {document.normalization_version || "Not available"}
        </p>
      </details>
    </>
  );
}

function Occurrence({
  occurrence,
  mode,
  onOpen,
}: {
  occurrence: TextualOccurrence;
  mode: string;
  onOpen: () => void;
}) {
  const characters = Array.from(occurrence.snippet);
  const start = occurrence.start_offset - occurrence.snippet_start_offset;
  const end = start + Array.from(occurrence.matched_text).length;
  return (
    <article className="textual-occurrence">
      <div className="section-heading">
        <strong className="textual-score">
          Textual match: {occurrence.score.toFixed(2)}%
        </strong>
        <span className="fineprint">
          {occurrence.score === 100
            ? `Identical ${mode} text`
            : "Possible match · inspect differences"}
        </span>
      </div>
      <p className="search-snippet">
        {occurrence.snippet_start_offset > 0 && "…"}
        {characters.slice(0, start).join("")}
        <mark>{characters.slice(start, end).join("")}</mark>
        {characters.slice(end).join("")}
      </p>
      <div className="text-comparison" aria-label="Text comparison">
        <div>
          <h5>Search text ({mode})</h5>
          <pre>
            {occurrence.differences.map((part, index) =>
              part.kind === "equal" ? (
                <span key={index}>{part.query_text}</span>
              ) : (
                <del key={index}>{part.query_text}</del>
              ),
            )}
          </pre>
        </div>
        <div>
          <h5>Found passage ({mode})</h5>
          <pre>
            {occurrence.differences.map((part, index) =>
              part.kind === "equal" ? (
                <span key={index}>{part.passage_text}</span>
              ) : (
                <ins key={index}>{part.passage_text}</ins>
              ),
            )}
          </pre>
        </div>
      </div>
      <p className="fineprint">
        Differences are marked in both texts. A high score can still hide a
        changed name, amount, deadline or negation.
      </p>
      <button className="secondary" onClick={onOpen}>
        {occurrence.page_reference === "logical"
          ? "View source text"
          : occurrence.page_numbers.length
            ? `View page ${occurrence.page_numbers[0]}`
            : "Open document"}
      </button>
      <span className="fineprint">
        {" "}
        {occurrence.page_reference === "logical"
          ? "Logical text section"
          : occurrence.page_numbers.length
            ? `Pages: ${occurrence.page_numbers.join(", ")}`
            : "No reliable page reference"}
      </span>
    </article>
  );
}

function DocumentMatches({
  initial,
  response,
  onOpen,
}: {
  initial: TextualGroup;
  response: TextualSearchResponse;
  onOpen: (target: SearchTarget) => void;
}) {
  const [group, setGroup] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  async function pageMatches(delta: number) {
    setBusy(true);
    setError("");
    try {
      const result = await searchTextual({
        query: response.query,
        mode: response.mode,
        minimum_score: response.minimum_score,
        document_id: initial.document.document_id,
        occurrence_limit: group.occurrence_limit,
        occurrence_offset: group.occurrence_offset + delta,
      });
      const next = result.results[0];
      if (
        !next ||
        next.document.processing_job_id !== initial.document.processing_job_id
      ) {
        setStale(true);
        setError(
          "The selected text or result set has changed. Please run the search again.",
        );
      } else setGroup(next);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not load passages.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="search-result textual-document"
      aria-label={`Matches in ${group.document.title}`}
    >
      <div className="section-heading">
        <h3>{group.document.title}</h3>
        <span className="badge">
          Revision {group.document.revision_number} · {group.occurrence_total}{" "}
          passages
        </span>
      </div>
      <Provenance document={group.document} />
      {group.document.artifact_id && (
        <a className="download" href={artifactUrl(group.document.artifact_id)}>
          Download original ↓
        </a>
      )}
      {group.occurrences.map((occurrence) => (
        <Occurrence
          key={occurrence.occurrence_id}
          occurrence={occurrence}
          mode={response.mode}
          onOpen={() =>
            onOpen({
              document_id: group.document.document_id,
              revision_id: group.document.revision_id,
              processing_job_id: group.document.processing_job_id,
              page_number: occurrence.page_numbers[0] ?? null,
            })
          }
        />
      ))}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      <nav
        className="pagination"
        aria-label={`Passages in ${group.document.title}`}
      >
        <button
          className="secondary"
          disabled={busy || stale || group.occurrence_offset === 0}
          onClick={() => void pageMatches(-group.occurrence_limit)}
        >
          Previous passages
        </button>
        <span>
          {group.occurrences.length ? group.occurrence_offset + 1 : 0}–
          {group.occurrences.length
            ? group.occurrence_offset + group.occurrences.length
            : 0}{" "}
          of {group.occurrence_total}
        </span>
        <button
          className="secondary"
          disabled={
            busy ||
            stale ||
            group.occurrence_offset + group.occurrence_limit >=
              group.occurrence_total
          }
          onClick={() => void pageMatches(group.occurrence_limit)}
        >
          Next passages
        </button>
      </nav>
    </section>
  );
}

export default function TextualSearchPanel({
  onOpen,
}: {
  onOpen: (target: SearchTarget) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"exact" | "normalized">("normalized");
  const [threshold, setThreshold] = useState("85");
  const [response, setResponse] = useState<TextualSearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const minimum = Number(threshold);
  const validThreshold =
    threshold.trim() !== "" &&
    Number.isFinite(minimum) &&
    minimum >= 0 &&
    minimum <= 100;
  async function run(payload: Parameters<typeof searchTextual>[0]) {
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    try {
      const next = await searchTextual(payload);
      if (id === requestId.current) setResponse(next);
    } catch (error) {
      if (id === requestId.current)
        setError(error instanceof Error ? error.message : "Search failed.");
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!validThreshold) return;
    setResponse(null);
    void run({ query, mode, minimum_score: minimum });
  }
  function paginate(group: "results" | "unsearchable", delta: number) {
    if (!response) return;
    void run({
      query: response.query,
      mode: response.mode,
      minimum_score: response.minimum_score,
      limit: response.limit,
      offset: response.offset + (group === "results" ? delta : 0),
      unsearchable_limit: response.unsearchable_limit,
      unsearchable_offset:
        response.unsearchable_offset + (group === "unsearchable" ? delta : 0),
    });
  }
  return (
    <section
      className="panel textual-search-panel"
      aria-labelledby="textual-search-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">COMPARE WORDING</p>
          <h2 id="textual-search-heading">Find similar passages</h2>
        </div>
        <span className="scope-tag">Latest revision per document</span>
      </div>
      <form className="search-form" onSubmit={submit}>
        <div className="search-query">
          <label htmlFor="textual-query">Text passage</label>
          <textarea
            id="textual-query"
            required
            maxLength={500}
            rows={2}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Enter the wording you want to compare"
          />
        </div>
        <div>
          <label htmlFor="textual-mode">Text comparison mode</label>
          <select
            id="textual-mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as typeof mode)}
          >
            <option value="normalized">Normalized</option>
            <option value="exact">Exact</option>
          </select>
        </div>
        <div>
          <label htmlFor="textual-threshold">Minimum textual match</label>
          <input
            id="textual-threshold"
            type="number"
            min={0}
            max={100}
            step="any"
            required
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
            aria-describedby="textual-threshold-help"
          />
        </div>
        <button
          className="primary"
          disabled={busy || !query.trim() || !validThreshold}
        >
          {busy ? "Searching …" : "Find passages"}
        </button>
      </form>
      <p id="textual-threshold-help" className="fineprint">
        0 disables the text filter. 100 requires identical text in the selected
        mode. Normalized mode ignores case and whitespace differences. Scores
        measure character edits, not confidence or legal equivalence.
      </p>
      {validThreshold && riskMessage(minimum, query) && (
        <p role="status" className="message warning">
          {riskMessage(minimum, query)}
        </p>
      )}
      <p className="search-notice">
        Candidate passages are word windows; overlapping candidates are
        consolidated. Missing candidates do not establish clause absence. Use
        Literal search for the separate exact absence workflow. Semantic scoring
        is not available yet.
      </p>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {busy && <p role="status">Comparing selected document text …</p>}
      {response && (
        <div className="textual-response" aria-busy={busy}>
          <p className="search-query-summary">
            Results for <strong>“{response.query}”</strong> · {response.mode} ·
            minimum {response.minimum_score}%
          </p>
          {response.warnings.length > 0 && (
            <p className="message warning">
              Search snapshot:{" "}
              {response.warnings
                .map((reason) => riskWarnings[reason] || reason)
                .join(" ")}
            </p>
          )}
          <p className="fineprint">
            {response.summary.documents_searched} documents searched ·{" "}
            {response.total} with candidate passages ·{" "}
            {response.summary.occurrences_total} passages ·{" "}
            {response.summary.documents_without_matches} without a candidate
            match · {response.unsearchable_total} unsearchable
          </p>
          <p className="fineprint">
            Snapshot taken at {formatDate(response.searched_at)}. Rerun after
            processing changes.
          </p>
          <section aria-label="Similar passage results">
            {response.results.length ? (
              response.results.map((group) => (
                <DocumentMatches
                  key={`${response.searched_at}:${group.document.document_id}`}
                  initial={group}
                  response={response}
                  onOpen={onOpen}
                />
              ))
            ) : (
              <p className="search-empty">
                {response.total
                  ? "This page is empty after an update. Go back or run the search again."
                  : "No candidate passages for this selection. This is not proof of absence."}
              </p>
            )}
            <nav className="pagination" aria-label="Similar document pages">
              <button
                className="secondary"
                disabled={busy || response.offset === 0}
                onClick={() => paginate("results", -response.limit)}
              >
                Previous documents
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
                Next documents
              </button>
            </nav>
          </section>
          <section
            className="search-unknown"
            aria-label="Unsearchable documents"
          >
            <h3>Unsearchable ({response.unsearchable_total})</h3>
            <p className="fineprint">
              No selected text, no usable text, or unsupported normalization.
              These documents were not treated as missing the passage.
            </p>
            {response.unsearchable.map((document) => (
              <article
                className="search-result uncertain"
                key={document.document_id}
              >
                <h4>{document.title}</h4>
                <Provenance document={document} />
                <button
                  className="secondary"
                  onClick={() => onOpen({ ...document, page_number: null })}
                >
                  Open document
                </button>
              </article>
            ))}
            {!response.unsearchable.length && (
              <p>
                {response.unsearchable_total
                  ? "This page is empty after an update. Go back or run the search again."
                  : "No unsearchable documents in this scope."}
              </p>
            )}
            <nav
              className="pagination"
              aria-label="Unsearchable document pages"
            >
              <button
                className="secondary"
                disabled={busy || response.unsearchable_offset === 0}
                onClick={() =>
                  paginate("unsearchable", -response.unsearchable_limit)
                }
              >
                Previous unsearchable
              </button>
              <span>
                {response.unsearchable.length
                  ? response.unsearchable_offset + 1
                  : 0}
                –
                {response.unsearchable.length
                  ? response.unsearchable_offset + response.unsearchable.length
                  : 0}{" "}
                of {response.unsearchable_total}
              </span>
              <button
                className="secondary"
                disabled={
                  busy ||
                  response.unsearchable_offset + response.unsearchable_limit >=
                    response.unsearchable_total
                }
                onClick={() =>
                  paginate("unsearchable", response.unsearchable_limit)
                }
              >
                Next unsearchable
              </button>
            </nav>
          </section>
          <details className="search-provenance">
            <summary>Scoring method</summary>
            <p>
              100 × (1 − character edit distance / longer text length),
              evaluated before display rounding.
            </p>
            <p className="identifier">
              {response.scorer_version} · RapidFuzz{" "}
              {response.scorer_library_version}
              <br />
              {response.candidate_policy}
              <br />
              Offsets: {response.offset_basis}
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
