import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  addManualFact,
  getDocuments,
  getFacts,
  getConfiguration,
  getProfile,
  getProfileMemory,
  getSchedulerRuns,
  setCareerPreference,
  importFile,
  importText,
  reprocessDocument,
  reviseFact,
  ApiError,
  type CandidateFact,
  type ProfileMemory,
} from "./api";
import { formatChinaTime } from "./time";

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
type ProfileView = "facts" | "preferences" | "insights";
type InsightCategory = ProfileMemory["insights"][number]["category"];
const PROFILE_VIEWS: Array<{ id: ProfileView; label: string }> = [
  { id: "facts", label: "个人档案" },
  { id: "preferences", label: "求职偏好" },
  { id: "insights", label: "洞察建议" },
];
const INSIGHT_CATEGORIES: Array<{ id: "all" | InsightCategory; label: string }> = [
  { id: "all", label: "全部" },
  { id: "interview", label: "面试" },
  { id: "application", label: "投递" },
  { id: "resume", label: "简历" },
  { id: "learning", label: "学习" },
  { id: "career_direction", label: "职业方向" },
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
  return <>
    <header className="page-header profile-page-header">
      <div>
        <h1>个人档案</h1>
        {profile.data?.display_name && <p>{profile.data.display_name}</p>}
      </div>
    </header>

    <nav className="profile-view-tabs" aria-label="个人资料">
      {PROFILE_VIEWS.map(item => <button
        type="button"
        className={view === item.id ? "active" : ""}
        aria-current={view === item.id ? "page" : undefined}
        onClick={() => setView(item.id)}
        key={item.id}
      >
        {item.label}
      </button>)}
    </nav>

    {view === "facts" && <>
      <section className="profile-fact-actions" aria-label="个人档案操作">
        <strong>维护档案</strong>
        <div className="profile-fact-action-buttons">
          <Link className="download-button secondary" to="/profile/import">导入资料</Link>
          <Link className="download-button secondary" to="/profile/manual">手动添加</Link>
        </div>
      </section>
      {(facts.data?.total ?? 0) === 0
        ? <section className="empty-state"><div className="empty-icon">＋</div><h2>还没有个人档案</h2><div className="form-actions"><Link className="download-button" to="/profile/import">导入第一份资料</Link><Link className="download-button secondary" to="/profile/manual">手动添加经历</Link></div></section>
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
              <div className="profile-section-heading"><h2>{CATEGORY_LABELS[category] ?? category}</h2></div>
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
  const configuration = useQuery({
    queryKey: ["configuration"],
    queryFn: getConfiguration,
    enabled: view === "insights",
  });
  const schedulerRuns = useQuery({
    queryKey: ["scheduler-runs"],
    queryFn: getSchedulerRuns,
    enabled: view === "insights",
  });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["profile-memory"] }), client.invalidateQueries({ queryKey: ["unified-reviews"] })]); };
  const preference = useMutation({ mutationFn: ({ key, value }: { key: string; value: string[] }) => { const current = query.data?.preferences.find(item => item.preference_key === key); return setCareerPreference(key, value, current?.version ?? null); }, onSuccess: refresh });
  const [preferenceKey, setPreferenceKey] = useState("target_roles");
  const [preferenceDraft, setPreferenceDraft] = useState("");
  const [insightCategory, setInsightCategory] = useState<"all" | InsightCategory>("all");
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
  const error = query.error || preference.error || configuration.error
    || schedulerRuns.error;

  if (view === "preferences") {
    return <section className="profile-memory profile-preference-workspace">
      <section className="panel">
        <div className="panel-heading"><h2>编辑求职偏好</h2></div>
        <form className="form-grid" onSubmit={submitPreference}><label>偏好类型<select name="key" value={preferenceKey} onChange={event => setPreferenceKey(event.target.value)}><option value="target_roles">目标岗位</option><option value="target_cities">目标城市</option><option value="industries">目标行业</option><option value="work_modes">工作方式</option><option value="constraints">限制条件</option></select></label><label className="wide">内容（逗号分隔）<input name="value" value={preferenceDraft} onChange={event => setPreferenceDraft(event.target.value)} required placeholder="例如：后端工程、AI 应用" /></label><button disabled={preference.isPending}>{preference.isPending ? "正在保存…" : "保存求职偏好"}</button></form>
      </section>
      <section className="profile-preference-list" aria-label="当前求职偏好">
        {query.data?.preferences.map(item => <article className="profile-preference-row" key={item.id}><div><span>{PREFERENCE_LABELS[item.preference_key] ?? "求职偏好"}</span><strong>{Array.isArray(item.value) ? item.value.join("、") : JSON.stringify(item.value)}</strong></div><small>版本 {item.version}</small></article>)}
        {!query.data?.preferences.length && <section className="empty-state"><h2>还没有求职偏好</h2></section>}
      </section>
      {error && <section className="notice error">{error.message}</section>}
    </section>;
  }

  if (view === "insights") {
    const scheduler = configuration.data?.configuration.scheduler;
    const automationEnabled = Boolean(scheduler?.enabled && scheduler.profile_maintenance_enabled);
    const profileRun = schedulerRuns.data?.items.find(item => {
      const counters = item.counters;
      return (counters.profile_jobs_processed ?? 0) > 0
        || (counters.profile_insights_created ?? 0) > 0
        || (counters.profile_insights_reused ?? 0) > 0
        || (counters.profile_insight_skipped ?? 0) > 0
        || (counters.profile_insight_failed ?? 0) > 0;
    });
    const currentInsights = query.data?.insights ?? [];
    const categoryCounts = currentInsights.reduce<Record<string, number>>((counts, item) => {
      counts[item.category] = (counts[item.category] ?? 0) + 1;
      return counts;
    }, {});
    const filteredInsights = insightCategory === "all"
      ? currentInsights
      : currentInsights.filter(item => item.category === insightCategory);
    const latestActivityAt = profileRun?.finished_at ?? currentInsights[0]?.created_at;
    return <section className="profile-memory profile-insight-workspace">
      <section className="insight-toolbar">
        <div>
          <h2>当前建议</h2>
          {latestActivityAt && <span>更新于 {formatChinaTime(latestActivityAt)}</span>}
        </div>
        <aside className={`insight-automation ${automationEnabled ? "enabled" : "disabled"}`} aria-label="自动分析状态">
          <div className="insight-status-line"><span>自动分析</span><strong>{automationEnabled ? "已开启" : "未开启"}</strong></div>
          <Link to="/settings?section=automation">{automationEnabled ? `每 ${scheduler?.profile_maintenance_interval_days ?? 3} 天` : "去开启"}</Link>
        </aside>
      </section>

      <div className="insight-category-workspace">
        <nav className="insight-category-rail" aria-label="建议类别">
          {INSIGHT_CATEGORIES.map(category => <button
            type="button"
            className={insightCategory === category.id ? "active" : ""}
            onClick={() => setInsightCategory(category.id)}
            key={category.id}
          >
            <span>{category.label}</span>
            <strong>{category.id === "all" ? currentInsights.length : categoryCounts[category.id] ?? 0}</strong>
          </button>)}
        </nav>
        <section className="insight-guidance-list" aria-label="当前洞察建议">
          {filteredInsights.length > 0
            ? filteredInsights.map(item => <article className={`insight-guidance-item ${item.category}`} key={item.id}>
              <header>
                <strong>{INSIGHT_CATEGORIES.find(category => category.id === item.category)?.label}</strong>
                <span>可信度 {Math.round(item.confidence * 100)}%</span>
              </header>
              <div className="insight-guidance-content">
                <section><span>分析</span><p>{item.analysis}</p></section>
                <section><span>建议</span><p>{item.recommendation}</p></section>
              </div>
            </article>)
            : <section className="quiet-state"><h3>这个方向还没有建议</h3><p>系统会在可信信息变化后自动重新分析。</p></section>}
        </section>
      </div>
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
    <form className="form-grid" onSubmit={submit}><label>经历类型<select name="category" defaultValue="project">{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><input type="hidden" name="field_key" value="manual_entry" /><label className="wide">经历内容<textarea name="value" required rows={5} placeholder="写清楚你做了什么、使用了什么能力、取得了什么结果" /></label><label className="wide">内容来源（可选）<textarea name="source_note" rows={2} placeholder="例如：本人补充，来自项目复盘记录" /></label><button disabled={mutation.isPending}>{mutation.isPending ? "保存中…" : "保存到个人档案"}</button>{mutation.error && <p className="form-error">{mutation.error.message}</p>}</form>
    {saved && <section className="notice success"><strong>经历已保存到个人档案。</strong><div className="form-actions"><Link className="download-button" to="/profile">返回个人档案</Link></div></section>}
  </section>;
}

export function ManualFactPage() {
  return <>
    <header className="page-header"><div><h1>添加一段经历</h1></div></header>
    <ManualFactForm />
  </>;
}

function FactRow({ fact }: { fact: CandidateFact }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [instruction, setInstruction] = useState("");
  const mutation = useMutation({
    mutationFn: () => reviseFact(fact, instruction),
    onSuccess: async () => {
      setEditing(false);
      setInstruction("");
      await Promise.all([
        client.invalidateQueries({ queryKey: ["facts"] }),
        client.invalidateQueries({ queryKey: ["profile"] }),
        client.invalidateQueries({ queryKey: ["profile-memory"] }),
      ]);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    mutation.mutate();
  };
  return <article className="profile-fact-row">
    <div className="profile-fact-copy">
      <strong>{fact.value}</strong>
      <div className="profile-fact-row-actions">
        <button type="button" className="secondary" aria-expanded={editing} onClick={() => setEditing(value => !value)}>修改</button>
      </div>
    </div>
    {editing && <form className="profile-fact-revision-form" onSubmit={submit}>
      <label>修改指示<textarea value={instruction} onChange={event => setInstruction(event.target.value)} rows={3} maxLength={2000} required placeholder="告诉 Agent 需要怎么改" /></label>
      <div className="form-actions">
        <button disabled={mutation.isPending || !instruction.trim()}>{mutation.isPending ? "正在修改…" : "应用修改"}</button>
        <button type="button" className="secondary" onClick={() => { setEditing(false); setInstruction(""); }}>取消</button>
      </div>
      {mutation.error && <p className="form-error">{mutation.error.message}</p>}
    </form>}
    <details className="profile-fact-evidence">
      <summary>查看来源</summary>
      <div className="profile-fact-evidence-body">
        {fact.sources.length > 0
          ? fact.sources.map(source => <blockquote key={source.id}>{source.evidence_text}</blockquote>)
          : <p className="profile-no-evidence">手动添加</p>}
        {fact.revisions.length > 0 && <details className="profile-fact-revisions">
          <summary>修改记录</summary>
          {fact.revisions.map(revision => <p className="profile-revision" key={revision.id}>{revision.reason}</p>)}
        </details>}
      </div>
    </details>
  </article>;
}

export function DocumentsPage() {
  const client = useQueryClient(); const documents = useQuery({ queryKey: ["documents"], queryFn: getDocuments });
  const [result, setResult] = useState<string | null>(null);
  const importedDocuments = documents.data?.items.filter((doc) => doc.parse_status === "parsed") ?? [];
  const incompleteDocuments = documents.data?.items.filter((doc) => doc.parse_status !== "parsed") ?? [];
  const finishImport = async (doc: Awaited<ReturnType<typeof importFile>>) => {
    if (doc.duplicate) {
      setResult("该内容已由当前简历提取 Agent 处理，无需重复提取。");
    } else if ((doc.maintained_fact_count ?? 0) > 0) {
      setResult(`已更新 ${doc.maintained_fact_count} 条个人档案。`);
    } else {
      setResult("Agent 已完成分析，没有发现新的档案内容。");
    }
    await client.invalidateQueries();
  };
  const upload = useMutation({ mutationFn: importFile, onMutate: () => setResult(null), onSuccess: finishImport });
  const paste = useMutation({ mutationFn: ({ name, text }: { name: string; text: string }) => importText(name, text), onMutate: () => setResult(null), onSuccess: finishImport });
  const reprocess = useMutation({
    mutationFn: reprocessDocument,
    onMutate: () => setResult(null),
    onSuccess: async (doc) => {
      setResult(`已重新整理 ${doc.maintained_fact_count ?? 0} 条档案，替换 ${doc.superseded_fact_count ?? 0} 条旧内容。`);
      await client.invalidateQueries();
    },
  });
  const importError = upload.error ?? paste.error ?? reprocess.error;
  const configurationError = importError instanceof ApiError && [
    "fact_extraction_provider_authentication_failed",
    "fact_extraction_provider_account_unavailable",
    "fact_extraction_provider_model_unavailable",
    "fact_extraction_provider_connection_failed",
    "fact_extraction_provider_timeout",
    "profile_fact_extraction_unavailable",
  ].includes(importError.code ?? "");
  function pasteSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); paste.mutate({ name: String(data.get("name")), text: String(data.get("text")) }); }
  return <><header className="page-header"><div><h1>导入资料</h1></div></header>
    <section className="import-grid"><form className="panel upload-card"><p className="eyebrow">文件导入</p><h2>上传文件</h2><p>支持 TXT、Markdown、PDF、DOCX，最大 10 MB。</p><label className="file-picker"><input type="file" aria-label="选择文件并导入" accept=".txt,.md,.markdown,.pdf,.docx" disabled={upload.isPending} onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} /><span>{upload.isPending ? "正在调用简历提取 Agent…" : "选择文件并导入"}</span></label></form>
      <form className="panel" onSubmit={pasteSubmit}><p className="eyebrow">粘贴文本</p><h2>粘贴简历文本</h2><input name="name" placeholder="资料名称" required /><textarea name="text" rows={7} placeholder="粘贴简历内容" required /><button disabled={paste.isPending}>{paste.isPending ? "正在调用简历提取 Agent…" : "导入并提取内容"}</button></form></section>
    {result && <section className="notice success"><strong>{result}</strong><div className="form-actions"><Link className="download-button" to="/profile">返回个人档案</Link></div></section>}{importError && <section className="notice error"><strong>导入未完成</strong><p>{importError.message}</p>{configurationError && <div className="form-actions"><Link className="download-button" to="/settings?section=providers">前往 AI 服务设置</Link></div>}</section>}
    <section className="panel"><div className="panel-heading"><h2>导入记录</h2><span>{importedDocuments.length} 份可用 · {incompleteDocuments.length} 份未完成</span></div>{documents.data?.items.map((doc) => {
      const completed = doc.parse_status === "parsed";
      return <div className="document-row" key={doc.id}><div><strong>{doc.file_name}</strong><span>{(doc.size_bytes / 1024).toFixed(1)} KB · {completed ? `已关联 ${doc.fact_source_count} 项档案对象` : "提取未完成，不会用于岗位匹配和材料生成"}</span></div><div className="document-row-actions">{completed && <button type="button" className="secondary" disabled={reprocess.isPending} onClick={() => reprocess.mutate(doc.id)}>{reprocess.isPending && reprocess.variables === doc.id ? "正在整理…" : "重新整理档案"}</button>}<details><summary>查看导入记录</summary><small>处理方式：{PARSER_LABELS[doc.parser_name] ?? "其他格式"}</small>{!completed && <small>状态：提取失败，修复 AI 服务后可重新导入</small>}<code>内容校验：{doc.sha256.slice(0, 12)}</code></details></div></div>;
    })}</section>
  </>;
}
