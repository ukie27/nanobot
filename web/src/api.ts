export interface SystemPaths {
  data_dir: string;
  database: string;
  logs: string;
  backups: string;
}

export interface SystemStatus {
  version: string;
  health: string;
  database: string;
  database_revision: string | null;
  expected_revision: string;
  recovered_jobs_at_startup: number;
  paths: SystemPaths;
}

export interface BackgroundJob {
  id: string;
  job_type: string;
  status: string;
  priority: number;
  run_after: string;
  attempt_count: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_error_code: string | null;
}

export interface BackgroundJobList {
  items: BackgroundJob[];
  total: number;
}

export type FactStatus = "proposed" | "confirmed" | "rejected";

export interface CandidateProfile {
  id: string;
  display_name: string | null;
  timezone: string;
  version: number;
  fact_counts: Record<FactStatus, number>;
  created_at: string;
  updated_at: string;
}

export interface FactSource {
  id: string;
  document_id: string | null;
  source_type: string;
  evidence_text: string;
  created_at: string;
}

export interface FactRevision {
  id: string;
  revision_number: number;
  previous_value: string;
  new_value: string;
  previous_status: FactStatus;
  new_status: FactStatus;
  reason: string;
  changed_by: string;
  created_at: string;
}

export interface CandidateFact {
  id: string;
  profile_id: string;
  category: string;
  field_key: string;
  value: string;
  status: FactStatus;
  confidence: number | null;
  version: number;
  sources: FactSource[];
  revisions: FactRevision[];
  created_at: string;
  updated_at: string;
}

export interface FactList { items: CandidateFact[]; total: number }

export interface ImportedDocument {
  id: string;
  file_name: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  parse_status: string;
  parser_name: string;
  text_preview: string;
  fact_source_count: number;
  duplicate: boolean;
  proposed_fact_count: number | null;
  extracted_candidate_count: number | null;
  created_at: string;
}

export interface DocumentList { items: ImportedDocument[]; total: number }

export interface JobAnalysisSummary {
  id: string; job_post_version_id: string; hard_gate_passed: boolean; score: number;
  matched_count: number; gap_count: number; must_gap_count: number; recommendation: string; created_at: string;
}
export interface JobRequirement {
  id: string; category: string; level: "must" | "preferred"; description: string;
  evidence_text: string; keywords: string[]; weight: number; ordinal: number;
}
export interface JobEvidence {
  requirement: JobRequirement; decision: "matched" | "gap"; rationale: string;
  facts: Array<{ id: string; category: string; field_key: string; value: string; version: number }>;
}
export interface JobAnalysis extends JobAnalysisSummary { evidence: JobEvidence[] }
export interface JobPostSummary {
  id: string; company: string; title: string; location: string | null; employment_type: string | null;
  work_mode: string | null; deadline_at: string | null; status: string; version: number;
  latest_analysis: JobAnalysisSummary | null; created_at: string; updated_at: string;
}
export interface JobPost extends JobPostSummary {
  duplicate: boolean; created: boolean; target_audience: string | null; raw_text: string; content_hash: string;
  requirements: JobRequirement[]; analyses: JobAnalysis[];
  versions: Array<{ id: string; version_number: number; content_hash: string; created_at: string }>;
  sources: Array<{ id: string; source_type: string; source_url: string | null; display_name: string; discovered_at: string; last_seen_at: string }>;
}
export interface JobPostList { items: JobPostSummary[]; total: number }

interface ProblemDetails {
  title?: string;
  detail?: string;
  correlationId?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly correlationId?: string,
  ) {
    super(message);
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as ProblemDetails;
    throw new ApiError(
      problem.detail ?? problem.title ?? `请求失败（HTTP ${response.status}）`,
      response.status,
      problem.correlationId,
    );
  }
  return (await response.json()) as T;
}

async function sendJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseResponse<T>(response);
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as ProblemDetails;
    throw new ApiError(
      problem.detail ?? problem.title ?? `请求失败（HTTP ${response.status}）`,
      response.status,
      problem.correlationId,
    );
  }
  return (await response.json()) as T;
}

export const getSystemStatus = () => getJson<SystemStatus>("/api/v1/system/status");
export const getBackgroundJobs = () => getJson<BackgroundJobList>("/api/v1/jobs");
export const getProfile = () => getJson<CandidateProfile>("/api/v1/profile");
export const getFacts = (status?: FactStatus) =>
  getJson<FactList>(`/api/v1/facts${status ? `?status=${status}` : ""}`);
export const getDocuments = () => getJson<DocumentList>("/api/v1/documents");
export const importText = (name: string, text: string) =>
  sendJson<ImportedDocument>("/api/v1/documents/import-text", { name, text });
export async function importFile(file: File): Promise<ImportedDocument> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/v1/documents/import", { method: "POST", body: form });
  return parseResponse<ImportedDocument>(response);
}
export const addManualFact = (body: {
  category: string; field_key: string; value: string; source_note: string;
}) => sendJson<CandidateFact>("/api/v1/facts", body);
export const confirmFact = (fact: CandidateFact) =>
  sendJson<CandidateFact>(`/api/v1/facts/${fact.id}/confirm`, {
    expected_version: fact.version, reason: "Confirmed in Career UI",
  });
export const rejectFact = (fact: CandidateFact) =>
  sendJson<CandidateFact>(`/api/v1/facts/${fact.id}/reject`, {
    expected_version: fact.version, reason: "Rejected in Career UI",
  });
export const editFact = (fact: CandidateFact, value: string) =>
  sendJson<CandidateFact>(`/api/v1/facts/${fact.id}/edit`, {
    expected_version: fact.version, value, reason: "Edited in Career UI",
  });
export const batchConfirmFacts = (facts: CandidateFact[]) =>
  sendJson<{ items: CandidateFact[]; completed: number }>("/api/v1/facts/batch-confirm", {
    items: facts.map((fact) => ({ id: fact.id, expected_version: fact.version })),
  });
export const getJobPosts = () => getJson<JobPostList>("/api/v1/job-posts");
export const getJobPost = (id: string) => getJson<JobPost>(`/api/v1/job-posts/${id}`);
export const importJobText = (name: string, text: string) => sendJson<JobPost>("/api/v1/job-posts/import-text", { name, text });
export const importJobUrl = (url: string) => sendJson<JobPost>("/api/v1/job-posts/import-url", { url, confirmed: true });
export async function importJobFile(file: File): Promise<JobPost> {
  const form = new FormData(); form.append("file", file);
  return parseResponse<JobPost>(await fetch("/api/v1/job-posts/import-file", { method: "POST", body: form }));
}
export const analyzeJob = (id: string) => sendJson<JobAnalysis>(`/api/v1/job-posts/${id}/analyses`, {});
