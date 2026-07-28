import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import {
  cancelInterview, createInterview, generateInterviewPreparation, getApplications, getImprovementItems,
  getInterview, getInterviewFeedback, getInterviews, resolveInterviewFeedback,
  rescheduleInterview, saveInterviewRecord, updateImprovementItem, type InterviewRound,
} from "./api";
import { chinaInputToIso, formatChinaTime, isoToChinaInput } from "./time";

const ROUND_LABELS: Record<InterviewRound, string> = {
  phone: "电话/HR 面", technical: "技术面", case: "案例面", final: "终面",
};
const FEEDBACK_STATUS: Record<string, string> = { pending: "待确认", confirmed: "已确认", rejected: "已拒绝" };
const IMPROVEMENT_STATUS: Record<string, string> = { active: "进行中", completed: "已完成", dismissed: "已忽略" };
function defaultInterviewTime() {
  const tomorrow = new Date(Date.now() + 24 * 3600_000);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(tomorrow);
  const value = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}T10:00`;
}

export function InterviewCenterPage() {
  const client = useQueryClient();
  const interviews = useQuery({ queryKey: ["interviews"], queryFn: getInterviews });
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const feedback = useQuery({ queryKey: ["interview-feedback"], queryFn: getInterviewFeedback });
  const improvements = useQuery({ queryKey: ["improvements"], queryFn: getImprovementItems });
  const refresh = async () => { await Promise.all([
    client.invalidateQueries({ queryKey: ["interviews"] }),
    client.invalidateQueries({ queryKey: ["interview-feedback"] }),
    client.invalidateQueries({ queryKey: ["improvements"] }),
  ]); };
  const create = useMutation({ mutationFn: createInterview, onSuccess: refresh });
  const resolve = useMutation({ mutationFn: ({ item, resolution }: { item: NonNullable<typeof feedback.data>["items"][number]; resolution: "confirmed" | "rejected" }) => resolveInterviewFeedback(item, resolution), onSuccess: refresh });
  const update = useMutation({ mutationFn: ({ id, status }: { id: string; status: "completed" | "dismissed" }) => updateImprovementItem(id, status), onSuccess: refresh });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    create.mutate({ application_id: String(data.get("application_id")), round_type: String(data.get("round_type")) as InterviewRound, scheduled_at: chinaInputToIso(String(data.get("scheduled_at"))), timezone: "Asia/Shanghai" });
  }
  const pendingFeedback = feedback.data?.items.filter(item => item.status === "pending") ?? [];
  const feedbackHistory = feedback.data?.items.filter(item => item.status !== "pending") ?? [];
  const activeImprovements = improvements.data?.items.filter(item => item.status === "active") ?? [];
  const improvementHistory = improvements.data?.items.filter(item => item.status !== "active") ?? [];
  return <><header className="page-header"><div><p className="eyebrow">面试与复盘</p><h1>面试中心</h1></div><span className="health-pill ok">{interviews.data?.total ?? 0} 场</span></header>
    <section className="panel interview-create"><div><h2>安排一轮面试</h2><p>准备包只读取岗位冻结版本、实际投递材料、已确认事实和已确认历史弱点。</p></div><form className="form-grid" onSubmit={submit}><label>关联申请<select name="application_id" required defaultValue=""><option value="" disabled>选择申请</option>{applications.data?.items.map((item) => <option key={item.id} value={item.id}>{item.company} · {item.job_title}</option>)}</select></label><label>轮次<select name="round_type"><option value="phone">电话/HR 面</option><option value="technical">技术面</option><option value="case">案例面</option><option value="final">终面</option></select></label><label>时间（北京时间）<input name="scheduled_at" type="datetime-local" defaultValue={defaultInterviewTime()} required /></label><button disabled={create.isPending || !applications.data?.total}>{create.isPending ? "正在创建…" : "创建面试"}</button>{!applications.data?.total && <p className="disabled-reason">还没有申请记录，请先在“申请总览”建立申请进度。</p>}{create.error && <p className="form-error">{create.error.message}</p>}</form></section>
    <section className="interview-grid">{interviews.data?.items.map((item) => <Link className="panel interview-card" to={`/interviews/${item.id}`} key={item.id}><span className="category-tag">{ROUND_LABELS[item.round_type]}</span><h2>{item.company} · {item.job_title}</h2><p>{formatChinaTime(item.scheduled_at)}（北京时间）</p><small>{item.preparation ? "准备包已生成" : "尚未生成准备包"} · {item.record ? "已复盘" : "待复盘"}</small></Link>)}</section>
    <section className="panel"><div className="panel-heading"><h2>待确认复盘建议</h2><span>{pendingFeedback.length}</span></div>{pendingFeedback.map((item) => <article className="feedback-row" key={item.id}><div><strong>{item.category} · {item.description}</strong><blockquote>{item.evidence_text || "未提供回答摘要"}</blockquote></div><div className="fact-actions"><button disabled={resolve.isPending} onClick={() => resolve.mutate({ item, resolution: "confirmed" })}>确认沉淀</button><button className="danger" disabled={resolve.isPending} onClick={() => resolve.mutate({ item, resolution: "rejected" })}>拒绝</button></div></article>)}{!pendingFeedback.length && <p>没有待确认的复盘建议。</p>}{feedbackHistory.length > 0 && <details><summary>已处理建议（{feedbackHistory.length}）</summary>{feedbackHistory.map(item => <p className="history-row" key={item.id}>{item.description}<small>{FEEDBACK_STATUS[item.status] ?? item.status}</small></p>)}</details>}</section>
    <section className="panel"><div className="panel-heading"><h2>长期改进项</h2><span>{activeImprovements.length} 进行中</span></div>{activeImprovements.map((item) => <article className="feedback-row" key={item.id}><div><strong>{item.title} · 出现 {item.occurrence_count} 次</strong><p>{item.description}</p></div><div className="fact-actions"><button disabled={update.isPending} onClick={() => update.mutate({ id: item.id, status: "completed" })}>完成</button><button className="secondary" disabled={update.isPending} onClick={() => update.mutate({ id: item.id, status: "dismissed" })}>忽略</button></div></article>)}{!activeImprovements.length && <p>当前没有进行中的长期改进项。</p>}{improvementHistory.length > 0 && <details><summary>历史改进项（{improvementHistory.length}）</summary>{improvementHistory.map(item => <p className="history-row" key={item.id}>{item.title}<small>{IMPROVEMENT_STATUS[item.status] ?? item.status}</small></p>)}</details>}</section></>;
}

interface ReviewQuestionDraft {
  key: number; question_text: string; answer_summary: string; self_rating: number;
}

export function InterviewDetailPage() {
  const { id = "" } = useParams(); const client = useQueryClient();
  const [questions, setQuestions] = useState<ReviewQuestionDraft[]>([
    { key: 1, question_text: "", answer_summary: "", self_rating: 3 },
  ]);
  const query = useQuery({ queryKey: ["interview", id], queryFn: () => getInterview(id), enabled: Boolean(id) });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["interview", id] }), client.invalidateQueries({ queryKey: ["interviews"] }), client.invalidateQueries({ queryKey: ["interview-feedback"] })]); };
  const prepare = useMutation({ mutationFn: () => generateInterviewPreparation(id), onSuccess: refresh });
  const record = useMutation({ mutationFn: (form: HTMLFormElement) => { const data = new FormData(form); return saveInterviewRecord(id, { occurred_at: chinaInputToIso(String(data.get("occurred_at"))), overall_summary: String(data.get("overall_summary")), self_rating: Number(data.get("self_rating")), result: String(data.get("result")), questions: questions.map(({ question_text, answer_summary, self_rating }) => ({ question_text, answer_summary, self_rating })) }); }, onSuccess: refresh });
  const reschedule = useMutation({ mutationFn: ({ item, scheduledAt }: { item: NonNullable<typeof query.data>; scheduledAt: string }) => rescheduleInterview(item, scheduledAt), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: ({ item, reason }: { item: NonNullable<typeof query.data>; reason: string }) => cancelInterview(item, reason), onSuccess: refresh });
  if (!query.data) return <section className="empty-state"><p>{query.error?.message ?? "正在加载面试…"}</p></section>;
  const interview = query.data; const pack = interview.preparation?.content;
  return <><header className="page-header"><div><p className="eyebrow"><Link to="/interviews">面试中心</Link> / {ROUND_LABELS[interview.round_type]}</p><h1>{interview.company} · {interview.job_title}</h1><p>{formatChinaTime(interview.scheduled_at)}（北京时间）</p></div><button onClick={() => prepare.mutate()} disabled={prepare.isPending}>{pack ? "重新生成冻结准备包" : "生成准备包"}</button></header>
    {interview.status === "scheduled" && <section className="panel interview-schedule"><form className="form-actions" onSubmit={(event) => { event.preventDefault(); reschedule.mutate({ item: interview, scheduledAt: chinaInputToIso(String(new FormData(event.currentTarget).get("scheduled_at"))) }); }}><label>改期（北京时间）<input name="scheduled_at" type="datetime-local" defaultValue={isoToChinaInput(interview.scheduled_at)} required /></label><button className="secondary">同步改期面试任务</button></form><form className="form-actions" onSubmit={(event) => { event.preventDefault(); cancel.mutate({ item: interview, reason: String(new FormData(event.currentTarget).get("reason")) }); }}><label>取消原因<input name="reason" required maxLength={500} /></label><button className="danger">取消面试和提醒</button></form></section>}
    {prepare.error && <section className="notice error">{prepare.error.message}</section>}
    {pack && <><section className="metric-grid"><article><span>岗位要求</span><strong>{pack.requirements.length}</strong><small>面试对应岗位版本</small></article><article><span>实际材料</span><strong>{pack.submitted_materials.length}</strong><small>投递时使用的内容</small></article><article><span>已确认事实</span><strong>{pack.confirmed_facts.length}</strong><small>回答依据</small></article><article><span>历史改进</span><strong>{pack.historical_improvements.length}</strong><small>仅已确认</small></article></section><section className="preparation-grid"><PackList title="模拟问题" items={pack.questions} /><PackList title="面试反问" items={pack.candidate_questions} /><PackList title="检查清单" items={pack.checklist} /><PackList title="缺口回答思路" items={pack.gap_bridges.map((item) => `${item.requirement}：${item.bridge}`)} /></section><section className="panel"><div className="panel-heading"><h2>实际投递材料证据</h2><span>{pack.submitted_materials.length}</span></div>{pack.submitted_materials.map((item) => <details key={item.id}><summary>{item.title}</summary><p>{item.evidence_excerpt}</p><details className="audit-details"><summary>校验信息</summary><code>{item.content_hash}</code></details></details>)}</section></>}
    {!interview.record && interview.status !== "cancelled" ? <section className="panel record-form"><h2>面试后手工复盘</h2><form className="form-grid" onSubmit={(event) => { event.preventDefault(); record.mutate(event.currentTarget); }}><label>发生时间（北京时间）<input name="occurred_at" type="datetime-local" defaultValue={isoToChinaInput(interview.scheduled_at)} required /></label><label>整体自评<select name="self_rating" defaultValue="3">{[1,2,3,4,5].map((item) => <option key={item}>{item}</option>)}</select></label><label>结果<select name="result"><option value="unknown">未知</option><option value="pending">等待结果</option><option value="passed">通过</option><option value="rejected">未通过</option><option value="withdrawn">主动退出</option></select></label><label className="wide">整体摘要<textarea name="overall_summary" required /></label><div className="wide question-editor"><div className="panel-heading"><h3>面试问题</h3><button type="button" className="secondary" onClick={() => setQuestions((items) => [...items, { key: Date.now(), question_text: "", answer_summary: "", self_rating: 3 }])} disabled={questions.length >= 50}>添加问题</button></div>{questions.map((item, index) => <article key={item.key}><label>问题 {index + 1}<textarea value={item.question_text} required onChange={(event) => setQuestions((items) => items.map((entry) => entry.key === item.key ? { ...entry, question_text: event.target.value } : entry))} /></label><label>回答摘要<textarea value={item.answer_summary} onChange={(event) => setQuestions((items) => items.map((entry) => entry.key === item.key ? { ...entry, answer_summary: event.target.value } : entry))} /></label><label>该题自评<select value={item.self_rating} onChange={(event) => setQuestions((items) => items.map((entry) => entry.key === item.key ? { ...entry, self_rating: Number(event.target.value) } : entry))}>{[1,2,3,4,5].map((rating) => <option key={rating}>{rating}</option>)}</select></label>{questions.length > 1 && <button type="button" className="danger" onClick={() => setQuestions((items) => items.filter((entry) => entry.key !== item.key))}>删除该题</button>}</article>)}</div><button>保存复盘并生成待审建议</button>{record.error && <p className="form-error">{record.error.message}</p>}</form></section> : interview.record ? <section className="panel"><div className="panel-heading"><h2>已完成复盘</h2><span>自评 {interview.record.self_rating}/5</span></div><p>{interview.record.overall_summary}</p>{interview.record.questions.map((item) => <blockquote key={item.id}>{item.question_text}<br />{item.answer_summary}</blockquote>)}</section> : <section className="notice">该面试已取消，不再接受复盘。</section>}</>;
}

function PackList({ title, items }: { title: string; items: string[] }) {
  return <section className="panel"><h2>{title}</h2><ol>{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ol></section>;
}
