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
} from "../api";

export function PageHeader({
  eyebrow: _eyebrow,
  title,
  description,
  action,
  compact = false,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <motion.header
      className={`page-header ${compact ? "compact-header" : ""}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div>
        <h1>
          {title}
          <small>{description}</small>
        </h1>
      </div>
      {action}
    </motion.header>
  );
}

export function MermaidDiagram({ source }: { source: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const diagramId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    container.replaceChildren();
    setError(null);
    mermaid.initialize({
      startOnLoad: false,
      theme: "neutral",
      securityLevel: "strict",
      fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    });

    void mermaid.render(`course-mermaid-${diagramId}`, source)
      .then(({ svg, bindFunctions }) => {
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svg;
        bindFunctions?.(containerRef.current);
      })
      .catch((renderError: unknown) => {
        if (cancelled) return;
        setError(renderError instanceof Error ? renderError.message : "图表语法无法解析");
      });

    return () => { cancelled = true; };
  }, [diagramId, source]);

  if (error) {
    return (
      <div className="mermaid-error">
        <strong>Mermaid 图表未能渲染</strong>
        <span>{error}</span>
        <pre><code>{source}</code></pre>
      </div>
    );
  }

  return <div className="mermaid-diagram" ref={containerRef} aria-label="Mermaid 图表" />;
}

export function CodeBlock({ language, source }: { language: string; source: string }) {
  if (language === "mermaid") return <MermaidDiagram source={source} />;

  return (
    <div className="code-block">
      <div className="code-block-header"><span className="code-block-language">{language || "text"}</span></div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        PreTag="div"
        customStyle={{ margin: 0, background: "transparent", padding: "18px 20px" }}
        codeTagProps={{ className: "code-block-content" }}
      >
        {source.replace(/\n$/, "")}
      </SyntaxHighlighter>
    </div>
  );
}

function courseAssetUrl(courseSlug: string, source: string) {
  if (/^(?:https?:|data:|\/)/i.test(source)) return source;
  const normalized = source.replace(/^(?:\.\.\/)+assets\//, "").replace(/^assets\//, "");
  if (normalized === source || !normalized || normalized.startsWith("..")) return source;
  return `/api/courses/${encodeURIComponent(courseSlug)}/assets/${normalized.split("/").map(encodeURIComponent).join("/")}`;
}

export function Markdown({ content, courseSlug }: { content: string; courseSlug?: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }) {
            const child = isValidElement<{ className?: string; children?: ReactNode }>(children) ? children : null;
            const className = child?.props.className || "";
            const language = /language-([\w+-]+)/.exec(className)?.[1] || "";
            const source = String(child?.props.children || "");
            return child ? <CodeBlock language={language} source={source} /> : <pre>{children}</pre>;
          },
          img({ src, alt }) {
            const resolvedSource = src && courseSlug ? courseAssetUrl(courseSlug, src) : src;
            return <img src={resolvedSource} alt={alt || ""} loading="lazy" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

export function FormSection({ number, title, description, children }: { number: string; title: string; description: string; children: ReactNode }) {
  return <section className="form-section"><div className="form-section-copy"><span>{number}</span><h2>{title}</h2><p>{description}</p></div><div className="form-fields">{children}</div></section>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function TemplateTextarea({
  label,
  value,
  templates,
  onChange,
}: {
  label: string;
  value: string;
  templates: Array<{ name: string; content: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="field template-field">
      <span>{label}</span>
      <div className="template-picker">
        <small>套用模板：</small>
        {templates.map((template) => (
          <button
            type="button"
            key={template.name}
            onClick={() => onChange(template.content)}
          >
            {template.name}
          </button>
        ))}
      </div>
      <textarea aria-label={label} required value={value} onChange={(event) => onChange(event.target.value)} />
      <small className="field-hint">模板中的 [[内容]] 需要替换；套用后可以继续自由修改。</small>
    </div>
  );
}

export function EmptyState({ icon, text }: { icon: ReactNode; text: string }) {
  return <div className="empty-state">{icon}<p>{text}</p></div>;
}

export function ToolOutput({ result, onClose }: { result: ToolResult; onClose: () => void }) {
  return <section className={`tool-output ${result.succeeded ? "success" : "failed"}`}><div className="section-heading"><div><span className="eyebrow">Tool result</span><h2>{result.succeeded ? "执行通过" : "执行失败"}</h2></div><button className="icon-button" onClick={onClose}><X size={17} /></button></div><code>{result.command.join(" ")}</code><pre>{result.stdout || result.stderr || "无输出"}</pre></section>;
}
