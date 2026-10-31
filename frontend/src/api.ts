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

export interface SearchAbortDetails {
  code: "textual_search_aborted";
  reason: string;
  message: string;
  resource: string;
  limit: number;
  observed_at_least: number;
  documents_inspected: number;
  results_complete: false;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public details: SearchAbortDetails | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchFromServer(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new Error(
      "Unable to reach the server. Please check your connection and try again.",
    );
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetchFromServer(url, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    let message = `Request failed (${response.status}).`;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = body.detail;
      if (
        detail &&
        typeof detail === "object" &&
        "code" in detail &&
        detail.code === "textual_search_aborted" &&
        "message" in detail &&
        typeof detail.message === "string"
      ) {
        throw new ApiError(detail.message, detail as SearchAbortDetails);
      }
      message =
        typeof body.detail === "string"
          ? body.detail
          : "Please check your input and file format.";
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
  const response = await fetchFromServer(artifactUrl(id));
  if (!response.ok) throw new Error(`File unavailable (${response.status}).`);
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

export interface SearchTarget {
  document_id: string;
  revision_id: string | null;
  processing_job_id: string | null;
  page_number: number | null;
}
export type ReviewDecision = "unreviewed" | "keep" | "dismiss" | "later";
export type ReviewFilter = "all" | ReviewDecision;
export type ReviewCounts = Record<ReviewDecision, number>;
export interface PassageReview {
  decision: ReviewDecision;
  version: number;
  updated_at: string | null;
}
export interface ReviewWrite {
  search_run_id?: string;
  occurrence_id: string;
  document_id: string;
  revision_id: string;
  processing_job_id: string;
  source_artifact_id: string;
  normalization_version: string;
  query: string;
  mode: "exact" | "normalized";
  scorer_version: string;
  candidate_policy: string;
  start_offset: number;
  end_offset: number;
  matched_sha256: string;
  decision: ReviewDecision;
  expected_version: number;
}
export const saveReview = (payload: ReviewWrite) =>
  request<PassageReview>("/api/reviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export interface TextualSearchRequest {
  review_filter?: ReviewFilter;
  minimum_semantic_score?: number | null;
  query: string;
  mode: "exact" | "normalized";
  minimum_score: number;
  scope?: "latest";
  document_id?: string;
  limit?: number;
  offset?: number;
  occurrence_limit?: number;
  occurrence_offset?: number;
  unsearchable_limit?: number;
  unsearchable_offset?: number;
}
export type TextualDocument = Pick<
  SearchResult,
  | "document_id"
  | "title"
  | "revision_id"
  | "revision_number"
  | "artifact_id"
  | "processing_job_id"
  | "normalization_version"
  | "processor_versions"
  | "coverage"
  | "quality_status"
  | "pages_total"
  | "pages_processed"
  | "pages_failed"
  | "warnings"
  | "latest_job"
>;
export interface TextualOccurrence {
  review_at_capture?: PassageReview | null;
  matched_sha256: string;
  review: PassageReview;
  occurrence_id: string;
  score: number;
  semantic_score: number | null;
  semantic_cosine: number | null;
  start_offset: number;
  end_offset: number;
  matched_text: string;
  snippet: string;
  snippet_start_offset: number;
  page_numbers: number[];
  page_reference: "physical" | "logical" | "unavailable";
  differences: {
    kind: "equal" | "replace" | "insert" | "delete";
    query_text: string;
    passage_text: string;
  }[];
}
export interface TextualGroup {
  review_counts: ReviewCounts;
  document: TextualDocument;
  occurrences: TextualOccurrence[];
  occurrence_total: number;
  occurrence_offset: number;
  occurrence_limit: number;
}
export interface TextualSearchResponse {
  captured_review_filter: ReviewFilter | null;
  run_id: string | null;
  run_name: string | null;
  parent_run_id: string | null;
  scope_total: number | null;
  review_filter: ReviewFilter;
  review_counts: ReviewCounts;
  minimum_semantic_score: number | null;
  textual_candidates_total: number;
  semantic: {
    model: string;
    pipeline: string;
    score_version: string;
    max_tokens: number;
  } | null;
  query: string;
  effective_query: string;
  mode: "exact" | "normalized";
  minimum_score: number;
  document_id: string | null;
  searched_at: string;
  scorer_version: string;
  scorer_library_version: string;
  candidate_policy: string;
  offset_basis: "plain_text" | "normalized_text";
  warnings: string[];
  assessment: TextualAssessment;
  result_warnings: QueryNotice[];
  summary: {
    documents_total: number;
    documents_searched: number;
    documents_with_matches: number;
    documents_without_matches: number;
    documents_unsearchable: number;
    occurrences_total: number;
  };
  results: TextualGroup[];
  total: number;
  limit: number;
  offset: number;
  unsearchable: TextualDocument[];
  unsearchable_total: number;
  unsearchable_limit: number;
  unsearchable_offset: number;
}
export const searchTextual = (payload: TextualSearchRequest) =>
  request<TextualSearchResponse>("/api/search/textual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export interface QueryNotice {
  code: string;
  message: string;
}
export interface TextualAssessment {
  policy_version: string;
  effective_query: string;
  comparison_characters: number;
  content_characters: number;
  word_count: number;
  equal_length_edit_budget: number;
  warnings: QueryNotice[];
}
export const assessTextual = (
  payload: Pick<TextualSearchRequest, "query" | "mode" | "minimum_score">,
  signal?: AbortSignal,
) =>
  request<TextualAssessment>("/api/search/textual/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

export interface SavedRunSummary {
  id: string;
  name: string;
  query: string;
  searched_at: string;
  created_at: string;
  parent_run_id: string | null;
  result_documents: number;
  result_passages: number;
}
export const createSearchRun = (
  search: TextualSearchRequest,
  name?: string,
  parent_run_id?: string,
) =>
  request<TextualSearchResponse>("/api/search-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ search, name, parent_run_id }),
  });
export function getSearchRun(
  id: string,
  view: Partial<TextualSearchRequest> = {},
) {
  const query = new URLSearchParams();
  for (const key of [
    "document_id",
    "review_filter",
    "limit",
    "offset",
    "occurrence_limit",
    "occurrence_offset",
    "unsearchable_limit",
    "unsearchable_offset",
  ] as const) {
    const value = view[key];
    if (value != null) query.set(key, String(value));
  }
  return request<TextualSearchResponse>(`/api/search-runs/${id}?${query}`);
}
export const listSearchRuns = (offset = 0) =>
  request<{
    items: SavedRunSummary[];
    total: number;
    limit: number;
    offset: number;
  }>(`/api/search-runs?offset=${offset}`);
export const renameSearchRun = (id: string, name: string) =>
  request<SavedRunSummary>(`/api/search-runs/${id}/name`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
export const getSavedSource = (id: string, job: string) =>
  request<TextContent>(`/api/search-runs/${id}/sources/${job}`);
export const getSavedScope = (id: string, offset = 0) =>
  request<{
    items: (TextualDocument & { searchable: boolean })[];
    total: number;
    limit: number;
    offset: number;
  }>(`/api/search-runs/${id}/scope?offset=${offset}`);
