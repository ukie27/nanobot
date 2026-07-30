import { Link } from "react-router-dom";

const sections = [
  ["建立可信职业档案", "导入简历和项目资料，按业务块核对原文证据。确认后才用于岗位判断和材料生成。", "/documents", "导入资料"],
  ["获取个性化岗位推荐", "系统每天获取牛客当天新增，解析官方具体 JD，并根据已确认档案、偏好、洞察和手动方向自动筛选。", "/opportunities", "查看岗位推荐"],
  ["准备并跟踪申请", "保存具体岗位，选择简历方向，生成有事实依据的材料，并维护完整申请时间线。", "/applications", "查看申请进度"],
  ["从邮件提取进度与日程", "只读同步已读和未读邮件。分析结果先进入确认中心，确认后才更新正式数据。", "/message-center", "查看招聘邮件"],
  ["连接网站和邮箱", "所有数据来源都在设置中保存、测试。网站同步前必须显示浏览器会话已登录。", "/settings?section=sources", "配置数据来源"],
  ["处理智能建议", "先看发现内容和证据，再决定确认、修改或拒绝。模型不能直接改变业务记录。", "/reviews", "打开待我确认"],
] as const;

export function HelpPage() {
  return <>
    <header className="page-header"><div><p className="eyebrow">使用说明</p><h1>从一份可信档案开始求职</h1><p>CareerConsole 把招聘发现、材料准备、申请进度和邮件日程连接成一个可核对的流程。</p></div></header>
    <section className="notice opportunity-note"><strong>核心原则</strong><p>智能功能负责整理和建议；涉及职业档案、申请进度、材料与任务的正式变化都由你确认。</p></section>
    <section className="help-grid">{sections.map(([title, text, to, action]) => <article className="panel" key={title}><h2>{title}</h2><p>{text}</p><Link to={to}>{action}</Link></article>)}</section>
    <section className="panel"><h2>首次使用顺序</h2><ol><li>选择工作区并完成初始化。</li><li>配置并测试模型服务、邮箱和 OpenCLI。</li><li>登录牛客或 BOSS，并检查会话状态。</li><li>导入资料，在待我确认中建立可信档案。</li><li>开始发现岗位、准备材料和跟踪申请。</li></ol></section>
  </>;
}
