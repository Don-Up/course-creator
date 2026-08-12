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

import { batchEventLabel, batchEvents, eventDisplayMessage } from "./batch-data";
import { eventReason } from "./artifacts";

export function formatElapsed(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes} 分 ${String(seconds).padStart(2, "0")} 秒` : `${seconds} 秒`;
}

export type TimedGenerationEvent = RunEvent & {
  durationMs: number;
  chapter?: number;
  attempt?: number;
  failed: boolean;
  batchId?: string;
};

export function generationTimingEvents(events: RunEvent[]): TimedGenerationEvent[] {
  const batchByEvent = new Map(batchEvents(events).map((event) => [event.id, event.batchId]));
  return events.flatMap((event) => {
    const completed = event.event_type.endsWith(".completed");
    const failed = event.event_type.endsWith(".failed");
    const duration = event.payload?.duration_ms;
    if ((!completed && !failed) || typeof duration !== "number") return [];
    const chapter = event.payload?.chapter;
    const attempt = event.payload?.attempt;
    return [{
      ...event,
      durationMs: duration,
      chapter: typeof chapter === "number" ? chapter : undefined,
      attempt: typeof attempt === "number" ? attempt : undefined,
      failed,
      batchId: batchByEvent.get(event.id),
    }];
  });
}

export function GenerationTimingPanel({
  events,
  compact = false,
}: {
  events: RunEvent[];
  compact?: boolean;
}) {
  const stages = generationTimingEvents(events).sort(
    (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at),
  );
  const totalMs = stages.reduce((total, item) => total + item.durationMs, 0);
  const failures = stages.filter((item) => item.failed);
  const retries = events.filter((event) => event.event_type === "generation.chapter.retrying").length;
  if (!stages.length && !events.some((event) => event.step === "generation")) return null;
  const activeBatchId = batchEvents(events).at(-1)?.batchId;
  const activeStages = activeBatchId
    ? stages.filter((event) => event.batchId === activeBatchId)
    : stages;
  const displayed = compact ? activeStages.slice(0, 6) : stages;
  return (
    <section className={`generation-timing ${compact ? "compact" : ""}`}>
      <div className="generation-timing-heading">
        <div>
          <span className="side-label">AGENT PRODUCTION TRACE</span>
          <strong>{compact ? `${batchEventLabel(events, activeBatchId)} 耗时` : "完整 Agent 生成流程"}</strong>
        </div>
        <div className="timing-metrics">
          <span>已计时 {formatElapsed(totalMs)}</span>
          <span>{retries} 次修复</span>
          <span className={failures.length ? "failed" : "passed"}>{failures.length} 次失败</span>
        </div>
      </div>
      {!compact && <p>每一行均来自持久化 Run Event；中断后仍可追溯每章、每轮和每个质量步骤的实际耗时。</p>}
      <ol className="generation-trace-list">
        {displayed.map((event) => {
          const label = eventDisplayMessage(events, event).replace(/完成$|失败：.*$/, "");
          return (
            <li className={event.failed ? "failed" : "passed"} key={event.id}>
              <i />
              <div>
                <strong>{label}</strong>
                <small>
                  {event.chapter ? `第 ${event.chapter} 章` : "批次级"}
                  {event.batchId && !compact ? ` · ${batchEventLabel(events, event.batchId)}` : ""}
                  {event.attempt ? ` · 修复轮 ${event.attempt}` : ""}
                  {event.failed && typeof event.payload?.error === "string" ? ` · ${event.payload.error}` : ""}
                </small>
              </div>
              <time>{formatElapsed(event.durationMs)}</time>
            </li>
          );
        })}
        {!displayed.length && <li className="pending"><i /><span>等待第一个可计时步骤完成</span></li>}
      </ol>
    </section>
  );
}

export function ElapsedTimer({ startedAt }: { startedAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const started = Date.parse(startedAt);
  return <time className="agent-elapsed">本轮已运行 {Number.isNaN(started) ? "—" : formatElapsed(now - started)}</time>;
}

export function currentNodeStart(
  step: string,
  events: RunDetail["events"],
) {
  return [...events].reverse().find(
    (event) => event.step === step && event.event_type === "node.started",
  );
}

export function NodeRunningStatus({
  step,
  events,
}: {
  step: string;
  events: RunDetail["events"];
}) {
  const start = currentNodeStart(step, events);
  const latest = [...events].reverse().find((event) => event.step === step);
  return <>
    <LoaderCircle className="spin" size={15} />
    <span>{latest?.message || "Agent 正在处理本节点"}</span>
    {start && <ElapsedTimer startedAt={start.created_at} />}
  </>;
}

export function LiveAgentActivity({
  step,
  events,
  onOpenArticle,
}: {
  step: string;
  events: RunDetail["events"];
  onOpenArticle?: (chapter: number) => void;
}) {
  const relevantEvents = [...events]
    .filter(
      (event) =>
        event.step === step &&
        (event.event_type.startsWith("generation.") ||
          event.event_type.startsWith("quality.repair.") ||
          event.event_type === "node.started" ||
          event.event_type === "run.heartbeat"),
    );
  const grouped = step === "generation" ? batchEvents(relevantEvents) : [];
  const activeBatchId = grouped.at(-1)?.batchId;
  const activeEvents = activeBatchId
    ? grouped.filter((event) => event.batchId === activeBatchId)
    : relevantEvents;
  // Heartbeats arrive every 15 seconds. Keep the latest one for its elapsed
  // signal, but do not let it hide the actual generation / review milestones.
  const latestHeartbeat = [...activeEvents]
    .reverse()
    .find((event) => event.event_type === "run.heartbeat");
  const processEvents = [
    ...(latestHeartbeat ? [latestHeartbeat] : []),
    ...activeEvents
      .filter((event) => event.event_type !== "run.heartbeat")
      .slice(-5)
      .reverse(),
  ];
  const completedChapters = [...new Set(
    activeEvents
      .filter((event) =>
        event.event_type === "generation.chapter.continuity" ||
        event.event_type === "generation.chapter.continuity.started" ||
        event.event_type === "generation.chapter.continuity.completed" ||
        event.event_type === "quality.repair.chapter.completed",
      )
      .map((event) => event.payload?.chapter)
      .filter((chapter): chapter is number => typeof chapter === "number"),
  )];
  const previousBatches = [...new Set(grouped.map((event) => event.batchId))]
    .filter((batch) => batch !== activeBatchId && batch !== "未归属批次")
    .reverse();
  const start = currentNodeStart(step, events);
  return (
    <section className="live-agent-activity" aria-live="polite">
      <div className="live-agent-heading">
        <span><LoaderCircle className="spin" size={14} />Agent 正在执行{activeBatchId && activeBatchId !== "未归属批次" ? ` · ${batchEventLabel(events, activeBatchId)}` : ""}</span>
        {start && <ElapsedTimer startedAt={start.created_at} />}
      </div>
      {completedChapters.length > 0 && (
        <div className="live-chapter-summary">
          <strong>本批已阶段性落盘</strong>
          <span>正文已保存，可在课程文章中预览：</span>
          {completedChapters.map((chapter) => (
            <button key={chapter} onClick={() => onOpenArticle?.(chapter)}>第 {chapter} 章</button>
          ))}
        </div>
      )}
      <ol>
        {processEvents.map((event, index) => (
          <li className={index === 0 ? "current" : ""} key={event.id}>
            <i />
            <span>
              {eventDisplayMessage(events, event)}
              {eventReason(event, activeEvents) && <small className="event-reason">原因：{eventReason(event, activeEvents)}</small>}
            </span>
            <time>{new Date(event.created_at).toLocaleTimeString()}</time>
          </li>
        ))}
      </ol>
      {previousBatches.length > 0 && (
        <details className="previous-batches">
          <summary>上一批次记录（{previousBatches.map((batch) => batchEventLabel(events, batch)).join("、")}）</summary>
          {previousBatches.map((batch) => {
            const records = grouped.filter((event) => event.batchId === batch);
            const last = records.at(-1);
            return <p key={batch}><strong>{batchEventLabel(events, batch)}</strong>{last ? `：${eventDisplayMessage(events, last)}` : "：无可展示事件"}</p>;
          })}
        </details>
      )}
    </section>
  );
}

export function QualityRepairHistory({
  events,
  running,
}: {
  events: RunDetail["events"];
  running: boolean;
}) {
  const repairEvents = events.filter(
    (event) =>
      event.step === "quality"
      && (event.event_type.startsWith("quality.repair.") || event.event_type.startsWith("recovery.supervisor."))
      && event.event_type !== "quality.repair.round.started",
  );
  const grouped = new Map<number, RunEvent[]>();
  for (const event of repairEvents) {
    const round = typeof event.payload?.repair_round === "number"
      ? event.payload.repair_round
      : 0;
    grouped.set(round, [...(grouped.get(round) || []), event]);
  }
  const rounds = [...grouped.entries()].sort(([left], [right]) => right - left);
  if (!rounds.length) return null;
  return (
    <section className="quality-repair-history">
      <div className="quality-repair-history-heading">
        <span className="side-label">REPAIR EXECUTION HISTORY</span>
        <small>过程记录永久保留 · 最新轮次置顶</small>
      </div>
      {rounds.map(([round, records], index) => {
        const completed = records.some(
          (event) => event.event_type === "quality.repair.round.completed",
        );
        const chapters = [...new Set(
          records
            .map((event) => event.payload?.chapter)
            .filter((chapter): chapter is number => typeof chapter === "number"),
        )];
        return (
          <details
            key={round || "legacy"}
            open={index === 0 && (round > 0 || running)}
            className="quality-repair-round"
          >
            <summary>
              <span>
                <strong>{round ? `第 ${round} 轮统一定向修复` : "历史定向修复记录"}</strong>
                <small>
                  {chapters.length ? `处理第 ${chapters.join("、")} 章 · ` : ""}
                  {completed ? "已完成" : running && index === 0 ? "执行中" : "已中断或待续"}
                </small>
              </span>
              <span>{records.length} 条</span>
            </summary>
            <ol>
              {[...records].reverse().map((event) => (
                <li key={event.id}>
                  <i className={event.event_type.endsWith(".failed") ? "failed" : ""} />
                  <span>
                    <strong>{event.message}</strong>
                    {Array.isArray(event.payload?.remaining_issues)
                      && event.payload.remaining_issues.length > 0
                      && <small>剩余：{event.payload.remaining_issues.join("；")}</small>}
                  </span>
                  <time>
                    {typeof event.payload?.duration_ms === "number"
                      ? formatElapsed(event.payload.duration_ms)
                      : new Date(event.created_at).toLocaleTimeString()}
                  </time>
                </li>
              ))}
            </ol>
          </details>
        );
      })}
    </section>
  );
}

