import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  BossConnectorUpdate,
  NowcoderConnectorUpdate,
  checkBossConnector,
  checkNowcoderConnector,
  configureBossConnector,
  configureNowcoderConnector,
  getBossConnector,
  getNowcoderConnector,
  loginBossConnector,
  loginNowcoderConnector,
  scanBossConnector,
  scanNowcoderConnector,
} from "./api";
import { formatChinaTime } from "./time";

const initial: BossConnectorUpdate = {
  enabled: false,
  profile_alias: "default",
  search_query: "",
  city: "全国",
  result_limit: 15,
  schedule_enabled: false,
  schedule_times: ["09:00", "18:00"],
  timezone: "Asia/Shanghai",
};

const nowcoderInitial: NowcoderConnectorUpdate = {
  enabled: false,
  search_query: "",
  city: "全国",
  result_limit: 500,
  schedule_enabled: false,
  schedule_times: ["09:00"],
};

const connectorErrors: Record<string, string> = {
  opencli_not_installed: "未检测到 OpenCLI，请先在“设置 → 数据来源”中配置 OpenCLI 可执行文件。",
  requires_login: "尚未登录，请先点击“打开登录”并在浏览器中完成登录。",
  plugin_not_installed: "对应的网站插件尚未安装，请先完成插件安装。",
  execution_failed: "调用 OpenCLI 失败，请检查可执行文件和插件配置。",
  temporary_timeout: "BOSS 登录状态检查超时。该来源可暂时保持关闭，不影响牛客每日招聘。",
  browser_bridge_unavailable: "浏览器连接不可用，请确认 OpenCLI 浏览器扩展已启用。",
};
const triggerLabels: Record<string, string> = {
  manual: "手动",
  schedule: "自动任务",
  scheduled: "自动任务",
  startup: "服务启动",
};
const runStatusLabels: Record<string, string> = {
  succeeded: "成功",
  completed: "成功",
  partial: "部分完成",
  failed: "失败",
  running: "进行中",
};

function connectorStatusLabel(status?: string, errorCode?: string | null) {
  if (!status || status === "unknown") return "尚未检查";
  if (status === "healthy") return "来源可用";
  if (status === "requires_login" || errorCode === "requires_login") return "需要登录";
  if (errorCode === "opencli_not_installed") return "OpenCLI 未配置";
  return "暂不可用";
}

function SessionSummary({ connector }: {
  connector?: {
    session_status: string;
    session_identity: Record<string, string | boolean | number>;
    session_checked_at: string | null;
  };
}) {
  const identity = connector?.session_identity ?? {};
  const label = connector?.session_status === "authenticated"
    ? "已登录"
    : connector?.session_status === "requires_login"
      ? "需要登录"
      : connector?.session_status === "expired"
        ? "登录已过期"
        : connector?.session_status === "unavailable"
          ? "无法检查"
          : "尚未检查";
  const name = identity.display_name ?? identity.nickname ?? identity.username ?? identity.user_type;
  return <div className="wide cursor-strip connector-session">
    <span>浏览器会话</span>
    <strong>{label}{name ? ` · ${String(name)}` : ""}</strong>
    <small>{connector?.session_checked_at
      ? `最后检查 ${formatChinaTime(connector.session_checked_at)}（北京时间）`
      : "保存设置后，打开登录并检查状态。"}</small>
  </div>;
}

function connectorHealthMessage(source: string, data: {
  status: string;
  opencli_version?: string;
  error_code?: string;
}) {
  if (data.status === "healthy") {
    return `${source}来源可用${data.opencli_version ? ` · OpenCLI ${data.opencli_version}` : ""}。`;
  }
  return connectorErrors[data.error_code ?? ""] ??
    `${source}来源暂不可用，请检查“设置 → 数据来源”中的配置。`;
}

export function DataSourcesPage({ setupOnly = false }: { setupOnly?: boolean }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["boss-connector"], queryFn: getBossConnector });
  const nowcoder = useQuery({ queryKey: ["nowcoder-connector"], queryFn: getNowcoderConnector });
  const [form, setForm] = useState(initial);
  const [nowcoderForm, setNowcoderForm] = useState(nowcoderInitial);
  const [lookback, setLookback] = useState<0 | 7 | 14 | 30>(0);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!query.data) return;
    setForm({
      enabled: query.data.enabled,
      profile_alias: query.data.profile_alias,
      search_query: query.data.search_query,
      city: query.data.city,
      result_limit: query.data.result_limit,
      schedule_enabled: query.data.schedule_enabled,
      schedule_times: query.data.schedule_times,
      timezone: query.data.timezone,
    });
  }, [query.data]);
  useEffect(() => {
    if (!nowcoder.data) return;
    setNowcoderForm({
      enabled: nowcoder.data.enabled,
      search_query: nowcoder.data.search_query,
      city: nowcoder.data.city,
      result_limit: nowcoder.data.result_limit,
      schedule_enabled: nowcoder.data.schedule_enabled,
      schedule_times: nowcoder.data.schedule_times,
    });
  }, [nowcoder.data]);
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["boss-connector"] }),
      client.invalidateQueries({ queryKey: ["onboarding"] }),
    ]);
  };
  const save = useMutation({ mutationFn: configureBossConnector, onSuccess: async () => { setMessage("设置已保存。"); await refresh(); } });
  const health = useMutation({ mutationFn: checkBossConnector, onSuccess: async (data) => { setMessage(connectorHealthMessage("BOSS", data)); await refresh(); } });
  const login = useMutation({ mutationFn: loginBossConnector, onSuccess: async () => { setMessage("BOSS 登录已确认。"); await refresh(); } });
  const scan = useMutation({ mutationFn: scanBossConnector, onSuccess: async (run) => { setMessage(`扫描完成：新增 ${run.created_count}，更新 ${run.updated_count}，重复 ${run.duplicate_count}，隔离 ${run.quarantined_count}。`); await refresh(); } });
  const refreshNowcoder = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["nowcoder-connector"] }),
      client.invalidateQueries({ queryKey: ["onboarding"] }),
    ]);
  };
  const saveNowcoder = useMutation({ mutationFn: configureNowcoderConnector, onSuccess: async () => { setMessage("牛客数据源设置已保存。"); await refreshNowcoder(); } });
  const healthNowcoder = useMutation({ mutationFn: checkNowcoderConnector, onSuccess: async (data) => { setMessage(connectorHealthMessage("牛客", data)); await refreshNowcoder(); } });
  const loginNowcoder = useMutation({ mutationFn: loginNowcoderConnector, onSuccess: async () => { setMessage("牛客登录已确认。"); await refreshNowcoder(); } });
  const scanNowcoder = useMutation({ mutationFn: scanNowcoderConnector, onSuccess: async (run) => { setMessage(`牛客同步完成：发现 ${run.discovered_count}，新增 ${run.created_count}，更新 ${run.updated_count}，重复 ${run.duplicate_count}。`); await refreshNowcoder(); } });
  const error = save.error || health.error || login.error || scan.error || saveNowcoder.error || healthNowcoder.error || loginNowcoder.error || scanNowcoder.error;
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(form); };
  const nowcoderScanBlocked = !nowcoderForm.enabled
    ? "请先启用牛客来源并保存设置。"
    : nowcoder.data?.session_status !== "authenticated"
      ? "请先打开牛客登录并检查状态。"
      : "";
  const bossScanBlocked = !form.enabled
    ? "请先启用 BOSS 来源并保存设置。"
    : !form.search_query.trim()
      ? "请先填写要搜索的岗位关键词。"
      : query.data?.session_status !== "authenticated"
        ? "请先打开 BOSS 登录并检查状态。"
        : "";

  return <>
    {!setupOnly && <header className="page-header"><div><p className="eyebrow">招聘信息来源</p><h1>招聘信息来源</h1><p>管理每日招聘信息与手动定向搜索。OpenCLI 只作为外部应用被调用。</p></div><span className={`health-pill ${nowcoder.data?.health_status === "healthy" ? "ok" : ""}`}>{connectorStatusLabel(nowcoder.data?.health_status, nowcoder.data?.last_error_code)}</span></header>}
    {!setupOnly && <section className="notice"><strong>只读安全边界</strong><p>CareerConsole 通过外部 OpenCLI 读取牛客校招日程及可选的 BOSS 岗位信息，不提供打招呼、发消息、交换联系方式、邀请、收藏、订阅或自动投递。</p></section>}
    {message && <section className="notice success">{message}</section>}
    {error && <section className="notice error" role="alert">{error.message}</section>}
    <section className="panel settings-anchor-card" id="source-nowcoder" tabIndex={-1}>
      <div className="panel-heading"><div><p className="eyebrow">每日招聘</p><h2>牛客校招日程</h2></div><span>{setupOnly ? connectorStatusLabel(nowcoder.data?.health_status, nowcoder.data?.last_error_code) : nowcoder.data?.last_success_at ? `最近成功 ${formatChinaTime(nowcoder.data.last_success_at)}（北京时间）` : "尚未同步"}</span></div>
      <section className="notice"><strong>日期边界</strong><p>自动任务只获取中国时间当天新收录的信息，不向前回扫。最近 7、14 或 30 天只能由你在下方主动选择并执行，最长不超过一个月。</p></section>
      <form className="form-grid" onSubmit={(event) => { event.preventDefault(); saveNowcoder.mutate(nowcoderForm); }}>
        <label><span>启用来源</span><input type="checkbox" checked={nowcoderForm.enabled} onChange={e => setNowcoderForm({ ...nowcoderForm, enabled: e.target.checked })} /></label>
        <label><span>公司关键词（可选）</span><input value={nowcoderForm.search_query} placeholder="留空表示全部" onChange={e => setNowcoderForm({ ...nowcoderForm, search_query: e.target.value })} /></label>
        <label><span>每次最多条数</span><input type="number" min="1" max="1000" value={nowcoderForm.result_limit} onChange={e => setNowcoderForm({ ...nowcoderForm, result_limit: Number(e.target.value) })} /></label>
        <label><span>每日 09:00 自动获取当天</span><input type="checkbox" checked={nowcoderForm.schedule_enabled} onChange={e => setNowcoderForm({ ...nowcoderForm, schedule_enabled: e.target.checked })} /></label>
        <SessionSummary connector={nowcoder.data} />
        <div className="form-actions wide"><button type="submit" disabled={saveNowcoder.isPending}>{saveNowcoder.isPending ? "正在保存…" : "保存牛客设置"}</button><button type="button" className="secondary" onClick={() => loginNowcoder.mutate()} disabled={loginNowcoder.isPending}>{loginNowcoder.isPending ? "正在打开…" : "打开登录"}</button><button type="button" className="secondary" onClick={() => healthNowcoder.mutate()} disabled={healthNowcoder.isPending}>{healthNowcoder.isPending ? "正在检查…" : "检查登录状态"}</button></div>
      </form>
      {!setupOnly && <div className="form-actions">
        <label><span>手动获取范围</span><select value={lookback} onChange={e => setLookback(Number(e.target.value) as 0 | 7 | 14 | 30)}><option value={0}>仅今天</option><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select></label>
        <button type="button" onClick={() => scanNowcoder.mutate(lookback)} disabled={scanNowcoder.isPending || Boolean(nowcoderScanBlocked)}>{scanNowcoder.isPending ? "正在获取…" : "主动获取"}</button>
      </div>}
      {!setupOnly && nowcoderScanBlocked && <p className="disabled-reason">{nowcoderScanBlocked}</p>}
    </section>
    {!setupOnly && <section className="panel table-wrap"><div className="panel-heading"><div><p className="eyebrow">同步记录</p><h2>牛客同步记录</h2></div></div><table><thead><tr><th>时间（北京时间）</th><th>触发</th><th>状态</th><th>发现</th><th>新增 / 更新 / 重复 / 隔离</th></tr></thead><tbody>{nowcoder.data?.runs.map(run => <tr key={run.id}><td>{formatChinaTime(run.started_at)}</td><td>{triggerLabels[run.trigger_type] ?? "系统任务"}</td><td>{runStatusLabels[run.status] ?? "已结束"}{run.error_code && <details className="audit-details"><summary>查看失败信息</summary><small>{connectorErrors[run.error_code] ?? `错误代码：${run.error_code}`}</small></details>}</td><td>{run.discovered_count}</td><td>{run.created_count} / {run.updated_count} / {run.duplicate_count} / {run.quarantined_count}</td></tr>)}</tbody></table></section>}
    <section className="panel settings-anchor-card" id="source-boss" tabIndex={-1}>
      <div className="panel-heading"><div><p className="eyebrow">手动定向搜索</p><h2>BOSS 直聘</h2></div><span>{setupOnly ? connectorStatusLabel(query.data?.health_status, query.data?.last_error_code) : query.data?.last_success_at ? `最近成功 ${formatChinaTime(query.data.last_success_at)}（北京时间）` : "尚未同步"}</span></div>
      <form className="form-grid" onSubmit={submit}>
        <label><span>启用来源</span><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} /></label>
        <label><span>浏览器登录配置名称</span><input value={form.profile_alias} onChange={e => setForm({ ...form, profile_alias: e.target.value })} /></label>
        <label><span>搜索关键词</span><input value={form.search_query} placeholder="例如 Python 后端" onChange={e => setForm({ ...form, search_query: e.target.value })} /></label>
        <label><span>城市</span><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} /></label>
        <label><span>每次岗位数</span><input type="number" min="1" max="50" value={form.result_limit} onChange={e => setForm({ ...form, result_limit: Number(e.target.value) })} /></label>
        <div className="wide cursor-strip"><span>BOSS 使用方式</span><strong>仅手动定向搜索；每日自动信息获取由牛客承担</strong></div>
        <SessionSummary connector={query.data} />
        <div className="form-actions"><button type="submit" disabled={save.isPending}>{save.isPending ? "正在保存…" : "保存 BOSS 设置"}</button><button type="button" className="secondary" onClick={() => health.mutate()} disabled={health.isPending}>{health.isPending ? "正在测试…" : "测试环境与登录"}</button><button type="button" className="secondary" onClick={() => login.mutate()} disabled={login.isPending}>{login.isPending ? "正在打开…" : "打开登录"}</button>{!setupOnly && <button type="button" onClick={() => scan.mutate()} disabled={scan.isPending || Boolean(bossScanBlocked)}>{scan.isPending ? "正在搜索…" : "立即搜索"}</button>}</div>
        {health.isPending && <p className="disabled-reason wide">正在检查 OpenCLI 与浏览器登录状态，最多等待 15 秒。</p>}
      </form>
      {!setupOnly && bossScanBlocked && <p className="disabled-reason">{bossScanBlocked}</p>}
      <details><summary>这项配置是什么</summary><p>浏览器登录配置名称用于选择 OpenCLI 已保存的浏览器会话；通常保留 <code>default</code> 即可。</p></details>
    </section>
    {!setupOnly && <><section className="panel table-wrap"><div className="panel-heading"><div><p className="eyebrow">同步记录</p><h2>BOSS 最近同步</h2></div></div><table><thead><tr><th>时间（北京时间）</th><th>触发</th><th>状态</th><th>发现</th><th>新增 / 更新 / 重复 / 隔离</th></tr></thead><tbody>{query.data?.runs.map(run => <tr key={run.id}><td>{formatChinaTime(run.started_at)}</td><td>{triggerLabels[run.trigger_type] ?? "系统任务"}</td><td>{runStatusLabels[run.status] ?? "已结束"}{run.error_code && <details className="audit-details"><summary>查看失败信息</summary><small>{connectorErrors[run.error_code] ?? `错误代码：${run.error_code}`}</small></details>}</td><td>{run.discovered_count}</td><td>{run.created_count} / {run.updated_count} / {run.duplicate_count} / {run.quarantined_count}</td></tr>)}</tbody></table></section>
    {!!query.data?.quarantine.length && <section className="panel"><div className="panel-heading"><h2>未导入的数据</h2><span>不会写入岗位池</span></div>{query.data.quarantine.map(item => <details className="audit-details" key={item.id}><summary>一条数据因格式问题未导入</summary><p>请重新搜索或检查网站插件是否需要更新。</p><small>外部记录：{item.external_id} · 错误代码：{item.error_code}</small></details>)}</section>}</>}
  </>;
}
