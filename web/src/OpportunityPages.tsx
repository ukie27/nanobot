import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  acceptJobRecommendation,
  dismissJobRecommendation,
  getJobRecommendations,
  getNowcoderConnector,
  scanNowcoderConnector,
  type JobRecommendation,
  type SyncRun,
} from "./api";
import { formatChinaTime } from "./time";

const PRIORITY_LABELS = { high: "优先关注", medium: "可以考虑", low: "低优先级" } as const;

function commandId(item: JobRecommendation) {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `recommendation-accepted:${item.id}:${random}`;
}

export function OpportunityPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [lastSync, setLastSync] = useState<SyncRun | null>(null);
  const recommendations = useQuery({
    queryKey: ["job-recommendations", "active"],
    queryFn: () => getJobRecommendations("active"),
  });
  const connector = useQuery({
    queryKey: ["nowcoder-connector"],
    queryFn: getNowcoderConnector,
  });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["job-recommendations"] }),
      queryClient.invalidateQueries({ queryKey: ["applications"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["nowcoder-connector"] }),
    ]);
  };
  const sync = useMutation({ mutationFn: () => scanNowcoderConnector(0), onSuccess: async data => {
    setLastSync(data);
    await refresh();
  } });
  const dismiss = useMutation({ mutationFn: dismissJobRecommendation, onSuccess: refresh });
  const accept = useMutation({
    mutationFn: (item: JobRecommendation) =>
      acceptJobRecommendation(item, commandId(item)),
    onSuccess: async (item) => {
      await refresh();
      if (item.application_id) navigate(`/applications/${item.application_id}`);
    },
  });

  const total = recommendations.data?.total ?? 0;
  const sourceEnabled = Boolean(connector.data?.enabled);
  const sourceHealthy = connector.data?.health_status === "healthy";
  const hasSuccessfulSync = Boolean(connector.data?.last_success_at);
  const error = recommendations.error ?? connector.error ?? sync.error ?? dismiss.error ?? accept.error;

  return <>
    <header className="page-header">
      <div>
        <p className="eyebrow">自动发现 · JD 解析 · 个性化筛选</p>
        <h1>岗位推荐</h1>
        <p>这里只展示 Agent 根据可信档案和已确认方向筛选后，值得你关注的具体岗位。</p>
      </div>
      <span className="health-pill ok">{total} 个待处理</span>
    </header>
    <section className="notice opportunity-note">
      <strong>推荐池不是牛客信息搬运</strong>
      <p>系统每天按北京时间获取当天新增，访问官方招聘地址解析具体 JD，再结合已确认事实、偏好、洞察和手动方向分析。打开官网不会自动改变进度；加入投递计划后，需要在申请详情绑定实际简历并确认投递。</p>
    </section>
    {error && <section className="notice error" role="alert">{error.message}</section>}
    {lastSync && <section className="notice success recommendation-sync-result" aria-live="polite">
      <strong>本次岗位推荐处理完成</strong>
      <p>来源发现 {lastSync.discovered_count} 条，新增来源记录 {lastSync.created_count} 条，更新 {lastSync.updated_count} 条，重复 {lastSync.duplicate_count} 条，隔离 {lastSync.quarantined_count} 条。</p>
      <p>发现具体 JD {lastSync.jd_discovered ?? 0} 个，成功导入 {lastSync.jd_imported ?? 0} 个；生成推荐 {lastSync.recommendations_created ?? 0} 个，筛除 {lastSync.recommendations_rejected ?? 0} 个。</p>
      {(lastSync.recommendations_created ?? 0) === 0 && <p>没有出现推荐卡片，表示本次来源记录未形成完整可用的 JD，或岗位未通过方向、硬门槛和可信证据筛选。</p>}
      {Boolean((lastSync.jd_discovery_failed ?? 0) + (lastSync.recommendation_failed ?? 0)) && <p>其中 JD 获取失败 {lastSync.jd_discovery_failed ?? 0} 个，推荐分析失败 {lastSync.recommendation_failed ?? 0} 个；失败项不会进入正式推荐池。</p>}
    </section>}
    {!recommendations.isLoading && total === 0 && <section className="empty-state">
      <div className="empty-icon">荐</div>
      {!sourceEnabled ? <>
        <h2>尚未启用牛客岗位来源</h2>
        <p>先配置 OpenCLI、登录牛客并启用每日任务，系统才能自动发现和分析岗位。</p>
        <Link className="download-button" to="/settings?section=sources">配置数据来源</Link>
      </> : !sourceHealthy ? <>
        <h2>牛客岗位来源当前不可用</h2>
        <p>请在设置中测试 OpenCLI 和牛客登录状态，连接恢复后再执行同步。</p>
        <Link className="download-button" to="/settings?section=sources">检查数据来源</Link>
      </> : !hasSuccessfulSync ? <>
        <h2>今天还没有运行岗位推荐</h2>
        <p>立即运行会获取北京时间当天新增，并自动完成 JD 解析、匹配分析和筛选。</p>
        <button type="button" disabled={sync.isPending} onClick={() => sync.mutate()}>
          {sync.isPending ? "正在分析…" : "运行今天的推荐"}
        </button>
      </> : <>
        <h2>当前没有值得关注的新岗位</h2>
        <p>今天的来源已经处理完成；不满足方向或硬门槛的岗位不会进入这里。</p>
        <div className="empty-actions">
          <button type="button" className="secondary" disabled={sync.isPending} onClick={() => sync.mutate()}>
            {sync.isPending ? "正在分析…" : "再次检查今天"}
          </button>
          <Link className="download-button secondary" to="/profile">检查我的档案与偏好</Link>
        </div>
      </>}
    </section>}
    <section className="recommendation-list">
      {recommendations.data?.items?.map(item => <RecommendationCard
        item={item}
        busy={dismiss.isPending || accept.isPending}
        onDismiss={() => dismiss.mutate(item)}
        onAccept={() => accept.mutate(item)}
        key={item.id}
      />)}
    </section>
  </>;
}

function RecommendationCard({
  item,
  busy,
  onDismiss,
  onAccept,
}: {
  item: JobRecommendation;
  busy: boolean;
  onDismiss: () => void;
  onAccept: () => void;
}) {
  const content = item.content;
  return <article className={`panel recommendation-card priority-${item.priority}`}>
    <div className="recommendation-heading">
      <div>
        <div className="recommendation-badges">
          <span className={`priority-badge ${item.priority}`}>{PRIORITY_LABELS[item.priority]}</span>
          <span className="score-badge">{item.score} 分</span>
          {content.matchedDirections.map(direction =>
            <span className="category-tag" key={direction}>{direction}</span>)}
        </div>
        <h2>{item.company} · {item.title}</h2>
        <p>{item.location || "地点待确认"}{item.deadline_at ? ` · 截止 ${formatChinaTime(item.deadline_at)}` : ""}</p>
      </div>
      <small>推荐于 {formatChinaTime(item.recommended_at)}（北京时间）</small>
    </div>
    <p className="recommendation-summary">{content.summary}</p>
    <div className="recommendation-reasons">
      <section>
        <h3>为什么推荐</h3>
        <ul>{content.strengths.map(value => <li key={value}>{value}</li>)}</ul>
        {content.preferenceReasons.length > 0 && <ul className="preference-list">
          {content.preferenceReasons.map(value => <li key={value}>{value}</li>)}
        </ul>}
      </section>
      <section>
        <h3>需要留意</h3>
        {content.gaps.length
          ? <ul>{content.gaps.map(value => <li key={value}>{value}</li>)}</ul>
          : <p>没有识别到明显能力缺口。</p>}
        <strong className="action-suggestion">{content.actionSuggestion}</strong>
      </section>
    </div>
    <details className="audit-details">
      <summary>查看逐项匹配依据</summary>
      <div className="assessment-list">{content.assessments.map(assessment =>
        <article key={assessment.requirementId}>
          <span className={assessment.decision === "matched" ? "matched" : "gap"}>
            {assessment.decision === "matched" ? "匹配" : "缺口"}
          </span>
          <p>{assessment.rationale}</p>
        </article>)}
      </div>
    </details>
    <div className="recommendation-actions">
      {item.application_url
        ? <a className="download-button" href={item.application_url} target="_blank" rel="noreferrer">去官网投递</a>
        : <span className="disabled-reason">官方投递地址暂不可用</span>}
      <button type="button" disabled={busy} onClick={onAccept}>加入投递计划</button>
      <button type="button" className="secondary" disabled={busy} onClick={onDismiss}>移除</button>
      <Link className="action-link secondary" to={`/job-posts/${item.job_post_id}`}>查看完整 JD</Link>
    </div>
  </article>;
}
