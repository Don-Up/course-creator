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
  WorkflowStep,
  WorkspaceFile,
} from "../api";
import { PageHeader } from "../components/common";
import { AgentOrchestrationGraph, StepStatus, WorkflowMap } from "../features/run/visuals";
export function WorkflowOverview() {
  const { data } = useQuery({ queryKey: ["workflow-snapshot"], queryFn: api.workflow });
  const [selected, setSelected] = useState("intake");
  const fakeRun = useMemo<{ current_step: string; status: string; artifacts: RunArtifact[]; workflow_steps: WorkflowStep[] }>(() => ({
    current_step: "",
    status: "PENDING",
    artifacts: [] as RunArtifact[],
    workflow_steps: data?.topologies.find((item) => item.mode === "new_course")?.steps.map((step) => ({ ...step, status: "pending" as const, artifacts: [] })) || [],
  }), [data]);
  return (
    <>
      <PageHeader
        eyebrow="Visible state machine"
        title="每一步都能看见输入、输出和暂停原因"
        description="工作流结构由系统确定；模型负责课程判断与写作，用户保留方向和发布决策。"
      />
      <WorkflowMap
        steps={fakeRun.workflow_steps}
        currentStep=""
        runStatus={undefined}
        selectedStep={selected}
        onSelect={setSelected}
      />
      <AgentOrchestrationGraph selectedPhase={selected} onPhaseChange={setSelected} />
      {fakeRun.workflow_steps
        .filter((step: RunDetail["workflow_steps"][number]) => step.id === selected)
        .map((step: RunDetail["workflow_steps"][number]) => (
          <section className="step-workspace pending" key={step.id}>
            <div className="step-workspace-heading">
              <div>
                <span className="eyebrow">WORKFLOW NODE {String(fakeRun.workflow_steps.findIndex((item: RunDetail["workflow_steps"][number]) => item.id === step.id) + 1).padStart(2, "0")}</span>
                <h2>{step.title}</h2>
                <p>{step.description}</p>
              </div>
              <StepStatus status="pending" />
            </div>
            <div className="step-columns">
              <section className="step-input-panel">
                <span className="side-label">USER INPUT</span>
                <p className="input-copy">{step.user_input}</p>
              </section>
              <section className="step-output-panel">
                <span className="side-label">MODEL OUTPUT</span>
                <div className="output-placeholder"><span className="empty-dot" /><span>{step.model_output}</span></div>
              </section>
            </div>
          </section>
        ))}
    </>
  );
}
