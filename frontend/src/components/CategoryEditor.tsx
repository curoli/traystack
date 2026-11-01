import { useEffect, useState } from "react";
import { setDocumentCategory, type Document } from "../api";

export default function CategoryEditor({
  document,
  onSaved,
}: {
  document: Document;
  onSaved: () => Promise<void>;
}) {
  const [category, setCategory] = useState(
    String(document.metadata.category ?? ""),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setCategory(String(document.metadata.category ?? ""));
  }, [document.id, document.metadata.category]);
  async function save() {
    setBusy(true);
    setError("");
    try {
      await setDocumentCategory(document.id, category.trim() || null);
      await onSaved();
      window.dispatchEvent(new Event("categories-changed"));
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not save category.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <label htmlFor="document-category">Category</label>
      <input
        id="document-category"
        value={category}
        maxLength={100}
        onChange={(e) => setCategory(e.target.value)}
        disabled={busy}
      />
      <button className="secondary" disabled={busy} onClick={() => void save()}>
        Save category
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
