import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createApplication, deleteResume, editMaterial, finalizeMaterial, forkResumeFromMaterial, generateResume, getApplicationResumes, getApplications, getDefaultResume, getJobPosts, getMaterial, getMaterials, getResume, getResumeSeries, getResumeVersionDiff, importResume, saveApplicationResumeToLibrary, reviewMaterial, setDefaultResume, type ApplicationStatus, type Material, type MaterialType, type ResumeSeries } from "./api";
import { formatChinaTime } from "./time";

const TYPE_LABELS: Record<MaterialType, string> = { resume: "定制简历", cover_letter: "求职信", introduction: "自我介绍" };
const STATUS_LABELS: Record<string, string> = { draft: "需要修复", reviewed: "检查通过", final: "已定稿" };

export function MaterialsPage() {
  const client = useQueryClient();
  const [tab, setTab] = useState<"library" | "application">("library");
  const [copyingResumeId, setCopyingResumeId] = useState<string | null>(null);
  const resumes = useQuery({ queryKey: ["resume-series"], queryFn: getResumeSeries });
  const applicationResumes = useQuery({ queryKey: ["application-resumes"], queryFn: getApplicationResumes });
  const defaultResume = useQuery({ queryKey: ["default-resume"], queryFn: getDefaultResume });
  const generate = useMutation({
    mutationFn: generateResume,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["resume-series"] });
    },
  });
  const importFile = useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) => importResume(name, file),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["resume-series"] });
    },
  });
  const archive = useMutation({
    mutationFn: deleteResume,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["resume-series"] }),
        client.invalidateQueries({ queryKey: ["default-resume"] }),
      ]);
    },
  });
  const makeDefault = useMutation({
    mutationFn: (resume: ResumeSeries) => setDefaultResume(resume, defaultResume.data ?? null),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["default-resume"] }),
        client.invalidateQueries({ queryKey: ["resume-series"] }),
      ]);
    },
  });
  const copyToLibrary = useMutation({
    mutationFn: ({ resumeId, name }: { resumeId: string; name: string }) =>
      saveApplicationResumeToLibrary(resumeId, name),
    onSuccess: async () => {
      setCopyingResumeId(null);
      await client.invalidateQueries({ queryKey: ["resume-series"] });
    },
  });
  function submitGeneration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    generate.mutate(
      { name: String(data.get("name")), prompt: String(data.get("prompt")) },
      { onSuccess: () => form.reset() },
    );
  }
  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    if (!(file instanceof File) || !file.size) return;
    importFile.mutate(
      { name: String(data.get("name")), file },
      { onSuccess: () => form.reset() },
    );
  }
  const libraryCount = resumes.data?.total ?? 0;
  const applicationCount = applicationResumes.data?.total ?? 0;
  return <><header className="page-header"><div><p className="eyebrow">个人资料</p><h1>我的简历</h1></div><span className="health-pill ok">{libraryCount + applicationCount} 份</span></header>
    <div className="resume-tabs" role="tablist" aria-label="简历类型">
      <button type="button" role="tab" aria-selected={tab === "library"} className={tab === "library" ? "active" : ""} onClick={() => setTab("library")}>简历库 <span>{libraryCount}</span></button>
      <button type="button" role="tab" aria-selected={tab === "application"} className={tab === "application" ? "active" : ""} onClick={() => setTab("application")}>投递岗位简历 <span>{applicationCount}</span></button>
    </div>
    {tab === "library" ? <>
      <section className="resume-workbench">
        <form className="resume-action-form" onSubmit={submitGeneration}>
          <div><h2>生成简历</h2></div>
          <label>简历名称<input name="name" required placeholder="后端开发通用简历" /></label>
          <label className="wide">生成要求<textarea name="prompt" required rows={3} placeholder="突出后端工程和项目交付经历，控制在两页内" /></label>
          <button disabled={generate.isPending}>{generate.isPending ? "正在生成…" : "生成并加入简历库"}</button>
          {generate.error && <p className="form-error">{generate.error.message}</p>}
        </form>
        <form className="resume-action-form resume-import-form" onSubmit={submitImport}>
          <div><h2>导入简历</h2></div>
          <label>简历名称<input name="name" required placeholder="现有通用简历" /></label>
          <label className="wide">选择文件<input name="file" type="file" required accept=".docx,.pdf,.txt,.md,.markdown" /></label>
          <button className="secondary" disabled={importFile.isPending}>{importFile.isPending ? "正在导入…" : "导入到简历库"}</button>
          {importFile.error && <p className="form-error">{importFile.error.message}</p>}
        </form>
      </section>
      <section className="resume-inventory" aria-label="简历库">
        <div className="resume-inventory-heading"><h2>简历库</h2><Link to="/job-posts">目标岗位</Link></div>
        {resumes.data?.items.map(resume => <article className="resume-inventory-row" key={resume.id}>
          <button type="button" className={`resume-star ${resume.is_default ? "active" : ""}`} title={resume.is_default ? "默认简历" : "设为默认简历"} aria-label={resume.is_default ? `${resume.name}是默认简历` : `将${resume.name}设为默认简历`} disabled={makeDefault.isPending || resume.is_default} onClick={() => makeDefault.mutate(resume)}>{resume.is_default ? "★" : "☆"}</button>
          <Link className="resume-row-main" to={`/resumes/${resume.id}`}><strong>{resume.name}</strong><small>{resume.source_file_name ? `导入自 ${resume.source_file_name}` : "Agent 生成"} · v{resume.latest_finalized_version?.version_number ?? 1}</small></Link>
          <div className="resume-row-actions">
            {resume.docx_export && <a className="text-button" href={resume.docx_export.download_url} title="下载 Word 简历">下载 DOCX</a>}
            <button type="button" className="text-button danger-text" disabled={archive.isPending} onClick={() => { if (window.confirm(`归档“${resume.name}”？已绑定和已投递的版本不会受影响。`)) archive.mutate(resume.id); }}>归档</button>
          </div>
        </article>)}
        {!resumes.data?.items.length && <div className="resume-empty"><h2>简历库为空</h2><p>生成一份简历，或导入已有文件。</p></div>}
        {(makeDefault.error || archive.error) && <p className="form-error">{makeDefault.error?.message ?? archive.error?.message}</p>}
      </section>
    </> : <section className="resume-inventory" aria-label="投递岗位简历">
      <div className="resume-inventory-heading"><h2>投递岗位简历</h2><Link to="/applications">申请进度</Link></div>
      {applicationResumes.data?.items.map(resume => <article className="resume-inventory-row application-resume-row" key={resume.id}>
        <span className="resume-scope-mark" aria-hidden="true">↗</span>
        <div className="resume-row-main"><strong>{resume.company} · {resume.job_title}</strong><small>{resume.name} · {applicationStatusLabel(resume.application_status)}</small></div>
        <div className="resume-row-actions">
          {resume.docx_export && <a className="text-button" href={resume.docx_export.download_url}>下载 DOCX</a>}
          <button type="button" className="text-button" onClick={() => setCopyingResumeId(copyingResumeId === resume.id ? null : resume.id)}>保存到简历库</button>
        </div>
        {copyingResumeId === resume.id && <form className="resume-copy-form" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); copyToLibrary.mutate({ resumeId: resume.id, name: String(data.get("name")) }); }}><input name="name" required defaultValue={`${resume.job_title ?? resume.name}简历`} aria-label="保存后的简历名称" /><button disabled={copyToLibrary.isPending}>{copyToLibrary.isPending ? "正在保存…" : "保存"}</button></form>}
      </article>)}
      {!applicationResumes.data?.items.length && <div className="resume-empty"><h2>暂无岗位简历</h2><p>从申请进度中为具体岗位生成。</p></div>}
      {copyToLibrary.error && <p className="form-error">{copyToLibrary.error.message}</p>}
    </section>}
  </>;
}

export function JobMaterialsPage() {
  const { id: jobId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const jobs = useQuery({ queryKey: ["job-posts"], queryFn: getJobPosts });
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const create = useMutation({
    mutationFn: () => createApplication(jobId),
    onSuccess: async application => {
      await client.invalidateQueries({ queryKey: ["applications"] });
      navigate(`/applications/${application.id}`);
    },
  });
  const job = jobs.data?.items.find(item => item.id === jobId);
  const application = applications.data?.items.find(item => item.job_post_id === jobId && item.current_status !== "archived");
  if (application) return <section className="empty-state"><h2>在申请进度中准备简历</h2><button onClick={() => navigate(`/applications/${application.id}`)}>进入申请</button></section>;
  return <><header className="page-header"><div><p className="eyebrow">目标岗位</p><h1>{job ? `${job.company} · ${job.title}` : "岗位简历"}</h1></div></header>
    <section className="empty-state"><h2>先建立申请进度</h2><p>建立后可选择简历库版本，或生成一份岗位专属简历。</p><button disabled={create.isPending || !job} onClick={() => create.mutate()}>{create.isPending ? "正在建立…" : "建立申请并准备简历"}</button>{create.error && <p className="form-error">{create.error.message}</p>}</section>
  </>;
}

function applicationStatusLabel(status: ApplicationStatus | null) {
  const labels: Partial<Record<ApplicationStatus, string>> = {
    preparing_materials: "准备材料",
    ready_to_apply: "待投递",
    submitted: "已投递",
    application_confirmed: "网申确认",
    assessment: "测评",
    written_test: "笔试",
    interview: "面试",
  };
  return status ? labels[status] ?? "流程进行中" : "申请流程";
}

export function ResumeDetailPage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: ["resume", id], queryFn: () => getResume(id), enabled: Boolean(id) });
  if (query.isLoading) return <section className="empty-state"><p>正在读取简历版本…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "简历不存在"}</section>;
  const resume = query.data;
  const docx = resume.docx_export ?? resume.exports.find(item => item.format === "docx");
  const pdf = resume.export ?? resume.exports.find(item => item.format === "pdf");
  return <><header className="page-header resume-detail-header"><div><p className="eyebrow">{resume.scope === "application" ? "岗位简历" : "简历库"}</p><h1>{resume.name}</h1><p>{resume.source_file_name ? `导入自 ${resume.source_file_name}` : "根据个人档案生成"}</p></div><div className="resume-detail-actions">{docx && <a className="download-button" href={docx.download_url}>下载 DOCX</a>}{pdf && <a className="download-button secondary" href={pdf.download_url}>下载 PDF</a>}</div></header>
    <section className="resume-metadata" aria-label="简历信息"><span>v{resume.current_version.version_number}</span><span>{formatChinaTime(resume.current_version.created_at)}（北京时间）</span><span>{resume.current_version.blocks.length} 个部分</span>{resume.is_default && <span className="current-mark">默认简历</span>}</section>
    <section className="resume-document" aria-label="简历正文">{resume.current_version.blocks.map(block => <section className="resume-document-section" key={block.id}><h2>{block.section}</h2><p>{block.text}</p></section>)}</section>
    {pdf && <section className="resume-preview"><div className="resume-preview-heading"><div><p className="eyebrow">PDF 预览</p><h2>打印效果</h2></div><span>{pdf.page_count} 页</span></div><img src={pdf.preview_url} alt={`${resume.name} PDF 第一页预览`} /></section>}
    <details className="panel audit-details"><summary>版本历史（{resume.versions.length}）</summary>{resume.versions.map(version => <p className="history-row" key={version.id}>v{version.version_number} · {STATUS_LABELS[version.status] ?? version.status}<small>{formatChinaTime(version.created_at)}（北京时间） · {version.content_hash}</small></p>)}</details>
  </>;
}

export function MaterialDetailPage() {
  const { id = "" } = useParams(); const client = useQueryClient(); const navigate = useNavigate();
  const query = useQuery({ queryKey: ["material", id], queryFn: () => getMaterial(id), enabled: Boolean(id) });
  const applications = useQuery({ queryKey: ["applications"], queryFn: getApplications });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["material", id] }); await client.invalidateQueries({ queryKey: ["materials"] }); };
  const review = useMutation({ mutationFn: () => reviewMaterial(id), onSuccess: refresh });
  const finalize = useMutation({ mutationFn: (material: Material) => finalizeMaterial(material), onSuccess: refresh });
  const createTracking = useMutation({
    mutationFn: (jobPostId: string) => createApplication(jobPostId),
    onSuccess: async application => {
      await client.invalidateQueries({ queryKey: ["applications"] });
      navigate(`/applications/${application.id}`);
    },
  });
  const resumes = useQuery({ queryKey: ["resume-series"], queryFn: getResumeSeries });
  if (query.isLoading) return <section className="empty-state"><p>正在读取材料版本…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "材料不存在"}</section>;
  const material = query.data;
  const existingApplication = applications.data?.items?.find(item => item.job_post_id === material.job_post_id);
  const comparisonFrom = material.source_resume_version_id ?? material.versions.at(-1)?.id ?? null;
  return <><header className="page-header job-detail-header"><div><p className="eyebrow"><Link to={`/job-posts/${material.job_post_id}/materials`}>岗位申请材料</Link> / {material.company}</p><h1>{material.current_version.title}</h1><p>{TYPE_LABELS[material.material_type]}</p></div><span className={`health-pill ${material.status === "draft" ? "blocked" : "ok"}`}>{STATUS_LABELS[material.status]}</span></header>
    {material.strategy_stale && <section className="notice error"><strong>材料策略需要重新确认</strong><p>{material.strategy_stale_reason} 已定稿材料不会被自动改写；保存新版本后清除此标记。</p></section>}
    <section className="metric-grid"><article><span>内容状态</span><strong>{STATUS_LABELS[material.status]}</strong><small>{material.current_version.blocks.length} 个内容块</small></article><article><span>材料复核</span><strong>{material.review?.error_count ?? 0} 错误</strong><small>{material.review?.warning_count ?? 0} 条风险提示</small></article><article><span>事实引用</span><strong>{material.current_version.blocks.reduce((total, block) => total + block.fact_snapshots.length, 0)}</strong><small>条已确认事实快照</small></article><article><span>导出</span><strong>{material.export ? `${material.export.page_count} 页` : "未生成"}</strong><small>{material.export?.text_layer_ok ? "文本层通过" : "最终确认后生成"}</small></article></section>
    {material.review?.findings.length ? <section className="panel findings"><div className="panel-heading"><h2>复核发现</h2><span>{material.review.findings.length} 项</span></div>{material.review.findings.map((item) => <div className={`finding ${item.severity}`} key={item.id}><strong>{item.severity === "error" ? "阻断" : "风险"} · {item.code}</strong><p>{item.message}</p></div>)}</section> : <section className="notice success">未发现事实冲突；请仍检查经历、教育、技能和联系方式是否完整。</section>}
    <MaterialEditor material={material} onSaved={refresh} />
    {material.material_type === "resume" && material.status !== "draft" && <details className="advanced-settings"><summary>将当前版本保存为可复用简历</summary><ResumeForkPanel material={material} resumes={resumes.data?.items ?? []} /></details>}
    {material.status !== "final" && <section className="panel final-actions"><div><h2>确认定稿</h2><p>定稿后内容不可继续编辑，并会生成经过文本层和页面渲染检查的 PDF。</p></div><div><button className="secondary" onClick={() => review.mutate()} disabled={review.isPending}>重新检查</button><button onClick={() => finalize.mutate(material)} disabled={finalize.isPending || Boolean(material.review?.error_count)}>确认定稿并导出 PDF</button></div>{Boolean(material.review?.error_count) && <p className="disabled-reason">仍有阻断问题，请先根据检查结果修改材料。</p>}{(review.error || finalize.error) && <p className="form-error">{review.error?.message ?? finalize.error?.message}</p>}</section>}
    {material.status === "final" && <section className="panel next-action-card"><div><p className="eyebrow">下一步</p><h2>建立申请进度</h2><p>材料已经确认，可以开始跟踪投递、测评、面试和结果。</p></div>{existingApplication ? <Link className="download-button" to={`/applications/${existingApplication.id}`}>查看已有申请进度</Link> : <button type="button" onClick={() => createTracking.mutate(material.job_post_id)} disabled={createTracking.isPending}>{createTracking.isPending ? "正在创建…" : "创建申请"}</button>}{createTracking.error && <p className="form-error">{createTracking.error.message}</p>}</section>}
    {material.export && <section className="panel export-result"><div><p className="eyebrow">已验证 PDF</p><h2>最终导出已通过</h2><p>{(material.export.size_bytes / 1024).toFixed(1)} KB · {material.export.page_count} 页 · 文本层 {material.export.text_layer_ok ? "通过" : "失败"} · 渲染 {material.export.render_ok ? "通过" : "失败"}</p><details><summary>查看文件校验值</summary><code>{material.export.sha256}</code></details><p><a className="download-button" href={material.export.download_url}>下载 PDF</a></p></div><img src={material.export.preview_url} alt="最终 PDF 第一页渲染预览" /></section>}
    <details className="panel audit-details"><summary>审计与版本信息</summary><p>{material.resume_series_type === "direction" ? "方向简历" : "基础简历"} → 岗位定制 v{material.current_version.version_number}{material.source_resume_version_id ? "，来源版本已锁定。" : "，当前版本没有上游可复用版本。"}</p>{comparisonFrom && comparisonFrom !== material.current_version.id && <Link to={`/resume-diff/${comparisonFrom}/${material.current_version.id}`}>比较来源版本与当前版本</Link>}<p><small>事实集合校验值：{material.current_version.fact_set_hash}</small></p>{material.versions.map((version) => <p className="history-row" key={version.id}>v{version.version_number} · {STATUS_LABELS[version.status] ?? version.status}<small>{formatChinaTime(version.created_at)}（北京时间） · {version.content_hash}</small></p>)}</details></>;
}

function ResumeForkPanel({ material, resumes }: { material: Material; resumes: Awaited<ReturnType<typeof getResumeSeries>>["items"] }) {
  const client = useQueryClient(); const [seriesType, setSeriesType] = useState<"base" | "direction">("base");
  const fork = useMutation({ mutationFn: (body: { name: string; parent_resume_id?: string; direction_label?: string }) => forkResumeFromMaterial({ material_id: material.id, series_type: seriesType, ...body }), onSuccess: () => client.invalidateQueries({ queryKey: ["resume-series"] }) });
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); fork.mutate({ name: String(data.get("name")), ...(seriesType === "direction" ? { parent_resume_id: String(data.get("parent_resume_id")), direction_label: String(data.get("direction_label")) } : {}) }); }
  return <section className="nested-panel"><div><h3>保存为可复用简历版本</h3><p>复制当前内容和事实快照；方向简历必须从基础简历派生。</p></div><form className="form-grid" onSubmit={submit}><label>系列类型<select value={seriesType} onChange={event => setSeriesType(event.target.value as "base" | "direction")}><option value="base">基础简历</option><option value="direction">方向简历</option></select></label><label>名称<input name="name" required defaultValue={seriesType === "base" ? "通用基础简历" : `${material.job_title}方向简历`} /></label>{seriesType === "direction" && <><label>父基础简历<select name="parent_resume_id" required defaultValue=""><option value="" disabled>选择基础简历</option>{resumes.filter(item => item.series_type === "base" && item.latest_version).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>方向名称<input name="direction_label" required placeholder="例如：后端工程" /></label></>}<button disabled={fork.isPending}>{fork.isPending ? "保存中…" : "保存可复用版本"}</button>{fork.data && <p className="notice success">已创建{fork.data.series_type === "base" ? "基础" : "方向"}简历：{fork.data.name}</p>}{fork.error && <p className="form-error">{fork.error.message}</p>}</form></section>;
}

export function ResumeDiffPage() {
  const { fromVersionId = "", toVersionId = "" } = useParams();
  const query = useQuery({ queryKey: ["resume-version-diff", fromVersionId, toVersionId], queryFn: () => getResumeVersionDiff(fromVersionId, toVersionId), enabled: Boolean(fromVersionId && toVersionId) });
  if (query.isLoading) return <section className="empty-state"><p>正在计算版本差异…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "无法读取版本差异"}</section>;
  const diff = query.data;
  return <><header className="page-header"><div><p className="eyebrow"><Link to="/materials">申请材料</Link> / 版本比较</p><h1>简历版本差异</h1></div><span className="health-pill ok">{diff.summary.changed + diff.summary.added + diff.summary.removed} 项变化</span></header><section className="metric-grid"><article><span>新增块</span><strong>{diff.summary.added}</strong></article><article><span>删除块</span><strong>{diff.summary.removed}</strong></article><article><span>修改块</span><strong>{diff.summary.changed}</strong></article><article><span>事实变化</span><strong>{diff.fact_changes.added_fact_ids.length + diff.fact_changes.removed_fact_ids.length}</strong></article></section><section className="panel"><div className="panel-heading"><div><h2>{diff.from_version.title}</h2><small>{diff.from_version.version_scope} → {diff.to_version.version_scope}</small></div><span>{diff.blocks.length} 个内容块</span></div>{diff.blocks.map(block => <article className={`material-block finding ${block.change === "unchanged" ? "info" : "warning"}`} key={block.block_id}><strong>{block.change.toUpperCase()} · {block.block_id}</strong><div className="metric-grid"><div><small>之前</small><p>{block.before?.text ?? "—"}</p><code>{block.before?.fact_ids.join(", ") || "无事实引用"}</code></div><div><small>之后</small><p>{block.after?.text ?? "—"}</p><code>{block.after?.fact_ids.join(", ") || "无事实引用"}</code></div></div></article>)}</section></>;
}

function MaterialEditor({ material, onSaved }: { material: Material; onSaved: () => Promise<void> }) {
  const [values, setValues] = useState(() => Object.fromEntries(material.current_version.blocks.map((block) => [block.id, block.text])));
  const edit = useMutation({ mutationFn: () => editMaterial(material, material.current_version.blocks.map((block) => ({ id: block.id, text: values[block.id] ?? block.text }))), onSuccess: onSaved });
  return <section className="panel material-editor"><div className="panel-heading"><div><p className="eyebrow">材料正文</p><h2>{material.status === "final" ? "最终内容" : "编辑事实表达"}</h2></div><span>{material.current_version.blocks.length} 条</span></div>{material.current_version.blocks.map((block) => <article className="material-block" key={block.id}><strong>{block.section}</strong>{material.status === "final" ? <div className="readonly-material">{values[block.id] ?? block.text}</div> : <textarea aria-label={`${block.section}内容`} rows={3} value={values[block.id] ?? block.text} onChange={(event) => setValues((previous) => ({ ...previous, [block.id]: event.target.value }))} />}<details><summary>事实引用（{block.fact_snapshots.length}）</summary>{block.fact_snapshots.map((fact) => <blockquote key={fact.id}>{fact.value}<small>{fact.category} · {fact.field_key} · 事实版本 {fact.fact_version}</small></blockquote>)}</details></article>)}{material.status !== "final" && <button onClick={() => edit.mutate()} disabled={edit.isPending}>{edit.isPending ? "保存并审查中…" : "保存为新版本并重新审查"}</button>}{edit.error && <p className="form-error">{edit.error.message}</p>}</section>;
}
