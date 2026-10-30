import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  getDocument,
  listDocuments,
  uploadDocument,
  type Document,
  type SearchResult,
  type SearchPageLocation,
} from "./api";

import { formatDate } from "./format";

import SearchPanel from "./components/SearchPanel";
import ArtifactCard from "./components/ArtifactCard";
import ProcessingDetails from "./components/ProcessingDetails";
import { needsReview, statusLabel } from "./components/processingLabels";

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Request failed.";

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
        `“${document.title}” was saved. The original is ready to download.`,
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
        <a className="brand" href="/" aria-label="TrayStack home">
          <span className="brand-mark">T</span>TrayStack
        </a>
        <span className="environment">Local demo</span>
        <a className="api-link" href="/docs" target="_blank" rel="noreferrer">
          API documentation ↗
        </a>
      </header>
      <main>
        <div className="intro">
          <p className="eyebrow">CONTRACT LIBRARY</p>
          <h1>
            Keep your originals.
            <br />
            Trace every result.
          </h1>
          <p className="lead">
            Contracts and scans in one place, with unchanged original files and
            traceable file information.
          </p>
        </div>
        <div className="scope-note">
          <strong>Full-text search for your contracts.</strong> Upload documents
          and start processing in the details. Then search the latest revision
          of each document and inspect matches and quality warnings.
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
            <p className="eyebrow">NEW DOCUMENT</p>
            <h2>Add a contract</h2>
            <form onSubmit={upload}>
              <label htmlFor="title">Title</label>
              <input
                id="title"
                name="title"
                type="text"
                required
                maxLength={300}
                placeholder="e.g. Confidentiality agreement"
              />
              <label htmlFor="file">Original file</label>
              <div className="file-field">
                <input
                  id="file"
                  name="file"
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.txt,.htm,.html"
                  required
                />
                <small>
                  PDF, JPEG, PNG, UTF-8 TXT or HTML · up to 25 MiB by default
                </small>
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  name="requires_manual_review"
                  value="true"
                />
                <span>
                  Manual review required
                  <small>
                    For handwriting and hard-to-read scans. Remains flagged for
                    review even after successful OCR.
                  </small>
                </span>
              </label>
              <button className="primary" disabled={uploading}>
                {uploading ? "Saving …" : "Save document"}
                <span aria-hidden="true">↑</span>
              </button>
            </form>
            <p className="fineprint">
              Please use synthetic test contracts. The original is stored byte
              for byte.
            </p>
          </aside>
          <section className="panel library" aria-labelledby="library-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">YOUR LIBRARY</p>
                <h2 id="library-heading">
                  Documents <span className="count">{total}</span>
                </h2>
              </div>
              <button
                className="secondary"
                onClick={() => setGeneration((value) => value + 1)}
                disabled={loading}
              >
                Refresh
              </button>
            </div>
            {listError ? (
              <div role="alert" className="message error">
                {listError}
              </div>
            ) : loading ? (
              <p role="status" className="empty">
                Loading documents …
              </p>
            ) : documents.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden="true">
                  ▤
                </div>
                <h3>Room for your first contract.</h3>
                <p>
                  Upload a demo file using the form.
                  <br />
                  Your stored documents will appear here.
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
                          {formatDate(document.created_at)} ·{" "}
                          {document.revisions.length}{" "}
                          {document.revisions.length === 1
                            ? "revision"
                            : "revisions"}
                        </small>
                      </span>
                      <span className="badge">
                        {openingDocumentId === document.id
                          ? "Opening …"
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
            <nav className="pagination" aria-label="Document pages">
              <button
                className="secondary"
                disabled={offset === 0 || loading}
                onClick={() => setOffset((value) => Math.max(0, value - 20))}
              >
                ← Previous
              </button>
              <span>Page {Math.floor(offset / 20) + 1}</span>
              <button
                className="secondary"
                disabled={offset + 20 >= total || loading}
                onClick={() => setOffset((value) => value + 20)}
              >
                Next →
              </button>
            </nav>
          </section>
        </div>
        {documents.some((document) => document.revisions.some(needsReview)) && (
          <section
            className="panel review-group"
            aria-labelledby="review-heading"
          >
            <p className="eyebrow">MANUAL REVIEW · CURRENT LIST PAGE</p>
            <h2 id="review-heading">Review originals</h2>
            <p>
              These documents are flagged for review or have extraction quality
              issues. Open the original and verify the content.
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
                <p className="eyebrow">DOCUMENT DETAILS</p>
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
                Close
              </button>
            </div>
            <p className="identifier">Document ID: {selected.id}</p>
            {Object.keys(selected.metadata).length > 0 && (
              <details>
                <summary>Metadata</summary>
                <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
              </details>
            )}
            {selected.revisions.map((revision) => (
              <div className="revision" key={revision.id}>
                <h3>
                  Revision {revision.revision_number} {revision.label}
                </h3>
                <p className="identifier">Revision ID: {revision.id}</p>
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
        TrayStack · Traceable document storage
        <span>Local prototype for the Riverty case study</span>
      </footer>
    </>
  );
}
