import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  completeOnboarding,
  createWorkspace,
  getConfiguration,
  getOnboardingStatus,
  getWorkspaceStatus,
  pickWorkspaceDirectory,
  restartService,
  validateWorkspace,
  type WorkspaceValidation,
} from "./api";
import { DataSourcesPage } from "./ConnectorPages";
import { MessageCenterPage } from "./MailPages";
import { DocumentsPage } from "./ProfilePages";
import {
  ChannelSettings,
  DataSourceSettings,
  ProviderAgentConfiguration,
  SchedulerSettings,
} from "./SettingsPage";

const STEPS = ["工作区", "AI 与 Agent", "职业档案", "数据来源", "通知渠道", "自动任务", "完成"];
const CAPABILITY_LABELS: Record<string, string> = {
  workspace: "正式工作区",
  provider: "AI Provider",
  profile: "职业档案",
  mail: "只读邮箱",
  opencli: "OpenCLI / 牛客",
  channel: "通知渠道",
  scheduler: "自动任务",
};

async function requestRestartBestEffort() {
  try {
    await restartService();
  } catch {
    // The process may close the connection after accepting the restart request.
  }
}

export function OnboardingPage() {
  const client = useQueryClient();
  const [step, setStep] = useState(0);
  const [validation, setValidation] = useState<WorkspaceValidation | null>(null);
  const [switching, setSwitching] = useState(false);
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
      setSwitching(true);
      await requestRestartBestEffort();
      window.setTimeout(() => window.location.reload(), 1_500);
    },
  });
  const finish = useMutation({
    mutationFn: async () => {
      const capabilities = onboarding.data?.capabilities ?? {};
      const optional = ["provider", "profile", "mail", "opencli", "channel"];
      await completeOnboarding(optional.filter(name => !capabilities[name as keyof typeof capabilities]));
      await requestRestartBestEffort();
    },
    onSuccess: () => {
      setSwitching(true);
      window.setTimeout(() => window.location.reload(), 1_500);
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

  if (onboarding.isLoading || workspace.isLoading) {
    return <main className="onboarding-shell"><section className="onboarding-card"><p>正在检查本地初始化状态…</p></section></main>;
  }
  const error = onboarding.error ?? workspace.error ?? configuration.error;
  if (error) {
    return <main className="onboarding-shell"><section className="notice error"><strong>初始化控制面不可用</strong><p>{error.message}</p></section></main>;
  }

  const current = onboarding.data!;
  return <main className="onboarding-shell">
    <header className="onboarding-header">
      <div className="brand onboarding-brand"><div className="brand-mark">C</div><div><strong>CareerConsole</strong><span>首次初始化</span></div></div>
      <div><p className="eyebrow">LOCAL-FIRST SETUP</p><h1>配置你的求职工作台</h1><p>完成正式工作区后，按需启用 AI、邮箱、岗位来源和通知。所有可选能力以后仍可在设置中修改。</p></div>
    </header>
    <ol className="setup-steps" aria-label="初始化步骤">
      {STEPS.map((label, index) => <li className={index === step ? "active" : index < step ? "done" : ""} key={label}><span>{index < step ? "✓" : index + 1}</span>{label}</li>)}
    </ol>

    {step === 0 && <section className="onboarding-card">
      <div className="panel-heading"><div><p className="eyebrow">STEP 1 · REQUIRED</p><h2>选择正式工作区</h2></div><span className={`health-pill ${current.workspace_ready ? "ok" : "blocked"}`}>{current.workspace_ready ? "已就绪" : "必须完成"}</span></div>
      {current.workspace_ready && !changingWorkspace ? <><p>CareerConsole 的数据库、配置、材料、日志和导出文件都保存在这里。</p><dl className="path-list"><div><dt>工作区</dt><dd>{workspace.data?.workspace_path}</dd></div><div><dt>数据库</dt><dd>{workspace.data?.paths.database}</dd></div></dl><div className="form-actions"><button className="secondary" type="button" onClick={() => { setValidation(null); setChangingWorkspace(true); }}>更换工作区</button></div></> : <>
        <p>请选择一个具体父目录，CareerConsole 会在其中创建独立文件夹。机器级 Bootstrap 文件只保存这个路径，不保存业务数据或密钥。</p>
        <form className="form-grid" onSubmit={submitWorkspace}><label className="wide">父目录<div className="path-picker-row"><input name="parent_directory" required placeholder="例如 D:\CareerWorkspace" value={workspaceParent} onChange={event => { setWorkspaceParent(event.target.value); setValidation(null); }} /><button className="secondary" type="button" disabled={pickDirectory.isPending || switching} onClick={() => pickDirectory.mutate()}>{pickDirectory.isPending ? "正在选择…" : "选择文件夹"}</button></div></label><label>工作区名称<input name="name" defaultValue="CareerConsole" required /></label><div className="form-actions"><button disabled={validate.isPending || create.isPending || switching}>{validation?.valid ? "创建并切换" : "验证目录"}</button>{current.workspace_ready && <button className="secondary" type="button" disabled={switching} onClick={() => { setValidation(null); setChangingWorkspace(false); }}>取消更换</button>}</div>{validation && <div className={`notice wide ${validation.valid ? "success" : "error"}`}><strong>{validation.valid ? "目录可以使用" : "目录不可使用"}</strong><p>{validation.valid ? `将创建：${validation.workspace_path}` : validation.error}</p></div>}{pickDirectory.error && <p className="form-error wide">{pickDirectory.error.message}</p>}</form>
      </>}
      {(create.error || validate.error) && <p className="form-error">{(create.error ?? validate.error)?.message}</p>}
      {switching && <div className="notice success"><strong>正在切换工作区</strong><p>本地服务会自动重启并继续初始化，无需重新输入启动命令。</p></div>}
    </section>}

    {step === 1 && configuration.data && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">STEP 2 · OPTIONAL</p><h2>AI 与 Agent</h2><p>至少配置一个 Provider 才能使用邮件分析、岗位匹配和简历生成；不影响手工档案与投递管理。</p></div><ProviderAgentConfiguration status={configuration.data} /></section>}
    {step === 2 && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">STEP 3 · OPTIONAL</p><h2>建立职业档案</h2><p>导入一份简历作为事实来源。Agent 只生成候选事实，进入正式档案前仍需人工确认。</p></div><DocumentsPage /></section>}
    {step === 3 && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">STEP 4 · OPTIONAL</p><h2>连接招聘数据</h2><p>邮箱严格只读且最多扫描最近30天；牛客由外部 OpenCLI 使用现有浏览器登录态读取。</p><button className="secondary" type="button" onClick={() => window.open("https://www.nowcoder.com/jobs/school/schedule?tab=3", "_blank", "noopener,noreferrer")}>打开牛客登录页</button></div><DataSourceSettings /><DataSourcesPage setupOnly /><MessageCenterPage setupOnly /></section>}
    {step === 4 && configuration.data && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">STEP 5 · OPTIONAL</p><h2>通知渠道</h2><p>Channel 默认只作为提醒出口。没有 QQ 或暂时不需要外部通知时可以直接跳过。</p></div><ChannelSettings status={configuration.data} /></section>}
    {step === 5 && configuration.data && <section className="onboarding-stage"><div className="setup-intro"><p className="eyebrow">STEP 6</p><h2>自动任务</h2><p>初始化完成并重启后，Scheduler 才会开始邮件轮询、当天岗位同步、档案维护和提醒分发。</p></div><SchedulerSettings status={configuration.data} /></section>}
    {step === 6 && <section className="onboarding-card"><div className="panel-heading"><div><p className="eyebrow">READY REVIEW</p><h2>能力检查</h2></div><span>可选项可稍后补充</span></div><div className="capability-grid">{Object.entries(current.capabilities).map(([name, ready]) => <article className={ready ? "ready" : "optional"} key={name}><span>{ready ? "✓" : "○"}</span><div><strong>{CAPABILITY_LABELS[name] ?? name}</strong><small>{ready ? "已配置" : "暂未配置"}</small></div></article>)}</div><div className="notice"><strong>启动边界</strong><p>点击完成后，本地服务会重启到 Product 模式。未配置的能力保持关闭，不会产生后台错误或网络请求。</p></div>{finish.error && <p className="form-error">{finish.error.message}</p>}</section>}

    <footer className="setup-actions"><button type="button" className="secondary" disabled={step === 0 || switching} onClick={() => void move(step - 1)}>上一步</button><span>{step + 1} / {STEPS.length}</span>{step < STEPS.length - 1 ? <button type="button" disabled={(step === 0 && !current.workspace_ready) || switching} onClick={() => void move(step + 1)}>{step > 0 ? "保存状态并继续" : "继续"}</button> : <button type="button" disabled={finish.isPending || switching} onClick={() => finish.mutate()}>{finish.isPending || switching ? "正在启动…" : "完成初始化并启动"}</button>}</footer>
  </main>;
}
