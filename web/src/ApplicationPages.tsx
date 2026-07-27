import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { addApplicationEvent, archiveApplication, correctApplicationEvent, createApplication, getApplication, getApplicationReviewTasks, getApplications, getJobPosts, proposeApplicationEvent, resolveApplicationProposal, submitApplication, type Application, type ApplicationEvent, type ApplicationReviewTask, type ApplicationStatus } from "./api";
import { chinaInputToIso, formatChinaTime, isoToChinaInput } from "./time";

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  discovered: "已发现", preparing_materials: "准备材料", ready_to_apply: "待投递", submitted: "已投递",
  application_confirmed: "网申确认", assessment: "测评", written_test: "笔试", interview: "面试",
  offer: "Offer", rejected: "已拒绝", withdrawn: "已撤回", archived: "已归档",
};
const NEXT_STATUSES: Partial<Record<ApplicationStatus, ApplicationStatus[]>> = {
  discovered: ["preparing_materials", "ready_to_apply", "withdrawn"],
  preparing_materials: ["ready_to_apply", "withdrawn"],
  ready_to_apply: ["submitted", "withdrawn"],
  submitted: ["application_confirmed", "assessment", "written_test", "interview", "rejected", "withdrawn"],
  application_confirmed: ["assessment", "written_test", "interview", "offer", "rejected", "withdrawn"],
  assessment: ["written_test", "interview", "offer", "rejected", "withdrawn"],
  written_test: ["interview", "offer", "rejected", "withdrawn"],
  interview: ["interview", "offer", "rejected", "withdrawn"],
  offer: ["withdrawn"],
};
const EVENT_TYPE_LABELS: Record<string, string> = {
  application_created: "开始跟踪申请",
  application_status_changed: "申请状态更新",
  application_submitted: "确认已投递",
  application_confirmed: "收到网申确认",
  assessment_scheduled: "收到测评安排",
  written_test_scheduled: "收到笔试安排",
  interview_scheduled: "收到面试安排",
  offer_received: "收到 Offer",
  application_rejected: "申请未通过",
  application_withdrawn: "已撤回申请",
  application_archived: "已归档申请",
  event_corrected: "更正历史记录",
};
const sourceLabel = (source: string) => {
  if (source === "user" || source === "manual_proposal") return "手动记录";
  if (source === "system") return "系统";
  if (source.includes("mail")) return "招聘邮件";
  if (source.includes("agent")) return "AI 分析";
  return "外部来源";
};
const noteLabel = (note: string) => ({
  "Application tracking created from the selected job post.": "已从目标岗位开始跟踪这份申请。",
  "Application materials must be prepared before submission.": "需要先准备申请材料，再确认投递。",
  "Final material is available.": "申请材料已定稿，可以准备投递。",
}[note] ?? note);
const materialTypeLabel = (materialType: string) => ({
  resume: "简历",
  cover_letter: "求职信",
  introduction: "自我介绍",
}[materialType] ?? "申请材料");
const localNow = () => isoToChinaInput();

export function ApplicationsPage() {
  const client = useQueryClient(); const navigate = useNavigate();
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const jobs = useQuery({ queryKey: ["job-posts"], queryFn: getJobPosts });
  const create = useMutation({ mutationFn: createApplication, onSuccess: async (item) => { await client.invalidateQueries({ queryKey: ["applications"] }); navigate(`/applications/${item.id}`); } });
  const tracked = new Set(applications.data?.items.map((item) => item.job_post_id));
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate(String(new FormData(event.currentTarget).get("job_post_id"))); }
  return <><header className="page-header"><div><p className="eyebrow">申请进度</p><h1>申请进度</h1></div><span className="health-pill ok">{applications.data?.total ?? 0} 个流程</span></header>
    <section className="panel application-create"><div><h2>跟踪一个岗位</h2><p>岗位有 Final 材料时进入待投递，否则进入准备材料。状态只由时间线事件推进。</p></div><form onSubmit={submit}><select name="job_post_id" required defaultValue=""><option value="" disabled>选择尚未跟踪的岗位</option>{jobs.data?.items.filter((job) => !tracked.has(job.id)).map((job) => <option key={job.id} value={job.id}>{job.company} · {job.title}</option>)}</select><button disabled={create.isPending}>创建申请流程</button>{create.error && <p className="form-error">{create.error.message}</p>}</form></section>
    {!applications.data?.total && <section className="empty-state"><div className="empty-icon">↗</div><h2>还没有申请记录</h2><p>选择一个真实岗位开始跟踪。系统不会替你投递或联系招聘方。</p></section>}
    <section className="application-board">{applications.data?.items.map((item) => <Link className={`panel application-card status-${item.current_status}`} to={`/applications/${item.id}`} key={item.id}><span className="category-tag">{STATUS_LABELS[item.current_status]}</span><h2>{item.job_title}</h2><p>{item.company}</p><small>事件流 v{item.version} · 已绑定 {item.material_count} 份材料</small></Link>)}</section></>;
}

export function ApplicationDetailPage() {
  const { id = "" } = useParams(); const client = useQueryClient();
  const [searchParams] = useSearchParams();
  const reviewId = searchParams.get("review");
  const query = useQuery({ queryKey: ["application", id], queryFn: () => getApplication(id), enabled: Boolean(id) });
  const reviewTasks = useQuery({ queryKey: ["application-review-tasks"], queryFn: getApplicationReviewTasks });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["application", id] }), client.invalidateQueries({ queryKey: ["applications"] }), client.invalidateQueries({ queryKey: ["application-review-tasks"] })]); };
  const archive = useMutation({ mutationFn: (item: Application) => archiveApplication(item), onSuccess: refresh });
  const resolve = useMutation({ mutationFn: ({ task, resolution }: { task: ApplicationReviewTask; resolution: "confirmed" | "rejected" }) => resolveApplicationProposal(task, resolution, resolution === "confirmed" ? "用户已核对" : "用户判定不准确"), onSuccess: refresh });
  useEffect(() => {
    if (!reviewId || !query.data) return;
    window.requestAnimationFrame(() => {
      document.getElementById(`proposal-${reviewId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [query.data, reviewId]);
  if (query.isLoading) return <section className="empty-state"><p>正在重建申请时间线…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "申请不存在"}</section>;
  const application = query.data;
  const mailEvidence = application.mail_evidence ?? [];
  const tasksByProposal = new Map((reviewTasks.data?.items ?? []).filter(item => item.application_id === application.id).map(item => [item.id, item]));
  return <><header className="page-header job-detail-header"><div><p className="eyebrow"><Link to="/applications">申请进度</Link> / {application.company}</p><h1>{application.job_title}</h1><details><summary>查看记录版本</summary><p>岗位快照 {application.job_content_hash.slice(0, 12)} · 申请版本 {application.version}</p></details></div><span className={`health-pill ${application.current_status === "rejected" ? "blocked" : "ok"}`}>{STATUS_LABELS[application.current_status]}</span></header>
    <section className="panel next-action-card"><div><p className="eyebrow">下一步</p><h2>继续推进这份申请</h2><p>岗位、材料、任务和邮件证据都围绕同一份申请记录关联。</p></div><div className="primary-actions"><Link className="download-button secondary" to={`/job-posts/${application.job_post_id}`}>查看目标岗位</Link><Link className="download-button secondary" to={`/materials?jobId=${application.job_post_id}`}>查看材料</Link><Link className="download-button" to={`/tasks?applicationId=${application.id}`}>创建关联任务</Link></div></section>
    <section className="metric-grid"><article><span>当前状态</span><strong>{STATUS_LABELS[application.current_status]}</strong><small>从不可变事件流重建</small></article><article><span>实际材料</span><strong>{application.material_count}</strong><small>提交时 Final 快照</small></article><article><span>时间线</span><strong>{application.events.length}</strong><small>含更正和历史事件</small></article><article><span>候选事件</span><strong>{application.proposals.filter((item) => item.status === "pending").length}</strong><small>确认前不改变状态</small></article></section>
    {application.current_status === "ready_to_apply" && <SubmissionPanel application={application} onSaved={refresh} />}
    {!['ready_to_apply', 'archived', 'rejected', 'withdrawn'].includes(application.current_status) && <EventPanel application={application} onSaved={refresh} />}
    <section className="panel proposal-list"><div className="panel-heading"><div><p className="eyebrow">待确认进度</p><h2>候选进度</h2></div><span>{application.proposals.filter(item => item.status === "pending").length} 待确认</span></div>{application.proposals.map(proposal => {
      const task = tasksByProposal.get(proposal.id);
      return <article id={`proposal-${proposal.id}`} className={`proposal-card ${reviewId === proposal.id ? "focused-review" : ""}`} key={proposal.id}><div><span className="category-tag">{proposal.source === "manual_proposal" ? "手动补充" : proposal.source.includes("mail") ? "招聘邮件" : "外部来源"}</span><h3>{STATUS_LABELS[proposal.proposed_status]}</h3><p>{formatChinaTime(proposal.occurred_at)}（北京时间）</p><blockquote>{proposal.note}</blockquote></div>{proposal.status === "pending" && task ? <div className="fact-actions"><button disabled={resolve.isPending} onClick={() => resolve.mutate({ task, resolution: "confirmed" })}>确认进度</button><button className="danger" disabled={resolve.isPending} onClick={() => resolve.mutate({ task, resolution: "rejected" })}>拒绝候选</button></div> : <span className={`health-pill ${proposal.status === "confirmed" ? "ok" : "blocked"}`}>{proposal.status === "confirmed" ? "已确认" : proposal.status === "rejected" ? "已拒绝" : "正在加载审查信息"}</span>}</article>;
    })}{!application.proposals.length && <p>目前没有需要确认的候选进度。</p>}{resolve.error && <p className="form-error">{resolve.error.message}</p>}</section>
    <Timeline application={application} onSaved={refresh} />
    <section className="panel mail-evidence-panel"><div className="panel-heading"><div><p className="eyebrow">邮件证据</p><h2>招聘邮件证据</h2></div><span>{mailEvidence.length} 封</span></div>{mailEvidence.map(mail => <article className="mail-intelligence-item" key={mail.analysis_id}><div className="panel-heading"><strong>{mail.subject || "（无主题）"}</strong><Link to="/message-center">消息中心</Link></div><p>{mail.summary}</p><small>{mail.sender} · {mail.sent_at ? `${formatChinaTime(mail.sent_at)}（北京时间）` : "时间未知"} · 匹配度 {Math.round(mail.match_confidence * 100)}%</small>{mail.items.map(item => <details key={item.id}><summary>{item.title} · {item.status === "confirmed" ? "已确认" : item.status === "rejected" ? "已拒绝" : "待审核"}</summary><p>{item.details}</p><blockquote>{item.evidence}</blockquote>{(item.scheduled_at || item.occurred_at) && <time>{formatChinaTime(item.scheduled_at || item.occurred_at!)}（北京时间）</time>}</details>)}</article>)}{!mailEvidence.length && <p>尚无 Agent 匹配到该申请的邮件证据。</p>}</section>
    <section className="panel snapshot-panel"><div className="panel-heading"><h2>投递材料快照</h2><span>{application.material_snapshots.length} 份</span></div>{application.material_snapshots.map((item) => <details key={item.id}><summary>{item.title} · {materialTypeLabel(item.material_type)}</summary><p>{item.rendered_text}</p><code>content {item.content_hash} · PDF {item.export_sha256 ?? "无"}</code></details>)}{!application.material_snapshots.length && <p>确认投递时才会锁定实际使用材料。</p>}</section>
    {application.current_status !== "archived" && <button className="danger archive-button" onClick={() => archive.mutate(application)} disabled={archive.isPending}>归档申请</button>}</>;
}

function SubmissionPanel({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  const submit = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return submitApplication(application, data.getAll("material_ids").map(String), chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: onSaved });
  return <section className="panel workflow-panel"><div><h2>确认已经投递</h2><p>只有你确认后才会标记为“已投递”；所选定稿材料会复制为不可变快照。</p></div><form onSubmit={(event) => { event.preventDefault(); submit.mutate(event.currentTarget); }}><div className="material-choices">{application.available_final_materials.map((item) => <label key={item.id}><input type="checkbox" name="material_ids" value={item.id} /> {item.name} · {materialTypeLabel(item.material_type)}</label>)}</div><label>实际投递时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={localNow()} required /></label><label>备注<input name="note" defaultValue="官网提交" /></label><button disabled={submit.isPending}>确认投递并锁定材料</button>{submit.error && <p className="form-error">{submit.error.message}</p>}</form></section>;
}

function EventPanel({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  const event = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return addApplicationEvent(application, String(data.get("target_status")) as ApplicationStatus, chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: onSaved });
  const proposal = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return proposeApplicationEvent(application, String(data.get("proposed_status")) as ApplicationStatus, chinaInputToIso(String(data.get("proposal_time"))), String(data.get("proposal_note"))); }, onSuccess: onSaved });
  const allowedStatuses = NEXT_STATUSES[application.current_status] ?? [];
  return <section className="application-actions"><form className="panel" onSubmit={(e) => { e.preventDefault(); event.mutate(e.currentTarget); }}><h2>手动添加已确认进度</h2><label>新的申请进度<select name="target_status">{allowedStatuses.map((item) => <option value={item} key={item}>{STATUS_LABELS[item]}</option>)}</select></label><label>发生时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={localNow()} required /></label><input name="note" aria-label="进度备注" placeholder="例如：技术一面，线上会议" /><button>确认并写入时间线</button>{event.error && <p className="form-error">{event.error.message}</p>}</form><form className="panel" onSubmit={(e) => { e.preventDefault(); proposal.mutate(e.currentTarget); }}><h2>添加待确认的进度</h2><label>建议的申请进度<select name="proposed_status">{allowedStatuses.map((item) => <option value={item} key={item}>{STATUS_LABELS[item]}</option>)}</select></label><label>发生时间（北京时间）<input name="proposal_time" type="datetime-local" defaultValue={localNow()} required /></label><input name="proposal_note" aria-label="候选依据或消息摘要" placeholder="候选依据或消息摘要" required /><button className="secondary">送到“待我确认”</button>{proposal.error && <p className="form-error">{proposal.error.message}</p>}</form></section>;
}

function Timeline({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  return <section className="panel timeline"><div className="panel-heading"><h2>完整时间线</h2><span>{application.events.length} 个事件</span></div>{[...application.events].reverse().map((item) => <article className={item.superseded ? "superseded" : ""} key={item.id}><div className="timeline-marker">{item.sequence_number}</div><div><strong>{EVENT_TYPE_LABELS[item.event_type] ?? "申请记录更新"} · {STATUS_LABELS[item.to_status as ApplicationStatus]}</strong><p>{formatChinaTime(item.occurred_at)}（北京时间） · {noteLabel(item.note) || "无备注"}</p><small>来源：{sourceLabel(item.source)}{item.supersedes_event_id ? ` · 更正记录 ${item.supersedes_event_id.slice(0, 8)}` : ""}</small>{!item.superseded && !["application_created", "event_corrected"].includes(item.event_type) && <CorrectionForm application={application} event={item} onSaved={onSaved} />}</div></article>)}</section>;
}

function CorrectionForm({ application, event, onSaved }: { application: Application; event: ApplicationEvent; onSaved: () => Promise<void> }) {
  const [open, setOpen] = useState(false); const correct = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return correctApplicationEvent(application, event.id, chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: async () => { setOpen(false); await onSaved(); } });
  if (!open) return <button className="text-button" onClick={() => setOpen(true)}>更正时间或备注</button>;
  return <form className="correction-form" onSubmit={(e) => { e.preventDefault(); correct.mutate(e.currentTarget); }}><input type="datetime-local" name="occurred_at" aria-label="发生时间（北京时间）" defaultValue={isoToChinaInput(event.occurred_at)} required /><input name="note" defaultValue={event.note} required /><button>追加更正事件</button>{correct.error && <p className="form-error">{correct.error.message}</p>}</form>;
}

export function ApplicationReviewPage() {
  const client = useQueryClient(); const query = useQuery({ queryKey: ["application-review-tasks"], queryFn: getApplicationReviewTasks });
  const resolve = useMutation({ mutationFn: ({ task, resolution }: { task: ApplicationReviewTask; resolution: "confirmed" | "rejected" }) => resolveApplicationProposal(task, resolution, resolution === "confirmed" ? "用户已核对" : "用户判定不准确"), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["application-review-tasks"] }), client.invalidateQueries({ queryKey: ["applications"] })]); } });
  return <><header className="page-header"><div><p className="eyebrow">人工确认</p><h1>进度审查</h1></div><span className="health-pill">{query.data?.items.filter((item) => item.status === "pending").length ?? 0} 待处理</span></header><section className="review-list">{query.data?.items.map((task) => <article className="panel proposal-card" key={task.id}><div><span className="category-tag">{task.source}</span><h2>{task.company} · {task.job_title}</h2><p>建议状态：{STATUS_LABELS[task.proposed_status]} · {formatChinaTime(task.occurred_at)}（北京时间）</p><blockquote>{task.note}</blockquote><Link to={`/applications/${task.application_id}?review=${task.id}`}>查看完整申请记录</Link></div>{task.status === "pending" ? <div className="fact-actions"><button onClick={() => resolve.mutate({ task, resolution: "confirmed" })}>确认进度</button><button className="danger" onClick={() => resolve.mutate({ task, resolution: "rejected" })}>拒绝候选</button></div> : <span className="health-pill ok">已{task.status === "confirmed" ? "确认" : "拒绝"}</span>}</article>)}</section>{!query.data?.total && <section className="empty-state"><h2>没有候选进度</h2><p>邮件和其他数据来源只会生成待确认内容，不会直接改变申请状态。</p></section>}</>;
}
