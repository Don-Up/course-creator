import { useMemo, useState } from "react";
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { Bot, Check, ChevronDown, ChevronRight, CircleAlert, GitBranch, Hand, LoaderCircle, ShieldCheck, Wrench } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { api, RunDetail, WorkflowNode, WorkflowTopology } from "../../api";
import { statusLabel } from "../../constants";

export function AgentOrchestrationGraph({
  run, selectedPhase, onPhaseChange,
}: {
  run?: Pick<RunDetail, "current_step" | "status" | "request">;
  selectedPhase?: string;
  onPhaseChange?: (phase: string) => void;
}) {
  const { data: snapshot, error, isLoading } = useQuery({ queryKey: ["workflow-snapshot"], queryFn: api.workflow });
  const mode = String(run?.request?.workflow_scope || run?.request?.scope || "new_course");
  const topology = snapshot?.topologies.find((item) => item.mode === mode)
    || snapshot?.topologies.find((item) => item.mode === "new_course");
  const [expandedPhase, setExpandedPhase] = useState<string | null>(run?.current_step || "blueprint");

  if (isLoading) return <section className="orchestration-loading"><LoaderCircle className="spin" size={18} />正在读取实际 Workflow 定义…</section>;
  if (error || !topology) return <section className="orchestration-loading failed"><CircleAlert size={18} />执行拓扑暂不可用。7 步课程阶段仍可继续使用。</section>;

  return <TopologyView topology={topology} currentStep={run?.current_step} status={run?.status} expandedPhase={selectedPhase || expandedPhase} onExpand={onPhaseChange || setExpandedPhase} />;
}

export function TopologyView({
  topology, currentStep, status, expandedPhase, onExpand,
}: { topology: WorkflowTopology; currentStep?: string; status?: string; expandedPhase: string | null; onExpand: (phase: string) => void }) {
  const nodesByPhase = useMemo(() => new Map(topology.phases.map(([id]) => [id, topology.nodes.filter((node) => node.phase === id)])), [topology]);
  return <section className="topology-view tab-content">
    <header className="topology-heading">
      <div><span className="side-label">LANGGRAPH ORCHESTRATION</span><h2>{topology.title}</h2><p>7 步是课程生产的易读阶段；展开任一泳道可查看当前 LangGraph 节点、条件路由与受控运行时调用。</p></div>
      {status && status !== "PENDING" && <span className={`run-status ${status.toLowerCase()}`}>{statusLabel[status] || status}</span>}
    </header>
    <WorkflowDiagram topology={topology} currentStep={currentStep} />
    {topology.phases.map(([phase, title, description]) => {
      const nodes = nodesByPhase.get(phase) || [];
      if (phase !== expandedPhase) return null;
      return <section className="topology-lane" key={phase}>
        <header><div><span>阶段 {String(topology.phases.findIndex(([id]) => id === phase) + 1).padStart(2, "0")}</span><h3>{title}</h3><p>{description}</p></div><small>{nodes.length} 个执行节点</small></header>
        {nodes.length ? <div className="topology-nodes">{nodes.map((node) => <article key={node.id} className={currentStep === phase ? "active" : ""}><span className="node-handler">{node.handler}</span><strong>{node.title}</strong><code>{node.id}</code>{node.agents.length > 0 && <div className="runtime-tags"><GitBranch size={12} />{node.agents.join(" · ")}</div>}{node.tools.length > 0 && <div className="runtime-tags tools"><Wrench size={12} />{node.tools.join(" · ")}</div>}</article>)}</div> : <div className="topology-intake">该阶段由 API 在创建或启动 Run 前完成校验并持久化，不会作为 LangGraph 节点重复执行。</div>}
        <div className="topology-routes"><strong>从此阶段出发的真实路由</strong>{topology.edges.filter((edge) => nodes.some((node) => node.id === edge.from)).map((edge) => <span key={`${edge.from}-${edge.to}-${edge.label}`}><code>{edge.from}</code><ChevronRight size={13} /><code>{edge.to}</code><small>{edge.label}</small></span>)}</div>
      </section>;
    })}
    <footer className="runtime-manifest"><div><strong>Teaching Agent Runtime</strong>{topology.mode === "new_course" ? " Writer / Reviewer / Repair 的角色与模型策略由后端定义。" : " Review 流程使用受控 Reviewer。"}</div><div><strong>Tool Runtime</strong> Source Contract、Build、Validate 和 Workspace Patch 仅能被被授权的 Workflow handler 调用。</div></footer>
  </section>;
}

type WorkflowCanvasNodeData = WorkflowNode & { active: boolean };
type ExecutionMode = NonNullable<WorkflowNode["execution_mode"]>;

const modeLabels = {
  llm: "LLM Agent",
  hybrid: "LLM + 精确校验",
  deterministic: "精确任务",
  approval: "人工确认",
  system: "系统节点",
} as const;

const modeDescriptions = {
  llm: "模型推理",
  hybrid: "模型推理 + 确定性质量门",
  deterministic: "脚本 / 规则 / 编排处理",
  approval: "由人决定下一条路径",
  system: "API、完成或终止控制",
} as const;

const nodeSummaries: Record<string, string> = {
  intake: "校验课程请求并创建可恢复的 Run。",
  draft_mission: "把课程想法整理为可验收的教学任务。",
  approve_mission: "人工确认任务定义，或提出全局修改意见。",
  revise_workspace: "把确认后的修改同步到课程工作区。",
  research_sources: "规划检索问题，筛选可用于教学的来源。",
  draft_blueprint: "将目标与资料组织成模块、章节和学习路径。",
  verify_workspace_contract: "检查任务、资料与蓝图是否彼此一致。",
  record_contract_retry: "记录未通过的约束，并进入下一轮同步。",
  reconcile_global_requirements: "把全局要求重新同步到受影响的产物。",
  approve_blueprint: "人工确认蓝图，决定继续规划或返工。",
  plan_batches: "按模块依赖将章节分成可恢复的生产批次。",
  approve_plan: "人工确认批次划分、顺序与生产边界。",
  generate_batch: "生成章节，并依次完成结构、语义和表达质量门。",
  repair_batch_chapters: "只修复当前批次已定位的问题，完成后继续下一批。",
  request_batch_review: "自动流程无法收敛时，请人决定下一步处理方式。",
  approve_batch: "遗留的批次确认节点；当前图中尚未接入。",
  repair_open_chapters: "仅修复有证据的未达标章节，并重新验证。",
  prepare_course_quality_review: "汇总整课质量证据，准备统一审校。",
  course_quality_review: "检查整课门禁，决定修复、发布或停止。",
  prepare_release_review: "整理发布前的课程摘要与交付状态。",
  release_approval: "人工决定发布，或返回质量闭环继续修复。",
  finalize: "写入发布结果，结束本次课程生产。",
  inspect: "审阅已有课程的目标章节与质量证据。",
  approve_review: "人工确认既有课程的审阅结果。",
  finish: "完成既有课程 Review。",
  stop: "安全停止当前 Run，保留已持久化的状态。",
};

const agentLabels: Record<string, string> = {
  "mission.agent": "任务定义 Agent",
  "research.agent": "资料研究 Agent",
  "blueprint.agent": "课程设计 Agent",
  "writer.agent": "章节写作 Agent",
  "reviewer.agent": "教学审校 Agent",
  "repair.agent": "定向修复 Agent",
  "presenter.agent": "结果呈现 Agent",
};

const toolLabels: Record<string, string> = {
  "course.source_contract": "正文结构检查",
  "course.build": "课程构建",
  "course.validate": "课程校验",
  "workspace.patch": "工作区增量写入",
};

function describeNode(node: WorkflowNode) {
  return nodeSummaries[node.id] || "执行该阶段定义的受控工作。";
}

function describeAgents(agents: string[]) {
  return agents.map((agent) => agentLabels[agent] || agent).join(" · ");
}

function describeTools(tools: string[]) {
  return tools.map((tool) => toolLabels[tool] || tool).join(" · ");
}

function executionModeForNode(node: WorkflowNode): ExecutionMode {
  if (node.execution_mode) return node.execution_mode;
  if (["intake", "finalize", "finish", "stop"].includes(node.id)) return "system";
  if (node.id.startsWith("approve_") || node.id === "release_approval" || node.id === "request_batch_review") return "approval";
  if (node.agents.length > 0 && node.tools.length > 0) return "hybrid";
  if (node.agents.length > 0) return "llm";
  return "deterministic";
}

function WorkflowCanvasNode({ data }: NodeProps<Node<WorkflowCanvasNodeData>>) {
  const node = data as WorkflowCanvasNodeData;
  const executionMode = executionModeForNode(node);
  const isAgent = executionMode === "llm" || executionMode === "hybrid";
  const Icon = isAgent ? Bot : executionMode === "approval" ? Hand : executionMode === "deterministic" ? ShieldCheck : GitBranch;
  return <div className={`workflow-canvas-node ${executionMode} ${node.active ? "active" : ""}`}>
    {portOffsets.map((offset, index) => <Handle id={`left-${index}`} key={`left-${index}`} type="target" position={Position.Left} style={{ top: `${offset}%` }} />)}
    <Handle id="top" type="target" position={Position.Top} />
    <div className="workflow-canvas-node-kind"><Icon size={13} /><span>{modeLabels[executionMode]}</span><small>{modeDescriptions[executionMode]}</small></div>
    <strong>{node.title}</strong>
    <p>{describeNode(node)}</p>
    {node.agents.length > 0 && <small className="workflow-canvas-agent">{describeAgents(node.agents)}</small>}
    {node.tools.length > 0 && <small className="workflow-canvas-tool">{describeTools(node.tools)}</small>}
    {portOffsets.map((offset, index) => <Handle id={`right-${index}`} key={`right-${index}`} type="source" position={Position.Right} style={{ top: `${offset}%` }} />)}
    <Handle id="bottom" type="source" position={Position.Bottom} />
  </div>;
}

function PhaseFrame({ data }: NodeProps<Node<{ index: number; title: string; description: string }>>) {
  const frame = data as { index: number; title: string; description: string };
  return <div className="workflow-phase-frame"><span>阶段 {String(frame.index + 1).padStart(2, "0")}</span><strong>{frame.title}</strong><small>{frame.description}</small></div>;
}

const workflowNodeTypes = { workflow: WorkflowCanvasNode, phase: PhaseFrame };

const portOffsets = [18, 39, 61, 82];

type EdgeTone = "mainline" | "approval" | "branch" | "stop";

function edgeTone(edge: WorkflowTopology["edges"][number], source?: WorkflowNode, target?: WorkflowNode): EdgeTone {
  if (edge.label === "停止" || target?.id === "stop") return "stop";
  if (/修改|修复|重试|审计|重新同步|刷新|人工/.test(edge.label)) return "branch";
  if (source?.execution_mode === "approval" || target?.execution_mode === "approval") return "approval";
  return "mainline";
}

function buildCanvasGraph(topology: WorkflowTopology, currentStep?: string) {
  const phaseWidth = 300;
  const phaseGap = 120;
  const phaseTop = 88;
  const nodeHeight = 144;
  const nodeGap = 42;
  const phaseNodes = new Map(topology.phases.map(([id]) => [
    id, topology.nodes.filter((node) => node.phase === id && node.id !== "stop"),
  ]));
  const canvasNodes: Node[] = [];
  const visibleEdges = topology.edges.filter(
    (edge) => edge.from !== "START" && edge.to !== "END" && edge.to !== "stop",
  );
  const outgoingPorts = new Map<string, number>();
  const incomingPorts = new Map<string, number>();
  const nodeOrder = new Map(
    [...phaseNodes.values()].flatMap((nodes) => nodes.map((node, index) => [node.id, index])),
  );

  topology.phases.forEach(([phase, title, description], index) => {
    const children = phaseNodes.get(phase) || [];
    const height = Math.max(204, 70 + children.length * (nodeHeight + nodeGap));
    const frameId = `phase:${phase}`;
    canvasNodes.push({
      id: frameId, type: "phase", position: { x: 60 + index * (phaseWidth + phaseGap), y: phaseTop },
      data: { index, title, description }, draggable: false, selectable: false,
      style: { width: phaseWidth, height, zIndex: -1 },
    });
    children.forEach((node, nodeIndex) => canvasNodes.push({
      id: node.id, type: "workflow", parentId: frameId, extent: "parent",
      position: { x: 16, y: 58 + nodeIndex * (nodeHeight + nodeGap) },
      data: { ...node, execution_mode: executionModeForNode(node), active: currentStep === node.phase },
      style: { width: phaseWidth - 32, height: nodeHeight },
    }));
  });

  const edges: Edge[] = visibleEdges
    .map((edge) => {
      const source = topology.nodes.find((node) => node.id === edge.from);
      const target = topology.nodes.find((node) => node.id === edge.to);
      const samePhase = Boolean(source && target && source.phase === target.phase);
      const verticalSequence = Boolean(
        samePhase
        && (nodeOrder.get(edge.to) || 0) > (nodeOrder.get(edge.from) || 0),
      );
      const isForward = Boolean(source && target && topology.phases.findIndex(([id]) => id === target.phase) > topology.phases.findIndex(([id]) => id === source.phase));
      const sourcePort = outgoingPorts.get(edge.from) || 0;
      const targetPort = incomingPorts.get(edge.to) || 0;
      outgoingPorts.set(edge.from, sourcePort + 1);
      incomingPorts.set(edge.to, targetPort + 1);
      const tone = edgeTone(edge, source, target);
      const labelColors = {
        mainline: "#46613d",
        approval: "#96651e",
        branch: "#6e7c2d",
        stop: "#8a594e",
      };
      return {
        id: `${edge.from}-${edge.to}-${edge.label}`, source: edge.from, target: edge.to,
        sourceHandle: verticalSequence ? "bottom" : `right-${sourcePort % portOffsets.length}`,
        targetHandle: verticalSequence ? "top" : `left-${targetPort % portOffsets.length}`,
        type: verticalSequence ? "straight" : "smoothstep",
        label: edge.label,
        animated: tone === "branch" || edge.from === edge.to || !isForward,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        className: `workflow-canvas-edge ${isForward ? tone : tone === "mainline" ? "branch" : tone}`,
        labelStyle: { fill: labelColors[tone], fontSize: 10, fontWeight: 800 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.94 }, labelBgPadding: [5, 3], labelBgBorderRadius: 4,
      };
    });
  return { canvasNodes, edges };
}

function WorkflowDiagram({ topology, currentStep }: { topology: WorkflowTopology; currentStep?: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const { canvasNodes, edges } = useMemo(() => buildCanvasGraph(topology, currentStep), [topology, currentStep]);
  const selected = topology.nodes.find((node) => node.id === selectedId);
  const selectedMode = selected && executionModeForNode(selected);
  const stopSources = topology.edges
    .filter((edge) => edge.to === "stop")
    .map((edge) => topology.nodes.find((node) => node.id === edge.from)?.title)
    .filter((title): title is string => Boolean(title));
  return <section className="workflow-canvas-wrap" aria-label="实际 Agent Workflow 有向图">
    <div className="workflow-canvas-heading"><div><span>EXECUTABLE LANGGRAPH TOPOLOGY</span><p>展示主流程、修订与质量回路。拖拽移动，滚轮缩放；使用右下角控件复位全图。</p>{stopSources.length > 0 && <small className="workflow-stop-summary">可随时停止的人工出口：{stopSources.join("、")}。</small>}</div><div className="workflow-canvas-legend"><span className="llm"><Bot size={12} />LLM Agent</span><span className="hybrid"><Bot size={12} />LLM + 精确校验</span><span className="deterministic"><ShieldCheck size={12} />精确任务</span><span className="approval"><Hand size={12} />人工闸门</span><span className="system"><GitBranch size={12} />系统节点</span></div><div className="workflow-route-legend"><span className="mainline">主线</span><span className="approval">人工决策</span><span className="branch">返工 / 修复</span></div><button className="workflow-canvas-toggle" type="button" aria-expanded={!collapsed} onClick={() => setCollapsed((value) => !value)}>{collapsed ? "展开实际拓扑" : "收起实际拓扑"}<ChevronDown className={collapsed ? "collapsed" : ""} size={15} /></button></div>
    {!collapsed && <><div className="workflow-canvas">
      <ReactFlow nodes={canvasNodes} edges={edges} nodeTypes={workflowNodeTypes} fitView minZoom={0.2} maxZoom={1.65} nodesDraggable={false} onNodeClick={(_, node) => !node.id.startsWith("phase:") && setSelectedId(node.id)}>
        <Background gap={18} size={1} color="#dce4d7" />
        <MiniMap zoomable pannable nodeColor={(node) => ({ llm: "#a8d737", hybrid: "#63a889", deterministic: "#6f89d2", approval: "#d69c45", system: "#89958e" }[String(node.data.execution_mode) as ExecutionMode] || "#c9d2c4")} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
    {selected && selectedMode && <aside className="workflow-node-inspector"><div><span>{modeLabels[selectedMode]}</span><h3>{selected.title}</h3><p>{describeNode(selected)}</p></div><p>{selected.agents.length ? `参与角色：${describeAgents(selected.agents)}。` : "不调用 LLM；"}{selected.tools.length ? `受控能力：${describeTools(selected.tools)}。` : "不调用 Tool Runtime。"}</p><small>下一步：{topology.edges.filter((edge) => edge.from === selected.id).map((edge) => `${edge.label} → ${edge.to}`).join("；") || "无（终止节点）"}<br />实现定位：<code>{selected.handler} · {selected.id}</code></small></aside>}</>}
  </section>;
}

export function WorkflowMap({ steps, currentStep, runStatus, selectedStep, onSelect }: { steps: RunDetail["workflow_steps"]; currentStep: string; runStatus?: string; selectedStep: string; onSelect: (id: string) => void }) {
  return <nav className="workflow-map" aria-label="课程生成流程">{steps.map((step, index) => {
    const isRunning = currentStep === step.id && step.status === "active" && runStatus === "RUNNING";
    return <div className="workflow-map-segment" key={step.id}><button className={`workflow-node ${step.status} ${selectedStep === step.id ? "selected" : ""} ${isRunning ? "is-running" : ""}`} onClick={() => onSelect(step.id)} aria-current={currentStep === step.id ? "step" : undefined}><span className="node-index">{step.status === "completed" ? <Check size={14} /> : isRunning ? <LoaderCircle className="spin" size={15} /> : index + 1}</span><span><strong>{step.title}</strong><small>{isRunning ? "Agent 运行中" : currentStep === step.id && step.status === "active" ? "当前节点" : step.status === "completed" ? "已完成" : "未开始"}</small></span></button>{index < steps.length - 1 && <ChevronRight className="map-arrow" size={17} />}</div>;
  })}</nav>;
}

export function StepStatus({ status, runStatus }: { status: string; runStatus?: string }) {
  if (status === "active" && runStatus === "RUNNING") return <span className="step-status running"><LoaderCircle className="spin" size={14} />Running</span>;
  if (status === "active" && runStatus === "WAITING_APPROVAL") return <span className="step-status waiting">等待确认</span>;
  return <span className={`step-status ${status}`}>{status === "completed" ? "已完成" : status === "pending" ? "未开始" : "进行中"}</span>;
}
