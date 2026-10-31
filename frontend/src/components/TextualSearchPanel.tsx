import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  assessTextual,
  artifactUrl,
  type Document,
  type SearchAbortDetails,
  type TextualAssessment,
  searchTextual,
  saveReview,
  type ReviewDecision,
  type ReviewCounts,
  type ReviewFilter,
  type SearchTarget,
  type TextualDocument,
  type TextualGroup,
  type TextualOccurrence,
  type TextualSearchResponse,
} from "../api";
import { formatDate } from "../format";
import { coverageLabel, qualityLabel, warningLabel } from "./processingLabels";
import { searchWarnings } from "./SearchPanel";

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

const reviewLabels: Record<ReviewDecision, string> = {
  unreviewed: "Not reviewed",
  keep: "Keep",
  dismiss: "Dismiss",
  later: "Decide later",
};

function Occurrence({
  occurrence,
  mode,
  onOpen,
  onReview,
  reviewDisabled,
  saving,
  reviewError,
}: {
  onReview: (decision: ReviewDecision) => void;
  reviewDisabled: boolean;
  saving: boolean;
  reviewError: string;
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
        {occurrence.semantic_score != null && (
          <strong className="semantic-score">
            Semantic match: {occurrence.semantic_score.toFixed(2)}%
          </strong>
        )}
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
      <fieldset className="review-actions" disabled={reviewDisabled}>
        <legend>Review this passage</legend>
        <p className="review-status" role="status">
          {saving
            ? "Saving decision …"
            : `Review: ${reviewLabels[occurrence.review.decision]}`}
          {occurrence.review.updated_at && !saving && (
            <span className="fineprint">
              {" · Saved "}
              {formatDate(occurrence.review.updated_at)}
            </span>
          )}
        </p>
        <div className="review-buttons">
          {(["keep", "dismiss", "later"] as const).map((decision) => (
            <button
              key={decision}
              className="secondary"
              type="button"
              aria-pressed={occurrence.review.decision === decision}
              disabled={occurrence.review.decision === decision}
              onClick={() => onReview(decision)}
            >
              {reviewLabels[decision]}
            </button>
          ))}
          {occurrence.review.decision !== "unreviewed" && (
            <button
              className="secondary"
              type="button"
              onClick={() => onReview("unreviewed")}
            >
              Reset review
            </button>
          )}
        </div>
        {reviewError && (
          <p role="alert" className="message error">
            {reviewError}
          </p>
        )}
      </fieldset>
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
  onAbort,
  onReviewSaved,
  onReviewCounts,
  disabled,
}: {
  disabled: boolean;
  onReviewSaved: (counts: ReviewCounts) => void;
  onReviewCounts: (counts: ReviewCounts) => void;
  onAbort: (details: SearchAbortDetails) => void;
  initial: TextualGroup;
  response: TextualSearchResponse;
  onOpen: (target: SearchTarget) => void;
}) {
  const [group, setGroup] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const saving = useRef(false);
  const [reviewError, setReviewError] = useState<{
    id: string;
    message: string;
  } | null>(null);
  async function review(
    occurrence: TextualOccurrence,
    decision: ReviewDecision,
  ) {
    if (saving.current || busy || stale || disabled) return;
    saving.current = true;
    setSavingId(occurrence.occurrence_id);
    setReviewError(null);
    try {
      const saved = await saveReview({
        occurrence_id: occurrence.occurrence_id,
        document_id: group.document.document_id,
        revision_id: group.document.revision_id!,
        processing_job_id: group.document.processing_job_id!,
        source_artifact_id: group.document.artifact_id!,
        normalization_version: group.document.normalization_version!,
        query: response.query,
        mode: response.mode,
        scorer_version: response.scorer_version,
        candidate_policy: response.candidate_policy,
        start_offset: occurrence.start_offset,
        end_offset: occurrence.end_offset,
        matched_sha256: occurrence.matched_sha256,
        expected_version: occurrence.review.version,
        decision,
      });
      const counts = { ...group.review_counts };
      if (occurrence.review.decision !== saved.decision) {
        counts[occurrence.review.decision]--;
        counts[saved.decision]++;
      }
      setGroup((current) => ({
        ...current,
        review_counts: counts,
        occurrences: current.occurrences.map((item) =>
          item.occurrence_id === occurrence.occurrence_id
            ? { ...item, review: saved }
            : item,
        ),
      }));
      onReviewSaved(counts);
    } catch (error) {
      setReviewError({
        id: occurrence.occurrence_id,
        message:
          error instanceof Error
            ? error.message
            : "Could not save the review. Please try again.",
      });
    } finally {
      saving.current = false;
      setSavingId(null);
    }
  }
  async function pageMatches(delta: number) {
    setBusy(true);
    setError("");
    try {
      const result = await searchTextual({
        query: response.query,
        mode: response.mode,
        minimum_score: response.minimum_score,
        minimum_semantic_score: response.minimum_semantic_score,
        review_filter: response.review_filter,
        document_id: initial.document.document_id,
        occurrence_limit: group.occurrence_limit,
        occurrence_offset: group.occurrence_offset + delta,
      });
      const next = result.results[0];
      if (
        !next ||
        next.document.processing_job_id !==
          initial.document.processing_job_id ||
        result.semantic?.pipeline !== response.semantic?.pipeline ||
        result.semantic?.score_version !== response.semantic?.score_version ||
        result.scorer_version !== response.scorer_version ||
        result.scorer_library_version !== response.scorer_library_version ||
        result.candidate_policy !== response.candidate_policy
      ) {
        setStale(true);
        setError(
          "The selected text, comparison method or result set has changed. Please run the search again.",
        );
      } else {
        setGroup(next);
        onReviewCounts(next.review_counts);
      }
    } catch (error) {
      if (error instanceof ApiError && error.details) {
        onAbort(error.details);
        return;
      }
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
          onReview={(decision) => void review(occurrence, decision)}
          reviewDisabled={disabled || busy || stale || savingId !== null}
          saving={savingId === occurrence.occurrence_id}
          reviewError={
            reviewError?.id === occurrence.occurrence_id
              ? reviewError.message
              : ""
          }
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
          disabled={
            disabled ||
            busy ||
            stale ||
            savingId !== null ||
            group.occurrence_offset === 0
          }
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
            disabled ||
            busy ||
            savingId !== null ||
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
  openDocument,
}: {
  onOpen: (target: SearchTarget) => void;
  openDocument: Pick<Document, "id" | "title"> | null;
}) {
  const [query, setQuery] = useState("");
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [mode, setMode] = useState<"exact" | "normalized">("normalized");
  const [semanticEnabled, setSemanticEnabled] = useState(false);
  const [semanticThreshold, setSemanticThreshold] = useState("0");
  const [threshold, setThreshold] = useState("85");
  const [response, setResponse] = useState<TextualSearchResponse | null>(null);
  const [responseRequestId, setResponseRequestId] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [aborted, setAborted] = useState<SearchAbortDetails | null>(null);
  const [assessment, setAssessment] = useState<TextualAssessment | null>(null);
  const [assessmentError, setAssessmentError] = useState("");
  const [onlyOpenDocument, setOnlyOpenDocument] = useState(false);
  const requestId = useRef(0);
  const documentReviewCounts = useRef(new Map<string, ReviewCounts>());
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
    setError("");
  }
  async function run(payload: Parameters<typeof searchTextual>[0]) {
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    setAborted(null);
    try {
      const next = await searchTextual(payload);
      if (id === requestId.current) {
        documentReviewCounts.current = new Map(
          next.results.map((group) => [
            group.document.document_id,
            group.review_counts,
          ]),
        );
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
      if (id === requestId.current) setBusy(false);
    }
  }
  function updateReviewCounts(
    documentId: string,
    counts: ReviewCounts,
    originRequestId: number,
  ) {
    if (originRequestId !== requestId.current) return;
    const previous = documentReviewCounts.current.get(documentId);
    if (!previous) return;
    documentReviewCounts.current.set(documentId, counts);
    setResponse((current) => {
      if (!current || originRequestId !== requestId.current) return current;
      const updated = { ...current.review_counts };
      for (const state of Object.keys(reviewLabels) as ReviewDecision[]) {
        updated[state] += counts[state] - previous[state];
      }
      return { ...current, review_counts: updated };
    });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !validThreshold ||
      !validSemanticThreshold ||
      (onlyOpenDocument && !openDocument)
    )
      return;
    setResponse(null);
    void run({
      query,
      mode,
      minimum_score: minimum,
      minimum_semantic_score: semanticEnabled ? semanticMinimum : null,
      review_filter: reviewFilter,
      document_id: onlyOpenDocument ? openDocument!.id : undefined,
    });
  }
  function paginate(group: "results" | "unsearchable", delta: number) {
    if (!response) return;
    void run({
      query: response.query,
      mode: response.mode,
      minimum_score: response.minimum_score,
      minimum_semantic_score: response.minimum_semantic_score,
      review_filter: response.review_filter,
      document_id: response.document_id ?? undefined,
      limit: response.limit,
      offset: response.offset + (group === "results" ? delta : 0),
      unsearchable_limit: response.unsearchable_limit,
      unsearchable_offset:
        response.unsearchable_offset + (group === "unsearchable" ? delta : 0),
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
        <div>
          <label htmlFor="semantic-threshold">Minimum semantic match</label>
          <input
            id="semantic-threshold"
            type="number"
            min={0}
            max={100}
            step="any"
            value={semanticThreshold}
            disabled={!semanticEnabled}
            onChange={(event) => setSemanticThreshold(event.target.value)}
            aria-describedby="semantic-threshold-help"
          />
        </div>
        <div>
          <label htmlFor="review-filter">Review status</label>
          <select
            id="review-filter"
            value={reviewFilter}
            onChange={(event) =>
              setReviewFilter(event.target.value as ReviewFilter)
            }
          >
            <option value="all">All review states</option>
            {Object.entries(reviewLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <button
          className="primary"
          disabled={
            busy ||
            !query.trim() ||
            !validThreshold ||
            !validSemanticThreshold ||
            (onlyOpenDocument && !openDocument)
          }
        >
          {busy ? "Searching …" : "Find passages"}
        </button>
      </form>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={semanticEnabled}
          onChange={(event) => setSemanticEnabled(event.target.checked)}
        />
        <span>Compare meaning with local embeddings</span>
      </label>
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
      <label className="checkbox">
        <input
          type="checkbox"
          checked={onlyOpenDocument}
          onChange={(event) => setOnlyOpenDocument(event.target.checked)}
        />
        <span>
          Search only the open document
          <small>
            {openDocument
              ? openDocument.title
              : "Open a document in the library to narrow the selection."}
          </small>
        </span>
      </label>
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
        consolidated. Missing candidates do not establish clause absence. Use
        Literal search for the separate exact absence workflow. Semantic scores
        do not verify clause absence.
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
          <p className="search-query-summary">
            Results for <strong>“{response.query}”</strong> · {response.mode} ·
            minimum {response.minimum_score}% textual · review:{" "}
            {response.review_filter === "all"
              ? "All review states"
              : reviewLabels[response.review_filter]}
            {response.minimum_semantic_score != null &&
              ` · minimum semantic ${response.minimum_semantic_score}%`}
          </p>
          <section aria-label="Review counts" className="review-counts">
            <p>
              {Object.entries(response.review_counts)
                .map(
                  ([status, count]) =>
                    `${reviewLabels[status as ReviewDecision]}: ${count}`,
                )
                .join(" · ")}
            </p>
            <p className="fineprint">
              Counts cover all passages passing the submitted textual and
              semantic thresholds, before the review filter. Your saves update
              these counts; rerun to include changes from other views. Decisions
              are shared in this local app.
            </p>
          </section>
          <QueryGuidance
            assessment={response.assessment}
            title="Submitted search guidance"
          />
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
            these filters · {response.unsearchable_total} unsearchable
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
            Snapshot taken at {formatDate(response.searched_at)}. Rerun after
            processing changes.
          </p>
          <section aria-label="Similar passage results">
            {response.results.length ? (
              response.results.map((group) => (
                <DocumentMatches
                  key={`${response.searched_at}:${group.document.document_id}`}
                  initial={group}
                  onAbort={(details) => stop(details, responseRequestId)}
                  disabled={busy}
                  onReviewCounts={(counts) =>
                    updateReviewCounts(
                      group.document.document_id,
                      counts,
                      responseRequestId,
                    )
                  }
                  onReviewSaved={(counts) => {
                    if (responseRequestId !== requestId.current) return;
                    if (response.review_filter !== "all") {
                      // Refill filtered pages after a passage leaves the selected state.
                      // Use submitted criteria; unrelated form edits remain unapplied.
                      setResponse(null);
                      void run({
                        query: response.query,
                        mode: response.mode,
                        minimum_score: response.minimum_score,
                        minimum_semantic_score: response.minimum_semantic_score,
                        review_filter: response.review_filter,
                        document_id: response.document_id ?? undefined,
                        limit: response.limit,
                        unsearchable_limit: response.unsearchable_limit,
                      });
                    } else {
                      updateReviewCounts(
                        group.document.document_id,
                        counts,
                        responseRequestId,
                      );
                    }
                  }}
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
