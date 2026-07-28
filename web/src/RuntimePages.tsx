import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { getAgentRuns, getUnifiedReviews, resolveMailIntelligenceItem, type UnifiedReviewTask } from "./api";
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

export function ReviewCenterPage() {
  const client = useQueryClient();
  const [status, setStatus] = useState("open");
  const query = useQuery({
    queryKey: ["unified-reviews", status],
    queryFn: () => getUnifiedReviews(status),
  });
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
  return <>
    <header className="page-header"><div><p className="eyebrow">待我确认</p><h1>审查中心</h1></div><span className="health-pill">{query.data?.total ?? 0} 项</span></header>
    <section className="notice opportunity-note"><strong>智能分析只会生成待确认建议</strong><p>职业事实、申请进度和面试改进统一进入这里；只有你确认后，内容才会写入正式记录。</p></section>
    <div className="opportunity-filters"><button className={status === "open" ? "" : "secondary"} onClick={() => setStatus("open")}>待处理</button><button className={status === "resolved" ? "" : "secondary"} onClick={() => setStatus("resolved")}>已处理</button></div>
    {(query.error || resolve.error) && <section className="notice error">{query.error?.message ?? resolve.error?.message}</section>}
    <section className="review-runtime-list">{query.data?.items.map((item) => <article className="panel review-runtime-card" key={item.id}><div><span className="category-tag">{TYPE_LABELS[item.entity_type] ?? "待确认事项"}</span><h2>{item.title}</h2><p>{item.summary}</p><small>{SOURCE_LABELS[item.source_type] ?? "业务流程"} · {formatChinaTime(item.created_at)}（北京时间）</small></div><div className="review-runtime-actions"><span className={`health-pill ${item.status === "resolved" ? "ok" : ""}`}>{item.status === "open" ? "等待确认" : RESOLUTION_LABELS[item.resolution ?? ""] ?? "已处理"}</span>{item.status === "open" && item.can_resolve_inline ? <div className="form-actions"><button type="button" disabled={resolve.isPending} onClick={() => resolve.mutate({ item, resolution: "confirmed" })}>确认</button><button type="button" className="secondary" disabled={resolve.isPending} onClick={() => resolve.mutate({ item, resolution: "rejected" })}>拒绝</button></div> : <Link to={item.target_url}>{item.entity_subtype === "create_application" ? "建立或关联申请" : "查看并处理"}</Link>}{item.agent_run_id && <details><summary>运行记录</summary><small>{item.agent_run_id}</small></details>}</div></article>)}</section>
    {!query.isLoading && !query.data?.total && <section className="empty-state"><h2>{status === "open" ? "没有待审事项" : "没有已处理记录"}</h2><p>所有正式变化都保留业务事件和审查结果。</p></section>}
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
