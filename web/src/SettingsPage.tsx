import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import {
  configureQQChannel,
  configureOpenCli,
  configureScheduler,
  createWorkspace,
  deleteQQChannel,
  deleteProvider,
  exportPortableWorkspace,
  getChannelDeliveries,
  getConfiguration,
  getConfigurationChanges,
  getOpenCliConfiguration,
  getProviderCatalog,
  getProviders,
  getProviderTests,
  getQQChannel,
  getSchedulerRuns,
  getWorkspaceStatus,
  importPortableWorkspace,
  pickWorkspaceDirectory,
  reopenOnboarding,
  restartService,
  testProvider,
  testQQChannel,
  updateAgentConfiguration,
  updateConfiguration,
  upsertProvider,
  type AgentConfiguration,
  type AgentTaskName,
  validateWorkspace,
  type CareerConsoleConfiguration,
  type ConfigurationStatus,
} from "./api";

function applyAppearance(configuration: CareerConsoleConfiguration) {
  document.documentElement.dataset.density = configuration.appearance.density;
  document.documentElement.classList.toggle(
    "reduce-motion", configuration.appearance.reduce_motion,
  );
}

function ConfigurationForm({ status }: { status: ConfigurationStatus }) {
  const client = useQueryClient();
  const [saved, setSaved] = useState<ConfigurationStatus | null>(null);
  useEffect(() => applyAppearance(status.configuration), [status.configuration]);
  const save = useMutation({
    mutationFn: ({ configuration, reason }: { configuration: CareerConsoleConfiguration; reason: string }) =>
      updateConfiguration(status.revision, configuration, reason),
    onSuccess: async (result) => {
      applyAppearance(result.configuration); setSaved(result);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["configuration"] }),
        client.invalidateQueries({ queryKey: ["configuration-changes"] }),
      ]);
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const current = status.configuration;
    const configuration: CareerConsoleConfiguration = {
      general: {
        locale: String(data.get("locale")) as "zh-CN" | "en-US",
        timezone: String(data.get("timezone")),
        date_format: String(data.get("date_format")) as "yyyy-MM-dd" | "yyyy/MM/dd",
        open_browser_on_start: data.has("open_browser_on_start"),
      },
      appearance: {
        density: String(data.get("density")) as "comfortable" | "compact",
        reduce_motion: data.has("reduce_motion"),
      },
      runtime: {
        log_level: String(data.get("log_level")) as CareerConsoleConfiguration["runtime"]["log_level"],
        log_retention_days: Number(data.get("log_retention_days")),
        agent_trace_retention_days: Number(data.get("agent_trace_retention_days")),
        job_lease_seconds: Number(data.get("job_lease_seconds")),
        max_document_mb: Number(data.get("max_document_mb")),
      },
      privacy: {
        diagnostics_metadata_enabled: data.has("diagnostics_metadata_enabled"),
        redact_sensitive_logs: current.privacy.redact_sensitive_logs,
        local_only_network_binding: current.privacy.local_only_network_binding,
      },
      providers: current.providers,
      agents: current.agents,
      connectors: current.connectors,
      channels: current.channels,
      scheduler: current.scheduler,
    };
    save.mutate({ configuration, reason: String(data.get("reason")) });
  }
  const item = status.configuration;
  return <form onSubmit={submit} className="settings-stack">
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">GENERAL</p><h2>常规</h2></div><span>revision {status.revision}</span></div><div className="form-grid">
      <label>界面语言<select name="locale" defaultValue={item.general.locale}><option value="zh-CN">简体中文</option><option value="en-US">English</option></select></label>
      <label>业务时区<input name="timezone" defaultValue={item.general.timezone} required /></label>
      <label>日期格式<select name="date_format" defaultValue={item.general.date_format}><option value="yyyy-MM-dd">2026-07-26</option><option value="yyyy/MM/dd">2026/07/26</option></select></label>
      <label className="check-row"><input type="checkbox" name="open_browser_on_start" defaultChecked={item.general.open_browser_on_start} />启动后自动打开浏览器</label>
    </div></section>
    <section className="panel"><div><p className="eyebrow">APPEARANCE · HOT RELOAD</p><h2>外观</h2></div><div className="form-grid">
      <label>界面密度<select name="density" defaultValue={item.appearance.density}><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label>
      <label className="check-row"><input type="checkbox" name="reduce_motion" defaultChecked={item.appearance.reduce_motion} />减少界面动效</label>
    </div></section>
    <section className="panel"><div><p className="eyebrow">RUNTIME · RESTART REQUIRED</p><h2>运行维护</h2></div><div className="form-grid">
      <label>日志级别<select name="log_level" defaultValue={item.runtime.log_level}>{["DEBUG", "INFO", "WARNING", "ERROR"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>日志保留天数<input name="log_retention_days" type="number" min="1" max="365" defaultValue={item.runtime.log_retention_days} /></label>
      <label>Agent 审计保留天数<input name="agent_trace_retention_days" type="number" min="1" max="3650" defaultValue={item.runtime.agent_trace_retention_days} /></label>
      <label>后台任务租约（秒）<input name="job_lease_seconds" type="number" min="10" max="3600" defaultValue={item.runtime.job_lease_seconds} /></label>
      <label>单个文档上限（MB）<input name="max_document_mb" type="number" min="1" max="50" defaultValue={item.runtime.max_document_mb} /></label>
    </div></section>
    <section className="panel"><div><p className="eyebrow">PRIVACY</p><h2>隐私与安全</h2></div><div className="security-grid"><label className="check-row"><input type="checkbox" name="diagnostics_metadata_enabled" defaultChecked={item.privacy.diagnostics_metadata_enabled} />保存不含业务正文的诊断元数据</label><p>敏感日志脱敏：强制开启</p><p>仅绑定本机网络：强制开启</p><p>此配置文件不接受 API Key、Token 或邮箱授权码。</p></div></section>
    <section className="panel save-bar"><label>变更原因<input name="reason" defaultValue="用户从设置页面更新配置" required maxLength={300} /></label><button disabled={save.isPending}>{save.isPending ? "保存中…" : "保存配置"}</button>{saved && <div className={`notice ${saved.activation_effect === "hot_reload" ? "success" : "warning"}`}><strong>{saved.activation_effect === "hot_reload" ? "配置已热更新" : "配置已保存，需要重启"}</strong><p>revision {saved.revision} · {saved.changed_paths?.join("、")}</p></div>}{save.error && <p className="form-error">{save.error.message}</p>}</section>
  </form>;
}

const TASK_LABELS: Record<AgentTaskName, string> = {
  fact_extraction: "事实提取", mail_intelligence: "邮件分析",
  profile_insight: "档案洞察", job_fit: "岗位匹配",
  resume_direction: "简历方向", resume_drafting: "简历撰写（Drafter）",
  material_review: "材料复核（Reviewer）",
};

export function ProviderAgentConfiguration({ status }: { status: ConfigurationStatus }) {
  const client = useQueryClient();
  const catalog = useQuery({ queryKey: ["provider-catalog"], queryFn: getProviderCatalog });
  const providers = useQuery({ queryKey: ["providers"], queryFn: getProviders });
  const tests = useQuery({ queryKey: ["provider-tests"], queryFn: getProviderTests });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["configuration"] }),
      client.invalidateQueries({ queryKey: ["providers"] }),
      client.invalidateQueries({ queryKey: ["provider-tests"] }),
      client.invalidateQueries({ queryKey: ["configuration-changes"] }),
    ]);
  };
  const saveProvider = useMutation({
    mutationFn: ({ id, form }: { id: string; form: FormData }) => upsertProvider(id, {
      expected_revision: status.revision,
      provider_type: String(form.get("provider_type")) as Parameters<typeof upsertProvider>[1]["provider_type"],
      display_name: String(form.get("display_name")), enabled: form.has("enabled"),
      api_base: String(form.get("api_base") || "") || null,
      default_model: String(form.get("default_model")),
      models: String(form.get("models") || "").split(/[\n,]/).map(value => value.trim()).filter(Boolean),
      ...(form.get("api_key") ? { api_key: String(form.get("api_key")) } : {}),
    }),
    onSuccess: refresh,
  });
  const removeProvider = useMutation({
    mutationFn: (id: string) => deleteProvider(id, status.revision), onSuccess: refresh,
  });
  const runTest = useMutation({
    mutationFn: (id: string) => testProvider(id), onSuccess: refresh,
  });
  const saveAgents = useMutation({
    mutationFn: (agents: AgentConfiguration) => updateAgentConfiguration(status.revision, agents),
    onSuccess: refresh,
  });
  function providerSubmit(event: FormEvent<HTMLFormElement>, existingId?: string) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    saveProvider.mutate({ id: existingId ?? String(form.get("provider_id")), form });
  }
  function agentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const tasks = Object.fromEntries((Object.keys(TASK_LABELS) as AgentTaskName[]).map(name => {
      const current = status.configuration.agents.tasks[name];
      return [name, { ...current, enabled: form.has(`${name}.enabled`),
        provider_id: String(form.get(`${name}.provider_id`) || "") || null,
        model: String(form.get(`${name}.model`) || "") || null }];
    })) as AgentConfiguration["tasks"];
    saveAgents.mutate({ tasks });
  }
  const providerItems = providers.data?.items ?? [];
  return <div className="settings-stack provider-settings">
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">PROVIDERS · KEYRING SECRETS</p><h2>模型 Provider</h2></div><span>{providerItems.length} 个</span></div>
      <p className="section-note">API Key 只写入操作系统凭据库；保存后不会回显，也不会进入工作区配置或审计记录。</p>
      {providerItems.map(item => <details className="provider-editor" key={item.id}><summary>{item.display_name} · {item.default_model} · {item.has_secret ? "凭据已配置" : "未配置凭据"}</summary>
        <form className="form-grid" onSubmit={event => providerSubmit(event, item.id)}>
          <label>类型<select name="provider_type" defaultValue={item.provider_type}>{catalog.data?.items.map(option => <option value={option.type} key={option.type}>{option.label}</option>)}</select></label>
          <label>显示名称<input name="display_name" defaultValue={item.display_name} required /></label>
          <label className="wide">API URL<input name="api_base" defaultValue={item.api_base ?? ""} placeholder="留空使用 Provider 默认地址" /></label>
          <label>默认模型<input name="default_model" defaultValue={item.default_model} required /></label>
          <label>可选模型（逗号或换行分隔）<textarea name="models" defaultValue={item.models.join("\n")} /></label>
          <label>更新 API Key<input name="api_key" type="password" autoComplete="new-password" placeholder={item.has_secret ? "已安全保存；留空保持不变" : "输入 API Key"} /></label>
          <label className="check-row"><input name="enabled" type="checkbox" defaultChecked={item.enabled} />启用 Provider</label>
          <div className="form-actions"><button disabled={saveProvider.isPending}>保存</button><button type="button" className="secondary" onClick={() => runTest.mutate(item.id)} disabled={runTest.isPending}>连接测试</button><button type="button" className="secondary" onClick={() => removeProvider.mutate(item.id)} disabled={removeProvider.isPending}>删除</button></div>
        </form></details>)}
      <details className="provider-editor"><summary>新增 Provider</summary><form className="form-grid" onSubmit={providerSubmit}>
        <label>Provider ID<input name="provider_id" pattern="[a-z][a-z0-9_-]{1,63}" placeholder="例如 main_openai" required /></label>
        <label>类型<select name="provider_type" defaultValue="openai">{catalog.data?.items.map(option => <option value={option.type} key={option.type}>{option.label}</option>)}</select></label>
        <label>显示名称<input name="display_name" required /></label><label>API URL<input name="api_base" /></label>
        <label>默认模型<input name="default_model" required /></label><label>可选模型<textarea name="models" /></label>
        <label>API Key<input name="api_key" type="password" autoComplete="new-password" /></label>
        <label className="check-row"><input name="enabled" type="checkbox" defaultChecked />启用 Provider</label>
        <div className="form-actions"><button disabled={saveProvider.isPending}>新增并安全保存</button></div>
      </form></details>
      {(saveProvider.error || removeProvider.error || runTest.error) && <p className="form-error">{(saveProvider.error ?? removeProvider.error ?? runTest.error)?.message}</p>}
      {runTest.data && <div className={`notice ${runTest.data.status === "passed" ? "success" : "error"}`}><strong>{runTest.data.status === "passed" ? "连接测试通过" : "连接测试失败"}</strong><p>{runTest.data.model} · {runTest.data.duration_ms}ms{runTest.data.error_code ? ` · ${runTest.data.error_code}` : ""}</p></div>}
    </section>
    <section className="panel"><div><p className="eyebrow">AGENT TASK ROUTING</p><h2>Agent 任务模型映射</h2></div><p className="section-note">每类业务任务可独立选择 Provider 和模型；Drafter 与 Reviewer 建议分别配置以形成交叉复核。</p>
      <form onSubmit={agentSubmit}><div className="agent-mapping-list">{(Object.keys(TASK_LABELS) as AgentTaskName[]).map(name => {
        const task = status.configuration.agents.tasks[name]; return <div className="agent-mapping-row" key={name}><label className="check-row"><input type="checkbox" name={`${name}.enabled`} defaultChecked={task.enabled} />{TASK_LABELS[name]}</label><label>Provider<select name={`${name}.provider_id`} defaultValue={task.provider_id ?? ""}><option value="">未配置</option>{providerItems.map(provider => <option value={provider.id} key={provider.id}>{provider.display_name}</option>)}</select></label><label>模型<input name={`${name}.model`} defaultValue={task.model ?? ""} placeholder="留空使用默认模型" /></label></div>;
      })}</div><div className="form-actions"><button disabled={saveAgents.isPending}>保存任务映射</button><span>保存后需重启 Agent Runtime</span></div>{saveAgents.error && <p className="form-error">{saveAgents.error.message}</p>}</form>
    </section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">SAFE CONNECTION AUDIT</p><h2>连接测试历史</h2></div><span>{tests.data?.total ?? 0} 条</span></div>{tests.data?.items.map(item => <article className="change-row" key={item.id}><strong>{item.provider_id} · {item.status === "passed" ? "通过" : "失败"}</strong><span>{item.model} · {item.duration_ms}ms{item.error_code ? ` · ${item.error_code}` : ""}</span><small>{new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</small></article>)}</section>
  </div>;
}

export function ChannelSettings({ status }: { status: ConfigurationStatus }) {
  const client = useQueryClient();
  const qq = useQuery({ queryKey: ["channel-qq"], queryFn: getQQChannel });
  const deliveries = useQuery({ queryKey: ["channel-deliveries"], queryFn: getChannelDeliveries });
  const refresh = async () => { await Promise.all([
    client.invalidateQueries({ queryKey: ["configuration"] }),
    client.invalidateQueries({ queryKey: ["configuration-changes"] }),
    client.invalidateQueries({ queryKey: ["channel-qq"] }),
    client.invalidateQueries({ queryKey: ["channel-deliveries"] }),
  ]); };
  const save = useMutation({ mutationFn: (form: FormData) => configureQQChannel({
    expected_revision: status.revision, enabled: form.has("enabled"),
    app_id: String(form.get("app_id") || ""),
    ...(form.get("secret") ? { secret: String(form.get("secret")) } : {}),
    allow_from: [],
    notification_targets: String(form.get("notification_targets") || "").split(/[\n,]/).map(value => value.trim()).filter(Boolean),
    event_subscriptions: ["task_reminder", "application_update", "daily_digest", "system_alert"].filter(name => form.has(`event.${name}`)),
    message_format: String(form.get("message_format")) as "plain" | "markdown",
    outbound_only: true,
    quiet_hours: { enabled: form.has("quiet_enabled"), start: String(form.get("quiet_start")),
      end: String(form.get("quiet_end")), timezone: "Asia/Shanghai" },
  }), onSuccess: refresh });
  const test = useMutation({ mutationFn: testQQChannel, onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => deleteQQChannel(status.revision), onSuccess: refresh });
  const config = status.configuration.channels.qq;
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); save.mutate(new FormData(event.currentTarget)); }
  return <div className="settings-stack provider-settings"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">OUTBOUND CHANNEL · QQ</p><h2>QQ 通知出口</h2></div><span>{qq.data?.has_secret ? "凭据已配置" : "未配置凭据"}</span></div>
    <p className="section-note">QQ 仅作为任务提醒、申请进度、每日摘要和系统告警的发送出口。目标格式为 <code>c2c:用户OpenID</code> 或 <code>group:群OpenID</code>，密钥保存后不会回显。</p>
    <form className="form-grid" onSubmit={submit}><label className="check-row"><input type="checkbox" name="enabled" defaultChecked={config.enabled} />启用 QQ 通知</label><label>App ID<input name="app_id" defaultValue={config.app_id} /></label>
      <label>App Secret<input name="secret" type="password" autoComplete="new-password" placeholder={qq.data?.has_secret ? "已安全保存；留空保持不变" : "输入 App Secret"} /></label>
      <label>消息格式<select name="message_format" defaultValue={config.message_format}><option value="plain">纯文本</option><option value="markdown">Markdown</option></select></label>
      <label className="wide">通知目标（每行一个）<textarea name="notification_targets" defaultValue={config.notification_targets.join("\n")} placeholder="c2c:user-open-id" /></label>
      <fieldset className="wide channel-events"><legend>事件订阅</legend>{[["task_reminder", "任务提醒"], ["application_update", "申请进度"], ["daily_digest", "每日摘要"], ["system_alert", "系统告警"]].map(([name, label]) => <label className="check-row" key={name}><input type="checkbox" name={`event.${name}`} defaultChecked={config.event_subscriptions.includes(name)} />{label}</label>)}</fieldset>
      <label className="check-row"><input type="checkbox" name="quiet_enabled" defaultChecked={config.quiet_hours.enabled} />启用免打扰</label><label>免打扰开始<input name="quiet_start" type="time" defaultValue={config.quiet_hours.start} /></label><label>免打扰结束<input name="quiet_end" type="time" defaultValue={config.quiet_hours.end} /></label>
      <div className="form-actions wide"><button disabled={save.isPending}>保存 QQ 配置</button><button className="secondary" type="button" onClick={() => test.mutate()} disabled={test.isPending || !config.enabled}>发送测试通知</button><button className="secondary" type="button" onClick={() => remove.mutate()} disabled={remove.isPending}>删除配置</button></div>
    </form>{(save.error || test.error || remove.error) && <p className="form-error">{(save.error ?? test.error ?? remove.error)?.message}</p>}{test.data && <div className={`notice ${test.data.status === "passed" ? "success" : "error"}`}><strong>{test.data.status === "passed" ? "测试通知已发送" : "测试发送失败"}</strong><p>{test.data.target_masked} · {test.data.duration_ms}ms{test.data.error_code ? ` · ${test.data.error_code}` : ""}</p></div>}
  </section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">CHANNEL DELIVERY AUDIT</p><h2>通知发送记录</h2></div><span>{deliveries.data?.total ?? 0} 条</span></div>{(deliveries.data?.items ?? []).map(item => <article className="change-row" key={item.id}><strong>QQ · {item.status === "passed" ? "成功" : "失败"}</strong><span>{item.event_type} · {item.target_masked} · {item.duration_ms}ms</span><small>{item.error_code ?? new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</small></article>)}</section></div>;
}

export function SchedulerSettings({ status }: { status: ConfigurationStatus }) {
  const client = useQueryClient();
  const runs = useQuery({ queryKey: ["scheduler-runs"], queryFn: getSchedulerRuns });
  const save = useMutation({ mutationFn: (form: FormData) => configureScheduler(status.revision, {
    enabled: form.has("enabled"), poll_seconds: Number(form.get("poll_seconds")),
    reminders_enabled: form.has("reminders_enabled"),
    connector_jobs_enabled: form.has("connector_jobs_enabled"),
    profile_maintenance_enabled: form.has("profile_maintenance_enabled"),
    profile_maintenance_time: String(form.get("profile_maintenance_time")),
    channel_dispatch_enabled: form.has("channel_dispatch_enabled"),
  }), onSuccess: async () => { await Promise.all([
    client.invalidateQueries({ queryKey: ["configuration"] }),
    client.invalidateQueries({ queryKey: ["configuration-changes"] }),
    client.invalidateQueries({ queryKey: ["scheduler-runs"] }),
  ]); } });
  const item = status.configuration.scheduler;
  return <div className="settings-stack provider-settings"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">BUSINESS SCHEDULER</p><h2>定时任务运行时</h2></div><span>Asia/Shanghai</span></div><p className="section-note">统一控制任务提醒、邮件轮询、牛客当天同步、档案维护与通知分发。失败会隔离记录，不会阻断其他任务。</p><form className="form-grid" onSubmit={event => { event.preventDefault(); save.mutate(new FormData(event.currentTarget)); }}>
    <label className="check-row"><input name="enabled" type="checkbox" defaultChecked={item.enabled} />启用 Scheduler</label><label>检查周期（秒）<input name="poll_seconds" type="number" min="10" max="3600" defaultValue={item.poll_seconds} /></label>
    <label className="check-row"><input name="reminders_enabled" type="checkbox" defaultChecked={item.reminders_enabled} />任务与日程提醒</label><label className="check-row"><input name="connector_jobs_enabled" type="checkbox" defaultChecked={item.connector_jobs_enabled} />邮箱与招聘数据源</label><label className="check-row"><input name="profile_maintenance_enabled" type="checkbox" defaultChecked={item.profile_maintenance_enabled} />每日档案维护</label><label>档案维护时间<input name="profile_maintenance_time" type="time" defaultValue={item.profile_maintenance_time} /></label><label className="check-row"><input name="channel_dispatch_enabled" type="checkbox" defaultChecked={item.channel_dispatch_enabled} />向 Channel 分发通知</label><div className="form-actions"><button disabled={save.isPending}>保存 Scheduler</button></div>
  </form>{save.error && <p className="form-error">{save.error.message}</p>}</section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">SCHEDULER RUN AUDIT</p><h2>调度运行记录</h2></div><span>{runs.data?.total ?? 0} 条</span></div>{(runs.data?.items ?? []).map(run => <article className="change-row" key={run.id}><strong>{run.trigger_type} · {run.status}</strong><span>提醒 {run.counters.reminders_triggered ?? 0} · 数据源 {run.counters.connector_runs_processed ?? 0} · 通知 {run.counters.channel_sent ?? 0}</span><small>{run.error_codes.join("、") || new Date(run.started_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</small></article>)}</section></div>;
}

export function DataSourceSettings() {
  const client = useQueryClient();
  const opencli = useQuery({ queryKey: ["opencli-configuration"], queryFn: getOpenCliConfiguration });
  const save = useMutation({ mutationFn: (value: string) => configureOpenCli(value || null), onSuccess: async () => {
    await Promise.all([client.invalidateQueries({ queryKey: ["opencli-configuration"] }), client.invalidateQueries({ queryKey: ["configuration"] })]);
  } });
  return <section className="panel provider-settings"><div className="panel-heading"><div><p className="eyebrow">EXTERNAL DATA SOURCES</p><h2>OpenCLI 与邮箱</h2></div><span>{opencli.data?.installed ? "OpenCLI 可用" : "OpenCLI 未检测到"}</span></div><form className="form-grid" onSubmit={event => { event.preventDefault(); save.mutate(String(new FormData(event.currentTarget).get("executable") || "")); }}><label className="wide">OpenCLI 可执行文件<input name="executable" defaultValue={opencli.data?.executable ?? ""} placeholder="留空自动从 PATH 查找；也可填写 opencli.cmd 绝对路径" /></label><div className="form-actions wide"><button disabled={save.isPending}>保存 OpenCLI 路径</button><a className="download-button secondary" href="/data-sources">配置牛客与 BOSS</a><a className="download-button secondary" href="/message-center">配置只读邮箱</a></div></form>{opencli.data?.resolved_executable && <p className="section-note">当前解析路径：{opencli.data.resolved_executable}</p>}{save.error && <p className="form-error">{save.error.message}</p>}</section>;
}

function WorkspaceTransfer() {
  const [includeSecrets, setIncludeSecrets] = useState(false);
  const createExport = useMutation({
    mutationFn: ({ include, passphrase }: { include: boolean; passphrase: string }) =>
      exportPortableWorkspace(include, passphrase),
  });
  const runImport = useMutation({
    mutationFn: ({ file, parent, passphrase }: { file: File; parent: string; passphrase: string }) =>
      importPortableWorkspace(file, parent, passphrase),
  });
  return <section className="panel provider-settings"><div className="panel-heading"><div><p className="eyebrow">PORTABLE WORKSPACE · CC-5</p><h2>迁移、导入与导出</h2></div><span>manifest + SHA-256</span></div>
    <p className="section-note">导出包含一致性数据库快照、配置、材料 Blob 和本地集成文件，不包含日志、旧备份或运行时文件。普通导出永不包含凭据。</p>
    <div className="workspace-grid">
      <form className="form-grid" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); createExport.mutate({ include: includeSecrets, passphrase: String(form.get("export_passphrase") || "") }); }}>
        <h3 className="wide">导出当前工作区</h3><label className="check-row wide"><input type="checkbox" name="include_secrets" checked={includeSecrets} onChange={event => setIncludeSecrets(event.currentTarget.checked)} />使用密码加密并包含已配置凭据</label>{includeSecrets && <label className="wide">导出密码（至少 12 个字符）<input type="password" name="export_passphrase" minLength={12} required autoComplete="new-password" /></label>}<div className="form-actions wide"><button disabled={createExport.isPending}>{createExport.isPending ? "正在生成…" : "生成迁移包"}</button></div>
        {createExport.data && <div className="notice success wide"><strong>迁移包已通过哈希封装</strong><p>{createExport.data.filename} · {(createExport.data.size_bytes / 1024 / 1024).toFixed(2)} MiB · {createExport.data.file_count} 个文件</p><a className="download-button" href={createExport.data.download_url}>下载迁移包</a></div>}{createExport.error && <p className="form-error wide">{createExport.error.message}</p>}
      </form>
      <form className="form-grid" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const file = form.get("workspace_archive"); if (file instanceof File) runImport.mutate({ file, parent: String(form.get("import_parent")), passphrase: String(form.get("import_passphrase") || "") }); }}>
        <h3 className="wide">恢复到新工作区</h3><label className="wide">迁移包<input type="file" name="workspace_archive" accept=".ccworkspace,application/zip" required /></label><label className="wide">新工作区父目录<input name="import_parent" required placeholder="例如 D:\CareerRestore" /></label><label className="wide">迁移包密码（普通包留空）<input type="password" name="import_passphrase" autoComplete="current-password" /></label><div className="form-actions wide"><button disabled={runImport.isPending}>{runImport.isPending ? "正在校验并恢复…" : "校验并导入"}</button></div>
        {runImport.data && <div className="notice success wide"><strong>新工作区已恢复并激活</strong><p>{runImport.data.workspace_path} · 凭据 {runImport.data.secrets_restored} 项</p>{runImport.data.restart_required && <p>请重启 CareerConsole 切换到恢复后的工作区。</p>}</div>}{runImport.error && <p className="form-error wide">{runImport.error.message}</p>}
      </form>
    </div><div className="security-grid"><p>防 Zip Slip 与链接穿越</p><p>限制文件数、大小和压缩比</p><p>SQLite quick_check + revision</p><p>凭据：PBKDF2 + AES-256-GCM</p></div>
  </section>;
}

export function SettingsPage() {
  const client = useQueryClient();
  const [section, setSection] = useState<"general" | "ai" | "sources" | "notifications" | "automation" | "data" | "advanced">("general");
  const [validation, setValidation] = useState<Awaited<ReturnType<typeof validateWorkspace>> | null>(null);
  const [workspaceParent, setWorkspaceParent] = useState("");
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: getWorkspaceStatus });
  const configuration = useQuery({ queryKey: ["configuration"], queryFn: getConfiguration });
  const changes = useQuery({ queryKey: ["configuration-changes"], queryFn: getConfigurationChanges });
  const validate = useMutation({ mutationFn: validateWorkspace, onSuccess: setValidation });
  const pickDirectory = useMutation({ mutationFn: () => pickWorkspaceDirectory(workspaceParent), onSuccess: result => { if (!result.cancelled && result.parent_directory) { setWorkspaceParent(result.parent_directory); setValidation(null); } } });
  const create = useMutation({ mutationFn: ({ parent, name }: { parent: string; name: string }) => createWorkspace(parent, name), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["workspace"] }); } });
  const reopen = useMutation({ mutationFn: async () => {
    await reopenOnboarding();
    try { await restartService(); } catch { /* Process replacement may close the response. */ }
  }, onSuccess: () => window.setTimeout(() => window.location.reload(), 1_500) });
  function submitWorkspace(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); const parent = String(data.get("parent_directory") ?? ""); const name = String(data.get("name") ?? "CareerConsole"); if (validation?.valid && validation.parent_directory === parent) create.mutate({ parent, name }); else validate.mutate(parent); }
  const error = workspace.error ?? configuration.error ?? changes.error;
  const sections = [["general", "常规与工作区"], ["ai", "AI 与 Agent"], ["sources", "数据来源"], ["notifications", "通知渠道"], ["automation", "自动任务"], ["data", "数据与迁移"], ["advanced", "高级诊断"]] as const;
  return <><header className="page-header"><div><p className="eyebrow">CAREERCONSOLE SETTINGS</p><h1>设置</h1><p>按能力分组管理配置；初始化后仍可随时修改。</p></div><span className={`health-pill ${configuration.data?.activation_status === "restart_required" ? "blocked" : "ok"}`}>{configuration.data?.activation_status === "restart_required" ? "有配置等待重启" : "配置已生效"}</span></header>
    {error && <p className="form-error">{error.message}</p>}
    <nav className="settings-nav" aria-label="设置分类">{sections.map(([value, label]) => <button type="button" className={section === value ? "active" : "secondary"} onClick={() => setSection(value)} key={value}>{label}</button>)}</nav>
    {section === "general" && <>{workspace.data && <section className="panel"><div className="panel-heading"><div><p className="eyebrow">WORKSPACE</p><h2>当前工作区</h2></div><span>{workspace.data.manifest?.schemaVersion ?? "临时启动工作区"}</span></div><dl className="path-list"><div><dt>根目录</dt><dd>{workspace.data.workspace_path}</dd></div><div><dt>数据库</dt><dd>{workspace.data.paths.database}</dd></div><div><dt>配置</dt><dd>{workspace.data.paths.config}</dd></div><div><dt>备份</dt><dd>{workspace.data.paths.backups}</dd></div><div><dt>导出</dt><dd>{workspace.data.paths.exports}</dd></div></dl><details><summary>创建或切换工作区</summary><form className="form-grid workspace-switch" onSubmit={submitWorkspace}><label>父目录<div className="path-picker-row"><input name="parent_directory" required placeholder="例如 D:\CareerWorkspace" value={workspaceParent} onChange={event => { setWorkspaceParent(event.target.value); setValidation(null); }} /><button className="secondary" type="button" disabled={pickDirectory.isPending} onClick={() => pickDirectory.mutate()}>{pickDirectory.isPending ? "正在选择…" : "选择文件夹"}</button></div></label><label>工作区名称<input name="name" defaultValue="CareerConsole" required /></label><button disabled={validate.isPending || create.isPending}>{validation?.valid ? "确认创建并激活" : "验证目录"}</button>{validation && <div className={`notice ${validation.valid ? "success" : "error"}`}><strong>{validation.valid ? "目录可以使用" : "目录不可使用"}</strong><p>{validation.valid ? `将创建：${validation.workspace_path}` : validation.error}</p></div>}{pickDirectory.error && <p className="form-error">{pickDirectory.error.message}</p>}{create.data && <div className="notice success"><strong>工作区已创建</strong><p>{create.data.workspace_path}</p>{create.data.restart_required && <p>重启 CareerConsole 后切换到新工作区。</p>}</div>}</form></details></section>}{configuration.data && <ConfigurationForm status={configuration.data} />}</>}
    {section === "ai" && configuration.data && <ProviderAgentConfiguration status={configuration.data} />}
    {section === "sources" && <DataSourceSettings />}
    {section === "notifications" && configuration.data && <ChannelSettings status={configuration.data} />}
    {section === "automation" && configuration.data && <SchedulerSettings status={configuration.data} />}
    {section === "data" && <WorkspaceTransfer />}
    {section === "advanced" && <><section className="panel"><div className="panel-heading"><div><p className="eyebrow">DIAGNOSTICS</p><h2>运行与诊断</h2></div><span>高级功能</span></div><p>运行状态、Agent 记录和后台任务用于排障，普通使用无需关注。</p><div className="form-actions"><a className="download-button secondary" href="/status">运行状态</a><a className="download-button secondary" href="/agent-runs">Agent 记录</a><a className="download-button secondary" href="/jobs">后台任务</a><button className="secondary" type="button" disabled={reopen.isPending} onClick={() => reopen.mutate()}>重新进入初始化向导</button></div>{reopen.error && <p className="form-error">{reopen.error.message}</p>}</section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">CHANGE AUDIT</p><h2>配置变更历史</h2></div><span>{changes.data?.total ?? 0} 条</span></div><div>{changes.data?.items.map(item => <article className="change-row" key={item.id}><strong>revision {item.previous_revision} → {item.new_revision}</strong><span>{item.reason} · {item.activation_effect}</span><small>{item.changed_paths.join("、")} · {new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</small></article>)}</div></section></>}
  </>;
}
