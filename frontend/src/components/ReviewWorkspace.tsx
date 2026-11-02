import OriginalActions from "./OriginalActions";
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type KeyboardEvent,
} from "react";
import {
  ApiError,
  getReviewWorkspace,
  saveReview,
  type ReviewDecision,
  type SearchAbortDetails,
  type SearchTarget,
  type TextualSearchResponse,
} from "../api";
import DocumentGroups, { currentDocumentOutcomes } from "./DocumentGroups";
import { Occurrence, reviewLabels } from "./PassageDetails";

export default function ReviewWorkspace({
  response,
  disabled,
  onChange,
  onOpen,
  onAbort,
  onSelectionChange,
  source,
  initialSelectedId,
}: {
  response: TextualSearchResponse;
  disabled: boolean;
  onChange: (response: TextualSearchResponse) => void;
  onOpen: (target: SearchTarget) => void;
  onAbort: (details: SearchAbortDetails) => void;
  initialSelectedId: string | null;
  onSelectionChange: (identity: string | null) => void;
  source: ReactNode;
}) {
  const [data, setData] = useState<TextualSearchResponse | null>(null);
  const [selected, setSelected] = useState(0);
  const [showAutoConfirmed, setShowAutoConfirmed] = useState(false);
  const [navigationMessage, setNavigationMessage] = useState("");
  const [emptyDocumentId, setEmptyDocumentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [saving, setSaving] = useState(false);
  const alive = useRef(false);
  const writing = useRef(false);
  const detail = useRef<HTMLElement>(null);
  const list = useRef<HTMLElement>(null);
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    setLoading(true);
    setData(null);
    setLoadError("");
    const load = response.run_id
      ? getReviewWorkspace(
          response.run_id,
          response.review_filter,
          controller.signal,
        )
      : Promise.resolve(response);
    load
      .then((next) => {
        if (controller.signal.aborted) return;
        if (
          next.run_id !== response.run_id ||
          next.scorer_version !== response.scorer_version ||
          next.scorer_library_version !== response.scorer_library_version ||
          next.candidate_policy !== response.candidate_policy ||
          next.semantic?.pipeline !== response.semantic?.pipeline ||
          next.semantic?.score_version !== response.semantic?.score_version
        ) {
          throw Error(
            "The saved comparison metadata has changed. Refresh saved results before reviewing.",
          );
        }
        // Old deferred annotations are pending, not a fourth UI state.
        next.review_counts.unreviewed += next.review_counts.later;
        next.review_counts.later = 0;
        for (const group of next.results) {
          group.review_counts.unreviewed += group.review_counts.later;
          group.review_counts.later = 0;
          for (const item of group.occurrences)
            if (item.review.decision === "later")
              item.review.decision = "unreviewed";
        }
        const flat = next.results
          .flatMap((group) => group.occurrences)
          .filter((item) => !item.auto_confirmed);
        const retained = flat.findIndex(
          (item) => item.occurrence_id === initialSelectedId,
        );
        setData(next);
        setSelected(Math.max(0, retained));
        onSelectionChange(flat[Math.max(0, retained)]?.occurrence_id ?? null);
        onChange(next);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.details) onAbort(error.details);
        else
          setLoadError(
            error instanceof Error
              ? error.message
              : "Could not load the review workspace.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
    // The parent remounts this component for each search/view request. Local saves
    // update counts without restarting the captured workspace request.
  }, [generation]);

  const allEntries =
    data?.results.flatMap((group) =>
      group.occurrences.map((occurrence) => ({
        document: group.document,
        occurrence,
      })),
    ) ?? [];
  const entries = allEntries.filter(
    (item) => showAutoConfirmed || !item.occurrence.auto_confirmed,
  );
  const automaticCount = allEntries.filter(
    (item) => item.occurrence.auto_confirmed,
  ).length;
  const active = emptyDocumentId ? undefined : entries[selected];
  const emptyDocument = data?.document_outcomes.find(
    (item) => item.document.document_id === emptyDocumentId,
  )?.document;
  const locked = disabled || loading || saving;
  const nextPassage = (direction: number, unreviewed: boolean) => {
    if (!active) return undefined;
    for (
      let i = selected + direction;
      i >= 0 && i < entries.length;
      i += direction
    ) {
      if (!unreviewed || entries[i].occurrence.review.decision === "unreviewed")
        return i;
    }
    return undefined;
  };
  const previous = nextPassage(-1, false);
  const next = nextPassage(1, false);
  const previousUnreviewed = nextPassage(-1, true);
  const nextUnreviewed = nextPassage(1, true);
  function toggleAutomatic(show: boolean) {
    setEmptyDocumentId(null);
    const visible = allEntries.filter(
      (item) => show || !item.occurrence.auto_confirmed,
    );
    const index = Math.max(
      0,
      visible.findIndex(
        (item) =>
          item.occurrence.occurrence_id === active?.occurrence.occurrence_id,
      ),
    );
    setShowAutoConfirmed(show);
    setSelected(index);
    onSelectionChange(visible[index]?.occurrence.occurrence_id ?? null);
  }
  function selectDocument(id: string, occurrenceId?: string) {
    if (locked) return;
    const state = data?.document_outcomes.find(
      (item) => item.document.document_id === id,
    )?.state;
    const index = allEntries.findIndex(
      (item) =>
        item.document.document_id === id &&
        (occurrenceId
          ? item.occurrence.occurrence_id === occurrenceId
          : state === "confirmed"
            ? item.occurrence.review.decision === "keep"
            : state === "unreviewed"
              ? item.occurrence.review.decision === "unreviewed"
              : true),
    );
    if (index < 0) {
      setEmptyDocumentId(id);
      onSelectionChange(null);
      requestAnimationFrame(() => {
        detail.current?.focus();
        detail.current?.scrollIntoView({ block: "start" });
      });
      setNavigationMessage(
        "No candidate passages were found for this document at the search thresholds.",
      );
      return;
    }
    setEmptyDocumentId(null);
    const target = allEntries[index];
    const visible = allEntries.filter(
      (item) =>
        showAutoConfirmed ||
        target.occurrence.auto_confirmed ||
        !item.occurrence.auto_confirmed,
    );
    if (target.occurrence.auto_confirmed) setShowAutoConfirmed(true);
    setSelected(
      visible.findIndex(
        (item) =>
          item.occurrence.occurrence_id === target.occurrence.occurrence_id,
      ),
    );
    onSelectionChange(target.occurrence.occurrence_id);
    setNavigationMessage("");
    requestAnimationFrame(() => {
      detail.current?.focus();
      detail.current?.scrollIntoView({ block: "start" });
    });
  }
  function select(index: number, focusList = false) {
    if (locked || index < 0 || index >= entries.length) return;
    setEmptyDocumentId(null);
    setSelected(index);
    setReviewError("");
    setNavigationMessage("");
    onSelectionChange(entries[index].occurrence.occurrence_id);
    if (focusList)
      requestAnimationFrame(() =>
        list.current
          ?.querySelector<HTMLButtonElement>(`[data-index="${index}"]`)
          ?.focus(),
      );
  }
  function listKey(event: KeyboardEvent, index: number) {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const next =
      event.key === "ArrowDown"
        ? index + 1
        : event.key === "ArrowUp"
          ? index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? entries.length - 1
              : null;
    if (next !== null) {
      event.preventDefault();
      select(next, true);
    }
  }
  async function review(decision: ReviewDecision) {
    if (!data || !active || locked || writing.current) return;
    writing.current = true;
    setSaving(true);
    setReviewError("");
    const { document, occurrence } = active;
    try {
      const saved = await saveReview({
        search_run_id: response.run_id ?? undefined,
        occurrence_id: occurrence.occurrence_id,
        document_id: document.document_id,
        revision_id: document.revision_id!,
        processing_job_id: document.processing_job_id!,
        source_artifact_id: document.artifact_id!,
        normalization_version: document.normalization_version!,
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
      if (!alive.current) return;
      const counts = { ...data.review_counts };
      counts[occurrence.review.decision]--;
      counts[saved.decision]++;
      const results = data.results
        .map((group) => {
          const changed = group.occurrences.some(
            (item) => item.occurrence_id === occurrence.occurrence_id,
          );
          const reviewCounts = { ...group.review_counts };
          if (changed) {
            reviewCounts[occurrence.review.decision]--;
            reviewCounts[saved.decision]++;
          }
          const occurrences = group.occurrences
            .map((item) =>
              item.occurrence_id === occurrence.occurrence_id
                ? { ...item, review: saved, auto_confirmed: false }
                : item,
            )
            .filter(
              (item) =>
                data.review_filter === "all" ||
                item.review.decision === data.review_filter,
            );
          return {
            ...group,
            review_counts: reviewCounts,
            occurrences,
            occurrence_total: occurrences.length,
          };
        })
        .filter((group) => group.occurrences.length);
      const remaining = results.reduce(
        (sum, group) => sum + group.occurrences.length,
        0,
      );
      const next = {
        ...data,
        results,
        review_counts: counts,
        total: results.length,
        summary: {
          ...data.summary,
          documents_with_matches: results.length,
          documents_without_matches:
            data.summary.documents_searched - results.length,
          occurrences_total: remaining,
        },
      };
      next.document_outcomes = currentDocumentOutcomes(
        data.document_outcomes,
        next.results,
      );
      const visible = next.results
        .flatMap((group) => group.occurrences)
        .filter((item) => showAutoConfirmed || !item.auto_confirmed);
      setSelected(
        Math.max(
          0,
          visible.findIndex(
            (item) => item.occurrence_id === occurrence.occurrence_id,
          ),
        ),
      );
      setData(next);
      onChange(next);
    } catch (error) {
      if (alive.current)
        setReviewError(
          error instanceof Error ? error.message : "Could not save the review.",
        );
    } finally {
      writing.current = false;
      if (alive.current) setSaving(false);
    }
  }
  if (loading) return <p role="status">Loading saved passages for review …</p>;
  if (loadError)
    return (
      <div className="message error">
        <p role="alert">{loadError}</p>
        <button
          className="secondary"
          disabled={disabled}
          onClick={() => setGeneration((value) => value + 1)}
        >
          Retry loading passages
        </button>
      </div>
    );
  return (
    <>
      <p role="status">
        Automatically confirmed: {automaticCount}{" "}
        {automaticCount === 1 ? "passage" : "passages"}.
      </p>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={showAutoConfirmed}
          disabled={locked}
          onChange={(event) => toggleAutomatic(event.target.checked)}
        />
        Show automatically confirmed passages for review
      </label>
      <div className="review-workspace" aria-busy={locked}>
        <nav className="passage-list" aria-label="Passage list" ref={list}>
          <h3>Passages ({entries.length})</h3>
          <p className="fineprint">
            Select a passage, or use ↑ / ↓ and Home / End. Review states change
            only when you choose a state button.
          </p>
          {entries.map(({ document, occurrence }, index) => (
            <button
              key={occurrence.occurrence_id}
              className="passage-choice"
              tabIndex={selected === index ? 0 : -1}
              aria-controls="selected-passage"
              data-index={index}
              aria-label={`Passage ${index + 1} in ${document.title}`}
              aria-current={selected === index ? "true" : undefined}
              disabled={locked}
              onClick={() => select(index)}
              onKeyDown={(event) => listKey(event, index)}
            >
              <strong>{document.title}</strong>
              <span className="passage-preview">{occurrence.matched_text}</span>
              <span>
                Passage {index + 1} · {reviewLabels[occurrence.review.decision]}
              </span>
              <span>
                Textual {occurrence.score.toFixed(2)}%
                {occurrence.semantic_score !== null &&
                  ` · Semantic ${occurrence.semantic_score.toFixed(2)}%`}
              </span>
            </button>
          ))}
          {!entries.length && (
            <p>
              {automaticCount > 0 && !showAutoConfirmed
                ? "All candidate passages are automatically confirmed. Show them to review their states."
                : "No candidate passages for this selection. This is not proof of absence."}
            </p>
          )}
        </nav>
        <section
          id="selected-passage"
          className="passage-detail"
          ref={detail}
          tabIndex={-1}
          aria-label={
            active ? `Matches in ${active.document.title}` : "Passage details"
          }
        >
          <nav className="passage-navigation" aria-label="Passage navigation">
            <button
              className="secondary"
              disabled={locked || previousUnreviewed === undefined}
              onClick={() =>
                previousUnreviewed !== undefined && select(previousUnreviewed)
              }
            >
              Previous unreviewed
            </button>
            <button
              className="secondary"
              disabled={locked || previous === undefined}
              onClick={() => previous !== undefined && select(previous)}
            >
              Previous
            </button>
            <span role="status">
              {active
                ? `Passage ${selected + 1} of ${entries.length}`
                : "No passage selected"}
            </span>
            <button
              className="secondary"
              disabled={locked || next === undefined}
              onClick={() => next !== undefined && select(next)}
            >
              Next
            </button>
            <button
              className="secondary"
              disabled={locked || nextUnreviewed === undefined}
              onClick={() =>
                nextUnreviewed !== undefined && select(nextUnreviewed)
              }
            >
              Next unreviewed
            </button>
          </nav>
          <p className="fineprint">
            Navigation changes passages without changing their review states.
          </p>
          {!active && emptyDocument && (
            <>
              <h3>{emptyDocument.title}</h3>
              <p>
                No candidate passages passed the search thresholds for this
                document.
              </p>
              {emptyDocument.artifact_id && (
                <OriginalActions id={emptyDocument.artifact_id} />
              )}
            </>
          )}
          {active && (
            <>
              <h3>{active.document.title}</h3>
              <p className="fineprint">
                Revision {active.document.revision_number} ·{" "}
                {active.occurrence.page_reference === "logical"
                  ? "Logical text section"
                  : `Pages: ${active.occurrence.page_numbers.join(", ") || "unavailable"}`}
              </p>
              <Occurrence
                occurrence={active.occurrence}
                mode={response.mode}
                onReview={(decision) => void review(decision)}
                reviewDisabled={locked}
                saving={saving}
                reviewError={reviewError}
                source={source}
                onOpen={() =>
                  onOpen({
                    document_id: active.document.document_id,
                    revision_id: active.document.revision_id,
                    processing_job_id: active.document.processing_job_id,
                    page_number: active.occurrence.page_numbers[0] ?? null,
                  })
                }
              />
              {active.document.artifact_id && (
                <OriginalActions id={active.document.artifact_id} />
              )}
            </>
          )}
        </section>
      </div>
      {navigationMessage && <p role="status">{navigationMessage}</p>}
      <DocumentGroups
        outcomes={data?.document_outcomes ?? []}
        results={data?.results ?? []}
        disabled={locked}
        onSelect={selectDocument}
      />
    </>
  );
}
