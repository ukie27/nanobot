import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { getAgentRuns, getUnifiedReviews } from "./api";
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

export function ReviewCenterPage() {
  const [status, setStatus] = useState("open");
  const query = useQuery({
    queryKey: ["unified-reviews", status],
    queryFn: () => getUnifiedReviews(status),
  });
  return <>
    <header className="page-header"><div><p className="eyebrow">HUMAN REVIEW QUEUE</p><h1>审查中心</h1></div><span className="health-pill">{query.data?.total ?? 0} 项</span></header>
    <section className="notice opportunity-note"><strong>Agent 只能提出候选，不能直接改变正式业务事实</strong><p>职业事实、申请事件和面试改进统一进入这里；点击后仍由对应业务模块执行确认或拒绝。</p></section>
    <div className="opportunity-filters"><button className={status === "open" ? "" : "secondary"} onClick={() => setStatus("open")}>待处理</button><button className={status === "resolved" ? "" : "secondary"} onClick={() => setStatus("resolved")}>已处理</button></div>
    {query.error && <section className="notice error">{query.error.message}</section>}
    <section className="review-runtime-list">{query.data?.items.map((item) => <Link className="panel review-runtime-card" to={item.target_url} key={item.id}><div><span className="category-tag">{TYPE_LABELS[item.entity_type] ?? item.entity_type}</span><h2>{item.title}</h2><p>{item.summary}</p><small>{item.source_type} · {formatChinaTime(item.created_at)}（北京时间）</small></div><div><span className={`health-pill ${item.status === "resolved" ? "ok" : ""}`}>{item.status === "open" ? "等待确认" : `已${item.resolution ?? "处理"}`}</span>{item.agent_run_id && <small>AgentRun {item.agent_run_id.slice(0, 8)}</small>}</div></Link>)}</section>
    {!query.isLoading && !query.data?.total && <section className="empty-state"><h2>{status === "open" ? "没有待审事项" : "没有已处理记录"}</h2><p>所有正式变化都保留业务事件和审查结果。</p></section>}
  </>;
}

export function AgentRunsPage() {
  const query = useQuery({ queryKey: ["agent-runs"], queryFn: getAgentRuns });
  return <>
    <header className="page-header"><div><p className="eyebrow">AUDITED TASK EXECUTION</p><h1>Agent 运行记录</h1></div><span className="health-pill ok">{query.data?.total ?? 0} 次</span></header>
    <section className="notice opportunity-note"><strong>这里是业务 Agent 审计记录，不是聊天 Session</strong><p>记录实际模型、Schema、输入输出哈希、工具摘要、耗时和错误；不展示简历或邮件全文。</p></section>
    {query.error && <section className="notice error">{query.error.message}</section>}
    <section className="agent-run-list">{query.data?.items.map((run) => <article className="panel agent-run-card" key={run.id}><div><span className={`health-pill ${run.status === "succeeded" ? "ok" : "blocked"}`}>{run.status}</span><h2>{run.task_type}</h2><p>{run.provider ?? "未记录 Provider"} · {run.model ?? run.implementation}</p></div><dl><div><dt>Schema / Prompt</dt><dd>{run.schema_version} / {run.prompt_version ?? "—"}</dd></div><div><dt>输入对象</dt><dd>{run.input_entity_type ?? "—"} · {run.input_entity_id?.slice(0, 12) ?? "—"}</dd></div><div><dt>Token</dt><dd>{run.input_tokens ?? "—"} / {run.output_tokens ?? "—"}</dd></div><div><dt>耗时</dt><dd>{run.duration_ms ?? "—"} ms</dd></div></dl><small>{formatChinaTime(run.created_at)}（北京时间） · {run.sensitivity} · tools {run.tool_calls.length}</small>{run.error_code && <p className="form-error">{run.error_code}</p>}</article>)}</section>
    {!query.isLoading && !query.data?.total && <section className="empty-state"><h2>尚无 Agent 运行</h2><p>导入简历并执行事实提取后会生成第一条审计记录。</p></section>}
  </>;
}
