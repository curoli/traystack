import type { Revision } from "../api";

export const statusLabel: Record<Revision["processing_status"], string> = {
  not_processed: "Nicht verarbeitet",
  queued: "Wartet auf Verarbeitung",
  running: "Wird verarbeitet",
  completed: "Verarbeitet",
  failed: "Verarbeitung fehlgeschlagen",
};
export const qualityLabel = {
  no_known_issue: "Keine Auffälligkeit erkannt",
  needs_review: "Manuelle Prüfung erforderlich",
  unassessed: "Qualität nicht bewertet",
};
export const coverageLabel = {
  complete: "Vollständig verarbeitet",
  partial: "Teilweise verarbeitet",
  unavailable: "Text nicht verfügbar",
};
const warnings: Record<string, string> = {
  manual_review_requested: "Manuelle Prüfung wurde angefordert.",
  no_text_detected:
    "Kein lesbarer Text erkannt; auch leere Seiten werden vorsichtshalber zur Prüfung markiert.",
  low_ocr_confidence: "Die OCR meldet geringe Erkennungssicherheit.",
  ocr_confidence_unavailable:
    "Die OCR hat keine bewertbaren Konfidenzwerte geliefert.",
  suspicious_text:
    "Der erkannte Text enthält auffällige Zeichen oder sehr wenig Inhalt.",
  null_character_replaced:
    "Ein nicht speicherbares Nullzeichen wurde durch ein Ersatzzeichen markiert.",
  ocr_timeout: "Die OCR hat das Zeitlimit überschritten.",
  ocr_failed: "Die OCR konnte diese Seite nicht verarbeiten.",
  page_extraction_failed: "Die Seite konnte nicht ausgelesen werden.",
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
