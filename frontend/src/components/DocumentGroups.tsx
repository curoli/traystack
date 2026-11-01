import { useState } from "react";
import { artifactUrl, type TextualSearchResponse } from "../api";

export default function DocumentGroups({
  outcomes,
  onSelect,
  disabled,
}: {
  outcomes: TextualSearchResponse["document_outcomes"];
  disabled: boolean;
  onSelect: (documentId: string) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [limits, setLimits] = useState<Record<string, number>>({});
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
        const rows = outcomes.filter((item) => item.state === state);
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
