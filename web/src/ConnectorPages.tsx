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

export function DataSourcesPage() {
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
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["boss-connector"] }); };
  const save = useMutation({ mutationFn: configureBossConnector, onSuccess: async () => { setMessage("设置已保存。"); await refresh(); } });
  const health = useMutation({ mutationFn: checkBossConnector, onSuccess: async (data) => { setMessage(data.status === "healthy" ? `OpenCLI ${data.opencli_version ?? ""}，登录有效。` : `检查结果：${data.error_code ?? data.status}`); await refresh(); } });
  const login = useMutation({ mutationFn: loginBossConnector, onSuccess: async () => { setMessage("BOSS 登录已确认。"); await refresh(); } });
  const scan = useMutation({ mutationFn: scanBossConnector, onSuccess: async (run) => { setMessage(`扫描完成：新增 ${run.created_count}，更新 ${run.updated_count}，重复 ${run.duplicate_count}，隔离 ${run.quarantined_count}。`); await refresh(); } });
  const refreshNowcoder = async () => { await client.invalidateQueries({ queryKey: ["nowcoder-connector"] }); };
  const saveNowcoder = useMutation({ mutationFn: configureNowcoderConnector, onSuccess: async () => { setMessage("牛客数据源设置已保存。"); await refreshNowcoder(); } });
  const healthNowcoder = useMutation({ mutationFn: checkNowcoderConnector, onSuccess: async (data) => { setMessage(data.status === "healthy" ? `牛客插件可用 · OpenCLI ${data.opencli_version ?? ""}` : `牛客检查结果：${data.error_code ?? data.status}`); await refreshNowcoder(); } });
  const scanNowcoder = useMutation({ mutationFn: scanNowcoderConnector, onSuccess: async (run) => { setMessage(`牛客同步完成：发现 ${run.discovered_count}，新增 ${run.created_count}，更新 ${run.updated_count}，重复 ${run.duplicate_count}。`); await refreshNowcoder(); } });
  const error = save.error || health.error || login.error || scan.error || saveNowcoder.error || healthNowcoder.error || scanNowcoder.error;
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(form); };

  return <>
    <header className="page-header"><div><p className="eyebrow">CONTROLLED CONNECTORS</p><h1>数据来源</h1></div><span className={`health-pill ${query.data?.health_status === "healthy" ? "ok" : ""}`}>{query.data?.health_status ?? "检查中"}</span></header>
    <section className="notice"><strong>只读安全边界</strong><p>Career 通过外部 OpenCLI 读取牛客校招日程及可选的 BOSS 岗位信息，不提供打招呼、发消息、交换联系方式、邀请、收藏、订阅或自动投递。</p></section>
    {message && <section className="notice success">{message}</section>}
    {error && <section className="notice error" role="alert">{error.message}</section>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">OPENCLI · NOWCODER</p><h2>牛客校招日程</h2></div><span>{nowcoder.data?.last_success_at ? `最近成功 ${formatChinaTime(nowcoder.data.last_success_at)}（北京时间）` : "尚未同步"}</span></div>
      <section className="notice"><strong>日期边界</strong><p>自动任务只获取中国时间当天新收录的信息，不向前回扫。最近 7、14 或 30 天只能由你在下方主动选择并执行，最长不超过一个月。</p></section>
      <form className="form-grid" onSubmit={(event) => { event.preventDefault(); saveNowcoder.mutate(nowcoderForm); }}>
        <label><span>启用来源</span><input type="checkbox" checked={nowcoderForm.enabled} onChange={e => setNowcoderForm({ ...nowcoderForm, enabled: e.target.checked })} /></label>
        <label><span>公司关键词（可选）</span><input value={nowcoderForm.search_query} placeholder="留空表示全部" onChange={e => setNowcoderForm({ ...nowcoderForm, search_query: e.target.value })} /></label>
        <label><span>每次最多条数</span><input type="number" min="1" max="1000" value={nowcoderForm.result_limit} onChange={e => setNowcoderForm({ ...nowcoderForm, result_limit: Number(e.target.value) })} /></label>
        <label><span>每日 09:00 自动获取当天</span><input type="checkbox" checked={nowcoderForm.schedule_enabled} onChange={e => setNowcoderForm({ ...nowcoderForm, schedule_enabled: e.target.checked })} /></label>
        <div className="form-actions wide"><button type="submit" disabled={saveNowcoder.isPending}>保存设置</button><button type="button" className="secondary" onClick={() => healthNowcoder.mutate()} disabled={healthNowcoder.isPending}>检查插件</button></div>
      </form>
      <div className="form-actions">
        <label><span>手动获取范围</span><select value={lookback} onChange={e => setLookback(Number(e.target.value) as 0 | 7 | 14 | 30)}><option value={0}>仅今天</option><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select></label>
        <button type="button" onClick={() => scanNowcoder.mutate(lookback)} disabled={scanNowcoder.isPending || !nowcoderForm.enabled}>主动获取</button>
      </div>
    </section>
    <section className="panel table-wrap"><div className="panel-heading"><div><p className="eyebrow">NOWCODER SYNC HISTORY</p><h2>牛客同步记录</h2></div></div><table><thead><tr><th>时间（北京时间）</th><th>触发</th><th>状态</th><th>发现</th><th>新增 / 更新 / 重复 / 隔离</th></tr></thead><tbody>{nowcoder.data?.runs.map(run => <tr key={run.id}><td>{formatChinaTime(run.started_at)}</td><td>{run.trigger_type}</td><td>{run.status}{run.error_code ? ` · ${run.error_code}` : ""}</td><td>{run.discovered_count}</td><td>{run.created_count} / {run.updated_count} / {run.duplicate_count} / {run.quarantined_count}</td></tr>)}</tbody></table></section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">OPENCLI · BOSS</p><h2>BOSS 直聘</h2></div><span>{query.data?.last_success_at ? `最近成功 ${formatChinaTime(query.data.last_success_at)}（北京时间）` : "尚未同步"}</span></div>
      <form className="form-grid" onSubmit={submit}>
        <label><span>启用来源</span><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} /></label>
        <label><span>Browser Profile alias</span><input value={form.profile_alias} onChange={e => setForm({ ...form, profile_alias: e.target.value })} /></label>
        <label><span>搜索关键词</span><input value={form.search_query} placeholder="例如 Python 后端" onChange={e => setForm({ ...form, search_query: e.target.value })} /></label>
        <label><span>城市</span><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} /></label>
        <label><span>每次岗位数</span><input type="number" min="1" max="50" value={form.result_limit} onChange={e => setForm({ ...form, result_limit: Number(e.target.value) })} /></label>
        <div className="wide cursor-strip"><span>BOSS 使用方式</span><strong>仅手动定向搜索；每日自动信息获取由牛客承担</strong></div>
        <div className="form-actions"><button type="submit" disabled={save.isPending}>保存设置</button><button type="button" className="secondary" onClick={() => health.mutate()} disabled={health.isPending}>检查环境与登录</button><button type="button" className="secondary" onClick={() => login.mutate()} disabled={login.isPending}>打开登录</button><button type="button" onClick={() => scan.mutate()} disabled={scan.isPending || !form.enabled}>立即扫描</button></div>
      </form>
    </section>
    <section className="panel table-wrap"><div className="panel-heading"><div><p className="eyebrow">SYNC HISTORY</p><h2>最近同步</h2></div></div><table><thead><tr><th>时间（北京时间）</th><th>触发</th><th>状态</th><th>发现</th><th>新增 / 更新 / 重复 / 隔离</th></tr></thead><tbody>{query.data?.runs.map(run => <tr key={run.id}><td>{formatChinaTime(run.started_at)}</td><td>{run.trigger_type}</td><td>{run.status}{run.error_code ? ` · ${run.error_code}` : ""}</td><td>{run.discovered_count}</td><td>{run.created_count} / {run.updated_count} / {run.duplicate_count} / {run.quarantined_count}</td></tr>)}</tbody></table></section>
    {!!query.data?.quarantine.length && <section className="panel"><div className="panel-heading"><h2>隔离数据</h2><span>不会写入岗位池</span></div>{query.data.quarantine.map(item => <p key={item.id}><code>{item.external_id}</code> · {item.error_code}</p>)}</section>}
  </>;
}
