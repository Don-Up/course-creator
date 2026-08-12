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
  ToolResult,
  WorkspaceFile,
} from "../../api";
import { allBatchOutputs, chapterQualityMap, type BatchOutput, type ChapterQualityInfo } from "./batch-data";
export function BatchReviewPanel({
  batch,
  feedback,
  onFeedbackChange,
  reviewEnabled,
  running,
  label,
  onOpenArticle,
}: {
  batch: BatchOutput;
  feedback: string;
  onFeedbackChange: (value: string) => void;
  reviewEnabled: boolean;
  running: boolean;
  label?: string;
  onOpenArticle: (path: string) => void;
}) {
  return (
    <div className="batch-review-panel">
      <div className="batch-review-heading">
        <div>
          <strong>{label || `批次 ${batch.batch.id}`} · 章节预览</strong>
          <small>{batch.live ? "当前正在处理本批；章节完成后会立即写入课程文章预览。" : batch.passed ? "本批已通过，将自动进入下一批" : "Agent 正在依据质量报告自动返工"}</small>
        </div>
        <span className={`batch-result ${batch.passed ? "passed" : "repairing"}`}>
          {batch.passed ? "已通过" : running ? (batch.live ? "生成中" : "修复中") : "待人工建议"}
        </span>
      </div>
      <div className="batch-chapter-summary" aria-label="本批次章节">
        {batch.chapters.map((item) => (
          <button
            key={item.path}
            onClick={() => item.persisted && onOpenArticle(item.path)}
            disabled={!item.persisted}
          >
            <span>第 {item.chapter} 章</span>
            <strong>{item.title}</strong>
            <small>{item.passed ? "通过 · 查看全文" : item.persisted ? "正文已落盘 · 查看全文" : "等待或处理中"}</small>
          </button>
        ))}
      </div>
      {!batch.passed && !batch.live && (
        <div className="batch-open-issues">
          <strong>本批次待处理项</strong>
          {batch.chapters.flatMap((item) => (item.issues || []).map((issue) => ({ chapter: item.chapter, issue }))).length ? (
            <ul>
              {batch.chapters.flatMap((item) => (item.issues || []).map((issue) => ({ chapter: item.chapter, issue }))).slice(0, 12).map((item, index) => (
                <li key={`${item.chapter}-${index}`}>第 {item.chapter} 章：{item.issue}</li>
              ))}
            </ul>
          ) : <p>存在未通过的质量门，详细证据已写入本批次质量报告。</p>}
        </div>
      )}
      <p className="batch-article-hint">{batch.live ? "已落盘章节可直接打开全文；其余章节会随生成进度出现。" : "点击章节卡片，在“课程文章”中以全宽阅读模式预览正文；本区域只保留批次状态与修改操作。"}</p>
      {reviewEnabled ? (
        <div className="batch-feedback">
          <label htmlFor="batch-feedback">批次修改建议</label>
          <textarea
            id="batch-feedback"
            value={feedback}
            onChange={(event) => onFeedbackChange(event.target.value)}
            placeholder="指出需要保留、补充或调整的内容。建议会与质量报告一并送入下一轮定向返工。"
          />
        </div>
      ) : (
        <p className="batch-auto-note">
          {running
            ? "本批内容可随时预览；Agent 会继续自动处理下一批或当前返工。"
            : "本批记录已保留；需要改写时可在课程完成后发起章节 Review。"}
        </p>
      )}
    </div>
  );
}

export function CourseQualityReviewPanel({ output, repairTasks = [] }: { output: unknown; repairTasks?: NonNullable<RunDetail["repair_tasks"]> }) {
  const report = output && typeof output === "object"
    ? output as {
      status?: string;
      message?: string;
      summary?: {
        batch_count?: number;
        unresolved_batch_count?: number;
        unresolved_chapter_count?: number;
        course_quality_passed?: boolean;
      };
      repair_scope?: string;
      user_direction?: string;
      completed_repair_round?: number;
      previous_repair_result?: {
        round?: number;
        repaired_count?: number;
        remaining_count?: number;
        build_succeeded?: boolean;
        validation_succeeded?: boolean;
        chapters?: Array<{
          chapter?: number;
          passed?: boolean;
          remaining_issues?: string[];
        }>;
      } | null;
      unresolved?: Array<{
        batch?: { display_label?: string; id?: string; chapter_numbers?: number[] };
        batch_integration_failed?: boolean;
        chapters?: Array<{
          chapter?: number;
          title?: string;
          issues?: string[];
          repair_agents?: string[];
        }>;
      }>;
    }
    : {};
  if (!Array.isArray(report.unresolved)) {
    return <div className="course-quality-review-panel pending">
      <strong>整课质量 Review 尚未运行</strong>
      <p>{report.message || "系统会先汇总全部批次的最新质量证据，再生成待修复章节清单。"}</p>
      <small>不会重新生成课程正文，也不会把历史批次建议当作本阶段输入。</small>
    </div>;
  }
  const summary = report.summary || {};
  const previousRound = report.previous_repair_result;
  const openTasks = repairTasks.filter((task) => !["fixed_verified", "fixed_static_only", "stale_evidence", "advisory_accepted"].includes(task.status));
  return <div className="course-quality-review-panel">
    <div className="course-quality-review-heading">
      <div>
        <span className="side-label">COURSE QUALITY REVIEW</span>
        <strong>{summary.course_quality_passed ? "整课质量门已全部通过" : "整课 Review：待定向修复清单"}</strong>
      </div>
      <span>{summary.unresolved_chapter_count ?? 0} 章待处理</span>
    </div>
    {previousRound && (
      <section className="quality-round-result">
        <div>
          <strong>第 {previousRound.round ?? report.completed_repair_round} 轮修复后复检结果</strong>
          <span>下方清单仅展示本轮结束后仍未关闭的问题，不是上一轮的原始待办。</span>
        </div>
        <dl>
          <div><dt>本轮通过</dt><dd>{previousRound.repaired_count ?? 0} 章</dd></div>
          <div><dt>章节问题残留</dt><dd>{previousRound.remaining_count ?? 0} 章</dd></div>
          <div><dt>整课构建</dt><dd>{previousRound.build_succeeded ? "通过" : "未通过"}</dd></div>
        </dl>
      </section>
    )}
    <p className="course-quality-scope">{report.repair_scope || "仅修复未达标章节；已通过正文保持不变。"}</p>
    {repairTasks.length > 0 && (
      <section className="repair-task-summary" aria-label="RepairTask 状态">
        <header><strong>证据驱动修复任务</strong><span>{openTasks.length} 项未关闭</span></header>
        {repairTasks.slice(0, 12).map((task) => (
          <article key={task.id} className={`repair-task ${task.status}`}>
            <div><strong>第 {task.chapter ?? "—"} 章 · {task.category}</strong><small>{task.batch_id || "整课"} · 已尝试 {task.attempt_count} 次</small></div>
            <span>{task.status === "fixed_verified" ? "已验证" : task.status === "needs_runtime_verification" ? "待运行验证" : task.status === "human_decision_required" ? "需人工确认" : "待定向修复"}</span>
            <p>{friendlyQualityIssue(task.issue)}</p>
          </article>
        ))}
      </section>
    )}
    {report.user_direction && <p className="course-quality-direction">已纳入本轮方向：{report.user_direction}</p>}
    {!report.unresolved.length ? <p className="course-quality-empty">没有待修复章节，可以确认进入整课验收。</p> : (
      <div className="course-quality-list">
        {report.unresolved.map((batch, index) => (
          <section key={`${batch.batch?.id || index}`}>
            <header>
              <strong>{batch.batch?.display_label || (() => {
                const numbers = batch.batch?.chapter_numbers || [];
                return numbers.length
                  ? `批次 ${index + 1} · 第 ${numbers[0]}${numbers.length > 1 ? `–${numbers[numbers.length - 1]}` : ""} 章`
                  : `批次 ${index + 1}`;
              })()}</strong>
              {batch.batch_integration_failed && <span>构建 / 硬检查待修复</span>}
            </header>
            {(batch.chapters || []).map((chapter) => (
              <article key={`${chapter.chapter}-${chapter.title}`}>
                <strong>第 {chapter.chapter} 章 · {chapter.title}</strong>
                <p>{(chapter.issues || []).slice(0, 3).map(friendlyQualityIssue).join("；") || "批次集成检查未通过，需要复核本章关联产物。"}</p>
                <small>计划调用：{(chapter.repair_agents || ["确定性构建 / 格式修复工具"]).join(" → ")}</small>
              </article>
            ))}
          </section>
        ))}
      </div>
    )}
  </div>;
}

export function qualityReviewHasOpenIssues(output: unknown): boolean {
  if (!output || typeof output !== "object") return false;
  const unresolved = (output as { unresolved?: unknown }).unresolved;
  return Array.isArray(unresolved) && unresolved.length > 0;
}

export type ReleaseReviewReport = {
  course?: { slug?: string; title?: string; status?: string; chapter_count?: number; planned_chapter_count?: number };
  request?: { audience?: string; goals?: string; scope?: string; source_policy?: string; effective_char_min?: number };
  production?: {
    batch_count?: number; chapter_generated?: number; change_request_count?: number;
    quality_repair_rounds?: number;
    repair_round_summaries?: Array<{ round?: number; repaired_count?: number; remaining_count?: number; build_succeeded?: boolean; validation_succeeded?: boolean }>;
  };
  quality?: {
    gates?: Array<{ batch?: string; language_volume?: boolean; semantic?: boolean; integration?: boolean; passed?: boolean }>;
    chapter_metrics?: Array<{ chapter?: number; title?: string; humanizer_score?: number; effective_chars?: number; effective_char_min?: number; semantic_decision?: string; passed?: boolean }>;
    unresolved?: Array<{ chapters?: Array<{ chapter?: number; title?: string; issues?: string[] }> }>;
    unresolved_chapter_count?: number;
    course_quality_passed?: boolean;
  };
  operations?: { model_operation_events?: number; timed_operation_count?: number; total_operation_seconds?: number; event_count?: number };
};

export function asReleaseReview(output: unknown): ReleaseReviewReport | null {
  if (!output || typeof output !== "object") return null;
  const review = (output as { release_review?: unknown }).release_review;
  if (!review || typeof review !== "object") return null;
  return review as ReleaseReviewReport;
}

export function releaseReviewReady(output: unknown): boolean {
  return Boolean(asReleaseReview(output));
}

export function ReleaseReviewPanel({ output }: { output: unknown }) {
  const review = asReleaseReview(output);
  if (!review) {
    return <div className="course-quality-review-panel pending">
      <strong>整课总结尚未生成</strong>
      <p>点击下方"重新生成整课总结"按钮，系统会汇总各节点产物、生成轮次、质量门禁与剩余问题后，再交由你做发布决定。总结生成前无法发布课程。</p>
    </div>;
  }
  const flag = (value?: boolean) => value === undefined ? "—" : value ? "✓" : "✗";
  const production = review.production || {};
  const quality = review.quality || {};
  const operations = review.operations || {};
  const orderedGates = [...(quality.gates || [])].sort((left, right) => {
    const firstChapter = (value?: string) => Number(String(value || "").match(/(?:m\d+)?-?(\d+)-(\d+)/)?.[1] || Number.MAX_SAFE_INTEGER);
    return firstChapter(left.batch) - firstChapter(right.batch);
  });
  return <div className="course-quality-review-panel release-review-panel">
    <div className="course-quality-review-heading">
      <div>
        <span className="side-label">RELEASE REVIEW</span>
        <strong>{review.course?.title || "整课总结"}</strong>
      </div>
      <span>{quality.course_quality_passed ? "质量门全部通过" : `${quality.unresolved_chapter_count ?? 0} 章仍有遗留问题`}</span>
    </div>
    <dl className="release-summary-grid">
      <div><dt>章节</dt><dd>{review.course?.chapter_count ?? 0} / {review.course?.planned_chapter_count ?? "—"}</dd></div>
      <div><dt>生成批次</dt><dd>{production.batch_count ?? 0}</dd></div>
      <div><dt>已生成章节</dt><dd>{production.chapter_generated ?? 0}</dd></div>
      <div><dt>全局变更轮次</dt><dd>{production.change_request_count ?? 0}</dd></div>
      <div><dt>质量修复轮次</dt><dd>{production.quality_repair_rounds ?? 0}</dd></div>
      <div><dt>Agent 操作</dt><dd>{operations.timed_operation_count ?? 0} 次 / {operations.total_operation_seconds ?? 0}s</dd></div>
      <div><dt>模型产出事件</dt><dd>{operations.model_operation_events ?? 0}</dd></div>
      <div><dt>运行事件</dt><dd>{operations.event_count ?? 0}</dd></div>
    </dl>
    <p className="course-quality-scope">受众：{review.request?.audience || "—"} · 有效字符目标：{review.request?.effective_char_min ?? "—"} · 来源政策：{review.request?.source_policy || "—"}</p>
    {orderedGates.length > 0 && (
      <table className="release-gate-table">
        <thead><tr><th>批次</th><th>语言与篇幅</th><th>语义审校</th><th>集成构建</th><th>批次通过</th></tr></thead>
        <tbody>
          {orderedGates.map((gate, index) => (
            <tr key={gate.batch}>
              <td>{canonicalBatchDisplayId(gate.batch, index + 1)}</td>
              <td className={gate.language_volume ? "passed" : "failed"}>{flag(gate.language_volume)}</td>
              <td className={gate.semantic ? "passed" : "failed"}>{flag(gate.semantic)}</td>
              <td className={gate.integration ? "passed" : "failed"}>{flag(gate.integration)}</td>
              <td className={gate.passed ? "passed" : "failed"}>{flag(gate.passed)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
    {(quality.unresolved || []).length > 0 ? (
      <div className="course-quality-list">
        {(quality.unresolved || []).flatMap((batch) => (batch.chapters || [])).map((chapter) => (
          <section key={chapter.chapter}>
            <header><strong>第 {chapter.chapter} 章 · {chapter.title}</strong></header>
            <ul>{(chapter.issues || []).slice(0, 5).map((issue, index) => <li key={index}>{friendlyQualityIssue(issue)}</li>)}</ul>
          </section>
        ))}
      </div>
    ) : <p className="course-quality-empty">所有质量门禁已通过，可以放心发布。</p>}
  </div>;
}

export function friendlyQualityIssue(issue: string): string {
  const lines = issue.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const errorLine = lines.find((line) => line.startsWith("Error: courses/"));
  const message = errorLine?.replace(/^Error:\s*/, "")
    || lines.find((line) => line.startsWith("[ERROR]"))
    || lines[0]
    || issue;
  return message.length > 320 ? `${message.slice(0, 320)}…` : message;
}

export function canonicalBatchDisplayId(value: string | undefined, ordinal: number): string {
  const range = String(value || "").match(/(?:m\d+)?-?(\d+)-(\d+)/);
  if (!range) return `批次 ${ordinal}`;
  return `m${ordinal}-${range[1].padStart(2, "0")}-${range[2].padStart(2, "0")}`;
}
