import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import {
  configureQQChannel,
  ApiError,
  configureOpenCli,
  configureScheduler,
  cancelPendingWorkspace,
  createWorkspaceBackup,
  createWorkspace,
  deleteAllCareerData,
  deleteConnectorData,
  deleteQQChannel,
  deleteProvider,
  exportWorkspaceData,
  exportPortableWorkspace,
  garbageCollectWorkspace,
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
import { ConfigurationTestButton } from "./ConfigurationTest";
import { DataSourcesPage } from "./ConnectorPages";
import { MessageCenterPage } from "./MailPages";
import { formatChinaTime } from "./time";

function applyAppearance(configuration: CareerConsoleConfiguration) {
  document.documentElement.dataset.density = configuration.appearance.density;
  document.documentElement.classList.toggle(
    "reduce-motion", configuration.appearance.reduce_motion,
  );
}

function ConfigurationForm({ status, advanced = false }: { status: ConfigurationStatus; advanced?: boolean }) {
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
        locale: (data.get("locale") ?? current.general.locale) as "zh-CN" | "en-US",
        timezone: String(data.get("timezone") ?? current.general.timezone),
        date_format: (data.get("date_format") ?? current.general.date_format) as "yyyy-MM-dd" | "yyyy/MM/dd",
        open_browser_on_start: advanced ? current.general.open_browser_on_start : data.has("open_browser_on_start"),
      },
      appearance: {
        density: (data.get("density") ?? current.appearance.density) as "comfortable" | "compact",
        reduce_motion: advanced ? current.appearance.reduce_motion : data.has("reduce_motion"),
      },
      runtime: {
        log_level: (data.get("log_level") ?? current.runtime.log_level) as CareerConsoleConfiguration["runtime"]["log_level"],
        log_retention_days: Number(data.get("log_retention_days") ?? current.runtime.log_retention_days),
        agent_trace_retention_days: Number(data.get("agent_trace_retention_days") ?? current.runtime.agent_trace_retention_days),
        job_lease_seconds: Number(data.get("job_lease_seconds") ?? current.runtime.job_lease_seconds),
        max_document_mb: Number(data.get("max_document_mb") ?? current.runtime.max_document_mb),
      },
      privacy: {
        diagnostics_metadata_enabled: advanced ? current.privacy.diagnostics_metadata_enabled : data.has("diagnostics_metadata_enabled"),
        redact_sensitive_logs: current.privacy.redact_sensitive_logs,
        local_only_network_binding: current.privacy.local_only_network_binding,
      },
      providers: current.providers,
      agents: current.agents,
      connectors: current.connectors,
      channels: current.channels,
      scheduler: current.scheduler,
    };
    save.mutate({ configuration, reason: advanced ? "用户更新高级运行参数" : "用户更新常规设置" });
  }
  const item = status.configuration;
  const today = new Date();
  const dateDash = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const dateSlash = dateDash.replaceAll("-", "/");
  return <form onSubmit={submit} className="settings-stack">
    {!advanced && <><section className="panel"><div className="panel-heading"><div><p className="eyebrow">语言与时间</p><h2>常规</h2></div><span>保存后立即生效</span></div><div className="form-grid">
      <label>界面语言<select name="locale" defaultValue={item.general.locale}><option value="zh-CN">简体中文</option><option value="en-US">English</option></select></label>
      <label>业务时区<input name="timezone" defaultValue={item.general.timezone} required /></label>
      <label>日期格式<select name="date_format" defaultValue={item.general.date_format}><option value="yyyy-MM-dd">{dateDash}</option><option value="yyyy/MM/dd">{dateSlash}</option></select></label>
      <label className="check-row"><input type="checkbox" name="open_browser_on_start" defaultChecked={item.general.open_browser_on_start} />启动后自动打开浏览器</label>
    </div></section>
    <section className="panel"><div><p className="eyebrow">界面偏好</p><h2>外观</h2></div><div className="form-grid">
      <label>界面密度<select name="density" defaultValue={item.appearance.density}><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label>
      <label className="check-row"><input type="checkbox" name="reduce_motion" defaultChecked={item.appearance.reduce_motion} />减少界面动效</label>
    </div></section>
    <section className="panel"><div><p className="eyebrow">本地数据保护</p><h2>隐私与安全</h2></div><div className="security-grid"><label className="check-row"><input type="checkbox" name="diagnostics_metadata_enabled" defaultChecked={item.privacy.diagnostics_metadata_enabled} />保存不含业务正文的诊断元数据</label><p>敏感日志脱敏：强制开启</p><p>仅绑定本机网络：强制开启</p><p>配置文件不会保存 API Key、Token 或邮箱授权码。</p></div></section></>}
    {advanced && <section className="panel advanced-settings-card"><div><p className="eyebrow">高级运行参数</p><h2>运行维护</h2></div><p className="section-note">这些参数用于日志、审计和后台任务故障处理。修改后可能需要重启服务。</p><div className="form-grid">
      <label>日志级别<select name="log_level" defaultValue={item.runtime.log_level}>{["DEBUG", "INFO", "WARNING", "ERROR"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>日志保留天数<input name="log_retention_days" type="number" min="1" max="365" defaultValue={item.runtime.log_retention_days} /></label>
      <label>智能功能审计保留天数<input name="agent_trace_retention_days" type="number" min="1" max="3650" defaultValue={item.runtime.agent_trace_retention_days} /></label>
      <label>后台任务租约（秒）<input name="job_lease_seconds" type="number" min="10" max="3600" defaultValue={item.runtime.job_lease_seconds} /></label>
      <label>单个文档上限（MB）<input name="max_document_mb" type="number" min="1" max="50" defaultValue={item.runtime.max_document_mb} /></label>
    </div><ConfigurationTestButton capability="runtime" label="测试运行环境" /></section>}
    <section className="panel save-bar"><button disabled={save.isPending}>{save.isPending ? "保存中…" : advanced ? "保存高级参数" : "保存常规设置"}</button>{saved && <div className={`notice ${saved.activation_effect === "hot_reload" ? "success" : "warning"}`}><strong>{saved.activation_effect === "hot_reload" ? "设置已保存并生效" : "设置已保存，重启后生效"}</strong><p>{saved.changed_paths?.length ? `已更新 ${saved.changed_paths.length} 项设置。` : "配置内容没有变化。"}</p></div>}{save.error && <p className="form-error">{save.error.message}</p>}</section>
  </form>;
}

const TASK_LABELS: Record<AgentTaskName, string> = {
  fact_extraction: "事实提取", mail_intelligence: "邮件分析",
  profile_insight: "档案洞察", job_fit: "岗位匹配",
  resume_direction: "简历方向", resume_drafting: "材料撰写",
  material_review: "材料复核",
};

export function ProviderAgentConfiguration({ status }: { status: ConfigurationStatus }) {
  const client = useQueryClient();
  const [providerNotice, setProviderNotice] = useState("");
  const [agentNotice, setAgentNotice] = useState("");
  const catalog = useQuery({ queryKey: ["provider-catalog"], queryFn: getProviderCatalog });
  const providers = useQuery({ queryKey: ["providers"], queryFn: getProviders });
  const tests = useQuery({ queryKey: ["provider-tests"], queryFn: getProviderTests });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["configuration"] }),
      client.invalidateQueries({ queryKey: ["providers"] }),
      client.invalidateQueries({ queryKey: ["provider-tests"] }),
      client.invalidateQueries({ queryKey: ["configuration-changes"] }),
      client.invalidateQueries({ queryKey: ["onboarding"] }),
    ]);
  };
  const currentRevision = () =>
    client.getQueryData<ConfigurationStatus>(["configuration"])?.revision ?? status.revision;
  const saveProvider = useMutation({
    mutationFn: async ({ id, form, testAfter }: { id: string; form: FormData; testAfter: boolean }) => {
      const providerType = String(form.get("provider_type")) as Parameters<typeof upsertProvider>[1]["provider_type"];
      const defaultBase = catalog.data?.items.find(item => item.type === providerType)?.default_api_base ?? null;
      const saved = await upsertProvider(id, {
        expected_revision: currentRevision(),
        provider_type: providerType,
        display_name: String(form.get("display_name")), enabled: form.has("enabled"),
        api_base: String(form.get("api_base") || "") || defaultBase,
        default_model: String(form.get("default_model")),
        models: String(form.get("models") || "").split(/[\n,]/).map(value => value.trim()).filter(Boolean),
        ...(form.get("api_key") ? { api_key: String(form.get("api_key")) } : {}),
      });
      if (testAfter) await testProvider(saved.provider.id);
      return { ...saved, testAfter };
    },
    onMutate: () => setProviderNotice(""),
    onSuccess: async data => {
      setProviderNotice(`AI 服务“${data.provider.display_name}”已保存${data.testAfter ? "并完成连接测试" : ""}。下一步可应用推荐任务配置。`);
      await refresh();
    },
  });
  const removeProvider = useMutation({
    mutationFn: (id: string) => deleteProvider(id, currentRevision()),
    onMutate: () => setProviderNotice(""),
    onSuccess: async () => {
      setProviderNotice("AI 服务已删除。");
      await refresh();
    },
  });
  const runTest = useMutation({
    mutationFn: (id: string) => testProvider(id), onSuccess: refresh,
  });
  const saveAgents = useMutation({
    mutationFn: (agents: AgentConfiguration) => updateAgentConfiguration(currentRevision(), agents),
    onMutate: () => setAgentNotice(""),
    onSuccess: () => {
      setAgentNotice("高级模型分配已保存。重启服务后应用新的 AI 运行配置。");
      void refresh();
    },
  });
  function createProviderId() {
    const suffix = globalThis.crypto?.randomUUID?.().replaceAll("-", "").slice(0, 12)
      ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    return `provider-${suffix}`;
  }
  function providerSubmit(event: FormEvent<HTMLFormElement>, existingId?: string) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    saveProvider.mutate({ id: existingId ?? createProviderId(), form, testAfter: submitter?.value === "save-test" });
  }
  function agentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const tasks = Object.fromEntries((Object.keys(TASK_LABELS) as AgentTaskName[]).map(name => {
      const current = status.configuration.agents.tasks[name];
      return [name, { ...current, enabled: form.has(`${name}.enabled`),
        provider_id: String(form.get(`${name}.provider_id`) || "") || null,
        model: String(form.get(`${name}.model`) || "") || null }];
    })) as AgentConfiguration["tasks"];
    const missing = (Object.keys(TASK_LABELS) as AgentTaskName[])
      .filter(name => tasks[name].enabled && !tasks[name].provider_id)
      .map(name => TASK_LABELS[name]);
    if (missing.length) {
      setAgentNotice(`无法保存：请先为${missing.join("、")}选择 AI 服务。`);
      return;
    }
    saveAgents.mutate({ tasks });
  }
  const providerItems = providers.data?.items ?? [];
  return <div className="settings-stack provider-settings">
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">智能功能</p><h2>AI 服务</h2></div><span>{providerItems.length} 个</span></div>
      <p className="section-note">通常只需要选择服务商、填写模型名称和 API Key。密钥只保存在操作系统凭据库中。</p>
      {providerItems.map(item => <details className="provider-editor" key={item.id}><summary>{item.display_name} · {item.default_model} · {item.has_secret ? "凭据已配置" : "未配置凭据"}</summary>
        <form className="form-grid" onSubmit={event => providerSubmit(event, item.id)}>
          <label>服务商<select name="provider_type" defaultValue={item.provider_type}>{catalog.data?.items.map(option => <option value={option.type} key={option.type}>{option.label}</option>)}</select></label>
          <label>在界面中的名称<input name="display_name" defaultValue={item.display_name} required /></label>
          <label>默认模型<input name="default_model" defaultValue={item.default_model} required /></label>
          <label>更新 API Key<input name="api_key" type="password" autoComplete="new-password" placeholder={item.has_secret ? "已安全保存；留空保持不变" : "输入 API Key"} /></label>
          <label className="check-row"><input name="enabled" type="checkbox" defaultChecked={item.enabled} />启用此 AI 服务</label>
          <details className="wide inline-advanced"><summary>高级连接设置</summary><div className="form-grid">
            <label className="wide">服务连接地址<input name="api_base" defaultValue={item.api_base ?? ""} placeholder="留空使用服务商默认地址" /></label>
            <label className="wide">可选模型（逗号或换行分隔）<textarea name="models" defaultValue={item.models.join("\n")} /></label>
          </div></details>
          <div className="form-actions"><button value="save-test" disabled={saveProvider.isPending}>保存并测试</button><button value="save" className="secondary" disabled={saveProvider.isPending}>仅保存</button><button type="button" className="secondary" onClick={() => runTest.mutate(item.id)} disabled={runTest.isPending}>重新测试</button><button type="button" className="secondary" onClick={() => removeProvider.mutate(item.id)} disabled={removeProvider.isPending}>删除</button></div>
        </form></details>)}
      <details className="provider-editor"><summary>新增 AI 服务</summary><form className="form-grid" onSubmit={providerSubmit}>
        <label>服务商<select name="provider_type" defaultValue="openai">{catalog.data?.items.map(option => <option value={option.type} key={option.type}>{option.label}</option>)}</select></label>
        <label>在界面中的名称<input name="display_name" required placeholder="例如：主要 AI 服务" /></label>
        <label>默认模型<input name="default_model" required placeholder="例如：gpt-5-mini" /></label>
        <label>API Key<input name="api_key" type="password" autoComplete="new-password" /></label>
        <label className="check-row"><input name="enabled" type="checkbox" defaultChecked />启用此 AI 服务</label>
        <details className="wide inline-advanced"><summary>高级连接设置</summary><div className="form-grid">
          <label className="wide">服务连接地址<input name="api_base" placeholder="留空自动使用服务商默认地址" /></label>
          <label className="wide">可选模型<textarea name="models" /></label>
        </div></details>
        <div className="form-actions"><button value="save-test" disabled={saveProvider.isPending}>{saveProvider.isPending ? "正在保存并测试…" : "保存并测试"}</button><button value="save" className="secondary" disabled={saveProvider.isPending}>仅保存</button></div>
      </form></details>
      {(saveProvider.error || removeProvider.error || runTest.error) && (() => { const error = saveProvider.error ?? removeProvider.error ?? runTest.error; return <p className="form-error">{error?.message}{error instanceof ApiError && error.correlationId ? `（关联 ID：${error.correlationId}）` : ""}</p>; })()}
      {providerNotice && <div className="notice success"><strong>{providerNotice}</strong></div>}
      {runTest.data && <div className={`notice ${runTest.data.status === "passed" ? "success" : "error"}`}><strong>{runTest.data.status === "passed" ? "连接测试通过" : "连接测试失败"}</strong><p>{runTest.data.model} · {runTest.data.duration_ms}ms{runTest.data.error_code ? ` · ${runTest.data.error_code}` : ""}</p></div>}
    </section>
    <details className="panel settings-disclosure"><summary><span><small>高级设置</small><strong>按任务选择不同模型</strong></span><em>普通使用无需调整</em></summary><p className="section-note">默认让所有智能功能使用同一个 AI 服务。只有需要控制成本或使用不同模型复核时，才逐项调整。</p>
      <form onSubmit={agentSubmit}><div className="agent-mapping-list">{(Object.keys(TASK_LABELS) as AgentTaskName[]).map(name => {
        const task = status.configuration.agents.tasks[name];
        const providerRevision = providerItems.map(provider => provider.id).join(",");
        return <div className="agent-mapping-row" key={`${name}:${providerRevision}`}><label className="check-row"><input type="checkbox" name={`${name}.enabled`} defaultChecked={task.enabled} />{TASK_LABELS[name]}</label><label>AI 服务<select name={`${name}.provider_id`} defaultValue={task.provider_id ?? ""}><option value="">未配置</option>{providerItems.map(provider => <option value={provider.id} key={provider.id}>{provider.display_name}</option>)}</select></label><label>指定模型<input name={`${name}.model`} defaultValue={task.model ?? ""} placeholder="留空使用默认模型" /></label></div>;
      })}</div><div className="form-actions"><button type="button" className="secondary" disabled={!providerItems.length} onClick={event => {
        const form = event.currentTarget.form;
        const providerId = providerItems.find(item => item.enabled)?.id ?? providerItems[0]?.id ?? "";
        if (!form || !providerId) return;
        (Object.keys(TASK_LABELS) as AgentTaskName[]).forEach(name => {
          const enabled = form.elements.namedItem(`${name}.enabled`) as HTMLInputElement | null;
          const provider = form.elements.namedItem(`${name}.provider_id`) as HTMLSelectElement | null;
          if (enabled) enabled.checked = true;
          if (provider) provider.value = providerId;
        });
        setAgentNotice("已让所有智能功能使用同一个 AI 服务，请保存并测试。");
      }}>全部使用同一个 AI 服务</button><button disabled={saveAgents.isPending}>{saveAgents.isPending ? "正在保存…" : "保存高级分配"}</button><span>保存后需重新加载智能功能</span></div>{agentNotice && <div className={`notice ${agentNotice.startsWith("无法") ? "error" : "success"}`}><strong>{agentNotice}</strong></div>}{saveAgents.error && <p className="form-error">{saveAgents.error.message}{saveAgents.error instanceof ApiError && saveAgents.error.correlationId ? `（关联 ID：${saveAgents.error.correlationId}）` : ""}</p>}</form>
      <ConfigurationTestButton capability="agent_routing" label="测试模型分配" />
    </details>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">连接记录</p><h2>最近测试</h2></div><span>{tests.data?.total ?? 0} 条</span></div>{tests.data?.items.map(item => {
      const provider = providerItems.find(candidate => candidate.id === item.provider_id);
      return <article className="change-row" key={item.id}><strong>{provider?.display_name ?? "已删除的服务商"} · {item.status === "passed" ? "通过" : "失败"}</strong><span>{item.model} · {item.duration_ms}ms{item.error_code ? ` · ${item.error_code}` : ""}</span><small>{formatChinaTime(item.created_at)}（北京时间）</small></article>;
    })}</section>
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
  return <div className="settings-stack provider-settings"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">高级通知渠道</p><h2>QQ 通知</h2></div><span>{qq.data?.has_secret ? "凭据已配置" : "未配置凭据"}</span></div>
    <p className="section-note">QQ 仅用于发送任务提醒、申请进度、每日摘要和系统告警。密钥保存后不会回显。</p>
    <form className="form-grid" onSubmit={submit}><label className="check-row"><input type="checkbox" name="enabled" defaultChecked={config.enabled} />启用 QQ 通知</label><label>App ID<input name="app_id" defaultValue={config.app_id} /></label>
      <label>App Secret<input name="secret" type="password" autoComplete="new-password" placeholder={qq.data?.has_secret ? "已安全保存；留空保持不变" : "输入 App Secret"} /></label>
      <label>消息格式<select name="message_format" defaultValue={config.message_format}><option value="plain">纯文本</option><option value="markdown">Markdown</option></select></label>
      <label className="wide">通知目标<textarea name="notification_targets" defaultValue={config.notification_targets.join("\n")} placeholder="每行一个接收目标；可填写个人或群通知目标" /></label>
      <details className="wide"><summary>查看目标填写格式</summary><p><code>c2c:用户OpenID</code> 用于个人通知，<code>group:群OpenID</code> 用于群通知。</p></details>
      <fieldset className="wide channel-events"><legend>事件订阅</legend>{[["task_reminder", "任务提醒"], ["application_update", "申请进度"], ["daily_digest", "每日摘要"], ["system_alert", "系统告警"]].map(([name, label]) => <label className="check-row" key={name}><input type="checkbox" name={`event.${name}`} defaultChecked={config.event_subscriptions.includes(name)} />{label}</label>)}</fieldset>
      <label className="check-row"><input type="checkbox" name="quiet_enabled" defaultChecked={config.quiet_hours.enabled} />启用免打扰</label><label>免打扰开始<input name="quiet_start" type="time" defaultValue={config.quiet_hours.start} /></label><label>免打扰结束<input name="quiet_end" type="time" defaultValue={config.quiet_hours.end} /></label>
      <div className="form-actions wide"><button disabled={save.isPending}>保存 QQ 配置</button><button className="secondary" type="button" onClick={() => test.mutate()} disabled={test.isPending || !config.enabled || !qq.data?.has_secret || !config.notification_targets.length}>发送测试通知</button>{(qq.data?.has_secret || config.app_id) && <button className="secondary" type="button" onClick={() => remove.mutate()} disabled={remove.isPending}>删除配置</button>}</div>
      {(!config.enabled || !qq.data?.has_secret || !config.notification_targets.length) && <p className="disabled-reason wide">发送测试通知前，需要启用 QQ 通知、保存 App ID 与 App Secret，并至少配置一个通知目标。</p>}
    </form>{(save.error || test.error || remove.error) && <p className="form-error">{(save.error ?? test.error ?? remove.error)?.message}</p>}{test.data && <div className={`notice ${test.data.status === "passed" ? "success" : "error"}`}><strong>{test.data.status === "passed" ? "测试通知已发送" : "测试发送失败"}</strong><p>{test.data.target_masked} · {test.data.duration_ms}ms{test.data.error_code ? ` · ${test.data.error_code}` : ""}</p></div>}
  </section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">发送审计</p><h2>通知发送记录</h2></div><span>{deliveries.data?.total ?? 0} 条</span></div>{(deliveries.data?.items ?? []).map(item => <article className="change-row" key={item.id}><strong>QQ · {item.status === "passed" ? "成功" : "失败"}</strong><span>{item.event_type} · {item.target_masked} · {item.duration_ms}ms</span><small>{item.error_code ?? `${formatChinaTime(item.created_at)}（北京时间）`}</small></article>)}</section></div>;
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
  const triggerLabels: Record<string, string> = {
    manual: "手动运行",
    interval: "定时检查",
    startup: "启动检查",
    scheduled: "计划运行",
  };
  const statusLabels: Record<string, string> = {
    completed: "已完成",
    succeeded: "已完成",
    partial: "部分完成",
    failed: "失败",
    running: "运行中",
    skipped: "已跳过",
  };
  const meaningfulRuns = (runs.data?.items ?? []).filter(run => {
    const counters = Object.values(run.counters);
    return run.status === "failed" || run.status === "partial" || run.error_codes.length > 0
      || counters.some(value => value > 0);
  });
  return <div className="settings-stack provider-settings"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">北京时间运行</p><h2>自动任务</h2></div><span>Asia/Shanghai</span></div><p className="section-note">统一控制任务提醒、邮件轮询、牛客当天同步、档案维护与通知分发。失败会隔离记录，不会阻断其他任务。</p><form className="form-grid" onSubmit={event => { event.preventDefault(); save.mutate(new FormData(event.currentTarget)); }}>
    <label className="check-row"><input name="enabled" type="checkbox" defaultChecked={item.enabled} />启用自动任务服务</label>
    <label className="check-row"><input name="reminders_enabled" type="checkbox" defaultChecked={item.reminders_enabled} />发送任务与日程提醒</label><label className="check-row"><input name="connector_jobs_enabled" type="checkbox" defaultChecked={item.connector_jobs_enabled} />同步招聘信息与邮箱</label><label className="check-row"><input name="profile_maintenance_enabled" type="checkbox" defaultChecked={item.profile_maintenance_enabled} />每天整理职业档案</label><label>档案整理时间<input name="profile_maintenance_time" type="time" defaultValue={item.profile_maintenance_time} /></label><label className="check-row"><input name="channel_dispatch_enabled" type="checkbox" defaultChecked={item.channel_dispatch_enabled} />向已配置的通知渠道发送提醒</label>
    <details className="wide inline-advanced"><summary>高级运行频率</summary><label>后台检查周期（秒）<input name="poll_seconds" type="number" min="10" max="3600" defaultValue={item.poll_seconds} /></label></details>
    <div className="form-actions"><button disabled={save.isPending}>{save.isPending ? "正在保存…" : "保存自动任务设置"}</button></div>
  </form>{save.error && <p className="form-error">{save.error.message}</p>}<ConfigurationTestButton capability="scheduler" label="测试自动任务配置" /></section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">有效运行</p><h2>最近自动任务</h2></div><span>{meaningfulRuns.length} 条</span></div>{meaningfulRuns.length ? meaningfulRuns.map(run => <article className="change-row" key={run.id}><strong>{triggerLabels[run.trigger_type] ?? run.trigger_type} · {statusLabels[run.status] ?? run.status}</strong><span>提醒 {run.counters.reminders_triggered ?? 0} · 数据来源 {run.counters.connector_runs_processed ?? 0} · 通知 {run.counters.channel_sent ?? 0}</span><small>{run.error_codes.join("、") || `${formatChinaTime(run.started_at)}（北京时间）`}</small></article>) : <div className="quiet-state"><strong>自动任务服务运行正常</strong><p>最近没有产生提醒、数据同步、通知或错误。空检查记录已隐藏。</p></div>}<details className="audit-details"><summary>关于空检查记录</summary><p>后台仍会按设置周期检查任务；没有产生业务结果的心跳不会显示在这里。</p></details></section></div>;
}

export function DataSourceSettings({ embedded = false }: { embedded?: boolean }) {
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const opencli = useQuery({ queryKey: ["opencli-configuration"], queryFn: getOpenCliConfiguration });
  const save = useMutation({ mutationFn: (value: string) => configureOpenCli(value || null), onMutate: () => setNotice(""), onSuccess: async () => {
    setNotice("OpenCLI 路径已保存。");
    await Promise.all([client.invalidateQueries({ queryKey: ["opencli-configuration"] }), client.invalidateQueries({ queryKey: ["configuration"] }), client.invalidateQueries({ queryKey: ["onboarding"] })]);
  } });
  return <section className="panel provider-settings settings-anchor-card" id="source-opencli" tabIndex={-1}><div className="panel-heading"><div><p className="eyebrow">招聘来源依赖</p><h2>OpenCLI 应用</h2></div><span>{opencli.data?.installed ? "OpenCLI 可用" : "OpenCLI 未检测到"}</span></div><p className="section-note">OpenCLI 是牛客和 BOSS 数据来源所需的外部应用。通常安装后会自动识别，无需手工填写路径。</p><details className="inline-advanced" open={!opencli.data?.installed}><summary>高级：指定 OpenCLI 可执行文件</summary><form className="form-grid" onSubmit={event => { event.preventDefault(); save.mutate(String(new FormData(event.currentTarget).get("executable") || "")); }}><label className="wide">可执行文件路径<input name="executable" defaultValue={opencli.data?.executable ?? ""} placeholder="留空时从 PATH 自动查找" /></label><div className="form-actions wide"><button disabled={save.isPending}>{save.isPending ? "正在保存…" : "保存路径"}</button></div></form>{opencli.data?.resolved_executable && <p className="section-note">当前解析路径：{opencli.data.resolved_executable}</p>}</details>{notice && <div className="notice success"><strong>{notice}</strong></div>}{save.error && <p className="form-error">{save.error.message}</p>}<ConfigurationTestButton capability="opencli" label="测试 OpenCLI" /></section>;
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
  return <section className="panel provider-settings"><div className="panel-heading"><div><p className="eyebrow">设备迁移</p><h2>导入与导出</h2></div><span>完整性校验</span></div>
    <p className="section-note">导出包含一致性数据库快照、配置、材料 Blob 和本地集成文件，不包含日志、旧备份或运行时文件。普通导出永不包含凭据。</p>
    <div className="workspace-grid">
      <form className="form-grid" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); createExport.mutate({ include: includeSecrets, passphrase: String(form.get("export_passphrase") || "") }); }}>
        <h3 className="wide">导出当前工作区</h3><label className="check-row wide"><input type="checkbox" name="include_secrets" checked={includeSecrets} onChange={event => setIncludeSecrets(event.currentTarget.checked)} />使用密码加密并包含已配置凭据</label>{includeSecrets && <label className="wide">导出密码（至少 12 个字符）<input type="password" name="export_passphrase" minLength={12} required autoComplete="new-password" /></label>}<div className="form-actions wide"><button disabled={createExport.isPending}>{createExport.isPending ? "正在生成…" : "生成迁移包"}</button></div>
        {createExport.data && <div className="notice success wide"><strong>迁移包已完成完整性校验</strong><p>{createExport.data.filename} · {(createExport.data.size_bytes / 1024 / 1024).toFixed(2)} MiB · {createExport.data.file_count} 个文件</p><a className="download-button" href={createExport.data.download_url}>下载迁移包</a></div>}{createExport.error && <p className="form-error wide">{createExport.error.message}</p>}
      </form>
      <form className="form-grid" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const file = form.get("workspace_archive"); if (file instanceof File) runImport.mutate({ file, parent: String(form.get("import_parent")), passphrase: String(form.get("import_passphrase") || "") }); }}>
        <h3 className="wide">恢复到新工作区</h3><label className="file-picker wide"><input type="file" name="workspace_archive" aria-label="选择迁移包" accept=".ccworkspace,application/zip" required /><span>选择迁移包</span></label><label className="wide">新工作区父目录<input name="import_parent" required placeholder="例如 D:\CareerRestore" /></label><label className="wide">迁移包密码（普通包留空）<input type="password" name="import_passphrase" autoComplete="current-password" /></label><p className="section-note wide">导入会创建一个新工作区，不会覆盖当前工作区。校验通过后才会恢复文件。</p><div className="form-actions wide"><button disabled={runImport.isPending}>{runImport.isPending ? "正在校验并恢复…" : "校验并导入"}</button></div>
        {runImport.data && <div className="notice success wide"><strong>新工作区已恢复并激活</strong><p>{runImport.data.workspace_path} · 凭据 {runImport.data.secrets_restored} 项</p>{runImport.data.restart_required && <p>请重启 CareerConsole 切换到恢复后的工作区。</p>}</div>}{runImport.error && <p className="form-error wide">{runImport.error.message}</p>}
      </form>
    </div><div className="security-grid"><p>防止压缩包中的路径越界</p><p>限制异常文件数量、大小和压缩比</p><p>导入前检查数据库完整性和版本</p><p>凭据使用强加密保护</p></div>
    <details><summary>查看安全校验的工程细节</summary><p>包括 Zip Slip/链接穿越防护、SQLite quick_check、PBKDF2 密钥派生和 AES-256-GCM 加密。</p></details>
  </section>;
}

function DataGovernance() {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const backup = useMutation({
    mutationFn: createWorkspaceBackup,
    onMutate: () => setMessage(""),
    onSuccess: item => setMessage(`完整备份已创建：${item.path}`),
  });
  const exportData = useMutation({
    mutationFn: exportWorkspaceData,
    onMutate: () => setMessage(""),
    onSuccess: item => setMessage(`结构化数据导出已创建：${item.path}`),
  });
  const garbageCollect = useMutation({
    mutationFn: garbageCollectWorkspace,
    onMutate: () => setMessage(""),
    onSuccess: item => setMessage(`存储清理完成：移除 ${item.removed_files} 个未引用文件。`),
  });
  const deleteConnector = useMutation({
    mutationFn: ({ type, confirmation }: { type: string; confirmation: string }) =>
      deleteConnectorData(type, confirmation),
    onMutate: () => setMessage(""),
    onSuccess: async item => {
      setMessage(`已删除 ${item.deleted_connectors} 项数据来源配置及其专属数据。`);
      await client.invalidateQueries();
    },
  });
  const deleteAll = useMutation({
    mutationFn: deleteAllCareerData,
    onMutate: () => setMessage(""),
    onSuccess: async item => {
      setMessage(`个人业务数据已删除；删除前备份位于：${item.backup_path}`);
      await client.invalidateQueries();
    },
  });
  const error = backup.error ?? exportData.error ?? garbageCollect.error
    ?? deleteConnector.error ?? deleteAll.error;
  return <section className="panel governance-panel"><div className="panel-heading"><div><p className="eyebrow">数据维护</p><h2>备份、清理与删除</h2></div><span>高风险操作需二次确认</span></div>
    <p className="section-note">备份和结构化导出不会读取操作系统凭据库中的 API Key、Token 或邮箱授权码。</p>
    <div className="form-actions"><button type="button" onClick={() => backup.mutate()} disabled={backup.isPending}>创建完整备份</button><button type="button" className="secondary" onClick={() => exportData.mutate()} disabled={exportData.isPending}>导出结构化数据</button><button type="button" className="secondary" onClick={() => garbageCollect.mutate()} disabled={garbageCollect.isPending}>清理未引用文件</button></div>
    {message && <div className="notice success"><strong>{message}</strong></div>}
    {error && <div className="notice error"><strong>操作未完成</strong><p>{error.message}</p></div>}
    <details className="danger-zone"><summary>删除单个数据来源的配置与数据</summary><form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); deleteConnector.mutate({ type: String(data.get("connector_type")), confirmation: String(data.get("confirmation")) }); }}><label>数据来源<select name="connector_type"><option value="opencli_nowcoder">牛客校招日程</option><option value="opencli_boss">BOSS 招聘</option><option value="imap_readonly">只读邮箱</option></select></label><label>按所选类型输入确认文本<input name="confirmation" required placeholder="例如 DELETE imap_readonly" /></label><button className="danger" disabled={deleteConnector.isPending}>删除该数据来源</button></form></details>
    <details className="danger-zone"><summary>删除全部个人业务数据</summary><form onSubmit={event => { event.preventDefault(); deleteAll.mutate(String(new FormData(event.currentTarget).get("confirmation"))); }}><label>输入 DELETE ALL CAREER DATA<input name="confirmation" required /></label><button className="danger" disabled={deleteAll.isPending}>先备份再删除</button></form></details>
    <ConfigurationTestButton capability="workspace" label="测试数据目录" />
  </section>;
}

export function SettingsPage() {
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [validation, setValidation] = useState<Awaited<ReturnType<typeof validateWorkspace>> | null>(null);
  const [workspaceParent, setWorkspaceParent] = useState("");
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: getWorkspaceStatus });
  const configuration = useQuery({ queryKey: ["configuration"], queryFn: getConfiguration });
  const changes = useQuery({ queryKey: ["configuration-changes"], queryFn: getConfigurationChanges });
  const validate = useMutation({ mutationFn: validateWorkspace, onSuccess: setValidation });
  const pickDirectory = useMutation({ mutationFn: () => pickWorkspaceDirectory(workspaceParent), onSuccess: result => { if (!result.cancelled && result.parent_directory) { setWorkspaceParent(result.parent_directory); setValidation(null); } } });
  const create = useMutation({ mutationFn: ({ parent, name }: { parent: string; name: string }) => createWorkspace(parent, name), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["workspace"] }); } });
  const cancelPending = useMutation({ mutationFn: cancelPendingWorkspace, onSuccess: async () => { await client.invalidateQueries({ queryKey: ["workspace"] }); } });
  const switchPending = useMutation({
    mutationFn: async () => {
      try {
        return await restartService();
      } catch (error) {
        if (error instanceof ApiError) throw error;
        return { restarting: true };
      }
    },
    onSuccess: () => window.setTimeout(() => window.location.reload(), 1_500),
  });
  const reopen = useMutation({ mutationFn: async () => {
    await reopenOnboarding();
    try { await restartService(); } catch { /* Process replacement may close the response. */ }
  }, onSuccess: () => window.setTimeout(() => window.location.reload(), 1_500) });
  function submitWorkspace(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); const parent = String(data.get("parent_directory") ?? ""); const name = String(data.get("name") ?? "CareerConsole"); if (validation?.valid && validation.parent_directory === parent) create.mutate({ parent, name }); else validate.mutate(parent); }
  const error = workspace.error ?? configuration.error ?? changes.error;
  const sections = [["general", "基础设置"], ["ai", "AI 服务"], ["sources", "数据来源"], ["notifications", "消息通知"], ["automation", "定时任务"], ["data", "备份与迁移"], ["advanced", "高级设置"]] as const;
  type SettingsSection = (typeof sections)[number][0];
  const requestedSection = searchParams.get("section");
  const section: SettingsSection = sections.some(([value]) => value === requestedSection)
    ? requestedSection as SettingsSection
    : "general";
  const selectSection = (value: SettingsSection) => {
    setSearchParams(value === "general" ? {} : { section: value });
  };
  return <><header className="page-header"><div><p className="eyebrow">按需要逐项设置</p><h1>设置</h1><p>日常使用通常只需配置工作区、AI 服务和招聘来源。运行参数与诊断功能集中在高级设置中。</p></div><span className={`health-pill ${configuration.data?.activation_status === "restart_required" ? "blocked" : "ok"}`}>{configuration.data?.activation_status === "restart_required" ? "有配置等待重启" : "配置已生效"}</span></header>
    {error && <p className="form-error">{error.message}</p>}
    <label className="settings-nav-select">设置分类<select value={section} onChange={event => selectSection(event.target.value as SettingsSection)}>{sections.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
    <nav className="settings-nav" aria-label="设置分类">{sections.map(([value, label]) => <button type="button" className={section === value ? "active" : "secondary"} onClick={() => selectSection(value)} key={value}>{label}</button>)}</nav>
    {section === "general" && <>{workspace.data && <section className="panel"><div className="panel-heading"><div><p className="eyebrow">本地数据位置</p><h2>当前工作区</h2></div><span>{workspace.data.manifest ? "正式工作区" : "临时启动工作区"}</span></div><dl className="path-list"><div><dt>根目录</dt><dd>{workspace.data.workspace_path}</dd></div></dl><details className="audit-details"><summary>查看工作区内部位置</summary><dl className="path-list"><div><dt>数据库</dt><dd>{workspace.data.paths.database}</dd></div><div><dt>配置</dt><dd>{workspace.data.paths.config}</dd></div><div><dt>备份</dt><dd>{workspace.data.paths.backups}</dd></div><div><dt>导出</dt><dd>{workspace.data.paths.exports}</dd></div></dl></details><ConfigurationTestButton capability="workspace" label="测试当前工作区" />{workspace.data.pending_workspace_path && <div className="notice warning"><strong>新工作区等待切换</strong><p>当前：{workspace.data.active_workspace_path ?? workspace.data.workspace_path}</p><p>待切换：{workspace.data.pending_workspace_path}</p><div className="form-actions"><button type="button" disabled={switchPending.isPending} onClick={() => switchPending.mutate()}>{switchPending.isPending ? "正在切换…" : "检查并重启到新工作区"}</button><button type="button" className="secondary" disabled={cancelPending.isPending} onClick={() => cancelPending.mutate()}>取消切换</button></div></div>}{(workspace.data.last_switch_error || switchPending.error) && <div className="notice error"><strong>工作区没有切换</strong><p>{workspace.data.last_switch_error || switchPending.error?.message}</p><p>当前工作区仍保持可用。</p></div>}<details><summary>创建或切换工作区</summary><form className="form-grid workspace-switch" onSubmit={submitWorkspace}><label>父目录<div className="path-picker-row"><input name="parent_directory" required placeholder="例如 D:\CareerWorkspace" value={workspaceParent} onChange={event => { setWorkspaceParent(event.target.value); setValidation(null); }} /><button className="secondary" type="button" disabled={pickDirectory.isPending} onClick={() => pickDirectory.mutate()}>{pickDirectory.isPending ? "正在选择…" : "选择文件夹"}</button></div></label><label>工作区名称<input name="name" defaultValue="CareerConsole" required /></label><button disabled={validate.isPending || create.isPending}>{validation?.valid ? "创建为待切换工作区" : "验证目录"}</button>{validation && <div className={`notice ${validation.valid ? "success" : "error"}`}><strong>{validation.valid ? "目录可以使用" : "目录不可使用"}</strong><p>{validation.valid ? `将创建：${validation.workspace_path}` : validation.error}</p></div>}{pickDirectory.error && <p className="form-error">{pickDirectory.error.message}</p>}{create.data && <div className="notice success"><strong>工作区已创建，尚未切换</strong><p>{create.data.workspace_path}</p><p>请使用上方“检查并重启到新工作区”。切换失败时当前工作区不会改变。</p></div>}</form></details></section>}{configuration.data && <ConfigurationForm status={configuration.data} />}</>}
    {section === "ai" && configuration.data && <ProviderAgentConfiguration status={configuration.data} />}
    {section === "sources" && <div className="settings-stack source-settings">
      <section className="panel source-settings-guide">
        <div className="panel-heading"><div><p className="eyebrow">统一配置入口</p><h2>招聘与邮箱配置</h2></div><span>全部在本页完成</span></div>
        <p className="section-note">按下面的顺序完成保存和测试。点击项目只会定位到本页对应表单，不会离开设置。</p>
        <nav className="source-settings-index" aria-label="招聘与邮箱配置目录">
          <a href="#source-opencli"><span>1</span><strong>OpenCLI</strong><small>外部应用路径与可用性</small></a>
          <a href="#source-nowcoder"><span>2</span><strong>牛客招聘</strong><small>每日新增招聘来源</small></a>
          <a href="#source-boss"><span>3</span><strong>BOSS</strong><small>手动定向搜索来源</small></a>
          <a href="#source-mail"><span>4</span><strong>招聘邮箱</strong><small>只读 IMAP 连接</small></a>
        </nav>
      </section>
      <DataSourceSettings embedded />
      <DataSourcesPage setupOnly />
      <MessageCenterPage setupOnly />
    </div>}
    {section === "notifications" && configuration.data && <ChannelSettings status={configuration.data} />}
    {section === "automation" && configuration.data && <SchedulerSettings status={configuration.data} />}
    {section === "data" && <><WorkspaceTransfer /><DataGovernance /></>}
    {section === "advanced" && <>{configuration.data && <ConfigurationForm status={configuration.data} advanced />}<section className="panel"><div className="panel-heading"><div><p className="eyebrow">出现问题时使用</p><h2>运行与诊断</h2></div><span>高级功能</span></div><p>服务状态、智能功能运行记录和后台任务主要用于排查问题，普通使用无需关注。</p><div className="form-actions"><a className="download-button secondary" href="/status">查看服务状态</a><a className="download-button secondary" href="/agent-runs">查看智能功能记录</a><a className="download-button secondary" href="/jobs">查看后台任务</a><button className="secondary" type="button" disabled={reopen.isPending} onClick={() => reopen.mutate()}>重新进入初始化向导</button></div>{reopen.error && <p className="form-error">{reopen.error.message}</p>}</section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">设置修改记录</p><h2>配置变更历史</h2></div><span>{changes.data?.total ?? 0} 条</span></div><div>{changes.data?.items.map(item => <article className="change-row" key={item.id}><strong>配置版本 {item.previous_revision} → {item.new_revision}</strong><span>{item.reason} · {item.activation_effect === "hot_reload" ? "已即时生效" : item.activation_effect === "restart_required" ? "重启后生效" : item.activation_effect}</span><small>{item.changed_paths.join("、")} · {formatChinaTime(item.created_at)}（北京时间）</small></article>)}</div></section></>}
  </>;
}
