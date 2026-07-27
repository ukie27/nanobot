import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  getIntegrationHealth, getWorkspaceOverview, getWorkspaceReviews, searchWorkspace,
} from "./api";
import { formatChinaTime } from "./time";

const FUNNEL_LABELS: Record<string, string> = {
  preparing_materials: "准备材料", ready_to_apply: "待投递", submitted: "已投递",
  application_confirmed: "网申确认", assessment: "测评", written_test: "笔试",
  interview: "面试", offer: "Offer", rejected: "拒绝", withdrawn: "撤回", archived: "归档",
};

export function WorkspacePage() {
  const [query, setQuery] = useState("");
  const overview = useQuery({ queryKey: ["workspace-overview"], queryFn: getWorkspaceOverview });
  const reviews = useQuery({ queryKey: ["workspace-reviews"], queryFn: getWorkspaceReviews });
  const health = useQuery({ queryKey: ["integration-health"], queryFn: getIntegrationHealth });
  const search = useQuery({ queryKey: ["workspace-search", query], queryFn: () => searchWorkspace(query), enabled: query.length >= 2 });
  function searchSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setQuery(String(new FormData(event.currentTarget).get("query")).trim()); }
  return <><header className="page-header"><div><p className="eyebrow">整体进展</p><h1>求职进展</h1><p>集中查看申请漏斗、近期变化和跨模块数据一致性。</p></div><span className="health-pill ok">数据已联动</span></header>
    <section className="metric-grid"><article><span>申请总数</span><strong>{overview.data?.total_applications ?? 0}</strong><small>完整漏斗</small></article><article><span>待审事项</span><strong>{overview.data?.pending_review_count ?? 0}</strong><small>统一人工确认</small></article><article><span>即将面试</span><strong>{overview.data?.upcoming_interview_count ?? 0}</strong><small>面试中心</small></article><article><span>改进项</span><strong>{overview.data?.active_improvement_count ?? 0}</strong><small>长期反馈闭环</small></article></section>
    <section className="brief-grid"><article className="panel"><h2>每日简报</h2><p>{overview.data?.daily_brief.summary}</p></article><article className="panel"><h2>每周简报</h2><p>{overview.data?.weekly_brief.summary}</p></article></section>
    <section className="panel"><div className="panel-heading"><h2>申请漏斗</h2><span>{Object.keys(overview.data?.funnel ?? {}).length} 阶段</span></div><div className="funnel-grid">{Object.entries(overview.data?.funnel ?? {}).map(([status, count]) => <article key={status}><span>{FUNNEL_LABELS[status] ?? status}</span><strong>{count}</strong></article>)}</div></section>
    <section className="workspace-grid"><section className="panel"><div className="panel-heading"><h2>跨模块搜索</h2><span>岗位/材料/申请/任务/面试</span></div><form className="workspace-search" onSubmit={searchSubmit}><input name="query" minLength={2} placeholder="输入公司、岗位或任务关键词" required /><button>搜索</button></form>{search.data?.items.map((item) => <Link className="search-result" to={item.url} key={`${item.type}-${item.id}`}><strong>{item.title}</strong><span>{item.type} · {item.subtitle}</span></Link>)}</section>
      <section className="panel"><div className="panel-heading"><h2>待我确认</h2><span>{reviews.data?.total ?? 0}</span></div>{reviews.data?.items.map((item) => <Link className="search-result" to={item.target_url} key={item.id}><strong>{item.title}</strong><span>{formatChinaTime(item.created_at)}（北京时间）</span></Link>)}</section></section>
    <section className="panel"><div className="panel-heading"><h2>最近状态变化</h2><span>{overview.data?.recent_changes.length ?? 0}</span></div>{overview.data?.recent_changes.map((item) => <Link className="change-row" to={`/applications/${item.application_id}`} key={item.id}><strong>{item.event_type} → {item.to_status}</strong><span>{formatChinaTime(item.occurred_at)}（北京时间） · {item.note || "无备注"}</span></Link>)}</section>
    <section className="panel"><div className="panel-heading"><h2>跨模块一致性</h2><span className={`health-pill ${health.data?.status === "ok" ? "ok" : ""}`}>{health.data?.status === "ok" ? "一致" : `${health.data?.issue_count ?? 0} 项需关注`}</span></div>{health.data?.issues.length === 0 && <p>申请、事件、投递快照、面试、任务和审查队列的关联完整。</p>}{health.data?.issues.map((item) => <article className="change-row" key={item.code}><strong>{item.severity === "error" ? "错误" : "提醒"} · {item.count} 项</strong><span>{item.message}（{item.code}）</span></article>)}</section>
  </>;
}
