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

export function Layout({ children }: { children: ReactNode }) {
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [providerSettingsOpen, setProviderSettingsOpen] = useState(false);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/">
          <span className="brand-mark">CA</span>
          <span>
            <strong>Course Agent</strong>
            <small>Local workspace</small>
          </span>
        </Link>
        <nav className="main-nav">
          <NavLink to="/" end>
            <Home size={18} />课程
          </NavLink>
          <NavLink to="/new">
            <Plus size={18} />新建课程
          </NavLink>
          <NavLink to="/workflow">
            <GitBranch size={18} />工作流
          </NavLink>
        </nav>
        <button className="sidebar-status provider-trigger" onClick={() => setProviderSettingsOpen(true)}>
          <span className={health?.provider_configured ? "dot ok" : "dot"} />
          <div>
            <strong>{health?.provider === "codex_gateway" ? "Codex Gateway" : health?.provider_configured ? "外部 API 已配置" : "配置模型"}</strong>
            <small>{health?.model || "等待选择"} · 本地</small>
          </div>
          <Settings2 size={15} />
        </button>
      </aside>
      <div className="content-shell">
        <header className="topbar">
          <div>
            <span className="eyebrow">基于 LLM 的高质量课程生成 Agent</span>
          </div>
          <Link className="button secondary compact" to="/workflow">
            <Settings2 size={16} />引导模式
          </Link>
        </header>
        <main className="page">{children}</main>
      </div>
      {providerSettingsOpen && <ProviderSettingsDialog onClose={() => setProviderSettingsOpen(false)} />}
    </div>
  );
}

export function ProviderSettingsDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [provider, setProvider] = useState<"codex_gateway" | "deepseek">("codex_gateway");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  useEffect(() => {
    if (!health) return;
    setProvider(health.provider === "deepseek" ? "deepseek" : "codex_gateway");
    setModel(health.model);
  }, [health]);
  const mutation = useMutation({
    mutationFn: () => api.updateProviderPreferences({
      provider,
      model: model.trim(),
      deepseek_api_key: apiKey.trim(),
      llm_base_url: baseUrl.trim(),
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["health"] });
      onClose();
    },
  });
  const codexModels = health?.codex_gateway_models || [];
  const selectProvider = (next: "codex_gateway" | "deepseek") => {
    setProvider(next);
    if (next === "codex_gateway") setModel(codexModels[0] || "llm-gateway--kimi-k3");
  };
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="provider-dialog" role="dialog" aria-modal="true" aria-labelledby="provider-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-heading">
          <div><span className="side-label">LOCAL MODEL CONFIGURATION</span><h2 id="provider-dialog-title">模型与凭据</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={18} /></button>
        </div>
        <p className="dialog-copy">选择会用于后续新 Run 的模型。已有 Run 保留创建时的 Provider，避免中途切换影响可恢复性。</p>
        <div className="provider-options">
          <button type="button" className={provider === "codex_gateway" ? "selected" : ""} onClick={() => selectProvider("codex_gateway")}>
            <strong>读取当前 Codex</strong><small>复用本机 LLM Gateway 与登录凭据</small>
          </button>
          <button type="button" className={provider === "deepseek" ? "selected" : ""} onClick={() => selectProvider("deepseek")}>
            <strong>外部 DeepSeek API</strong><small>本机保存模型、地址与 API Key</small>
          </button>
        </div>
        <label>模型
          {provider === "codex_gateway" ? <select value={model} onChange={(event) => setModel(event.target.value)}>{codexModels.map((item) => <option key={item} value={item}>{item}</option>)}</select> : <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="deepseek-chat" />}
        </label>
        {provider === "codex_gateway" ? <p className="provider-note">当前策略：推理强度 {health?.reasoning_effort || "medium"}，速度档位 {health?.service_tier || "standard"}。Gateway 凭据只从 <code>~/.codex/config.toml</code> 读取。</p> : <div className="provider-fields"><label>API Key<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="输入或替换本机 DeepSeek API Key" /></label><label>兼容 API 地址（可选）<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.deepseek.com" /></label></div>}
        {mutation.error && <div className="error-banner">{mutation.error.message}</div>}
        <div className="dialog-actions"><button className="button secondary" onClick={onClose}>取消</button><button className="button primary" onClick={() => mutation.mutate()} disabled={!model.trim() || mutation.isPending}>{mutation.isPending ? "正在保存" : "保存模型配置"}</button></div>
      </section>
    </div>
  );
}

