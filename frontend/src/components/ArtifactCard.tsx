import { useState } from "react";
import {
  artifactUrl,
  getArtifactText,
  type Artifact,
  type Revision,
} from "../api";
import { statusLabel } from "./processingLabels";

const labels: Record<string, string> = {
  original: "Original",
  structured_json: "Structured extraction · JSON",
  extracted_markdown: "Extracted text · Markdown",
};
export default function ArtifactCard({
  artifact,
  revision,
}: {
  artifact: Artifact;
  revision: Revision;
}) {
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const original = artifact.kind === "original";
  const previewable =
    ["text/markdown", "application/json"].includes(artifact.mime_type) &&
    artifact.size_bytes <= 512 * 1024;
  async function togglePreview() {
    if (preview !== null) {
      setPreview(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      setPreview(await getArtifactText(artifact.id));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Preview failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="artifact">
      <div className="artifact-heading">
        <div>
          <span className="eyebrow">
            {labels[artifact.kind] || artifact.kind}
          </span>
          <h3>{artifact.original_filename}</h3>
        </div>
        <div className="artifact-actions">
          {previewable && (
            <button
              className="secondary"
              onClick={togglePreview}
              disabled={busy}
            >
              {busy
                ? "Loading …"
                : preview !== null
                  ? "Close preview"
                  : "Text preview"}
            </button>
          )}
          <a className="download" href={artifactUrl(artifact.id)}>
            {original ? "Download original" : "Download file"} ↓
          </a>
        </div>
      </div>
      <dl>
        <div>
          <dt>File type / size</dt>
          <dd>
            {artifact.mime_type} · {(artifact.size_bytes / 1024).toFixed(1)} KB
          </dd>
        </div>
        {original && (
          <div>
            <dt>Processing</dt>
            <dd>
              {revision.processing_status === "not_processed"
                ? "Not processed yet"
                : statusLabel[revision.processing_status]}
              {artifact.parameters.requires_manual_review === true &&
                " · Flagged for manual review"}
            </dd>
          </div>
        )}
        <div>
          <dt>Artifact ID</dt>
          <dd>{artifact.id}</dd>
        </div>
        {artifact.source_artifact_id && (
          <div>
            <dt>Source / method</dt>
            <dd>
              {artifact.source_artifact_id}
              <br />
              {artifact.processor} {artifact.processor_version}
            </dd>
          </div>
        )}
        <div>
          <dt>SHA-256</dt>
          <dd className="hash">{artifact.sha256}</dd>
        </div>
      </dl>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {preview !== null && <pre className="text-preview">{preview}</pre>}
    </article>
  );
}
