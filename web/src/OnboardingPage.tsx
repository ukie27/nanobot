import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  ApiError,
  cancelPendingWorkspace,
  completeOnboarding,
  createWorkspace,
  getConfiguration,
  getOnboardingStatus,
  getWorkspaceStatus,
  pickWorkspaceDirectory,
  restartService,
  updateOnboardingStep,
  validateWorkspace,
  type WorkspaceValidation,
} from "./api";
import { ConfigurationTestButton } from "./ConfigurationTest";
import { DataSourcesPage } from "./ConnectorPages";
import { MessageCenterPage } from "./MailPages";
import { DocumentsPage } from "./ProfilePages";
import {
  ChannelSettings,
  DataSourceSettings,
  ProviderAgentConfiguration,
  SchedulerSettings,
} from "./SettingsPage";

const STEPS = [
  { key: "workspace", label: "工作区" },
  { key: "provider", label: "AI 能力" },
  { key: "profile", label: "职业档案" },
  { key: "recruitment_sources", label: "招聘来源" },
  { key: "mail", label: "招聘邮件" },
  { key: "channel", label: "通知渠道" },
  { key: "scheduler", label: "自动任务" },
  { key: "complete", label: "完成" },
] as const;
const CAPABILITY_LABELS: Record<string, string> = {
  workspace: "正式工作区",
  provider: "AI Provider",
  profile: "职业档案",
  mail: "只读邮箱",
  opencli: "OpenCLI / 牛客",
  channel: "通知渠道",
  scheduler: "自动任务",
};

async function requestRestart() {
  try {
    await restartService();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    // A successful process replacement can close the connection before a body is read.
  }
}

export function OnboardingPage() {
  const client = useQueryClient();
  const [step, setStep] = useState(0);
  const [validation, setValidation] = useState<WorkspaceValidation | null>(null);
  const [switching, setSwitching] = useState(false);
  const [restartError, setRestartError] = useState("");
  const [changingWorkspace, setChangingWorkspace] = useState(false);
  const [workspaceParent, setWorkspaceParent] = useState("");
  const onboarding = useQuery({ queryKey: ["onboarding"], queryFn: getOnboardingStatus, refetchInterval: switching ? 1_000 : false });
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: getWorkspaceStatus });
  const configuration = useQuery({ queryKey: ["configuration"], queryFn: getConfiguration, enabled: onboarding.data?.workspace_ready === true });
  const validate = useMutation({ mutationFn: validateWorkspace, onSuccess: setValidation });
  const pickDirectory = useMutation({
    mutationFn: () => pickWorkspaceDirectory(workspaceParent),
    onSuccess: result => {
      if (!result.cancelled && result.parent_directory) {
        setWorkspaceParent(result.parent_directory);
        setValidation(null);
      }
    },
  });
  const create = useMutation({
    mutationFn: ({ parent, name }: { parent: string; name: string }) => createWorkspace(parent, name),
    onSuccess: async () => {
      setRestartError("");
      try {
        setSwitching(true);
        await requestRestart();
        window.setTimeout(() => window.location.reload(), 1_500);
      } catch (error) {
        setSwitching(false);
        setRestartError(error instanceof Error ? error.message : "工作区切换失败。");
        await client.invalidateQueries({ queryKey: ["workspace"] });
      }
    },
  });
  const cancelPending = useMutation({
    mutationFn: cancelPendingWorkspace,
    onSuccess: async () => {
      setRestartError("");
      await client.invalidateQueries({ queryKey: ["workspace"] });
    },
  });
  const decideStep = useMutation({
    mutationFn: ({ key, state }: { key: string; state: "configured" | "skipped" }) =>
      updateOnboardingStep(key, state),
    onSuccess: async (_result, variables) => {
      await client.invalidateQueries({ queryKey: ["onboarding"] });
      if (variables.key !== "complete") {
        setStep(value => Math.min(STEPS.length - 1, value + 1));
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    },
  });
  const finish = useMutation({
    mutationFn: async () => {
      const latest = await getOnboardingStatus();
      const skipped = Object.entries(latest.step_states ?? {})
        .filter(([, state]) => state === "skipped")
        .map(([name]) => name);
      const completed = await completeOnboarding(skipped);
      if (completed.restart_required) await requestRestart();
      return completed;
    },
    onSuccess: () => {
      setSwitching(true);
      window.setTimeout(() => window.location.reload(), 500);
    },
  });

  function submitWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const parent = String(data.get("parent_directory") ?? "").trim();
    const name = String(data.get("name") ?? "CareerConsole").trim();
    if (validation?.valid && validation.parent_directory === parent) {
      create.mutate({ parent, name });
    } else {
      validate.mutate(parent);
    }
  }

  async function move(next: number) {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["onboarding"] }),
      client.invalidateQueries({ queryKey: ["configuration"] }),
    ]);
    setStep(Math.max(0, Math.min(STEPS.length - 1, next)));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function capabilityReady(key: typeof STEPS[number]["key"]) {
    const capabilities = onboarding.data?.capabilities;
    if (!capabilities) return false;
    if (key === "recruitment_sources") return capabilities.opencli;
    if (key === "complete") return true;
    return capabilities[key as keyof typeof capabilities] ?? false;
  }

  if (onboarding.isLoading || workspace.isLoading) {
    return <main className="onboarding-shell"><section className="onboarding-card"><p>正在检查本地初始化状态…</p></section></main>;
  }
  const error = onboarding.error ?? workspace.error ?? configuration.error;
  if (error) {
    return <main className="onboarding-shell"><section className="notice error"><strong>初始化控制面不可用</strong><p>{error.message}</p></section></main>;
  }

  const current = onboarding.data!;
  const stepStates = current.step_states ?? {};
  return <main className="onboarding-shell">
    <header className="onboarding-header">
      <div className="brand onboarding-brand"><div className="brand-mark">C</div><div><strong>CareerConsole</strong><span>首次初始化</span></div></div>
      <div><p className="eyebrow">首次设置</p><h1>配置你的求职工作台</h1><p>先确定数据保存位置，再逐项启用 AI、招聘来源、邮箱和通知。每一步都可以测试，也可以明确选择稍后配置。</p></div>
    </header>
    <ol className="setup-steps" aria-label="初始化步骤">
      {STEPS.map((item, index) => {
        const state = stepStates[item.key];
        const done = state === "configured" || state === "skipped" || index < step;
        return <li className={index === step ? "active" : done ? "done" : ""} key={item.key}>
          <span>{done ? "✓" : index + 1}</span>{item.label}
        </li>;
      })}
    </ol>

    {step === 0 && <section className="onboarding-card">
      <div className="panel-heading"><div><p className="eyebrow">必需设置</p><h2>选择正式工作区</h2></div><span className={`health-pill ${current.workspace_ready ? "ok" : "blocked"}`}>{current.workspace_ready ? "已就绪" : "必须完成"}</span></div>
      {current.workspace_ready && !changingWorkspace ? <><p>CareerConsole 的数据库、配置、材料、日志和导出文件都保存在这里。</p><dl className="path-list"><div><dt>工作区</dt><dd>{workspace.data?.workspace_path}</dd></div><div><dt>数据库</dt><dd>{workspace.data?.paths.database}</dd></div></dl><div className="form-actions"><button className="secondary" type="button" onClick={() => { setValidation(null); setChangingWorkspace(true); }}>更换工作区</button></div></> : <>
        <p>请选择一个具体父目录，CareerConsole 会在其中创建独立文件夹。机器级 Bootstrap 文件只保存这个路径，不保存业务数据或密钥。</p>
        <form className="form-grid" onSubmit={submitWorkspace}><label className="wide">父目录<div className="path-picker-row"><input name="parent_directory" required placeholder="例如 D:\CareerWorkspace" value={workspaceParent} onChange={event => { setWorkspaceParent(event.target.value); setValidation(null); }} /><button className="secondary" type="button" disabled={pickDirectory.isPending || switching} onClick={() => pickDirectory.mutate()}>{pickDirectory.isPending ? "正在选择…" : "选择文件夹"}</button></div></label><label>工作区名称<input name="name" defaultValue="CareerConsole" required /></label><div className="form-actions"><button disabled={validate.isPending || create.isPending || switching}>{validation?.valid ? "创建并切换" : "验证目录"}</button>{current.workspace_ready && <button className="secondary" type="button" disabled={switching} onClick={() => { setValidation(null); setChangingWorkspace(false); }}>取消更换</button>}</div>{validation && <div className={`notice wide ${validation.valid ? "success" : "error"}`}><strong>{validation.valid ? "目录可以使用" : "目录不可使用"}</strong><p>{validation.valid ? `将创建：${validation.workspace_path}` : validation.error}</p></div>}{pickDirectory.error && <p className="form-error wide">{pickDirectory.error.message}</p>}</form>
      </>}
      {(create.error || validate.error) && <p className="form-error">{(create.error ?? validate.error)?.message}</p>}
      {workspace.data?.pending_workspace_path && <div className="notice warning">
        <strong>有一个工作区等待切换</strong>
        <p>当前仍在使用：{workspace.data.active_workspace_path ?? workspace.data.workspace_path}</p>
        <p>等待切换到：{workspace.data.pending_workspace_path}</p>
        <div className="form-actions">
          <button type="button" disabled={switching} onClick={async () => {
            setRestartError("");
            try {
              setSwitching(true);
              await requestRestart();
              window.setTimeout(() => window.location.reload(), 1_500);
            } catch (error) {
              setSwitching(false);
              setRestartError(error instanceof Error ? error.message : "工作区切换失败。");
            }
          }}>检查并切换</button>
          <button type="button" className="secondary" disabled={cancelPending.isPending || switching} onClick={() => cancelPending.mutate()}>取消切换</button>
        </div>
      </div>}
      {(restartError || workspace.data?.last_switch_error) && <div className="notice error">
        <strong>未切换工作区，当前工作区仍可使用</strong>
        <p>{restartError || workspace.data?.last_switch_error}</p>
      </div>}
      <ConfigurationTestButton capability="workspace" label="测试当前工作区" disabled={!current.workspace_ready} />
      {switching && <div className="notice success"><strong>正在切换工作区</strong><p>本地服务会自动重启并继续初始化，无需重新输入启动命令。</p></div>}
    </section>}

    {step === 1 && configuration.data && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">可选能力</p><h2>AI 分析与生成</h2><p>配置后可使用邮件结构化分析、语义岗位匹配和简历生成；不配置时，手工档案、确定性匹配和投递管理仍可使用。</p></div><ProviderAgentConfiguration status={configuration.data} /></section>}
    {step === 2 && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">个人资料</p><h2>建立职业档案</h2><p>导入简历后会生成候选事实。导入完成后可进入事实审查，只有确认过的内容才会用于匹配和材料生成。</p></div><DocumentsPage /></section>}
    {step === 3 && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">招聘信息来源</p><h2>连接每日招聘</h2><p>OpenCLI 是外部应用，牛客负责每天获取当天新增信息；历史数据只在你主动选择时回看，最长 30 天。</p><button className="secondary" type="button" onClick={() => window.open("https://www.nowcoder.com/jobs/school/schedule?tab=3", "_blank", "noopener,noreferrer")}>打开牛客登录页</button></div><DataSourceSettings embedded /><DataSourcesPage setupOnly /></section>}
    {step === 4 && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">申请进度来源</p><h2>连接招聘邮箱</h2><p>邮箱以只读方式扫描最近 30 天的已读和未读邮件，为申请进度、日程和注意事项提供证据。</p></div><MessageCenterPage setupOnly /></section>}
    {step === 5 && configuration.data && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">提醒出口</p><h2>通知渠道</h2><p>QQ 只用于发送任务提醒、进度变化和系统告警。暂时不需要外部通知时可以跳过。</p></div><ChannelSettings status={configuration.data} /></section>}
    {step === 6 && configuration.data && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">后台自动化</p><h2>自动任务</h2><p>默认只保留本地任务提醒。邮箱、招聘来源、档案维护和外部通知需要你明确开启。</p></div><SchedulerSettings status={configuration.data} /></section>}
    {step === 7 && <section className="onboarding-card"><div className="panel-heading"><div><p className="eyebrow">启用前检查</p><h2>确认已选择的能力</h2></div><span>以后仍可在设置中修改</span></div><div className="capability-grid">{Object.entries(current.capabilities).map(([name, ready]) => <article className={ready ? "ready" : "optional"} key={name}><span>{ready ? "✓" : "○"}</span><div><strong>{CAPABILITY_LABELS[name] ?? name}</strong><small>{ready ? "可以使用" : "本次未启用"}</small></div></article>)}</div><div className="notice"><strong>开始使用后会发生什么</strong><p>服务会重新加载到正式模式。未配置或已跳过的能力保持关闭，不会主动产生网络请求。</p></div>{finish.error && <p className="form-error">{finish.error.message}</p>}</section>}

    <footer className="setup-actions">
      <button type="button" className="secondary" disabled={step === 0 || switching || decideStep.isPending} onClick={() => void move(step - 1)}>上一步</button>
      <span>{step + 1} / {STEPS.length}</span>
      {step < STEPS.length - 1 ? <div className="setup-decision-actions">
        {step > 0 && <button type="button" className="secondary" disabled={decideStep.isPending || switching} onClick={() => decideStep.mutate({ key: STEPS[step].key, state: "skipped" })}>暂时跳过</button>}
        <button type="button" disabled={!capabilityReady(STEPS[step].key) || decideStep.isPending || switching} onClick={() => decideStep.mutate({ key: STEPS[step].key, state: "configured" })}>
          {step === 0 ? "确认工作区并继续" : "已完成此步并继续"}
        </button>
      </div> : <button type="button" disabled={finish.isPending || switching} onClick={() => finish.mutate()}>{finish.isPending || switching ? "正在启动…" : "完成初始化并启动"}</button>}
    </footer>
  </main>;
}
