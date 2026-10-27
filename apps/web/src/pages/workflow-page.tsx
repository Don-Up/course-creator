import { useQuery } from "@tanstack/react-query";

import { api, WorkflowSnapshot } from "../api";


/**
 * The page that shows the phases of the course production.
 *
 * The topology on this page is not written down here.  It is read from
 * `GET /api/workflow`, which projects the graph of the workflow in the
 * backend, so a phase the backend adds, renames or reorders shows up here
 * without a second copy to keep in step.
 *
 * @returns The page with the phases of the workflow and the transitions
 *   between them.
 */
export function WorkflowPage() {
  const topology = useQuery({
    queryKey: ["workflow"],
    queryFn: () => api.workflow(),
  });

  return (
    <section className="workflow-page">
      <p className="eyebrow">Product contract</p>
      <h1>{topology.data?.name ?? "七阶段课程生产工作流"}</h1>
      <p>这份拓扑由后端的可执行图导出，前端不再另写一份。</p>
      <p className="notice">
        当前脚手架还不执行工作流、不调用模型，也不保存运行记录；这里显示的是运行时要走的那张图。
      </p>
      {topology.isLoading && <p className="notice">正在读取工作流拓扑。</p>}
      {topology.error && (
        <p className="notice error">
          工作流拓扑读不出来：{topology.error.message}
        </p>
      )}
      {topology.data && <WorkflowPhases snapshot={topology.data} />}
    </section>
  );
}


/**
 * The phases of the workflow and the transitions that leave them.
 *
 * @param snapshot The topology as the API answered it.
 * @returns The element with the list of the phases and the number of the
 *   nodes and transitions the topology holds.
 */
function WorkflowPhases({ snapshot }: { snapshot: WorkflowSnapshot }) {
  return (
    <>
      <ol className="workflow-list">
        {snapshot.phases.map((phase, index) => (
          <li key={phase.id}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <strong>{phase.id}</strong>
              <p>{phase.description}</p>
              <p className="workflow-next">
                下一步：{nextTargets(snapshot, phase.id).join("、") || "流程结束"}
              </p>
            </div>
          </li>
        ))}
      </ol>
      <p className="workflow-counts">
        节点 {snapshot.nodes.length} 个 · 转换 {snapshot.edges.length} 条
      </p>
    </>
  );
}


/**
 * The nodes the work of one phase continues with.
 *
 * The transitions are read out of the topology, so the answer follows the
 * graph: a phase that grows a second way out shows both ways here.
 *
 * @param snapshot The topology as the API answered it.
 * @param phaseId The phase the question is about, for example "intake".
 * @returns The ids of the nodes the transitions of that phase lead to,
 *   for example ["mission"].  The list is empty at the end of the flow.
 */
function nextTargets(snapshot: WorkflowSnapshot, phaseId: string): string[] {
  const sources = new Set(
    snapshot.phases
      .filter((phase) => phase.id === phaseId)
      .flatMap((phase) => phase.nodes),
  );
  return snapshot.edges
    .filter((edge) => sources.has(edge.source))
    .map((edge) => edge.target);
}
