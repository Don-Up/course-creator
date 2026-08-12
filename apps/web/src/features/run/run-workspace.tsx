import { FormEvent, ReactNode, isValidElement, useEffect, useId, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  CircleAlert,
  ChevronDown,
  FileText,
  FolderOpen,
  FilePenLine,
  GitBranch,
  Home,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Upload,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  api,
  Course,
  RunArtifact,
  RunDetail,
  RunEvent,
  BudgetSnapshot,
  TraceProjection,
  ToolResult,
  WorkspaceFile,
} from "../../api";
import { statusLabel } from "../../constants";
import { EmptyState, PageHeader, ToolOutput } from "../../components/common";
import { ResourceUploader, WorkspaceExplorer } from "../../components/workspace";
import { BatchReviewPanel, CourseQualityReviewPanel, ReleaseReviewPanel, qualityReviewHasOpenIssues, releaseReviewReady } from "./batch-panels";
import { activeBatchOutput, batchPresentation, latestBatchOutput } from "./batch-data";
import { BatchEventHistory } from "./batch-data";
import { CourseArticlePreview, CourseQualityOverview, ChapterQualityPanel } from "./course-output";
import { AgentOrchestrationGraph, WorkflowMap } from "./visuals";
import { NodeRunningStatus } from "./activity";
import { GenerationTimingPanel, LiveAgentActivity, QualityRepairHistory } from "./activity";
import { ArtifactTimeline, WorkflowRow } from "./artifacts";
import { ExecutionPanel } from "./execution-panel";
import { BudgetPanel, TracePanel } from "./observability-panels";
import { shouldPollRun } from "./run-polling";
export function RunWorkspace() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const [feedback, setFeedback] = useState("");
  const [selectedStepId, setSelectedStepId] = useState("");
  const [mainTab, setMainTab] = useState<"step" | "workspace" | "lessons" | "graph" | "trace">("step");
  const [workspaceRefreshToken, setWorkspaceRefreshToken] = useState(0);
  const [selectedArticleKey, setSelectedArticleKey] = useState("");
  const queryClient = useQueryClient();
  const { data: run, isLoading } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: (query) => shouldPollRun(query.state.data) ? 1200 : false,
  });
  const { data: budget } = useQuery<BudgetSnapshot>({ queryKey: ["run", runId, "budget"], queryFn: () => api.budget(runId), refetchInterval: shouldPollRun(run) ? 1200 : false });
  const { data: trace } = useQuery<TraceProjection>({ queryKey: ["run", runId, "trace"], queryFn: () => api.trace(runId), refetchInterval: shouldPollRun(run) ? 1200 : false });
  const isReviewRun = ["review_course", "regenerate_course"].includes(
    String(run?.request?.workflow_scope || run?.request?.scope || ""),
  );
  const { data: reviewedCourse } = useQuery({
    queryKey: ["course", run?.course_slug, "resume-check"],
    queryFn: () => api.course(run?.course_slug || ""),
    enabled: Boolean(run?.course_slug && isReviewRun),
  });
  useEffect(() => {
    if (reviewedCourse?.resumable_run_id && reviewedCourse.resumable_run_id !== runId) {
      navigate(`/runs/${reviewedCourse.resumable_run_id}`, { replace: true });
    }
  }, [navigate, reviewedCourse?.resumable_run_id, runId]);
  const resolveMutation = useMutation({
    mutationFn: (action: "APPROVE" | "REVISE" | "STOP") =>
      api.resolveRun(runId, action, feedback),
    onSuccess: () => {
      setFeedback("");
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
    },
  });
  const continueMutation = useMutation({
    mutationFn: () => api.continueRun(runId, feedback, run?.status),
    onSuccess: () => {
      setFeedback("");
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
    },
  });
  const stopMutation = useMutation({
    mutationFn: () => api.stopRun(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", runId] }),
  });
  useEffect(() => {
    if (!run?.current_step) return;
    setSelectedStepId(run.current_step);
    setMainTab("step");
  }, [run?.current_step]);
  if (isLoading || !run) {
    return <EmptyState icon={<LoaderCircle className="spin" />} text="正在读取 Agent Run" />;
  }
  if (reviewedCourse?.resumable_run_id && reviewedCourse.resumable_run_id !== runId) {
    return <EmptyState icon={<LoaderCircle className="spin" />} text="该课程尚未生成章节，正在返回创建 Workflow…" />;
  }
  const selectedStep =
    run.workflow_steps.find((step) => step.id === selectedStepId) ||
    run.workflow_steps.find((step) => step.id === run.current_step) ||
    run.workflow_steps[0];
  const isSelectedCurrent = selectedStep.id === run.current_step;
  const commandPending = Boolean(run.active_command);
  const isMutating = resolveMutation.isPending || continueMutation.isPending || stopMutation.isPending || commandPending;
  const latestBatch = latestBatchOutput(run);
  const activeBatch = run.status === "RUNNING" ? activeBatchOutput(run) : null;
  const displayedBatch = activeBatch || latestBatch;
  const displayedBatchPresentation = displayedBatch
    ? batchPresentation(run, displayedBatch.batch)
    : null;
  const isBatchReview = Boolean(
    isSelectedCurrent &&
      selectedStep.id === "generation" &&
      run.interrupt_payload,
  );
  return (
    <>
      <PageHeader
        eyebrow={`Run ${run.id.slice(0, 8)}`}
        title="课程 Workflow"
        description={`${run.course_slug} · ${run.provider}/${run.model}`}
        action={<span className={`run-status ${run.status.toLowerCase()}`}>{statusLabel[run.status] || run.status}</span>}
      />
      <div className="run-page-layout">
        <div className="run-main-content">
          <WorkflowMap
            steps={run.workflow_steps}
            currentStep={run.current_step}
            runStatus={run.status}
            selectedStep={selectedStep.id}
            onSelect={(id) => {
              setSelectedStepId(id);
              if (mainTab !== "graph") setMainTab("step");
            }}
          />
          <ExecutionPanel run={run} stopping={stopMutation.isPending} onStop={() => stopMutation.mutate()} />
          <BudgetPanel budget={budget} />
          <div className="run-workbench">
            <div className="run-content-tabs" role="tablist" aria-label="Workflow 内容">
              <button
                role="tab"
                aria-selected={mainTab === "step"}
                className={mainTab === "step" ? "active" : ""}
                onClick={() => setMainTab("step")}
              >
                当前节点
                <small>{selectedStep.title}</small>
              </button>
              <button
                role="tab"
                aria-selected={mainTab === "workspace"}
                className={mainTab === "workspace" ? "active" : ""}
                onClick={() => {
                  setWorkspaceRefreshToken((value) => value + 1);
                  setMainTab("workspace");
                }}
              >
                课程 Workspace
                <small>资料与上下文文件</small>
              </button>
              <button
                role="tab"
                aria-selected={mainTab === "lessons"}
                className={mainTab === "lessons" ? "active" : ""}
                onClick={() => setMainTab("lessons")}
              >
                课程文章
                <small>全宽只读预览</small>
              </button>
              <button
                role="tab"
                aria-selected={mainTab === "graph"}
                className={mainTab === "graph" ? "active" : ""}
                onClick={() => setMainTab("graph")}
              >
                Agent 编排图
                <small>LangGraph 有向循环</small>
              </button>
              <button role="tab" aria-selected={mainTab === "trace"} className={mainTab === "trace" ? "active" : ""} onClick={() => setMainTab("trace")}>
                统一 Trace
                <small>{trace?.spans.length || 0} 个 Span</small>
              </button>
            </div>
            {mainTab === "step" ? (
              <section className={`step-workspace tab-content ${selectedStep.status}`}>
              {selectedStep.status === "pending" ? (
                <div className="pending-step-message">
                  <span className="empty-dot" />
                  <div>
                    <strong>该节点尚未开始</strong>
                    <p>完成前序节点后，Agent 才会读取输入并生成本节点产物。</p>
                  </div>
                </div>
              ) : (
                <div className="step-columns">
                  <section className="step-input-panel">
                    <span className="side-label">USER INPUT</span>
                    {selectedStep.id === "generation" && displayedBatch ? (
                      <BatchReviewPanel
                        batch={displayedBatch}
                        feedback={feedback}
                        onFeedbackChange={setFeedback}
                        reviewEnabled={isBatchReview}
                        running={run.status === "RUNNING"}
                        label={displayedBatchPresentation?.label}
                        onOpenArticle={(path) => {
                          setSelectedArticleKey(path);
                          setMainTab("lessons");
                        }}
                      />
                    ) : selectedStep.id === "quality" && run.interrupt_payload ? (
                      <CourseQualityReviewPanel output={run.interrupt_payload.output} repairTasks={run.repair_tasks} />
                    ) : selectedStep.id === "release" && run.interrupt_payload ? (
                      <ReleaseReviewPanel output={run.interrupt_payload.output} />
                    ) : (
                      <p className="input-copy">{selectedStep.user_input}</p>
                    )}
                    {isSelectedCurrent && run.interrupt_payload ? (
                      <div className="approval-box">
                        <h3>{selectedStep.id === "generation" && displayedBatchPresentation
                          ? `${displayedBatchPresentation.label} 需要人工建议`
                          : run.interrupt_payload.title}</h3>
                        {selectedStep.id !== "generation" && (
                          <textarea
                            placeholder={selectedStep.id === "quality"
                              ? "可选：补充本轮定向修复建议。Agent 只会修改未通过质量门的章节，不会重写已通过正文。"
                              : "批准时可留空；要求修改时填写全局课程变更。Agent 会重算影响范围、同步任务定义/蓝图/规格/计划并执行一致性检查。"}
                            value={feedback}
                            disabled={isMutating}
                            onChange={(event) => setFeedback(event.target.value)}
                          />
                        )}
                        {isMutating && (
                          <div className="inline-running">
                            <LoaderCircle className="spin" size={15} />
                            正在提交意见并唤醒 Agent…
                          </div>
                        )}
                        <div className="button-row">
                          {selectedStep.id === "release" && (
                            <button className="button secondary" disabled={isMutating} onClick={() => continueMutation.mutate()}>
                              {continueMutation.isPending ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}
                              重新生成整课总结
                            </button>
                          )}
                          {selectedStep.id === "generation" && run.interrupt_payload.actions.includes("REVISE") && (
                            <button className="button primary" disabled={isMutating} onClick={() => continueMutation.mutate()}>
                              {continueMutation.isPending ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}
                              继续自动修复
                            </button>
                          )}
                          {run.interrupt_payload.actions.includes("STOP") && (
                            <button className="button secondary" disabled={isMutating} onClick={() => resolveMutation.mutate("STOP")}>停止</button>
                          )}
                          {(run.interrupt_payload.actions.includes("REVISE") || (selectedStep.id === "release" && releaseReviewReady(run.interrupt_payload.output))) && (
                            <button className="button secondary" disabled={isMutating || (!["generation", "quality", "release"].includes(selectedStep.id) && !feedback.trim())} onClick={() => resolveMutation.mutate("REVISE")}>
                              {selectedStep.id === "generation"
                                ? "提交建议并修复本批次"
                                : selectedStep.id === "quality"
                                  ? run.interrupt_payload.type === "COURSE_QUALITY_REVIEW_PENDING"
                                    ? "运行整课质量 Review"
                                    : "统一定向修复未达标章节"
                                  : selectedStep.id === "release"
                                    ? "返回质量闭环，继续修复"
                                  : "要求修改"}
                            </button>
                          )}
                          {(run.interrupt_payload.actions.includes("APPROVE") || (selectedStep.id === "release" && releaseReviewReady(run.interrupt_payload.output))) && (
                            <button className="button primary" disabled={isMutating || (selectedStep.id === "release" && !releaseReviewReady(run.interrupt_payload.output))} onClick={() => resolveMutation.mutate("APPROVE")}>
                              <Check size={16} />{selectedStep.id === "release"
                                ? "课程发布"
                                : selectedStep.id === "generation"
                                ? displayedBatchPresentation?.isFinal
                                  ? "进入整课质量闭环"
                                  : "暂不修复，生成下一批"
                                : selectedStep.id === "quality"
                                  ? qualityReviewHasOpenIssues(run.interrupt_payload.output)
                                    ? "保留剩余问题，进入整课确认"
                                    : "确认质量通过，进入整课确认"
                                : "确认并继续"}
                            </button>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="input-state-note">
                        {isSelectedCurrent && run.status === "RUNNING" ? (
                          <NodeRunningStatus step={selectedStep.id} events={run.events} />
                        ) : selectedStep.status === "completed" ? (
                          <><Check size={15} />本节点输入已处理</>
                        ) : null}
                      </div>
                    )}
                    {isSelectedCurrent && run.status === "FAILED" && (
                      <div className="resume-box">
                        <CircleAlert size={16} />
                        <span>执行意外中断，但最近的 LangGraph 检查点与已生成章节仍已保留。</span>
                        <button className="button primary compact" disabled={isMutating} onClick={() => continueMutation.mutate()}>
                          {continueMutation.isPending ? <LoaderCircle className="spin" size={14} /> : <Play size={14} />}
                          继续生成
                        </button>
                      </div>
                    )}
                    {["mission", "blueprint"].includes(selectedStep.id) && (
                      <ResourceUploader slug={run.course_slug} />
                    )}
                  </section>
                  <section className="step-output-panel">
                    <span className="side-label">MODEL OUTPUT · HISTORY</span>
                    {isSelectedCurrent && run.status === "RUNNING" && (
                      <LiveAgentActivity
                        step={selectedStep.id}
                        events={run.events}
                        onOpenArticle={(chapter) => {
                          setSelectedArticleKey(String(chapter));
                          setMainTab("lessons");
                        }}
                      />
                    )}
                    {selectedStep.id === "generation" && (
                      <GenerationTimingPanel events={run.events} compact />
                    )}
                    {selectedStep.id === "quality" && (
                      <QualityRepairHistory
                        events={run.events}
                        running={isSelectedCurrent && run.status === "RUNNING"}
                      />
                    )}
                    <ArtifactTimeline
                      artifacts={selectedStep.artifacts || []}
                      running={isSelectedCurrent && run.status === "RUNNING"}
                    />
                  </section>
                </div>
              )}
              </section>
            ) : mainTab === "workspace" ? (
              <WorkspaceExplorer
                slug={run.course_slug}
                embedded
                refreshToken={workspaceRefreshToken}
              />
            ) : mainTab === "lessons" ? (
              <CourseArticlePreview
                slug={run.course_slug}
                run={run}
                selectedKey={selectedArticleKey}
                onSelect={setSelectedArticleKey}
              />
            ) : mainTab === "trace" ? (
              <TracePanel trace={trace} />
            ) : (
              <AgentOrchestrationGraph run={run} selectedPhase={selectedStep.id} onPhaseChange={setSelectedStepId} />
            )}
          </div>
          {run.error_message && <div className="error-banner">{run.error_message}</div>}
          {resolveMutation.error && <div className="error-banner">{resolveMutation.error.message}</div>}
          {continueMutation.error && <div className="error-banner">{continueMutation.error.message}</div>}
          {stopMutation.error && <div className="error-banner">{stopMutation.error.message}</div>}
        </div>
        <aside className="event-panel event-dock">
          <div className="event-dock-heading">
            <span className="eyebrow">Run events</span>
            <h2>运行记录</h2>
            <small>{run.events.length} 条事件</small>
          </div>
          <BatchEventHistory run={run} />
        </aside>
      </div>
    </>
  );
}
