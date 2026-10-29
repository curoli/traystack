export interface Artifact {
  id: string;
  revision_id: string;
  source_artifact_id: string | null;
  kind: string;
  mime_type: string;
  original_filename: string | null;
  sha256: string;
  size_bytes: number;
  processor: string | null;
  processor_version: string | null;
  parameters: Record<string, unknown>;
  created_at: string;
}

export interface Revision {
  id: string;
  revision_number: number;
  label: string | null;
  processing_status: "not_processed";
  artifacts: Artifact[];
}

export interface Document {
  id: string;
  title: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  revisions: Revision[];
}

interface DocumentList {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    let message = `Anfrage fehlgeschlagen (${response.status}).`;
    if (body && typeof body === "object" && "detail" in body) {
      message =
        typeof body.detail === "string"
          ? body.detail
          : "Bitte Eingaben und Dateiformat prüfen.";
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const listDocuments = (offset: number) =>
  request<DocumentList>(`/api/documents?limit=20&offset=${offset}`);
export const getDocument = (id: string) =>
  request<Document>(`/api/documents/${id}`);
export const uploadDocument = (form: FormData) =>
  request<Document>("/api/documents/upload", { method: "POST", body: form });
export const artifactUrl = (id: string) => `/api/artifacts/${id}/content`;
