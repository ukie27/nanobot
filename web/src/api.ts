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

export interface SyncRun {
  id: string; trigger_type: string; status: string; discovered_count: number;
  created_count: number; updated_count: number; duplicate_count: number;
  quarantined_count: number; error_code: string | null; started_at: string; finished_at: string | null;
}

export interface QuarantinedEvent {
  id: string; external_id: string; source_url: string; status: string;
  error_code: string | null; created_at: string;
}

export interface BossConnector {
  id: string; connector_type: string; display_name: string; enabled: boolean;
  profile_alias: string; search_query: string; city: string; result_limit: number;
  schedule_enabled: boolean; schedule_times: string[]; timezone: string;
  next_scan_at: string | null; health_status: string; last_error_code: string | null;
  last_success_at: string | null; version: number; runs: SyncRun[]; quarantine: QuarantinedEvent[];
}

export interface BossConnectorUpdate {
  enabled: boolean; profile_alias: string; search_query: string; city: string;
  result_limit: number; schedule_enabled: boolean; schedule_times: string[]; timezone: string;
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

export type MaterialType = "resume" | "cover_letter" | "introduction";
export interface MaterialSummary {
  id: string; resume_id: string; name: string; material_type: MaterialType; status: "draft" | "reviewed" | "final";
  version: number; job_post_id: string; job_post_version_id: string; job_title: string; company: string;
  current_version_number: number; created_at: string; updated_at: string;
}
export interface MaterialFactSnapshot { id: string; fact_id: string; fact_version: number; category: string; field_key: string; value: string }
export interface MaterialBlock { id: string; section: string; text: string; fact_snapshots: MaterialFactSnapshot[] }
export interface MaterialVersion {
  id: string; parent_version_id: string | null; version_number: number; status: string; title: string;
  content_hash: string; fact_set_hash: string; created_at: string; finalized_at: string | null;
}
export interface MaterialReview {
  id: string; status: string; schema_version: string; error_count: number; warning_count: number; created_at: string;
  findings: Array<{ id: string; severity: string; code: string; message: string; block_id: string | null }>;
}
export interface MaterialExport {
  id: string; format: string; sha256: string; size_bytes: number; page_count: number; text_layer_ok: boolean;
  render_ok: boolean; extracted_text_hash: string; created_at: string; download_url: string; preview_url: string;
}
export interface Material extends MaterialSummary {
  current_version: MaterialVersion & { rendered_text: string; blocks: MaterialBlock[] };
  versions: MaterialVersion[]; review: MaterialReview | null; export: MaterialExport | null;
}
export interface MaterialList { items: MaterialSummary[]; total: number }
export interface ResumeSeries { id: string; name: string; material_count: number; created_at: string; updated_at: string }
export interface ResumeSeriesList { items: ResumeSeries[]; total: number }

export type ApplicationStatus = "discovered" | "preparing_materials" | "ready_to_apply" | "submitted" | "application_confirmed" | "assessment" | "written_test" | "interview" | "offer" | "rejected" | "withdrawn" | "archived";
export interface ApplicationSummary {
  id: string; job_post_id: string; job_post_version_id: string; job_title: string; company: string;
  job_content_hash: string; current_status: ApplicationStatus; version: number; material_count: number;
  created_at: string; updated_at: string; archived_at: string | null;
}
export interface ApplicationEvent {
  id: string; sequence_number: number; event_type: string; from_status: string | null; to_status: string;
  occurred_at: string; note: string; source: string; proposal_id: string | null;
  supersedes_event_id: string | null; superseded: boolean; created_at: string;
}
export interface ApplicationMaterialSnapshot {
  id: string; material_draft_id: string; resume_version_id: string; material_type: string; title: string;
  rendered_text: string; content_hash: string; fact_set_hash: string; export_id: string | null;
  export_sha256: string | null; created_at: string;
}
export interface ApplicationProposal {
  id: string; application_id: string; proposed_status: ApplicationStatus; occurred_at: string; note: string;
  source: string; source_ref: string | null; status: string; version: number; resolution_reason: string | null;
  created_at: string; resolved_at: string | null;
}
export interface Application extends ApplicationSummary {
  events: ApplicationEvent[]; material_snapshots: ApplicationMaterialSnapshot[]; proposals: ApplicationProposal[];
  available_final_materials: Array<{ id: string; name: string; material_type: string }>;
}
export interface ApplicationList { items: ApplicationSummary[]; total: number }
export interface ApplicationReviewTask extends ApplicationProposal {
  task_id: string; task_status: string; task_version: number; resolution: string | null; resolved_by: string | null;
  application_version: number; job_title: string; company: string;
}
export interface ApplicationReviewTaskList { items: ApplicationReviewTask[]; total: number }

export interface Reminder {
  id: string; task_id: string; offset_minutes: number; generation: number; scheduled_for: string;
  status: string; version: number; created_at: string; updated_at: string; triggered_at: string | null;
}
export interface CareerTask {
  id: string; application_id: string | null; job_post_id: string | null; source_event_id: string | null;
  task_type: string; title: string; notes: string; status: "pending" | "completed" | "cancelled";
  priority: number; due_at: string; timezone: string; version: number; company: string | null;
  job_title: string | null; reminders: Reminder[]; conflict_ids: string[]; created_at: string;
  updated_at: string; completed_at: string | null; cancelled_at: string | null;
}
export interface CareerTaskList { items: CareerTask[]; total: number }
export interface Dashboard {
  generated_at: string; timezone: string; today: CareerTask[]; overdue: CareerTask[]; upcoming: CareerTask[];
  interviews: CareerTask[]; pending_review_count: number; unread_notification_count: number; conflict_count: number;
}
export interface CareerNotification {
  id: string; reminder_id: string; notification_type: string; title: string; body: string;
  status: "unread" | "read"; created_at: string; read_at: string | null;
}
export interface CareerNotificationList { items: CareerNotification[]; total: number }

export interface ImapAccountUpdate {
  enabled: boolean; email_address: string; host: string; port: number; username: string;
  password?: string; folder: string; initial_lookback_days: number; poll_interval_minutes: number;
}
export interface MailCandidate {
  id: string; application_id: string | null; match_confidence: number | null; match_reason: string;
  status: string; proposal_id: string | null; created_at: string; updated_at: string;
}
export interface MailMessage {
  id: string; uid: number; sender: string; subject: string; sent_at: string | null;
  classification: string; event_kind: string | null; extracted: Record<string, unknown>;
  evidence_excerpt: string | null; body_hash: string | null; body_fetched: boolean;
  attachments: Array<{ filename: string | null; content_type: string; size_bytes: number }>;
  candidate: MailCandidate | null; created_at: string;
}
export interface MailConnector {
  configured: boolean; enabled: boolean; health_status: string; last_error_code: string | null;
  last_success_at: string | null; next_sync_at: string | null;
  account: null | { id: string; email_address: string; host: string; port: number; username: string;
    username_masked: string; folder: string; initial_lookback_days: number; poll_interval_minutes: number;
    credential_configured: boolean; };
  cursor: { uid_validity: string | null; last_committed_uid: number };
  runs: Array<{ id: string; trigger_type: string; status: string; discovered_count: number;
    created_count: number; duplicate_count: number; error_code: string | null; started_at: string; finished_at: string | null }>;
}
export interface MailMessageList { items: MailMessage[]; total: number }

export type InterviewRound = "phone" | "technical" | "case" | "final";
export interface InterviewPreparation {
  id: string; version_number: number; job_post_version_id: string;
  material_snapshot_ids: string[]; confirmed_fact_ids: string[]; prior_improvement_ids: string[];
  content: {
    company: string; job_title: string; round_type: InterviewRound;
    requirements: Array<{ id: string; description: string; level: string }>;
    submitted_materials: Array<{ id: string; title: string; content_hash: string; evidence_excerpt: string }>;
    confirmed_facts: Array<{ id: string; category: string; field_key: string; value: string }>;
    star_prompts: Array<{ fact_id: string; prompt: string }>;
    gap_bridges: Array<{ requirement_id: string; requirement: string; bridge: string }>;
    questions: string[]; candidate_questions: string[];
    historical_improvements: Array<{ id: string; category: string; title: string; description: string }>;
    checklist: string[];
  };
  created_at: string;
}
export interface InterviewFeedback {
  id: string; record_id: string; category: string; description: string; evidence_text: string;
  status: "pending" | "confirmed" | "rejected"; version: number; task_id: string | null;
  created_at: string; resolved_at: string | null;
}
export interface InterviewRecord {
  id: string; occurred_at: string; overall_summary: string; self_rating: number; result: string; version: number;
  questions: Array<{ id: string; question_text: string; answer_summary: string; category: string; self_rating: number | null; ordinal: number }>;
  feedback: InterviewFeedback[];
}
export interface Interview {
  id: string; application_id: string; application_event_id: string | null; task_id: string | null;
  job_title: string; company: string; round_type: InterviewRound;
  scheduled_at: string; timezone: string; status: "scheduled" | "completed" | "cancelled"; version: number;
  preparation: InterviewPreparation | null; record: InterviewRecord | null; created_at: string; updated_at: string;
}
export interface InterviewList { items: Interview[]; total: number }
export interface ImprovementItem {
  id: string; feedback_id: string; category: string; title: string; description: string;
  status: "active" | "completed" | "dismissed"; occurrence_count: number; created_at: string; updated_at: string;
}
export interface WorkspaceOverview {
  generated_at: string; funnel: Record<string, number>; total_applications: number;
  pending_review_count: number; active_improvement_count: number; upcoming_interview_count: number;
  recent_changes: Array<{ id: string; application_id: string; event_type: string; to_status: string; occurred_at: string; note: string }>;
  daily_brief: { period_days: number; application_count: number; change_count: number; summary: string };
  weekly_brief: { period_days: number; application_count: number; change_count: number; summary: string };
}
export interface WorkspaceSearchItem { type: string; id: string; title: string; subtitle: string; url: string }
export interface WorkspaceReviewItem { id: string; review_type: string; entity_id: string; created_at: string; target_url: string }
export interface IntegrationHealth {
  status: "ok" | "attention"; issue_count: number; checked_counts: Record<string, number>;
  issues: Array<{ code: string; count: number; severity: "warning" | "error"; message: string }>;
}

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

let csrfTokenPromise: Promise<string> | null = null;
function csrfToken(): Promise<string> {
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetch("/api/v1/system/session", { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error("无法建立本地安全会话。");
        return ((await response.json()) as { csrf_token: string }).csrf_token;
      })
      .catch((error) => { csrfTokenPromise = null; throw error; });
  }
  return csrfTokenPromise;
}

async function sendJson<T>(path: string, body: unknown): Promise<T> {
  const csrf = await csrfToken();
  const response = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": csrf },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  return parseResponse<T>(response);
}

async function putJson<T>(path: string, body: unknown): Promise<T> {
  const csrf = await csrfToken();
  const response = await fetch(path, {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": csrf },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  return parseResponse<T>(response);
}

async function deleteJson<T>(path: string): Promise<T> {
  const csrf = await csrfToken();
  return parseResponse<T>(await fetch(path, { method: "DELETE", credentials: "same-origin", headers: { Accept: "application/json", "X-CSRF-Token": csrf } }));
}

async function sendForm<T>(path: string, body: FormData): Promise<T> {
  const csrf = await csrfToken();
  return parseResponse<T>(await fetch(path, {
    method: "POST", body, credentials: "same-origin",
    headers: { Accept: "application/json", "X-CSRF-Token": csrf },
  }));
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
export const retryBackgroundJob = (id: string) => sendJson<BackgroundJob>(`/api/v1/jobs/${id}/retry`, {});
export const cancelBackgroundJob = (id: string) => sendJson<BackgroundJob>(`/api/v1/jobs/${id}/cancel`, {});
export const getBossConnector = () => getJson<BossConnector>("/api/v1/connectors/boss");
export const configureBossConnector = (body: BossConnectorUpdate) => putJson<BossConnector>("/api/v1/connectors/boss", body);
export const checkBossConnector = () => sendJson<{ status: string; opencli_version?: string; error_code?: string }>("/api/v1/connectors/boss/health", {});
export const loginBossConnector = () => sendJson<Record<string, unknown>>("/api/v1/connectors/boss/login", { timeout: 300 });
export const scanBossConnector = () => sendJson<SyncRun>("/api/v1/connectors/boss/scan", {});
export const getMailConnector = () => getJson<MailConnector>("/api/v1/mail/account");
export const configureMailConnector = (body: ImapAccountUpdate) => putJson<MailConnector>("/api/v1/mail/account", body);
export const testMailConnector = () => sendJson<{ status: string; uid_validity: string; read_only: boolean }>("/api/v1/mail/account/test", {});
export const syncMailConnector = () => sendJson<MailConnector["runs"][number]>("/api/v1/mail/sync", {});
export const deleteMailConnector = () => deleteJson<{ deleted: boolean }>("/api/v1/mail/account");
export const getMailMessages = () => getJson<MailMessageList>("/api/v1/mail/messages");
export const proposeMailMessage = (body: { message_id: string; application_id: string }) =>
  sendJson<{ message: MailMessage; candidate: MailCandidate }>(
    `/api/v1/mail/messages/${body.message_id}/proposal`,
    { application_id: body.application_id },
  );
export const getInterviews = () => getJson<InterviewList>("/api/v1/interviews");
export const getInterview = (id: string) => getJson<Interview>(`/api/v1/interviews/${id}`);
export const createInterview = (body: { application_id: string; round_type: InterviewRound; scheduled_at: string; timezone: string }) =>
  sendJson<Interview>("/api/v1/interviews", body);
export const rescheduleInterview = (item: Interview, scheduled_at: string) =>
  sendJson<Interview>(`/api/v1/interviews/${item.id}/reschedule`, {
    expected_version: item.version, scheduled_at, timezone: "Asia/Shanghai",
  });
export const cancelInterview = (item: Interview, reason: string) =>
  sendJson<Interview>(`/api/v1/interviews/${item.id}/cancel`, {
    expected_version: item.version, reason,
  });
export const generateInterviewPreparation = (id: string) =>
  sendJson<InterviewPreparation>(`/api/v1/interviews/${id}/preparation`, {});
export const saveInterviewRecord = (id: string, body: {
  occurred_at: string; overall_summary: string; self_rating: number; result: string;
  questions: Array<{ question_text: string; answer_summary: string; self_rating: number | null }>;
}) => sendJson<InterviewRecord>(`/api/v1/interviews/${id}/record`, body);
export const getInterviewFeedback = () =>
  getJson<{ items: InterviewFeedback[]; total: number }>("/api/v1/interview-feedback");
export const resolveInterviewFeedback = (item: InterviewFeedback, resolution: "confirmed" | "rejected") =>
  sendJson<InterviewFeedback>(`/api/v1/interview-feedback/${item.id}/resolve`, {
    expected_version: item.version, resolution, reason: resolution === "confirmed" ? "用户确认需要改进" : "用户判定建议不准确",
  });
export const getImprovementItems = () =>
  getJson<{ items: ImprovementItem[]; total: number }>("/api/v1/improvement-items");
export const updateImprovementItem = (id: string, status: ImprovementItem["status"]) =>
  putJson<ImprovementItem>(`/api/v1/improvement-items/${id}`, { status });
export const getWorkspaceOverview = () => getJson<WorkspaceOverview>("/api/v1/workspace/overview");
export const searchWorkspace = (query: string) =>
  getJson<{ items: WorkspaceSearchItem[]; total: number }>(`/api/v1/workspace/search?q=${encodeURIComponent(query)}`);
export const getWorkspaceReviews = () =>
  getJson<{ items: WorkspaceReviewItem[]; total: number }>("/api/v1/workspace/reviews");
export const getIntegrationHealth = () => getJson<IntegrationHealth>("/api/v1/workspace/integration-health");
export const createWorkspaceBackup = () => sendJson<{ path: string; size_bytes: number }>("/api/v1/workspace/backup", {});
export const exportWorkspaceData = () => sendJson<{ path: string; size_bytes: number; table_count: number; secrets_included: boolean }>("/api/v1/workspace/export", {});
export const garbageCollectWorkspace = () => sendJson<{ removed_files: number; removed_bytes: number }>("/api/v1/workspace/garbage-collect", {});
export const deleteAllCareerData = (confirmation: string) =>
  sendJson<{ deleted: boolean; backup_path: string }>("/api/v1/workspace/delete-all", { confirmation });
export const deleteConnectorData = (connectorType: string, confirmation: string) =>
  sendJson<{ deleted_connectors: number; connector_type: string }>(
    `/api/v1/workspace/connectors/${encodeURIComponent(connectorType)}/delete`, { confirmation },
  );
export const getProfile = () => getJson<CandidateProfile>("/api/v1/profile");
export const getFacts = (status?: FactStatus) =>
  getJson<FactList>(`/api/v1/facts${status ? `?status=${status}` : ""}`);
export const getDocuments = () => getJson<DocumentList>("/api/v1/documents");
export const importText = (name: string, text: string) =>
  sendJson<ImportedDocument>("/api/v1/documents/import-text", { name, text });
export async function importFile(file: File): Promise<ImportedDocument> {
  const form = new FormData();
  form.append("file", file);
  return sendForm<ImportedDocument>("/api/v1/documents/import", form);
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
  return sendForm<JobPost>("/api/v1/job-posts/import-file", form);
}
export const analyzeJob = (id: string) => sendJson<JobAnalysis>(`/api/v1/job-posts/${id}/analyses`, {});
export const getMaterials = () => getJson<MaterialList>("/api/v1/materials");
export const getResumeSeries = () => getJson<ResumeSeriesList>("/api/v1/resumes");
export const getMaterial = (id: string) => getJson<Material>(`/api/v1/materials/${id}`);
export const generateMaterial = (body: { job_post_id: string; material_type: MaterialType; name: string; resume_id?: string }) =>
  sendJson<Material>("/api/v1/materials", body);
export const editMaterial = (material: Material, blocks: Array<{ id: string; text: string }>) =>
  sendJson<Material>(`/api/v1/materials/${material.id}/versions`, { expected_version: material.version, blocks });
export const reviewMaterial = (id: string) => sendJson<Material>(`/api/v1/materials/${id}/reviews`, {});
export const finalizeMaterial = (material: Material) =>
  sendJson<Material>(`/api/v1/materials/${material.id}/finalize`, { expected_version: material.version });
export const getApplications = () => getJson<ApplicationList>("/api/v1/applications");
export const getApplication = (id: string) => getJson<Application>(`/api/v1/applications/${id}`);
export const createApplication = (job_post_id: string) => sendJson<Application>("/api/v1/applications", { job_post_id });
export const submitApplication = (application: Application, material_ids: string[], occurred_at: string, note: string) =>
  sendJson<Application>(`/api/v1/applications/${application.id}/submit`, { expected_version: application.version, material_ids, occurred_at, note });
export const addApplicationEvent = (application: Application, target_status: ApplicationStatus, occurred_at: string, note: string) =>
  sendJson<Application>(`/api/v1/applications/${application.id}/events`, { expected_version: application.version, target_status, occurred_at, note });
export const correctApplicationEvent = (application: Application, eventId: string, occurred_at: string, note: string) =>
  sendJson<Application>(`/api/v1/applications/${application.id}/events/${eventId}/corrections`, { expected_version: application.version, occurred_at, note });
export const archiveApplication = (application: Application) =>
  sendJson<Application>(`/api/v1/applications/${application.id}/archive`, { expected_version: application.version, note: "用户归档" });
export const proposeApplicationEvent = (application: Application, proposed_status: ApplicationStatus, occurred_at: string, note: string) =>
  sendJson<ApplicationReviewTask>(`/api/v1/applications/${application.id}/event-proposals`, { proposed_status, occurred_at, note, source: "manual_proposal" });
export const getApplicationReviewTasks = () => getJson<ApplicationReviewTaskList>("/api/v1/application-review-tasks");
export const resolveApplicationProposal = (task: ApplicationReviewTask, resolution: "confirmed" | "rejected", reason: string) =>
  sendJson<ApplicationReviewTask>(`/api/v1/application-event-proposals/${task.id}/resolve`, { expected_version: task.version, application_expected_version: task.application_version, resolution, reason });
export const getDashboard = () => getJson<Dashboard>("/api/v1/dashboard");
export const getTasks = () => getJson<CareerTaskList>("/api/v1/tasks");
export const createTask = (body: { title: string; task_type: string; due_at: string; timezone: string; notes: string; application_id?: string }) =>
  sendJson<CareerTask>("/api/v1/tasks", body);
export const completeTask = (task: CareerTask) => sendJson<CareerTask>(`/api/v1/tasks/${task.id}/complete`, { expected_version: task.version });
export const cancelTask = (task: CareerTask) => sendJson<CareerTask>(`/api/v1/tasks/${task.id}/cancel`, { expected_version: task.version });
export const postponeTask = (task: CareerTask, due_at: string) => sendJson<CareerTask>(`/api/v1/tasks/${task.id}/postpone`, { expected_version: task.version, due_at, timezone: task.timezone });
export const addTaskReminder = (taskId: string, offset_minutes: number) => sendJson<Reminder>(`/api/v1/tasks/${taskId}/reminders`, { offset_minutes });
export const runDueSchedules = () => sendJson<{ schedules_processed: number; reminders_triggered: number; outbox_dispatched: number; leases_recovered: number; connector_runs_processed: number; connector_error_code: string | null }>("/api/v1/scheduler/run-due", {});
export const getNotifications = () => getJson<CareerNotificationList>("/api/v1/notifications");
export const readNotification = (id: string) => sendJson<CareerNotification>(`/api/v1/notifications/${id}/read`, {});
