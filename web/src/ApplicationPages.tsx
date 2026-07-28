import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { addApplicationEvent, archiveApplication, correctApplicationEvent, createApplication, getApplication, getApplicationReviewTasks, getApplications, getJobPosts, resolveApplicationProposal, submitApplication, type Application, type ApplicationEvent, type ApplicationReviewTask, type ApplicationStatus } from "./api";
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

function nextAction(application: Application) {
  if (["discovered", "preparing_materials"].includes(application.current_status)) {
    return { title: "准备申请材料", detail: "先完成针对该岗位的材料，再进入投递确认。", to: `/materials?jobId=${application.job_post_id}`, label: "准备材料" };
  }
  if (application.current_status === "ready_to_apply") {
    return { title: "确认实际投递", detail: "核对并锁定实际使用的定稿材料，然后记录投递时间。", to: "#submission", label: "前往投递确认" };
  }
  if (["submitted", "application_confirmed"].includes(application.current_status)) {
    return { title: "关注招聘反馈", detail: "同步招聘邮件，或创建跟进任务，避免错过后续安排。", to: "/message-center", label: "查看招聘邮件" };
  }
  if (["assessment", "written_test", "interview"].includes(application.current_status)) {
    return { title: "推进当前流程", detail: "检查近期任务与面试准备内容。", to: application.current_status === "interview" ? "/interviews" : `/tasks?applicationId=${application.id}`, label: application.current_status === "interview" ? "进入面试中心" : "查看任务" };
  }
  if (application.current_status === "offer") {
    return { title: "记录决定与截止时间", detail: "创建任务，记录 Offer 比较、沟通和最终决定。", to: `/tasks?applicationId=${application.id}`, label: "创建决定任务" };
  }
  return { title: "查看并复盘申请", detail: "该流程已结束，可核对时间线后归档。", to: `/job-posts/${application.job_post_id}`, label: "查看目标岗位" };
}

export function ApplicationsPage() {
  const client = useQueryClient(); const navigate = useNavigate();
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const jobs = useQuery({ queryKey: ["job-posts"], queryFn: getJobPosts });
  const create = useMutation({ mutationFn: createApplication, onSuccess: async (item) => { await client.invalidateQueries({ queryKey: ["applications"] }); navigate(`/applications/${item.id}`); } });
  const tracked = new Set(applications.data?.items.map((item) => item.job_post_id));
  const availableJobs = jobs.data?.items.filter((job) => !tracked.has(job.id) && job.requirement_count > 0 && Boolean(job.latest_analysis)) ?? [];
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate(String(new FormData(event.currentTarget).get("job_post_id"))); }
  const createPanel = <section className="panel application-create"><div><h2>跟踪一个新岗位</h2><p>有定稿材料时进入待投递，否则先进入材料准备。</p></div><form onSubmit={submit}><select name="job_post_id" required defaultValue=""><option value="" disabled>选择尚未跟踪的岗位</option>{availableJobs.map((job) => <option key={job.id} value={job.id}>{job.company} · {job.title}</option>)}</select><button disabled={create.isPending}>{create.isPending ? "正在创建…" : "开始跟踪"}</button>{create.error && <p className="form-error">{create.error.message}</p>}</form></section>;
  return <><header className="page-header"><div><p className="eyebrow">申请进度</p><h1>申请进度</h1></div><span className="health-pill ok">{applications.data?.total ?? 0} 个流程</span></header>
    {availableJobs.length > 0 ? applications.data?.total ? <details className="application-create-details"><summary>跟踪新岗位</summary>{createPanel}</details> : createPanel : <section className="notice"><strong>没有可创建的申请</strong><p>只有已完成要求分析且尚未跟踪的岗位可以建立申请进度。</p><Link to="/job-posts">查看目标岗位</Link></section>}
    {!applications.data?.total && <section className="empty-state"><div className="empty-icon">↗</div><h2>还没有申请记录</h2><p>选择一个真实岗位开始跟踪。系统不会替你投递或联系招聘方。</p></section>}
    <section className="application-board">{applications.data?.items.map((item) => <Link className={`panel application-card status-${item.current_status}`} to={`/applications/${item.id}`} key={item.id}><span className="category-tag">{STATUS_LABELS[item.current_status]}</span><h2>{item.job_title}</h2><p>{item.company}</p><small>最近更新：{formatChinaTime(item.updated_at)} · 已绑定 {item.material_count} 份材料</small></Link>)}</section></>;
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
  const recommended = nextAction(application);
  const pendingProposals = application.proposals.filter(item => item.status === "pending");
  const resolvedProposals = application.proposals.filter(item => item.status !== "pending");
  const mailEvidence = application.mail_evidence ?? [];
  const tasksByProposal = new Map((reviewTasks.data?.items ?? []).filter(item => item.application_id === application.id).map(item => [item.id, item]));
  return <><header className="page-header job-detail-header"><div><p className="eyebrow"><Link to="/applications">申请进度</Link> / {application.company}</p><h1>{application.job_title}</h1><details><summary>查看记录版本</summary><p>岗位快照 {application.job_content_hash.slice(0, 12)} · 申请版本 {application.version}</p></details></div><span className={`health-pill ${application.current_status === "rejected" ? "blocked" : "ok"}`}>{STATUS_LABELS[application.current_status]}</span></header>
    <section className="panel next-action-card"><div><p className="eyebrow">建议下一步</p><h2>{recommended.title}</h2><p>{recommended.detail}</p></div><div className="primary-actions"><Link className="download-button" to={recommended.to}>{recommended.label}</Link><details className="secondary-actions"><summary>其他相关内容</summary><div><Link to={`/job-posts/${application.job_post_id}`}>目标岗位</Link><Link to={`/materials?jobId=${application.job_post_id}`}>申请材料</Link><Link to={`/tasks?applicationId=${application.id}`}>任务</Link></div></details></div></section>
    <section className="metric-grid"><article><span>当前状态</span><strong>{STATUS_LABELS[application.current_status]}</strong><small>根据完整申请记录更新</small></article><article><span>已投材料</span><strong>{application.material_count}</strong><small>确认投递时保存副本</small></article><article><span>进度记录</span><strong>{application.events.length}</strong><small>包含更正和历史进度</small></article><article><span>待确认进度</span><strong>{pendingProposals.length}</strong><small>确认后才会更新状态</small></article></section>
    {application.current_status === "ready_to_apply" && <div id="submission"><SubmissionPanel application={application} onSaved={refresh} /></div>}
    {!['ready_to_apply', 'archived', 'rejected', 'withdrawn'].includes(application.current_status) && <EventPanel application={application} onSaved={refresh} />}
    <section className="panel proposal-list"><div className="panel-heading"><div><p className="eyebrow">待确认进度</p><h2>来自邮件和数据来源的候选</h2></div><span>{pendingProposals.length} 待确认</span></div>{pendingProposals.map(proposal => {
      const task = tasksByProposal.get(proposal.id);
      return <article id={`proposal-${proposal.id}`} className={`proposal-card ${reviewId === proposal.id ? "focused-review" : ""}`} key={proposal.id}><div><span className="category-tag">{proposal.source === "manual_proposal" ? "手动补充" : proposal.source.includes("mail") ? "招聘邮件" : "外部来源"}</span><h3>{STATUS_LABELS[proposal.proposed_status]}</h3><p>{formatChinaTime(proposal.occurred_at)}（北京时间）</p><blockquote>{proposal.note}</blockquote></div>{proposal.status === "pending" && task ? <div className="fact-actions"><button disabled={resolve.isPending} onClick={() => resolve.mutate({ task, resolution: "confirmed" })}>确认进度</button><button className="danger" disabled={resolve.isPending} onClick={() => resolve.mutate({ task, resolution: "rejected" })}>拒绝候选</button></div> : <span className={`health-pill ${proposal.status === "confirmed" ? "ok" : "blocked"}`}>{proposal.status === "confirmed" ? "已确认" : proposal.status === "rejected" ? "已拒绝" : "正在加载审查信息"}</span>}</article>;
    })}{!pendingProposals.length && <p>目前没有需要确认的候选进度。</p>}{resolvedProposals.length > 0 && <details><summary>已处理候选（{resolvedProposals.length}）</summary>{resolvedProposals.map(proposal => <p className="history-row" key={proposal.id}>{STATUS_LABELS[proposal.proposed_status]} · {proposal.status === "confirmed" ? "已确认" : "已拒绝"}<small>{formatChinaTime(proposal.occurred_at)}（北京时间）</small></p>)}</details>}{resolve.error && <p className="form-error">{resolve.error.message}</p>}</section>
    <Timeline application={application} onSaved={refresh} />
    <section className="panel mail-evidence-panel"><div className="panel-heading"><div><p className="eyebrow">邮件证据</p><h2>招聘邮件证据</h2></div><span>{mailEvidence.length} 封</span></div>{mailEvidence.map(mail => <article className="mail-intelligence-item" key={mail.analysis_id}><div className="panel-heading"><strong>{mail.subject || "（无主题）"}</strong><Link to="/message-center">招聘邮件</Link></div><p>{mail.summary}</p><small>{mail.sender} · {mail.sent_at ? `${formatChinaTime(mail.sent_at)}（北京时间）` : "时间未知"} · 匹配度 {Math.round(mail.match_confidence * 100)}%</small>{mail.items.map(item => <details key={item.id}><summary>{item.title} · {item.status === "confirmed" ? "已确认" : item.status === "rejected" ? "已拒绝" : "待审核"}</summary><p>{item.details}</p><blockquote>{item.evidence}</blockquote>{(item.scheduled_at || item.occurred_at) && <time>{formatChinaTime(item.scheduled_at || item.occurred_at!)}（北京时间）</time>}</details>)}</article>)}{!mailEvidence.length && <p>尚未发现与该申请相关的招聘邮件。</p>}</section>
    <section className="panel snapshot-panel"><div className="panel-heading"><h2>投递材料快照</h2><span>{application.material_snapshots.length} 份</span></div>{application.material_snapshots.map((item) => <details key={item.id}><summary>{item.title} · {materialTypeLabel(item.material_type)}</summary><p>{item.rendered_text}</p><details className="audit-details"><summary>校验信息</summary><code>content {item.content_hash} · PDF {item.export_sha256 ?? "无"}</code></details></details>)}{!application.material_snapshots.length && <p>确认投递时才会锁定实际使用材料。</p>}</section>
    {application.current_status !== "archived" && <button className="danger archive-button" onClick={() => { if (window.confirm("归档后，该申请会从进行中流程移出，但历史记录仍保留。确认归档？")) archive.mutate(application); }} disabled={archive.isPending}>{archive.isPending ? "正在归档…" : "归档申请"}</button>}</>;
}

function SubmissionPanel({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  const [validationError, setValidationError] = useState("");
  const hasFinalMaterials = application.available_final_materials.length > 0;
  const submit = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return submitApplication(application, data.getAll("material_ids").map(String), chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: onSaved });
  return <section className="panel workflow-panel"><div><h2>确认已经投递</h2><p>只有你确认后才会标记为“已投递”；系统会保存本次实际使用的材料副本，便于以后核对。</p></div>{!hasFinalMaterials && <div className="notice"><strong>还没有可用于投递的定稿材料</strong><p>请先前往“简历与申请材料”生成、检查并确认定稿。</p><Link to={`/materials?jobId=${application.job_post_id}`}>准备并定稿材料</Link></div>}<form onSubmit={(event) => {
    event.preventDefault();
    const selectedMaterials = new FormData(event.currentTarget).getAll("material_ids");
    if (!selectedMaterials.length) {
      setValidationError(hasFinalMaterials ? "请至少选择一份定稿材料。" : "");
      return;
    }
    setValidationError("");
    submit.mutate(event.currentTarget);
  }}><div className="material-choices">{application.available_final_materials.map((item) => <label key={item.id}><input type="checkbox" name="material_ids" value={item.id} onChange={() => setValidationError("")} /> {item.name} · {materialTypeLabel(item.material_type)}</label>)}</div><label>实际投递时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={localNow()} required /></label><label>备注<input name="note" defaultValue="官网提交" /></label><button disabled={submit.isPending || !hasFinalMaterials}>确认投递并保存材料</button>{validationError && <p className="form-error">{validationError}</p>}{submit.error && <p className="form-error">{submit.error.message}</p>}</form></section>;
}

function EventPanel({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  const event = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return addApplicationEvent(application, String(data.get("target_status")) as ApplicationStatus, chinaInputToIso(String(data.get("occurred_at"))), String(data.get("note"))); }, onSuccess: onSaved });
  const allowedStatuses = NEXT_STATUSES[application.current_status] ?? [];
  return <section className="application-actions"><form className="panel" onSubmit={(e) => { e.preventDefault(); event.mutate(e.currentTarget); }}><h2>更新申请进度</h2><p>你手动记录的内容会直接写入时间线；来自邮件和外部来源的内容仍需确认。</p><label>新的申请进度<select name="target_status">{allowedStatuses.map((item) => <option value={item} key={item}>{STATUS_LABELS[item]}</option>)}</select></label><label>发生时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={localNow()} required /></label><input name="note" aria-label="进度备注" placeholder="例如：技术一面，线上会议" /><button disabled={event.isPending || !allowedStatuses.length}>{event.isPending ? "正在保存…" : "保存进度"}</button>{!allowedStatuses.length && <p className="disabled-reason">当前状态没有可继续推进的进度。</p>}{event.error && <p className="form-error">{event.error.message}</p>}</form></section>;
}

function Timeline({ application, onSaved }: { application: Application; onSaved: () => Promise<void> }) {
  return <section className="panel timeline"><div className="panel-heading"><h2>完整时间线</h2><span>{application.events.length} 条记录</span></div>{[...application.events].reverse().map((item) => <article className={item.superseded ? "superseded" : ""} key={item.id}><div className="timeline-marker" aria-hidden="true">•</div><div><strong>{EVENT_TYPE_LABELS[item.event_type] ?? "申请记录更新"} · {STATUS_LABELS[item.to_status as ApplicationStatus]}</strong><p>{formatChinaTime(item.occurred_at)}（北京时间） · {noteLabel(item.note) || "无备注"}</p><small>来源：{sourceLabel(item.source)}{item.supersedes_event_id ? " · 已更正早期记录" : ""}</small>{!item.superseded && !["application_created", "event_corrected"].includes(item.event_type) && <CorrectionForm application={application} event={item} onSaved={onSaved} />}</div></article>)}</section>;
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
