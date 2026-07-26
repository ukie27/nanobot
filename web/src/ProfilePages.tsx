import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

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
    <header className="page-header"><div><p className="eyebrow">TRUSTED PROFILE</p><h1>{profile.data?.display_name ?? "我的职业档案"}</h1></div><span className="health-pill ok">已确认 {profile.data?.fact_counts.confirmed ?? 0}</span></header>
    <section className="metric-grid profile-metrics">
      <article><span>待审查</span><strong>{profile.data?.fact_counts.proposed ?? 0}</strong><small>候选事实</small></article>
      <article><span>已确认</span><strong>{profile.data?.fact_counts.confirmed ?? 0}</strong><small>可用于正式内容</small></article>
      <article><span>已拒绝</span><strong>{profile.data?.fact_counts.rejected ?? 0}</strong><small>保留审计记录</small></article>
      <article><span>时区</span><strong>{profile.data?.timezone}</strong><small>档案版本 {profile.data?.version}</small></article>
    </section>
    <ProfileBusinessMemory />
    <ManualFactForm />
    {(facts.data?.total ?? 0) === 0 && <section className="empty-state"><div className="empty-icon">＋</div><h2>还没有已确认事实</h2><p>先导入简历，然后在“事实审查”中逐条确认。只有确认后的事实才会进入可信档案。</p></section>}
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
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">EXPLICIT PREFERENCES</p><h2>求职偏好</h2></div><span>{query.data?.preferences.length ?? 0} 项</span></div><form className="form-grid" onSubmit={submitPreference}><label>偏好类型<select name="key"><option value="target_roles">目标岗位族</option><option value="target_cities">目标城市</option><option value="industries">目标行业</option><option value="work_modes">工作方式</option><option value="constraints">限制条件</option></select></label><label className="wide">内容（逗号分隔）<input name="value" required placeholder="例如：后端工程、AI 应用" /></label><button disabled={preference.isPending}>确认并写入偏好事件</button></form>{query.data?.preferences.map(item => <div className="fact-row" key={item.id}><div><strong>{Array.isArray(item.value) ? item.value.join("、") : JSON.stringify(item.value)}</strong><span>{item.preference_key} · v{item.version}</span></div></div>)}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">REFLECTIVE MEMORY</p><h2>优势与成长洞察</h2></div><button className="secondary" onClick={() => insight.mutate()} disabled={insight.isPending}>调用 Agent 生成候选</button></div>{query.data?.insights.map(item => <article className="mail-intelligence-item" key={item.id}><strong>{item.insight_type} · 置信度 {Math.round(item.confidence * 100)}%</strong><p>{item.conclusion}</p><small>{item.source} · Fact IDs：{item.evidence_refs.join("、")}</small>{item.counter_evidence.length > 0 && <small>反证 Fact IDs：{item.counter_evidence.join("、")}</small>}{item.agent_run_id && <p><a href="/agent-runs">AgentRun {item.agent_run_id.slice(0, 8)}</a></p>}{item.status === "proposed" ? <div className="fact-actions"><button onClick={() => resolve.mutate({ entityType: "profile_insight", item, resolution: "confirmed" })}>确认洞察</button><button className="secondary" onClick={() => resolve.mutate({ entityType: "profile_insight", item, resolution: "rejected" })}>拒绝</button></div> : <span className="health-pill ok">已{item.status === "confirmed" ? "确认" : "拒绝"}</span>}</article>)}{!query.data?.insights.length && <p>尚无业务洞察。洞察只引用已确认事实，且确认前不会进入可信档案。</p>}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">VERSIONED STRATEGY</p><h2>策略历史</h2></div><button className="secondary" onClick={() => strategy.mutate()} disabled={strategy.isPending}>生成本周策略候选</button></div>{query.data?.strategies.map(item => <details key={item.id}><summary>策略 v{item.version_number} · {item.status}</summary><p>目标：{JSON.stringify(item.content.target_directions)} · 地点：{JSON.stringify(item.content.priority_locations)}</p><ul>{item.content.actions.map(action => <li key={action}>{action}</li>)}</ul>{item.status === "proposed" && <div className="fact-actions"><button onClick={() => resolve.mutate({ entityType: "strategy_snapshot", item, resolution: "confirmed" })}>确认策略</button><button className="secondary" onClick={() => resolve.mutate({ entityType: "strategy_snapshot", item, resolution: "rejected" })}>拒绝</button></div>}</details>)}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">DAILY DIGEST</p><h2>每日增量整理</h2></div><button className="secondary" onClick={() => digest.mutate()} disabled={digest.isPending}>立即重建今日摘要</button></div>{latestDigest ? <><p>{latestDigest.digest_date}：{latestDigest.content.changes.length} 项档案变化，{latestDigest.content.application_changes.length} 项申请变化，{latestDigest.content.pending_review_count} 项待确认。</p>{latestDigest.content.risks.map(risk => <p className="form-error" key={risk}>{risk}</p>)}</> : <p>摘要由业务事件重建，不会覆盖事实或策略。</p>}</section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">IMPACT PROJECTION</p><h2>档案变化影响处理</h2></div><button className="secondary" onClick={() => impacts.mutate()} disabled={impacts.isPending}>处理待执行影响</button></div>{query.data?.impact_runs.map(item => <div className="history-row" key={item.id}>{item.scope} · {item.status}<small>影响 {item.affected_count} 项 · revision {item.input_revision}</small>{item.error_code && <span className="form-error">{item.error_code}</span>}</div>)}{!query.data?.impact_runs.length && <p>尚无影响处理记录。事实、偏好或已确认洞察变化后会创建持久化任务。</p>}</section>
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
  return <section className="panel manual-fact"><div className="panel-heading"><div><p className="eyebrow">MANUAL SOURCE</p><h2>手动补充事实</h2></div><button className="secondary" onClick={() => setOpen(!open)}>{open ? "收起" : "添加"}</button></div>
    {open && <form className="form-grid" onSubmit={submit}><label>类别<select name="category" defaultValue="project">{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>字段标识<input name="field_key" defaultValue="project_achievement" required /></label><label className="wide">事实内容<textarea name="value" required rows={3} /></label><label className="wide">来源说明<textarea name="source_note" rows={2} placeholder="例如：本人补充，来自项目复盘记录" /></label><button disabled={mutation.isPending}>{mutation.isPending ? "保存中…" : "保存为待审查事实"}</button>{mutation.error && <p className="form-error">{mutation.error.message}</p>}</form>}
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
  return <><header className="page-header"><div><p className="eyebrow">HUMAN REVIEW</p><h1>事实审查</h1></div><button disabled={!selected.size || batch.isPending} onClick={() => batch.mutate()}>确认所选（{selected.size}）</button></header>
    {!items.length && <section className="empty-state"><div className="empty-icon">✓</div><h2>没有待审查事实</h2><p>导入简历或手动补充事实后，候选内容会出现在这里。</p></section>}
    <section className="review-list">{items.map((fact) => <FactReviewCard key={fact.id} fact={fact} selected={selected.has(fact.id)} toggle={() => setSelected((previous) => { const next = new Set(previous); next.has(fact.id) ? next.delete(fact.id) : next.add(fact.id); return next; })} act={(kind, value) => action.mutate({ kind, fact, value })} busy={action.isPending} />)}</section>
    {(action.error || batch.error) && <section className="notice error">{action.error?.message ?? batch.error?.message}</section>}
  </>;
}

function FactReviewCard({ fact, selected, toggle, act, busy }: { fact: CandidateFact; selected: boolean; toggle: () => void; act: (kind: string, value?: string) => void; busy: boolean }) {
  const [editing, setEditing] = useState(false); const [value, setValue] = useState(fact.value);
  return <article className={`panel fact-card ${selected ? "selected" : ""}`}><div className="fact-card-top"><input type="checkbox" checked={selected} onChange={toggle} aria-label="选择事实" /><span className="category-tag">{CATEGORY_LABELS[fact.category] ?? fact.category}</span><span className="confidence">置信度 {fact.confidence == null ? "手动" : `${Math.round(fact.confidence * 100)}%`}</span></div>
    {editing ? <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={3} /> : <h2>{fact.value}</h2>}
    <p className="field-key">{fact.field_key} · v{fact.version}</p>
    {fact.sources.map((source) => <details key={source.id}><summary>查看来源证据</summary><blockquote>{source.evidence_text}</blockquote><small>{source.source_type}</small></details>)}
    <div className="fact-actions">{editing ? <><button onClick={() => { act("edit", value); setEditing(false); }} disabled={busy}>保存修改</button><button className="secondary" onClick={() => setEditing(false)}>取消</button></> : <><button onClick={() => act("confirm")} disabled={busy}>确认</button><button className="secondary" onClick={() => setEditing(true)}>编辑</button><button className="danger" onClick={() => act("reject")} disabled={busy}>拒绝</button></>}</div>
  </article>;
}

function FactRow({ fact }: { fact: CandidateFact; readonly?: boolean }) {
  return <div className="fact-row"><div><strong>{fact.value}</strong><span>{fact.field_key} · v{fact.version}</span></div><details><summary>来源与历史</summary>{fact.sources.map((source) => <blockquote key={source.id}>{source.evidence_text}</blockquote>)}{fact.revisions.map((revision) => <p key={revision.id}>v{revision.revision_number}：{revision.reason}</p>)}</details></div>;
}

export function DocumentsPage() {
  const client = useQueryClient(); const documents = useQuery({ queryKey: ["documents"], queryFn: getDocuments });
  const [result, setResult] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: importFile, onSuccess: async (doc) => { setResult(doc.duplicate ? "该文件已导入，没有产生重复事实。" : `已提取 ${doc.proposed_fact_count ?? 0} 条待审查事实。`); await client.invalidateQueries(); } });
  const paste = useMutation({ mutationFn: ({ name, text }: { name: string; text: string }) => importText(name, text), onSuccess: async (doc) => { setResult(doc.duplicate ? "相同内容已导入。" : `已提取 ${doc.proposed_fact_count ?? 0} 条待审查事实。`); await client.invalidateQueries(); } });
  function pasteSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); paste.mutate({ name: String(data.get("name")), text: String(data.get("text")) }); }
  return <><header className="page-header"><div><p className="eyebrow">SOURCE DOCUMENTS</p><h1>简历与资料</h1></div></header>
    <section className="import-grid"><form className="panel upload-card"><p className="eyebrow">FILE IMPORT</p><h2>上传文件</h2><p>支持 TXT、Markdown、PDF、DOCX，最大 10 MB。</p><input type="file" accept=".txt,.md,.markdown,.pdf,.docx" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} />{upload.isPending && <small>正在解析…</small>}</form>
      <form className="panel" onSubmit={pasteSubmit}><p className="eyebrow">PASTE TEXT</p><h2>粘贴简历文本</h2><input name="name" placeholder="资料名称" required /><textarea name="text" rows={7} placeholder="粘贴简历内容" required /><button disabled={paste.isPending}>导入并提取候选事实</button></form></section>
    {result && <section className="notice success">{result}</section>}{(upload.error || paste.error) && <section className="notice error">{upload.error?.message ?? paste.error?.message}</section>}
    <section className="panel"><div className="panel-heading"><h2>已导入文档</h2><span>{documents.data?.total ?? 0} 份</span></div>{documents.data?.items.map((doc) => <div className="document-row" key={doc.id}><div><strong>{doc.file_name}</strong><span>{doc.parser_name} · {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.fact_source_count} 条来源</span></div><code>{doc.sha256.slice(0, 12)}</code></div>)}</section>
  </>;
}
