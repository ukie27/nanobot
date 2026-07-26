import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { addApplicationEvent, archiveApplication, correctApplicationEvent, createApplication, getApplication, getApplicationReviewTasks, getApplications, getJobPosts, proposeApplicationEvent, resolveApplicationProposal, submitApplication, type Application, type ApplicationEvent, type ApplicationReviewTask, type ApplicationStatus } from "./api";
import { chinaInputToIso, formatChinaTime, isoToChinaInput } from "./time";

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  discovered: "已发现", preparing_materials: "准备材料", ready_to_apply: "待投递", submitted: "已投递",
  application_confirmed: "网申确认", assessment: "测评", written_test: "笔试", interview: "面试",
  offer: "Offer", rejected: "已拒绝", withdrawn: "已撤回", archived: "已归档",
};
const NEXT_STATUSES: ApplicationStatus[] = ["ready_to_apply", "application_confirmed", "assessment", "written_test", "interview", "offer", "rejected", "withdrawn"];
const localNow = () => isoToChinaInput();

export function ApplicationsPage() {
  const client = useQueryClient(); const navigate = useNavigate();
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const jobs = useQuery({ queryKey: ["job-posts"], queryFn: getJobPosts });
  const create = useMutation({ mutationFn: createApplication, onSuccess: async (item) => { await client.invalidateQueries({ queryKey: ["applications"] }); navigate(`/applications/${item.id}`); } });
  const tracked = new Set(applications.data?.items.map((item) => item.job_post_id));
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate(String(new FormData(event.currentTarget).get("job_post_id"))); }
  return <><header className="page-header"><div><p className="eyebrow">APPLICATION EVENT STREAM</p><h1>申请看板</h1></div><span className="health-pill ok">{applications.data?.total ?? 0} 个流程</span></header>
    <section className="panel application-create"><div><h2>跟踪一个岗位</h2><p>岗位有 Final 材料时进入待投递，否则进入准备材料。状态只由时间线事件推进。</p></div><form onSubmit={submit}><select name="job_post_id" required defaultValue=""><option value="" disabled>选择尚未跟踪的岗位</option>{jobs.data?.items.filter((job) => !tracked.has(job.id)).map((job) => <option key={job.id} value={job.id}>{job.company} · {job.title}</option>)}</select><button disabled={create.isPending}>创建申请流程</button>{create.error && <p className="form-error">{create.error.message}</p>}</form></section>
    {!applications.data?.total && <section className="empty-state"><div className="empty-icon">↗</div><h2>还没有申请记录</h2><p>选择一个真实岗位开始跟踪。系统不会替你投递或联系招聘方。</p></section>}
    <section className="application-board">{applications.data?.items.map((item) => <Link className={`panel application-card status-${item.current_status}`} to={`/applications/${item.id}`} key={item.id}><span className="category-tag">{STATUS_LABELS[item.current_status]}</span><h2>{item.job_title}</h2><p>{item.company}</p><small>事件流 v{item.version} · 已绑定 {item.material_count} 份材料</small></Link>)}</section></>;
}

export function ApplicationDetailPage() {
  const { id = "" } = useParams(); const client = useQueryClient();
  const query = useQuery({ queryKey: ["application", id], queryFn: () => getApplication(id), enabled: Boolean(id) });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["application", id] }), client.invalidateQueries({ queryKey: ["applications"] }), client.invalidateQueries({ queryKey: ["application-review-tasks"] })]); };
  const archive = useMutation({ mutationFn: (item: Application) => archiveApplication(item), onSuccess: refresh });
  if (query.isLoading) return <section className="empty-state"><p>正在重建申请时间线…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "申请不存在"}</section>;
  const application = query.data;
  const mailEvidence = application.mail_evidence ?? [];
  return <><header className="page-header job-detail-header"><div><p className="eyebrow"><Link to="/applications">申请看板</Link> / {application.company}</p><h1>{application.job_title}</h1><p>岗位快照 {application.job_content_hash.slice(0, 12)} · 流程 v{application.version}</p></div><span className={`health-pill ${application.current_status === "rejected" ? "blocked" : "ok"}`}>{STATUS_LABELS[application.current_status]}</span></header>
    <section className="metric-grid"><article><span>当前状态</span><strong>{STATUS_LABELS[application.current_status]}</strong><small>从不可变事件流重建</small></article><article><span>实际材料</span><strong>{application.material_count}</strong><small>提交时 Final 快照</small></article><article><span>时间线</span><strong>{application.events.length}</strong><small>含更正和历史事件</small></article><article><span>候选事件</span><strong>{application.proposals.filter((item) => item.status === "pending").length}</strong><small>确认前不改变状态</small></article></section>
    {application.current_status === "ready_to_apply" && <SubmissionPanel application={application} onSaved={refresh} />}
    {!['ready_to_apply', 'archived', 'rejected', 'withdrawn'].includes(application.current_status) && <EventPanel application={application} onSaved={refresh} />}
    <Timeline application={application} onSaved={refresh} />
    <section className="panel mail-evidence-panel"><div className="panel-heading"><div><p className="eyebrow">MAIL EVIDENCE</p><h2>招聘邮件证据</h2></div><span>{mailEvidence.length} 封</span></div>{mailEvidence.map(mail => <article className="mail-intelligence-item" key={mail.analysis_id}><div className="panel-heading"><strong>{mail.subject || "（无主题）"}</strong><Link to="/mail">消息中心</Link></div><p>{mail.summary}</p><small>{mail.sender} · {mail.sent_at ? `${formatChinaTime(mail.sent_at)}（北京时间）` : "时间未知"} · 匹配度 {Math.round(mail.match_confidence * 100)}%</small>{mail.items.map(item => <details key={item.id}><summary>{item.title} · {item.status === "confirmed" ? "已确认" : item.status === "rejected" ? "已拒绝" : "待审核"}</summary><p>{item.details}</p><blockquote>{item.evidence}</blockquote>{(item.scheduled_at || item.occurred_at) && <time>{formatChinaTime(item.scheduled_at || item.occurred_at!)}（北京时间）</time>}</details>)}</article>)}{!mailEvidence.length && <p>尚无 Agent 匹配到该申请的邮件证据。</p>}</section>
    <section className="panel snapshot-panel"><div className="panel-heading"><h2>投递材料快照</h2><span>{application.material_snapshots.length} 份</span></div>{application.material_snapshots.map((item) => <details key={item.id}><summary>{item.title} · {item.material_type}</summary><p>{item.rendered_text}</p><code>content {item.content_hash} · PDF {item.export_sha256 ?? "无"}</code></details>)}{!application.material_snapshots.length && <p>确认投递时才会锁定实际使用材料。</p>}</section>
    {application.current_status !== "archived" && <button className="danger archive-button" onClick={() => archive.mutate(application)} disabled={archive.isPending}>归档申请</button>}</>;
}

function SubmissionPanel({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  const submit = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return submitApplication(application, data.getAll("material_ids").map(String), chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: onSaved });
  return <section className="panel workflow-panel"><div><h2>确认已经投递</h2><p>只有你确认后才进入 submitted；所选 Final 材料会复制为不可变快照。</p></div><form onSubmit={(event) => { event.preventDefault(); submit.mutate(event.currentTarget); }}><div className="material-choices">{application.available_final_materials.map((item) => <label key={item.id}><input type="checkbox" name="material_ids" value={item.id} /> {item.name} · {item.material_type}</label>)}</div><label>实际投递时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={localNow()} required /></label><label>备注<input name="note" defaultValue="官网提交" /></label><button disabled={submit.isPending}>确认投递并锁定材料</button>{submit.error && <p className="form-error">{submit.error.message}</p>}</form></section>;
}

function EventPanel({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  const event = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return addApplicationEvent(application, String(data.get("target_status")) as ApplicationStatus, chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: onSaved });
  const proposal = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return proposeApplicationEvent(application, String(data.get("proposed_status")) as ApplicationStatus, chinaInputToIso(String(data.get("proposal_time"))), String(data.get("proposal_note"))); }, onSuccess: onSaved });
  return <section className="application-actions"><form className="panel" onSubmit={(e) => { e.preventDefault(); event.mutate(e.currentTarget); }}><h2>手动添加已确认事件</h2><select name="target_status">{NEXT_STATUSES.map((item) => <option value={item} key={item}>{STATUS_LABELS[item]}</option>)}</select><label>发生时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={localNow()} required /></label><input name="note" placeholder="例如：技术一面，线上会议" /><button>写入不可变时间线</button>{event.error && <p className="form-error">{event.error.message}</p>}</form><form className="panel" onSubmit={(e) => { e.preventDefault(); proposal.mutate(e.currentTarget); }}><h2>添加待审事件候选</h2><select name="proposed_status">{NEXT_STATUSES.map((item) => <option value={item} key={item}>{STATUS_LABELS[item]}</option>)}</select><label>发生时间（北京时间）<input name="proposal_time" type="datetime-local" defaultValue={localNow()} required /></label><input name="proposal_note" placeholder="候选依据或消息摘要" required /><button className="secondary">送入审查中心</button>{proposal.error && <p className="form-error">{proposal.error.message}</p>}</form></section>;
}

function Timeline({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  return <section className="panel timeline"><div className="panel-heading"><h2>完整时间线</h2><span>{application.events.length} 个事件</span></div>{[...application.events].reverse().map((item) => <article className={item.superseded ? "superseded" : ""} key={item.id}><div className="timeline-marker">{item.sequence_number}</div><div><strong>{item.event_type} · {STATUS_LABELS[item.to_status as ApplicationStatus]}</strong><p>{formatChinaTime(item.occurred_at)}（北京时间） · {item.note || "无备注"}</p><small>来源 {item.source}{item.supersedes_event_id ? ` · 更正 ${item.supersedes_event_id.slice(0, 8)}` : ""}</small>{!item.superseded && !["application_created", "event_corrected"].includes(item.event_type) && <CorrectionForm application={application} event={item} onSaved={onSaved} />}</div></article>)}</section>;
}

function CorrectionForm({ application, event, onSaved }: { application: Application; event: ApplicationEvent; onSaved: () => Promise<void> }) {
  const [open, setOpen] = useState(false); const correct = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return correctApplicationEvent(application, event.id, chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: async () => { setOpen(false); await onSaved(); } });
  if (!open) return <button className="text-button" onClick={() => setOpen(true)}>更正时间或备注</button>;
  return <form className="correction-form" onSubmit={(e) => { e.preventDefault(); correct.mutate(e.currentTarget); }}><input type="datetime-local" name="occurred_at" aria-label="发生时间（北京时间）" defaultValue={isoToChinaInput(event.occurred_at)} required /><input name="note" defaultValue={event.note} required /><button>追加更正事件</button>{correct.error && <p className="form-error">{correct.error.message}</p>}</form>;
}

export function ApplicationReviewPage() {
  const client = useQueryClient(); const query = useQuery({ queryKey: ["application-review-tasks"], queryFn: getApplicationReviewTasks });
  const resolve = useMutation({ mutationFn: ({ task, resolution }: { task: ApplicationReviewTask; resolution: "confirmed" | "rejected" }) => resolveApplicationProposal(task, resolution, resolution === "confirmed" ? "用户已核对" : "用户判定不准确"), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["application-review-tasks"] }), client.invalidateQueries({ queryKey: ["applications"] })]); } });
  return <><header className="page-header"><div><p className="eyebrow">HUMAN-IN-THE-LOOP</p><h1>事件审查中心</h1></div><span className="health-pill">{query.data?.items.filter((item) => item.status === "pending").length ?? 0} 待处理</span></header><section className="review-list">{query.data?.items.map((task) => <article className="panel proposal-card" key={task.id}><div><span className="category-tag">{task.source}</span><h2>{task.company} · {task.job_title}</h2><p>建议状态：{STATUS_LABELS[task.proposed_status]} · {formatChinaTime(task.occurred_at)}（北京时间）</p><blockquote>{task.note}</blockquote></div>{task.status === "pending" ? <div className="fact-actions"><button onClick={() => resolve.mutate({ task, resolution: "confirmed" })}>确认事件</button><button className="danger" onClick={() => resolve.mutate({ task, resolution: "rejected" })}>拒绝候选</button></div> : <span className="health-pill ok">已{task.status === "confirmed" ? "确认" : "拒绝"}</span>}</article>)}</section>{!query.data?.total && <section className="empty-state"><h2>没有事件候选</h2><p>邮件 Connector 也只能把候选送到这里，不能直接改变申请状态。</p></section>}</>;
}
