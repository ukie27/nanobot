import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { analyzeJob, getJobPost, getJobPosts, importJobFile, importJobText, importJobUrl, type JobAnalysisSummary } from "./api";

const RECOMMENDATIONS: Record<string, string> = { blocked: "硬条件不满足", high_priority: "高优先级", consider: "值得考虑", low_priority: "低优先级" };
const CATEGORIES: Record<string, string> = { skill: "技能", experience: "经验", education: "学历", language: "语言", location: "地点", work_mode: "工作方式", other: "其他" };

function MatchBadge({ analysis }: { analysis: JobAnalysisSummary | null }) {
  if (!analysis) return <span className="health-pill">未分析</span>;
  return <span className={`health-pill ${analysis.hard_gate_passed ? "ok" : "blocked"}`}>{RECOMMENDATIONS[analysis.recommendation] ?? analysis.recommendation} · {analysis.score}</span>;
}

export function JobPoolPage() {
  const client = useQueryClient(); const query = useQuery({ queryKey: ["job-posts"], queryFn: getJobPosts });
  const [result, setResult] = useState<string | null>(null);
  const done = async (job: { duplicate: boolean; version: number }) => { setResult(job.duplicate ? "相同岗位内容已存在，没有创建重复版本。" : `岗位已保存为版本 v${job.version}，并完成可信事实匹配。`); await client.invalidateQueries({ queryKey: ["job-posts"] }); };
  const paste = useMutation({ mutationFn: ({ name, text }: { name: string; text: string }) => importJobText(name, text), onSuccess: done });
  const upload = useMutation({ mutationFn: importJobFile, onSuccess: done }); const fetchUrl = useMutation({ mutationFn: importJobUrl, onSuccess: done });
  function submitText(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); paste.mutate({ name: String(data.get("name")), text: String(data.get("text")) }); }
  function submitUrl(event: FormEvent<HTMLFormElement>) { event.preventDefault(); fetchUrl.mutate(String(new FormData(event.currentTarget).get("url"))); }
  const error = paste.error ?? upload.error ?? fetchUrl.error;
  return <><header className="page-header"><div><p className="eyebrow">VERSIONED JOB POOL</p><h1>岗位池</h1></div><span className="health-pill ok">{query.data?.total ?? 0} 个岗位</span></header>
    <section className="import-grid job-import-grid"><form className="panel" onSubmit={submitText}><p className="eyebrow">PASTE JD</p><h2>粘贴岗位正文</h2><input name="name" placeholder="来源名称，例如：公司官网" required /><textarea name="text" rows={10} placeholder="建议保留职位、公司、地点、截止时间和任职要求" required /><button disabled={paste.isPending}>导入并分析</button></form>
      <div className="job-import-stack"><form className="panel upload-card"><p className="eyebrow">FILE IMPORT</p><h2>上传岗位文件</h2><p>支持 TXT、Markdown 和带文本层的 PDF。</p><input type="file" accept=".txt,.md,.markdown,.pdf" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} /></form>
      <form className="panel" onSubmit={submitUrl}><p className="eyebrow">EXPLICIT WEB FETCH</p><h2>从公开 URL 获取</h2><p>点击后才会访问该公开网页；本地/内网地址和重定向会被拒绝。</p><input name="url" type="url" placeholder="https://example.com/jobs/123" required /><button className="secondary" disabled={fetchUrl.isPending}>确认访问并导入</button></form></div></section>
    {result && <section className="notice success">{result}</section>}{error && <section className="notice error">{error.message}</section>}
    {!query.isLoading && !query.data?.total && <section className="empty-state"><div className="empty-icon">＋</div><h2>岗位池还是空的</h2><p>先粘贴一个真实 JD。系统会保存原文和版本，并只用已确认职业事实生成匹配证据。</p></section>}
    <section className="job-list">{query.data?.items.map((job) => <Link className="panel job-card" to={`/job-posts/${job.id}`} key={job.id}><div><span className="category-tag">{job.company}</span><h2>{job.title}</h2><p>{job.location ?? "地点待确认"} · {job.work_mode ?? job.employment_type ?? "类型待确认"} · v{job.version}</p></div><MatchBadge analysis={job.latest_analysis} /></Link>)}</section></>;
}

export function JobDetailPage() {
  const { id = "" } = useParams(); const client = useQueryClient();
  const query = useQuery({ queryKey: ["job-post", id], queryFn: () => getJobPost(id), enabled: Boolean(id) });
  const rerun = useMutation({ mutationFn: () => analyzeJob(id), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["job-post", id] }); await client.invalidateQueries({ queryKey: ["job-posts"] }); } });
  if (query.isLoading) return <section className="empty-state"><p>正在读取岗位…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "岗位不存在"}</section>;
  const job = query.data; const analysis = job.analyses[0];
  return <><header className="page-header job-detail-header"><div><p className="eyebrow"><Link to="/job-posts">岗位池</Link> / {job.company}</p><h1>{job.title}</h1><p>{job.location ?? "地点待确认"} · {job.work_mode ?? job.employment_type ?? "类型待确认"}{job.deadline_at ? ` · 截止 ${new Date(job.deadline_at).toLocaleDateString("zh-CN")}` : ""}</p></div><button onClick={() => rerun.mutate()} disabled={rerun.isPending}>重新分析</button></header>
    <section className="metric-grid"><article><span>确定性匹配分</span><strong>{analysis?.score ?? 0}</strong><small>仅作为分项参考</small></article><article><span>硬门槛</span><strong>{analysis?.hard_gate_passed ? "通过" : "未通过"}</strong><small>{analysis?.must_gap_count ?? 0} 个硬条件缺口</small></article><article><span>证据支持</span><strong>{analysis?.matched_count ?? 0}</strong><small>项要求有可信事实</small></article><article><span>当前版本</span><strong>v{job.version}</strong><small>共 {job.versions.length} 个不可变版本</small></article></section>
    {!analysis?.hard_gate_passed && <section className="notice error"><strong>该岗位存在未满足的硬性条件</strong><p>总分不会覆盖硬门槛。请检查下方缺口，确认事实库是否缺失或确实不符合。</p></section>}
    <section className="panel evidence-panel"><div className="panel-heading"><div><p className="eyebrow">REQUIREMENT → EVIDENCE</p><h2>要求与可信证据</h2></div><span>{job.requirements.length} 项</span></div>{analysis?.evidence.map((item) => <article className={`evidence-row ${item.decision}`} key={item.requirement.id}><div className="requirement-copy"><div><span className={`requirement-level ${item.requirement.level}`}>{item.requirement.level === "must" ? "硬性" : "优先"}</span><span>{CATEGORIES[item.requirement.category] ?? item.requirement.category}</span></div><h3>{item.requirement.description}</h3><blockquote>{item.requirement.evidence_text}</blockquote></div><div className="evidence-copy"><strong>{item.decision === "matched" ? "有证据" : "缺口"}</strong><p>{item.rationale}</p>{item.facts.map((fact) => <div className="fact-proof" key={fact.id}>{fact.value}<small>{fact.category} · {fact.field_key} · v{fact.version}</small></div>)}</div></article>)}</section>
    <section className="detail-grid"><details className="panel"><summary>查看岗位原文</summary><pre className="raw-text">{job.raw_text}</pre></details><section className="panel"><div className="panel-heading"><h2>版本与分析历史</h2><span>{job.analyses.length} 次分析</span></div>{job.versions.map((version) => <p className="history-row" key={version.id}>JD v{version.version_number}<small>{new Date(version.created_at).toLocaleString("zh-CN")} · {version.content_hash.slice(0, 12)}</small></p>)}{job.analyses.map((item) => <p className="history-row" key={item.id}>分析：{RECOMMENDATIONS[item.recommendation]} · {item.score}<small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></p>)}</section></section></>;
}
