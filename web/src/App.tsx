import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { ApiError, getBackgroundJobs, getSystemStatus } from "./api";
import { JobDetailPage, JobPoolPage } from "./JobPages";
import { DocumentsPage, ProfilePage, ReviewPage } from "./ProfilePages";

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
          <NavLink to="/profile">职业档案</NavLink>
          <NavLink to="/documents">简历导入</NavLink>
          <NavLink to="/review">事实审查</NavLink>
          <NavLink to="/job-posts">岗位池</NavLink>
          <NavLink to="/status">运行状态</NavLink>
          <NavLink to="/jobs">后台任务</NavLink>
        </nav>
        <div className="phase-note">
          <span>当前阶段</span>
          <strong>Part 2 · 岗位匹配</strong>
          <p>手动导入岗位，使用已确认事实生成可解释匹配。</p>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/profile" replace />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/job-posts" element={<JobPoolPage />} />
          <Route path="/job-posts/:id" element={<JobDetailPage />} />
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
  const query = useQuery({ queryKey: ["background-jobs"], queryFn: getBackgroundJobs });
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
          <tbody>{query.data.items.map((job) => <tr key={job.id}><td>{job.job_type}</td><td>{job.status}</td><td>{job.attempt_count}/{job.max_attempts}</td><td>{new Date(job.created_at).toLocaleString("zh-CN")}</td></tr>)}</tbody>
        </table></section>
      )}
    </>
  );
}

export default Layout;
