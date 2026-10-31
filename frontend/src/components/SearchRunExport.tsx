import { useEffect, useRef, useState } from "react";
import { exportSearchRun, type ReviewFilter } from "../api";

export default function SearchRunExport({ runId }: { runId: string }) {
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function download(format: "csv" | "json") {
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const { blob, filename } = await exportSearchRun(
        runId,
        format,
        filter,
        request.signal,
      );
      if (request.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Give the browser time to begin reading before releasing the object URL.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(`${format.toUpperCase()} download prepared.`);
    } catch (error) {
      if (!request.signal.aborted)
        setError(error instanceof Error ? error.message : "Export failed.");
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }

  return (
    <details className="search-run-export">
      <summary>Export results</summary>
      <p className="fineprint">
        Download all matching passages across every page of this saved run.
        Exports include current review decisions, search and export times, and
        source references. Changing this filter does not change the on-screen
        results. Unsearchable documents are included separately in every export.
      </p>
      <label htmlFor="export-review-filter">Export review status</label>
      <select
        id="export-review-filter"
        disabled={busy}
        value={filter}
        onChange={(event) => setFilter(event.target.value as ReviewFilter)}
      >
        <option value="all">All review states</option>
        <option value="keep">Keep</option>
        <option value="dismiss">Dismiss</option>
        <option value="later">Decide later</option>
        <option value="unreviewed">Not reviewed</option>
      </select>
      <div className="saved-run-actions">
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void download("csv")}
        >
          Download CSV
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void download("json")}
        >
          Download JSON
        </button>
      </div>
      <p className="fineprint">
        CSV opens in spreadsheets and includes a summary row, passage rows and
        unsearchable document rows. Formula-like text is prefixed with an
        apostrophe. JSON preserves the original text and includes the complete
        captured scope, text differences and comparison versions. Scores do not
        establish legal equivalence or clause absence.
      </p>
      {busy && <p role="status">Preparing export …</p>}
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
    </details>
  );
}
