import { Link } from "react-router-dom";

const sections = [
  ["建立个人档案", "导入简历和项目资料，Agent 会整理有效信息并保留原文来源。", "/documents", "导入资料"],
  ["获取个性化岗位推荐", "系统每天获取牛客当天新增，解析官方具体 JD，并根据个人档案、偏好、洞察和手动方向自动筛选。", "/opportunities", "查看岗位推荐"],
  ["准备并跟踪申请", "保存具体岗位，选择简历方向，生成有事实依据的材料，并维护完整申请时间线。", "/applications", "查看申请进度"],
  ["从邮件提取进度与日程", "只读同步已读和未读邮件。需要人工判断的分析结果会进入待我处理，确认后才更新正式数据。", "/message-center", "查看招聘邮件"],
  ["连接网站和邮箱", "所有数据来源都在设置中保存、测试。网站同步前必须显示浏览器会话已登录。", "/settings?section=sources", "配置数据来源"],
  ["处理待定变化", "无法安全自动落地的申请、邮件和面试变化会集中在这里。", "/reviews", "打开待我处理"],
] as const;

export function HelpPage() {
  return <>
    <header className="page-header"><div><p className="eyebrow">使用说明</p><h1>从个人档案开始求职</h1><p>CareerConsole 把招聘发现、材料准备、申请进度和邮件日程连接成一个可核对的流程。</p></div></header>
    <section className="help-grid">{sections.map(([title, text, to, action]) => <article className="panel" key={title}><h2>{title}</h2><p>{text}</p><Link to={to}>{action}</Link></article>)}</section>
    <section className="panel"><h2>首次使用顺序</h2><ol><li>选择工作区并完成初始化。</li><li>配置并测试模型服务、邮箱和 OpenCLI。</li><li>导入资料并检查个人档案。</li><li>登录牛客或 BOSS，并检查会话状态。</li><li>开始发现岗位、准备材料和跟踪申请。</li></ol></section>
  </>;
}
