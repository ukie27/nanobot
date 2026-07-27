import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DataSourceSettings } from "./SettingsPage";
import { chinaInputToIso, isoToChinaInput } from "./time";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderApp(path = "/status") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Career app shell", () => {
  it("keeps embedded data-source setup inside the onboarding step", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        executable: "opencli.cmd",
        resolved_executable: "D:/tools/opencli.cmd",
        installed: true,
      }),
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><DataSourceSettings embedded /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "OpenCLI 应用" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "配置牛客与 BOSS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "配置只读邮箱" })).not.toBeInTheDocument();
  });

  it("uses China Standard Time independently of the browser timezone", () => {
    expect(chinaInputToIso("2026-07-25T14:30")).toBe("2026-07-25T06:30:00.000Z");
    expect(isoToChinaInput("2026-07-25T06:30:00Z")).toBe("2026-07-25T14:30");
  });

  it("renders real system status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        version: "0.1.4",
        health: "ready",
        database: "ok",
        database_revision: "20260723_0001",
        expected_revision: "20260723_0001",
        recovered_jobs_at_startup: 0,
        paths: { data_dir: "D:/career", database: "D:/career/db", logs: "D:/career/logs", backups: "D:/career/backups" },
      }),
    }));
    renderApp();
    expect(await screen.findByText("服务就绪")).toBeInTheDocument();
    expect(screen.getByText("20260723_0001")).toBeInTheDocument();
  });

  it("renders versioned unified settings and change audit", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string) => {
      if (input === "/api/v1/system/session") return Promise.resolve({
        ok: true, json: async () => ({ csrf_token: "test-token" }),
      });
      if (input === "/api/v1/workspace") return Promise.resolve({ ok: true, json: async () => ({
        product: "CareerConsole", workspace_path: "D:/CareerConsole",
        active_workspace_path: "D:/CareerConsole", onboarding_required: false,
        restart_required: false, manifest: { schemaVersion: "career-console.workspace.v1" },
        paths: { database: "D:/CareerConsole/data/career-console.sqlite3", config: "D:/CareerConsole/config", backups: "D:/CareerConsole/backups", exports: "D:/CareerConsole/exports" },
      }) });
      if (input === "/api/v1/configuration/changes") return Promise.resolve({ ok: true, json: async () => ({
        total: 1, items: [{ id: "change-1", previous_revision: 0, new_revision: 1,
          changed_paths: ["*"], activation_effect: "restart_required",
          reason: "初始化工作区配置", created_at: "2026-07-26T00:00:00Z" }],
      }) });
      if (input === "/api/v1/configuration/provider-catalog") return Promise.resolve({ ok: true, json: async () => ({
        total: 1, items: [{ type: "openai", label: "OpenAI", default_api_base: "https://api.openai.com/v1", requires_api_key: true, is_local: false }],
      }) });
      if (input === "/api/v1/configuration/providers") return Promise.resolve({ ok: true, json: async () => ({
        total: 1, items: [{ id: "main", provider_type: "openai", display_name: "主模型", enabled: true,
          api_base: "https://api.openai.com/v1", default_model: "gpt-main", models: ["gpt-main", "gpt-review"],
          secret_ref: "career-console:workspace:provider:main:api-key", has_secret: true }],
      }) });
      if (input === "/api/v1/configuration/provider-tests") return Promise.resolve({ ok: true, json: async () => ({
        total: 1, items: [{ id: "test-1", provider_id: "main", provider_type: "openai", model: "gpt-main",
          status: "passed", error_code: null, duration_ms: 128, created_at: "2026-07-26T00:00:00Z" }],
      }) });
      if (input === "/api/v1/configuration/agents") return Promise.resolve({
        ok: true,
        json: async () => ({
          schema_version: "career-console.configuration.v1",
          revision: 2,
          active_revision: 1,
          activation_status: "restart_required",
          changed_paths: ["agents.tasks"],
          activation_effect: "restart_required",
        }),
      });
      if (input === "/api/v1/channels/qq") return Promise.resolve({ ok: true, json: async () => ({
        enabled: true, app_id: "102000000", allow_from: [], notification_targets: ["c2c:user-open-id"],
        event_subscriptions: ["task_reminder", "system_alert"], message_format: "plain", outbound_only: true,
        quiet_hours: { enabled: true, start: "22:00", end: "08:00", timezone: "Asia/Shanghai" },
        has_secret: true, configuration_revision: 1,
      }) });
      if (input === "/api/v1/channels/deliveries") return Promise.resolve({ ok: true, json: async () => ({
        total: 1, items: [{ id: "delivery-1", channel_type: "qq", event_type: "connection_test",
          target_masked: "c2c:sha256:123456789abc", status: "passed", error_code: null,
          duration_ms: 120, created_at: "2026-07-26T00:00:00Z" }],
      }) });
      return Promise.resolve({ ok: true, json: async () => ({
        schema_version: "career-console.configuration.v1", revision: 1,
        updated_at: "2026-07-26T00:00:00Z", active_revision: 1,
        activation_status: "active", configuration: {
          general: { locale: "zh-CN", timezone: "Asia/Shanghai", date_format: "yyyy-MM-dd", open_browser_on_start: true },
          appearance: { density: "comfortable", reduce_motion: false },
          runtime: { log_level: "INFO", log_retention_days: 14, agent_trace_retention_days: 30, job_lease_seconds: 60, max_document_mb: 10 },
          privacy: { diagnostics_metadata_enabled: true, redact_sensitive_logs: true, local_only_network_binding: true },
          providers: { main: { provider_type: "openai", display_name: "主模型", enabled: true,
            api_base: "https://api.openai.com/v1", default_model: "gpt-main", models: ["gpt-main", "gpt-review"],
            secret_ref: "career-console:workspace:provider:main:api-key" } },
          agents: { tasks: Object.fromEntries([
            "fact_extraction", "mail_intelligence", "profile_insight", "job_fit", "resume_direction", "resume_drafting", "material_review",
          ].map(name => [name, { enabled: true, provider_id: "main", model: name === "material_review" ? "gpt-review" : "gpt-main", temperature: 0.1, max_tokens: 4096, reasoning_effort: null }])) },
          connectors: { opencli: { executable: null,
            boss: { enabled: false, profile_alias: "default", search_query: "", city: "全国", result_limit: 15 },
            nowcoder: { enabled: true, search_query: "", city: "全国", result_limit: 500, schedule_enabled: true, schedule_times: ["09:00"], timezone: "Asia/Shanghai" } },
            imap: { enabled: false, email_address: "", host: "", port: 993, username: "", folder: "INBOX", initial_lookback_days: 30, poll_interval_minutes: 10, secret_ref: null } },
          channels: { qq: { enabled: false, app_id: "", allow_from: [], notification_targets: [], event_subscriptions: ["task_reminder", "system_alert"], message_format: "plain", outbound_only: true, quiet_hours: { enabled: false, start: "22:00", end: "08:00", timezone: "Asia/Shanghai" }, secret_ref: null }, send_max_retries: 3 },
          scheduler: { enabled: true, poll_seconds: 60, reminders_enabled: true, connector_jobs_enabled: true, profile_maintenance_enabled: true, profile_maintenance_time: "21:30", channel_dispatch_enabled: true },
        },
      }) });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/settings");
    expect(await screen.findByRole("heading", { name: "常规" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Asia/Shanghai")).toBeInTheDocument();
    expect(screen.getByText("敏感日志脱敏：强制开启")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "数据与迁移" }));
    expect(screen.getByRole("heading", { name: "导入与导出" })).toBeInTheDocument();
    expect(screen.getByText("防止压缩包中的路径越界")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "AI 与 Agent" }));
    expect(await screen.findByText("主模型 · gpt-main · 凭据已配置")).toBeInTheDocument();
    expect(screen.getByText("材料撰写")).toBeInTheDocument();
    expect(screen.getByText("材料复核")).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("已安全保存；留空保持不变").find(element => element.getAttribute("name") === "api_key")).toHaveValue("");
    expect(screen.queryByDisplayValue("career-console:workspace:provider:main:api-key")).not.toBeInTheDocument();
    expect(await screen.findByText("主模型 · 通过")).toBeInTheDocument();
    expect(screen.queryByLabelText("Provider ID")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存任务映射" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/configuration/agents",
        expect.objectContaining({ method: "PUT" }),
      );
    });
    expect(await screen.findByText("任务映射已保存。重启服务后应用新的 AI 运行配置。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "通知渠道" }));
    expect(screen.getByRole("heading", { name: "QQ 通知" })).toBeInTheDocument();
    expect(await screen.findByText("凭据已配置")).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("已安全保存；留空保持不变").find(element => element.getAttribute("name") === "secret")).toHaveValue("");
    expect(screen.queryByDisplayValue("qq-secret-value")).not.toBeInTheDocument();
    expect(await screen.findByText(/c2c:sha256:123456789abc/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "高级诊断" }));
    expect(await screen.findByText("配置版本 0 → 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新进入初始化向导" })).toBeInTheDocument();
  });

  it("gates the product behind first-run onboarding", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => {
      if (input === "/api/v1/onboarding") return Promise.resolve({ ok: true, json: async () => ({
        schema_version: "career-console.onboarding.v1", onboarding_version: 1,
        required_version: 1, completed: false, completed_at: null, skipped_steps: [],
        step_states: {},
        workspace_ready: false, restart_required: false, runtime_mode: "bootstrap",
        capabilities: { workspace: false, provider: false, profile: false, mail: false,
          opencli: false, channel: false, scheduler: true },
      }) });
      return Promise.resolve({ ok: true, json: async () => ({
        product: "CareerConsole", workspace_path: "D:/bootstrap",
        active_workspace_path: null, onboarding_required: true, restart_required: false,
        manifest: null, paths: { database: "D:/bootstrap/data/career-console.sqlite3" },
      }) });
    }));

    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "配置你的求职工作台" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认工作区并继续" })).toBeDisabled();
    expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
  });

  it("allows changing an already selected workspace during onboarding", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => {
      if (input === "/api/v1/onboarding") return Promise.resolve({ ok: true, json: async () => ({
        completed: false, workspace_ready: true, restart_required: false,
        runtime_mode: "bootstrap", skipped_steps: [], step_states: {},
        capabilities: { workspace: true, provider: false, profile: false, mail: false,
          opencli: false, channel: false, scheduler: true },
      }) });
      if (input === "/api/v1/workspace") return Promise.resolve({ ok: true, json: async () => ({
        product: "CareerConsole", workspace_path: "D:/Current/CareerConsole",
        active_workspace_path: "D:/Current/CareerConsole", onboarding_required: true,
        restart_required: false, manifest: { schemaVersion: "career-console.workspace.v1" },
        paths: { database: "D:/Current/CareerConsole/data/career-console.sqlite3" },
      }) });
      if (input === "/api/v1/workspace/pick-directory") return Promise.resolve({ ok: true, json: async () => ({
        cancelled: false, parent_directory: "D:/SelectedParent",
      }) });
      return Promise.resolve({ ok: true, json: async () => ({
        activation_status: "active", configuration: { providers: {}, agents: { tasks: {} } },
      }) });
    }));

    renderApp("/dashboard");
    const change = await screen.findByRole("button", { name: "更换工作区" });
    expect(screen.getByText("D:/Current/CareerConsole")).toBeInTheDocument();
    fireEvent.click(change);
    expect(screen.getByLabelText("父目录")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "选择文件夹" }));
    expect(await screen.findByDisplayValue("D:/SelectedParent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消更换" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消更换" }));
    expect(screen.getByRole("button", { name: "更换工作区" })).toBeInTheDocument();
  });

  it("shows an actionable API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "Database is not ready", correlationId: "test-id" }),
    }));
    renderApp();
    expect(await screen.findByText("Database is not ready")).toBeInTheDocument();
    expect(screen.getByText(/test-id/)).toBeInTheDocument();
  });

  it("renders the trusted profile from confirmed facts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => {
      if (input === "/api/v1/profile") {
        return Promise.resolve({ ok: true, json: async () => ({
          id: "profile", display_name: "张三", timezone: "Asia/Shanghai", version: 2,
          fact_counts: { proposed: 1, confirmed: 1, rejected: 0 },
          created_at: "2026-07-23T00:00:00Z", updated_at: "2026-07-23T00:00:00Z",
        }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({
        total: 1, items: [{ id: "fact", profile_id: "profile", category: "skill",
          field_key: "skill", value: "Python", status: "confirmed", confidence: 0.9,
          version: 2, sources: [], revisions: [], created_at: "2026-07-23T00:00:00Z",
          updated_at: "2026-07-23T00:00:00Z" }],
      }) });
    }));
    renderApp("/profile");
    expect(await screen.findByRole("heading", { name: "张三" })).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("可用于正式内容")).toBeInTheDocument();
  });

  it("renders versioned jobs with hard-gate status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        total: 1,
        items: [{
          id: "job-1", company: "示例科技", title: "Python 后端工程师", location: "上海",
          employment_type: "全职", work_mode: "混合办公", deadline_at: null, status: "active",
          version: 2, created_at: "2026-07-23T00:00:00Z", updated_at: "2026-07-23T00:00:00Z",
          latest_analysis: { id: "analysis", job_post_version_id: "version", hard_gate_passed: false,
            score: 80, matched_count: 3, gap_count: 1, must_gap_count: 1,
            recommendation: "blocked", created_at: "2026-07-23T00:00:00Z" },
        }],
      }),
    }));
    renderApp("/job-posts");
    const heading = await screen.findByRole("heading", { name: "Python 后端工程师" });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("硬条件不满足 · 80")).toBeInTheDocument();
    expect(heading.closest("a")).toHaveTextContent("v2");
  });

  it("keeps recruitment opportunities separate from concrete job posts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        total: 1,
        items: [{
          id: "opportunity-1", company: "网易游戏雷火", batch: "27届秋招",
          cities: "杭州", careers: "后端开发,测试", industries: "游戏",
          evaluation: "公开校招项目", application_starts_at: "2026-07-26T00:00:00Z",
          application_ends_at: "2026-08-26T00:00:00Z",
          announcement_url: "https://example.com/announcement",
          application_url: "https://example.com/apply", triage_status: "new", version: 1,
          first_collected_at: "2026-07-26T01:00:00Z", last_collected_at: "2026-07-26T01:00:00Z",
          created_at: "2026-07-26T01:00:00Z", updated_at: "2026-07-26T01:00:00Z",
          sources: [{ id: "source", external_id: "895:1210:1784390400000",
            source_url: "https://www.nowcoder.com/enterprise/895", first_seen_at: "2026-07-26T01:00:00Z",
            last_seen_at: "2026-07-26T01:00:00Z" }],
          linked_jobs: [],
        }],
      }),
    }));
    renderApp("/opportunities");
    expect(await screen.findByRole("heading", { name: "每日招聘" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "网易游戏雷火 · 27届秋招" })).toBeInTheDocument();
    expect(screen.getByText("这里收录招聘项目线索，不代表具体岗位 JD")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开官方投递入口" })).toHaveAttribute(
      "href", "https://example.com/apply",
    );
    expect(
      screen
        .getAllByRole("link", { name: "目标岗位" })
        .some((link) => link.getAttribute("href") === "/job-posts"),
    ).toBe(true);
    expect(screen.getByRole("link", { name: "导入具体 JD" })).toHaveAttribute(
      "href", "/job-posts?opportunityId=opportunity-1",
    );
  });

  it("renders one cross-domain human review queue", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ total: 1, items: [{
        id: "review-1", task_type: "candidate_fact_review", entity_type: "candidate_fact",
        entity_id: "fact-1", title: "确认职业事实：Python", summary: "技能：Python",
        source_type: "agent_extraction", priority: 20, status: "open", version: 1,
        agent_run_id: "agent-run-1234", target_url: "/review",
        created_at: "2026-07-26T01:00:00Z", updated_at: "2026-07-26T01:00:00Z",
        resolved_at: null, resolution: null, resolution_reason: null, resolved_by: null,
      }] }),
    }));
    renderApp("/reviews");
    expect(await screen.findByRole("heading", { name: "审查中心" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "确认职业事实：Python" })).toBeInTheDocument();
    expect(screen.getByText("Agent 只能提出候选，不能直接改变正式业务事实")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /确认职业事实：Python/ })).toHaveAttribute("href", "/review");
  });

  it("renders safe AgentRun audit metadata without business content", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ total: 1, items: [{
        id: "run-1", task_type: "profile_fact_extraction", execution_mode: "task",
        implementation: "career_console_profile_fact_extractor", provider: "LocalProvider",
        model: "local-model", prompt_version: "profile_fact_extraction.v1", skill_version: null,
        schema_version: "candidate_fact.v1", input_entity_type: "document",
        input_entity_id: "document-1", input_revision: "hash", input_hash: "a".repeat(64),
        output_hash: "b".repeat(64), tool_calls: [], status: "succeeded", output_count: 2,
        input_tokens: 100, output_tokens: 40, duration_ms: 250, retry_count: 0,
        sensitivity: "sensitive", error_code: null, created_at: "2026-07-26T01:00:00Z",
        finished_at: "2026-07-26T01:00:00Z", retention_until: null,
      }] }),
    }));
    renderApp("/agent-runs");
    expect(await screen.findByRole("heading", { name: "Agent 运行记录" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "profile_fact_extraction" })).toBeInTheDocument();
    expect(screen.getByText("LocalProvider · local-model")).toBeInTheDocument();
    expect(screen.getByText("这里是业务 Agent 审计记录，不是聊天 Session")).toBeInTheDocument();
  });

  it("renders final material with fact evidence and verified export", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "material-1", name: "基础简历", material_type: "resume", status: "final", version: 3,
        job_post_id: "job", job_post_version_id: "job-version", job_title: "Python 后端工程师",
        company: "示例科技", current_version_number: 2, created_at: "2026-07-23T00:00:00Z", updated_at: "2026-07-23T00:00:00Z",
        current_version: { id: "version", parent_version_id: "parent", version_number: 2, status: "final",
          title: "张三 · Python 后端工程师 · 定制简历", content_hash: "a".repeat(64), fact_set_hash: "b".repeat(64),
          created_at: "2026-07-23T00:00:00Z", finalized_at: "2026-07-23T00:00:00Z", rendered_text: "熟练使用 Python",
          blocks: [{ id: "claim-1", section: "skill", text: "熟练使用 Python", fact_snapshots: [{ id: "snapshot", fact_id: "fact", fact_version: 2, category: "skill", field_key: "technical_skills", value: "熟练使用 Python" }] }] },
        versions: [{ id: "version", parent_version_id: "parent", version_number: 2, status: "final", title: "定制简历",
          content_hash: "a".repeat(64), fact_set_hash: "b".repeat(64), created_at: "2026-07-23T00:00:00Z", finalized_at: "2026-07-23T00:00:00Z" }],
        review: { id: "review", status: "passed", schema_version: "material_review.v1", error_count: 0, warning_count: 0, created_at: "2026-07-23T00:00:00Z", findings: [] },
        export: { id: "export", format: "pdf", sha256: "c".repeat(64), size_bytes: 12000, page_count: 1,
          text_layer_ok: true, render_ok: true, extracted_text_hash: "d".repeat(64), created_at: "2026-07-23T00:00:00Z",
          download_url: "/api/v1/material-exports/export/download", preview_url: "/api/v1/material-exports/export/preview" },
      }),
    }));
    renderApp("/materials/material-1");
    expect(await screen.findByRole("heading", { name: "张三 · Python 后端工程师 · 定制简历" })).toBeInTheDocument();
    expect(screen.getByText("熟练使用 Python", { selector: "blockquote" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "下载 PDF" })).toHaveAttribute("href", "/api/v1/material-exports/export/download");
    expect(screen.getByAltText("最终 PDF 第一页渲染预览")).toBeInTheDocument();
  });

  it("renders an immutable application timeline and material snapshot", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "application-1", job_post_id: "job", job_post_version_id: "job-version",
        job_title: "Python 后端工程师", company: "示例科技", job_content_hash: "a".repeat(64),
        current_status: "interview", version: 5, material_count: 1,
        created_at: "2026-07-24T00:00:00Z", updated_at: "2026-07-24T00:00:00Z", archived_at: null,
        events: [{ id: "event-1", sequence_number: 3, event_type: "interview_scheduled",
          from_status: "submitted", to_status: "interview", occurred_at: "2026-07-25T02:00:00Z",
          note: "技术一面", source: "user", proposal_id: null, supersedes_event_id: null,
          superseded: false, created_at: "2026-07-24T00:00:00Z" }],
        material_snapshots: [{ id: "snapshot", material_draft_id: "material", resume_version_id: "version",
          material_type: "resume", title: "Python 定制简历", rendered_text: "熟练使用 Python",
          content_hash: "b".repeat(64), fact_set_hash: "c".repeat(64), export_id: "export",
          export_sha256: "d".repeat(64), created_at: "2026-07-24T00:00:00Z" }],
        proposals: [], available_final_materials: [],
      }),
    }));
    renderApp("/applications/application-1");
    expect(await screen.findByRole("heading", { name: "Python 后端工程师" })).toBeInTheDocument();
    expect(screen.getAllByText("面试").length).toBeGreaterThan(0);
    expect(screen.getByText(/技术一面/)).toBeInTheDocument();
    expect(screen.getByText("Python 定制简历 · 简历")).toBeInTheDocument();
  });

  it("renders the daily dashboard with reminders and schedule conflicts", async () => {
    const task = {
      id: "task-1", application_id: "application", job_post_id: "job", source_event_id: "event",
      task_type: "interview", title: "参加面试 · 示例科技", notes: "技术一面", status: "pending",
      priority: 10, due_at: "2026-07-24T06:00:00Z", timezone: "Asia/Shanghai", version: 1,
      company: "示例科技", job_title: "Python 后端工程师", reminders: [], conflict_ids: ["task-2"],
      created_at: "2026-07-24T00:00:00Z", updated_at: "2026-07-24T00:00:00Z",
      completed_at: null, cancelled_at: null,
    };
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/api/v1/dashboard") ? {
        generated_at: "2026-07-24T00:00:00Z", timezone: "Asia/Shanghai", today: [task],
        overdue: [], upcoming: [task], interviews: [task], pending_review_count: 2,
        unread_notification_count: 1, conflict_count: 1,
      } : String(input).includes("/api/v1/opportunities") ? { total: 1, items: [{
        id: "opportunity", company: "网易游戏雷火", batch: "27届秋招", cities: "杭州",
        careers: "后端开发", industries: "游戏", evaluation: "", application_starts_at: null,
        application_ends_at: null, announcement_url: null, application_url: "https://example.com/apply",
        triage_status: "new", version: 1, first_collected_at: "2026-07-24T00:00:00Z",
        last_collected_at: "2026-07-24T00:00:00Z", created_at: "2026-07-24T00:00:00Z",
        updated_at: "2026-07-24T00:00:00Z", sources: [], linked_jobs: [],
      }] } : { total: 1, items: [{ id: "notification", reminder_id: "reminder", notification_type: "in_app",
        title: "参加面试 · 示例科技", body: "任务将在 60 分钟后到期。", status: "unread",
        created_at: "2026-07-24T00:00:00Z", read_at: null }] },
    })));
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "今日" })).toBeInTheDocument();
    expect(await screen.findByText("网易游戏雷火 · 27届秋招")).toBeInTheDocument();
    expect((await screen.findAllByText("参加面试 · 示例科技")).length).toBeGreaterThan(0);
    expect(screen.getByText("任务将在 60 分钟后到期。")).toBeInTheDocument();
    expect(screen.getAllByText("时间冲突").length).toBeGreaterThan(0);
  });

  it("renders the read-only OpenCLI BOSS data source", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/nowcoder") ? ({
        id: "nowcoder", connector_type: "opencli_nowcoder", display_name: "牛客校招日程（OpenCLI）",
        enabled: true, search_query: "", city: "全国", result_limit: 500,
        schedule_enabled: true, schedule_times: ["09:00"], timezone: "Asia/Shanghai",
        next_scan_at: "2026-07-25T01:00:00Z", health_status: "healthy",
        last_error_code: null, last_success_at: "2026-07-24T10:00:00Z", version: 1,
        automatic_scope: "today", manual_lookback_options: [0, 7, 14, 30],
        runs: [], quarantine: [],
      }) : ({
        id: "boss", connector_type: "opencli_boss", display_name: "BOSS 直聘（OpenCLI）",
        enabled: true, profile_alias: "career", search_query: "Python", city: "上海",
        result_limit: 10, schedule_enabled: true, schedule_times: ["09:00", "18:00"],
        timezone: "Asia/Shanghai", next_scan_at: "2026-07-25T01:00:00Z",
        health_status: "healthy", last_error_code: null, last_success_at: "2026-07-24T10:00:00Z",
        version: 2, runs: [{ id: "run", trigger_type: "manual", status: "succeeded",
          discovered_count: 10, created_count: 4, updated_count: 1, duplicate_count: 5,
          quarantined_count: 0, error_code: null, started_at: "2026-07-24T10:00:00Z",
          finished_at: "2026-07-24T10:01:00Z" }], quarantine: [],
      }),
    })));
    renderApp("/data-sources");
    expect(await screen.findByRole("heading", { name: "招聘信息来源" })).toBeInTheDocument();
    expect(screen.getByText("只读安全边界")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "牛客校招日程" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("career")).toBeInTheDocument();
    expect(await screen.findByText("4 / 1 / 5 / 0")).toBeInTheDocument();
  });

  it("explains an unavailable recruitment source without exposing codes as primary text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/nowcoder") ? ({
        id: "nowcoder", connector_type: "opencli_nowcoder", display_name: "牛客校招日程（OpenCLI）",
        enabled: false, search_query: "", city: "全国", result_limit: 500,
        schedule_enabled: false, schedule_times: ["09:00"], timezone: "Asia/Shanghai",
        next_scan_at: null, health_status: "unavailable",
        last_error_code: "opencli_not_installed", last_success_at: null, version: 1,
        automatic_scope: "today", manual_lookback_options: [0, 7, 14, 30],
        runs: [], quarantine: [],
      }) : ({
        id: "boss", connector_type: "opencli_boss", display_name: "BOSS 直聘（OpenCLI）",
        enabled: false, profile_alias: "default", search_query: "", city: "全国",
        result_limit: 15, schedule_enabled: false, schedule_times: ["09:00", "18:00"],
        timezone: "Asia/Shanghai", next_scan_at: null, health_status: "unknown",
        last_error_code: null, last_success_at: null, version: 1, runs: [], quarantine: [],
      }),
    })));
    renderApp("/data-sources");
    expect(await screen.findByText("OpenCLI 未配置")).toBeInTheDocument();
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("opencli_not_installed")).not.toBeInTheDocument();
  });

  it("renders read-only IMAP settings, cursor, and mail evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string, init?: RequestInit) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/account/test") && init?.method === "POST" ? {
        status: "passed", uid_validity: "42", read_only: true,
      } : String(input).includes("/messages") ? { total: 1, items: [{
        id: "mail-1", uid: 7, sender: "HR <hr@example.com>", subject: "测试公司面试通知",
        sent_at: "2026-07-24T02:00:00Z", classification: "recruiting", event_kind: "interview",
        extracted: { company: "测试公司" }, evidence_excerpt: "岗位：Python工程师，面试时间已安排。",
        body_hash: "hash", body_fetched: true, attachments: [{ filename: "invite.pdf", content_type: "application/pdf", size_bytes: 1024 }],
        candidate: { id: "candidate", application_id: "application", match_confidence: 1,
          match_reason: "公司/职位文本与现有申请确定性匹配。", status: "proposal_created",
          proposal_id: "proposal", created_at: "2026-07-24T02:00:00Z", updated_at: "2026-07-24T02:00:00Z" },
        created_at: "2026-07-24T02:00:00Z",
      }] } : {
        configured: true, enabled: true, health_status: "healthy", last_error_code: null,
        last_success_at: "2026-07-24T02:00:00Z", next_sync_at: "2026-07-24T02:10:00Z",
        account: { id: "account", email_address: "candidate@example.com", host: "imap.example.com",
          port: 993, username: "candidate@example.com", username_masked: "ca***@example.com",
          folder: "INBOX", initial_lookback_days: 30, poll_interval_minutes: 10, credential_configured: true },
        cursor: { uid_validity: "42", last_committed_uid: 7 }, runs: [],
      },
    })));
    renderApp("/message-center");
    expect(await screen.findByRole("heading", { name: "招聘邮件" })).toBeInTheDocument();
    expect(screen.getByText("严格只读边界")).toBeInTheDocument();
    expect(await screen.findByText("测试公司面试通知")).toBeInTheDocument();
    expect(screen.getByText("已创建待确认进度")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("app-password")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "测试只读连接" }));
    expect(await screen.findByText("只读邮箱连接正常，可以开始同步最近 30 天内的已读和未读邮件。")).toBeInTheDocument();
  });
});
