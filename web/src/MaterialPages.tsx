import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createApplication, editMaterial, editResume, finalizeMaterial, finalizeResume, forkResumeFromMaterial, generateMaterialAgentProposal, generateStandaloneResumeProposal, getApplications, getDefaultResume, getJobPosts, getMaterial, getMaterialAgentProposals, getMaterials, getResume, getResumeDirections, getResumeSeries, getResumeVersionDiff, getStandaloneResumeProposals, resolveMaterialAgentProposal, resolveStandaloneResumeProposal, reviewMaterial, reviewResume, setDefaultResume, type Material, type MaterialAgentProposal, type MaterialType, type ResumeDetail, type ResumeSeries, type StandaloneResumeProposal } from "./api";
import { formatChinaTime } from "./time";

const TYPE_LABELS: Record<MaterialType, string> = { resume: "定制简历", cover_letter: "求职信", introduction: "自我介绍" };
const STATUS_LABELS: Record<string, string> = { draft: "需要修复", reviewed: "检查通过", final: "已定稿" };

export function MaterialsPage() {
  const client = useQueryClient();
  const resumes = useQuery({ queryKey: ["resume-series"], queryFn: getResumeSeries });
  const defaultResume = useQuery({ queryKey: ["default-resume"], queryFn: getDefaultResume });
  const proposals = useQuery({ queryKey: ["standalone-resume-proposals"], queryFn: getStandaloneResumeProposals });
  const [generatedNotice, setGeneratedNotice] = useState(false);
  const generate = useMutation({
    mutationFn: generateStandaloneResumeProposal,
    onMutate: () => setGeneratedNotice(false),
    onSuccess: async () => {
      setGeneratedNotice(true);
      await client.invalidateQueries({ queryKey: ["standalone-resume-proposals"] });
    },
  });
  const resolve = useMutation({
    mutationFn: ({ proposal, resolution }: { proposal: StandaloneResumeProposal; resolution: "confirmed" | "rejected" }) =>
      resolveStandaloneResumeProposal(proposal, resolution),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["standalone-resume-proposals"] }),
        client.invalidateQueries({ queryKey: ["resume-series"] }),
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
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    generate.mutate(
      { name: String(data.get("name")), prompt: String(data.get("prompt")) },
      { onSuccess: () => form.reset() },
    );
  }
  return <><header className="page-header"><div><p className="eyebrow">我的资料</p><h1>我的简历</h1><p>维护可复用简历版本。针对具体岗位的定制，请从目标岗位进入。</p></div><span className="health-pill ok">{resumes.data?.total ?? 0} 份</span></header>
    <section className="panel resume-generator"><div><p className="eyebrow">Agent 生成 · 需要确认</p><h2>按你的要求创建一份简历</h2><p>Agent 只使用已确认的职业事实。生成结果先作为候选，确认后才创建正式简历版本。</p></div><form className="form-grid" onSubmit={submit}><label>简历名称<input name="name" required placeholder="例如：后端开发通用简历" /></label><label className="wide">生成要求<textarea name="prompt" required rows={4} placeholder="例如：突出 Python 后端、Agent 应用和项目交付经历，整体控制在两页内" /></label><button disabled={generate.isPending}>{generate.isPending ? "Agent 正在生成…" : "生成简历候选"}</button>{generate.error && <p className="form-error">{generate.error.message}</p>}</form></section>
    {generatedNotice && <section className="notice success" role="status">简历候选已生成，请在下方核对内容和事实依据。确认前不会创建正式简历。</section>}
    <section className="panel resume-proposals"><div className="panel-heading"><div><p className="eyebrow">生成结果</p><h2>待确认候选</h2></div><span>{proposals.data?.items.filter(item => item.status === "proposed").length ?? 0} 待确认</span></div>
      {proposals.data?.items.map((proposal, index) => <details className="resume-proposal" key={proposal.id} open={index === 0 && proposal.status === "proposed" ? true : undefined}><summary><span><strong>{proposal.resume_name}</strong><small>{proposal.content.rationale}</small></span><span className={`health-pill ${proposal.status === "confirmed" ? "ok" : proposal.status === "rejected" ? "blocked" : ""}`}>{proposal.status === "proposed" ? "待确认" : proposal.status === "confirmed" ? "已创建" : "已拒绝"}</span></summary><div className="resume-proposal-body"><p><strong>你的要求：</strong>{proposal.user_prompt}</p>{proposal.content.blocks.map(block => <article className="finding info" key={block.blockId}><strong>{block.section}</strong><p>{block.text}</p><details><summary>查看事实依据</summary><small>{block.factIds.join("、")}</small></details></article>)}{proposal.status === "proposed" && <div className="button-row"><button className="secondary" disabled={resolve.isPending} onClick={() => resolve.mutate({ proposal, resolution: "rejected" })}>拒绝</button><button disabled={resolve.isPending} onClick={() => resolve.mutate({ proposal, resolution: "confirmed" })}>{resolve.isPending ? "正在确认…" : "确认并创建简历"}</button></div>}{proposal.resume_id && <Link className="download-button secondary" to={`/resumes/${proposal.resume_id}`}>查看已创建简历</Link>}</div></details>)}
      {!proposals.data?.items.length && <p>还没有生成记录。填写名称和要求后，候选会显示在这里。</p>}
      {resolve.error && <p className="form-error">{resolve.error.message}</p>}
    </section>
    <section className="panel resume-library"><div className="panel-heading"><div><p className="eyebrow">正式资产</p><h2>简历版本库</h2></div><Link to="/job-posts">前往目标岗位定制</Link></div>
      {resumes.data?.items.map(resume => <div className="resume-series-row" key={resume.id}><Link to={`/resumes/${resume.id}`}><strong>{resume.series_type === "base" ? "基础简历" : "方向简历"} · {resume.name}</strong><small>{resume.direction_label ? `${resume.direction_label} · ` : ""}{resume.latest_finalized_version ? `最新定稿 v${resume.latest_finalized_version.version_number}` : resume.latest_version ? `最新版本 v${resume.latest_version.version_number}，尚未定稿` : "尚无版本"}</small></Link>{resume.is_default ? <span className="health-pill ok">默认简历</span> : <button type="button" className="secondary" disabled={!resume.latest_finalized_version || makeDefault.isPending} onClick={() => makeDefault.mutate(resume)}>{resume.latest_finalized_version ? "设为默认" : "定稿后可设置"}</button>}</div>)}
      {!resumes.data?.items.length && <div className="empty-state"><h2>还没有正式简历</h2><p>可以先由 Agent 生成候选并确认，或在岗位定制完成后保存为可复用版本。</p></div>}
      {makeDefault.error && <p className="form-error">{makeDefault.error.message}</p>}
    </section></>;
}

export function JobMaterialsPage() {
  const { id: jobId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [resumeId, setResumeId] = useState("");
  const [resumeName, setResumeName] = useState("");
  const jobs = useQuery({ queryKey: ["job-posts"], queryFn: getJobPosts });
  const materials = useQuery({ queryKey: ["materials"], queryFn: getMaterials });
  const resumes = useQuery({ queryKey: ["resume-series"], queryFn: getResumeSeries });
  const directions = useQuery({ queryKey: ["resume-directions", jobId], queryFn: () => getResumeDirections(jobId), enabled: Boolean(jobId) });
  const proposals = useQuery({ queryKey: ["material-agent-proposals", jobId], queryFn: () => getMaterialAgentProposals(jobId), enabled: Boolean(jobId) });
  const generate = useMutation({
    mutationFn: () => generateMaterialAgentProposal({
      job_post_id: jobId,
      resume_name: resumeId ? (resumes.data?.items.find(item => item.id === resumeId)?.name ?? "岗位定制简历") : resumeName,
      ...(resumeId ? { resume_id: resumeId } : {}),
    }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["material-agent-proposals", jobId] }),
  });
  const resolve = useMutation({
    mutationFn: ({ proposal, resolution }: { proposal: MaterialAgentProposal; resolution: "confirmed" | "rejected" }) => resolveMaterialAgentProposal(proposal, resolution),
    onSuccess: async proposal => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["material-agent-proposals", jobId] }),
        client.invalidateQueries({ queryKey: ["materials"] }),
        client.invalidateQueries({ queryKey: ["resume-series"] }),
      ]);
      if (proposal.material_draft_id) navigate(`/materials/${proposal.material_draft_id}`);
    },
  });
  const job = jobs.data?.items.find(item => item.id === jobId);
  const activeDirection = directions.data?.selections.find(item => item.status === "active");
  const jobReady = Boolean(job?.requirement_count && job.latest_analysis);
  const disabledReason = !jobReady
    ? "岗位尚未完成有效分析，请先返回岗位详情重新分析。"
    : !activeDirection
      ? "请先在岗位详情选择并确认简历方向。"
      : !resumeId && !resumeName.trim()
        ? "选择已有简历，或填写新简历名称。"
        : null;
  const jobMaterials = materials.data?.items.filter(item => item.job_post_id === jobId) ?? [];
  return <><header className="page-header"><div><p className="eyebrow">岗位申请材料</p><h1>{job ? `${job.company} · ${job.title}` : "岗位材料"}</h1><p>这里只处理当前岗位的简历选择与定制，不会改写简历库中的上游版本。</p></div><span className="health-pill ok">{jobMaterials.length} 份</span></header>
    <section className="panel material-create"><div><p className="eyebrow">Agent 定制 · 需要确认</p><h2>选择来源并生成岗位版本</h2><p>可以从已有简历开始，也可以基于已确认职业事实新建一份。Agent 会结合岗位要求和已确认方向生成候选。</p></div><div className="form-grid"><label>来源简历<select value={resumeId} onChange={event => setResumeId(event.target.value)}><option value="">不使用已有版本，创建新简历</option>{resumes.data?.items.map(resume => <option value={resume.id} key={resume.id} disabled={!resume.latest_version}>{resume.name}{resume.latest_finalized_version ? ` · 定稿 v${resume.latest_finalized_version.version_number}` : " · 未定稿"}</option>)}</select></label>{!resumeId && <label>新简历名称<input value={resumeName} onChange={event => setResumeName(event.target.value)} placeholder="例如：某公司后端岗位简历" /></label>}<div className="wide">{activeDirection && <p className="form-hint">已确认方向：{activeDirection.selected_directions.map(item => item.name).join(" + ")}</p>}<button onClick={() => generate.mutate()} disabled={generate.isPending || Boolean(disabledReason)}>{generate.isPending ? "Agent 正在生成并检查…" : "生成岗位定制候选"}</button>{disabledReason && <p className="disabled-reason">{disabledReason} {!activeDirection && jobReady && <Link to={`/job-posts/${jobId}`}>返回选择方向</Link>}</p>}{generate.error && <p className="form-error">{generate.error.message}</p>}</div></div></section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">生成结果</p><h2>岗位定制候选</h2></div><span>{proposals.data?.items.filter(item => item.status === "proposed").length ?? 0} 待确认</span></div>{proposals.data?.items.map(proposal => <details className="resume-proposal" key={proposal.id} open={proposal.status === "proposed" ? true : undefined}><summary><span><strong>{proposal.content.title}</strong><small>{proposal.content.rationale}</small></span><span className={`health-pill ${proposal.review.verdict === "pass" ? "ok" : "blocked"}`}>{proposal.review.verdict === "pass" ? "检查通过" : "需要修订"}</span></summary><div className="resume-proposal-body">{proposal.content.blocks.map(block => <article className="finding info" key={block.blockId}><strong>{block.section}</strong><p>{block.text}</p><details><summary>查看引用依据</summary><small>职业事实：{block.factIds.join("、")} · 岗位要求：{block.requirementIds.join("、") || "无"}</small></details></article>)}{proposal.review.findings.map((finding, index) => <div className={`finding ${finding.severity}`} key={`${finding.code}-${index}`}><strong>{finding.severity === "error" ? "阻断" : "提醒"} · {finding.code}</strong><p>{finding.message}</p></div>)}{proposal.status === "proposed" && <div className="button-row"><button className="secondary" onClick={() => resolve.mutate({ proposal, resolution: "rejected" })}>拒绝</button><button onClick={() => resolve.mutate({ proposal, resolution: "confirmed" })} disabled={proposal.review.verdict !== "pass" || resolve.isPending}>确认并创建岗位材料</button></div>}</div></details>)}{!proposals.data?.items.length && <p>尚无岗位定制候选。生成后先在这里核对，再写入申请材料。</p>}</section>
    <section className="job-list material-list">{jobMaterials.map(item => <Link className="panel job-card" to={`/materials/${item.id}`} key={item.id}><div><span className="category-tag">{TYPE_LABELS[item.material_type]}</span><h2>{item.name}</h2><p>岗位定制版本 v{item.current_version_number}</p></div><span className={`health-pill ${!item.strategy_stale && (item.status === "final" || item.status === "reviewed") ? "ok" : "blocked"}`}>{item.strategy_stale ? "需要重新检查" : STATUS_LABELS[item.status]}</span></Link>)}</section>
  </>;
}

export function ResumeDetailPage() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["resume", id], queryFn: () => getResume(id), enabled: Boolean(id) });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["resume", id] }),
      client.invalidateQueries({ queryKey: ["resume-series"] }),
    ]);
  };
  const review = useMutation({ mutationFn: () => reviewResume(id), onSuccess: refresh });
  const finalize = useMutation({ mutationFn: (resume: ResumeDetail) => finalizeResume(resume), onSuccess: refresh });
  if (query.isLoading) return <section className="empty-state"><p>正在读取简历版本…</p></section>;
  if (query.error || !query.data) return <section className="notice error">{query.error?.message ?? "简历不存在"}</section>;
  const resume = query.data;
  return <><header className="page-header"><div><p className="eyebrow">{resume.series_type === "base" ? "基础简历" : "方向简历"}</p><h1>{resume.name}</h1><p>这里维护可复用简历本身。岗位匹配与岗位定制不会在此页面执行。</p></div><span className={`health-pill ${resume.current_version.status === "draft" ? "blocked" : "ok"}`}>{STATUS_LABELS[resume.current_version.status] ?? resume.current_version.status}</span></header>
    <section className="metric-grid"><article><span>当前版本</span><strong>v{resume.current_version.version_number}</strong><small>{formatChinaTime(resume.current_version.created_at)}（北京时间）</small></article><article><span>内容块</span><strong>{resume.current_version.blocks.length}</strong><small>均保留事实快照</small></article><article><span>复核</span><strong>{resume.review?.error_count ?? 0} 错误</strong><small>{resume.review?.warning_count ?? 0} 条提醒</small></article><article><span>导出</span><strong>{resume.export ? `${resume.export.page_count} 页` : "未生成"}</strong><small>{resume.export ? "PDF 已验证" : "定稿后生成"}</small></article></section>
    {resume.review?.findings.length ? <section className="panel findings"><div className="panel-heading"><h2>复核发现</h2><span>{resume.review.findings.length} 项</span></div>{resume.review.findings.map(item => <div className={`finding ${item.severity}`} key={item.id}><strong>{item.severity === "error" ? "阻断" : "提醒"} · {item.code}</strong><p>{item.message}</p></div>)}</section> : <section className="notice success">当前版本未发现事实支持问题。</section>}
    <ResumeEditor resume={resume} onSaved={refresh} />
    {resume.current_version.status !== "final" && <section className="panel final-actions"><div><h2>复核并定稿</h2><p>定稿后当前版本不可修改，并生成经过文本层和页面渲染检查的 PDF。</p></div><div><button className="secondary" onClick={() => review.mutate()} disabled={review.isPending}>{review.isPending ? "正在复核…" : "重新复核"}</button><button onClick={() => finalize.mutate(resume)} disabled={finalize.isPending || Boolean(resume.review?.error_count)}>{finalize.isPending ? "正在导出…" : "确认定稿并导出 PDF"}</button></div>{(review.error || finalize.error) && <p className="form-error">{review.error?.message ?? finalize.error?.message}</p>}</section>}
    {resume.export && <section className="panel export-result"><div><p className="eyebrow">已验证 PDF</p><h2>可复用导出物</h2><p>{(resume.export.size_bytes / 1024).toFixed(1)} KB · {resume.export.page_count} 页 · 文本层 {resume.export.text_layer_ok ? "通过" : "失败"} · 渲染 {resume.export.render_ok ? "通过" : "失败"}</p><a className="download-button" href={resume.export.download_url}>下载 PDF</a></div><img src={resume.export.preview_url} alt={`${resume.name} PDF 第一页预览`} /></section>}
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

function ResumeEditor({ resume, onSaved }: { resume: ResumeDetail; onSaved: () => Promise<void> }) {
  const [values, setValues] = useState(() => Object.fromEntries(resume.current_version.blocks.map(block => [block.id, block.text])));
  const edit = useMutation({
    mutationFn: () => editResume(
      resume,
      resume.current_version.blocks.map(block => ({ id: block.id, text: values[block.id] ?? block.text })),
    ),
    onSuccess: onSaved,
  });
  const final = resume.current_version.status === "final";
  return <section className="panel material-editor"><div className="panel-heading"><div><p className="eyebrow">简历正文</p><h2>{final ? "已定稿内容" : "编辑当前版本"}</h2></div><span>{resume.current_version.blocks.length} 条</span></div>{resume.current_version.blocks.map(block => <article className="material-block" key={block.id}><strong>{block.section}</strong>{final ? <div className="readonly-material">{block.text}</div> : <textarea aria-label={`${block.section}内容`} rows={3} value={values[block.id] ?? block.text} onChange={event => setValues(previous => ({ ...previous, [block.id]: event.target.value }))} />}<details><summary>事实依据（{block.fact_snapshots.length}）</summary>{block.fact_snapshots.map(fact => <blockquote key={fact.id}>{fact.value}<small>{fact.category} · {fact.field_key} · 事实版本 {fact.fact_version}</small></blockquote>)}</details></article>)}{!final && <button onClick={() => edit.mutate()} disabled={edit.isPending}>{edit.isPending ? "保存并复核中…" : "保存为新版本并复核"}</button>}{edit.error && <p className="form-error">{edit.error.message}</p>}</section>;
}
