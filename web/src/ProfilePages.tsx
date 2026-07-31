import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

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
  importFile,
  importText,
  rejectFact,
  ApiError,
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
type ProfileView = "facts" | "preferences" | "insights";
const PROFILE_VIEWS: Array<{ id: ProfileView; label: string; description: string }> = [
  { id: "facts", label: "职业档案", description: "查看已确认的教育、项目、工作和能力信息" },
  { id: "preferences", label: "求职偏好", description: "管理目标岗位、城市、行业和限制条件" },
  { id: "insights", label: "洞察与策略", description: "查看 Agent 形成的优势洞察、策略和摘要" },
];

function Loading() { return <section className="empty-state"><p>正在读取本地数据…</p></section>; }

export function ProfilePage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: getProfile });
  const facts = useQuery({ queryKey: ["facts", "confirmed"], queryFn: () => getFacts("confirmed") });
  const [view, setView] = useState<ProfileView>("facts");
  const [activeCategory, setActiveCategory] = useState("all");
  const grouped = useMemo(
    () => (facts.data?.items ?? []).reduce<Record<string, CandidateFact[]>>((result, fact) => {
      (result[fact.category] ??= []).push(fact); return result;
    }, {}),
    [facts.data],
  );
  if (profile.isLoading || facts.isLoading) return <Loading />;
  const categoryEntries = Object.entries(grouped).filter((entry): entry is [string, CandidateFact[]] => Boolean(entry[1]?.length));
  const visibleGroups = activeCategory === "all"
    ? categoryEntries
    : categoryEntries.filter(([category]) => category === activeCategory);
  const activeView = PROFILE_VIEWS.find(item => item.id === view) ?? PROFILE_VIEWS[0];

  return <>
    <header className="page-header profile-page-header">
      <div>
        <p className="eyebrow">个人画像</p>
        <h1>{profile.data?.display_name ?? "我的资料"}</h1>
        <p>这里是岗位匹配、申请材料和面试准备共同使用的可信个人档案。</p>
      </div>
      <span className="health-pill ok">档案版本 {profile.data?.version ?? 1}</span>
    </header>
    <section className="profile-primary-actions" aria-label="完善个人资料">
      <Link to="/profile/import">
        <div><strong>导入简历或经历资料</strong><span>让 Agent 从文件或文本中整理职业经历</span></div>
        <em>导入资料</em>
      </Link>
      <Link to="/profile/reviews">
        <div><strong>处理 Agent 提取结果</strong><span>{profile.data?.fact_counts.proposed ?? 0} 项内容等待确认</span></div>
        <em>开始确认</em>
      </Link>
      <Link to="/profile/manual">
        <div><strong>手动添加一段经历</strong><span>没有现成文件时，直接补充完整经历</span></div>
        <em>添加经历</em>
      </Link>
    </section>
    <section className="profile-status-strip" aria-label="档案状态">
      <div><span>已确认</span><strong>{profile.data?.fact_counts.confirmed ?? 0}</strong><small>可用于正式业务</small></div>
      <div><span>待确认</span><strong>{profile.data?.fact_counts.proposed ?? 0}</strong><small>尚未写入档案</small></div>
      <div><span>已拒绝</span><strong>{profile.data?.fact_counts.rejected ?? 0}</strong><small>仅保留审计记录</small></div>
      <div><span>时间标准</span><strong>{profile.data?.timezone ?? "Asia/Shanghai"}</strong><small>日程与提醒统一使用</small></div>
    </section>

    <nav className="profile-view-tabs" aria-label="个人画像视图">
      {PROFILE_VIEWS.map(item => <button
        type="button"
        className={view === item.id ? "active" : ""}
        aria-current={view === item.id ? "page" : undefined}
        onClick={() => setView(item.id)}
        key={item.id}
      >
        <strong>{item.label}</strong>
        <span>{item.description}</span>
      </button>)}
    </nav>

    <section className="profile-view-heading">
      <div><p className="eyebrow">当前视图</p><h2>{activeView.label}</h2></div>
      <p>{activeView.description}</p>
    </section>

    {view === "facts" && <>
      {(facts.data?.total ?? 0) === 0
        ? <section className="empty-state"><div className="empty-icon">＋</div><h2>还没有已确认的经历</h2><p>导入资料或手动补充经历，然后确认 Agent 整理结果。</p><Link className="download-button" to="/profile/import">导入第一份资料</Link></section>
        : <div className="profile-facts-workspace">
          <aside className="profile-category-index" aria-label="档案类别">
            <button type="button" className={activeCategory === "all" ? "active" : ""} onClick={() => setActiveCategory("all")}>
              <span>全部档案</span><strong>{facts.data?.total ?? 0}</strong>
            </button>
            {categoryEntries.map(([category, items]) => <button
              type="button"
              className={activeCategory === category ? "active" : ""}
              onClick={() => setActiveCategory(category)}
              key={category}
            >
              <span>{CATEGORY_LABELS[category] ?? category}</span><strong>{items.length}</strong>
            </button>)}
          </aside>
          <div className="profile-fact-groups">
            {visibleGroups.map(([category, items]) => <section className="profile-fact-section" key={category}>
              <div className="profile-section-heading"><div><p className="eyebrow">已确认内容</p><h2>{CATEGORY_LABELS[category] ?? category}</h2></div><span>{items.length} 项</span></div>
              <div className="profile-fact-list">{items.map(fact => <FactRow fact={fact} key={fact.id} />)}</div>
            </section>)}
          </div>
        </div>}
    </>}
    {view !== "facts" && <ProfileBusinessMemory view={view} />}
  </>;
}

function ProfileBusinessMemory({
  view,
}: {
  view: Exclude<ProfileView, "facts">;
}) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["profile-memory"], queryFn: getProfileMemory });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["profile-memory"] }), client.invalidateQueries({ queryKey: ["unified-reviews"] })]); };
  const preference = useMutation({ mutationFn: ({ key, value }: { key: string; value: string[] }) => { const current = query.data?.preferences.find(item => item.preference_key === key); return setCareerPreference(key, value, current?.version ?? null); }, onSuccess: refresh });
  const digest = useMutation({ mutationFn: generateDailyDigest, onSuccess: refresh });
  const strategy = useMutation({ mutationFn: generateStrategyProposal, onSuccess: refresh });
  const insight = useMutation({ mutationFn: generateProfileInsight, onSuccess: refresh });
  const resolve = useMutation({ mutationFn: ({ entityType, item, resolution }: { entityType: "profile_insight" | "strategy_snapshot"; item: { id: string; version: number }; resolution: "confirmed" | "rejected" }) => resolveProfileMemoryProposal(entityType, item, resolution), onSuccess: refresh });
  const [preferenceKey, setPreferenceKey] = useState("target_roles");
  const [preferenceDraft, setPreferenceDraft] = useState("");
  useEffect(() => {
    const current = query.data?.preferences.find(item => item.preference_key === preferenceKey);
    setPreferenceDraft(Array.isArray(current?.value) ? current.value.join("、") : "");
  }, [preferenceKey, query.data?.preferences]);
  const submitPreference = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = preferenceDraft.split(/[,，、]/).map(item => item.trim()).filter(Boolean);
    preference.mutate({ key: preferenceKey, value });
  };
  if (query.isLoading) return <Loading />;
  const latestDigest = query.data?.digests[0];
  const error = query.error || preference.error || digest.error || strategy.error || insight.error || resolve.error;

  if (view === "preferences") {
    return <section className="profile-memory profile-preference-workspace">
      <section className="panel">
        <div className="panel-heading"><div><p className="eyebrow">匹配边界</p><h2>编辑求职偏好</h2></div><span>{query.data?.preferences.length ?? 0} 项</span></div>
        <p className="section-note">这些偏好会影响岗位推荐排序，但不会覆盖你的职业经历。</p>
        <form className="form-grid" onSubmit={submitPreference}><label>偏好类型<select name="key" value={preferenceKey} onChange={event => setPreferenceKey(event.target.value)}><option value="target_roles">目标岗位</option><option value="target_cities">目标城市</option><option value="industries">目标行业</option><option value="work_modes">工作方式</option><option value="constraints">限制条件</option></select></label><label className="wide">内容（逗号分隔）<input name="value" value={preferenceDraft} onChange={event => setPreferenceDraft(event.target.value)} required placeholder="例如：后端工程、AI 应用" /></label><button disabled={preference.isPending}>{preference.isPending ? "正在保存…" : "保存求职偏好"}</button></form>
      </section>
      <section className="profile-preference-list" aria-label="当前求职偏好">
        {query.data?.preferences.map(item => <article className="profile-preference-row" key={item.id}><div><span>{PREFERENCE_LABELS[item.preference_key] ?? "求职偏好"}</span><strong>{Array.isArray(item.value) ? item.value.join("、") : JSON.stringify(item.value)}</strong></div><small>版本 {item.version}</small></article>)}
        {!query.data?.preferences.length && <section className="empty-state"><h2>还没有求职偏好</h2><p>先添加目标岗位或目标城市，岗位推荐会据此调整优先级。</p></section>}
      </section>
      {error && <section className="notice error">{error.message}</section>}
    </section>;
  }

  if (view === "insights") {
    return <section className="profile-memory profile-insight-workspace">
      <section className="panel"><div className="panel-heading"><div><p className="eyebrow">档案洞察</p><h2>优势与成长洞察</h2></div><button className="secondary" onClick={() => insight.mutate()} disabled={insight.isPending}>生成洞察建议</button></div>{query.data?.insights.map(item => <article className="mail-intelligence-item" key={item.id}><strong>{item.insight_type} · 置信度 {Math.round(item.confidence * 100)}%</strong><p>{item.conclusion}</p><details><summary>查看依据与运行记录</summary><small>{item.source} · 事实依据：{item.evidence_refs.join("、")}</small>{item.counter_evidence.length > 0 && <small>反向依据：{item.counter_evidence.join("、")}</small>}{item.agent_run_id && <p><Link to="/agent-runs">查看智能功能记录 {item.agent_run_id.slice(0, 8)}</Link></p>}</details>{item.status === "proposed" ? <div className="fact-actions"><button onClick={() => resolve.mutate({ entityType: "profile_insight", item, resolution: "confirmed" })}>确认洞察</button><button className="secondary" onClick={() => resolve.mutate({ entityType: "profile_insight", item, resolution: "rejected" })}>拒绝</button></div> : <span className="health-pill ok">{PROPOSAL_STATUS_LABELS[item.status] ?? "已处理"}</span>}</article>)}{!query.data?.insights.length && <p>尚无业务洞察。洞察只引用已确认事实，且确认前不会进入可信档案。</p>}</section>
      <section className="profile-strategy-grid">
        <section className="panel"><div className="panel-heading"><div><p className="eyebrow">求职策略</p><h2>策略历史</h2></div><button className="secondary" onClick={() => strategy.mutate()} disabled={strategy.isPending}>生成本周策略</button></div>{query.data?.strategies.map(item => <details className="profile-strategy-item" key={item.id}><summary>本周策略 · {PROPOSAL_STATUS_LABELS[item.status] ?? "已处理"}</summary><p>目标：{JSON.stringify(item.content.target_directions)} · 地点：{JSON.stringify(item.content.priority_locations)}</p><ul>{item.content.actions.map(action => <li key={action}>{action}</li>)}</ul>{item.status === "proposed" && <div className="fact-actions"><button onClick={() => resolve.mutate({ entityType: "strategy_snapshot", item, resolution: "confirmed" })}>确认策略</button><button className="secondary" onClick={() => resolve.mutate({ entityType: "strategy_snapshot", item, resolution: "rejected" })}>拒绝</button></div>}<small>策略版本 {item.version_number}</small></details>)}{!query.data?.strategies.length && <p>尚未生成求职策略。</p>}</section>
        <section className="panel"><div className="panel-heading"><div><p className="eyebrow">每日整理</p><h2>档案摘要</h2></div><button className="secondary" onClick={() => digest.mutate()} disabled={digest.isPending}>重建今日摘要</button></div>{latestDigest ? <><p>{latestDigest.digest_date}：{latestDigest.content.changes.length} 项档案变化，{latestDigest.content.application_changes.length} 项申请变化，{latestDigest.content.pending_review_count} 项待确认。</p>{latestDigest.content.risks.map(risk => <p className="form-error" key={risk}>{risk}</p>)}</> : <p>摘要由业务事件重建，不会覆盖事实或策略。</p>}</section>
      </section>
      {error && <section className="notice error">{error.message}</section>}
    </section>;
  }
}

function ManualFactForm() {
  const client = useQueryClient();
  const [saved, setSaved] = useState(false);
  const mutation = useMutation({
    mutationFn: addManualFact,
    onMutate: () => setSaved(false),
    onSuccess: async () => {
      setSaved(true);
      await client.invalidateQueries();
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    mutation.mutate(
      { category: String(data.get("category")), field_key: String(data.get("field_key")), value: String(data.get("value")), source_note: String(data.get("source_note")) },
      { onSuccess: () => form.reset() },
    );
  }
  return <section className="panel manual-fact">
    <div className="panel-heading"><div><p className="eyebrow">没有文件也可以补充</p><h2>经历内容</h2></div></div>
    <form className="form-grid" onSubmit={submit}><label>经历类型<select name="category" defaultValue="project">{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><input type="hidden" name="field_key" value="manual_entry" /><label className="wide">经历内容<textarea name="value" required rows={5} placeholder="写清楚你做了什么、使用了什么能力、取得了什么结果" /></label><label className="wide">内容来源（可选）<textarea name="source_note" rows={2} placeholder="例如：本人补充，来自项目复盘记录" /></label><button disabled={mutation.isPending}>{mutation.isPending ? "保存中…" : "保存并等待确认"}</button>{mutation.error && <p className="form-error">{mutation.error.message}</p>}</form>
    {saved && <section className="notice success"><strong>经历已保存，确认后才会进入职业档案。</strong><div className="form-actions"><Link className="download-button" to="/profile/reviews">前往确认</Link><Link className="download-button secondary" to="/profile">返回我的资料</Link></div></section>}
  </section>;
}

export function ManualFactPage() {
  return <>
    <header className="page-header"><div><p className="eyebrow">我的资料 / 手动补充</p><h1>添加一段经历</h1><p>填写一段完整经历。保存后先进入待确认区，不会直接改写正式档案。</p></div></header>
    <ManualFactForm />
  </>;
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
  return <><header className="page-header"><div><p className="eyebrow">确认后才会用于正式内容</p><h1>简历内容确认</h1><p>每一项代表一段完整经历或一组完整信息。项目名称、职责、技术和成果不会再拆成零散事实。</p></div><button disabled={!selected.size || batch.isPending} onClick={() => batch.mutate()}>确认所选（{selected.size}）</button></header>
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
  return <article className="profile-fact-row">
    <div className="profile-fact-copy">
      <strong>{fact.value}</strong>
      <span>已确认 · 模型置信度 {fact.confidence == null ? "未提供" : `${Math.round(fact.confidence * 100)}%`}</span>
    </div>
    <details className="profile-fact-evidence">
      <summary>查看来源与记录 <small>{fact.sources.length} 处来源 · {fact.revisions.length} 次变更</small></summary>
      <div className="profile-fact-evidence-body">
        <p className="field-key">记录字段：{fact.field_key} · 版本 {fact.version}</p>
        {fact.sources.length > 0
          ? fact.sources.map(source => <blockquote key={source.id}><span>原文证据</span>{source.evidence_text}</blockquote>)
          : <p className="profile-no-evidence">这项内容没有关联原文证据，可能由你手动补充。</p>}
        {fact.revisions.map(revision => <p className="profile-revision" key={revision.id}>版本 {revision.revision_number}：{revision.reason}</p>)}
      </div>
    </details>
  </article>;
}

export function DocumentsPage() {
  const client = useQueryClient(); const navigate = useNavigate(); const documents = useQuery({ queryKey: ["documents"], queryFn: getDocuments });
  const [result, setResult] = useState<string | null>(null);
  const importedDocuments = documents.data?.items.filter((doc) => doc.parse_status === "parsed") ?? [];
  const incompleteDocuments = documents.data?.items.filter((doc) => doc.parse_status !== "parsed") ?? [];
  const finishImport = async (doc: Awaited<ReturnType<typeof importFile>>) => {
    if (doc.duplicate) {
      setResult("该内容已由当前简历提取 Agent 处理，无需重复提取。");
    } else if ((doc.proposed_fact_count ?? 0) > 0) {
      await client.invalidateQueries();
      navigate("/profile/reviews");
      return;
    } else {
      setResult("简历提取 Agent 已完成处理，但没有发现可供确认的职业档案对象。");
    }
    await client.invalidateQueries();
  };
  const upload = useMutation({ mutationFn: importFile, onMutate: () => setResult(null), onSuccess: finishImport });
  const paste = useMutation({ mutationFn: ({ name, text }: { name: string; text: string }) => importText(name, text), onMutate: () => setResult(null), onSuccess: finishImport });
  const importError = upload.error ?? paste.error;
  const configurationError = importError instanceof ApiError && [
    "fact_extraction_provider_authentication_failed",
    "fact_extraction_provider_account_unavailable",
    "fact_extraction_provider_model_unavailable",
    "fact_extraction_provider_connection_failed",
    "fact_extraction_provider_timeout",
    "profile_fact_extraction_unavailable",
  ].includes(importError.code ?? "");
  function pasteSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); paste.mutate({ name: String(data.get("name")), text: String(data.get("text")) }); }
  return <><header className="page-header"><div><p className="eyebrow">我的资料 / 导入</p><h1>导入资料</h1><p>导入简历、项目复盘和经历材料。系统会先提取内容，由你确认后再用于岗位匹配和材料生成。</p></div></header>
    <section className="import-grid"><form className="panel upload-card"><p className="eyebrow">文件导入</p><h2>上传文件</h2><p>支持 TXT、Markdown、PDF、DOCX，最大 10 MB。</p><label className="file-picker"><input type="file" aria-label="选择文件并导入" accept=".txt,.md,.markdown,.pdf,.docx" disabled={upload.isPending} onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} /><span>{upload.isPending ? "正在调用简历提取 Agent…" : "选择文件并导入"}</span></label></form>
      <form className="panel" onSubmit={pasteSubmit}><p className="eyebrow">粘贴文本</p><h2>粘贴简历文本</h2><input name="name" placeholder="资料名称" required /><textarea name="text" rows={7} placeholder="粘贴简历内容" required /><button disabled={paste.isPending}>{paste.isPending ? "正在调用简历提取 Agent…" : "导入并提取内容"}</button></form></section>
    {result && <section className="notice success"><strong>{result}</strong><div className="form-actions"><Link className="download-button" to="/profile/reviews">检查提取结果</Link></div></section>}{importError && <section className="notice error"><strong>导入未完成</strong><p>{importError.message}</p>{configurationError && <div className="form-actions"><Link className="download-button" to="/settings?section=providers">前往 AI 服务设置</Link></div>}</section>}
    <section className="panel"><div className="panel-heading"><h2>导入记录</h2><span>{importedDocuments.length} 份可用 · {incompleteDocuments.length} 份未完成</span></div>{documents.data?.items.map((doc) => {
      const completed = doc.parse_status === "parsed";
      return <div className="document-row" key={doc.id}><div><strong>{doc.file_name}</strong><span>{(doc.size_bytes / 1024).toFixed(1)} KB · {completed ? `已关联 ${doc.fact_source_count} 项档案对象` : "提取未完成，不会用于岗位匹配和材料生成"}</span></div><details><summary>查看导入记录</summary><small>处理方式：{PARSER_LABELS[doc.parser_name] ?? "其他格式"}</small>{!completed && <small>状态：提取失败，修复 AI 服务后可重新导入</small>}<code>内容校验：{doc.sha256.slice(0, 12)}</code></details></div>;
    })}</section>
  </>;
}
