"""The executable topology of the course generation workflow.

A workflow is not a list of stage names: it is a graph of nodes and the
transitions between them.  This module holds that graph, and it is the one
place where the topology of the course workflow is written down.  The
snapshot of `app.workflow.snapshot` is a projection of it, and the browser
reads that projection -- so a stage that is added, renamed or reordered
here shows up everywhere, and there is no second copy to keep in step.

The graph is a plain Python object on purpose.  It says what the workflow
is, not how a run is carried out: the runtime that walks it belongs to the
phase that owns the execution, and until then the graph is the contract
that runtime is written against.  Nothing here calls a model, opens a
database or writes a file.

The stages come from `app.workflow.definitions`, which owns the wording of
the seven stages.  The graph turns that wording into nodes and transitions,
and it is the place where a stage that needs a second unit of work -- a
batch, a gate, a repair -- gets one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.workflow.definitions import WORKFLOW_STEPS


@dataclass(frozen=True)
class WorkflowStage:
    """One stage of the workflow, as the graph knows it.

    The five fields are the ones of the contract of
    `app.workflow.definitions`.  The graph does not change the wording of a
    stage; it only says where the stage sits in the topology.
    """

    id: str
    title: str
    description: str
    user_input: str
    model_output: str


@dataclass(frozen=True)
class GraphNode:
    """One unit of work of the workflow.

    A node belongs to a stage and can be visited on its own: the stage is
    the phase the person sees, the node is the piece of work the runtime
    walks.  Today the two are one for one; a stage that grows a second
    unit of work adds a node instead of a stage, and the stages of the
    workflow stay the seven the product contract names.
    """

    id: str
    stage: str
    title: str
    description: str


@dataclass(frozen=True)
class GraphEdge:
    """One transition between two nodes of the graph.

    The transition says that the work of `source` is followed by the work
    of `target`.  A later phase adds the edges that leave the flow again,
    for example the one that sends a rejected chapter back into the
    generation.
    """

    source: str
    target: str


@dataclass
class WorkflowGraph:
    """The topology of one workflow.

    The graph holds the stages, the nodes and the transitions between the
    nodes.  It can be extended: `add_node` and `add_edge` are how a later
    phase adds a unit of work without touching the code that reads the
    graph.

    The graph is built anew on every call of `build_course_graph`, so a
    caller that adds a node to it cannot change the graph another caller
    sees.
    """

    id: str
    name: str
    stages: list[WorkflowStage] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def stage(self, stage_id: str) -> WorkflowStage:
        """Find one stage of the graph.

        Args:
            stage_id: The id of the stage, for example the id of the first
                stage of the workflow.

        Returns:
            The stage with that id.
        Raises KeyError when the graph has no such stage.
        """
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        raise KeyError(stage_id)

    def node(self, node_id: str) -> GraphNode:
        """Find one node of the graph.

        Args:
            node_id: The id of the node, for example the id of the node
                that follows the first stage.

        Returns:
            The node with that id.
        Raises KeyError when the graph has no such node.
        """
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def nodes_of(self, stage_id: str) -> list[GraphNode]:
        """List the nodes that belong to one stage.

        Args:
            stage_id: The id of the stage, for example the id of the stage
                that plans the batches.

        Returns:
            The nodes of that stage, in the order they were added.  The
            list is empty when the stage has no node of its own.
        """
        return [node for node in self.nodes if node.stage == stage_id]

    def edges_from(self, node_id: str) -> list[GraphEdge]:
        """List the transitions that leave one node.

        Args:
            node_id: The id of the node, for example the id of the node
                that plans the batches.

        Returns:
            The transitions whose source is that node, in the order they
            were added.  The list is empty at the end of the flow.
        """
        return [edge for edge in self.edges if edge.source == node_id]

    def next_node(self, node_id: str) -> GraphNode | None:
        """Find the node the work continues with.

        Args:
            node_id: The id of the node, for example the id of the node
                that plans the batches.

        Returns:
            The node the first transition of that node leads to, or None
            when the node has no outgoing transition -- which is how the
            end of the flow is told from the middle of it.
        """
        edges = self.edges_from(node_id)
        if not edges:
            return None
        return self.node(edges[0].target)

    def add_node(self, node: GraphNode) -> GraphNode:
        """Add one unit of work to the graph.

        Args:
            node: The node to add, for example a node that writes the
                quality report of one chapter.

        Returns:
            The node that was added.
        Raises ValueError when the id is already taken, or when the stage
        of the node is not one of the stages of the graph.
        """
        if any(existing.id == node.id for existing in self.nodes):
            raise ValueError(f"节点标识重复：{node.id}")
        if all(stage.id != node.stage for stage in self.stages):
            raise ValueError(f"节点不属于任何阶段：{node.stage}")
        self.nodes.append(node)
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add one transition between two nodes.

        Args:
            edge: The transition to add, for example the one that sends a
                rejected chapter back into the generation.

        Returns:
            The transition that was added.
        Raises ValueError when one of the two nodes is not in the graph.
        """
        known = {node.id for node in self.nodes}
        for node_id in (edge.source, edge.target):
            if node_id not in known:
                raise ValueError(f"边指向不存在的节点：{node_id}")
        self.edges.append(edge)
        return edge


def build_course_graph() -> WorkflowGraph:
    """Build the graph of the course generation workflow.

    The stages come from the contract of `app.workflow.definitions`, in the
    order that contract gives them.  Every stage starts as one node, and
    the stages are chained: the work of a stage is followed by the work of
    the next one.

    Args:
        Nothing. The contract of the workflow stages is the only input.

    Returns:
        The graph of the course generation workflow: the seven stages of
        the contract, one node per stage and the six transitions between
        them.
    """
    stages = [
        WorkflowStage(
            id=step["id"],
            title=step["title"],
            description=step["description"],
            user_input=step["user_input"],
            model_output=step["model_output"],
        )
        for step in WORKFLOW_STEPS
    ]
    nodes = [
        GraphNode(
            id=stage.id,
            stage=stage.id,
            title=stage.title,
            description=stage.description,
        )
        for stage in stages
    ]
    edges = [
        GraphEdge(source=source.id, target=target.id)
        for source, target in zip(nodes, nodes[1:], strict=False)
    ]
    return WorkflowGraph(
        id="course",
        name="课程生成主流程",
        stages=stages,
        nodes=nodes,
        edges=edges,
    )
