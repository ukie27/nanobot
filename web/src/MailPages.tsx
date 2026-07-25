import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ImapAccountUpdate, configureMailConnector, deleteMailConnector, getApplications,
  getMailConnector, getMailMessages, proposeMailMessage, syncMailConnector, testMailConnector,
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

export function MessageCenterPage() {
  const cache = useQueryClient();
  const connector = useQuery({ queryKey: ["mail-connector"], queryFn: getMailConnector });
  const messages = useQuery({ queryKey: ["mail-messages"], queryFn: getMailMessages });
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
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
  const refresh = async () => { await Promise.all([
    cache.invalidateQueries({ queryKey: ["mail-connector"] }),
    cache.invalidateQueries({ queryKey: ["mail-messages"] }),
  ]); };
  const save = useMutation({ mutationFn: configureMailConnector, onSuccess: async () => {
    setNotice("邮箱设置已安全保存，授权码已写入系统凭据库。");
    setForm(value => ({ ...value, password: "" })); await refresh();
  } });
  const test = useMutation({ mutationFn: testMailConnector, onSuccess: data => setNotice(`只读连接正常，UIDVALIDITY ${data.uid_validity}。`) });
  const sync = useMutation({ mutationFn: syncMailConnector, onSuccess: async data => {
    setNotice(`同步完成：发现 ${data.discovered_count}，新增 ${data.created_count}，重复 ${data.duplicate_count}。`); await refresh();
  } });
  const remove = useMutation({ mutationFn: deleteMailConnector, onSuccess: async () => {
    setForm(initial); setNotice("邮箱账户、同步数据和系统凭据已删除。"); await refresh();
  } });
  const propose = useMutation({ mutationFn: proposeMailMessage, onSuccess: async () => {
    setNotice("已按人工关联生成待确认 Proposal，请前往事件审查核对。"); await refresh();
  } });
  const error = connector.error || messages.error || applications.error || save.error || test.error || sync.error || remove.error || propose.error;
  const submit = (event: FormEvent) => {
    event.preventDefault(); save.mutate({ ...form, password: form.password || undefined });
  };

  return <>
    <header className="page-header"><div><p className="eyebrow">READ-ONLY IMAP</p><h1>消息中心</h1></div><span className={`health-pill ${connector.data?.health_status === "healthy" ? "ok" : ""}`}>{connector.data?.health_status ?? "未配置"}</span></header>
    <section className="notice"><strong>严格只读边界</strong><p>仅以 TLS 打开 INBOX，只执行 UID SEARCH 与 BODY.PEEK。不会标记已读、移动、复制、删除或发送邮件；邮件正文中的任何指令都只被视为普通文本。</p></section>
    {notice && <section className="notice success">{notice}</section>}
    {error && <section className="notice error" role="alert">{error.message}</section>}
    <section className="panel mail-settings">
      <div className="panel-heading"><div><p className="eyebrow">ACCOUNT & CURSOR</p><h2>邮箱设置</h2></div><span>{connector.data?.account?.credential_configured ? `凭据已配置 · ${connector.data.account.username_masked}` : "授权码不会回显"}</span></div>
      <form className="form-grid" onSubmit={submit}>
        <label><span>启用十分钟轮询</span><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} /></label>
        <label><span>邮箱地址</span><input type="email" required value={form.email_address} onChange={e => setForm({ ...form, email_address: e.target.value })} /></label>
        <label><span>IMAP TLS 主机</span><input required value={form.host} placeholder="imap.example.com" onChange={e => setForm({ ...form, host: e.target.value })} /></label>
        <label><span>端口</span><input type="number" min="1" max="65535" value={form.port} onChange={e => setForm({ ...form, port: Number(e.target.value) })} /></label>
        <label><span>登录用户名</span><input required value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
        <label><span>授权码{connector.data?.configured ? "（留空表示不更新）" : ""}</span><input type="password" required={!connector.data?.configured} autoComplete="new-password" value={form.password ?? ""} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
        <label><span>目录</span><input value={form.folder} readOnly title="Part 7 仅支持 INBOX" /></label>
        <label><span>首次同步范围（最长 30 天）</span><select value={Math.min(30, form.initial_lookback_days)} onChange={e => setForm({ ...form, initial_lookback_days: Number(e.target.value) })}><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select></label>
        <div className="wide cursor-strip"><span>UIDVALIDITY <strong>{connector.data?.cursor.uid_validity ?? "—"}</strong></span><span>Last committed UID <strong>{connector.data?.cursor.last_committed_uid ?? 0}</strong></span><span>下次同步（北京时间）<strong>{connector.data?.next_sync_at ? formatChinaTime(connector.data.next_sync_at) : "—"}</strong></span></div>
        <div className="form-actions wide"><button type="submit" disabled={save.isPending}>保存设置</button><button type="button" className="secondary" disabled={!connector.data?.configured || test.isPending} onClick={() => test.mutate()}>测试只读连接</button><button type="button" disabled={!connector.data?.enabled || sync.isPending} onClick={() => sync.mutate()}>立即同步</button>{connector.data?.configured && <button type="button" className="danger" disabled={remove.isPending} onClick={() => { if (window.confirm("删除邮箱配置、同步消息和系统凭据？")) remove.mutate(); }}>删除账户</button>}</div>
      </form>
    </section>
    <section className="notice manual-history"><strong>一个月以前的进度</strong><p>邮箱 Connector 不扫描 30 天以前的邮件。请到 <a href="/applications">申请看板</a> 打开对应申请，手动录入已发生的投递、笔试、面试、Offer 或拒绝进度；时间按北京时间填写。</p></section>
    <section className="mail-grid">
      <div className="mail-list">
        {messages.data?.items.length === 0 && <section className="empty-state"><div className="empty-icon">✉</div><h2>尚无邮件证据</h2><p>配置并启用邮箱后执行首次同步。无关邮件只保留最少 Header 信息。</p></section>}
        {messages.data?.items.map(message => <article className="panel mail-card" key={message.id}>
          <div className="mail-card-top"><span className={`category-tag mail-${message.classification}`}>{classificationLabel[message.classification] ?? message.classification}</span>{message.event_kind && <strong>{eventLabel[message.event_kind] ?? message.event_kind}</strong>}<time>{message.sent_at ? `${formatChinaTime(message.sent_at)}（北京时间）` : "时间未知"}</time></div>
          <h2>{message.subject || "（无主题）"}</h2><p className="mail-sender">{message.sender}</p>
          {message.evidence_excerpt && <blockquote>{message.evidence_excerpt}</blockquote>}
          {!!message.attachments.length && <p className="attachment-meta">附件元数据：{message.attachments.map(item => `${item.filename ?? "未命名"} · ${item.content_type} · ${item.size_bytes} B`).join("；")}</p>}
          {message.candidate && <div className="candidate-box"><strong>{message.candidate.status === "proposal_created" ? "已创建待确认 Proposal" : "需要人工关联"}</strong><p>{message.candidate.match_reason}</p>{message.candidate.proposal_id ? <a href="/application-review">前往事件审查确认</a> : <div className="manual-match"><select aria-label={`为 ${message.subject} 选择申请`} value={selectedApplications[message.id] ?? ""} onChange={event => setSelectedApplications(current => ({ ...current, [message.id]: event.target.value }))}><option value="">选择现有申请</option>{applications.data?.items.map(item => <option value={item.id} key={item.id}>{item.company} · {item.job_title}</option>)}</select><button type="button" disabled={!selectedApplications[message.id] || propose.isPending} onClick={() => propose.mutate({ message_id: message.id, application_id: selectedApplications[message.id] })}>生成待确认 Proposal</button></div>}</div>}
        </article>)}
      </div>
      <section className="panel sync-history"><div className="panel-heading"><h2>同步记录</h2><span>每 10 分钟</span></div>{connector.data?.runs.map(run => <article key={run.id}><strong>{run.status}</strong><span>{formatChinaTime(run.started_at)}（北京时间）</span><small>发现 {run.discovered_count} · 新增 {run.created_count} · 重复 {run.duplicate_count}{run.error_code ? ` · ${run.error_code}` : ""}</small></article>)}</section>
    </section>
  </>;
}
