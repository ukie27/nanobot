import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  getOpportunities,
  triageOpportunity,
  type OpportunityTriageStatus,
  type RecruitmentOpportunity,
} from "./api";
import { formatChinaTime } from "./time";

const STATUS_LABELS: Record<OpportunityTriageStatus, string> = {
  new: "未处理",
  following: "已关注",
  ignored: "已忽略",
};

export function OpportunityPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<OpportunityTriageStatus | undefined>();
  const query = useQuery({
    queryKey: ["opportunities", filter ?? "all"],
    queryFn: () => getOpportunities(filter),
  });
  const triage = useMutation({
    mutationFn: ({ item, status }: { item: RecruitmentOpportunity; status: OpportunityTriageStatus }) =>
      triageOpportunity(item, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
  });

  const filters: Array<[OpportunityTriageStatus | undefined, string]> = [
    [undefined, "全部"],
    ["new", "未处理"],
    ["following", "已关注"],
    ["ignored", "已忽略"],
  ];

  return <>
    <header className="page-header">
      <div><p className="eyebrow">RECRUITMENT OPPORTUNITIES</p><h1>招聘机会</h1></div>
      <span className="health-pill ok">{query.data?.total ?? 0} 条机会</span>
    </header>
    <section className="notice opportunity-note">
      <strong>这里收录招聘项目线索，不代表具体岗位 JD</strong>
      <p>牛客每日同步进入机会池。关注后请从官方入口查看具体职位，再将真实 JD 导入<Link to="/job-posts">具体岗位池</Link>进行匹配和材料生成。</p>
    </section>
    <div className="opportunity-filters" aria-label="机会状态筛选">
      {filters.map(([value, label]) => <button
        type="button"
        className={filter === value ? "" : "secondary"}
        key={label}
        onClick={() => setFilter(value)}
      >{label}</button>)}
    </div>
    {query.error && <section className="notice error">{query.error.message}</section>}
    {triage.error && <section className="notice error">{triage.error.message}</section>}
    {!query.isLoading && !query.data?.total && <section className="empty-state">
      <div className="empty-icon">＋</div><h2>当前筛选下没有招聘机会</h2>
      <p>在数据来源中启用牛客校招日程。自动任务只同步北京时间当天的新信息，历史一个月需由你手动触发。</p>
    </section>}
    <section className="opportunity-list">
      {query.data?.items.map((item) => <article className="panel opportunity-card" key={item.id}>
        <div className="opportunity-main">
          <div className="opportunity-title">
            <span className={`health-pill ${item.triage_status === "following" ? "ok" : ""}`}>
              {STATUS_LABELS[item.triage_status]}
            </span>
            <span className="category-tag">{item.industries || "行业待确认"}</span>
          </div>
          <h2>{item.company} · {item.batch}</h2>
          <p>{item.cities || "城市待确认"} · {item.careers || "岗位方向待确认"}</p>
          {item.evaluation && <p className="opportunity-evaluation">{item.evaluation}</p>}
          <small>牛客收录：{formatChinaTime(item.last_collected_at)}（北京时间） · v{item.version}</small>
          {item.application_ends_at && <small>网申截止：{formatChinaTime(item.application_ends_at)}（北京时间）</small>}
        </div>
        <div className="opportunity-actions">
          <a className="download-button" href={item.application_url} target="_blank" rel="noreferrer">打开官方投递入口</a>
          {item.announcement_url && <a href={item.announcement_url} target="_blank" rel="noreferrer">查看招聘公告</a>}
          <Link className="secondary action-link" to={`/job-posts?opportunityId=${encodeURIComponent(item.id)}`}>导入具体 JD</Link>
          {item.linked_jobs.map((job) => <Link className="text-button" to={`/job-posts/${job.id}`} key={job.id}>已关联：{job.title}</Link>)}
          {item.triage_status !== "following" && <button type="button" onClick={() => triage.mutate({ item, status: "following" })}>关注</button>}
          {item.triage_status !== "ignored" && <button type="button" className="secondary" onClick={() => triage.mutate({ item, status: "ignored" })}>忽略</button>}
          {item.triage_status !== "new" && <button type="button" className="text-button" onClick={() => triage.mutate({ item, status: "new" })}>恢复为未处理</button>}
        </div>
      </article>)}
    </section>
  </>;
}
