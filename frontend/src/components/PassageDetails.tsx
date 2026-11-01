import type { ReactNode } from "react";
import type {
  TextualDocument,
  TextualOccurrence,
  ReviewDecision,
} from "../api";
import { formatDate } from "../format";
export const reviewLabels: Record<ReviewDecision, string> = {
  unreviewed: "Unreviewed",
  keep: "Confirm match",
  dismiss: "Dismiss match",
  later: "Unreviewed",
};

export function Occurrence({
  occurrence,
  mode,
  onOpen,
  onReview,
  reviewDisabled,
  saving,
  reviewError,
  source,
}: {
  source?: ReactNode;
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
          {(["keep", "dismiss", "unreviewed"] as const).map((decision) => (
            <button
              key={decision}
              className="secondary"
              type="button"
              aria-pressed={
                (occurrence.review.decision === "later"
                  ? "unreviewed"
                  : occurrence.review.decision) === decision
              }
              disabled={
                (occurrence.review.decision === "later"
                  ? "unreviewed"
                  : occurrence.review.decision) === decision
              }
              onClick={() => onReview(decision)}
            >
              {reviewLabels[decision]}
            </button>
          ))}
        </div>
        {reviewError && (
          <p role="alert" className="message error">
            {reviewError}
          </p>
        )}
      </fieldset>
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
      {source}
    </article>
  );
}
