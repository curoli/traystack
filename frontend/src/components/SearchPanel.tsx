import { useRef, useState, type FormEvent } from "react";
import {
  artifactUrl,
  searchDocuments,
  type SearchRequest,
  type SearchResponse,
  type SearchResult,
} from "../api";
import { coverageLabel, qualityLabel, warningLabel } from "./processingLabels";

const searchWarnings: Record<string, string> = {
  no_revision: "Noch keine Revision vorhanden.",
  no_selected_text:
    "Noch kein ausgewählter Text vorhanden; Verarbeitung erforderlich.",
  processing_failed:
    "Die Verarbeitung ist fehlgeschlagen; es ist noch kein ausgewählter Text verfügbar.",
  processing_pending:
    "Die Verarbeitung ist noch nicht abgeschlossen; es ist noch kein ausgewählter Text verfügbar.",
  incomplete_extraction:
    "Mindestens eine Seite wurde nicht vollständig ausgelesen.",
  extraction_needs_review: "Die Extraktion muss manuell geprüft werden.",
  quality_unassessed: "Die Erkennungsqualität wurde nicht bewertet.",
  unsupported_normalization_version:
    "Die gespeicherten Normalisierungsregeln werden nicht unterstützt; Neuverarbeitung erforderlich.",
  newer_run_failed:
    "Ein neuerer Verarbeitungslauf ist fehlgeschlagen. Die Suche verwendet den weiterhin ausgewählten früheren Text.",
  newer_run_pending:
    "Eine neuere Verarbeitung ist noch nicht abgeschlossen. Die Suche verwendet den ausgewählten früheren Text.",
  page_location_unavailable:
    "Für diesen Treffer ist keine zuverlässige Seitenzuordnung verfügbar.",
};

function ResultCard({
  result,
  onOpen,
}: {
  result: SearchResult;
  onOpen: (result: SearchResult) => void;
}) {
  const start =
    result.start_offset !== null && result.snippet_start_offset !== null
      ? result.start_offset - result.snippet_start_offset
      : 0;
  // API offsets count Unicode code points; JavaScript string.slice counts UTF-16 units.
  const characters = Array.from(result.snippet || "");
  const end = start + Array.from(result.matched_text || "").length;
  return (
    <article
      className={`search-result ${result.status === "unverifiable" ? "uncertain" : ""}`}
    >
      <div className="section-heading">
        <h4>{result.title}</h4>
        <span className="badge">
          {result.revision_number
            ? `Revision ${result.revision_number}`
            : "Keine Revision"}
        </span>
      </div>
      {result.snippet !== null && (
        <p className="search-snippet">
          {result.snippet_start_offset !== 0 && "…"}
          {characters.slice(0, start).join("")}
          <mark>{characters.slice(start, end).join("")}</mark>
          {characters.slice(end).join("")}
        </p>
      )}
      {result.page_number !== null && (
        <p className="fineprint">
          Seite {result.page_number}
          {result.end_page_number !== result.page_number &&
            `–${result.end_page_number}`}{" "}
          · Erste Fundstelle im{" "}
          {result.offset_basis === "normalized_text"
            ? "normalisierten"
            : "extrahierten"}{" "}
          Text
        </p>
      )}
      {result.warnings.length > 0 && (
        <ul className="search-warnings">
          {result.warnings.map((reason) => (
            <li key={reason}>
              {searchWarnings[reason] || warningLabel(reason)}
            </li>
          ))}
        </ul>
      )}
      <div className="artifact-actions">
        <button className="secondary" onClick={() => onOpen(result)}>
          {result.page_number !== null
            ? `Seite ${result.page_number} ansehen`
            : "Dokument öffnen"}
        </button>
        {result.artifact_id && (
          <a className="download" href={artifactUrl(result.artifact_id)}>
            Original herunterladen ↓
          </a>
        )}
      </div>
      <details className="search-provenance">
        <summary>Herkunft und Verarbeitungsstand</summary>
        <p>
          {result.coverage
            ? coverageLabel[result.coverage]
            : "Nicht verarbeitet"}{" "}
          ·{" "}
          {result.quality_status
            ? qualityLabel[result.quality_status]
            : "Qualität nicht bewertet"}
        </p>
        {result.pages_total !== null && (
          <p>
            {result.pages_processed} von {result.pages_total} Seiten vollständig
            verarbeitet
          </p>
        )}
        <p className="identifier">
          Ausgewählter Lauf: {result.processing_job_id || "Keiner"}
          <br />
          Quelle: {result.artifact_id || "Keine ausgewählte Quelle"}
          <br />
          Normalisierung:{" "}
          {result.normalization_version || "Noch nicht verfügbar"}
        </p>
        {result.latest_job?.error_message && (
          <p className="job-error">
            Neuester Lauf: {result.latest_job.error_message}
          </p>
        )}
      </details>
    </article>
  );
}

export default function SearchPanel({
  onOpen,
}: {
  onOpen: (result: SearchResult) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchRequest["mode"]>("normalized");
  const [relation, setRelation] =
    useState<SearchRequest["relation"]>("contains");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);

  async function run(payload: SearchRequest) {
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    try {
      const result = await searchDocuments(payload);
      if (id === requestId.current) setResponse(result);
    } catch (error) {
      if (id === requestId.current)
        setError(
          error instanceof Error ? error.message : "Suche fehlgeschlagen.",
        );
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    setResponse(null);
    void run({
      query,
      mode,
      relation,
      scope: "latest",
      limit: 10,
      unverifiable_limit: 10,
    });
  }
  function paginate(group: "results" | "unverifiable", delta: number) {
    if (!response) return;
    void run({
      query: response.query,
      mode: response.mode,
      relation: response.relation,
      scope: response.scope,
      limit: response.limit,
      offset: group === "results" ? response.offset + delta : response.offset,
      unverifiable_limit: response.unverifiable_limit,
      unverifiable_offset:
        group === "unverifiable"
          ? response.unverifiable_offset + delta
          : response.unverifiable_offset,
    });
  }
  return (
    <section className="panel search-panel" aria-labelledby="search-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">VOLLSTÄNDIGER REVISIONSTEXT</p>
          <h2 id="search-heading">Textpassagen suchen</h2>
        </div>
        <span className="scope-tag">Neueste Revision je Dokument</span>
      </div>
      <form onSubmit={submit} className="search-form">
        <div className="search-query">
          <label htmlFor="search-query">Textpassage</label>
          <textarea
            id="search-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            maxLength={2000}
            rows={2}
            placeholder="z. B. The receiving party shall not disclose confidential information"
          />
        </div>
        <div>
          <label htmlFor="search-mode">Suchmodus</label>
          <select
            id="search-mode"
            value={mode}
            onChange={(event) =>
              setMode(event.target.value as SearchRequest["mode"])
            }
          >
            <option value="normalized">Normalisiert</option>
            <option value="exact">Exakt</option>
          </select>
        </div>
        <div>
          <label htmlFor="search-relation">Gesuchte Dokumente</label>
          <select
            id="search-relation"
            value={relation}
            onChange={(event) =>
              setRelation(event.target.value as SearchRequest["relation"])
            }
          >
            <option value="contains">Enthält die Passage</option>
            <option value="lacks">Nicht im extrahierten Text gefunden</option>
          </select>
        </div>
        <button className="primary" disabled={busy || !query.trim()}>
          {busy ? "Suche läuft …" : "Suche ausführen"}
        </button>
      </form>
      <p className="fineprint">
        {mode === "normalized"
          ? "Normalisiert gleicht Groß-/Kleinschreibung, Leerzeichen und Zeilenumbrüche an. Zahlen, Negationen, Satzzeichen und Bindestriche bleiben erhalten."
          : "Exakt berücksichtigt Groß-/Kleinschreibung, Leerzeichen und Zeilenumbrüche im extrahierten Text."}
      </p>
      <p className="search-notice">
        „Nicht gefunden“ bezieht sich auf den ausgewählten extrahierten Text.
        Unvollständige oder auffällige Extraktionen sind unverifizierbar; ein
        Suchergebnis ist keine rechtliche Bewertung.
      </p>
      {busy && (
        <p role="status" className="job-progress">
          Der gesamte ausgewählte Text wird geprüft …
        </p>
      )}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {response && (
        <div className="search-response" aria-busy={busy}>
          <p className="search-query-summary">
            Ergebnisse für <strong>„{response.query}“</strong> ·{" "}
            {response.mode === "exact" ? "Exakt" : "Normalisiert"} ·{" "}
            {response.relation === "contains"
              ? "Enthält"
              : "Nicht gefunden im extrahierten Text"}
          </p>
          <p className="fineprint">
            {response.summary.documents_total} Dokumente im Suchumfang ·{" "}
            {response.summary.found} gefunden ·{" "}
            {response.summary.not_found_in_processed_text} nicht im
            verarbeiteten Text gefunden · {response.summary.unverifiable}{" "}
            unverifizierbar
          </p>
          <p className="fineprint">
            Momentaufnahme vom{" "}
            {new Date(response.searched_at).toLocaleString("de-DE")}. Nach neuer
            Verarbeitung die Suche erneut ausführen.
          </p>
          <section aria-label="Suchtreffer">
            <h3>
              {response.relation === "contains"
                ? "Gefundene Dokumente"
                : "Nicht im extrahierten Text gefunden"}{" "}
              ({response.total})
            </h3>
            {response.results.length ? (
              response.results.map((result) => (
                <ResultCard
                  key={result.document_id}
                  result={result}
                  onOpen={onOpen}
                />
              ))
            ) : (
              <p className="search-empty">
                {response.summary.documents_total === 0
                  ? "Noch keine Dokumente vorhanden. Lade einen Demo-Vertrag hoch."
                  : response.total > 0
                    ? "Diese Ergebnisseite ist nach einer Aktualisierung leer. Bitte zurückblättern oder erneut suchen."
                    : "Keine Ergebnisse für diese Auswahl."}
              </p>
            )}
            <nav className="pagination" aria-label="Trefferseiten">
              <button
                className="secondary"
                disabled={busy || response.offset === 0}
                onClick={() => paginate("results", -response.limit)}
              >
                Treffer zurück
              </button>
              <span>
                {response.results.length ? response.offset + 1 : 0}–
                {response.results.length
                  ? response.offset + response.results.length
                  : 0}{" "}
                von {response.total}
              </span>
              <button
                className="secondary"
                disabled={
                  busy || response.offset + response.limit >= response.total
                }
                onClick={() => paginate("results", response.limit)}
              >
                Treffer weiter
              </button>
            </nav>
          </section>
          <section
            className="search-unknown"
            aria-label="Unverifizierbare Dokumente"
          >
            <h3>Unverifizierbar ({response.unverifiable_total})</h3>
            {response.unverifiable.length ? (
              response.unverifiable.map((result) => (
                <ResultCard
                  key={result.document_id}
                  result={result}
                  onOpen={onOpen}
                />
              ))
            ) : (
              <p className="search-empty">
                {response.unverifiable_total > 0
                  ? "Diese Ergebnisseite ist nach einer Aktualisierung leer. Bitte zurückblättern oder erneut suchen."
                  : "Keine unverifizierbaren Dokumente in diesem Suchumfang."}
              </p>
            )}
            <nav className="pagination" aria-label="Unverifizierbare Seiten">
              <button
                className="secondary"
                disabled={busy || response.unverifiable_offset === 0}
                onClick={() =>
                  paginate("unverifiable", -response.unverifiable_limit)
                }
              >
                Unverifizierbare zurück
              </button>
              <span>
                {response.unverifiable.length
                  ? response.unverifiable_offset + 1
                  : 0}
                –
                {response.unverifiable.length
                  ? response.unverifiable_offset + response.unverifiable.length
                  : 0}{" "}
                von {response.unverifiable_total}
              </span>
              <button
                className="secondary"
                disabled={
                  busy ||
                  response.unverifiable_offset + response.unverifiable_limit >=
                    response.unverifiable_total
                }
                onClick={() =>
                  paginate("unverifiable", response.unverifiable_limit)
                }
              >
                Unverifizierbare weiter
              </button>
            </nav>
          </section>
        </div>
      )}
    </section>
  );
}
