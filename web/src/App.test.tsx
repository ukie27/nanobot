import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
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
    expect(screen.getByAltText("Final PDF 第一页渲染预览")).toBeInTheDocument();
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
    expect(screen.getByText("Python 定制简历 · resume")).toBeInTheDocument();
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
      } : { total: 1, items: [{ id: "notification", reminder_id: "reminder", notification_type: "in_app",
        title: "参加面试 · 示例科技", body: "任务将在 60 分钟后到期。", status: "unread",
        created_at: "2026-07-24T00:00:00Z", read_at: null }] },
    })));
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "今日 Dashboard" })).toBeInTheDocument();
    expect((await screen.findAllByText("参加面试 · 示例科技")).length).toBeGreaterThan(0);
    expect(screen.getByText("任务将在 60 分钟后到期。")).toBeInTheDocument();
    expect(screen.getAllByText("时间冲突").length).toBeGreaterThan(0);
  });

  it("renders the read-only OpenCLI BOSS data source", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
    }));
    renderApp("/data-sources");
    expect(await screen.findByRole("heading", { name: "数据来源" })).toBeInTheDocument();
    expect(screen.getByText("只读安全边界")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("career")).toBeInTheDocument();
    expect(await screen.findByText("4 / 1 / 5 / 0")).toBeInTheDocument();
  });

  it("renders read-only IMAP settings, cursor, and mail evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("/messages") ? { total: 1, items: [{
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
    expect(await screen.findByRole("heading", { name: "消息中心" })).toBeInTheDocument();
    expect(screen.getByText("严格只读边界")).toBeInTheDocument();
    expect(await screen.findByText("测试公司面试通知")).toBeInTheDocument();
    expect(screen.getByText("已创建待确认 Proposal")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("app-password")).not.toBeInTheDocument();
  });
});
