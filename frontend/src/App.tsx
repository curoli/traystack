import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  getDocument,
  listDocuments,
  uploadDocument,
  type Document,
  type SearchResult,
  type SearchPageLocation,
} from "./api";

import SearchPanel from "./components/SearchPanel";
import ArtifactCard from "./components/ArtifactCard";
import ProcessingDetails from "./components/ProcessingDetails";
import { needsReview, statusLabel } from "./components/processingLabels";

const date = (value: string) =>
  new Date(value).toLocaleString("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  });
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Anfrage fehlgeschlagen.";

export default function App() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [generation, setGeneration] = useState(0);
  const [selected, setSelected] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [notice, setNotice] = useState("");
  const [openingDocumentId, setOpeningDocumentId] = useState<string | null>(
    null,
  );
  const [detailNavigation, setDetailNavigation] = useState(0);
  const [searchLocation, setSearchLocation] =
    useState<SearchPageLocation | null>(null);
  const detailRequest = useRef(0);
  const detailsRef = useRef<HTMLElement>(null);
  const detailHeadingRef = useRef<HTMLHeadingElement>(null);

  // Navigate only after an explicit open/upload, never on background polling.
  // A separate counter also handles opening the already selected document again.
  useEffect(() => {
    if (detailNavigation === 0) return;
    detailHeadingRef.current?.focus({ preventScroll: true });
    detailsRef.current?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [detailNavigation]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setListError("");
    listDocuments(offset)
      .then((result) => {
        if (active) {
          setDocuments(result.items);
          setTotal(result.total);
        }
      })
      .catch((error) => {
        if (active) setListError(errorText(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [offset, generation]);

  // Refresh list and the open document without hiding their contents while a worker runs.
  useEffect(() => {
    let alive = true;
    const selectedId = selected?.id;
    const timer = window.setInterval(async () => {
      try {
        const result = await listDocuments(offset);
        if (alive) {
          setDocuments(result.items);
          setTotal(result.total);
          setListError("");
        }
        if (selectedId) {
          const detail = await getDocument(selectedId);
          if (alive)
            setSelected((current) =>
              current?.id === selectedId ? detail : current,
            );
        }
      } catch (error) {
        if (alive) setListError(errorText(error));
      }
    }, 2000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [offset, selected?.id]);

  async function refreshDocument(id: string) {
    const document = await getDocument(id);
    setSelected((current) => (current?.id === id ? document : current));
    setDocuments((current) =>
      current.map((item) => (item.id === id ? document : item)),
    );
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setError("");
    setNotice("");
    setUploading(true);
    try {
      const document = await uploadDocument(new FormData(form));
      detailRequest.current++;
      setOpeningDocumentId(null);
      setSearchLocation(null);
      setSelected(document);
      setDetailNavigation((value) => value + 1);
      setOffset(0);
      setGeneration((value) => value + 1);
      setNotice(
        `„${document.title}“ wurde gespeichert. Das Original ist zum Download bereit.`,
      );
      form.reset();
    } catch (error) {
      setError(errorText(error));
    } finally {
      setUploading(false);
    }
  }

  async function openDocument(id: string, result?: SearchResult) {
    const requestId = ++detailRequest.current;
    setError("");
    setOpeningDocumentId(id);
    try {
      const document = await getDocument(id);
      if (requestId === detailRequest.current) {
        setSelected(document);
        setSearchLocation(
          result?.revision_id &&
            result.processing_job_id &&
            result.page_number !== null
            ? {
                revisionId: result.revision_id,
                processingJobId: result.processing_job_id,
                pageNumber: result.page_number,
                requestId,
              }
            : null,
        );
        setDetailNavigation((value) => value + 1);
      }
    } catch (error) {
      if (requestId === detailRequest.current) setError(errorText(error));
    } finally {
      if (requestId === detailRequest.current) setOpeningDocumentId(null);
    }
  }

  return (
    <>
      <header className="topbar">
        <a className="brand" href="/" aria-label="TrayStack Startseite">
          <span className="brand-mark">T</span>TrayStack
        </a>
        <span className="environment">Lokale Demo · Meilenstein 3</span>
        <a className="api-link" href="/docs" target="_blank" rel="noreferrer">
          API-Dokumentation ↗
        </a>
      </header>
      <main>
        <div className="intro">
          <p className="eyebrow">VERTRAGSBIBLIOTHEK</p>
          <h1>
            Originale sicher ablegen.
            <br />
            Herkunft im Blick behalten.
          </h1>
          <p className="lead">
            PDFs und Scans an einem Ort – mit unveränderten Originaldateien und
            nachvollziehbaren Dateiinformationen.
          </p>
        </div>
        <div className="scope-note">
          <strong>Volltextsuche für deine Verträge.</strong> Lade Dokumente hoch
          und starte die Verarbeitung in den Details. Suche anschließend über
          die neueste Revision und prüfe Fundstellen und Qualitätswarnungen.
        </div>
        {notice && (
          <div role="status" className="message success">
            {notice}
          </div>
        )}
        {error && (
          <div role="alert" className="message error">
            {error}
          </div>
        )}
        <SearchPanel
          onOpen={(result) => {
            void openDocument(result.document_id, result);
          }}
        />
        <div className="workspace">
          <aside className="panel upload-panel">
            <p className="eyebrow">NEUES DOKUMENT</p>
            <h2>Vertrag hinzufügen</h2>
            <form onSubmit={upload}>
              <label htmlFor="title">Titel</label>
              <input
                id="title"
                name="title"
                type="text"
                required
                maxLength={300}
                placeholder="z. B. Vertraulichkeitsvereinbarung"
              />
              <label htmlFor="file">Originaldatei</label>
              <div className="file-field">
                <input
                  id="file"
                  name="file"
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png"
                  required
                />
                <small>
                  PDF, JPEG oder PNG · maximal 25 MB in der
                  Standardkonfiguration
                </small>
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  name="requires_manual_review"
                  value="true"
                />
                <span>
                  Manuelle Prüfung erforderlich
                  <small>
                    Für Handschrift und schwer lesbare Scans. Bleibt auch nach
                    erfolgreicher OCR als Prüfbedarf sichtbar.
                  </small>
                </span>
              </label>
              <button className="primary" disabled={uploading}>
                {uploading ? "Wird gespeichert …" : "Dokument speichern"}
                <span aria-hidden="true">↑</span>
              </button>
            </form>
            <p className="fineprint">
              Bitte synthetische Testverträge verwenden. Das Original wird
              bytegetreu gespeichert.
            </p>
          </aside>
          <section className="panel library" aria-labelledby="library-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">DEINE ABLAGE</p>
                <h2 id="library-heading">
                  Dokumente <span className="count">{total}</span>
                </h2>
              </div>
              <button
                className="secondary"
                onClick={() => setGeneration((value) => value + 1)}
                disabled={loading}
              >
                Aktualisieren
              </button>
            </div>
            {listError ? (
              <div role="alert" className="message error">
                {listError}
              </div>
            ) : loading ? (
              <p role="status" className="empty">
                Dokumente werden geladen …
              </p>
            ) : documents.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden="true">
                  ▤
                </div>
                <h3>Platz für deinen ersten Vertrag.</h3>
                <p>
                  Lade links eine Demo-Datei hoch.
                  <br />
                  Hier erscheinen die tatsächlich gespeicherten Dokumente.
                </p>
              </div>
            ) : (
              <ul className="document-list">
                {documents.map((document) => (
                  <li key={document.id}>
                    <button
                      className={`document-row ${selected?.id === document.id ? "selected" : ""}`}
                      onClick={() => openDocument(document.id)}
                      aria-pressed={selected?.id === document.id}
                      aria-busy={openingDocumentId === document.id}
                    >
                      <span className="document-icon" aria-hidden="true">
                        ▤
                      </span>
                      <span className="document-info">
                        <strong>{document.title}</strong>
                        <small>
                          {date(document.created_at)} ·{" "}
                          {document.revisions.length} Revision(en)
                        </small>
                      </span>
                      <span className="badge">
                        {openingDocumentId === document.id
                          ? "Wird geöffnet …"
                          : statusLabel[
                              document.revisions.at(-1)?.processing_status ||
                                "not_processed"
                            ]}
                      </span>
                      <span aria-hidden="true">→</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <nav className="pagination" aria-label="Dokumentseiten">
              <button
                className="secondary"
                disabled={offset === 0 || loading}
                onClick={() => setOffset((value) => Math.max(0, value - 20))}
              >
                ← Zurück
              </button>
              <span>Seite {Math.floor(offset / 20) + 1}</span>
              <button
                className="secondary"
                disabled={offset + 20 >= total || loading}
                onClick={() => setOffset((value) => value + 20)}
              >
                Weiter →
              </button>
            </nav>
          </section>
        </div>
        {documents.some((document) => document.revisions.some(needsReview)) && (
          <section
            className="panel review-group"
            aria-labelledby="review-heading"
          >
            <p className="eyebrow">MANUELLE PRÜFUNG · AKTUELLE LISTENSEITE</p>
            <h2 id="review-heading">Original prüfen</h2>
            <p>
              Diese Dokumente haben eine Prüfvormerkung oder auffällige
              Extraktionsqualität. Öffne das Original und verifiziere den
              Inhalt.
            </p>
            <ul>
              {documents
                .filter((document) => document.revisions.some(needsReview))
                .map((document) => (
                  <li key={document.id}>
                    <button
                      className="review-link"
                      onClick={() => openDocument(document.id)}
                    >
                      {document.title} →
                    </button>
                  </li>
                ))}
            </ul>
          </section>
        )}
        {selected && (
          <section
            ref={detailsRef}
            className="panel details"
            aria-labelledby="detail-heading"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">DOKUMENTDETAILS</p>
                <h2 id="detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                  {selected.title}
                </h2>
              </div>
              <button
                className="secondary"
                onClick={() => {
                  detailRequest.current++;
                  setOpeningDocumentId(null);
                  setSelected(null);
                }}
              >
                Schließen
              </button>
            </div>
            <p className="identifier">Dokument-ID: {selected.id}</p>
            {Object.keys(selected.metadata).length > 0 && (
              <details>
                <summary>Metadaten</summary>
                <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
              </details>
            )}
            {selected.revisions.map((revision) => (
              <div className="revision" key={revision.id}>
                <h3>
                  Revision {revision.revision_number} {revision.label}
                </h3>
                <p className="identifier">Revision-ID: {revision.id}</p>
                <ProcessingDetails
                  revision={revision}
                  requestedPage={
                    searchLocation?.revisionId === revision.id
                      ? searchLocation
                      : undefined
                  }
                  onUpdated={() => refreshDocument(selected.id)}
                />
                {revision.artifacts.map((artifact) => (
                  <ArtifactCard
                    key={artifact.id}
                    artifact={artifact}
                    revision={revision}
                  />
                ))}
              </div>
            ))}
          </section>
        )}
      </main>
      <footer>
        TrayStack · Nachvollziehbare Dokumentablage
        <span>Lokaler Prototyp für die Riverty Case Study</span>
      </footer>
    </>
  );
}
