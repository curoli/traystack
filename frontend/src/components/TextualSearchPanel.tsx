import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  assessTextual,
  type Document,
  type ReviewDecision,
  type SearchAbortDetails,
  type TextualAssessment,
  searchTextual,
  createSearchRun,
  getSearchRun,
  getCategories,
  renameSearchRun,
  type ReviewFilter,
  type SearchTarget,
  type TextualSearchResponse,
} from "../api";
import { formatDate } from "../format";
import SavedSearches from "./SavedSearches";
import SavedSource, { type SavedSourceLocation } from "./SavedSource";
import ReviewWorkspace from "./ReviewWorkspace";
import { reviewLabels } from "./PassageDetails";
import SearchRunExport from "./SearchRunExport";

function QueryGuidance({
  assessment,
  title,
}: {
  assessment: TextualAssessment;
  title: string;
}) {
  return (
    <section className="query-guidance" aria-label={title}>
      <p className="fineprint">
        {title}: {assessment.comparison_characters} comparison characters ·{" "}
        {assessment.word_count} {assessment.word_count === 1 ? "word" : "words"}
        . For an equal-length passage, the threshold permits up to{" "}
        {assessment.equal_length_edit_budget} character edits. Different-length
        passages can allow a different number of edits.
      </p>
      {assessment.warnings.length > 0 && (
        <ul className="message warning">
          {assessment.warnings.map((notice) => (
            <li key={notice.code}>{notice.message}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SearchStopped({ details }: { details: SearchAbortDetails }) {
  const resources: Record<string, string> = {
    retained_passages_in_document: "passages in one document",
    retained_passages_total: "passages across inspected documents",
    passages_per_1000_characters: "passages per 1,000 characters",
    characters: "source characters",
    windows: "candidate comparisons",
    matches: "candidate intervals",
    snapshot_bytes: "bytes in the complete snapshot",
    snapshot_documents: "documents in the saved scope",
    semantic_passages: "passages for semantic comparison",
    semantic_tokens: "model tokens",
    semantic_seconds: "seconds in semantic comparison",
  };
  const count = (value: number) =>
    new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(value);
  return (
    <section role="alert" className="message error search-stopped">
      <h3>Search stopped — no results returned</h3>
      <p>{details.message}</p>
      <p>
        Observed at least{" "}
        {count(Math.floor(details.observed_at_least * 10) / 10)}{" "}
        {resources[details.resource] || "processing units"} (limit{" "}
        {count(details.limit)}). Inspected {details.documents_inspected}{" "}
        documents before stopping.
      </p>
      <p>
        The search did not complete. These are partial observations, not totals
        for the selection. No partial result list is shown, and your threshold
        was not changed.
      </p>
    </section>
  );
}

export default function TextualSearchPanel({
  onOpen,
  openDocument,
}: {
  onOpen: (target: SearchTarget) => void;
  openDocument: Pick<Document, "id" | "title"> | null;
}) {
  const [query, setQuery] = useState("");
  const [searchName, setSearchName] = useState("");
  const [historyGeneration, setHistoryGeneration] = useState(0);
  const [sourceLocation, setSourceLocation] =
    useState<SavedSourceLocation | null>(null);
  const sourceRequest = useRef(0);
  const selectedPassage = useRef<{
    runId: string | null;
    occurrenceId: string;
  } | null>(null);
  const [loadedSaved, setLoadedSaved] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [mode, setMode] = useState<"exact" | "normalized">("normalized");
  const semanticEnabled = true;
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [categoryError, setCategoryError] = useState("");
  const [autoConfirm, setAutoConfirm] = useState(true);
  const [autoText, setAutoText] = useState("100");
  const [autoSemantic, setAutoSemantic] = useState("100");
  const validAuto =
    !autoConfirm ||
    [autoText, autoSemantic].every(
      (value) =>
        value.trim() !== "" &&
        Number.isFinite(Number(value)) &&
        Number(value) >= 0 &&
        Number(value) <= 100,
    );
  useEffect(() => {
    let active = true,
      version = 0;
    const refresh = () => {
      const current = ++version;
      getCategories()
        .then((result) => {
          if (active && current === version) {
            setCategories(result.items);
            setCategoryError("");
          }
        })
        .catch(() => {
          if (active && current === version)
            setCategoryError(
              "Categories could not be loaded. All documents remains available.",
            );
        });
    };
    refresh();
    window.addEventListener("categories-changed", refresh);
    return () => {
      active = false;
      window.removeEventListener("categories-changed", refresh);
    };
  }, []);
  const [semanticThreshold, setSemanticThreshold] = useState("0");
  const [threshold, setThreshold] = useState("85");
  const [response, setResponse] = useState<TextualSearchResponse | null>(null);
  const [responseRequestId, setResponseRequestId] = useState(0);
  const [requestDurationMs, setRequestDurationMs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [aborted, setAborted] = useState<SearchAbortDetails | null>(null);
  const [assessment, setAssessment] = useState<TextualAssessment | null>(null);
  const [assessmentError, setAssessmentError] = useState("");
  const requestId = useRef(0);
  const minimum = Number(threshold);
  const validThreshold =
    threshold.trim() !== "" &&
    Number.isFinite(minimum) &&
    minimum > 0 &&
    minimum <= 100;
  const semanticMinimum = Number(semanticThreshold);
  const validSemanticThreshold =
    !semanticEnabled ||
    (semanticThreshold.trim() !== "" &&
      Number.isFinite(semanticMinimum) &&
      semanticMinimum >= 0 &&
      semanticMinimum <= 100);
  useEffect(() => {
    setAssessment(null);
    setAssessmentError("");
    if (!validThreshold || !query.trim()) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      assessTextual({ query, mode, minimum_score: minimum }, controller.signal)
        .then((result) => {
          if (active) setAssessment(result);
        })
        .catch(() => {
          if (active)
            setAssessmentError(
              "Guidance is unavailable. The search will assess the expression again when submitted.",
            );
        });
    }, 300);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, mode, minimum, validThreshold]);
  function stop(details: SearchAbortDetails, originRequestId: number) {
    // Passage pagination belongs to the search that produced its result card.
    // A superseded card must not clear a newer pending or completed search.
    if (originRequestId !== requestId.current) return;
    requestId.current++;
    setResponse(null);
    setAborted(details);
    setBusy(false);
    setRestoring(false);
    setError("");
  }
  async function perform(
    load: () => Promise<TextualSearchResponse>,
    restore = false,
    created = false,
  ) {
    const id = ++requestId.current;
    const started = performance.now();
    setRestoring(restore);
    setBusy(true);
    setError("");
    setAborted(null);
    try {
      const next = await load();
      if (created) setHistoryGeneration((value) => value + 1);
      if (id === requestId.current) {
        if (next.run_id) {
          const url = new URL(window.location.href);
          url.searchParams.set("search_run", next.run_id);
          window.history.replaceState(null, "", url);
        }
        setLoadedSaved(!created);
        if (restore) {
          setQuery(next.query);
          setMode(next.mode);
          setThreshold(String(next.minimum_score));
          setSemanticThreshold(String(next.minimum_semantic_score ?? 0));
          setSearchName(next.run_name ?? "");
          setCategory(
            next.uncategorized
              ? "__uncategorized__"
              : next.category
                ? `category:${next.category}`
                : "",
          );
          setAutoConfirm(next.auto_confirm_textual !== null);
          setAutoText(String(next.auto_confirm_textual ?? 100));
          setAutoSemantic(String(next.auto_confirm_semantic ?? 100));
        }
        setRequestDurationMs(performance.now() - started);
        setResponseRequestId(id);
        setResponse(next);
      }
    } catch (error) {
      if (id === requestId.current) {
        if (error instanceof ApiError && error.details) stop(error.details, id);
        else
          setError(error instanceof Error ? error.message : "Search failed.");
      }
    } finally {
      if (id === requestId.current) {
        setBusy(false);
        setRestoring(false);
      }
    }
  }
  function run(payload: Parameters<typeof searchTextual>[0], savedId?: string) {
    return perform(
      () =>
        savedId
          ? getSearchRun(savedId, payload)
          : createSearchRun(payload, searchName.trim() || undefined),
      false,
      !savedId,
    );
  }
  function openSaved(id: string) {
    setResponse(null);
    setSourceLocation(null);
    void perform(() => getSearchRun(id, { review_filter: "all" }), true);
  }
  async function rename() {
    if (!response?.run_id || !searchName.trim()) return;
    const origin = requestId.current;
    setError("");
    try {
      const result = await renameSearchRun(response.run_id, searchName.trim());
      setHistoryGeneration((value) => value + 1);
      if (origin === requestId.current)
        setResponse((current) =>
          current ? { ...current, run_name: result.name } : current,
        );
    } catch (error) {
      if (origin === requestId.current)
        setError(
          error instanceof Error ? error.message : "Could not save the name.",
        );
    }
  }
  function rerun() {
    if (!response?.run_id) return;
    const captured = response;
    setResponse(null);
    setSourceLocation(null);
    void perform(
      () =>
        createSearchRun(
          {
            query: captured.query,
            mode: captured.mode,
            minimum_score: captured.minimum_score,
            minimum_semantic_score: captured.minimum_semantic_score ?? 0,
            review_filter: "all",
            category: captured.category ?? undefined,
            uncategorized: captured.uncategorized,
            auto_confirm_textual: captured.auto_confirm_textual,
            auto_confirm_semantic: captured.auto_confirm_semantic,
            document_id: captured.document_id ?? undefined,
          },
          `${captured.run_name ?? "Search"} (rerun)`.slice(0, 200),
          captured.run_id!,
        ),
      true,
      true,
    );
  }
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("search_run");
    if (id) openSaved(id);
  }, []);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!validThreshold || !validSemanticThreshold || !validAuto) return;
    setResponse(null);
    setSourceLocation(null);
    void run({
      query,
      mode,
      minimum_score: minimum,
      minimum_semantic_score: semanticEnabled ? semanticMinimum : null,
      review_filter: "all",
      category: category.startsWith("category:")
        ? category.slice(9)
        : undefined,
      uncategorized: category === "__uncategorized__",
      auto_confirm_textual: autoConfirm ? Number(autoText) : null,
      auto_confirm_semantic: autoConfirm ? Number(autoSemantic) : null,
    });
  }
  return (
    <section
      className="panel search-panel textual-search-panel"
      aria-labelledby="textual-search-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">COMPARE WORDING</p>
          <h2 id="textual-search-heading">Find similar passages</h2>
        </div>
        <span className="scope-tag">Ready documents</span>
      </div>
      <SavedSearches
        generation={historyGeneration}
        onOpen={openSaved}
        disabled={busy}
      />
      <details className="search-parameters" open>
        <summary>Search parameters</summary>
        <label htmlFor="search-name">Search name</label>
        <div className="saved-run-actions">
          <input
            id="search-name"
            maxLength={200}
            disabled={restoring}
            value={searchName}
            onChange={(event) => setSearchName(event.target.value)}
            placeholder="Optional name for the next search"
          />
          <button
            className="secondary"
            disabled={busy || !response?.run_id || !searchName.trim()}
            onClick={() => void rename()}
          >
            Save name
          </button>
        </div>
        <p className="fineprint">
          Successful searches are saved automatically with all results.
          Pagination and reopening use the saved snapshot.
        </p>
        <form className="search-form" onSubmit={submit}>
          <div className="search-query">
            <label htmlFor="textual-query">Text passage</label>
            <textarea
              id="textual-query"
              disabled={restoring}
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
              disabled={restoring}
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
              disabled={restoring}
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
          <div>
            <label htmlFor="semantic-threshold">Minimum semantic match</label>
            <input
              id="semantic-threshold"
              type="number"
              min={0}
              max={100}
              step="any"
              value={semanticThreshold}
              disabled={restoring}
              onChange={(event) => setSemanticThreshold(event.target.value)}
              aria-describedby="semantic-threshold-help"
            />
          </div>
          <div>
            <label htmlFor="search-category">Document category</label>
            <select
              id="search-category"
              value={category}
              disabled={restoring}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All documents</option>
              <option value="__uncategorized__">Uncategorized documents</option>
              {[
                ...new Set([
                  ...categories,
                  ...(category.startsWith("category:")
                    ? [category.slice(9)]
                    : []),
                ]),
              ].map((name) => (
                <option key={name} value={`category:${name}`}>
                  {name}
                </option>
              ))}
            </select>
            {categoryError && <p role="status">{categoryError}</p>}
          </div>
          <fieldset className="auto-confirm-settings">
            <legend>Skip review for strong matches</legend>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={autoConfirm}
                disabled={restoring}
                onChange={(event) => setAutoConfirm(event.target.checked)}
              />
              Auto-confirm strong matches
            </label>
            <label htmlFor="auto-text">Auto-confirm textual minimum</label>
            <input
              id="auto-text"
              type="number"
              min={0}
              max={100}
              step="any"
              value={autoText}
              disabled={!autoConfirm || restoring}
              onChange={(event) => setAutoText(event.target.value)}
            />
            <label htmlFor="auto-semantic">Auto-confirm semantic minimum</label>
            <input
              id="auto-semantic"
              type="number"
              min={0}
              max={100}
              step="any"
              value={autoSemantic}
              disabled={!autoConfirm || restoring}
              onChange={(event) => setAutoSemantic(event.target.value)}
            />
            <p className="fineprint">
              Both thresholds must pass. Explicit review decisions always take
              precedence.
            </p>
            {!validAuto && (
              <p role="alert">
                Auto-confirm thresholds must be between 0 and 100.
              </p>
            )}
          </fieldset>
          <button
            className="primary"
            disabled={
              busy ||
              !query.trim() ||
              !validThreshold ||
              !validSemanticThreshold ||
              !validAuto
            }
          >
            {busy ? "Searching …" : "Find passages"}
          </button>
        </form>
      </details>
      <p id="semantic-threshold-help" className="fineprint">
        Semantic comparison scores only the passages found by the textual
        filter. 0 retains all textual candidates; 100 requires identical
        comparison text. Intermediate scores measure model similarity, not
        confidence or legal equivalence.
      </p>
      {!validSemanticThreshold && (
        <p role="alert" className="message error">
          Enter a semantic threshold from 0 to 100.
        </p>
      )}
      {semanticEnabled && semanticMinimum < 50 && (
        <p className="message warning">
          This semantic threshold is permissive and may retain unrelated
          wording. Zero applies no semantic filter.
        </p>
      )}
      {semanticEnabled && semanticMinimum === 100 && minimum < 100 && (
        <p className="message warning">
          Semantic 100 retains only identical comparison text. A textual
          threshold of 100 is sufficient for this purpose.
        </p>
      )}
      <p id="textual-threshold-help" className="fineprint">
        Choose a threshold greater than 0 and at most 100. 100 requires
        identical text in the selected mode. Normalized mode ignores case and
        whitespace differences. Scores measure character edits, not confidence
        or legal equivalence.
      </p>
      {!validThreshold && (
        <p role="alert" className="message error">
          Enter a threshold greater than 0 and no more than 100. The text filter
          cannot be disabled.
        </p>
      )}
      {assessment && (
        <QueryGuidance
          assessment={assessment}
          title="Current expression guidance"
        />
      )}
      {assessmentError && (
        <p role="status" className="fineprint">
          {assessmentError}
        </p>
      )}
      <p className="search-notice">
        Candidate passages are word windows; overlapping candidates are
        consolidated. Document groups summarize the reviewed candidates, not
        proof of legal clause absence. Semantic scores do not verify clause
        absence.
      </p>
      {aborted && <SearchStopped details={aborted} />}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {busy && <p role="status">Comparing selected document text …</p>}
      {response && (
        <div className="textual-response" aria-busy={busy}>
          <p className="fineprint search-duration">
            {loadedSaved ? "Saved results loaded" : "Search completed"} in{" "}
            {(requestDurationMs / 1000).toFixed(2)} s.
          </p>
          {response.run_id && (
            <section className="saved-run-info" aria-label="Saved search run">
              <h3>{response.run_name}</h3>
              <p className="message warning">
                Frozen matching results from {formatDate(response.searched_at)}.
                Later document changes do not alter this run. Review decisions
                show their current state.
              </p>
              <p className="fineprint">
                Review filters act on the preserved candidate set. Run again
                creates a separate snapshot using the current library.
              </p>
              {response.parent_run_id && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => openSaved(response.parent_run_id!)}
                >
                  Open previous run
                </button>
              )}
              <button className="secondary" disabled={busy} onClick={rerun}>
                Run again
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  void run(
                    {
                      query: response.query,
                      mode: response.mode,
                      minimum_score: response.minimum_score,
                      document_id: response.document_id ?? undefined,
                      review_filter: response.review_filter,
                    },
                    response.run_id!,
                  )
                }
              >
                Refresh reviews
              </button>
              <SearchRunExport
                key={`export:${response.run_id}`}
                runId={response.run_id}
              />
            </section>
          )}
          <p className="search-query-summary">
            Results for <strong>“{response.query}”</strong> · {response.mode} ·
            minimum {response.minimum_score}% textual · minimum semantic{" "}
            {response.minimum_semantic_score ??
              "not computed in this historical run"}
            % ·{" "}
            {response.category ??
              (response.uncategorized
                ? "Uncategorized documents"
                : "All documents")}
          </p>
          <section aria-label="Review counts" className="review-counts">
            <label htmlFor="review-progress">
              Final decisions:{" "}
              {response.review_counts.keep + response.review_counts.dismiss} of{" "}
              {Object.values(response.review_counts).reduce(
                (sum, count) => sum + count,
                0,
              )}
            </label>
            <progress
              id="review-progress"
              aria-label="Final review decisions"
              value={
                response.review_counts.keep + response.review_counts.dismiss
              }
              max={
                Object.values(response.review_counts).reduce(
                  (sum, count) => sum + count,
                  0,
                ) || 1
              }
            />
            <p className="fineprint">
              Review states belong to passages. Document groups below summarize
              the complete search scope.
            </p>
            <p>
              Unreviewed:{" "}
              {response.review_counts.unreviewed + response.review_counts.later}{" "}
              · Confirmed: {response.review_counts.keep} · Dismissed:{" "}
              {response.review_counts.dismiss}
            </p>
            <p className="fineprint">
              Counts cover all passages passing the submitted textual and
              semantic thresholds, before the review filter. Your saves update
              these counts; refresh reviews to include changes from other views.
              Decisions are shared in this local app.
            </p>
          </section>
          <details className="search-provenance">
            <summary>Submitted search guidance</summary>
            <QueryGuidance
              assessment={response.assessment}
              title="Submitted search guidance"
            />
          </details>
          {response.assessment.warnings.length > 0 && (
            <ul className="message warning">
              {response.assessment.warnings.map((notice) => (
                <li key={notice.code}>{notice.message}</li>
              ))}
            </ul>
          )}
          {response.result_warnings.length > 0 && (
            <ul className="message warning">
              {response.result_warnings.map((notice) => (
                <li key={notice.code}>{notice.message}</li>
              ))}
            </ul>
          )}
          <p className="fineprint">
            Scope: {response.document_id ? "one document" : "all documents"} ·{" "}
            {response.summary.documents_searched} documents searched ·{" "}
            {response.total} with candidate passages ·{" "}
            {response.summary.occurrences_total} passages ·{" "}
            {response.summary.documents_without_matches} without a match for
            these filters
          </p>
          {response.semantic && (
            <details className="search-provenance">
              <summary>Semantic comparison method</summary>
              <p>
                {response.textual_candidates_total} textual candidates assessed
                before semantic filtering. Only the matched passage is embedded;
                surrounding text is shown for review. Negations, names and
                amounts can change meaning despite a high score.
              </p>
              <p className="identifier">
                Model: {response.semantic.model}
                <br />
                Pipeline: {response.semantic.pipeline}
                <br />
                Score: {response.semantic.score_version}
              </p>
            </details>
          )}
          <p className="fineprint">
            Results from {formatDate(response.searched_at)}. Run again to create
            a new result set.
          </p>
          <section aria-label="Similar passage results">
            <ReviewWorkspace
              key={responseRequestId}
              response={response}
              disabled={busy}
              onAbort={(details) => stop(details, responseRequestId)}
              onChange={(next) => {
                if (responseRequestId !== requestId.current) return;
                setResponse((current) =>
                  current
                    ? {
                        ...current,
                        review_counts: next.review_counts,
                        total: next.total,
                        summary: next.summary,
                        document_outcomes: next.document_outcomes,
                      }
                    : current,
                );
              }}
              initialSelectedId={
                selectedPassage.current?.runId === response.run_id
                  ? selectedPassage.current.occurrenceId
                  : null
              }
              onSelectionChange={(identity) => {
                if (responseRequestId !== requestId.current) return;
                selectedPassage.current = identity
                  ? { runId: response.run_id, occurrenceId: identity }
                  : null;
                setSourceLocation(null);
              }}
              source={
                sourceLocation ? (
                  <SavedSource
                    location={sourceLocation}
                    onClose={() => setSourceLocation(null)}
                  />
                ) : null
              }
              onOpen={(target) => {
                if (responseRequestId !== requestId.current) return;
                if (response.run_id && target.processing_job_id)
                  setSourceLocation({
                    runId: response.run_id,
                    jobId: target.processing_job_id,
                    page: target.page_number ?? 1,
                    requestId: ++sourceRequest.current,
                  });
                else onOpen(target);
              }}
            />
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
