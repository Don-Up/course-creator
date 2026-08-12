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
import { statusLabel, audienceTemplates, goalTemplates, scopeTemplates, sourcePolicies } from "../constants";
import { EmptyState, Field, FormSection, Markdown, Metric, PageHeader, TemplateTextarea, ToolOutput } from "../components/common";
export function CourseCard({ course }: { course: Course }) {
  return (
    <motion.article className="course-card" whileHover={{ y: -3 }}>
      <div className="card-topline">
        <span className="status-chip">{statusLabel[course.status] || course.status}</span>
        <span>{course.chapter_count} 章</span>
      </div>
      <div>
        <h2>{course.title}</h2>
        <p>{course.description || "已导入本地课程，可进行审阅和修改。"}</p>
      </div>
      <div className="course-stats">
        <span><BookOpen size={16} />{course.chapter_count} 个 Markdown 章节</span>
        <span><ShieldCheck size={16} />{course.quality_report_count} 份质量记录</span>
      </div>
      <Link className="card-link" to={course.resumable_run_id ? `/runs/${course.resumable_run_id}` : `/courses/${course.slug}`}>
        {course.resumable_run_id ? "继续课程生成" : "打开课程工作台"} <ChevronRight size={17} />
      </Link>
    </motion.article>
  );
}

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["courses"],
    queryFn: api.courses,
  });
  return (
    <>
      <PageHeader
        eyebrow="Course library"
        title="课程不是一次生成，而是一条可以恢复的生产线"
        description="六门历史课程已经接入同一工作台。你可以审阅、直接编辑 Markdown，或启动新的课程 Agent Run。"
        action={
          <Link className="button primary" to="/new">
            <Sparkles size={17} />创建课程
          </Link>
        }
      />
      {isLoading && <EmptyState icon={<LoaderCircle className="spin" />} text="正在扫描本地课程" />}
      {error && <EmptyState icon={<CircleAlert />} text={(error as Error).message} />}
      <section className="course-grid">
        {data?.items.map((course) => <CourseCard key={course.slug} course={course} />)}
      </section>
    </>
  );
}

export function CourseWorkspace() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [toolResult, setToolResult] = useState<ToolResult | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [instruction, setInstruction] = useState("");
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const { data: course, isLoading } = useQuery({
    queryKey: ["course", slug],
    queryFn: () => api.course(slug),
  });
  const resumableCreationRunId = course?.resumable_run_id;
  useEffect(() => {
    if (resumableCreationRunId) {
      navigate(`/runs/${resumableCreationRunId}`, { replace: true });
    }
  }, [navigate, resumableCreationRunId]);
  const toolMutation = useMutation({
    mutationFn: (action: "build" | "validate") => api.runTool(slug, action),
    onSuccess: (result) => {
      setToolResult(result);
      queryClient.invalidateQueries({ queryKey: ["course", slug] });
    },
  });
  const runMutation = useMutation({
    mutationFn: (scope: "review_course" | "regenerate_course") =>
      api.startRun(slug, {
        provider: health?.provider || "codex_gateway",
        model: health?.model || "llm-gateway--kimi-k3",
        scope,
        chapter_keys: [...selectedKeys],
        instruction:
          instruction ||
          (scope === "review_course"
            ? "按课程质量量规审阅所选章节"
            : "在保留正确内容的前提下重生成所选章节"),
      }),
    onSuccess: ({ run_id }) => navigate(`/runs/${run_id}`),
  });
  const toggleChapter = (key: string) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  if (isLoading || !course) {
    return <EmptyState icon={<LoaderCircle className="spin" />} text="正在读取课程" />;
  }
  if (resumableCreationRunId) {
    return (
      <EmptyState
        icon={<LoaderCircle className="spin" />}
        text="正在恢复未完成的课程创建 Workflow…"
      />
    );
  }
  return (
    <>
      <PageHeader
        eyebrow={`courses/${course.slug}`}
        title={course.title}
        description={course.description || "本地课程工作区"}
        action={
          <div className="button-row">
            <button className="button secondary" onClick={() => toolMutation.mutate("validate")}>
              <ShieldCheck size={17} />运行质检
            </button>
            <button className="button primary" onClick={() => runMutation.mutate("review_course")}>
              <Play size={17} />Review {selectedKeys.size ? `(${selectedKeys.size})` : "整课"}
            </button>
          </div>
        }
      />
      <section className="metric-grid">
        <Metric label="章节" value={String(course.chapter_count)} />
        <Metric label="质量记录" value={String(course.quality_report_count)} />
        <Metric label="课程状态" value={statusLabel[course.status] || course.status} />
        <Metric label="事实源" value={course.has_course_json ? "course.json" : "目录扫描"} />
      </section>
      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Markdown sources</span>
            <h2>章节</h2>
          </div>
          <button className="text-button" onClick={() => toolMutation.mutate("build")}>
            <RefreshCw size={16} />重新构建 HTML
          </button>
        </div>
        <div className="chapter-list">
          {course.lessons.map((lesson) => (
            <div
              key={lesson.markdown}
              className="chapter-row"
            >
              <input
                aria-label={`选择 ${lesson.title}`}
                type="checkbox"
                checked={selectedKeys.has(String(lesson.number))}
                onChange={() => toggleChapter(String(lesson.number))}
              />
              <span className="chapter-number">{lesson.code || String(lesson.number).padStart(2, "0")}</span>
              <Link className="chapter-link" to={`/courses/${slug}/chapters/${lesson.number}`}>
                <span>
                <strong>{lesson.title}</strong>
                <small>{lesson.summary || lesson.markdown}</small>
                </span>
                <FilePenLine size={18} />
              </Link>
            </div>
          ))}
        </div>
      </section>
      <section className="panel agent-actions">
        <div>
          <span className="eyebrow">Agent actions</span>
          <h2>审阅或重生成</h2>
          <p>
            {selectedKeys.size
              ? `已选择 ${selectedKeys.size} 章。`
              : "未选择章节时，Review 会审阅整课；重生成必须先选择章节。"}
          </p>
        </div>
        <textarea
          aria-label="Agent 指令"
          placeholder="可选：写下审阅重点或定向重生成要求"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
        />
        <div className="button-row">
          <button
            className="button secondary"
            disabled={runMutation.isPending}
            onClick={() => runMutation.mutate("review_course")}
          >
            <ShieldCheck size={17} />Review
          </button>
          <button
            className="button primary"
            disabled={!selectedKeys.size || runMutation.isPending}
            onClick={() => runMutation.mutate("regenerate_course")}
          >
            <RefreshCw size={17} />重生成所选章节
          </button>
        </div>
        {runMutation.error && <div className="error-banner">{runMutation.error.message}</div>}
      </section>
      {toolResult && (
        <ToolOutput result={toolResult} onClose={() => setToolResult(null)} />
      )}
    </>
  );
}

export function ChapterWorkspace() {
  const { slug = "", key = "" } = useParams();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState("");
  const [rebuild, setRebuild] = useState(true);
  const { data: chapter, isLoading } = useQuery({
    queryKey: ["chapter", slug, key],
    queryFn: () => api.chapter(slug, key),
  });
  useEffect(() => {
    if (chapter) setContent(chapter.content);
  }, [chapter]);
  const saveMutation = useMutation({
    mutationFn: () =>
      api.saveChapter(slug, key, {
        content,
        expected_hash: chapter!.content_hash,
        reason: "课程工作台人工编辑",
        rebuild,
      }),
    onSuccess: ({ chapter: saved }) => {
      queryClient.setQueryData(["chapter", slug, key], saved);
      queryClient.invalidateQueries({ queryKey: ["course", slug] });
      setEditing(false);
    },
  });
  if (isLoading || !chapter) {
    return <EmptyState icon={<LoaderCircle className="spin" />} text="正在读取章节" />;
  }
  return (
    <>
      <Link className="back-link" to={`/courses/${slug}`}>
        <ArrowLeft size={16} />返回课程
      </Link>
      <PageHeader
        eyebrow={chapter.path}
        title={chapter.title}
        description={`本地 Markdown · ${new Date(chapter.updated_at).toLocaleString()}`}
        action={
          editing ? (
            <div className="button-row">
              <button className="button secondary" onClick={() => { setContent(chapter.content); setEditing(false); }}>
                <X size={17} />取消
              </button>
              <button className="button primary" onClick={() => saveMutation.mutate()}>
                <Save size={17} />保存到本地
              </button>
            </div>
          ) : (
            <button className="button primary" onClick={() => setEditing(true)}>
              <SquarePen size={17} />Edit
            </button>
          )
        }
      />
      {editing ? (
        <section className="editor-grid">
          <div className="editor-pane">
            <div className="pane-heading">
              <strong>Markdown</strong>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={rebuild}
                  onChange={(event) => setRebuild(event.target.checked)}
                />
                保存后重建 HTML
              </label>
            </div>
            <textarea
              aria-label="Markdown 编辑器"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              spellCheck={false}
            />
          </div>
          <div className="preview-pane">
            <div className="pane-heading"><strong>实时预览</strong><span>未保存</span></div>
            <Markdown content={content} courseSlug={slug} />
          </div>
        </section>
      ) : (
        <article className="markdown-preview"><Markdown content={chapter.content} courseSlug={slug} /></article>
      )}
      {saveMutation.error && <div className="error-banner">{saveMutation.error.message}</div>}
      {chapter.snapshot_path && (
        <p className="snapshot-note">上一个版本已保存到 {chapter.snapshot_path}</p>
      )}
    </>
  );
}

export function NewCourse() {
  const navigate = useNavigate();
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [form, setForm] = useState({
    title: "",
    slug: "",
    audience: "",
    goals: "",
    scope: "",
    source_policy: "允许使用用户资料与公开官方资料",
    delivery: "Markdown + HTML",
    preferred_chapter_count: 12,
    effective_char_min: 12000,
    token_budget_mtokens: null as number | null,
    provider: "codex_gateway",
    model: "llm-gateway--kimi-k3",
  });
  const mutation = useMutation({
    mutationFn: () => api.createCourse(form),
    onSuccess: ({ run_id }) => navigate(`/runs/${run_id}`),
  });
  useEffect(() => {
    if (health?.model && health?.provider) {
      setForm((current) => ({ ...current, provider: health.provider, model: health.model }));
    }
  }, [health?.model, health?.provider]);
  const update = (key: string, value: string | number) =>
    setForm((current) => ({ ...current, [key]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };
  return (
    <>
      <PageHeader
        eyebrow="Guided creation"
        title="创建一门新课程"
        description="提交后，Agent 先生成任务定义并暂停。你确认后才进入模块与章节蓝图。"
        compact
      />
      <form className="new-course-form" onSubmit={submit}>
        <FormSection number="01" title="课程身份" description="给本地目录和学生页面一个稳定名称。">
          <Field label="课程名称"><input required value={form.title} onChange={(e) => update("title", e.target.value)} /></Field>
          <Field label="课程本地目录名（英文标识）">
            <input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="langchain-langgraph-course" value={form.slug} onChange={(e) => update("slug", e.target.value)} />
            <small className="field-hint">用于创建 courses/[[目录名]]，只允许小写英文、数字和连字符；它不是课程介绍。</small>
          </Field>
        </FormSection>
        <FormSection number="02" title="学习任务" description="这些输入会成为 Course Context。">
          <TemplateTextarea label="核心受众" value={form.audience} templates={audienceTemplates} onChange={(value) => update("audience", value)} />
          <TemplateTextarea label="学习目标" value={form.goals} templates={goalTemplates} onChange={(value) => update("goals", value)} />
          <TemplateTextarea label="内容范围" value={form.scope} templates={scopeTemplates} onChange={(value) => update("scope", value)} />
        </FormSection>
        <FormSection number="03" title="生成约束" description="章节数是规划参考，不是硬性平均分配。">
          <Field label="期望章节数"><input type="number" min={1} max={60} value={form.preferred_chapter_count} onChange={(e) => update("preferred_chapter_count", Number(e.target.value))} /></Field>
          <Field label="单章有效字符数下限"><input type="number" min={1000} max={50000} value={form.effective_char_min} onChange={(e) => update("effective_char_min", Number(e.target.value))} /></Field>
          <div className="token-budget-field">
            <div><span className="field-label">Token 阈值</span><small>用于课程成本观测，不会中断 Agent；创建后不可修改。</small></div>
            <div className="token-budget-controls">
              <label className={!form.token_budget_mtokens ? "selected" : ""}><input type="radio" name="token-budget" checked={!form.token_budget_mtokens} onChange={() => setForm((current) => ({ ...current, token_budget_mtokens: null }))} />不限制</label>
              <label className={form.token_budget_mtokens ? "selected" : ""}><input type="radio" name="token-budget" checked={Boolean(form.token_budget_mtokens)} onChange={() => setForm((current) => ({ ...current, token_budget_mtokens: current.token_budget_mtokens || 1 }))} />设置阈值</label>
              {form.token_budget_mtokens && <div className="token-budget-input"><input aria-label="Token 阈值（M）" type="number" min="0.01" max="10000" step="0.1" value={form.token_budget_mtokens} onChange={(event) => setForm((current) => ({ ...current, token_budget_mtokens: Number(event.target.value) }))} /><span>M Token</span></div>}
            </div>
          </div>
          <div className="field">
            <span>来源政策</span>
            <div className="source-policy-grid">
              {sourcePolicies.map((policy) => (
                <label className={`source-policy ${form.source_policy === policy.value ? "selected" : ""}`} key={policy.value}>
                  <input
                    type="radio"
                    name="source-policy"
                    value={policy.value}
                    checked={form.source_policy === policy.value}
                    onChange={(event) => update("source_policy", event.target.value)}
                  />
                  <span><strong>{policy.label}</strong><small>{policy.description}</small></span>
                </label>
              ))}
            </div>
          </div>
        </FormSection>
        <div className="form-submit">
          <span>Provider: DeepSeek / {form.model} · 引导模式</span>
          <button className="button primary large" disabled={mutation.isPending}>
            {mutation.isPending ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
            创建并生成任务定义
          </button>
        </div>
        {mutation.error && <div className="error-banner">{mutation.error.message}</div>}
      </form>
    </>
  );
}
