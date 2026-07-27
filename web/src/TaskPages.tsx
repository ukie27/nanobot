import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { addTaskReminder, cancelTask, completeTask, createTask, getApplications, getDashboard, getNotifications, getTasks, getTodayOpportunities, postponeTask, readNotification, runDueSchedules, type CareerTask } from "./api";
import { chinaInputToIso, formatChinaTime, isoToChinaInput, parseBackendTime } from "./time";

const TYPE_LABELS: Record<string, string> = { custom: "自定义", application_plan: "投递计划", follow_up: "跟进", assessment: "测评", written_test: "笔试", interview: "面试", job_deadline: "岗位截止" };
const localInput = (value: Date | number = new Date(Date.now() + 24 * 3600_000)) => isoToChinaInput(new Date(value));

export function DashboardPage() {
  const client = useQueryClient();
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, refetchInterval: 60_000 });
  const opportunities = useQuery({ queryKey: ["opportunities", "today"], queryFn: getTodayOpportunities, refetchInterval: 60_000 });
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: getNotifications });
  const run = useMutation({ mutationFn: runDueSchedules, onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["notifications"] }), client.invalidateQueries({ queryKey: ["tasks"] })]); } });
  const read = useMutation({ mutationFn: readNotification, onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["notifications"] })]); } });
  return <><header className="page-header"><div><p className="eyebrow">今日行动</p><h1>今日</h1></div><button className="secondary" onClick={() => run.mutate()} disabled={run.isPending}>立即检查提醒</button></header>
    <section className="metric-grid"><article><span>今日新机会</span><strong>{opportunities.data?.total ?? 0}</strong><small>北京时间当天由牛客收录</small></article><article><span>今日待办 / 逾期</span><strong>{dashboard.data?.today.length ?? 0} / {dashboard.data?.overdue.length ?? 0}</strong><small>需要完成或重新安排</small></article><article><span>未来流程</span><strong>{dashboard.data?.interviews.length ?? 0}</strong><small>7 天内测评、笔试、面试</small></article><article><span>待确认 / 冲突</span><strong>{dashboard.data?.pending_review_count ?? 0} / {dashboard.data?.conflict_count ?? 0}</strong><small>人工审查与时间冲突</small></article></section>
    <section className="panel today-opportunities"><div className="panel-heading"><h2>今日招聘机会</h2><Link to="/opportunities">查看全部</Link></div>{opportunities.data?.items.slice(0, 5).map((item) => <Link to={`/job-posts?opportunityId=${encodeURIComponent(item.id)}`} key={item.id}><strong>{item.company} · {item.batch}</strong><span>{item.cities || "城市待确认"} · {item.careers || "方向待确认"}</span><em>{item.linked_jobs.length ? `已关联 ${item.linked_jobs.length} 个具体岗位` : "导入具体 JD"}</em></Link>)}{!opportunities.data?.total && <p>北京时间今天尚未收录新机会。</p>}</section>
    <div className="dashboard-grid"><TaskSection title="今天" items={dashboard.data?.today ?? []} empty="今天没有到期任务。" /><TaskSection title="即将进行" items={dashboard.data?.interviews ?? []} empty="未来 7 天没有测评或面试。" /><section className="panel notification-panel"><div className="panel-heading"><h2>本地通知</h2><span>{dashboard.data?.unread_notification_count ?? 0} 未读</span></div>{notifications.data?.items.map((item) => <article className={item.status} key={item.id}><strong>{item.title}</strong><p>{item.body}</p><small>{formatChinaTime(item.created_at)}（北京时间）</small>{item.status === "unread" && <button className="text-button" onClick={() => read.mutate(item.id)}>标记已读</button>}</article>)}{!notifications.data?.total && <p>尚无到期提醒。</p>}</section><TaskSection title="逾期事项" items={dashboard.data?.overdue ?? []} empty="没有逾期任务。" /></div>
    {(run.data || run.error) && <section className={`notice ${run.error ? "error" : "success"}`}>{run.error?.message ?? `已处理 ${run.data?.schedules_processed} 个计划，触发 ${run.data?.reminders_triggered} 个提醒。`}</section>}</>;
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
    <section className="panel task-create"><div><h2>新增真实任务</h2><p>面试时间线会自动同步；这里用于投递计划、跟进和其他自定义事项。</p></div><form className="form-grid" onSubmit={submit}><label>标题<input name="title" required placeholder="例如：完成网申" /></label><label>类型<select name="task_type"><option value="application_plan">投递计划</option><option value="follow_up">跟进</option><option value="custom">自定义</option></select></label><label>时间（北京时间）<input name="due_at" type="datetime-local" defaultValue={localInput()} required /></label><label>关联申请<select name="application_id" value={applicationId} onChange={event => setApplicationId(event.target.value)}><option value="">不关联</option>{applications.data?.items.map((item) => <option key={item.id} value={item.id}>{item.company} · {item.job_title}</option>)}</select></label><label className="wide">备注<input name="notes" /></label><button>创建任务</button>{create.error && <p className="form-error">{create.error.message}</p>}</form></section>
    <section className="task-list">{pending.map((item) => <TaskCard task={item} refresh={refresh} key={item.id} />)}</section>{!pending.length && <section className="empty-state"><h2>没有待办任务</h2><p>创建投递计划，或在申请时间线添加未来笔试/面试。</p></section>}
    {history.length > 0 && <section className="panel task-history"><div className="panel-heading"><h2>已处理</h2><span>{history.length}</span></div>{history.map((item) => <p key={item.id}>{item.title}<small>{item.status === "completed" ? "已完成" : "已取消"} · {formatChinaTime(item.updated_at)}（北京时间）</small></p>)}</section>}</>;
}

function TaskCard({ task, refresh }: { task: CareerTask; refresh: () => Promise<void> }) {
  const [postponing, setPostponing] = useState(false); const complete = useMutation({ mutationFn: () => completeTask(task), onSuccess: refresh }); const cancel = useMutation({ mutationFn: () => cancelTask(task), onSuccess: refresh }); const reminder = useMutation({ mutationFn: (offset: number) => addTaskReminder(task.id, offset), onSuccess: refresh }); const postpone = useMutation({ mutationFn: (value: string) => postponeTask(task, chinaInputToIso(value)), onSuccess: async () => { setPostponing(false); await refresh(); } });
  const error = complete.error ?? cancel.error ?? reminder.error ?? postpone.error;
  return <article className={`panel task-card ${task.conflict_ids.length ? "conflict" : ""}`}><div><span className="category-tag">{TYPE_LABELS[task.task_type] ?? task.task_type}</span><h2>{task.title}</h2><p>{task.company ? `${task.company} · ${task.job_title}` : "独立任务"}</p><strong>{formatChinaTime(task.due_at)}（北京时间）</strong>{task.conflict_ids.length > 0 && <small className="conflict-label">与 {task.conflict_ids.length} 个日程冲突</small>}</div><div className="task-controls"><button onClick={() => complete.mutate()}>完成</button><button className="secondary" onClick={() => reminder.mutate(60)}>提前 1 小时</button><button className="secondary" onClick={() => reminder.mutate(1440)}>提前 1 天</button><button className="secondary" onClick={() => setPostponing(!postponing)}>延后</button><button className="danger" onClick={() => cancel.mutate()}>取消</button></div>{postponing && <form className="postpone-form" onSubmit={(event) => { event.preventDefault(); postpone.mutate(String(new FormData(event.currentTarget).get("due_at"))); }}><input name="due_at" aria-label="延后时间（北京时间）" type="datetime-local" defaultValue={localInput(parseBackendTime(task.due_at).getTime() + 24 * 3600_000)} required /><button>保存新时间</button></form>}<div className="reminder-list">{task.reminders.map((item) => <small key={item.id}>提醒：提前 {item.offset_minutes} 分钟 · {item.status}</small>)}</div>{error && <p className="form-error">{error.message}</p>}</article>;
}
