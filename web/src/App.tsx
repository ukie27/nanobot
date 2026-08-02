import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ApiError, cancelBackgroundJob, getBackgroundJobs, getOnboardingStatus, getSystemStatus, retryBackgroundJob } from "./api";
import { ApplicationDetailPage, ApplicationReviewPage, ApplicationsPage } from "./ApplicationPages";
import { JobDetailPage, JobPoolPage } from "./JobPages";
import { InterviewCenterPage, InterviewDetailPage } from "./InterviewPages";
import { JobMaterialsPage, MaterialDetailPage, MaterialsPage, ResumeDetailPage, ResumeDiffPage } from "./MaterialPages";
import { MessageCenterPage } from "./MailPages";
import { OpportunityPage } from "./OpportunityPages";
import { DocumentsPage, ManualFactPage, ProfilePage } from "./ProfilePages";
import { DashboardPage, TasksPage } from "./TaskPages";
import { formatChinaTime } from "./time";
import { DataSourcesPage } from "./ConnectorPages";
import { WorkspacePage } from "./WorkspacePage";
import { AgentRunsPage, ReviewBundlePage, ReviewCenterPage } from "./RuntimePages";
import { SettingsPage } from "./SettingsPage";
import { OnboardingPage } from "./OnboardingPage";
import { HelpPage } from "./HelpPage";

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark" aria-hidden="true">C</div>
      <div>
        <strong>CareerConsole</strong>
        <span>本地求职工作台</span>
      </div>
    </div>
  );
}

type NavigationGroupProps = {
  label: string;
  paths: string[];
  children: ReactNode;
  onNavigate: () => void;
};

function NavigationGroup({ label, paths, children, onNavigate }: NavigationGroupProps) {
  const location = useLocation();
  const active = paths.some(path => location.pathname === path || location.pathname.startsWith(`${path}/`));
  return (
    <details className="nav-group" open={active}>
      <summary className={active ? "active" : ""}>{label}</summary>
      <div className="nav-group-links" onClick={onNavigate}>{children}</div>
    </details>
  );
}

function ProductLayout() {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const location = useLocation();
  const jobMaterialsMatch = location.pathname.match(/^\/job-posts\/([^/]+)\/materials$/);
  const contextualSubpage = location.pathname.startsWith("/profile/")
    ? { label: "返回个人资料", to: "/profile" }
    : location.pathname.startsWith("/resumes/")
      ? { label: "返回简历库", to: "/materials" }
      : jobMaterialsMatch
        ? { label: "返回岗位详情", to: `/job-posts/${jobMaterialsMatch[1]}` }
        : null;
  const closeNavigation = () => setMobileNavigationOpen(false);
  return (
    <div className={`app-shell ${contextualSubpage ? "profile-subpage-shell" : ""}`}>
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      {!contextualSubpage && <header className="mobile-header">
        <Brand />
        <button
          type="button"
          className="mobile-menu-button secondary"
          aria-expanded={mobileNavigationOpen}
          aria-controls="primary-sidebar"
          onClick={() => setMobileNavigationOpen(open => !open)}
        >
          {mobileNavigationOpen ? "关闭" : "菜单"}
        </button>
      </header>}
      {contextualSubpage && <header className="profile-subpage-header">
        <Brand />
        <NavLink className="back-link" end to={contextualSubpage.to}>{contextualSubpage.label}</NavLink>
      </header>}
      {!contextualSubpage && mobileNavigationOpen && <button className="sidebar-backdrop" aria-label="关闭导航" onClick={closeNavigation} />}
      {!contextualSubpage && <aside id="primary-sidebar" className={`sidebar ${mobileNavigationOpen ? "mobile-open" : ""}`}>
        <div className="desktop-brand"><Brand /></div>
        <p className="navigation-intro">按求职任务组织功能。当前要做什么，就从对应分组进入。</p>
        <nav aria-label="主导航">
          <NavLink to="/dashboard" onClick={closeNavigation}>今日</NavLink>
          <NavigationGroup label="机会" paths={["/opportunities", "/job-posts"]} onNavigate={closeNavigation}>
            <NavLink to="/opportunities">岗位推荐</NavLink>
            <NavLink to="/job-posts">目标岗位</NavLink>
          </NavigationGroup>
          <NavigationGroup label="申请" paths={["/workspace", "/applications", "/tasks", "/interviews"]} onNavigate={closeNavigation}>
            <NavLink to="/workspace">申请总览</NavLink>
            <NavLink to="/applications">申请进度</NavLink>
            <NavLink to="/tasks">任务与日程</NavLink>
            <NavLink to="/interviews">面试中心</NavLink>
          </NavigationGroup>
          <NavigationGroup label="个人资料" paths={["/profile", "/materials"]} onNavigate={closeNavigation}>
            <NavLink to="/profile">个人档案</NavLink>
            <NavLink to="/materials">我的简历</NavLink>
          </NavigationGroup>
          <NavLink to="/message-center" onClick={closeNavigation}>招聘邮件</NavLink>
          <NavLink to="/reviews" onClick={closeNavigation}>待我处理</NavLink>
          <NavLink to="/agent-runs" onClick={closeNavigation}>智能功能记录</NavLink>
          <NavLink to="/settings" onClick={closeNavigation}>设置</NavLink>
          <NavLink to="/help" onClick={closeNavigation}>帮助</NavLink>
        </nav>
      </aside>}
      <main className={`content ${contextualSubpage ? "profile-subpage-content" : ""}`} id="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/profile/import" element={<DocumentsPage />} />
          <Route path="/profile/reviews" element={<Navigate to="/profile" replace />} />
          <Route path="/profile/manual" element={<ManualFactPage />} />
          <Route path="/documents" element={<Navigate to="/profile/import" replace />} />
          <Route path="/review" element={<Navigate to="/reviews?category=profile" replace />} />
          <Route path="/reviews" element={<ReviewCenterPage />} />
          <Route path="/reviews/:id" element={<ReviewBundlePage />} />
          <Route path="/opportunities" element={<OpportunityPage />} />
          <Route path="/job-posts" element={<JobPoolPage />} />
          <Route path="/job-posts/:id" element={<JobDetailPage />} />
          <Route path="/materials" element={<MaterialsRoute />} />
          <Route path="/job-posts/:id/materials" element={<JobMaterialsPage />} />
          <Route path="/resumes/:id" element={<ResumeDetailPage />} />
          <Route path="/materials/:id" element={<MaterialDetailPage />} />
          <Route path="/resume-diff/:fromVersionId/:toVersionId" element={<ResumeDiffPage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/applications/:id" element={<ApplicationDetailPage />} />
          <Route path="/application-review" element={<ApplicationReviewPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/data-sources" element={<Navigate to="/settings?section=sources" replace />} />
          <Route path="/message-center" element={<MessageCenterPage />} />
          <Route path="/interviews" element={<InterviewCenterPage />} />
          <Route path="/interviews/:id" element={<InterviewDetailPage />} />
          <Route path="/agent-runs" element={<AgentRunsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}

function MaterialsRoute() {
  const location = useLocation();
  const jobId = new URLSearchParams(location.search).get("jobId");
  return jobId
    ? <Navigate to={`/job-posts/${encodeURIComponent(jobId)}/materials`} replace />
    : <MaterialsPage />;
}

function NotFoundPage() {
  return <section className="not-found">
    <span>404</span>
    <h1>这个页面不存在</h1>
    <p>链接可能已经变更。返回今日页面继续，或从菜单选择目标功能。</p>
    <NavLink className="download-button" to="/dashboard">返回今日</NavLink>
  </section>;
}

function PageError({ error }: { error: Error }) {
  const apiError = error instanceof ApiError ? error : null;
  return (
    <section className="notice error" role="alert">
      <strong>无法读取本地服务</strong>
      <p>{error.message}</p>
      {apiError?.correlationId && <code>关联 ID：{apiError.correlationId}</code>}
    </section>
  );
}

function StatusPage() {
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: getSystemStatus,
    refetchInterval: 15_000,
  });

  return (
    <>
      <header className="page-header">
        <div><p className="eyebrow">本地服务诊断</p><h1>运行状态</h1></div>
        <span className={`health-pill ${query.data?.health === "ready" ? "ok" : ""}`}>
          {query.isLoading ? "检查中" : query.data?.health === "ready" ? "服务就绪" : "需要处理"}
        </span>
      </header>
      {query.error && <PageError error={query.error} />}
      {query.data && (
        <>
          <section className="metric-grid">
            <article><span>应用版本</span><strong>{query.data.version}</strong><small>CareerConsole 本地服务</small></article>
            <article><span>数据库</span><strong>{query.data.database === "ok" ? "正常" : "异常"}</strong><small>SQLite · WAL</small></article>
            <article><span>数据库版本</span><strong>{query.data.database_revision ?? "—"}</strong><small>目标版本 {query.data.expected_revision}</small></article>
            <article><span>启动时恢复</span><strong>{query.data.recovered_jobs_at_startup}</strong><small>异常中断的后台任务</small></article>
          </section>
          <section className="panel">
            <div className="panel-heading"><div><p className="eyebrow">数据目录</p><h2>本地数据位置</h2></div><span>仅保存在本机</span></div>
            <dl className="path-list"><div><dt>数据目录</dt><dd>{query.data.paths.data_dir}</dd></div></dl>
            <details className="audit-details"><summary>查看内部存储位置</summary><dl className="path-list">
              <div><dt>数据库</dt><dd>{query.data.paths.database}</dd></div>
              <div><dt>日志</dt><dd>{query.data.paths.logs}</dd></div>
              <div><dt>备份</dt><dd>{query.data.paths.backups}</dd></div>
            </dl></details>
          </section>
        </>
      )}
    </>
  );
}

function JobsPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["background-jobs"], queryFn: getBackgroundJobs });
  const retry = useMutation({ mutationFn: retryBackgroundJob, onSuccess: async () => { await client.invalidateQueries({ queryKey: ["background-jobs"] }); } });
  const cancel = useMutation({ mutationFn: cancelBackgroundJob, onSuccess: async () => { await client.invalidateQueries({ queryKey: ["background-jobs"] }); } });
  const jobTypeLabels: Record<string, string> = {
    connector_sync: "数据来源同步",
    mail_sync: "招聘邮箱同步",
    document_parse: "资料解析",
    agent_task: "智能分析",
    material_generation: "申请材料生成",
    notification_dispatch: "通知发送",
  };
  const jobStatusLabels: Record<string, string> = {
    pending: "等待处理",
    running: "处理中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return (
    <>
      <header className="page-header">
        <div><p className="eyebrow">故障处理</p><h1>后台任务</h1></div>
        <button type="button" className="secondary" onClick={() => void query.refetch()}>刷新</button>
      </header>
      {query.error && <PageError error={query.error} />}
      {query.data?.total === 0 && (
        <section className="empty-state">
          <div className="empty-icon">✓</div><h2>任务队列已就绪</h2>
          <p>当前没有等待处理的同步、解析或生成任务。</p>
        </section>
      )}
      {query.data && query.data.total > 0 && (
        <section className="panel table-wrap"><table><thead><tr><th>类型</th><th>状态</th><th>尝试次数</th><th>创建时间</th></tr></thead>
          <tbody>{query.data.items.map((job) => <tr key={job.id}><td>{jobTypeLabels[job.job_type] ?? job.job_type}</td><td>{jobStatusLabels[job.status] ?? job.status}</td><td>{job.attempt_count}/{job.max_attempts}</td><td>{formatChinaTime(job.created_at)}（北京时间）</td><td>{["failed", "cancelled"].includes(job.status) && <button onClick={() => retry.mutate(job.id)}>重试</button>}{["pending", "running"].includes(job.status) && <button className="danger" onClick={() => cancel.mutate(job.id)}>取消</button>}</td></tr>)}</tbody>
        </table></section>
      )}
    </>
  );
}

export default function App() {
  const onboarding = useQuery({ queryKey: ["onboarding"], queryFn: getOnboardingStatus, staleTime: 0 });
  if (onboarding.isLoading) return <main className="startup-screen"><p>正在启动 CareerConsole…</p></main>;
  if (onboarding.data?.completed === false) return <OnboardingPage />;
  return <ProductLayout />;
}
