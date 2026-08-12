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
import { EmptyState, Markdown } from "./common";
export function ResourceUploader({ slug }: { slug: string }) {
  const queryClient = useQueryClient();
  const [fileName, setFileName] = useState("");
  const resourceDraftStorageKey = `course-agent:resource-draft:${slug}`;
  const [resourcesDraft, setResourcesDraft] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(resourceDraftStorageKey) || "";
  });
  const updateResourcesDraft = (value: string) => {
    setResourcesDraft(value);
    window.localStorage.setItem(resourceDraftStorageKey, value);
  };
  const saveResourcesMutation = useMutation({
    mutationFn: () =>
      api.appendWorkspaceResourceNote(slug, resourcesDraft),
    onSuccess: () => {
      setResourcesDraft("");
      window.localStorage.removeItem(resourceDraftStorageKey);
      queryClient.invalidateQueries({ queryKey: ["workspace-file", slug, "RESOURCES.md"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-files", slug] });
    },
  });
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const content_base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("无法读取资源文件"));
        reader.onload = () =>
          resolve(String(reader.result).split(",", 2)[1] || "");
        reader.readAsDataURL(file);
      });
      return api.uploadWorkspaceResource(slug, {
        filename: file.name,
        content_base64,
        media_type: file.type || "application/octet-stream",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace-files", slug] });
      queryClient.invalidateQueries({
        queryKey: ["workspace-file", slug, "RESOURCES.md"],
      });
    },
  });
  return (
    <div className="resource-uploader">
      <div className="resource-editor-heading">
        <div>
          <strong>补充课程资源 <small>可选</small></strong>
          <p>可登记 GitHub、官方文档或文章；不补充任何资源也可以继续。</p>
        </div>
      </div>
      <textarea
        className="resource-markdown-editor"
        aria-label="课程资源 Markdown"
        value={resourcesDraft}
        onChange={(event) => updateResourcesDraft(event.target.value)}
        placeholder={"# 课程资源\n\n## GitHub 课程\n\n- [项目名称](https://github.com/owner/repo)：用于……\n\n## 官方资料\n\n- [文档名称](https://example.com)：用于……"}
        spellCheck={false}
      />
      <div className="resource-upload-row">
        <span>支持链接清单与本地附件</span>
        <div className="resource-actions">
          <button
            className="button primary compact"
            disabled={
              !resourcesDraft.trim() ||
              saveResourcesMutation.isPending
            }
            onClick={() => saveResourcesMutation.mutate()}
          >
            <Save size={14} />
            {saveResourcesMutation.isPending ? "上传中…" : "上传资源"}
          </button>
        <label className="button secondary compact">
          <Upload size={15} />
          {uploadMutation.isPending ? "上传中…" : "上传附件"}
          <input
            type="file"
            accept=".md,.txt,.json,.yaml,.yml,.pdf,.docx,.pptx,.xlsx,.csv"
            disabled={uploadMutation.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                setFileName(file.name);
                uploadMutation.mutate(file);
              }
              event.target.value = "";
            }}
          />
        </label>
        </div>
      </div>
      {saveResourcesMutation.isSuccess && (
        <small className="upload-success"><Check size={13} />RESOURCES.md 已更新</small>
      )}
      {saveResourcesMutation.error && <small className="upload-error">{saveResourcesMutation.error.message}</small>}
      {uploadMutation.isSuccess && (
        <small className="upload-success"><Check size={13} />{fileName} 已加入资源库</small>
      )}
      {uploadMutation.error && <small className="upload-error">{uploadMutation.error.message}</small>}
    </div>
  );
}

export function WorkspaceExplorer({
  slug,
  embedded = false,
  refreshToken = 0,
}: {
  slug: string;
  embedded?: boolean;
  refreshToken?: number;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(embedded);
  const [selectedPath, setSelectedPath] = useState("");
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const { data: files, error: filesError, refetch: refetchFiles } = useQuery({
    queryKey: ["workspace-files", slug],
    queryFn: () => api.workspaceFiles(slug),
    enabled: open,
  });
  useEffect(() => {
    if (open && !selectedPath && files?.items.length) {
      const preferred = files.items.find((item) => item.path === "RESOURCES.md");
      setSelectedPath((preferred || files.items[0]).path);
    }
  }, [open, files, selectedPath]);
  const { data: file, isLoading, refetch: refetchFile } = useQuery({
    queryKey: ["workspace-file", slug, selectedPath],
    queryFn: () => api.workspaceFile(slug, selectedPath),
    enabled: open && Boolean(selectedPath),
  });
  useEffect(() => {
    if (!open) return;
    void refetchFiles();
    if (selectedPath) void refetchFile();
  }, [open, refreshToken]);
  useEffect(() => {
    if (file) {
      setDraft(file.content);
      setEditing(false);
    }
  }, [file]);
  const saveMutation = useMutation({
    mutationFn: () =>
      api.saveWorkspaceFile(slug, selectedPath, draft, file!.content_hash),
    onSuccess: (saved) => {
      queryClient.setQueryData(["workspace-file", slug, selectedPath], saved);
      queryClient.invalidateQueries({ queryKey: ["workspace-files", slug] });
      setEditing(false);
    },
  });
  return (
    <section className={`panel workspace-explorer ${open ? "open" : ""} ${embedded ? "embedded" : ""}`}>
      {!embedded && (
        <button className="workspace-toggle" onClick={() => setOpen((value) => !value)}>
          <span><FolderOpen size={19} /><strong>课程 Workspace</strong><small>查看并编辑任务定义、资源、生成规格、蓝图与 Agent 状态文件</small></span>
          <ChevronDown size={18} />
        </button>
      )}
      {open && (
        <div className="workspace-layout">
          <aside className="workspace-files">
            {files?.items.map((item) => (
              <button
                className={selectedPath === item.path ? "selected" : ""}
                key={item.path}
                onClick={() => setSelectedPath(item.path)}
              >
                <FileText size={15} />
                <span><strong>{item.path}</strong><small>{Math.max(1, Math.ceil(item.size / 1024))} KB</small></span>
              </button>
            ))}
          </aside>
          <div className="workspace-file-view">
            {filesError ? (
              <div className="workspace-unavailable">
                <CircleAlert size={20} />
                <div>
                  <strong>暂时无法读取 Workspace</strong>
                  <p>请确认本地 Agent 已启动后重试；不会影响当前节点的确认操作。</p>
                </div>
                <button className="button secondary compact" onClick={() => refetchFiles()}>
                  <RefreshCw size={14} />重试
                </button>
              </div>
            ) : isLoading || !file ? (
              <EmptyState icon={<LoaderCircle className="spin" />} text="正在读取 Workspace 文件" />
            ) : !file.editable ? (
              <div className="binary-file">
                <FileText size={28} />
                <strong>{file.path}</strong>
                <p>二进制资源已保存在本地工作区，可被 Agent 作为课程资料使用。</p>
              </div>
            ) : (
              <>
                <div className="workspace-file-toolbar">
                  <div><strong>{file.path}</strong><small>{new Date(file.updated_at).toLocaleString()}</small></div>
                  <div className="button-row">
                    {editing && <button className="button secondary compact" onClick={() => { setDraft(file.content); setEditing(false); }}>取消</button>}
                    <button
                      className="button primary compact"
                      disabled={saveMutation.isPending}
                      onClick={() => editing ? saveMutation.mutate() : setEditing(true)}
                    >
                      {editing ? <><Save size={14} />保存</> : <><SquarePen size={14} />Edit</>}
                    </button>
                  </div>
                </div>
                {editing ? (
                  <textarea className="workspace-editor" value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} />
                ) : file.path.endsWith(".md") ? (
                  <div className="workspace-preview"><Markdown content={file.content} /></div>
                ) : (
                  <pre className="workspace-code">{file.content}</pre>
                )}
                {saveMutation.error && <div className="error-banner">{saveMutation.error.message}</div>}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

