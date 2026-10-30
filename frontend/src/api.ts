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
  processing_status: "not_processed" | Job["status"];
  jobs: Job[];
  text_index: TextSummary | null;
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

export interface Job {
  id: string;
  revision_id: string;
  source_artifact_id: string;
  retry_of_job_id: string | null;
  status: "queued" | "running" | "completed" | "failed";
  attempts: number;
  parameters: Record<string, unknown>;
  processor_versions: Record<string, string>;
  normalization_version: string;
  error_message: string | null;
  result_artifact_ids: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface TextSummary {
  revision_id: string;
  source_artifact_id: string;
  processing_job_id: string;
  normalization_version: string;
  status: "complete" | "partial" | "unavailable";
  quality_status: "no_known_issue" | "needs_review" | "unassessed";
  quality_warnings: string[];
  pages_total: number;
  pages_processed: number;
  pages_failed: number;
  updated_at: string;
}

export interface PageText {
  page_number: number;
  text: string;
  normalized_text: string;
  extraction_method: string;
  status: string;
  quality_status: string;
  quality_warnings: string[];
  confidence: number | null;
}

export interface TextContent extends TextSummary {
  plain_text: string;
  normalized_text: string;
  pages: PageText[];
}

export const startProcessing = (
  revisionId: string,
  sourceId: string,
  manualReview: boolean,
) =>
  request<Job>(`/api/revisions/${revisionId}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_artifact_id: sourceId,
      requires_manual_review: manualReview,
    }),
  });
export const retryJob = (id: string) =>
  request<Job>(`/api/jobs/${id}/retry`, { method: "POST" });
export const getText = (revisionId: string) =>
  request<TextContent>(`/api/revisions/${revisionId}/text`);
export async function getArtifactText(id: string): Promise<string> {
  const response = await fetch(artifactUrl(id));
  if (!response.ok)
    throw new Error(`Datei nicht verfügbar (${response.status}).`);
  return response.text();
}

export interface SearchRequest {
  query: string;
  mode: "exact" | "normalized";
  relation: "contains" | "lacks";
  scope: "latest";
  limit?: number;
  offset?: number;
  unverifiable_limit?: number;
  unverifiable_offset?: number;
}
export interface SearchResult {
  document_id: string;
  title: string;
  revision_id: string | null;
  revision_number: number | null;
  artifact_id: string | null;
  processing_job_id: string | null;
  normalization_version: string | null;
  processor_versions: Record<string, unknown> | null;
  mode: "exact" | "normalized";
  status: "found" | "not_found_in_processed_text" | "unverifiable";
  coverage: "complete" | "partial" | "unavailable" | null;
  quality_status: "no_known_issue" | "needs_review" | "unassessed" | null;
  pages_total: number | null;
  pages_processed: number | null;
  pages_failed: number | null;
  warnings: string[];
  latest_job: {
    id: string;
    status: string;
    error_message: string | null;
  } | null;
  matched_text: string | null;
  snippet: string | null;
  snippet_start_offset: number | null;
  page_number: number | null;
  end_page_number: number | null;
  page_numbers: number[];
  start_offset: number | null;
  end_offset: number | null;
  offset_basis: "plain_text" | "normalized_text";
}
export interface SearchResponse {
  query: string;
  effective_query: string;
  mode: "exact" | "normalized";
  relation: "contains" | "lacks";
  scope: "latest";
  searched_at: string;
  summary: {
    documents_total: number;
    found: number;
    not_found_in_processed_text: number;
    unverifiable: number;
  };
  results: SearchResult[];
  total: number;
  limit: number;
  offset: number;
  unverifiable: SearchResult[];
  unverifiable_total: number;
  unverifiable_limit: number;
  unverifiable_offset: number;
}
export interface SearchPageLocation {
  revisionId: string;
  processingJobId: string;
  pageNumber: number;
  requestId: number;
}
export const searchDocuments = (payload: SearchRequest) =>
  request<SearchResponse>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
