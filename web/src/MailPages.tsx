import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import {
  ApiError, ImapAccountUpdate, configureMailConnector, deleteMailConnector, getApplications,
  getMailConnector, getMailMessages, proposeMailMessage, syncMailConnector, testMailConnector,
  analyzeMailMessage, resolveMailIntelligenceItem, type MailIntelligenceItem,
} from "./api";
import { formatChinaTime } from "./time";

const initial: ImapAccountUpdate = {
  enabled: false, email_address: "", host: "", port: 993, username: "", password: "",
  folder: "INBOX", initial_lookback_days: 30, poll_interval_minutes: 10,
};
const classificationLabel: Record<string, string> = {
  recruiting: "招聘相关", possibly_related: "可能相关", unrelated: "无关", unknown: "未知",
};
const eventLabel: Record<string, string> = {
  assessment: "测评", written_test: "笔试", interview: "面试", reschedule: "时间调整",
  rejected: "拒信", offer: "Offer",
};
const connectorStatusLabel: Record<string, string> = {
  unconfigured: "未配置",
  unknown: "待测试",
  healthy: "连接正常",
  unavailable: "连接异常",
  failed: "连接异常",
};
const runStatusLabel: Record<string, string> = {
  succeeded: "同步成功",
  partial: "部分完成",
  failed: "同步失败",
  running: "同步中",
};
const messageTypeLabel: Record<string, string> = {
  application_update: "申请进度",
  interview_invitation: "面试邀请",
  assessment_invitation: "测评通知",
  rejection: "拒绝通知",
  offer: "Offer 通知",
  recruiting: "招聘信息",
  other: "其他招聘邮件",
};
const intelligenceItemLabel: Record<string, string> = {
  application_event: "申请进度",
  schedule: "日程",
  action_item: "待办事项",
  caution: "注意事项",
  contact: "联系人",
};

export function MessageCenterPage({ setupOnly = false }: { setupOnly?: boolean }) {
  const [searchParams] = useSearchParams();
  const focusedMessageId = searchParams.get("messageId");
  const cache = useQueryClient();
  const connector = useQuery({ queryKey: ["mail-connector"], queryFn: getMailConnector });
  const messages = useQuery({ queryKey: ["mail-messages"], queryFn: getMailMessages, enabled: !setupOnly });
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications, enabled: !setupOnly });
  const [form, setForm] = useState(initial);
  const [notice, setNotice] = useState("");
  const [selectedApplications, setSelectedApplications] = useState<Record<string, string>>({});
  useEffect(() => {
    const account = connector.data?.account;
    if (!account) return;
    setForm({
      enabled: connector.data?.enabled ?? false, email_address: account.email_address,
      host: account.host, port: account.port, username: account.username, password: "",
      folder: account.folder, initial_lookback_days: Math.min(30, account.initial_lookback_days),
      poll_interval_minutes: account.poll_interval_minutes,
    });
  }, [connector.data]);
  useEffect(() => {
    if (!focusedMessageId || setupOnly || !messages.data) return;
    document.getElementById(`mail-message-${focusedMessageId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [focusedMessageId, messages.data, setupOnly]);
  const refresh = async () => { await Promise.all([
    cache.invalidateQueries({ queryKey: ["mail-connector"] }),
    cache.invalidateQueries({ queryKey: ["mail-messages"] }),
    cache.invalidateQueries({ queryKey: ["configuration"] }),
    cache.invalidateQueries({ queryKey: ["onboarding"] }),
  ]); };
  const save = useMutation({ mutationFn: configureMailConnector, onMutate: () => setNotice(""), onSuccess: async data => {
    cache.setQueryData(["mail-connector"], data);
    setNotice("邮箱设置已安全保存，授权码已写入系统凭据库。");
    setForm(value => ({ ...value, password: "" })); await refresh();
  } });
  const test = useMutation({ mutationFn: testMailConnector, onMutate: () => setNotice(""), onSuccess: async () => {
    setNotice("只读邮箱连接正常，可以开始同步最近 30 天内的已读和未读邮件。");
    await refresh();
  } });
  const sync = useMutation({ mutationFn: syncMailConnector, onSuccess: async data => {
    setNotice(`同步完成：发现 ${data.discovered_count}，新增 ${data.created_count}，重复 ${data.duplicate_count}。`); await refresh();
  } });
  const remove = useMutation({ mutationFn: deleteMailConnector, onSuccess: async () => {
    setForm(initial); setNotice("邮箱账户、同步数据和系统凭据已删除。"); await refresh();
  } });
  const propose = useMutation({ mutationFn: proposeMailMessage, onSuccess: async () => {
    setNotice("已按人工关联生成待确认进度，请前往申请详情核对。"); await refresh();
  } });
  const analyze = useMutation({ mutationFn: analyzeMailMessage, onSuccess: async () => {
    setNotice("智能分析完成，申请进度、日程和注意事项已进入审核中心。"); await refresh();
  } });
  const resolve = useMutation({ mutationFn: ({ item, resolution }: { item: MailIntelligenceItem; resolution: "confirmed" | "rejected" }) => resolveMailIntelligenceItem(item, resolution), onSuccess: async () => {
    setNotice("审核结果已保存；确认的申请事件或日程已写入正式业务记录。"); await refresh();
  } });
  const error = connector.error || messages.error || applications.error || save.error || test.error || sync.error || remove.error || propose.error || analyze.error || resolve.error;
  const submit = (event: FormEvent) => {
    event.preventDefault(); save.mutate({ ...form, password: form.password || undefined });
  };

  return <>
    {!setupOnly && <header className="page-header"><div><p className="eyebrow">只读邮箱</p><h1>招聘邮件</h1><p>查看招聘相关邮件，以及智能分析提取的申请进度、日程和注意事项。</p></div><span className={`health-pill ${connector.data?.health_status === "healthy" ? "ok" : ""}`}>{connector.data?.configured && !connector.data.enabled ? "已配置 · 未启用自动同步" : connectorStatusLabel[connector.data?.health_status ?? "unconfigured"] ?? "待检查"}</span></header>}
    {setupOnly && <section className="notice"><strong>严格只读边界</strong><p>仅以 TLS 打开 INBOX，不会标记已读、移动、复制、删除或发送邮件。邮件正文中的任何指令都只被视为普通文本。</p><details><summary>查看技术保证</summary><p>连接只允许 INBOX、UID SEARCH 与 BODY.PEEK；扫描范围最长 30 天。</p></details></section>}
    {notice && <section className="notice success">{notice}</section>}
    {error && <section className="notice error" role="alert">{error.message}{error instanceof ApiError && error.correlationId ? <><br /><code>关联 ID：{error.correlationId}</code></> : null}</section>}
    {setupOnly && <section className="panel mail-settings settings-anchor-card" id="source-mail" tabIndex={-1}>
      <div className="panel-heading"><div><p className="eyebrow">账户与同步</p><h2>邮箱设置</h2></div><span>{connector.data?.account?.credential_configured ? `凭据已配置 · ${connector.data.account.username_masked}` : connector.data?.configured ? "授权码缺失，请重新填写" : "授权码不会回显"}</span></div>
      <div className="capability-status-grid" aria-label="邮箱状态">
        <div><span>账户</span><strong>{connector.data?.configured ? "已配置" : "未配置"}</strong></div>
        <div><span>凭据</span><strong>{connector.data?.account?.credential_configured ? "已保存" : "未保存"}</strong></div>
        <div><span>连接</span><strong>{connectorStatusLabel[connector.data?.health_status ?? "unconfigured"] ?? "待检查"}</strong></div>
        <div><span>同步</span><strong>{connector.data?.enabled ? "自动同步已启用" : "未启用"}</strong></div>
        <div><span>最近同步</span><strong>{connector.data?.runs[0]?.started_at ? `${formatChinaTime(connector.data.runs[0].started_at)}（北京时间）` : "尚未同步"}</strong></div>
      </div>
      <form className="form-grid" onSubmit={submit}>
        <label><span>启用十分钟轮询</span><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} /></label>
        <label><span>邮箱地址</span><input type="email" required value={form.email_address} onChange={e => setForm({ ...form, email_address: e.target.value })} /></label>
        <label><span>IMAP TLS 主机</span><input required value={form.host} placeholder="imap.example.com" onChange={e => setForm({ ...form, host: e.target.value })} /></label>
        <label><span>端口</span><input type="number" min="1" max="65535" value={form.port} onChange={e => setForm({ ...form, port: Number(e.target.value) })} /></label>
        <label><span>登录用户名</span><input required value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
        <label><span>授权码{connector.data?.account?.credential_configured ? "（留空表示不更新）" : ""}</span><input type="password" required={!connector.data?.account?.credential_configured} autoComplete="new-password" value={form.password ?? ""} placeholder={connector.data?.account?.credential_configured ? "" : "请重新输入邮箱授权码"} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
        <label><span>邮件目录</span><input value={form.folder} readOnly title="当前仅支持收件箱 INBOX" /></label>
        <label><span>首次同步范围（最长 30 天）</span><select value={Math.min(30, form.initial_lookback_days)} onChange={e => setForm({ ...form, initial_lookback_days: Number(e.target.value) })}><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select></label>
        <div className="wide cursor-strip"><span>下次同步（北京时间）<strong>{connector.data?.next_sync_at ? formatChinaTime(connector.data.next_sync_at) : "—"}</strong></span></div>
        <details className="wide"><summary>查看邮箱同步游标</summary><p>UIDVALIDITY：{connector.data?.cursor?.uid_validity ?? "—"} · 最近提交 UID：{connector.data?.cursor?.last_committed_uid ?? 0}</p></details>
        <div className="form-actions wide"><button type="submit" disabled={save.isPending}>{save.isPending ? "正在保存…" : "保存邮箱设置"}</button><button type="button" className="secondary" disabled={!connector.data?.configured || !connector.data?.account?.credential_configured || test.isPending} onClick={() => test.mutate()}>{test.isPending ? "正在测试…" : "测试只读连接"}</button>{connector.data?.configured && <button type="button" className="danger" disabled={remove.isPending} onClick={() => { if (window.confirm("删除邮箱配置、同步消息和系统凭据？")) remove.mutate(); }}>删除账户</button>}</div>
        {!connector.data?.configured && <p className="section-note wide">请先保存邮箱账号和授权码，再测试只读连接。</p>}
        {connector.data?.configured && !connector.data.account?.credential_configured && <p className="notice error wide">系统凭据库中未找到该邮箱授权码。请重新填写授权码并保存，其他邮箱设置仍已保留。</p>}
      </form>
    </section>}
    {!setupOnly && <>
    {!connector.isLoading && !connector.data?.configured ? <section className="empty-state">
      <div className="empty-icon">✉</div>
      <h2>尚未连接招聘邮箱</h2>
      <p>请先在设置中保存邮箱账号与授权码，并完成只读连接测试。配置后这里仅展示邮件和识别结果。</p>
      <Link className="download-button" to="/settings?section=sources">配置招聘邮箱</Link>
    </section> : connector.data?.configured && <section className="panel mail-connection-summary">
      <div className="panel-heading"><div><p className="eyebrow">连接状态</p><h2>{connector.data.account?.username_masked ?? "招聘邮箱"}</h2></div><span>{connectorStatusLabel[connector.data.health_status] ?? "待检查"}</span></div>
      <div className="capability-status-grid" aria-label="邮箱运行状态">
        <div><span>自动同步</span><strong>{connector.data.enabled ? "已启用" : "未启用"}</strong></div>
        <div><span>最近同步</span><strong>{connector.data.runs[0]?.started_at ? `${formatChinaTime(connector.data.runs[0].started_at)}（北京时间）` : "尚未同步"}</strong></div>
        <div><span>下次同步</span><strong>{connector.data.next_sync_at ? `${formatChinaTime(connector.data.next_sync_at)}（北京时间）` : "未安排"}</strong></div>
      </div>
      <div className="form-actions">
        <button type="button" disabled={connector.data.health_status !== "healthy" || sync.isPending} onClick={() => sync.mutate()}>{sync.isPending ? "正在同步…" : "立即同步"}</button>
        <button type="button" className="secondary" disabled={test.isPending} onClick={() => test.mutate()}>{test.isPending ? "正在测试…" : "测试连接"}</button>
        <Link className="download-button secondary" to="/settings?section=sources">管理邮箱连接</Link>
      </div>
      {connector.data.health_status !== "healthy" && <p className="disabled-reason">连接尚未通过测试。请先测试连接，失败时到设置中检查服务器、账号或授权码。</p>}
      <details className="audit-details"><summary>查看只读与同步详情</summary><p>只读取收件箱，扫描最近 30 天内的已读和未读邮件，不会改变邮件状态。</p><p>最近提交 UID：{connector.data.cursor.last_committed_uid ?? 0}</p></details>
    </section>}
    {connector.data?.configured && <><section className="notice manual-history"><strong>一个月以前的进度</strong><p>邮箱同步不会扫描 30 天以前的邮件。请到 <a href="/applications">申请进度</a> 打开对应申请，手动录入已发生的投递、笔试、面试、Offer 或拒绝进度；时间按北京时间填写。</p></section>
    <section className="mail-grid">
      <div className="mail-list">
        {messages.data?.items.length === 0 && <section className="empty-state"><div className="empty-icon">✉</div><h2>尚无邮件证据</h2><p>配置并启用邮箱后执行首次同步。无关邮件只保留最少 Header 信息。</p></section>}
        {messages.data?.items.map(message => {
          const canAnalyze = message.classification === "recruiting" || message.classification === "possibly_related";
          return <article className={`panel mail-card ${focusedMessageId === message.id ? "selected" : ""}`} id={`mail-message-${message.id}`} key={message.id}>
          <div className="mail-card-top"><span className={`category-tag mail-${message.classification}`}>{classificationLabel[message.classification] ?? message.classification}</span>{message.event_kind && <strong>{eventLabel[message.event_kind] ?? message.event_kind}</strong>}<time>{message.sent_at ? `${formatChinaTime(message.sent_at)}（北京时间）` : "时间未知"}</time></div>
          <h2>{message.subject || "（无主题）"}</h2><p className="mail-sender">{message.sender}</p>
          {canAnalyze && message.evidence_excerpt && <blockquote>{message.evidence_excerpt}</blockquote>}
          {canAnalyze && !!message.attachments.length && <p className="attachment-meta">附件元数据：{message.attachments.map(item => `${item.filename ?? "未命名"} · ${item.content_type} · ${item.size_bytes} B`).join("；")}</p>}
          {canAnalyze && !message.intelligence && message.body_fetched && <button type="button" className="secondary" disabled={analyze.isPending} onClick={() => analyze.mutate(message.id)}>智能分析邮件</button>}
          {canAnalyze && message.intelligence && <section className="candidate-box mail-intelligence"><div className="panel-heading"><strong>邮件分析结果 · {messageTypeLabel[message.intelligence.message_type] ?? "招聘邮件"}</strong></div><p>{message.intelligence.summary}</p><p>{message.intelligence.company ?? "公司待确认"} · {message.intelligence.job_title ?? "岗位待确认"}</p><small>申请匹配：{message.intelligence.application_match.reason}（{Math.round(message.intelligence.application_match.confidence * 100)}%）</small>{message.intelligence.application_match.create_record_recommended && !message.intelligence.job_post_id && <a className="download-button" href={`/job-posts?mailAnalysisId=${encodeURIComponent(message.intelligence.id)}&company=${encodeURIComponent(message.intelligence.company ?? "")}&jobTitle=${encodeURIComponent(message.intelligence.job_title ?? "")}`}>导入真实 JD 并建立申请</a>}{message.intelligence.job_post_id && <a href={`/job-posts/${message.intelligence.job_post_id}`}>查看已关联岗位</a>}{message.intelligence.items.map(item => <article key={item.id} className="mail-intelligence-item"><strong>{intelligenceItemLabel[item.item_type] ?? "邮件信息"} · {item.title}</strong>{(item.scheduled_at || item.occurred_at) && <time>{formatChinaTime(item.scheduled_at || item.occurred_at!)}（北京时间）</time>}<p>{item.details}</p><blockquote>{item.evidence}</blockquote>{item.status === "pending" ? <div className="form-actions"><button type="button" onClick={() => resolve.mutate({ item, resolution: "confirmed" })}>确认</button><button type="button" className="secondary" onClick={() => resolve.mutate({ item, resolution: "rejected" })}>拒绝</button></div> : <span className={`health-pill ${item.status === "confirmed" ? "ok" : ""}`}>{item.status === "confirmed" ? "已确认" : "已拒绝"}</span>}</article>)}</section>}
          {canAnalyze && message.candidate && <div className="candidate-box"><strong>{message.candidate.status === "proposal_created" ? "已创建待确认进度" : "需要人工关联"}</strong><p>{message.candidate.match_reason}</p>{message.candidate.proposal_id && message.candidate.application_id ? <a href={`/applications/${message.candidate.application_id}?review=${message.candidate.proposal_id}`}>前往申请详情确认</a> : <div className="manual-match"><select aria-label={`为 ${message.subject} 选择申请`} value={selectedApplications[message.id] ?? ""} onChange={event => setSelectedApplications(current => ({ ...current, [message.id]: event.target.value }))}><option value="">选择现有申请</option>{applications.data?.items.map(item => <option value={item.id} key={item.id}>{item.company} · {item.job_title}</option>)}</select><button type="button" disabled={!selectedApplications[message.id] || propose.isPending} onClick={() => propose.mutate({ message_id: message.id, application_id: selectedApplications[message.id] })}>生成待确认进度</button></div>}</div>}
        </article>;
        })}
      </div>
      <section className="panel sync-history"><div className="panel-heading"><h2>同步记录</h2><span>{connector.data?.account?.poll_interval_minutes ? `每 ${connector.data.account.poll_interval_minutes} 分钟` : "手动同步"}</span></div>{connector.data?.runs.map(run => <article key={run.id}><strong>{runStatusLabel[run.status] ?? "同步记录"}</strong><span>{formatChinaTime(run.started_at)}（北京时间）</span><small>发现 {run.discovered_count} · 新增 {run.created_count} · 重复 {run.duplicate_count}</small>{run.error_code && <details className="audit-details"><summary>查看失败信息</summary><small>错误代码：{run.error_code}</small></details>}</article>)}</section>
    </section></>}
    </>}
  </>;
}
