import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  confirmFact,
  getAgentRuns,
  getFacts,
  getUnifiedReview,
  getUnifiedReviews,
  editFact,
  rejectFact,
  resolveUnifiedReviewBundle,
  resolveMailIntelligenceItem,
  type CandidateFact,
  type UnifiedReviewTask,
} from "./api";
import { formatChinaTime } from "./time";

const TYPE_LABELS: Record<string, string> = {
  candidate_fact: "职业事实",
  application_event_proposal: "申请进度",
  mail_intelligence_item: "邮件智能",
  profile_insight: "档案洞察",
  strategy_snapshot: "求职策略",
  job_fit_proposal: "岗位语义匹配",
  resume_direction_proposal: "简历方向选择",
  interview_feedback: "面试改进",
};
const SOURCE_LABELS: Record<string, string> = {
  manual_proposal: "手动补充",
  mail_intelligence: "招聘邮件分析",
  profile_agent: "档案 AI 分析",
  job_fit_agent: "岗位匹配 AI 分析",
  resume_direction_agent: "简历方向 AI 分析",
  material_agent_review: "申请材料 AI 审查",
};
const RESOLUTION_LABELS: Record<string, string> = {
  confirmed: "已确认",
  rejected: "已拒绝",
};
const AGENT_TASK_LABELS: Record<string, string> = {
  profile_fact_extraction: "职业事实提取",
  fact_extraction: "职业事实提取",
  mail_intelligence: "招聘邮件分析",
  profile_insight: "职业档案洞察",
  job_fit: "岗位匹配分析",
  resume_direction: "简历方向建议",
  resume_drafting: "申请材料撰写",
  material_review: "申请材料复核",
};
const AGENT_STATUS_LABELS: Record<string, string> = {
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
  pending: "等待运行",
};
const FACT_CATEGORY_LABELS: Record<string, string> = {
  basic: "基础信息",
  education: "教育经历",
  internship: "实习经历",
  work: "工作经历",
  project: "项目经历",
  skill: "技能与能力",
  award: "奖项荣誉",
  certificate: "证书资质",
  preference: "求职偏好",
  constraint: "限制条件",
};

function factReviewTitle(item: UnifiedReviewTask, fact: CandidateFact) {
  return item.title
    .replace(/^确认完整档案对象：/, "")
    .replace(/^确认手动职业事实：/, "")
    .trim() || fact.field_key;
}

function FactReviewRow({
  item,
  fact,
  busy,
  onConfirm,
  onReject,
  onEdit,
}: {
  item: UnifiedReviewTask;
  fact: CandidateFact;
  busy: boolean;
  onConfirm: () => void;
  onReject: () => void;
  onEdit: (value: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact.value);
  useEffect(() => setDraft(fact.value), [fact.value]);
  const changed = draft.trim() !== fact.value;
  const confidence = fact.confidence == null ? null : Math.round(fact.confidence * 100);

  return <article className={`fact-review-row ${fact.status !== "proposed" ? "resolved" : ""}`}>
    <div className="fact-review-heading">
      <div>
        <div className="fact-review-meta">
          <span className="category-tag">{FACT_CATEGORY_LABELS[fact.category] ?? fact.category}</span>
          {confidence != null && <span className="confidence">模型置信度 {confidence}%</span>}
        </div>
        <h3>{factReviewTitle(item, fact)}</h3>
      </div>
      <span className={`health-pill ${fact.status === "confirmed" ? "ok" : fact.status === "rejected" ? "blocked" : ""}`}>
        {fact.status === "proposed" ? "等待确认" : fact.status === "confirmed" ? "已确认" : "已拒绝"}
      </span>
    </div>

    <div className="agent-proposal">
      <strong>Agent 整理结果</strong>
      {editing
        ? <textarea
            aria-label={`修改 ${factReviewTitle(item, fact)}`}
            rows={Math.min(10, Math.max(4, draft.split("\n").length + 1))}
            value={draft}
            onChange={event => setDraft(event.target.value)}
          />
        : <p>{fact.value}</p>}
    </div>

    {!!fact.sources.length && <details className="evidence-details">
      <summary>对照原文证据（{fact.sources.length} 处）</summary>
      {fact.sources.map(source => <blockquote key={source.id}>{source.evidence_text}</blockquote>)}
    </details>}

    {fact.status === "proposed" && <div className="fact-actions">
      {editing ? <>
        <button
          type="button"
          disabled={busy || !draft.trim() || !changed}
          onClick={async () => {
            await onEdit(draft.trim());
            setEditing(false);
          }}
        >
          保存修改
        </button>
        <button type="button" className="secondary" disabled={busy} onClick={() => {
          setDraft(fact.value);
          setEditing(false);
        }}>
          取消
        </button>
      </> : <>
        <button type="button" disabled={busy} onClick={onConfirm}>确认这一项</button>
        <button type="button" className="secondary" disabled={busy} onClick={() => setEditing(true)}>修改</button>
        <button type="button" className="danger" disabled={busy} onClick={onReject}>拒绝</button>
      </>}
    </div>}
  </article>;
}

function ProfileBundleReview({
  bundle,
  factMap,
  expanded,
  onToggle,
  onRefresh,
}: {
  bundle: UnifiedReviewTask;
  factMap: Map<string, CandidateFact>;
  expanded: boolean;
  onToggle?: () => void;
  onRefresh: () => Promise<void>;
}) {
  const pendingFacts = bundle.items
    .map(item => factMap.get(item.entity_id))
    .filter((fact): fact is CandidateFact => Boolean(fact && fact.status === "proposed"));
  const single = useMutation({
    mutationFn: ({ fact, resolution }: { fact: CandidateFact; resolution: "confirmed" | "rejected" }) =>
      resolution === "confirmed" ? confirmFact(fact) : rejectFact(fact),
    onSuccess: onRefresh,
  });
  const confirmAll = useMutation({
    mutationFn: () => resolveUnifiedReviewBundle(bundle, "confirmed"),
    onSuccess: onRefresh,
  });
  const rejectAll = useMutation({
    mutationFn: () => resolveUnifiedReviewBundle(bundle, "rejected"),
    onSuccess: onRefresh,
  });
  const edit = useMutation({
    mutationFn: ({ fact, value }: { fact: CandidateFact; value: string }) => editFact(fact, value),
    onSuccess: onRefresh,
  });
  const busy = single.isPending || confirmAll.isPending || rejectAll.isPending || edit.isPending;
  const error = single.error ?? confirmAll.error ?? rejectAll.error ?? edit.error;

  return <div className="review-bundle-workbench">
    <div className="review-bundle-toolbar">
      <div>
        <strong>{pendingFacts.length ? `还有 ${pendingFacts.length} 项待确认` : "这组内容已处理"}</strong>
        <span>可以逐项核对，也可以在确认内容准确后整组处理。</span>
      </div>
      <div className="form-actions">
        {pendingFacts.length > 0 && <button type="button" disabled={busy} onClick={() => confirmAll.mutate()}>
          确认整组（{pendingFacts.length}）
        </button>}
        {onToggle && <button type="button" className="secondary" aria-expanded={expanded} onClick={onToggle}>
          {expanded ? "收起内容" : "展开核对"}
        </button>}
        {!onToggle && <Link className="download-button secondary" to="/reviews">返回审查中心</Link>}
        {pendingFacts.length > 0 && <details className="secondary-actions">
          <summary>更多操作</summary>
          <button type="button" className="danger" disabled={busy} onClick={() => rejectAll.mutate()}>
            拒绝整组
          </button>
        </details>}
      </div>
    </div>

    {expanded && <div className="review-fact-stack">
      <section className="agent-analysis-note" aria-label="Agent 分析说明">
        <strong>这些内容已经过 Agent 提取和归组</strong>
        <p>“Agent 整理结果”是模型形成的完整职业对象；“原文证据”是用于核对的简历原句。置信度只表示模型对抽取结果的把握，不代表内容已经确认。</p>
      </section>
      {bundle.items.map(item => {
        const fact = factMap.get(item.entity_id);
        if (!fact) return <section className="notice warning" key={item.id}>对应的候选事实暂时无法读取，请刷新后重试。</section>;
        return <FactReviewRow
          key={item.id}
          item={item}
          fact={fact}
          busy={busy}
          onConfirm={() => single.mutate({ fact, resolution: "confirmed" })}
          onReject={() => single.mutate({ fact, resolution: "rejected" })}
          onEdit={value => edit.mutateAsync({ fact, value }).then(() => undefined)}
        />;
      })}
    </div>}
    {error && <section className="notice error">{error.message}</section>}
  </div>;
}

export function ReviewCenterPage({ profileOnly = false }: { profileOnly?: boolean }) {
  const client = useQueryClient();
  const [status, setStatus] = useState("open");
  const [expandedBundles, setExpandedBundles] = useState<Set<string>>(new Set());
  const query = useQuery({
    queryKey: ["unified-reviews", status],
    queryFn: () => getUnifiedReviews(status),
  });
  const facts = useQuery({
    queryKey: ["facts", "review-center"],
    queryFn: () => getFacts(),
  });
  const factMap = useMemo(
    () => new Map((facts.data?.items ?? []).map(fact => [fact.id, fact])),
    [facts.data],
  );
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["unified-reviews"] }),
      client.invalidateQueries({ queryKey: ["unified-review"] }),
      client.invalidateQueries({ queryKey: ["facts"] }),
      client.invalidateQueries({ queryKey: ["profile"] }),
    ]);
  };
  const resolve = useMutation({
    mutationFn: ({ item, resolution }: {
      item: UnifiedReviewTask; resolution: "confirmed" | "rejected";
    }) => resolveMailIntelligenceItem(
      { id: item.entity_id, version: item.version },
      resolution,
    ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["unified-reviews"] }),
        client.invalidateQueries({ queryKey: ["mail-messages"] }),
        client.invalidateQueries({ queryKey: ["applications"] }),
        client.invalidateQueries({ queryKey: ["tasks"] }),
      ]);
    },
  });
  const visibleItems = (query.data?.items ?? []).filter(item => !profileOnly || (
    (item.entity_type === "review_bundle" && item.bundle_type === "profile_section")
    || item.entity_type === "candidate_fact"
  ));
  return <>
    <header className="page-header"><div><p className="eyebrow">{profileOnly ? "我的资料 / 内容确认" : "待我确认"}</p><h1>{profileOnly ? "确认档案内容" : "审查中心"}</h1></div><span className="health-pill">{visibleItems.length} 项</span></header>
    <section className="notice opportunity-note"><strong>智能分析只会生成待确认建议</strong><p>职业事实可直接在本页展开核对；只有你确认后，内容才会写入正式记录。</p></section>
    <div className="opportunity-filters"><button className={status === "open" ? "" : "secondary"} onClick={() => setStatus("open")}>待处理</button><button className={status === "resolved" ? "" : "secondary"} onClick={() => setStatus("resolved")}>已处理</button></div>
    {(query.error || facts.error || resolve.error) && <section className="notice error">{query.error?.message ?? facts.error?.message ?? resolve.error?.message}</section>}
    <section className="review-runtime-list">{visibleItems.map((item) => {
      const isProfileBundle = item.entity_type === "review_bundle" && item.bundle_type === "profile_section";
      const expanded = expandedBundles.has(item.id);
      return <article className={`panel review-runtime-card ${expanded ? "expanded" : ""}`} key={item.id}>
        <div className="review-runtime-summary">
          <div>
            <span className="category-tag">{item.entity_type === "review_bundle" ? `${item.item_count} 项组成一组` : TYPE_LABELS[item.entity_type] ?? "待确认事项"}</span>
            <h2>{item.title}</h2>
            <p>{item.summary}</p>
            {!isProfileBundle && item.items?.length > 0 && <ul className="review-preview">{item.items.slice(0, 3).map(child => <li key={child.id}>{child.title}</li>)}</ul>}
            <small>{SOURCE_LABELS[item.source_type] ?? "业务流程"} · {formatChinaTime(item.created_at)}（北京时间）</small>
          </div>
          <div className="review-runtime-actions">
            <span className={`health-pill ${item.status === "resolved" ? "ok" : ""}`}>{item.status === "open" ? "等待确认" : RESOLUTION_LABELS[item.resolution ?? ""] ?? "已处理"}</span>
            {!isProfileBundle && (item.status === "open" && item.can_resolve_inline
              ? <div className="form-actions"><button type="button" disabled={resolve.isPending} onClick={() => resolve.mutate({ item, resolution: "confirmed" })}>确认</button><button type="button" className="secondary" disabled={resolve.isPending} onClick={() => resolve.mutate({ item, resolution: "rejected" })}>拒绝</button></div>
              : <Link to={item.target_url}>{item.entity_subtype === "create_application" ? "建立或关联申请" : "查看并处理"}</Link>)}
            {item.agent_run_id && <details><summary>Agent 运行记录</summary><small>{item.agent_run_id}</small></details>}
          </div>
        </div>
        {isProfileBundle && <ProfileBundleReview
          bundle={item}
          factMap={factMap}
          expanded={expanded}
          onToggle={() => setExpandedBundles(current => {
            const next = new Set(current);
            if (next.has(item.id)) next.delete(item.id);
            else next.add(item.id);
            return next;
          })}
          onRefresh={refresh}
        />}
      </article>;
    })}</section>
    {!query.isLoading && !visibleItems.length && <section className="empty-state"><h2>{status === "open" ? "没有待审事项" : "没有已处理记录"}</h2><p>{profileOnly ? "导入资料或手动补充经历后，需要确认的档案内容会出现在这里。" : "所有正式变化都保留业务事件和审查结果。"}</p></section>}
  </>;
}

export function ReviewBundlePage() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const review = useQuery({ queryKey: ["unified-review", id], queryFn: () => getUnifiedReview(id) });
  const facts = useQuery({ queryKey: ["facts", "all-for-review"], queryFn: () => getFacts() });
  const factMap = useMemo(
    () => new Map((facts.data?.items ?? []).map(fact => [fact.id, fact])),
    [facts.data],
  );
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["unified-review", id] }),
      client.invalidateQueries({ queryKey: ["unified-reviews"] }),
      client.invalidateQueries({ queryKey: ["facts"] }),
      client.invalidateQueries({ queryKey: ["profile"] }),
    ]);
  };
  if (review.isLoading) return <section className="empty-state"><p>正在读取确认内容…</p></section>;
  if (review.error || !review.data) return <section className="notice error">{review.error?.message ?? "确认内容不存在。"}</section>;
  const bundle = review.data;
  if (bundle.bundle_type === "mail_analysis") {
    return <><Link className="back-link" to="/reviews">返回审查中心</Link><header className="page-header"><div><p className="eyebrow">招聘邮件分析</p><h1>{bundle.title}</h1><p>{bundle.summary}</p></div></header><section className="panel"><h2>为什么需要确认</h2><p>一封邮件可能同时包含进度、日程和准备事项。请在邮件详情中结合原文证据一次处理，系统不会仅凭分析结果直接修改申请档案。</p><div className="form-actions"><Link className="download-button" to={bundle.target_url}>查看邮件、证据和处理结果</Link><Link className="download-button secondary" to="/reviews">返回审查中心</Link></div></section></>;
  }
  return <><Link className="back-link" to="/reviews">返回审查中心</Link>
    <header className="page-header"><div><p className="eyebrow">职业档案业务块</p><h1>{bundle.title}</h1><p>{bundle.summary}</p></div></header>
    <section className="notice opportunity-note"><strong>确认后会发生什么</strong><p>确认内容将进入可信职业档案，可用于岗位匹配和申请材料；拒绝内容只保留审计记录，不参与后续生成。</p></section>
    <ProfileBundleReview bundle={bundle} factMap={factMap} expanded onRefresh={refresh} />
  </>;
}

export function AgentRunsPage() {
  const query = useQuery({ queryKey: ["agent-runs"], queryFn: getAgentRuns });
  return <>
    <header className="page-header"><div><p className="eyebrow">高级诊断</p><h1>智能功能记录</h1></div><span className="health-pill ok">{query.data?.total ?? 0} 次</span></header>
    <section className="notice opportunity-note"><strong>这里记录智能功能的执行结果</strong><p>可用于确认使用的模型、执行时间和失败原因。技术审计信息默认折叠，且不展示简历或邮件全文。</p></section>
    {query.error && <section className="notice error">{query.error.message}</section>}
    <section className="agent-run-list">{query.data?.items.map((run) => <article className="panel agent-run-card" key={run.id}>
      <div><span className={`health-pill ${run.status === "succeeded" ? "ok" : "blocked"}`}>{AGENT_STATUS_LABELS[run.status] ?? run.status}</span><h2>{AGENT_TASK_LABELS[run.task_type] ?? run.task_type}</h2><p>{run.provider ?? "未记录服务商"} · {run.model ?? run.implementation}</p></div>
      <dl><div><dt>执行时间</dt><dd>{formatChinaTime(run.created_at)}（北京时间）</dd></div><div><dt>耗时</dt><dd>{run.duration_ms ?? "—"} ms</dd></div></dl>
      {run.error_code && <p className="form-error">执行失败，请展开技术审计信息查看错误代码。</p>}
      <details className="audit-details"><summary>查看技术审计信息</summary><dl>{run.error_code && <div><dt>错误代码</dt><dd>{run.error_code}</dd></div>}<div><dt>Schema / Prompt</dt><dd>{run.schema_version} / {run.prompt_version ?? "—"}</dd></div><div><dt>输入对象</dt><dd>{run.input_entity_type ?? "—"} · {run.input_entity_id?.slice(0, 12) ?? "—"}</dd></div><div><dt>Token</dt><dd>{run.input_tokens ?? "—"} / {run.output_tokens ?? "—"}</dd></div><div><dt>重试次数</dt><dd>{run.retry_count}</dd></div><div><dt>敏感级别</dt><dd>{run.sensitivity}</dd></div><div><dt>工具调用</dt><dd>{run.tool_calls.length}</dd></div></dl></details>
    </article>)}</section>
    {!query.isLoading && !query.data?.total && <section className="empty-state"><h2>尚无智能功能记录</h2><p>导入简历并执行内容提取后会生成第一条记录。</p></section>}
  </>;
}
