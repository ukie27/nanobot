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
    expect(screen.getByRole("link", { name: "跳到主要内容" })).toHaveAttribute("href", "#main-content");
    const menuButton = screen.getByRole("button", { name: "菜单" });
    expect(menuButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(menuButton);
    expect(screen.getByRole("button", { name: "关闭" })).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(screen.getByRole("button", { name: "菜单" })).toHaveAttribute("aria-expanded", "false");
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
    expect(screen.getByRole("combobox", { name: "设置分类" })).toHaveValue("general");

    fireEvent.click(screen.getByRole("button", { name: "备份与迁移" }));
    expect(screen.getByRole("heading", { name: "导入与导出" })).toBeInTheDocument();
    expect(screen.getByText("防止压缩包中的路径越界")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "AI 服务" }));
    expect(await screen.findByText("主模型 · gpt-main · 凭据已配置")).toBeInTheDocument();
    expect(screen.getByText("材料撰写")).toBeInTheDocument();
    expect(screen.getByText("材料复核")).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("已安全保存；留空保持不变").find(element => element.getAttribute("name") === "api_key")).toHaveValue("");
    expect(screen.queryByDisplayValue("career-console:workspace:provider:main:api-key")).not.toBeInTheDocument();
    expect(await screen.findByText("主模型 · 通过")).toBeInTheDocument();
    expect(screen.queryByLabelText("Provider ID")).not.toBeInTheDocument();
    for (const summary of screen.getAllByText("高级连接设置")) {
      expect(summary.closest("details")).not.toHaveAttribute("open");
    }
    const taskAssignmentSummary = screen.getByText("按任务选择不同模型");
    expect(taskAssignmentSummary.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(taskAssignmentSummary);
    fireEvent.click(screen.getByRole("button", { name: "保存高级分配" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/configuration/agents",
        expect.objectContaining({ method: "PUT" }),
      );
    });
    expect(await screen.findByText("高级模型分配已保存。重启服务后应用新的 AI 运行配置。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "消息通知" }));
    expect(screen.getByRole("heading", { name: "QQ 通知" })).toBeInTheDocument();
    expect(await screen.findByText("凭据已配置")).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("已安全保存；留空保持不变").find(element => element.getAttribute("name") === "secret")).toHaveValue("");
    expect(screen.queryByDisplayValue("qq-secret-value")).not.toBeInTheDocument();
    expect(await screen.findByText(/c2c:sha256:123456789abc/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "高级设置" }));
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
    expect(screen.queryByText("skill · v2")).not.toBeInTheDocument();
    const factRecord = screen.getByText("查看来源与记录").closest("details");
    expect(factRecord).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("查看来源与记录"));
    expect(factRecord).toHaveAttribute("open");
    expect(screen.getByText("记录字段：skill · 版本 2")).toBeInTheDocument();
  });

  it("keeps document processing metadata behind a user-facing disclosure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        total: 1,
        items: [{
          id: "document-1", file_name: "项目经历.txt", parser_name: "pasted_text_v1",
          size_bytes: 1024, fact_source_count: 3, sha256: "a".repeat(64),
          created_at: "2026-07-27T00:00:00Z",
        }],
      }),
    }));
    renderApp("/documents");
    expect(await screen.findByRole("heading", { name: "导入资料" })).toBeInTheDocument();
    expect(screen.getByLabelText("选择文件并导入")).toBeInTheDocument();
    expect(await screen.findByText("1.0 KB · 已提取 3 条内容来源")).toBeInTheDocument();
    const importRecord = screen.getByText("查看导入记录").closest("details");
    expect(importRecord).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("查看导入记录"));
    expect(importRecord).toHaveAttribute("open");
    expect(screen.getByText("处理方式：粘贴文本")).toBeInTheDocument();
  });

  it("renders versioned jobs with hard-gate status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        total: 1,
        items: [{
          id: "job-1", company: "示例科技", title: "Python 后端工程师", location: "上海",
          employment_type: "全职", work_mode: "混合办公", deadline_at: null, status: "active",
          version: 2, requirement_count: 4, created_at: "2026-07-23T00:00:00Z", updated_at: "2026-07-23T00:00:00Z",
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
    expect(heading.closest("a")).not.toHaveTextContent("v2");
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
        entity_subtype: null, can_resolve_inline: false,
        created_at: "2026-07-26T01:00:00Z", updated_at: "2026-07-26T01:00:00Z",
        resolved_at: null, resolution: null, resolution_reason: null, resolved_by: null,
      }] }),
    }));
    renderApp("/reviews");
    expect(await screen.findByRole("heading", { name: "审查中心" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "确认职业事实：Python" })).toBeInTheDocument();
    expect(screen.getByText("智能分析只会生成待确认建议")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看并处理" })).toHaveAttribute("href", "/review");
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
    expect(await screen.findByRole("heading", { name: "智能功能记录" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "职业事实提取" })).toBeInTheDocument();
    expect(screen.getByText("LocalProvider · local-model")).toBeInTheDocument();
    expect(screen.getByText("这里记录智能功能的执行结果")).toBeInTheDocument();
    expect(screen.getByText("查看技术审计信息").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("重试次数")).toBeInTheDocument();
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

  it("guides users to prepare a final material before submission", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/application-review-tasks") ? { total: 0, items: [] } : ({
        id: "application-ready", job_post_id: "job-ready", job_post_version_id: "job-version",
        job_title: "Python 后端工程师", company: "示例科技", job_content_hash: "a".repeat(64),
        current_status: "ready_to_apply", version: 2, material_count: 0,
        created_at: "2026-07-24T00:00:00Z", updated_at: "2026-07-24T00:00:00Z", archived_at: null,
        events: [], material_snapshots: [], proposals: [], mail_evidence: [], available_final_materials: [],
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/applications/application-ready");

    expect(await screen.findByText("还没有可用于投递的定稿材料")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "准备并定稿材料" })).toHaveAttribute("href", "/materials?jobId=job-ready");
    expect(screen.getByRole("button", { name: "确认投递并保存材料" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/submit"))).toBe(false);
  });

  it("requires selecting at least one final material before submission", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/application-review-tasks") ? { total: 0, items: [] } : ({
        id: "application-ready", job_post_id: "job-ready", job_post_version_id: "job-version",
        job_title: "Python 后端工程师", company: "示例科技", job_content_hash: "a".repeat(64),
        current_status: "ready_to_apply", version: 2, material_count: 0,
        created_at: "2026-07-24T00:00:00Z", updated_at: "2026-07-24T00:00:00Z", archived_at: null,
        events: [], material_snapshots: [], proposals: [], mail_evidence: [],
        available_final_materials: [{ id: "material-final", name: "岗位定制简历", material_type: "resume" }],
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/applications/application-ready");

    fireEvent.click(await screen.findByRole("button", { name: "确认投递并保存材料" }));
    expect(await screen.findByText("请至少选择一份定稿材料。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/submit"))).toBe(false);
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
    expect(await screen.findByRole("heading", { name: "今日行动台" })).toBeInTheDocument();
    expect(screen.getByText("建议下一步")).toBeInTheDocument();
    expect(await screen.findByText("网易游戏雷火 · 27届秋招")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "处理待确认内容" })).toBeInTheDocument();
    expect(screen.getByText("2 项内容需要你决定后才能进入正式记录。")).toBeInTheDocument();
    expect((await screen.findAllByText("参加面试 · 示例科技")).length).toBeGreaterThan(0);
    expect(screen.getByText("任务将在 60 分钟后到期。")).toBeInTheDocument();
    expect(screen.getAllByText("时间冲突").length).toBeGreaterThan(0);
  });

  it("renders the read-only OpenCLI BOSS data source", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/connectors/opencli") ? ({
        executable: null, resolved_executable: null, installed: false,
      }) : String(input).includes("/mail/account") ? ({
        configured: false, enabled: false, health_status: "unconfigured", last_error_code: null,
        last_success_at: null, next_sync_at: null, account: null,
        cursor: { uid_validity: null, last_committed_uid: 0 }, runs: [],
      }) : String(input).includes("/configuration/changes") ? ({
        total: 0, items: [],
      }) : String(input).endsWith("/api/v1/configuration") ? ({
        activation_status: "active",
      }) : String(input).includes("/nowcoder") ? ({
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
    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "招聘与邮箱配置" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "牛客校招日程" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("career")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "立即搜索" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主动获取" })).not.toBeInTheDocument();
  });

  it("explains an unavailable recruitment source without exposing codes as primary text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/connectors/opencli") ? ({
        executable: null, resolved_executable: null, installed: false,
      }) : String(input).includes("/mail/account") ? ({
        configured: false, enabled: false, health_status: "unconfigured", last_error_code: null,
        last_success_at: null, next_sync_at: null, account: null,
        cursor: { uid_validity: null, last_committed_uid: 0 }, runs: [],
      }) : String(input).includes("/configuration/changes") ? ({
        total: 0, items: [],
      }) : String(input).endsWith("/api/v1/configuration") ? ({
        activation_status: "active",
      }) : String(input).includes("/nowcoder") ? ({
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
    expect(screen.queryByLabelText("邮箱地址")).not.toBeInTheDocument();
    expect(await screen.findByText("测试公司面试通知")).toBeInTheDocument();
    expect(screen.getByText("已创建待确认进度")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("app-password")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(await screen.findByText("只读邮箱连接正常，可以开始同步最近 30 天内的已读和未读邮件。")).toBeInTheDocument();
  });

  it("blocks material and application actions when a job has no extracted requirements", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => {
      if (input === "/api/v1/job-posts/job-empty") return Promise.resolve({ ok: true, json: async () => ({
        id: "job-empty", company: "示例科技", title: "信息不完整岗位", location: null,
        employment_type: null, work_mode: null, deadline_at: null, status: "active",
        version: 1, requirement_count: 0, latest_analysis: null,
        created_at: "2026-07-28T00:00:00Z", updated_at: "2026-07-28T00:00:00Z",
        duplicate: false, created: true, target_audience: null, raw_text: "仅有岗位标题",
        content_hash: "a".repeat(64), requirements: [], analyses: [],
        versions: [{ id: "version", version_number: 1, content_hash: "a".repeat(64), created_at: "2026-07-28T00:00:00Z" }],
        sources: [], opportunity_ids: [],
      }) });
      if (input.includes("/agent-fit-proposals")) return Promise.resolve({ ok: true, json: async () => ({ total: 0, items: [] }) });
      if (input.includes("/resume-directions")) return Promise.resolve({ ok: true, json: async () => ({ proposals: [], selections: [] }) });
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }));
    renderApp("/job-posts/job-empty");
    expect(await screen.findByText("尚无法判断岗位是否适合")).toBeInTheDocument();
    expect(screen.getByText("尚无法判断")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新分析岗位" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "准备申请材料" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始跟踪申请" })).not.toBeInTheDocument();
  });

  it("does not render an application creation submit when no analyzed jobs are available", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/applications"
        ? { total: 0, items: [] }
        : input === "/api/v1/job-posts"
          ? { total: 1, items: [{ id: "job", company: "示例", title: "待分析岗位", requirement_count: 0, latest_analysis: null }] }
          : {},
    })));
    renderApp("/applications");
    expect(await screen.findByText("没有可创建的申请")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始跟踪" })).not.toBeInTheDocument();
  });

  it("explains why material generation is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/job-posts"
        ? { total: 1, items: [{ id: "job", company: "示例", title: "待分析岗位", requirement_count: 0, latest_analysis: null }] }
        : input === "/api/v1/materials"
          ? { total: 0, items: [] }
          : input === "/api/v1/resumes"
            ? { total: 0, items: [] }
            : { total: 0, items: [], proposals: [], selections: [] },
    })));
    renderApp("/materials");
    expect(await screen.findByRole("heading", { name: "生成草稿" })).toBeInTheDocument();
    expect(screen.getByText("请先选择岗位。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成草稿" })).toBeDisabled();
  });

  it("prioritizes confirming a ready-to-apply application on the dashboard", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/dashboard"
        ? { generated_at: "2026-07-28T00:00:00Z", timezone: "Asia/Shanghai", today: [], overdue: [], upcoming: [], interviews: [], pending_review_count: 0, unread_notification_count: 0, conflict_count: 0 }
        : input.startsWith("/api/v1/opportunities")
          ? { total: 0, items: [] }
          : input === "/api/v1/applications"
            ? { total: 1, items: [{ id: "application", job_post_id: "job", company: "示例科技", job_title: "后端工程师", current_status: "ready_to_apply" }] }
            : input === "/api/v1/materials"
              ? { total: 0, items: [] }
              : input === "/api/v1/profile"
                ? { fact_counts: { confirmed: 3 } }
                : { total: 0, items: [] },
    })));
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "确认实际投递" })).toBeInTheDocument();
    expect(screen.getByText("示例科技 · 后端工程师 已具备定稿材料。")).toBeInTheDocument();
  });

  it.each([
    ["disabled", { enabled: false, health_status: "unknown", last_success_at: null }, "尚未启用牛客招聘来源"],
    ["unhealthy", { enabled: true, health_status: "unavailable", last_success_at: null }, "牛客招聘来源当前不可用"],
    ["never", { enabled: true, health_status: "healthy", last_success_at: null }, "今天还没有同步招聘信息"],
    ["empty today", { enabled: true, health_status: "healthy", last_success_at: "2026-07-28T01:00:00Z" }, "今天暂时没有新机会"],
  ])("renders the %s recruitment empty state", async (_name, connector, expected) => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/opportunities"
        ? { total: 0, items: [] }
        : input === "/api/v1/connectors/nowcoder"
          ? { ...connector, runs: [], quarantine: [] }
          : {},
    })));
    renderApp("/opportunities");
    expect(await screen.findByRole("heading", { name: expected })).toBeInTheDocument();
  });

  it("renders a distinct empty state for an opportunity filter with no matches", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/opportunities"
        ? { total: 1, items: [{ id: "item", company: "示例", batch: "秋招", cities: "", careers: "", industries: "", evaluation: "", application_starts_at: null, application_ends_at: null, announcement_url: null, application_url: "https://example.com", triage_status: "new", version: 1, first_collected_at: "2026-07-28T00:00:00Z", last_collected_at: "2026-07-28T00:00:00Z", created_at: "2026-07-28T00:00:00Z", updated_at: "2026-07-28T00:00:00Z", sources: [], linked_jobs: [] }] }
        : input === "/api/v1/opportunities?triage_status=ignored"
          ? { total: 0, items: [] }
          : input === "/api/v1/connectors/nowcoder"
            ? { enabled: true, health_status: "healthy", last_success_at: "2026-07-28T01:00:00Z", runs: [], quarantine: [] }
            : {},
    })));
    renderApp("/opportunities");
    fireEvent.click(await screen.findByRole("button", { name: "已忽略" }));
    expect(await screen.findByRole("heading", { name: "当前筛选下没有招聘机会" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "清除筛选" })).toBeInTheDocument();
  });

  it("opens settings directly on data sources and keeps mail account fields out of daily mail", async () => {
    const mail = { configured: false, enabled: false, health_status: "unconfigured", last_error_code: null, last_success_at: null, next_sync_at: null, account: null, cursor: { uid_validity: null, last_committed_uid: 0 }, runs: [] };
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/connectors/opencli"
        ? { executable: null, resolved_executable: null, installed: false }
        : input === "/api/v1/connectors/nowcoder"
          ? { enabled: false, health_status: "unknown", last_success_at: null, runs: [], quarantine: [], schedule_times: ["09:00"], manual_lookback_options: [0, 7, 14, 30] }
          : input === "/api/v1/connectors/boss"
            ? { enabled: false, health_status: "unknown", last_success_at: null, runs: [], quarantine: [], schedule_times: ["09:00"] }
            : input === "/api/v1/mail/account"
              ? mail
              : input === "/api/v1/mail/messages"
                ? { total: 0, items: [] }
                : input === "/api/v1/applications"
                  ? { total: 0, items: [] }
                  : {},
    })));
    const settings = renderApp("/settings?section=sources");
    expect(await screen.findByRole("combobox", { name: "设置分类" })).toHaveValue("sources");
    expect(screen.getByRole("heading", { name: "招聘与邮箱配置" })).toBeInTheDocument();
    expect(screen.getByText("邮箱设置")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "立即同步" })).not.toBeInTheDocument();
    settings.unmount();

    renderApp("/message-center");
    expect(await screen.findByRole("heading", { name: "招聘邮件" })).toBeInTheDocument();
    expect(screen.queryByText("邮箱设置")).not.toBeInTheDocument();
    expect(screen.queryByText("IMAP TLS 主机")).not.toBeInTheDocument();
  });

  it("defaults interviews to tomorrow at 10:00 China time and explains missing applications", async () => {
    vi.setSystemTime(new Date("2026-07-28T02:00:00Z"));
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/interviews" || input === "/api/v1/interview-feedback" || input === "/api/v1/improvement-items"
        ? { total: 0, items: [] }
        : input === "/api/v1/applications"
          ? { total: 0, items: [] }
          : {},
    })));
    renderApp("/interviews");
    expect(await screen.findByDisplayValue("2026-07-29T10:00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建面试" })).toBeDisabled();
    expect(screen.getByText("还没有申请记录，请先在“申请总览”建立申请进度。")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("hides empty scheduler heartbeats and does not offer QQ deletion before configuration", async () => {
    const configuration = {
      schema_version: "career-console.configuration.v1", revision: 1, active_revision: 1,
      activation_status: "active", configuration: {
        general: { locale: "zh-CN", timezone: "Asia/Shanghai", date_format: "yyyy-MM-dd", open_browser_on_start: false },
        appearance: { density: "comfortable", reduce_motion: false },
        runtime: { log_level: "INFO", log_retention_days: 14, agent_trace_retention_days: 30, job_lease_seconds: 60, max_document_mb: 10 },
        privacy: { diagnostics_metadata_enabled: true, redact_sensitive_logs: true, local_only_network_binding: true },
        providers: {}, agents: { tasks: {} }, connectors: {},
        channels: { qq: { enabled: false, app_id: "", notification_targets: [], event_subscriptions: [], message_format: "plain", outbound_only: true, quiet_hours: { enabled: false, start: "22:00", end: "08:00", timezone: "Asia/Shanghai" } }, send_max_retries: 3 },
        scheduler: { enabled: true, poll_seconds: 60, reminders_enabled: true, connector_jobs_enabled: true, profile_maintenance_enabled: true, profile_maintenance_time: "21:30", channel_dispatch_enabled: true },
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => input === "/api/v1/configuration"
        ? configuration
        : input === "/api/v1/scheduler/runs"
          ? { total: 1, items: [{ id: "heartbeat", trigger_type: "interval", status: "completed", counters: { reminders_triggered: 0, connector_runs_processed: 0, channel_sent: 0 }, error_codes: [], started_at: "2026-07-28T00:00:00Z", finished_at: "2026-07-28T00:00:01Z" }] }
          : input === "/api/v1/channels/qq"
            ? { enabled: false, app_id: "", notification_targets: [], event_subscriptions: [], message_format: "plain", outbound_only: true, quiet_hours: { enabled: false, start: "22:00", end: "08:00", timezone: "Asia/Shanghai" }, has_secret: false, configuration_revision: 1 }
            : input === "/api/v1/channels/deliveries"
              ? { total: 0, items: [] }
              : { total: 0, items: [] },
    })));
    const scheduler = renderApp("/settings?section=automation");
    expect(await screen.findByText("自动任务服务运行正常")).toBeInTheDocument();
    expect(screen.queryByText("定时检查 · 已完成")).not.toBeInTheDocument();
    scheduler.unmount();

    renderApp("/settings?section=notifications");
    expect(await screen.findByRole("heading", { name: "QQ 通知" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除配置" })).not.toBeInTheDocument();
  });
});
