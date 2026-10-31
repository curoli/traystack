import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type KeyboardEvent,
} from "react";
import {
  ApiError,
  artifactUrl,
  getReviewWorkspace,
  saveReview,
  type ReviewDecision,
  type SearchAbortDetails,
  type SearchTarget,
  type TextualSearchResponse,
} from "../api";
import { Occurrence, Provenance, reviewLabels } from "./PassageDetails";

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
        const flat = next.results.flatMap((group) => group.occurrences);
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

  const entries =
    data?.results.flatMap((group) =>
      group.occurrences.map((occurrence) => ({
        document: group.document,
        occurrence,
      })),
    ) ?? [];
  const active = entries[selected];
  const locked = disabled || loading || saving;
  const nextUnreviewed = [...entries.keys()]
    .slice(selected + 1)
    .concat([...entries.keys()].slice(0, selected))
    .find(
      (index) => entries[index].occurrence.review.decision === "unreviewed",
    );
  function select(index: number, focusList = false) {
    if (locked || index < 0 || index >= entries.length) return;
    setSelected(index);
    setReviewError("");
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
                ? { ...item, review: saved }
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
      setData(next);
      onChange(next);
      if (data.review_filter !== "all" && decision !== data.review_filter) {
        setSelected(Math.min(selected, Math.max(0, remaining - 1)));
        const flat = results.flatMap((group) => group.occurrences);
        onSelectionChange(
          flat[Math.min(selected, Math.max(0, remaining - 1))]?.occurrence_id ??
            null,
        );
        requestAnimationFrame(() =>
          detail.current?.focus({ preventScroll: true }),
        );
      }
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
    <div className="review-workspace" aria-busy={locked}>
      <nav className="passage-list" aria-label="Passage list" ref={list}>
        <h3>Passages ({entries.length})</h3>
        <p className="fineprint">
          Use ↑ / ↓ or Home / End in this list. Tab to the review controls.
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
            No candidate passages for this selection. This is not proof of
            absence.
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
            disabled={locked || !active || selected === 0}
            onClick={() => select(selected - 1)}
          >
            Previous passage
          </button>
          <span role="status">
            {active
              ? `Passage ${selected + 1} of ${entries.length}`
              : "No passage selected"}
          </span>
          <button
            className="secondary"
            disabled={locked || !active || selected + 1 >= entries.length}
            onClick={() => select(selected + 1)}
          >
            Next passage
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
          Navigation follows the current review filter. Next unreviewed wraps
          within this view.
        </p>
        {active && (
          <>
            <h3>{active.document.title}</h3>
            <p className="fineprint">
              Revision {active.document.revision_number} ·{" "}
              {active.occurrence.page_reference === "logical"
                ? "Logical text section"
                : `Pages: ${active.occurrence.page_numbers.join(", ") || "unavailable"}`}
            </p>
            <Provenance document={active.document} />
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
              <a
                className="download"
                href={artifactUrl(active.document.artifact_id)}
              >
                Download original ↓
              </a>
            )}
          </>
        )}
      </section>
    </div>
  );
}
