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

export type BatchChapterOutput = {
  chapter: number;
  title: string;
  path: string;
  passed: boolean;
  humanizer_score?: number;
  effective_chars?: number;
  effective_char_min?: number;
  deferred?: boolean;
  persisted?: boolean;
  issues?: string[];
  semantic_review?: { decision?: string; issues?: string[] };
  attempts?: Array<Record<string, unknown>>;
};

export type BatchOutput = {
  batch: {
    id: string;
    ordinal?: number;
    display_label?: string;
    display_id?: string;
    chapter_numbers: number[];
    chapter_titles?: string[];
  };
  chapters: BatchChapterOutput[];
  passed: boolean;
  quality_gates?: {
    stage_1_chapter_language_and_volume?: { passed?: boolean };
    stage_2_semantic_review?: { passed?: boolean };
    stage_3_batch_integration?: { passed?: boolean };
  };
  live?: boolean;
};

export type BatchedEvent = RunEvent & { batchId: string };

export function batchEvents(events: RunEvent[]): BatchedEvent[] {
  let activeBatch = "未归属批次";
  return events
    .filter((event) => event.step === "generation")
    .map((event) => {
      const explicit = typeof event.payload?.batch === "string" ? event.payload.batch : "";
      if (event.event_type === "generation.batch.started" && explicit) activeBatch = explicit;
      return { ...event, batchId: explicit || activeBatch };
    });
}

export function batchEventLabel(events: RunEvent[], batchId?: string): string {
  if (!batchId || batchId === "未归属批次") return "当前批次";
  const orderedIds = [...new Set(
    batchEvents(events)
      .filter((event) => event.event_type === "generation.batch.started")
      .map((event) => event.batchId),
  )];
  const ordinal = orderedIds.indexOf(batchId) + 1;
  const matches = batchId.match(/-(\d+)-(\d+)$/);
  const range = matches
    ? `第 ${Number(matches[1])}${matches[1] === matches[2] ? "" : `–${Number(matches[2])}`} 章`
    : batchId;
  return `批次 ${ordinal > 0 ? ordinal : "—"} · ${range}`;
}

export function eventDisplayMessage(events: RunEvent[], event: RunEvent): string {
  const matching = batchEvents(events).find((item) => item.id === event.id);
  const batchId = matching?.batchId;
  return batchId && batchId !== "未归属批次"
    ? event.message.replace(`批次 ${batchId}`, batchEventLabel(events, batchId))
    : event.message;
}

export function batchPresentation(
  run: RunDetail,
  batch: BatchOutput["batch"],
): { label: string; ordinal?: number; total: number; isFinal: boolean } {
  const orderedIds = [...new Set(
    batchEvents(run.events)
      .filter((event) => event.event_type === "generation.batch.started")
      .map((event) => event.batchId)
      .filter((id) => id !== "未归属批次"),
  )];
  const eventOrdinal = orderedIds.indexOf(batch.id) + 1;
  const ordinal = batch.ordinal ?? (eventOrdinal > 0 ? eventOrdinal : undefined);
  const outputOrdinals = allBatchOutputs(run)
    .map((item) => item.batch.ordinal)
    .filter((item): item is number => typeof item === "number");
  const plannedCount = plannedBatchCount(run);
  const observedTotal = Math.max(orderedIds.length, ...outputOrdinals, ordinal || 0);
  const total = plannedCount || observedTotal;
  const requestedChapterCount = Number(run.request?.preferred_chapter_count ?? 0);
  const numbers = batch.chapter_numbers;
  const chapterRange = numbers.length
    ? `第 ${numbers[0]}${numbers.length > 1 ? `–${numbers[numbers.length - 1]}` : ""} 章`
    : "章节范围待确认";
  return {
    label: batch.display_label || `批次 ${ordinal || "—"} · ${chapterRange}`,
    ordinal,
    total,
    isFinal: Boolean(
      (plannedCount && ordinal && ordinal === total)
      || (requestedChapterCount && numbers.at(-1) && numbers.at(-1)! >= requestedChapterCount),
    ),
  };
}

export function plannedBatchCount(run: RunDetail): number | undefined {
  const candidates = run.artifacts
    .filter((artifact) => artifact.step === "batch_plan")
    .map((artifact) => artifact.raw_output);
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    const batches = (candidate as { batches?: unknown }).batches;
    if (Array.isArray(batches) && batches.length) return batches.length;
  }
  return undefined;
}

export function BatchEventHistory({ run }: { run: RunDetail }) {
  const generation = useMemo(() => batchEvents(run.events), [run.events]);
  const batchIds = useMemo(
    () => [...new Set(generation.map((event) => event.batchId))]
      .filter((id) => id !== "未归属批次")
      .reverse(),
    [generation],
  );
  const outputById = useMemo(
    () => new Map(allBatchOutputs(run).map((batch) => [batch.batch.id, batch])),
    [run],
  );
  const eventsByBatch = useMemo(() => {
    const map = new Map<string, BatchedEvent[]>();
    for (const event of generation) {
      const list = map.get(event.batchId) || [];
      list.push(event);
      map.set(event.batchId, list);
    }
    return map;
  }, [generation]);
  const allOtherEvents = useMemo(
    () => [...run.events].filter((event) => event.step !== "generation").reverse(),
    [run.events],
  );
  const [otherVisibleCount, setOtherVisibleCount] = useState(20);
  const otherEvents = allOtherEvents.slice(0, otherVisibleCount);
  return <div className="event-list batch-event-history">
    {batchIds.map((batchId, index) => {
      const output = outputById.get(batchId);
      const label = output
        ? batchPresentation(run, output.batch).label
        : batchEventLabel(run.events, batchId);
      const total = eventsByBatch.get(batchId)?.length ?? 0;
      return (
        <details key={batchId} open={index === 0} className="batch-event-group">
          <summary>
            <span>{label}</span>
            <small>{total} 条</small>
          </summary>
          <BatchEventItems
            events={(eventsByBatch.get(batchId) || []).slice().reverse()}
            allEvents={run.events}
          />
        </details>
      );
    })}
    {otherEvents.length > 0 && <details className="batch-event-group other-events">
      <summary><span>其他 Workflow 事件</span><small>{allOtherEvents.length} 条</small></summary>
      <div className="batch-event-items paginated">
        {otherEvents.map((event) => <div key={event.id}>
          <span>{event.seq}</span>
          <strong>{eventDisplayMessage(run.events, event)}</strong>
          <time>{new Date(event.created_at).toLocaleTimeString()}</time>
        </div>)}
        {allOtherEvents.length > otherVisibleCount && (
          <button type="button" className="button ghost event-load-more" onClick={() => setOtherVisibleCount((value) => value + 40)}>
            加载更早的 {Math.min(40, allOtherEvents.length - otherVisibleCount)} 条（已显示 {otherVisibleCount}/{allOtherEvents.length}）
          </button>
        )}
      </div>
    </details>}
    {!batchIds.length && !otherEvents.length && <p className="event-empty">尚无运行事件</p>}
  </div>;
}

export function BatchEventItems({ events, allEvents }: { events: BatchedEvent[]; allEvents: RunEvent[] }) {
  const PAGE_SIZE = 20;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const visible = events.slice(0, visibleCount);
  return (
    <div className="batch-event-items paginated">
      {visible.map((event) => <div key={event.id}>
        <span>{event.seq}</span>
        <strong>{eventDisplayMessage(allEvents, event)}</strong>
        <time>{new Date(event.created_at).toLocaleTimeString()}</time>
      </div>)}
      {events.length > visibleCount && (
        <button type="button" className="button ghost event-load-more" onClick={() => setVisibleCount((value) => value + PAGE_SIZE)}>
          加载更早的 {Math.min(PAGE_SIZE, events.length - visibleCount)} 条（已显示 {visibleCount}/{events.length}）
        </button>
      )}
    </div>
  );
}

export function activeBatchOutput(run: RunDetail): BatchOutput | null {
  const events = batchEvents(run.events);
  const started = [...events].reverse().find((event) => event.event_type === "generation.batch.started");
  if (!started || started.batchId === "未归属批次") return null;
  const matches = started.batchId.match(/-(\d+)-(\d+)$/);
  if (!matches) return null;
  const first = Number(matches[1]);
  const last = Number(matches[2]);
  const currentEvents = events.filter((event) => event.batchId === started.batchId);
  const chapters = Array.from({ length: last - first + 1 }, (_, offset) => {
    const number = first + offset;
    const chapterEvents = currentEvents.filter((event) => event.payload?.chapter === number);
    const latest = chapterEvents.at(-1);
    const persisted = chapterEvents.some(
      (event) =>
        event.event_type === "generation.chapter.continuity" ||
        event.event_type === "generation.chapter.continuity.started" ||
        event.event_type === "generation.chapter.continuity.completed",
    );
    return {
      chapter: number,
      title: latest?.message.replace(/^第\s*\d+\s*章[：:]/, "").replace(/（.*$/, "") || "等待开始",
      path: String(number),
      passed: false,
      deferred: false,
      issues: [],
      persisted,
    };
  });
  return {
    batch: { id: started.batchId, chapter_numbers: chapters.map((chapter) => chapter.chapter) },
    chapters,
    passed: false,
    live: true,
  };
}

export function asBatchOutput(value: unknown): BatchOutput | null {
  if (!value || typeof value !== "object") return null;
  const source = value as { batch?: unknown; chapters?: unknown; batch_results?: unknown };
  if (Array.isArray(source.batch_results)) {
    const latest = source.batch_results[source.batch_results.length - 1];
    return asBatchOutput(latest);
  }
  if (
    !source.batch ||
    typeof source.batch !== "object" ||
    !Array.isArray(source.chapters)
  ) return null;
  const batch = source.batch as { id?: unknown; ordinal?: unknown; display_label?: unknown; chapter_numbers?: unknown; chapter_titles?: unknown };
  if (typeof batch.id !== "string" || !Array.isArray(batch.chapter_numbers)) return null;
  return source as BatchOutput;
}

export function latestBatchOutput(run: RunDetail): BatchOutput | null {
  const candidates: unknown[] = [
    run.interrupt_payload?.output,
    ...[...run.artifacts]
      .filter((artifact) => artifact.step === "generation")
      .reverse()
      .map((artifact) => artifact.raw_output),
  ];
  for (const candidate of candidates) {
    const batch = asBatchOutput(candidate);
    if (batch) return batch;
  }
  return null;
}

export function effectiveCharCount(markdown: string): number {
  let value = markdown.replace(/```[\s\S]*?```/g, "");
  value = value.replace(/!\[[^\]]*]\([^)]+\)/g, "");
  value = value.replace(/\[([^\]]+)]\([^)]+\)/g, "$1");
  value = value.replace(/[#>*_`|~\-\s]/g, "");
  return value.length;
}

export function allBatchOutputs(run: RunDetail): BatchOutput[] {
  const results: BatchOutput[] = [];
  // Quality repair updates are newer than the original generation artifact.
  // Read the current course-quality report / repair patch first so chapter
  // cards and article metrics do not remain frozen at the first batch result.
  const candidates: unknown[] = [
    run.interrupt_payload?.output,
    ...[...run.artifacts]
      .filter((artifact) => artifact.step === "quality")
      .reverse()
      .map((artifact) => artifact.raw_output),
    ...[...run.artifacts]
      .filter((artifact) => artifact.step === "generation")
      .reverse()
      .map((artifact) => artifact.raw_output),
  ];
  for (const candidate of candidates) {
    const batches = batchOutputsFrom(candidate);
    for (const batch of batches) {
      if (!results.some((item) => item.batch.id === batch.batch.id)) results.push(batch);
    }
  }
  return results;
}

export function batchOutputsFrom(value: unknown): BatchOutput[] {
  const direct = asBatchOutput(value);
  if (direct) return [direct];
  if (!value || typeof value !== "object") return [];
  const record = value as { batches?: unknown; batch_results?: unknown; course_quality_report?: unknown };
  const batches = Array.isArray(record.batches)
    ? record.batches
    : Array.isArray(record.batch_results)
      ? record.batch_results
      : [];
  if (batches.length) return batches.map(asBatchOutput).filter((item): item is BatchOutput => Boolean(item));
  return batchOutputsFrom(record.course_quality_report);
}

export type ChapterQualityInfo = {
  humanizerScore?: number;
  semanticDecision?: string;
  effectiveCharMin?: number;
  effectiveChars?: number;
  passed?: boolean;
  integrationPassed?: boolean;
  courseIntegrationPassed?: boolean;
  repairStatus?: string;
  updatedAt?: string;
  source: "snapshot" | "latest" | "none";
};

export function chapterQualityMap(
  run: RunDetail,
  snapshot?: import("../../api").CourseQualitySnapshot,
): Map<number, ChapterQualityInfo> {
  const map = new Map<number, ChapterQualityInfo>();
  // The atomically-written course snapshot is the only live quality fact
  // source. Artifact parsing remains strictly as a migration fallback for
  // older courses that predate the snapshot.
  if (snapshot?.chapters?.length) {
    for (const chapter of snapshot.chapters) {
      map.set(chapter.chapter, {
        humanizerScore: chapter.humanizer_score,
        semanticDecision: chapter.semantic_decision,
        effectiveCharMin: chapter.effective_char_min,
        effectiveChars: chapter.effective_chars,
        passed: chapter.chapter_passed,
        integrationPassed: chapter.batch_integration_passed ?? undefined,
        courseIntegrationPassed: chapter.course_integration_passed ?? undefined,
        repairStatus: chapter.repair_status,
        updatedAt: chapter.updated_at,
        source: "snapshot",
      });
    }
    return map;
  }
  for (const batch of allBatchOutputs(run)) {
    for (const chapter of batch.chapters) {
      if (map.has(chapter.chapter)) continue;
      map.set(chapter.chapter, {
        humanizerScore: chapter.humanizer_score,
        semanticDecision: chapter.semantic_review?.decision,
        effectiveCharMin: chapter.effective_char_min,
        effectiveChars: chapter.effective_chars,
        // A chapter gate and batch integration are distinct facts. Do not
        // turn a passed chapter red because another source broke its batch.
        passed: Boolean(chapter.passed),
        integrationPassed: batch.quality_gates?.stage_3_batch_integration?.passed,
        source: "latest",
      });
    }
  }
  return map;
}

