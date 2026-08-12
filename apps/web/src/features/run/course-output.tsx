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
import { EmptyState, Markdown } from "../../components/common";
import { GenerationTimingPanel } from "./activity";
import { chapterQualityMap, effectiveCharCount } from "./batch-data";
import { authoritativeEffectiveChars } from "./quality-metrics";

export function CourseArticlePreview({
  slug,
  run,
  selectedKey,
  onSelect,
}: {
  slug: string;
  run: RunDetail;
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  const { data: course, isLoading: isCourseLoading, error: courseError } = useQuery({
    queryKey: ["course", slug, "article-preview"],
    queryFn: () => api.course(slug),
    refetchInterval: ["RUNNING", "WAITING_APPROVAL"].includes(run.status) || run.current_step === "quality" ? 1200 : false,
  });
  const selectedNumber = Number(selectedKey);
  const selectedLesson = course?.lessons.find((lesson) => lesson.markdown === selectedKey)
    || (Number.isFinite(selectedNumber)
      ? course?.lessons.find((lesson) => lesson.number === selectedNumber)
      : undefined)
    // While a batch is live, make the newest saved chapter the default. It is
    // the one a reader just saw in the current generation trace.
    || (run.status === "RUNNING" ? course?.lessons.at(-1) : course?.lessons[0]);
  useEffect(() => {
    if (selectedLesson && selectedLesson.markdown !== selectedKey) {
      onSelect(selectedLesson.markdown);
    }
  }, [onSelect, selectedKey, selectedLesson]);
  const { data: chapter, isLoading: isChapterLoading, error: chapterError } = useQuery({
    queryKey: ["course-article", slug, selectedLesson?.markdown],
    queryFn: () => api.chapter(slug, selectedLesson!.markdown),
    enabled: Boolean(selectedLesson?.markdown),
    refetchInterval: ["RUNNING", "WAITING_APPROVAL"].includes(run.status) || run.current_step === "quality" ? 1200 : false,
  });
  if (isCourseLoading) {
    return <EmptyState icon={<LoaderCircle className="spin" />} text="正在读取已生成的课程文章" />;
  }
  if (courseError) {
    return <div className="error-banner">{courseError.message}</div>;
  }
  if (!course?.lessons.length) {
    return <section className="course-article-preview tab-content">
      <GenerationTimingPanel events={run.events} />
      <EmptyState icon={<FileText />} text="课程文章会在第一个批次生成后出现在这里" />
    </section>;
  }
  return (
    <section className="course-article-preview tab-content">
      <div className="article-preview-heading">
        <div>
          <span className="side-label">COURSE ARTICLE · READ ONLY</span>
          <h2>课程文章预览</h2>
          <p>这里仅用于阅读已生成的正文。质量建议和重写请求请回到“当前节点”提交。</p>
        </div>
        <span>{course.chapter_count} 个章节</span>
      </div>
      <CourseQualityOverview
        lessons={course.lessons}
        run={run}
        snapshot={course.course_quality_snapshot || run.course_quality_snapshot}
        selectedMarkdown={selectedLesson?.markdown}
        onSelect={onSelect}
      />
      <nav className="article-chapter-nav" aria-label="课程章节导航">
        {course.lessons.map((lesson) => (
          <button
            key={lesson.markdown}
            className={lesson.markdown === selectedLesson?.markdown ? "active" : ""}
            onClick={() => onSelect(lesson.markdown)}
          >
            <span>第 {lesson.number} 章</span>
            <strong>{lesson.title}</strong>
          </button>
        ))}
      </nav>
      <article className="course-article-reader">
        {isChapterLoading ? (
          <EmptyState icon={<LoaderCircle className="spin" />} text="正在加载章节正文" />
        ) : chapterError ? (
          <div className="error-banner">{chapterError.message}</div>
        ) : chapter ? (
          <>
            <ChapterQualityPanel
              chapter={chapter}
              run={run}
              snapshot={course.course_quality_snapshot || run.course_quality_snapshot}
            />
            <div className="article-reader-meta">
              <span>{chapter.path}</span>
              <span>只读预览</span>
            </div>
            <Markdown content={chapter.content} courseSlug={run.course_slug} />
          </>
        ) : null}
      </article>
      <GenerationTimingPanel events={run.events} />
    </section>
  );
}

export function CourseQualityOverview({
  lessons,
  run,
  snapshot,
  selectedMarkdown,
  onSelect,
}: {
  lessons: Array<{ number: number; title: string; markdown: string }>;
  run: RunDetail;
  snapshot?: import("../../api").CourseQualitySnapshot;
  selectedMarkdown?: string;
  onSelect: (markdown: string) => void;
}) {
  const qualityMap = useMemo(() => chapterQualityMap(run, snapshot), [run, snapshot]);
  return (
    <section className="course-quality-overview" aria-label="全课程质量概览">
      <div className="course-quality-overview-heading">
        <span className="side-label">COURSE QUALITY OVERVIEW</span>
        <strong>所有章节质量状态</strong>
        <small>{snapshot?.revision ? `质量快照更新于 ${new Date(snapshot.revision).toLocaleTimeString()}` : "点击章节可直接预览正文"}</small>
      </div>
      {snapshot?.course_integration?.passed === false && (
        <p className="course-quality-integration-alert">
          整课构建 / 确定性检查尚未通过：章节门禁可单独达标，但课程尚不能进入发布。请以整课质量闭环中的构建诊断为准。
        </p>
      )}
      {snapshot?.source_contract_gate?.passed === false && (
        <p className="course-quality-contract-alert">
          章节内容门可以独立通过，但 Markdown 结构门仍有 {snapshot.source_contract_gate.diagnostics?.length || 0} 项待修复；当前不会读取旧 HTML 作为质量事实。
        </p>
      )}
      <div className="course-quality-overview-grid">
        {lessons.map((lesson) => {
          const quality = qualityMap.get(lesson.number);
          const charMin = quality?.effectiveCharMin ?? Number(run.request?.effective_char_min ?? 12000);
          const chars = quality?.effectiveChars;
          const charsPassed = typeof chars === "number" ? chars >= charMin : undefined;
          const humanizerPassed = typeof quality?.humanizerScore === "number"
            ? quality.humanizerScore >= 45
            : undefined;
          const semanticPassed = quality?.semanticDecision === "ready";
          const passed = quality?.passed ?? (charsPassed === true && humanizerPassed === true && semanticPassed);
          const integrationFailed = quality?.integrationPassed === false;
          const sourceContractFailed = snapshot?.source_contract_gate?.passed === false;
          return (
            <button
              type="button"
              key={lesson.markdown}
              onClick={() => onSelect(lesson.markdown)}
              className={`${lesson.markdown === selectedMarkdown ? "active " : ""}${passed ? "passed" : quality ? "failed" : "pending"}`}
            >
              <span>第 {lesson.number} 章</span>
              <strong title={lesson.title}>{lesson.title}</strong>
              <small>有效字符 {typeof chars === "number" ? chars.toLocaleString() : "—"} / {charMin.toLocaleString()}</small>
              <em>语言 {typeof quality?.humanizerScore === "number" ? `${quality.humanizerScore}/50` : "—"} · 语义 {quality?.semanticDecision || "—"}</em>
              <b>{passed
                ? sourceContractFailed ? "章节内容门通过 · Markdown 结构门待修复" : integrationFailed ? "章节通过 · 批次构建待修复" : "章节通过"
                : integrationFailed ? "章节待修复 · 批次构建待修复" : quality ? "章节待修复" : "待质检"}</b>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function ChapterQualityPanel({
  chapter,
  run,
  snapshot,
}: {
  chapter: import("../../api").Chapter;
  run: RunDetail;
  snapshot?: import("../../api").CourseQualitySnapshot;
}) {
  const qualityMap = useMemo(() => chapterQualityMap(run, snapshot), [run, snapshot]);
  const quality = qualityMap.get(chapter.number);
  const liveChars = chapter.content ? effectiveCharCount(chapter.content) : 0;
  const effectiveChars = authoritativeEffectiveChars(quality?.effectiveChars, liveChars);
  const charMin = quality?.effectiveCharMin ?? Number(run.request?.effective_char_min ?? 12000);
  const humanizerScore = quality?.humanizerScore;
  const semanticDecision = quality?.semanticDecision;
  const charPassed = effectiveChars >= charMin;
  const humanizerPassed = typeof humanizerScore === "number" ? humanizerScore >= 45 : undefined;
  const semanticPassed = semanticDecision === "ready";
  return (
    <section className="chapter-quality-panel" aria-label="本章质量指标">
      <div className="chapter-quality-heading">
        <span className="side-label">CHAPTER QUALITY</span>
        <strong>第 {chapter.number} 章质量指标</strong>
        {quality?.updatedAt && <small>快照更新：{new Date(quality.updatedAt).toLocaleTimeString()}</small>}
      </div>
      <div className="chapter-quality-grid">
        <div className={`quality-metric ${charPassed ? "passed" : "failed"}`}>
          <small>有效字符</small>
          <strong>{effectiveChars.toLocaleString()}<span> / {charMin.toLocaleString()}</span></strong>
          <em>{charPassed ? "达标" : "未达标"}</em>
        </div>
        <div className={`quality-metric ${humanizerPassed === true ? "passed" : humanizerPassed === false ? "failed" : "unknown"}`}>
          <small>Humanizer 语言门</small>
          <strong>{typeof humanizerScore === "number" ? `${humanizerScore}<span> / 50</span>` : "—"}</strong>
          <em>{humanizerPassed === undefined ? "暂无评分" : humanizerPassed ? "达标（≥45）" : "未达标"}</em>
        </div>
        <div className={`quality-metric ${semanticDecision ? (semanticPassed ? "passed" : "failed") : "unknown"}`}>
          <small>语义审校门</small>
          <strong>{semanticDecision === "ready" ? "ready" : semanticDecision || "—"}</strong>
          <em>{!semanticDecision ? "暂无结论" : semanticPassed ? "达标" : "未通过"}</em>
        </div>
        <div className="quality-metric info">
          <small>确定性硬检查</small>
          <strong>{quality?.integrationPassed === true ? "ready" : quality?.integrationPassed === false ? "failed" : "批次级"}</strong>
          <em>{quality?.integrationPassed === true ? "构建与链接检查通过" : quality?.integrationPassed === false ? "构建或链接检查未通过" : "构建与链接检查随批次运行"}</em>
        </div>
        <div className={`quality-metric ${snapshot?.source_contract_gate?.passed === true ? "passed" : snapshot?.source_contract_gate?.passed === false ? "failed" : "unknown"}`}>
          <small>Markdown 结构门</small>
          <strong>{snapshot?.source_contract_gate?.passed === true ? "ready" : snapshot?.source_contract_gate?.passed === false ? "failed" : "—"}</strong>
          <em>{snapshot?.source_contract_gate?.passed === false ? `${snapshot.source_contract_gate.diagnostics?.length || 0} 项结构诊断待处理` : snapshot?.source_contract_gate?.passed ? "源文件契约通过" : "等待整课源文件扫描"}</em>
        </div>
        <div className={`quality-metric ${snapshot?.build_gate?.passed === true ? "passed" : snapshot?.build_gate?.passed === false ? "failed" : "unknown"}`}>
          <small>当前修订构建门</small>
          <strong>{snapshot?.build_gate?.passed === true ? "ready" : snapshot?.build_gate?.passed === false ? "failed" : "—"}</strong>
          <em>{snapshot?.build_gate?.passed ? "HTML 已从当前 Markdown 构建" : "结构门通过后才允许构建"}</em>
        </div>
        <div className={`quality-metric ${snapshot?.artifact_gate?.passed === true ? "passed" : snapshot?.artifact_gate?.passed === false ? "failed" : "unknown"}`}>
          <small>构建产物门</small>
          <strong>{snapshot?.artifact_gate?.passed === true ? "ready" : snapshot?.artifact_gate?.passed === false ? "failed" : "—"}</strong>
          <em>{snapshot?.artifact_gate?.passed === null ? "未扫描旧 HTML" : snapshot?.artifact_gate?.passed ? "导航、资源与链接通过" : "等待当前 build revision"}</em>
        </div>
        <div className="quality-metric info">
          <small>整课集成 / 修复</small>
          <strong>{quality?.courseIntegrationPassed === true ? "ready" : quality?.courseIntegrationPassed === false ? "pending" : quality?.repairStatus || "—"}</strong>
          <em>{quality?.courseIntegrationPassed === false ? "整课构建待处理，不影响本章门禁结论" : quality?.repairStatus ? `RepairTask：${quality.repairStatus}` : "等待整课复检"}</em>
        </div>
      </div>
    </section>
  );
}
