import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  artifactUrl,
  getDocument,
  listDocuments,
  uploadDocument,
  type Document,
} from "./api";

const date = (value: string) =>
  new Date(value).toLocaleString("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  });
const size = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
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
  const detailRequest = useRef(0);

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

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setError("");
    setNotice("");
    setUploading(true);
    try {
      const document = await uploadDocument(new FormData(form));
      detailRequest.current++;
      setSelected(document);
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

  async function openDocument(id: string) {
    const requestId = ++detailRequest.current;
    setError("");
    try {
      const document = await getDocument(id);
      if (requestId === detailRequest.current) setSelected(document);
    } catch (error) {
      if (requestId === detailRequest.current) setError(errorText(error));
    }
  }

  return (
    <>
      <header className="topbar">
        <a className="brand" href="/" aria-label="TrayStack Startseite">
          <span className="brand-mark">T</span>TrayStack
        </a>
        <span className="environment">Lokale Demo · Meilenstein 1</span>
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
          <strong>Aktueller Stand: Ablage und Download.</strong> Textextraktion,
          OCR und Suche folgen in den nächsten Meilensteinen. Hochgeladene
          Dokumente sind noch nicht verarbeitet.
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
                    Für Handschrift und schwer lesbare Scans. Wird für die
                    spätere Verarbeitung vorgemerkt.
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
                      <span className="badge">Nicht verarbeitet</span>
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
        {selected && (
          <section className="panel details" aria-labelledby="detail-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">DOKUMENTDETAILS</p>
                <h2 id="detail-heading">{selected.title}</h2>
              </div>
              <button
                className="secondary"
                onClick={() => {
                  detailRequest.current++;
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
                {revision.artifacts.map((artifact) => (
                  <article className="artifact" key={artifact.id}>
                    <div className="artifact-heading">
                      <div>
                        <span className="eyebrow">ORIGINAL</span>
                        <h3>{artifact.original_filename}</h3>
                      </div>
                      <a className="download" href={artifactUrl(artifact.id)}>
                        Original herunterladen ↓
                      </a>
                    </div>
                    <dl>
                      <div>
                        <dt>Dateityp / Größe</dt>
                        <dd>
                          {artifact.mime_type} · {size(artifact.size_bytes)}
                        </dd>
                      </div>
                      <div>
                        <dt>Verarbeitung</dt>
                        <dd>
                          Noch nicht verarbeitet
                          {artifact.parameters.requires_manual_review ===
                            true && " · Manuelle Prüfung vorgemerkt"}
                        </dd>
                      </div>
                      <div>
                        <dt>Artefakt-ID</dt>
                        <dd>{artifact.id}</dd>
                      </div>
                      <div>
                        <dt>SHA-256 der Originaldatei</dt>
                        <dd className="hash">{artifact.sha256}</dd>
                      </div>
                    </dl>
                  </article>
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
