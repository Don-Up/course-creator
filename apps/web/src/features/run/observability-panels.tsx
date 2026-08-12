import { useMemo } from "react";
import { AlertTriangle, ChevronRight, Network } from "lucide-react";
import { BudgetSnapshot, TraceProjection, TraceSpan } from "../../api";

const labels: Record<string, string> = { total_tokens: "总 Token", input_tokens: "输入 Token", output_tokens: "输出 Token", model_calls: "模型调用", estimated_cost_microusd: "估算成本（微美元）" };

const million = (value: number) => `${(value / 1_000_000).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} M`;

export function BudgetPanel({ budget }: { budget?: BudgetSnapshot }) {
  if (!budget) return <section className="execution-panel"><span className="side-label">BUDGET LEDGER</span><p>正在读取 Token 与成本观测数据…</p></section>;
  const exceeded = budget.status === "EXCEEDED";
  const limit = budget.effective_policy.max_total_tokens;
  return <section className={`budget-snapshot ${exceeded ? "is-exceeded" : ""}`} aria-label="Token 消耗">
    <div className="budget-snapshot-copy"><span className="side-label">TOKEN OBSERVATION</span><strong>Token 消耗</strong></div>
    <div className="budget-snapshot-metrics"><div><span>已用</span><strong>{million(budget.usage_totals.total_tokens)}</strong></div><div><span>阈值</span><strong>{limit ? million(limit) : "不限制"}</strong></div><div><span>调用</span><strong>{budget.usage_totals.model_calls}</strong></div></div>
    {exceeded && <p><AlertTriangle size={14}/>{budget.violations.map((item) => `${labels[item.metric] || item.metric} 已超过 ${million(item.limit)}`).join("；")}。仅记录，不影响运行。</p>}
  </section>;
}

function TraceBranch({ span, childrenByParent, depth = 0 }: { span: TraceSpan; childrenByParent: Map<string, TraceSpan[]>; depth?: number }) {
  const children = childrenByParent.get(span.id) || [];
  return <li style={{ marginLeft: depth * 14 }}><div><ChevronRight size={13}/><strong>{span.kind} · {span.name}</strong><small>{span.status}{span.duration_ms != null ? ` · ${span.duration_ms}ms` : ""}</small></div>{span.error_message && <small>{span.error_message}</small>}{children.length > 0 && <ul>{children.map((item) => <TraceBranch key={item.id} span={item} childrenByParent={childrenByParent} depth={depth + 1} />)}</ul>}</li>;
}

export function TracePanel({ trace }: { trace?: TraceProjection }) {
  const { roots, childrenByParent } = useMemo(() => {
    const children = new Map<string, TraceSpan[]>(); const ids = new Set(trace?.spans.map((span) => span.id) || []);
    for (const span of trace?.spans || []) if (span.parent_span_id && ids.has(span.parent_span_id)) children.set(span.parent_span_id, [...(children.get(span.parent_span_id) || []), span]);
    return { roots: (trace?.spans || []).filter((span) => !span.parent_span_id || !ids.has(span.parent_span_id)), childrenByParent: children };
  }, [trace]);
  return <section className="execution-panel" aria-label="统一调用链"><header><div><span className="side-label">UNIFIED TRACE</span><strong>执行 Span 树</strong></div><Network size={18}/></header>{roots.length ? <ul className="execution-history">{roots.map((span) => <TraceBranch key={span.id} span={span} childrenByParent={childrenByParent} />)}</ul> : <p>当前 Run 暂无可追踪调用；历史 Run 保持可读，不补写旧调用数据。</p>}</section>;
}
