import { useState } from "react";
import { artifactUrl, type TextualSearchResponse } from "../api";

export function currentDocumentOutcomes(
  outcomes: TextualSearchResponse["document_outcomes"],
  results: TextualSearchResponse["results"],
): TextualSearchResponse["document_outcomes"] {
  const passages = new Map(
    results.map((group) => [group.document.document_id, group.occurrences]),
  );
  return outcomes.map((item) => {
    const matches = passages.get(item.document.document_id) ?? [];
    return {
      ...item,
      state: matches.some((p) => p.review.decision === "keep")
        ? "confirmed"
        : matches.some(
              (p) =>
                p.review.decision === "unreviewed" ||
                p.review.decision === "later",
            )
          ? "unreviewed"
          : "no_active_match",
    };
  });
}

export default function DocumentGroups({
  outcomes,
  results,
  onSelect,
  disabled,
}: {
  outcomes: TextualSearchResponse["document_outcomes"];
  results: TextualSearchResponse["results"];
  disabled: boolean;
  onSelect: (documentId: string, occurrenceId?: string) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [limits, setLimits] = useState<Record<string, number>>({});
  const passages = new Map(
    results.map((group) => [group.document.document_id, group.occurrences]),
  );
  const currentOutcomes = currentDocumentOutcomes(outcomes, results);
  return (
    <section className="document-groups" aria-label="Document match groups">
      <h3>Documents in this search</h3>
      <p className="fineprint">
        These groups reflect the candidate passages and their current review
        states. The last group is not proof that equivalent wording is absent.
      </p>
      {(
        [
          ["confirmed", "Documents with at least one confirmed match"],
          [
            "unreviewed",
            "Documents with no confirmed match but at least one unreviewed match",
          ],
          [
            "no_active_match",
            "Documents with no confirmed or unreviewed match",
          ],
        ] as const
      ).map(([state, label]) => {
        const rows = currentOutcomes.filter((item) => item.state === state);
        return (
          <details
            key={state}
            onToggle={(event) => {
              const open = event.currentTarget.open;
              setExpanded((current) => ({ ...current, [state]: open }));
            }}
          >
            <summary>
              {label} ({rows.length})
            </summary>
            {expanded[state] && !rows.length && (
              <p>No documents in this group.</p>
            )}
            {expanded[state] &&
              rows.slice(0, limits[state] ?? 100).map(({ document }) => (
                <div className="document-outcome" key={document.document_id}>
                  <button
                    className="secondary"
                    disabled={disabled}
                    onClick={() => onSelect(document.document_id)}
                  >
                    {document.title}
                  </button>
                  <ul aria-label={`Passages in ${document.title}`}>
                    {(passages.get(document.document_id) ?? []).map(
                      (passage, index) => (
                        <li key={passage.occurrence_id}>
                          <a
                            href="#selected-passage"
                            aria-disabled={disabled || undefined}
                            onClick={(event) => {
                              event.preventDefault();
                              if (!disabled)
                                onSelect(
                                  document.document_id,
                                  passage.occurrence_id,
                                );
                            }}
                          >
                            Passage {index + 1} —{" "}
                            {passage.review.decision === "keep"
                              ? "Confirmed"
                              : passage.review.decision === "dismiss"
                                ? "Dismissed"
                                : "Unreviewed"}
                            {passage.auto_confirmed ? " (automatic)" : ""}
                          </a>
                          <span className="passage-preview">
                            {passage.matched_text}
                          </span>
                        </li>
                      ),
                    )}
                  </ul>
                  {!passages.get(document.document_id)?.length && (
                    <p>No candidate passages.</p>
                  )}
                  {document.artifact_id && (
                    <a
                      className="download"
                      href={artifactUrl(document.artifact_id)}
                    >
                      Download original ↓
                    </a>
                  )}
                </div>
              ))}
            {expanded[state] && rows.length > (limits[state] ?? 100) && (
              <button
                className="secondary"
                onClick={() =>
                  setLimits((current) => ({
                    ...current,
                    [state]: (current[state] ?? 100) + 100,
                  }))
                }
              >
                Show more documents
              </button>
            )}
          </details>
        );
      })}
    </section>
  );
}
