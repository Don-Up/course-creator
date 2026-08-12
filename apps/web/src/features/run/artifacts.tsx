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

export function eventReason(event: RunEvent, events: RunEvent[]): string {
  const direct = event.payload?.issues;
  if (Array.isArray(direct) && direct.length) return String(direct[0]);
  const chapter = event.payload?.chapter;
  if (typeof chapter !== "number") return "";
  const index = events.findIndex((item) => item.id === event.id);
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const candidate = events[cursor];
    if (candidate.payload?.chapter !== chapter) continue;
    if (
      candidate.event_type !== "generation.chapter.retrying" &&
      candidate.event_type !== "generation.chapter.enriching"
    ) continue;
    const issues = candidate.payload?.issues;
    if (Array.isArray(issues) && issues.length) return String(issues[0]);
  }
  return "";
}

export function ArtifactTimeline({
  artifacts,
  running,
}: {
  artifacts: RunArtifact[];
  running: boolean;
}) {
  const newestFirst = [...artifacts].sort((left, right) => {
    const timeDifference = Date.parse(right.created_at) - Date.parse(left.created_at);
    return timeDifference || right.id.localeCompare(left.id);
  });
  if (!newestFirst.length) {
    return (
      <div className="output-placeholder">
        {running ? <LoaderCircle className="spin" size={18} /> : <span className="empty-dot" />}
        <span>{running ? "Agent 正在生成本节点的第一份产物…" : "本节点还没有输出记录"}</span>
      </div>
    );
  }
  return (
    <div className="artifact-timeline">
      {running && (
        <div className="timeline-running"><LoaderCircle className="spin" size={15} />正在生成新的版本</div>
      )}
      {newestFirst.map((artifact, index) => (
        <div className="timeline-entry" key={artifact.id}>
          <span className="timeline-dot" />
          {index === 0 ? (
            <ArtifactCard artifact={artifact} />
          ) : (
            <details className="artifact-history-item">
              <summary>
                <span>
                  <strong>{artifact.presentation.headline || artifact.title}</strong>
                  <small>{new Date(artifact.created_at).toLocaleString()}</small>
                </span>
                <ChevronDown size={16} />
              </summary>
              <ArtifactCard artifact={artifact} />
            </details>
          )}
        </div>
      ))}
    </div>
  );
}


export function WorkflowRow({
  step,
  index,
  run,
  children,
}: {
  step: RunDetail["workflow_steps"][number];
  index: number;
  run: RunDetail;
  children: ReactNode;
}) {
  const artifacts = step.artifacts || [];
  return (
    <motion.div
      className={`workflow-row ${step.status}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <div className="workflow-index">{String(index + 1).padStart(2, "0")}</div>
      <div className="workflow-side user-side">
        <span className="side-label">USER INPUT</span>
        <h2>{step.title}</h2>
        <p>{step.description}</p>
        {children}
      </div>
      <div className="workflow-arrow"><ChevronRight size={18} /></div>
      <div className="workflow-side model-side">
        <span className="side-label">MODEL OUTPUT</span>
        {artifacts.length ? (
          <div className="artifact-list">
            {artifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} />
            ))}
          </div>
        ) : (
          <div className="output-placeholder">
            {step.status === "completed" ? <Check size={18} /> : step.status === "active" ? <LoaderCircle className="spin" size={18} /> : <span className="empty-dot" />}
            <span>{step.status === "completed" ? "本步已完成，产物已持久化" : step.model_output}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export function ArtifactCard({ artifact }: { artifact: RunArtifact }) {
  const presentation = artifact.presentation;
  const blockers = presentation.blockers || [];
  return (
    <article className="artifact-card">
      <div className="artifact-heading">
        <div>
          <span className={`artifact-source ${artifact.source}`}>
            {artifact.source === "recovered"
              ? "历史文件恢复"
              : artifact.source === "submitted"
                ? "本次创建输入"
                : "Agent 生成"}
          </span>
          <h3>{presentation.headline || artifact.title}</h3>
        </div>
        <time>{new Date(artifact.created_at).toLocaleString()}</time>
      </div>
      <p className="artifact-conclusion">{presentation.conclusion}</p>
      {Object.keys(presentation.metrics || {}).length > 0 && (
        <div className="artifact-metrics">
          {Object.entries(presentation.metrics).map(([label, value]) => (
            <span key={label}><small>{label}</small><strong>{String(value)}</strong></span>
          ))}
        </div>
      )}
      {presentation.highlights?.length > 0 && (
        <ul className="artifact-highlights">
          {presentation.highlights.filter(Boolean).map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
      {blockers.length > 0 && (
        <div className="artifact-blockers">
          <strong>阻塞问题</strong>
          <ul>{blockers.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {presentation.issues?.length > 0 && (
        <div className="artifact-issues">
          <strong>建议关注，可优化项</strong>
          <ul>{presentation.issues.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {presentation.next_action && <p className="artifact-next">{presentation.next_action}</p>}
      <details className="raw-output">
        <summary>查看完整原始输出</summary>
        <pre>{JSON.stringify(artifact.raw_output, null, 2)}</pre>
      </details>
    </article>
  );
}
