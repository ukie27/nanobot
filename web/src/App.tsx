import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { ApiError, cancelBackgroundJob, getBackgroundJobs, getSystemStatus, retryBackgroundJob } from "./api";
import { ApplicationDetailPage, ApplicationReviewPage, ApplicationsPage } from "./ApplicationPages";
import { JobDetailPage, JobPoolPage } from "./JobPages";
import { InterviewCenterPage, InterviewDetailPage } from "./InterviewPages";
import { MaterialDetailPage, MaterialsPage } from "./MaterialPages";
import { MessageCenterPage } from "./MailPages";
import { DocumentsPage, ProfilePage, ReviewPage } from "./ProfilePages";
import { DashboardPage, TasksPage } from "./TaskPages";
import { formatChinaTime } from "./time";
import { DataSourcesPage } from "./ConnectorPages";
import { WorkspacePage } from "./WorkspacePage";

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark" aria-hidden="true">N</div>
      <div>
        <strong>Nanobot Career</strong>
        <span>本地求职工作台</span>
      </div>
    </div>
  );
}

function Layout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav aria-label="主导航">
          <NavLink to="/dashboard">今日概览</NavLink>
          <NavLink to="/workspace">全链路工作区</NavLink>
          <NavLink to="/profile">职业档案</NavLink>
          <NavLink to="/documents">简历导入</NavLink>
          <NavLink to="/review">事实审查</NavLink>
          <NavLink to="/job-posts">岗位池</NavLink>
          <NavLink to="/materials">申请材料</NavLink>
          <NavLink to="/applications">申请看板</NavLink>
          <NavLink to="/application-review">事件审查</NavLink>
          <NavLink to="/tasks">任务日程</NavLink>
          <NavLink to="/data-sources">数据来源</NavLink>
          <NavLink to="/message-center">消息中心</NavLink>
          <NavLink to="/interviews">面试中心</NavLink>
          <NavLink to="/status">运行状态</NavLink>
          <NavLink to="/jobs">后台任务</NavLink>
        </nav>
        <div className="phase-note">
          <span>当前阶段</span>
          <strong>Part 9 · 集成与治理</strong>
          <p>全链路搜索、统一审查、备份恢复和个人数据治理。</p>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/job-posts" element={<JobPoolPage />} />
          <Route path="/job-posts/:id" element={<JobDetailPage />} />
          <Route path="/materials" element={<MaterialsPage />} />
          <Route path="/materials/:id" element={<MaterialDetailPage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/applications/:id" element={<ApplicationDetailPage />} />
          <Route path="/application-review" element={<ApplicationReviewPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
          <Route path="/message-center" element={<MessageCenterPage />} />
          <Route path="/interviews" element={<InterviewCenterPage />} />
          <Route path="/interviews/:id" element={<InterviewDetailPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="*" element={<Navigate to="/status" replace />} />
        </Routes>
      </main>
    </div>
  );
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
        <div><p className="eyebrow">SYSTEM OVERVIEW</p><h1>运行状态</h1></div>
        <span className={`health-pill ${query.data?.health === "ready" ? "ok" : ""}`}>
          {query.isLoading ? "检查中" : query.data?.health === "ready" ? "服务就绪" : "需要处理"}
        </span>
      </header>
      {query.error && <PageError error={query.error} />}
      {query.data && (
        <>
          <section className="metric-grid">
            <article><span>应用版本</span><strong>{query.data.version}</strong><small>Nanobot Runtime</small></article>
            <article><span>数据库</span><strong>{query.data.database === "ok" ? "正常" : "异常"}</strong><small>SQLite · WAL</small></article>
            <article><span>Schema revision</span><strong>{query.data.database_revision ?? "—"}</strong><small>目标 {query.data.expected_revision}</small></article>
            <article><span>启动恢复任务</span><strong>{query.data.recovered_jobs_at_startup}</strong><small>过期 lease</small></article>
          </section>
          <section className="panel">
            <div className="panel-heading"><div><p className="eyebrow">LOCAL STORAGE</p><h2>本地数据位置</h2></div><span>仅保存在本机</span></div>
            <dl className="path-list">
              <div><dt>数据目录</dt><dd>{query.data.paths.data_dir}</dd></div>
              <div><dt>数据库</dt><dd>{query.data.paths.database}</dd></div>
              <div><dt>日志</dt><dd>{query.data.paths.logs}</dd></div>
              <div><dt>备份</dt><dd>{query.data.paths.backups}</dd></div>
            </dl>
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
  return (
    <>
      <header className="page-header">
        <div><p className="eyebrow">PERSISTENT QUEUE</p><h1>后台任务</h1></div>
        <button type="button" className="secondary" onClick={() => void query.refetch()}>刷新</button>
      </header>
      {query.error && <PageError error={query.error} />}
      {query.data?.total === 0 && (
        <section className="empty-state">
          <div className="empty-icon">✓</div><h2>任务队列已就绪</h2>
          <p>Part 0 不创建虚假业务任务。后续模块会在这里显示真实同步、解析和生成任务。</p>
        </section>
      )}
      {query.data && query.data.total > 0 && (
        <section className="panel table-wrap"><table><thead><tr><th>类型</th><th>状态</th><th>尝试次数</th><th>创建时间</th></tr></thead>
          <tbody>{query.data.items.map((job) => <tr key={job.id}><td>{job.job_type}</td><td>{job.status}</td><td>{job.attempt_count}/{job.max_attempts}</td><td>{formatChinaTime(job.created_at)}（北京时间）</td><td>{["failed", "cancelled"].includes(job.status) && <button onClick={() => retry.mutate(job.id)}>重试</button>}{["pending", "running"].includes(job.status) && <button className="danger" onClick={() => cancel.mutate(job.id)}>取消</button>}</td></tr>)}</tbody>
        </table></section>
      )}
    </>
  );
}

export default Layout;
