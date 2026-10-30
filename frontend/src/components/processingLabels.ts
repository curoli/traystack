import type { Revision } from "../api";

export const statusLabel: Record<Revision["processing_status"], string> = {
  not_processed: "Not processed",
  queued: "Queued for processing",
  running: "Processing",
  completed: "Processed",
  failed: "Processing failed",
};
export const qualityLabel = {
  no_known_issue: "No known quality issue",
  needs_review: "Manual review required",
  unassessed: "Quality not assessed",
};
export const coverageLabel = {
  complete: "Fully processed",
  partial: "Partially processed",
  unavailable: "Text unavailable",
};
const warnings: Record<string, string> = {
  manual_review_requested: "Manual review was requested.",
  no_text_detected:
    "No readable text detected; blank pages are also flagged for review as a precaution.",
  low_ocr_confidence: "OCR reports low recognition confidence.",
  ocr_confidence_unavailable: "OCR did not provide usable confidence scores.",
  suspicious_text:
    "The extracted text contains unusual characters or very little content.",
  null_character_replaced:
    "A null character that cannot be stored was marked with a replacement character.",
  ocr_timeout: "OCR exceeded the time limit.",
  ocr_failed: "OCR could not process this page.",
  page_extraction_failed: "The page could not be extracted.",
};
export const warningLabel = (reason: string) => warnings[reason] || reason;
export function needsReview(revision: Revision): boolean {
  return (
    (revision.text_index !== null &&
      revision.text_index.quality_status !== "no_known_issue") ||
    revision.artifacts.some(
      (artifact) => artifact.parameters.requires_manual_review === true,
    ) ||
    revision.jobs.some((job) => job.parameters.requires_manual_review === true)
  );
}
