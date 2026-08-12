import { Clock3, LoaderCircle, OctagonX } from "lucide-react";
import { CommandExecution, NodeExecution, RunDetail } from "../../api";

const commandLabel: Record<string, string> = {
  START: "启动 Run",
  RESUME: "恢复审批",
  CONTINUE: "继续检查点",
  STOP: "停止 Run",
};

function time(value?: string | null) {
  return value ? new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
}

function CommandRow({ command }: { command: CommandExecution }) {
  return <li>
    <span className={`execution-dot ${command.status.toLowerCase()}`} />
    <div>
      <strong>{commandLabel[command.kind] || command.kind}</strong>
      <small>{command.status} · 第 {command.attempt_count}/{command.max_attempts} 次 · {time(command.created_at)}</small>
    </div>
  </li>;
}

function NodeRow({ node }: { node: NodeExecution }) {
  return <li>
    <span className={`execution-dot ${node.status.toLowerCase()}`} />
    <div>
      <strong>{node.node_id}</strong>
      <small>{node.status} · 第 {node.attempt_count} 次 · {time(node.started_at || node.finished_at)}</small>
    </div>
  </li>;
}

export function ExecutionPanel({ run, stopping, onStop }: { run: RunDetail; stopping: boolean; onStop: () => void }) {
  const command = run.active_command;
  const node = run.current_node_execution;
  const stoppingRequested = Boolean(command?.cancel_requested) || command?.kind === "STOP";
  const canStop = Boolean(command) && !stoppingRequested;
  return <section className="execution-panel" aria-label="Worker 执行状态">
    <header>
      <div>
        <span className="side-label">PERSISTENT EXECUTION</span>
        <strong>{command ? (stoppingRequested ? "正在请求停止" : "Worker 正在处理命令") : "当前没有活跃命令"}</strong>
      </div>
      {canStop && <button className="button secondary compact" disabled={stopping} onClick={onStop}>
        {stopping ? <LoaderCircle className="spin" size={14} /> : <OctagonX size={14} />} 停止运行
      </button>}
    </header>
    <div className="execution-current">
      <div><Clock3 size={14} /><span>Command</span><strong>{command ? `${commandLabel[command.kind] || command.kind} · ${command.status}` : "等待新的执行命令"}</strong></div>
      <div><Clock3 size={14} /><span>Node</span><strong>{node ? `${node.node_id} · ${node.status}` : "尚未进入业务节点"}</strong></div>
    </div>
    {command && <p className="execution-note">{command.leased_by ? `Worker：${command.leased_by}` : "命令已持久化，等待 Worker 领取"}{command.heartbeat_at ? ` · 最近心跳 ${time(command.heartbeat_at)}` : ""}</p>}
    <details className="execution-history">
      <summary>执行时间线 · {run.command_timeline?.length || 0} 个 Command / {run.node_execution_timeline?.length || 0} 个节点</summary>
      <div className="execution-history-grid">
        <ol>{(run.command_timeline || []).map((item) => <CommandRow key={item.id} command={item} />)}</ol>
        <ol>{(run.node_execution_timeline || []).map((item) => <NodeRow key={item.id} node={item} />)}</ol>
      </div>
    </details>
  </section>;
}
