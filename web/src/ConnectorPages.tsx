import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  BossConnectorUpdate,
  checkBossConnector,
  configureBossConnector,
  getBossConnector,
  loginBossConnector,
  scanBossConnector,
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

export function DataSourcesPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["boss-connector"], queryFn: getBossConnector });
  const [form, setForm] = useState(initial);
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
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["boss-connector"] }); };
  const save = useMutation({ mutationFn: configureBossConnector, onSuccess: async () => { setMessage("设置已保存。"); await refresh(); } });
  const health = useMutation({ mutationFn: checkBossConnector, onSuccess: async (data) => { setMessage(data.status === "healthy" ? `OpenCLI ${data.opencli_version ?? ""}，登录有效。` : `检查结果：${data.error_code ?? data.status}`); await refresh(); } });
  const login = useMutation({ mutationFn: loginBossConnector, onSuccess: async () => { setMessage("BOSS 登录已确认。"); await refresh(); } });
  const scan = useMutation({ mutationFn: scanBossConnector, onSuccess: async (run) => { setMessage(`扫描完成：新增 ${run.created_count}，更新 ${run.updated_count}，重复 ${run.duplicate_count}，隔离 ${run.quarantined_count}。`); await refresh(); } });
  const error = save.error || health.error || login.error || scan.error;
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(form); };

  return <>
    <header className="page-header"><div><p className="eyebrow">CONTROLLED CONNECTORS</p><h1>数据来源</h1></div><span className={`health-pill ${query.data?.health_status === "healthy" ? "ok" : ""}`}>{query.data?.health_status ?? "检查中"}</span></header>
    <section className="notice"><strong>只读安全边界</strong><p>Career 只调用外部 OpenCLI 的 BOSS 登录、状态、搜索和详情命令，不提供打招呼、发消息、交换联系方式、邀请或自动投递。</p></section>
    {message && <section className="notice success">{message}</section>}
    {error && <section className="notice error" role="alert">{error.message}</section>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">OPENCLI · BOSS</p><h2>BOSS 直聘</h2></div><span>{query.data?.last_success_at ? `最近成功 ${formatChinaTime(query.data.last_success_at)}（北京时间）` : "尚未同步"}</span></div>
      <form className="form-grid" onSubmit={submit}>
        <label><span>启用来源</span><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} /></label>
        <label><span>Browser Profile alias</span><input value={form.profile_alias} onChange={e => setForm({ ...form, profile_alias: e.target.value })} /></label>
        <label><span>搜索关键词</span><input value={form.search_query} placeholder="例如 Python 后端" onChange={e => setForm({ ...form, search_query: e.target.value })} /></label>
        <label><span>城市</span><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} /></label>
        <label><span>每次岗位数</span><input type="number" min="1" max="50" value={form.result_limit} onChange={e => setForm({ ...form, result_limit: Number(e.target.value) })} /></label>
        <label><span>每日 09:00 / 18:00</span><input type="checkbox" checked={form.schedule_enabled} onChange={e => setForm({ ...form, schedule_enabled: e.target.checked })} /></label>
        <div className="form-actions"><button type="submit" disabled={save.isPending}>保存设置</button><button type="button" className="secondary" onClick={() => health.mutate()} disabled={health.isPending}>检查环境与登录</button><button type="button" className="secondary" onClick={() => login.mutate()} disabled={login.isPending}>打开登录</button><button type="button" onClick={() => scan.mutate()} disabled={scan.isPending || !form.enabled}>立即扫描</button></div>
      </form>
    </section>
    <section className="panel table-wrap"><div className="panel-heading"><div><p className="eyebrow">SYNC HISTORY</p><h2>最近同步</h2></div></div><table><thead><tr><th>时间（北京时间）</th><th>触发</th><th>状态</th><th>发现</th><th>新增 / 更新 / 重复 / 隔离</th></tr></thead><tbody>{query.data?.runs.map(run => <tr key={run.id}><td>{formatChinaTime(run.started_at)}</td><td>{run.trigger_type}</td><td>{run.status}{run.error_code ? ` · ${run.error_code}` : ""}</td><td>{run.discovered_count}</td><td>{run.created_count} / {run.updated_count} / {run.duplicate_count} / {run.quarantined_count}</td></tr>)}</tbody></table></section>
    {!!query.data?.quarantine.length && <section className="panel"><div className="panel-heading"><h2>隔离数据</h2><span>不会写入岗位池</span></div>{query.data.quarantine.map(item => <p key={item.id}><code>{item.external_id}</code> · {item.error_code}</p>)}</section>}
  </>;
}
