import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  addManualFact,
  batchConfirmFacts,
  confirmFact,
  editFact,
  getDocuments,
  getFacts,
  getProfile,
  getProfileMemory,
  setCareerPreference,
  generateDailyDigest,
  generateStrategyProposal,
  generateProfileInsight,
  resolveProfileMemoryProposal,
  runProfileImpacts,
  importFile,
  importText,
  rejectFact,
  type CandidateFact,
} from "./api";

const CATEGORY_LABELS: Record<string, string> = {
  basic: "基本信息", education: "教育经历", internship: "实习经历", work: "工作经历",
  project: "项目经历", skill: "技能", award: "奖项", certificate: "证书",
  preference: "求职偏好", constraint: "限制条件",
};
const PARSER_LABELS: Record<string, string> = {
  plain_text_v1: "文本文件",
  pasted_text_v1: "粘贴文本",
  pypdf_v1: "PDF 文件",
  python_docx_v1: "Word 文档",
};
const PREFERENCE_LABELS: Record<string, string> = {
  target_roles: "目标岗位",
  target_cities: "目标城市",
  industries: "目标行业",
  work_modes: "工作方式",
  constraints: "限制条件",
};
const PROPOSAL_STATUS_LABELS: Record<string, string> = {
  proposed: "待确认",
  confirmed: "已确认",
  rejected: "已拒绝",
};
const IMPACT_SCOPE_LABELS: Record<string, string> = {
  job_matches: "岗位匹配",
  materials: "申请材料",
  applications: "申请进度",
  all: "全部业务",
};
const IMPACT_STATUS_LABELS: Record<string, string> = {
  pending: "等待处理",
  running: "处理中",
  succeeded: "处理完成",
  failed: "处理失败",
};

function Loading() { return <section className="empty-state"><p>正在读取本地数据…</p></section>; }

export function ProfilePage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: getProfile });
  const facts = useQuery({ queryKey: ["facts", "confirmed"], queryFn: () => getFacts("confirmed") });
  const grouped = useMemo(
    () => (facts.data?.items ?? []).reduce<Record<string, CandidateFact[]>>((result, fact) => {
      (result[fact.category] ??= []).push(fact); return result;
    }, {}),
    [facts.data],
  );
  if (profile.isLoading || facts.isLoading) return <Loading />;
  return <>
    <header className="page-header"><div><p className="eyebrow">用于匹配岗位和生成材料</p><h1>{profile.data?.display_name ?? "我的经历"}</h1><p>这里只展示你确认过的教育、项目、实习和技能信息。</p></div><span className="health-pill ok">已确认 {profile.data?.fact_counts.confirmed ?? 0}</span></header>
    <section className="profile-next-steps">
      <Link to="/documents"><strong>导入简历或经历</strong><span>从文件和文本中提取内容</span></Link>
      <Link to="/review"><strong>确认提取结果</strong><span>{profile.data?.fact_counts.proposed ?? 0} 条等待确认</span></Link>
      <Link to="/materials"><strong>准备申请材料</strong><span>根据目标岗位修改简历</span></Link>
    </section>
    <section className="metric-grid profile-metrics">
      <article><span>待确认</span><strong>{profile.data?.fact_counts.proposed ?? 0}</strong><small>尚未写入个人经历</small></article>
      <article><span>已确认</span><strong>{profile.data?.fact_counts.confirmed ?? 0}</strong><small>可用于正式内容</small></article>
      <article><span>已拒绝</span><strong>{profile.data?.fact_counts.rejected ?? 0}</strong><small>保留审计记录</small></article>
      <article><span>时区</span><strong>{profile.data?.timezone}</strong><small>用于所有日程和提醒</small></article>
    </section>
    <details className="profile-record-details"><summary>查看档案记录</summary><small>当前档案版本：{profile.data?.version}</small></details>
    <details className="panel profile-tools">
      <summary><span><small>可选功能</small><strong>求职偏好、优势洞察与每周策略</strong></span><em>展开管理</em></summary>
      <ProfileBusinessMemory />
    </details>
    <ManualFactForm />
    {(facts.data?.total ?? 0) === 0 && <section className="empty-state"><div className="empty-icon">＋</div><h2>还没有已确认的经历</h2><p>先导入简历，然后在“简历内容确认”中检查提取结果。只有你确认的内容才会用于岗位分析和材料生成。</p><Link className="download-button" to="/documents">导入第一份资料</Link></section>}
    {Object.entries(grouped).map(([category, items]) => items && <section className="panel fact-group" key={category}><div className="panel-heading"><h2>{CATEGORY_LABELS[category] ?? category}</h2><span>{items.length} 条</span></div>{items.map((fact) => <FactRow fact={fact} readonly key={fact.id} />)}</section>)}
  </>;
}

function ProfileBusinessMemory() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["profile-memory"], queryFn: getProfileMemory });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["profile-memory"] }), client.invalidateQueries({ queryKey: ["unified-reviews"] })]); };
  const preference = useMutation({ mutationFn: ({ key, value }: { key: string; value: string[] }) => { const current = query.data?.preferences.find(item => item.preference_key === key); return setCareerPreference(key, value, current?.version ?? null); }, onSuccess: refresh });
  const digest = useMutation({ mutationFn: generateDailyDigest, onSuccess: refresh });
  const strategy = useMutation({ mutationFn: generateStrategyProposal, onSuccess: refresh });
  const insight = useMutation({ mutationFn: generateProfileInsight, onSuccess: refresh });
  const impacts = useMutation({ mutationFn: runProfileImpacts, onSuccess: refresh });
  const resolve = useMutation({ mutationFn: ({ entityType, item, resolution }: { entityType: "profile_insight" | "strategy_snapshot"; item: { id: string; version: number }; resolution: "confirmed" | "rejected" }) => resolveProfileMemoryProposal(entityType, item, resolution), onSuccess: refresh });
  const submitPreference = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const key = String(data.get("key")); const value = String(data.get("value")).split(/[,，、]/).map(item => item.trim()).filter(Boolean); preference.mutate({ key, value }); };
  const latestDigest = query.data?.digests[0];
  return <section className="profile-memory">
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">明确偏好</p><h2>求职偏好</h2></div><span>{query.data?.preferences.length ?? 0} 项</span></div><form className="form-grid" onSubmit={submitPreference}><label>偏好类型<select name="key"><option value="target_roles">目标岗位</option><option value="target_cities">目标城市</option><option value="industries">目标行业</option><option value="work_modes">工作方式</option><option value="constraints">限制条件</option></select></label><label className="wide">内容（逗号分隔）<input name="value" required placeholder="例如：后端工程、AI 应用" /></label><button disabled={preference.isPending}>保存求职偏好</button></form>{query.data?.preferences.map(item => <div className="fact-row" key={item.id}><div><strong>{Array.isArray(item.value) ? item.value.join("、") : JSON.stringify(item.value)}</strong><span>{PREFERENCE_LABELS[item.preference_key] ?? "求职偏好"}</span></div><details className="audit-details"><summary>查看记录信息</summary><small>版本 {item.version}</small></details></div>)}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">档案洞察</p><h2>优势与成长洞察</h2></div><button className="secondary" onClick={() => insight.mutate()} disabled={insight.isPending}>生成洞察建议</button></div>{query.data?.insights.map(item => <article className="mail-intelligence-item" key={item.id}><strong>{item.insight_type} · 置信度 {Math.round(item.confidence * 100)}%</strong><p>{item.conclusion}</p><details><summary>查看依据与运行记录</summary><small>{item.source} · 事实依据：{item.evidence_refs.join("、")}</small>{item.counter_evidence.length > 0 && <small>反向依据：{item.counter_evidence.join("、")}</small>}{item.agent_run_id && <p><a href="/agent-runs">查看智能功能记录 {item.agent_run_id.slice(0, 8)}</a></p>}</details>{item.status === "proposed" ? <div className="fact-actions"><button onClick={() => resolve.mutate({ entityType: "profile_insight", item, resolution: "confirmed" })}>确认洞察</button><button className="secondary" onClick={() => resolve.mutate({ entityType: "profile_insight", item, resolution: "rejected" })}>拒绝</button></div> : <span className="health-pill ok">{PROPOSAL_STATUS_LABELS[item.status] ?? "已处理"}</span>}</article>)}{!query.data?.insights.length && <p>尚无业务洞察。洞察只引用已确认事实，且确认前不会进入可信档案。</p>}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">求职策略</p><h2>策略历史</h2></div><button className="secondary" onClick={() => strategy.mutate()} disabled={strategy.isPending}>生成本周策略建议</button></div>{query.data?.strategies.map(item => <details key={item.id}><summary>本周策略 · {PROPOSAL_STATUS_LABELS[item.status] ?? "已处理"}</summary><p>目标：{JSON.stringify(item.content.target_directions)} · 地点：{JSON.stringify(item.content.priority_locations)}</p><ul>{item.content.actions.map(action => <li key={action}>{action}</li>)}</ul>{item.status === "proposed" && <div className="fact-actions"><button onClick={() => resolve.mutate({ entityType: "strategy_snapshot", item, resolution: "confirmed" })}>确认策略</button><button className="secondary" onClick={() => resolve.mutate({ entityType: "strategy_snapshot", item, resolution: "rejected" })}>拒绝</button></div>}<details className="audit-details"><summary>查看记录信息</summary><small>策略版本 {item.version_number}</small></details></details>)}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">每日整理</p><h2>每日增量整理</h2></div><button className="secondary" onClick={() => digest.mutate()} disabled={digest.isPending}>立即重建今日摘要</button></div>{latestDigest ? <><p>{latestDigest.digest_date}：{latestDigest.content.changes.length} 项档案变化，{latestDigest.content.application_changes.length} 项申请变化，{latestDigest.content.pending_review_count} 项待确认。</p>{latestDigest.content.risks.map(risk => <p className="form-error" key={risk}>{risk}</p>)}</> : <p>摘要由业务事件重建，不会覆盖事实或策略。</p>}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">变化影响</p><h2>档案变化影响处理</h2></div><button className="secondary" onClick={() => impacts.mutate()} disabled={impacts.isPending}>处理待执行影响</button></div>{query.data?.impact_runs.map(item => <div className="history-row" key={item.id}>{IMPACT_SCOPE_LABELS[item.scope] ?? "业务数据"} · {IMPACT_STATUS_LABELS[item.status] ?? "处理中"}<small>影响 {item.affected_count} 项</small><details className="audit-details"><summary>查看运行详情</summary><small>输入版本 {item.input_revision}{item.error_code ? ` · 错误代码 ${item.error_code}` : ""}</small></details></div>)}{!query.data?.impact_runs.length && <p>尚无影响处理记录。事实、偏好或已确认洞察变化后会创建持久化任务。</p>}</section>
    {(query.error || preference.error || digest.error || strategy.error || insight.error || impacts.error || resolve.error) && <section className="notice error">{(query.error || preference.error || digest.error || strategy.error || insight.error || impacts.error || resolve.error)?.message}</section>}
  </section>;
}

function ManualFactForm() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const mutation = useMutation({ mutationFn: addManualFact, onSuccess: async () => { setOpen(false); await client.invalidateQueries(); } });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    mutation.mutate({ category: String(data.get("category")), field_key: String(data.get("field_key")), value: String(data.get("value")), source_note: String(data.get("source_note")) });
  }
  return <section className="panel manual-fact"><div className="panel-heading"><div><p className="eyebrow">没有文件也可以补充</p><h2>手动添加一段经历</h2></div><button className="secondary" onClick={() => setOpen(!open)}>{open ? "收起" : "添加"}</button></div>
    {open && <form className="form-grid" onSubmit={submit}><label>经历类型<select name="category" defaultValue="project">{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><input type="hidden" name="field_key" value="manual_entry" /><label className="wide">经历内容<textarea name="value" required rows={3} placeholder="写清楚你做了什么、使用了什么能力、取得了什么结果" /></label><label className="wide">内容来源（可选）<textarea name="source_note" rows={2} placeholder="例如：本人补充，来自项目复盘记录" /></label><button disabled={mutation.isPending}>{mutation.isPending ? "保存中…" : "保存并等待确认"}</button>{mutation.error && <p className="form-error">{mutation.error.message}</p>}</form>}
  </section>;
}

export function ReviewPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["facts", "proposed"], queryFn: () => getFacts("proposed") });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const refresh = async () => { setSelected(new Set()); await client.invalidateQueries(); };
  const action = useMutation({ mutationFn: ({ kind, fact, value }: { kind: string; fact: CandidateFact; value?: string }) => kind === "confirm" ? confirmFact(fact) : kind === "reject" ? rejectFact(fact) : editFact(fact, value ?? fact.value), onSuccess: refresh });
  const batch = useMutation({ mutationFn: () => batchConfirmFacts((query.data?.items ?? []).filter((fact) => selected.has(fact.id))), onSuccess: refresh });
  if (query.isLoading) return <Loading />;
  const items = query.data?.items ?? [];
  return <><header className="page-header"><div><p className="eyebrow">确认后才会用于正式内容</p><h1>简历内容确认</h1><p>检查系统从简历和经历资料中提取的内容，修改错误后再确认。</p></div><button disabled={!selected.size || batch.isPending} onClick={() => batch.mutate()}>确认所选（{selected.size}）</button></header>
    {!items.length && <section className="empty-state"><div className="empty-icon">✓</div><h2>没有等待确认的内容</h2><p>导入简历或手动添加经历后，提取结果会出现在这里。</p><Link className="download-button" to="/documents">导入资料</Link></section>}
    <section className="review-list">{items.map((fact) => <FactReviewCard key={fact.id} fact={fact} selected={selected.has(fact.id)} toggle={() => setSelected((previous) => { const next = new Set(previous); next.has(fact.id) ? next.delete(fact.id) : next.add(fact.id); return next; })} act={(kind, value) => action.mutate({ kind, fact, value })} busy={action.isPending} />)}</section>
    {(action.error || batch.error) && <section className="notice error">{action.error?.message ?? batch.error?.message}</section>}
  </>;
}

function FactReviewCard({ fact, selected, toggle, act, busy }: { fact: CandidateFact; selected: boolean; toggle: () => void; act: (kind: string, value?: string) => void; busy: boolean }) {
  const [editing, setEditing] = useState(false); const [value, setValue] = useState(fact.value);
  return <article className={`panel fact-card ${selected ? "selected" : ""}`}><div className="fact-card-top"><input type="checkbox" checked={selected} onChange={toggle} aria-label="选择事实" /><span className="category-tag">{CATEGORY_LABELS[fact.category] ?? fact.category}</span><span className="confidence">置信度 {fact.confidence == null ? "手动" : `${Math.round(fact.confidence * 100)}%`}</span></div>
    {editing ? <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={3} /> : <h2>{fact.value}</h2>}
    <details><summary>查看记录信息</summary><p className="field-key">记录字段：{fact.field_key} · 版本 {fact.version}</p></details>
    {fact.sources.map((source) => <details key={source.id}><summary>查看来源证据</summary><blockquote>{source.evidence_text}</blockquote><small>{source.source_type}</small></details>)}
    <div className="fact-actions">{editing ? <><button onClick={() => { act("edit", value); setEditing(false); }} disabled={busy}>保存修改</button><button className="secondary" onClick={() => setEditing(false)}>取消</button></> : <><button onClick={() => act("confirm")} disabled={busy}>确认</button><button className="secondary" onClick={() => setEditing(true)}>编辑</button><button className="danger" onClick={() => act("reject")} disabled={busy}>拒绝</button></>}</div>
  </article>;
}

function FactRow({ fact }: { fact: CandidateFact; readonly?: boolean }) {
  return <div className="fact-row"><strong>{fact.value}</strong><details><summary>查看来源与记录</summary><p className="field-key">记录字段：{fact.field_key} · 版本 {fact.version}</p>{fact.sources.map((source) => <blockquote key={source.id}>{source.evidence_text}</blockquote>)}{fact.revisions.map((revision) => <p key={revision.id}>版本 {revision.revision_number}：{revision.reason}</p>)}</details></div>;
}

export function DocumentsPage() {
  const client = useQueryClient(); const documents = useQuery({ queryKey: ["documents"], queryFn: getDocuments });
  const [result, setResult] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: importFile, onSuccess: async (doc) => { setResult(doc.duplicate ? "该文件已导入，没有产生重复事实。" : `已提取 ${doc.proposed_fact_count ?? 0} 条待审查事实。`); await client.invalidateQueries(); } });
  const paste = useMutation({ mutationFn: ({ name, text }: { name: string; text: string }) => importText(name, text), onSuccess: async (doc) => { setResult(doc.duplicate ? "相同内容已导入。" : `已提取 ${doc.proposed_fact_count ?? 0} 条待审查事实。`); await client.invalidateQueries(); } });
  function pasteSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); paste.mutate({ name: String(data.get("name")), text: String(data.get("text")) }); }
  return <><header className="page-header"><div><p className="eyebrow">建立可靠的个人经历</p><h1>导入资料</h1><p>导入简历、项目复盘和经历材料。系统会先提取内容，由你确认后再用于岗位匹配和材料生成。</p></div></header>
    <section className="import-grid"><form className="panel upload-card"><p className="eyebrow">文件导入</p><h2>上传文件</h2><p>支持 TXT、Markdown、PDF、DOCX，最大 10 MB。</p><label className="file-picker"><input type="file" aria-label="选择文件并导入" accept=".txt,.md,.markdown,.pdf,.docx" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} /><span>{upload.isPending ? "正在解析文件…" : "选择文件并导入"}</span></label></form>
      <form className="panel" onSubmit={pasteSubmit}><p className="eyebrow">粘贴文本</p><h2>粘贴简历文本</h2><input name="name" placeholder="资料名称" required /><textarea name="text" rows={7} placeholder="粘贴简历内容" required /><button disabled={paste.isPending}>导入并提取内容</button></form></section>
    {result && <section className="notice success"><strong>{result}</strong><div className="form-actions"><Link className="download-button" to="/review">检查提取结果</Link></div></section>}{(upload.error || paste.error) && <section className="notice error">{upload.error?.message ?? paste.error?.message}</section>}
    <section className="panel"><div className="panel-heading"><h2>已导入文档</h2><span>{documents.data?.total ?? 0} 份</span></div>{documents.data?.items.map((doc) => <div className="document-row" key={doc.id}><div><strong>{doc.file_name}</strong><span>{(doc.size_bytes / 1024).toFixed(1)} KB · 已提取 {doc.fact_source_count} 条内容来源</span></div><details><summary>查看导入记录</summary><small>处理方式：{PARSER_LABELS[doc.parser_name] ?? "其他格式"}</small><code>内容校验：{doc.sha256.slice(0, 12)}</code></details></div>)}</section>
  </>;
}
