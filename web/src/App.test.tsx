import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => vi.restoreAllMocks());

function renderApp(path = "/status") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Career app shell", () => {
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
});
