import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { addTaskReminder, cancelTask, completeTask, createTask, getApplications, getDashboard, getJobRecommendations, getMaterials, getNotifications, getProfile, getTasks, postponeTask, readNotification, type CareerTask } from "./api";
import { chinaInputToIso, formatChinaTime, isoToChinaInput, parseBackendTime } from "./time";

const TYPE_LABELS: Record<string, string> = { custom: "自定义", application_plan: "投递计划", follow_up: "跟进", assessment: "测评", written_test: "笔试", interview: "面试", job_deadline: "岗位截止" };
const localInput = (value: Date | number = new Date(Date.now() + 24 * 3600_000)) => isoToChinaInput(new Date(value));

export function DashboardPage() {
  const client = useQueryClient();
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, refetchInterval: 60_000 });
  const opportunities = useQuery({ queryKey: ["job-recommendations", "active"], queryFn: () => getJobRecommendations("active"), refetchInterval: 60_000 });
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: getNotifications });
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const materials = useQuery({ queryKey: ["materials"], queryFn: getMaterials });
  const profile = useQuery({ queryKey: ["profile"], queryFn: getProfile });
  const read = useMutation({ mutationFn: readNotification, onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["notifications"] })]); } });
  const pendingReviews = dashboard.data?.pending_review_count ?? 0;
  const todayTasks = (dashboard.data?.today.length ?? 0) + (dashboard.data?.overdue.length ?? 0);
  const todayOpportunities = opportunities.data?.total ?? 0;
  const readyApplication = applications.data?.items.find(item => item.current_status === "ready_to_apply");
  const preparingApplication = applications.data?.items.find(item => ["discovered", "preparing_materials"].includes(item.current_status));
  const activeApplication = applications.data?.items.find(item => ["assessment", "written_test", "interview"].includes(item.current_status));
  const trackedJobIds = new Set(applications.data?.items.map(item => item.job_post_id));
  const untrackedFinal = materials.data?.items.find(item => item.status === "final" && !trackedJobIds.has(item.job_post_id));
  const confirmedFacts = profile.data?.fact_counts?.confirmed ?? 0;
  const nextAction = pendingReviews > 0
    ? { label: "处理待确认内容", detail: `${pendingReviews} 项内容需要你决定后才能进入正式记录。`, to: "/reviews" }
    : todayTasks > 0
      ? { label: "处理今天的任务", detail: `${todayTasks} 项任务已到期或需要重新安排。`, to: "/tasks" }
      : readyApplication
        ? { label: "确认实际投递", detail: `${readyApplication.company} · ${readyApplication.job_title} 已具备定稿材料。`, to: `/applications/${readyApplication.id}` }
        : preparingApplication
          ? { label: "准备申请材料", detail: `${preparingApplication.company} · ${preparingApplication.job_title} 正在等待材料。`, to: `/materials?jobId=${preparingApplication.job_post_id}` }
          : activeApplication
            ? { label: "推进当前申请", detail: `${activeApplication.company} · ${activeApplication.job_title} 有进行中的流程。`, to: `/applications/${activeApplication.id}` }
            : untrackedFinal
              ? { label: "建立申请进度", detail: `${untrackedFinal.company} · ${untrackedFinal.job_title} 已有定稿材料，但尚未开始跟踪。`, to: "/applications" }
      : todayOpportunities > 0
        ? { label: "查看推荐岗位", detail: `当前有 ${todayOpportunities} 个经过分析的岗位值得关注。`, to: "/opportunities" }
        : confirmedFacts === 0
          ? { label: "导入个人资料", detail: "先建立已确认的职业事实，岗位分析和材料生成才有可靠依据。", to: "/documents" }
          : applications.data?.total
            ? { label: "查看申请总览", detail: "当前没有紧急事项，可以检查所有申请的最新状态。", to: "/applications" }
            : { label: "保存目标岗位", detail: "个人档案已经具备基础信息，下一步导入一个具体岗位。", to: "/job-posts" };
  return <><header className="page-header"><div><p className="eyebrow">今天先做什么</p><h1>今日行动台</h1><p>只展示今天需要关注的机会、任务和确认事项。提醒由后台自动检查。</p></div></header>
    <section className="today-command">
      <div><span>建议下一步</span><h2>{nextAction.label}</h2><p>{nextAction.detail}</p></div>
      <Link className="download-button" to={nextAction.to}>开始处理</Link>
    </section>
    <nav className="quick-start" aria-label="常用操作">
      <Link to="/opportunities"><strong>看推荐</strong><span>处理 Agent 筛选后的岗位</span></Link>
      <Link to="/job-posts"><strong>保存目标岗位</strong><span>导入并分析具体岗位</span></Link>
      <Link to="/applications"><strong>记进度</strong><span>维护投递和面试状态</span></Link>
      <Link to="/materials"><strong>改材料</strong><span>按目标岗位准备简历</span></Link>
    </nav>
    <section className="metric-grid"><article><span>待处理推荐</span><strong>{opportunities.data?.total ?? 0}</strong><small>已完成 JD 解析与个性化筛选</small></article><article><span>今日待办 / 逾期</span><strong>{dashboard.data?.today.length ?? 0} / {dashboard.data?.overdue.length ?? 0}</strong><small>需要完成或重新安排</small></article><article><span>未来流程</span><strong>{dashboard.data?.interviews.length ?? 0}</strong><small>7 天内测评、笔试、面试</small></article><article><span>待确认 / 冲突</span><strong>{dashboard.data?.pending_review_count ?? 0} / {dashboard.data?.conflict_count ?? 0}</strong><small>人工审查与时间冲突</small></article></section>
    <section className="panel today-opportunities"><div className="panel-heading"><h2>推荐岗位</h2><Link to="/opportunities">查看全部</Link></div>{opportunities.data?.items?.slice(0, 5).map((item) => <Link to="/opportunities" key={item.id}><strong>{item.company} · {item.title}</strong><span>{item.location || "地点待确认"} · {item.content.matchedDirections.join("、") || "综合匹配"}</span><em>{item.score} 分 · {item.priority === "high" ? "优先关注" : item.priority === "medium" ? "可以考虑" : "低优先级"}</em></Link>)}{!opportunities.data?.total && <p>当前没有经过筛选后值得关注的新岗位。</p>}</section>
    <div className="dashboard-grid"><TaskSection title="今天" items={dashboard.data?.today ?? []} empty="今天没有到期任务。" /><TaskSection title="即将进行" items={dashboard.data?.interviews ?? []} empty="未来 7 天没有测评或面试。" /><section className="panel notification-panel"><div className="panel-heading"><h2>本地通知</h2><span>{dashboard.data?.unread_notification_count ?? 0} 未读</span></div>{notifications.data?.items.map((item) => <article className={item.status} key={item.id}><strong>{item.title}</strong><p>{item.body}</p><small>{formatChinaTime(item.created_at)}（北京时间）</small>{item.status === "unread" && <button className="text-button" onClick={() => read.mutate(item.id)}>标记已读</button>}</article>)}{!notifications.data?.total && <p>尚无到期提醒。</p>}</section><TaskSection title="逾期事项" items={dashboard.data?.overdue ?? []} empty="没有逾期任务。" /></div>
    </>;
}

function TaskSection({ title, items, empty }: { title: string; items: CareerTask[]; empty: string }) {
  return <section className="panel dashboard-tasks"><div className="panel-heading"><h2>{title}</h2><span>{items.length}</span></div>{items.map((item) => <Link to="/tasks" key={item.id}><strong>{item.title}</strong><span>{formatChinaTime(item.due_at)}（北京时间）</span>{item.conflict_ids.length > 0 && <em>时间冲突</em>}</Link>)}{!items.length && <p>{empty}</p>}</section>;
}

export function TasksPage() {
  const [searchParams] = useSearchParams();
  const selectedApplicationId = searchParams.get("applicationId") ?? "";
  const [applicationId, setApplicationId] = useState(selectedApplicationId);
  useEffect(() => setApplicationId(selectedApplicationId), [selectedApplicationId]);
  const client = useQueryClient(); const tasks = useQuery({ queryKey: ["tasks"], queryFn: getTasks }); const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["tasks"] }), client.invalidateQueries({ queryKey: ["dashboard"] })]); };
  const create = useMutation({ mutationFn: createTask, onSuccess: refresh });
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); create.mutate({ title: String(data.get("title")), task_type: String(data.get("task_type")), due_at: chinaInputToIso(String(data.get("due_at"))), timezone: "Asia/Shanghai", notes: String(data.get("notes")), ...(data.get("application_id") ? { application_id: String(data.get("application_id")) } : {}) }); }
  const pending = tasks.data?.items.filter((item) => item.status === "pending") ?? []; const history = tasks.data?.items.filter((item) => item.status !== "pending") ?? [];
  return <><header className="page-header"><div><p className="eyebrow">行动安排</p><h1>任务与日程</h1></div><span className="health-pill ok">{pending.length} 待办</span></header>
    <section className="panel task-create"><div><h2>新增任务</h2><p>面试时间线会自动同步；这里用于投递计划、跟进和其他自定义事项。</p></div><form className="form-grid" onSubmit={submit}><label>标题<input name="title" required placeholder="例如：完成网申" /></label><label>类型<select name="task_type"><option value="application_plan">投递计划</option><option value="follow_up">跟进</option><option value="custom">自定义</option></select></label><label>时间（北京时间）<input name="due_at" type="datetime-local" defaultValue={localInput()} required /></label><label>关联申请<select name="application_id" value={applicationId} onChange={event => setApplicationId(event.target.value)}><option value="">不关联</option>{applications.data?.items.map((item) => <option key={item.id} value={item.id}>{item.company} · {item.job_title}</option>)}</select></label><label className="wide">备注<input name="notes" /></label><button disabled={create.isPending}>{create.isPending ? "正在创建…" : "创建任务"}</button>{create.error && <p className="form-error">{create.error.message}</p>}</form></section>
    <section className="task-list">{pending.map((item) => <TaskCard task={item} refresh={refresh} key={item.id} />)}</section>{!pending.length && <section className="empty-state"><h2>没有待办任务</h2><p>创建投递计划，或在申请时间线添加未来笔试/面试。</p></section>}
    {history.length > 0 && <section className="panel task-history"><div className="panel-heading"><h2>已处理</h2><span>{history.length}</span></div>{history.map((item) => <p key={item.id}>{item.title}<small>{item.status === "completed" ? "已完成" : "已取消"} · {formatChinaTime(item.updated_at)}（北京时间）</small></p>)}</section>}</>;
}

function TaskCard({ task, refresh }: { task: CareerTask; refresh: () => Promise<void> }) {
  const [postponing, setPostponing] = useState(false); const complete = useMutation({ mutationFn: () => completeTask(task), onSuccess: refresh }); const cancel = useMutation({ mutationFn: () => cancelTask(task), onSuccess: refresh }); const reminder = useMutation({ mutationFn: (offset: number) => addTaskReminder(task.id, offset), onSuccess: refresh }); const postpone = useMutation({ mutationFn: (value: string) => postponeTask(task, chinaInputToIso(value)), onSuccess: async () => { setPostponing(false); await refresh(); } });
  const error = complete.error ?? cancel.error ?? reminder.error ?? postpone.error;
  const hasReminder = (offset: number) => task.reminders.some(item => item.offset_minutes === offset && !["cancelled", "failed"].includes(item.status));
  const statusLabel = (status: string) => ({ pending: "等待提醒", triggered: "已提醒", cancelled: "已取消", failed: "失败" }[status] ?? status);
  const busy = complete.isPending || cancel.isPending || reminder.isPending || postpone.isPending;
  return <article className={`panel task-card ${task.conflict_ids.length ? "conflict" : ""}`}><div><span className="category-tag">{TYPE_LABELS[task.task_type] ?? task.task_type}</span><h2>{task.title}</h2><p>{task.company ? `${task.company} · ${task.job_title}` : "独立任务"}</p><strong>{formatChinaTime(task.due_at)}（北京时间）</strong>{task.conflict_ids.length > 0 && <small className="conflict-label">与 {task.conflict_ids.length} 个日程冲突</small>}</div><div className="task-controls"><button onClick={() => complete.mutate()} disabled={busy}>{complete.isPending ? "正在完成…" : "完成"}</button><details><summary>更多操作</summary><div><button className="secondary" onClick={() => reminder.mutate(60)} disabled={busy || hasReminder(60)}>{hasReminder(60) ? "已设提前 1 小时" : "提前 1 小时提醒"}</button><button className="secondary" onClick={() => reminder.mutate(1440)} disabled={busy || hasReminder(1440)}>{hasReminder(1440) ? "已设提前 1 天" : "提前 1 天提醒"}</button><button className="secondary" onClick={() => setPostponing(!postponing)} disabled={busy}>延后</button><button className="danger" onClick={() => cancel.mutate()} disabled={busy}>取消任务</button></div></details></div>{postponing && <form className="postpone-form" onSubmit={(event) => { event.preventDefault(); postpone.mutate(String(new FormData(event.currentTarget).get("due_at"))); }}><input name="due_at" aria-label="延后时间（北京时间）" type="datetime-local" defaultValue={localInput(parseBackendTime(task.due_at).getTime() + 24 * 3600_000)} required /><button disabled={postpone.isPending}>{postpone.isPending ? "正在保存…" : "保存新时间"}</button></form>}<div className="reminder-list">{task.reminders.map((item) => <small key={item.id}>提前 {item.offset_minutes >= 1440 ? `${item.offset_minutes / 1440} 天` : `${item.offset_minutes} 分钟`} · {statusLabel(item.status)}</small>)}</div>{error && <p className="form-error">{error.message}</p>}</article>;
}
