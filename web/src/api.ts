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

export interface WorkspaceStatus {
  product: "CareerConsole"; workspace_path: string; active_workspace_path: string | null;
  pending_workspace_path: string | null; last_switch_error: string | null;
  onboarding_required: boolean; restart_required: boolean;
  manifest: null | { schemaVersion: string; workspaceId: string; name: string;
    product: string; createdAt: string; lastOpenedAt: string; portable: boolean;
    paths: Record<string, string> };
  paths: Record<string, string>;
}

export interface WorkspaceValidation {
  parent_directory: string; workspace_path: string; valid: boolean; error: string | null;
}

export interface WorkspaceDirectorySelection {
  cancelled: boolean; parent_directory: string | null;
}

export interface OnboardingStatus {
  schema_version: string;
  onboarding_version: number;
  required_version: number;
  completed: boolean;
  completed_at: string | null;
  skipped_steps: string[];
  step_states: Record<string, "not_started" | "in_progress" | "configured" | "skipped" | "failed_validation">;
  workspace_ready: boolean;
  restart_required: boolean;
  runtime_mode: "bootstrap" | "product";
  capabilities: Record<"workspace" | "provider" | "profile" | "mail" | "opencli" | "channel" | "scheduler", boolean>;
}

export interface ConfigurationCheckResult {
  capability: string;
  status: "passed" | "failed" | "blocked";
  checked_at: string;
  summary: string;
  details: string[];
  error_code: string | null;
}

export interface PortableWorkspaceExport {
  filename: string; path: string; sha256: string; size_bytes: number;
  file_count: number; secrets_included: boolean; download_url: string;
}

export interface PortableWorkspaceImport {
  workspace_path: string; workspace_id: string; database_revision: string;
  secrets_restored: number; restart_required: boolean;
}

export interface CareerConsoleConfiguration {
  general: {
    locale: "zh-CN" | "en-US"; timezone: string;
    date_format: "yyyy-MM-dd" | "yyyy/MM/dd"; open_browser_on_start: boolean;
  };
  appearance: { density: "comfortable" | "compact"; reduce_motion: boolean };
  runtime: {
    log_level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
    log_retention_days: number; agent_trace_retention_days: number;
    job_lease_seconds: number; max_document_mb: number;
  };
  privacy: {
    diagnostics_metadata_enabled: boolean;
    redact_sensitive_logs: true; local_only_network_binding: true;
  };
  providers: Record<string, ProviderConfiguration>;
  agents: AgentConfiguration;
  connectors: {
    opencli: {
      executable: string | null;
      boss: { enabled: boolean; profile_alias: string; search_query: string; city: string; result_limit: number };
      nowcoder: { enabled: boolean; search_query: string; city: string; result_limit: number;
        schedule_enabled: boolean; schedule_times: string[]; timezone: "Asia/Shanghai" };
    };
    imap: { enabled: boolean; email_address: string; host: string; port: number;
      username: string; folder: "INBOX"; initial_lookback_days: number;
      poll_interval_minutes: number; secret_ref: string | null };
  };
  channels: {
    qq: { enabled: boolean; app_id: string; allow_from: string[];
      notification_targets: string[]; event_subscriptions: string[];
      message_format: "plain" | "markdown"; outbound_only: true;
      quiet_hours: { enabled: boolean; start: string; end: string; timezone: "Asia/Shanghai" };
      secret_ref: string | null };
    send_max_retries: number;
  };
  scheduler: { enabled: boolean; poll_seconds: number; reminders_enabled: boolean;
    connector_jobs_enabled: boolean; nowcoder_sync_enabled: boolean;
    mail_sync_enabled: boolean; profile_maintenance_enabled: boolean;
    profile_maintenance_interval_days: number; profile_maintenance_time: string;
    channel_dispatch_enabled: boolean };
}

export type ProviderType = "custom" | "azure_openai" | "anthropic" | "openai" |
  "openrouter" | "deepseek" | "gemini" | "zhipu" | "dashscope" | "moonshot" |
  "minimax" | "mistral" | "stepfun" | "xiaomi_mimo" | "aihubmix" |
  "siliconflow" | "volcengine" | "volcengine_coding_plan" | "byteplus" |
  "byteplus_coding_plan" | "groq" | "ollama" | "vllm" | "ovms";
export interface ProviderConfiguration {
  provider_type: ProviderType; display_name: string; enabled: boolean;
  api_base: string | null; default_model: string; models: string[];
  secret_ref: string | null;
}
export interface ProviderView extends ProviderConfiguration { id: string; has_secret: boolean }
export interface ProviderCatalogItem {
  type: ProviderType; label: string; default_api_base: string | null;
  requires_api_key: boolean; is_local: boolean;
}
export interface AgentTaskConfiguration {
  enabled: boolean; provider_id: string | null; model: string | null;
  temperature: number; max_tokens: number;
  reasoning_effort: "low" | "medium" | "high" | null;
}
export type AgentTaskName = "fact_extraction" | "profile_revision" | "mail_intelligence" | "profile_insight" |
  "job_fit" | "resume_direction" | "resume_drafting" | "material_review" |
  "daily_job_recommendation";
export interface AgentConfiguration { tasks: Record<AgentTaskName, AgentTaskConfiguration> }
export interface ProviderTestRun {
  id: string; provider_id: string; provider_type: ProviderType; model: string;
  status: "passed" | "failed"; error_code: string | null;
  duration_ms: number; created_at: string;
}
export interface QQChannelView extends Omit<CareerConsoleConfiguration["channels"]["qq"], "secret_ref"> {
  has_secret: boolean; configuration_revision: number;
}
export interface ChannelDeliveryRun {
  id: string; channel_type: "qq"; event_type: string; target_masked: string;
  status: "passed" | "failed"; error_code: string | null;
  duration_ms: number; created_at: string;
}
export interface SchedulerRun {
  id: string; trigger_type: string; status: string; counters: Record<string, number>;
  error_codes: string[]; started_at: string; finished_at: string;
}

export interface ConfigurationStatus {
  schema_version: string; revision: number; updated_at: string;
  active_revision: number; activation_status: "active" | "restart_required";
  configuration: CareerConsoleConfiguration;
  changed_paths?: string[]; activation_effect?: "hot_reload" | "service_reload" | "restart_required" | null;
}

export interface ConfigurationChange {
  id: string; previous_revision: number; new_revision: number; changed_paths: string[];
  activation_effect: string; reason: string; created_at: string;
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
  opportunities_discovered?: number; jd_discovered?: number; jd_imported?: number;
  recommendations_created?: number; recommendations_rejected?: number;
  jd_discovery_failed?: number; recommendation_failed?: number;
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
  session_status: "authenticated" | "requires_login" | "expired" | "unknown" | "checking" | "unavailable";
  session_identity: Record<string, string | boolean | number>;
  session_checked_at: string | null;
  last_success_at: string | null; version: number; runs: SyncRun[]; quarantine: QuarantinedEvent[];
}

export interface BossConnectorUpdate {
  enabled: boolean; profile_alias: string; search_query: string; city: string;
  result_limit: number; schedule_enabled: boolean; schedule_times: string[]; timezone: string;
}

export interface NowcoderConnector {
  id: string; connector_type: string; display_name: string; enabled: boolean;
  search_query: string; city: string; result_limit: number;
  schedule_enabled: boolean; schedule_times: string[]; timezone: string;
  next_scan_at: string | null; health_status: string; last_error_code: string | null;
  session_status: "authenticated" | "requires_login" | "expired" | "unknown" | "checking" | "unavailable";
  session_identity: Record<string, string | boolean | number>;
  session_checked_at: string | null;
  last_success_at: string | null; version: number; runs: SyncRun[];
  quarantine: QuarantinedEvent[]; automatic_scope: "today";
  manual_lookback_options: number[];
}

export interface NowcoderConnectorUpdate {
  enabled: boolean; search_query: string; city: string; result_limit: number;
  schedule_enabled: boolean; schedule_times: string[];
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

export interface ProfileMemory {
  preferences: Array<{ id: string; preference_key: string; value: unknown; status: string; version: number; created_at: string; updated_at: string }>;
  insights: Array<{ id: string; category: "interview" | "application" | "resume" | "learning" | "career_direction"; analysis: string; recommendation: string; evidence_refs: string[]; evidence_fact_ids: string[]; evidence_improvement_ids: string[]; counter_evidence: string[]; confidence: number; source: string; status: string; version: number; agent_run_id: string | null; review_task_id: string | null; resolution_reason: string | null; created_at: string; resolved_at: string | null }>;
  strategies: Array<{ id: string; version_number: number; schema_version: string; period_start: string; period_end: string; content: { target_directions: unknown; priority_locations: unknown; constraints: unknown; application_count: number; confirmed_fact_count: number; actions: string[]; evaluation_period_days: number }; evidence_refs: string[]; status: string; version: number; review_task_id: string | null; resolution_reason: string | null; created_at: string; resolved_at: string | null }>;
  digests: Array<{ id: string; digest_date: string; schema_version: string; content: { changes: unknown[]; application_changes: unknown[]; pending_review_count: number; risks: string[]; tomorrow_actions: Array<{ task_id: string; title: string; due_at: string }> }; input_hash: string; generated_at: string }>;
  changes: Array<{ id: string; event_type: string; entity_type: string; entity_id: string; entity_revision: number; changed_fields: Record<string, unknown>; impact_scopes: string[]; source: string; occurred_at: string }>;
  impact_runs: Array<{ id: string; change_event_id: string; scope: string; status: string; background_job_id: string | null; input_revision: string; affected_count: number; error_code: string | null; created_at: string; started_at: string | null; finished_at: string | null }>;
}

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
  maintained_fact_count: number | null;
  extracted_candidate_count: number | null;
  superseded_fact_count: number | null;
  created_at: string;
}

export interface DocumentList { items: ImportedDocument[]; total: number }

export interface JobAnalysisSummary {
  id: string; job_post_version_id: string; hard_gate_passed: boolean; score: number;
  matched_count: number; gap_count: number; must_gap_count: number; recommendation: string; created_at: string; reused?: boolean;
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
  requirement_count: number; latest_analysis: JobAnalysisSummary | null; created_at: string; updated_at: string;
}
export interface JobPost extends JobPostSummary {
  duplicate: boolean; created: boolean; target_audience: string | null; raw_text: string; content_hash: string;
  requirements: JobRequirement[]; analyses: JobAnalysis[];
  versions: Array<{ id: string; version_number: number; content_hash: string; created_at: string }>;
  sources: Array<{ id: string; source_type: string; source_url: string | null; display_name: string; discovered_at: string; last_seen_at: string }>;
  opportunity_ids: string[];
}
export interface JobPostList { items: JobPostSummary[]; total: number }
export interface JobFitProposal {
  id: string; job_post_id: string; job_post_version_id: string; fact_set_hash: string; preference_set_hash: string;
  schema_version: string; status: "proposed" | "confirmed" | "rejected"; version: number;
  agent_run_id: string; review_task_id: string | null; formal_analysis_id: string | null;
  resolution_reason: string | null; created_at: string; resolved_at: string | null;
  decision_projection: { requirement_score: number; hard_gate_passed: boolean; preference_adjustment: number; cost_adjustment: number; decision_score: number; priority: string; reasons: string[] };
  content: {
    schemaVersion: "job_fit_analysis.v2"; summary: string;
    assessments: Array<{ requirementId: string; interpretation: string; decision: "matched" | "gap"; evidenceFactIds: string[]; transferableFactIds: string[]; rationale: string; confidence: number }>;
    strengths: string[]; risks: string[]; materialEffort: "low" | "medium" | "high";
    preparationHours: number; recommendationContext: string;
  };
}
export interface JobFitProposalList { items: JobFitProposal[]; total: number }
export interface ResumeDirectionItem {
  directionId: string; name: string; narrative: string; focusRequirementIds: string[];
  emphasizeFactIds: string[]; deEmphasizeFactIds: string[]; estimatedChangePercent: number;
  expectedPages: number; gaps: string[]; risks: string[]; rationale: string;
}
export interface ResumeDirectionProposal {
  id: string; job_post_id: string; job_post_version_id: string; job_match_analysis_id: string;
  fact_set_hash: string; preference_set_hash: string; schema_version: string;
  content: { schemaVersion: "resume_direction.v1"; directions: ResumeDirectionItem[]; comparisonNote: string };
  status: "proposed" | "confirmed" | "rejected"; version: number; agent_run_id: string;
  review_task_id: string | null; selection_id: string | null; resolution_reason: string | null;
  created_at: string; resolved_at: string | null;
}
export interface ResumeDirectionSelection {
  id: string; proposal_id: string; job_post_id: string; job_post_version_id: string;
  selected_direction_ids: string[]; selected_directions: ResumeDirectionItem[];
  status: "active" | "superseded"; version: number; created_at: string;
}
export interface ResumeDirectionOverview { proposals: ResumeDirectionProposal[]; selections: ResumeDirectionSelection[] }

export type OpportunityTriageStatus = "new" | "following" | "ignored";
export interface RecruitmentOpportunity {
  id: string; company: string; batch: string; cities: string; careers: string;
  industries: string; evaluation: string; application_starts_at: string | null;
  application_ends_at: string | null; announcement_url: string | null;
  application_url: string; triage_status: OpportunityTriageStatus; version: number;
  first_collected_at: string; last_collected_at: string; created_at: string;
  updated_at: string;
  sources: Array<{ id: string; external_id: string; source_url: string; first_seen_at: string; last_seen_at: string }>;
  linked_jobs: Array<{ id: string; company: string; title: string; location: string | null; version: number; created_at: string }>;
}
export interface RecruitmentOpportunityDetail extends RecruitmentOpportunity {
  versions: Array<{ id: string; version_number: number; content_hash: string; collected_at: string; created_at: string }>;
}
export interface RecruitmentOpportunityList { items: RecruitmentOpportunity[]; total: number }

export interface JobRecommendationAssessment {
  requirementId: string; decision: "matched" | "gap";
  evidenceFactIds: string[]; transferableFactIds: string[]; rationale: string;
}
export interface JobRecommendationContent {
  schemaVersion: "daily_job_recommendation.v1"; decision: "recommend" | "reject";
  score: number; priority: "high" | "medium" | "low"; summary: string;
  matchedDirections: string[]; strengths: string[]; gaps: string[];
  hardGateFailures: string[]; preferenceReasons: string[]; actionSuggestion: string;
  assessments: JobRecommendationAssessment[];
}
export interface JobRecommendation {
  id: string; job_post_id: string; job_post_version_id: string;
  source_opportunity_id: string | null; agent_run_id: string;
  application_id: string | null; company: string; title: string;
  location: string | null; deadline_at: string | null; application_url: string | null;
  schema_version: string; decision: "recommend" | "reject"; score: number;
  priority: "high" | "medium" | "low"; content: JobRecommendationContent;
  status: "active" | "accepted" | "dismissed" | "stale"; version: number;
  recommended_at: string; resolved_at: string | null; resolution_reason: string | null;
}
export interface JobRecommendationList { items: JobRecommendation[]; total: number }

export type MaterialType = "resume" | "cover_letter" | "introduction";
export interface MaterialSummary {
  id: string; resume_id: string; name: string; material_type: MaterialType; status: "draft" | "reviewed" | "final";
  version: number; job_post_id: string; job_post_version_id: string; job_title: string; company: string;
  resume_series_type: "base" | "direction"; source_resume_version_id: string | null;
  resume_direction_selection_id: string | null;
  current_version_number: number; created_at: string; updated_at: string;
  strategy_stale: boolean; strategy_stale_reason: string | null; strategy_stale_at: string | null;
}
export interface MaterialFactSnapshot { id: string; fact_id: string; fact_version: number; category: string; field_key: string; value: string }
export interface MaterialBlock { id: string; section: string; text: string; fact_snapshots: MaterialFactSnapshot[] }
export interface MaterialVersion {
  id: string; parent_version_id: string | null; source_resume_version_id: string | null;
  version_scope: "base" | "direction" | "job_tailored"; version_number: number; status: string; title: string;
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
  exports: MaterialExport[];
}
export interface MaterialList { items: MaterialSummary[]; total: number }
export interface ResumeSeries {
  id: string; name: string; series_type: "base" | "direction"; parent_resume_id: string | null;
  direction_label: string | null; scope: "library" | "application"; application_id: string | null;
  application_status: ApplicationStatus | null; job_title: string | null; company: string | null;
  source_file_name: string | null; material_count: number; latest_version: MaterialVersion | null;
  latest_finalized_version: MaterialVersion | null; is_default: boolean; default_version: number | null;
  docx_export: MaterialExport | null;
  created_at: string; updated_at: string;
}
export interface ResumeSeriesList { items: ResumeSeries[]; total: number }
export interface ResumeDetail extends ResumeSeries {
  current_version: MaterialVersion & { rendered_text: string; blocks: MaterialBlock[] };
  versions: MaterialVersion[];
  review: MaterialReview | null;
  export: MaterialExport | null;
  exports: MaterialExport[];
}
export interface StandaloneResumeProposal {
  id: string;
  resume_name: string;
  user_prompt: string;
  fact_set_hash: string;
  schema_version: "resume_draft.v2";
  content: {
    schemaVersion: "resume_draft.v2";
    title: string;
    rationale: string;
    blocks: Array<{
      blockId: string;
      section: string;
      text: string;
      factIds: string[];
      requirementIds: string[];
    }>;
  };
  status: "proposed" | "confirmed" | "rejected";
  version: number;
  drafter_run_id: string;
  review_task_id: string | null;
  resume_id: string | null;
  resume_version_id: string | null;
  resolution_reason: string | null;
  created_at: string;
  resolved_at: string | null;
}
export interface StandaloneResumeProposalList {
  items: StandaloneResumeProposal[];
  total: number;
}
export interface ResumeVersionDiff {
  from_version: MaterialVersion; to_version: MaterialVersion;
  summary: { added: number; removed: number; changed: number; unchanged: number };
  fact_changes: { added_fact_ids: string[]; removed_fact_ids: string[] };
  blocks: Array<{ block_id: string; change: "added" | "removed" | "changed" | "unchanged";
    before: null | { id: string; section: string; text: string; fact_ids: string[] };
    after: null | { id: string; section: string; text: string; fact_ids: string[] } }>;
}
export interface MaterialAgentProposal {
  id: string; job_post_id: string; job_post_version_id: string; resume_direction_selection_id: string;
  base_resume_version_id: string | null;
  schema_version: "resume_draft.v2"; status: "proposed" | "confirmed" | "rejected"; version: number;
  content: { schemaVersion: "resume_draft.v2"; title: string; rationale: string; blocks: Array<{
    blockId: string; section: string; text: string; factIds: string[]; requirementIds: string[];
  }> };
  review_schema_version: "material_review.v2"; review: { schemaVersion: "material_review.v2";
    verdict: "pass" | "needs_revision"; summary: string; findings: Array<{
      severity: "error" | "warning" | "info"; code: string; message: string; blockId: string | null;
    }> };
  drafter_run_id: string; reviewer_run_id: string; review_task_id: string | null;
  material_draft_id: string | null; resolution_reason: string | null; created_at: string; resolved_at: string | null;
}
export interface MaterialAgentProposalList { items: MaterialAgentProposal[]; total: number }

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
  id: string; material_draft_id: string | null; resume_version_id: string; material_type: string; title: string;
  rendered_text: string; content_hash: string; fact_set_hash: string; export_id: string | null;
  export_sha256: string | null; created_at: string;
}
export interface ApplicationResumeBinding {
  id: string; application_id: string; resume_id: string; resume_name: string;
  resume_version_id: string; version_number: number; version_title: string;
  status: "active" | "replaced" | "locked"; source: string; reason: string; version: number;
  replaced_by_binding_id: string | null; created_at: string; updated_at: string;
  replaced_at: string | null; locked_at: string | null;
}
export interface AvailableFinalMaterial {
  id: string; resume_id: string; resume_version_id: string; version_number: number;
  name: string; title: string; material_type: string; scope: "library" | "application";
  application_id: string | null; finalized_at: string;
}
export interface ApplicationProposal {
  id: string; application_id: string; proposed_status: ApplicationStatus; occurred_at: string; note: string;
  source: string; source_ref: string | null; status: string; version: number; resolution_reason: string | null;
  created_at: string; resolved_at: string | null;
}
export interface Application extends ApplicationSummary {
  events: ApplicationEvent[]; material_snapshots: ApplicationMaterialSnapshot[]; proposals: ApplicationProposal[];
  resume_bindings: ApplicationResumeBinding[];
  active_resume_binding: ApplicationResumeBinding | null;
  available_final_materials: AvailableFinalMaterial[];
  mail_evidence: Array<{
    analysis_id: string; message_id: string; agent_run_id: string; sender: string; subject: string;
    sent_at: string | null; message_type: string; summary: string; match_confidence: number;
    items: Array<{ id: string; item_type: string; category: string; title: string; details: string;
      evidence: string; occurred_at: string | null; scheduled_at: string | null; status: string }>;
    created_at: string;
  }>;
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
export interface MailIntelligenceItem {
  id: string; item_type: "event" | "schedule" | "attention" | "create_application";
  application_id: string | null;
  category: string; status_candidate: string | null; occurred_at: string | null;
  scheduled_at: string | null; title: string; details: string; evidence: string;
  confidence: number | null; severity: string | null; status: "pending" | "confirmed" | "rejected";
  version: number; resolution_reason: string | null; review_task_id: string | null;
  created_at: string; resolved_at: string | null;
}
export interface MailIntelligence {
  id: string; agent_run_id: string; schema_version: string; relevance: string;
  message_type: string; summary: string; company: string | null; job_title: string | null;
  application_reference: string | null;
  job_post_id: string | null;
  application_match: { application_id: string | null; confidence: number; reason: string; create_record_recommended: boolean };
  items: MailIntelligenceItem[]; created_at: string; updated_at: string;
}
export interface MailMessage {
  id: string; uid: number; sender: string; subject: string; sent_at: string | null;
  classification: string; event_kind: string | null; extracted: Record<string, unknown>;
  evidence_excerpt: string | null; body_hash: string | null; body_fetched: boolean;
  attachments: Array<{ filename: string | null; content_type: string; size_bytes: number }>;
  candidate: MailCandidate | null; intelligence: MailIntelligence | null; created_at: string;
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
export interface UnifiedReviewTask {
  id: string; task_type: string; entity_type: string; entity_id: string; title: string;
  summary: string; source_type: string; priority: number; status: string; version: number;
  agent_run_id: string | null; target_url: string; created_at: string; updated_at: string;
  entity_subtype: string | null; can_resolve_inline: boolean;
  resolved_at: string | null; resolution: string | null; resolution_reason: string | null;
  resolved_by: string | null;
  bundle_type: string | null; section_type: string | null; aggregate_key: string | null;
  item_count: number; items: UnifiedReviewTask[];
}
export interface AgentRunAudit {
  id: string; task_type: string; execution_mode: string; implementation: string;
  provider: string | null; model: string | null; prompt_version: string | null;
  skill_version: string | null; schema_version: string; input_entity_type: string | null;
  input_entity_id: string | null; input_revision: string | null; input_hash: string | null;
  output_hash: string | null; tool_calls: Array<Record<string, unknown>>; status: string;
  output_count: number; input_tokens: number | null; output_tokens: number | null;
  duration_ms: number | null; retry_count: number; sensitivity: string;
  error_code: string | null; created_at: string; finished_at: string | null;
  retention_until: string | null;
}
export interface IntegrationHealth {
  status: "ok" | "attention"; issue_count: number; checked_counts: Record<string, number>;
  issues: Array<{ code: string; count: number; severity: "warning" | "error"; message: string }>;
}

interface ProblemDetails {
  title?: string;
  detail?: string | { message?: string; code?: string };
  code?: string;
  correlationId?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly correlationId?: string,
    readonly code?: string,
  ) {
    super(message);
  }
}

function problemMessage(problem: ProblemDetails, status: number): string {
  if (typeof problem.detail === "string") return problem.detail;
  if (problem.detail?.message) return problem.detail.message;
  return problem.title ?? `请求失败（HTTP ${status}）`;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as ProblemDetails;
    throw new ApiError(
      problemMessage(problem, response.status),
      response.status,
      problem.correlationId,
      problem.code,
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
      problemMessage(problem, response.status),
      response.status,
      problem.correlationId,
      problem.code,
    );
  }
  if (response.status === 204) return undefined as T;
  const contentLength = response.headers?.get?.("content-length");
  if (contentLength === "0") return undefined as T;
  return (await response.json()) as T;
}

export const getSystemStatus = () => getJson<SystemStatus>("/api/v1/system/status");
export const getOnboardingStatus = () => getJson<OnboardingStatus>("/api/v1/onboarding");
export const completeOnboarding = (skipped_steps: string[]) =>
  sendJson<OnboardingStatus>("/api/v1/onboarding/complete", { skipped_steps });
export const updateOnboardingStep = (step: string, state: string) =>
  putJson<OnboardingStatus>(`/api/v1/onboarding/steps/${step}`, { state });
export const reopenOnboarding = () => sendJson<OnboardingStatus>("/api/v1/onboarding/reopen", {});
export const restartService = () => sendJson<{ status: string }>("/api/v1/system/restart", {});
export const getWorkspaceStatus = () => getJson<WorkspaceStatus>("/api/v1/workspace");
export const validateWorkspace = (parent_directory: string) =>
  sendJson<WorkspaceValidation>("/api/v1/workspace/validate", { parent_directory });
export const pickWorkspaceDirectory = (initial_directory?: string) =>
  sendJson<WorkspaceDirectorySelection>("/api/v1/workspace/pick-directory", {
    initial_directory: initial_directory || null,
  });
export const createWorkspace = (parent_directory: string, name: string) =>
  sendJson<{ workspace_path: string; manifest: WorkspaceStatus["manifest"]; restart_required: boolean }>(
    "/api/v1/workspace", { parent_directory, name },
  );
export const cancelPendingWorkspace = () =>
  deleteJson<{ cancelled: boolean }>("/api/v1/workspace/pending");
export const exportPortableWorkspace = (include_secrets: boolean, passphrase?: string) =>
  sendJson<PortableWorkspaceExport>("/api/v1/workspace/portable-export", {
    include_secrets, passphrase: passphrase || null,
  });
export const importPortableWorkspace = (
  file: File, parentDirectory: string, passphrase?: string,
) => {
  const body = new FormData();
  body.append("file", file); body.append("parent_directory", parentDirectory);
  if (passphrase) body.append("passphrase", passphrase);
  return sendForm<PortableWorkspaceImport>("/api/v1/workspace/portable-import", body);
};
export const getConfiguration = () =>
  getJson<ConfigurationStatus>("/api/v1/configuration");
export const testConfigurationCapability = (capability: string) =>
  sendJson<ConfigurationCheckResult>(
    `/api/v1/configuration/checks/${capability}`, {},
  );
export const updateConfiguration = (
  expected_revision: number, configuration: CareerConsoleConfiguration, reason: string,
) => putJson<ConfigurationStatus>("/api/v1/configuration", {
  expected_revision, configuration, reason,
});
export const getConfigurationChanges = () =>
  getJson<{ items: ConfigurationChange[]; total: number }>("/api/v1/configuration/changes");
export const getProviderCatalog = () =>
  getJson<{ items: ProviderCatalogItem[]; total: number }>("/api/v1/configuration/provider-catalog");
export const getProviders = () =>
  getJson<{ items: ProviderView[]; total: number }>("/api/v1/configuration/providers");
export const upsertProvider = (providerId: string, body: {
  expected_revision: number; provider_type: ProviderType; display_name: string;
  enabled: boolean; api_base: string | null; default_model: string;
  models: string[]; api_key?: string;
}) => putJson<{ provider: ProviderView; configuration_revision: number; restart_required: boolean }>(
  `/api/v1/configuration/providers/${encodeURIComponent(providerId)}`, body,
);
export const deleteProvider = (providerId: string, expectedRevision: number) =>
  deleteJson<{ deleted: boolean; configuration_revision: number }>(
    `/api/v1/configuration/providers/${encodeURIComponent(providerId)}?expected_revision=${expectedRevision}`,
  );
export const updateAgentConfiguration = (expected_revision: number, agents: AgentConfiguration) =>
  putJson<ConfigurationStatus>("/api/v1/configuration/agents", { expected_revision, agents });
export const testProvider = (providerId: string, model?: string) =>
  sendJson<ProviderTestRun>(`/api/v1/configuration/providers/${encodeURIComponent(providerId)}/test`, { model: model || null });
export const getProviderTests = () =>
  getJson<{ items: ProviderTestRun[]; total: number }>("/api/v1/configuration/provider-tests");
export const getQQChannel = () => getJson<QQChannelView>("/api/v1/channels/qq");
export const configureQQChannel = (body: Omit<QQChannelView, "has_secret" | "configuration_revision"> & {
  expected_revision: number; secret?: string;
}) => putJson<QQChannelView>("/api/v1/channels/qq", body);
export const deleteQQChannel = (revision: number) =>
  deleteJson<{ deleted: boolean }>(`/api/v1/channels/qq?expected_revision=${revision}`);
export const testQQChannel = () => sendJson<ChannelDeliveryRun>("/api/v1/channels/qq/test", {});
export const getChannelDeliveries = () =>
  getJson<{ items: ChannelDeliveryRun[]; total: number }>("/api/v1/channels/deliveries");
export const configureScheduler = (expected_revision: number, scheduler: CareerConsoleConfiguration["scheduler"]) =>
  putJson<CareerConsoleConfiguration["scheduler"] & { configuration_revision: number }>(
    "/api/v1/scheduler/configuration", { expected_revision, scheduler },
  );
export const getSchedulerRuns = () =>
  getJson<{ items: SchedulerRun[]; total: number }>("/api/v1/scheduler/runs");
export const getBackgroundJobs = () => getJson<BackgroundJobList>("/api/v1/jobs");
export const retryBackgroundJob = (id: string) => sendJson<BackgroundJob>(`/api/v1/jobs/${id}/retry`, {});
export const cancelBackgroundJob = (id: string) => sendJson<BackgroundJob>(`/api/v1/jobs/${id}/cancel`, {});
export const getBossConnector = () => getJson<BossConnector>("/api/v1/connectors/boss");
export const getOpenCliConfiguration = () => getJson<{ executable: string | null; resolved_executable: string | null; installed: boolean }>("/api/v1/connectors/opencli");
export const configureOpenCli = (executable: string | null) => putJson<{ executable: string | null; resolved_executable: string | null; installed: boolean }>("/api/v1/connectors/opencli", { executable });
export const configureBossConnector = (body: BossConnectorUpdate) => putJson<BossConnector>("/api/v1/connectors/boss", body);
export const checkBossConnector = () => sendJson<{ status: string; opencli_version?: string; error_code?: string }>("/api/v1/connectors/boss/health", {});
export const loginBossConnector = () => sendJson<Record<string, unknown>>("/api/v1/connectors/boss/login", { timeout: 300 });
export const scanBossConnector = () => sendJson<SyncRun>("/api/v1/connectors/boss/scan", {});
export const getNowcoderConnector = () => getJson<NowcoderConnector>("/api/v1/connectors/nowcoder");
export const configureNowcoderConnector = (body: NowcoderConnectorUpdate) => putJson<NowcoderConnector>("/api/v1/connectors/nowcoder", body);
export const checkNowcoderConnector = () => sendJson<{ status: string; opencli_version?: string; error_code?: string }>("/api/v1/connectors/nowcoder/health", {});
export const loginNowcoderConnector = () => sendJson<Record<string, unknown>>("/api/v1/connectors/nowcoder/login", { timeout: 300 });
export const scanNowcoderConnector = (lookbackDays: 0 | 7 | 14 | 30) => sendJson<SyncRun>("/api/v1/connectors/nowcoder/scan", { lookback_days: lookbackDays });
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
export const analyzeMailMessage = (messageId: string) =>
  sendJson<MailIntelligence>(`/api/v1/mail/messages/${messageId}/analyze`, {});
export const resolveMailIntelligenceItem = (
  item: Pick<MailIntelligenceItem, "id" | "version">, resolution: "confirmed" | "rejected",
) => sendJson<MailIntelligenceItem>(`/api/v1/mail/intelligence-items/${item.id}/resolve`, {
  expected_version: item.version, resolution,
  reason: resolution === "confirmed" ? "用户核对邮件证据后确认" : "用户判定该分析不准确",
});
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
  getJson<{ items: UnifiedReviewTask[]; total: number }>("/api/v1/runtime/reviews");
export const getUnifiedReviews = (status = "open") =>
  getJson<{ items: UnifiedReviewTask[]; total: number }>(
    `/api/v1/runtime/reviews?status=${encodeURIComponent(status)}`,
  );
export const getUnifiedReview = (id: string) =>
  getJson<UnifiedReviewTask>(`/api/v1/runtime/reviews/${encodeURIComponent(id)}`);
export const resolveUnifiedReviewBundle = (
  review: UnifiedReviewTask,
  resolution: "confirmed" | "rejected",
) => sendJson<UnifiedReviewTask>(
  `/api/v1/runtime/reviews/${encodeURIComponent(review.id)}/resolve`,
  { expected_version: review.version, resolution, reason: "用户在待我处理整组处理" },
);
export const getAgentRuns = () =>
  getJson<{ items: AgentRunAudit[]; total: number }>("/api/v1/runtime/agent-runs");
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
export const getProfileMemory = () => getJson<ProfileMemory>("/api/v1/profile-memory");
export const setCareerPreference = (key: string, value: unknown, expected_version: number | null) =>
  putJson<ProfileMemory["preferences"][number]>(`/api/v1/profile-memory/preferences/${encodeURIComponent(key)}`, { value, expected_version });
export const generateDailyDigest = () => sendJson<ProfileMemory["digests"][number]>("/api/v1/profile-memory/digests/daily", {});
export const generateStrategyProposal = () => sendJson<ProfileMemory["strategies"][number]>("/api/v1/profile-memory/strategies", {});
export const generateProfileInsight = () => sendJson<ProfileMemory["insights"]>("/api/v1/profile-memory/insights", {});
export const runProfileImpacts = () => sendJson<{ queued: number; processed: number }>("/api/v1/profile-memory/impacts/run", {});
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
export const reprocessDocument = (documentId: string) =>
  sendJson<ImportedDocument>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/reprocess`,
    {},
  );
export const addManualFact = (body: {
  category: string; field_key: string; value: string; source_note: string;
}) => sendJson<CandidateFact>("/api/v1/facts", body);
export const reviseFact = (fact: CandidateFact, instruction: string) =>
  sendJson<CandidateFact>(`/api/v1/facts/${fact.id}/agent-revise`, {
    expected_version: fact.version,
    instruction,
  });
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
export const getOpportunities = (triageStatus?: OpportunityTriageStatus) =>
  getJson<RecruitmentOpportunityList>(
    `/api/v1/opportunities${triageStatus ? `?triage_status=${triageStatus}` : ""}`,
  );
export const getTodayOpportunities = () =>
  getJson<RecruitmentOpportunityList>("/api/v1/opportunities?today=true");
export const getOpportunity = (id: string) =>
  getJson<RecruitmentOpportunityDetail>(`/api/v1/opportunities/${id}`);
export const triageOpportunity = (
  opportunity: RecruitmentOpportunity,
  triage_status: OpportunityTriageStatus,
) => sendJson<RecruitmentOpportunity>(`/api/v1/opportunities/${opportunity.id}/triage`, {
  triage_status,
  expected_version: opportunity.version,
});
export const getJobRecommendations = (status: JobRecommendation["status"] = "active") =>
  getJson<JobRecommendationList>(
    `/api/v1/job-recommendations?status=${encodeURIComponent(status)}`,
  );
export const dismissJobRecommendation = (recommendation: JobRecommendation) =>
  sendJson<JobRecommendation>(`/api/v1/job-recommendations/${recommendation.id}/dismiss`, {
    expected_version: recommendation.version,
    reason: "用户从岗位推荐池移除",
  });
export const acceptJobRecommendation = (
  recommendation: JobRecommendation,
  commandId: string,
) => sendJson<JobRecommendation>(
  `/api/v1/job-recommendations/${recommendation.id}/accept`,
  {
    expected_version: recommendation.version,
    command_id: commandId,
  },
);
export const getJobPost = (id: string) => getJson<JobPost>(`/api/v1/job-posts/${id}`);
export const importJobText = (name: string, text: string, opportunity_id?: string, mail_analysis_id?: string) =>
  sendJson<JobPost>("/api/v1/job-posts/import-text", { name, text, opportunity_id, mail_analysis_id });
export const importJobUrl = (url: string, opportunity_id?: string, mail_analysis_id?: string) =>
  sendJson<JobPost>("/api/v1/job-posts/import-url", { url, confirmed: true, opportunity_id, mail_analysis_id });
export async function importJobFile(file: File, opportunityId?: string, mailAnalysisId?: string): Promise<JobPost> {
  const form = new FormData(); form.append("file", file);
  if (opportunityId) form.append("opportunity_id", opportunityId);
  if (mailAnalysisId) form.append("mail_analysis_id", mailAnalysisId);
  return sendForm<JobPost>("/api/v1/job-posts/import-file", form);
}
export const analyzeJob = (id: string) => sendJson<JobAnalysis>(`/api/v1/job-posts/${id}/analyses`, {});
export const getJobFitProposals = (id: string) => getJson<JobFitProposalList>(`/api/v1/job-posts/${id}/agent-fit-proposals`);
export const generateJobFitProposal = (id: string) => sendJson<JobFitProposal>(`/api/v1/job-posts/${id}/agent-fit-proposals`, {});
export const resolveJobFitProposal = (proposal: JobFitProposal, resolution: "confirmed" | "rejected") =>
  sendJson<JobFitProposal>(`/api/v1/job-posts/agent-fit-proposals/${proposal.id}/resolve`, {
    expected_version: proposal.version, resolution, reason: resolution === "confirmed" ? "用户逐项核验 Agent 岗位证据" : "用户拒绝该 Agent 分析",
  });
export const getResumeDirections = (jobId: string) => getJson<ResumeDirectionOverview>(`/api/v1/job-posts/${jobId}/resume-directions`);
export const generateResumeDirections = (jobId: string) => sendJson<ResumeDirectionProposal>(`/api/v1/job-posts/${jobId}/resume-directions`, {});
export const resolveResumeDirections = (proposal: ResumeDirectionProposal, resolution: "confirmed" | "rejected", selectedDirectionIds: string[]) =>
  sendJson<ResumeDirectionProposal>(`/api/v1/job-posts/resume-directions/${proposal.id}/resolve`, {
    expected_version: proposal.version, resolution,
    selected_direction_ids: resolution === "confirmed" ? selectedDirectionIds : [],
    reason: resolution === "confirmed" ? "用户选择并确认简历方向" : "用户拒绝本组简历方向",
  });
export const getMaterials = () => getJson<MaterialList>("/api/v1/materials");
export const getResumeSeries = () => getJson<ResumeSeriesList>("/api/v1/resumes");
export const getApplicationResumes = () => getJson<ResumeSeriesList>("/api/v1/resumes/application");
export const getResume = (id: string) => getJson<ResumeDetail>(`/api/v1/resumes/${id}`);
export const generateResume = (body: { name: string; prompt: string }) =>
  sendJson<ResumeDetail>("/api/v1/resumes/generate", body);
export async function importResume(name: string, file: File): Promise<ResumeDetail> {
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  return sendForm<ResumeDetail>("/api/v1/resumes/import", form);
}
export const deleteResume = (resumeId: string) =>
  deleteJson<void>(`/api/v1/resumes/${encodeURIComponent(resumeId)}`);
export const saveApplicationResumeToLibrary = (resumeId: string, name: string) =>
  sendJson<ResumeDetail>(
    `/api/v1/resumes/${encodeURIComponent(resumeId)}/save-to-library`,
    { name },
  );
export const getStandaloneResumeProposals = () =>
  getJson<StandaloneResumeProposalList>("/api/v1/resumes/agent-proposals");
export const generateStandaloneResumeProposal = (body: { name: string; prompt: string }) =>
  sendJson<StandaloneResumeProposal>("/api/v1/resumes/agent-proposals", body);
export const resolveStandaloneResumeProposal = (
  proposal: StandaloneResumeProposal,
  resolution: "confirmed" | "rejected",
) => sendJson<StandaloneResumeProposal>(
  `/api/v1/resumes/agent-proposals/${proposal.id}/resolve`,
  {
    expected_version: proposal.version,
    resolution,
    reason: resolution === "confirmed"
      ? "用户核对内容与事实依据后确认创建简历"
      : "用户拒绝该独立简历候选",
  },
);
export const editResume = (
  resume: ResumeDetail,
  blocks: Array<{ id: string; text: string }>,
) => sendJson<ResumeDetail>(`/api/v1/resumes/${resume.id}/versions`, {
  expected_version_id: resume.current_version.id,
  blocks,
});
export const reviewResume = (id: string) =>
  sendJson<ResumeDetail>(`/api/v1/resumes/${id}/reviews`, {});
export const finalizeResume = (resume: ResumeDetail) =>
  sendJson<ResumeDetail>(`/api/v1/resumes/${resume.id}/finalize`, {
    expected_version_id: resume.current_version.id,
  });
export const getDefaultResume = () => getJson<ResumeSeries | null>("/api/v1/resumes/default");
export const setDefaultResume = (resume: ResumeSeries, currentDefault: ResumeSeries | null) =>
  putJson<ResumeSeries>("/api/v1/resumes/default", {
    resume_id: resume.id,
    expected_version: currentDefault?.default_version ?? null,
  });
export const forkResumeFromMaterial = (body: { material_id: string; series_type: "base" | "direction";
  name: string; parent_resume_id?: string; direction_label?: string }) =>
  sendJson<ResumeSeries>("/api/v1/resumes/from-material", body);
export const getResumeVersionDiff = (fromVersionId: string, toVersionId: string) =>
  getJson<ResumeVersionDiff>(`/api/v1/resumes/versions/${fromVersionId}/diff/${toVersionId}`);
export const getMaterial = (id: string) => getJson<Material>(`/api/v1/materials/${id}`);
export const generateMaterial = (body: { job_post_id: string; material_type: MaterialType; name: string; resume_id?: string }) =>
  sendJson<Material>("/api/v1/materials", body);
export const generateApplicationResume = (body: {
  application_id: string;
  job_post_id: string;
  source_resume_version_id: string | null;
  resume_name: string;
  prompt: string;
}) => sendJson<Material>("/api/v1/materials/generate", body);
export const getMaterialAgentProposals = (jobId: string) =>
  getJson<MaterialAgentProposalList>(`/api/v1/materials/agent-proposals?job_post_id=${encodeURIComponent(jobId)}`);
export const generateMaterialAgentProposal = (body: { job_post_id: string; resume_name: string; resume_id?: string }) =>
  sendJson<MaterialAgentProposal>("/api/v1/materials/agent-proposals", body);
export const resolveMaterialAgentProposal = (proposal: MaterialAgentProposal, resolution: "confirmed" | "rejected") =>
  sendJson<MaterialAgentProposal>(`/api/v1/materials/agent-proposals/${proposal.id}/resolve`, {
    expected_version: proposal.version, resolution,
    reason: resolution === "confirmed" ? "用户确认 Drafter–Reviewer 草稿" : "用户拒绝 Agent 材料候选",
  });
export const editMaterial = (material: Material, blocks: Array<{ id: string; text: string }>) =>
  sendJson<Material>(`/api/v1/materials/${material.id}/versions`, { expected_version: material.version, blocks });
export const reviewMaterial = (id: string) => sendJson<Material>(`/api/v1/materials/${id}/reviews`, {});
export const finalizeMaterial = (material: Material) =>
  sendJson<Material>(`/api/v1/materials/${material.id}/finalize`, { expected_version: material.version });
export const getApplications = () => getJson<ApplicationList>("/api/v1/applications");
export const getApplication = (id: string) => getJson<Application>(`/api/v1/applications/${id}`);
export const createApplication = (job_post_id: string) => sendJson<Application>("/api/v1/applications", { job_post_id });
export const bindApplicationResume = (
  application: Application,
  selection: {
    resume_version_id?: string;
    use_default: boolean;
    reason: string;
    source?: "user" | "generated" | "mail_default" | "migration";
  },
) => sendJson<Application>(`/api/v1/applications/${application.id}/resume-bindings`, {
  expected_version: application.version,
  command_id: globalThis.crypto?.randomUUID?.() ?? `bind-${Date.now()}`,
  ...selection,
  source: selection.source ?? "user",
});
export const submitApplication = (application: Application, resume_version_id: string, occurred_at: string, note: string) =>
  sendJson<Application>(`/api/v1/applications/${application.id}/submit`, {
    expected_version: application.version,
    resume_version_id,
    occurred_at,
    note,
    command_id: globalThis.crypto?.randomUUID?.() ?? `submit-${Date.now()}`,
  });
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
