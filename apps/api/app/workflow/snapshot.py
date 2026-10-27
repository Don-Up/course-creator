"""The projection of the executable graph for the outside world.

The snapshot is what the browser and every other consumer of the workflow
sees: the phases, the nodes and the transitions between the nodes.  It is
a *projection* of `app.workflow.graph` and not a second description of the
workflow: everything in it is read out of the graph, so the graph stays the
only place where the topology is written down.

A stage of the graph is a phase of the snapshot.  The two words are used
apart on purpose: the graph speaks of the stages the runtime walks, the
snapshot speaks of the phases a person sees.

The projection is deliberately dumb.  It copies what the graph says and
adds nothing: a phase the graph does not know is not in the answer, and a
node the graph grows shows up in the answer as well.  The source of this
module therefore names no phase of its own -- the test
`test_snapshot_module_names_no_phase_of_its_own` keeps it that way.
"""

from __future__ import annotations

from typing import Any

from app.workflow.graph import WorkflowGraph, WorkflowStage, build_course_graph

# The version of the shape of the answer.  A consumer that reads an older
# shape can tell the two apart by this number.
SNAPSHOT_VERSION = 1


def workflow_snapshot(graph: WorkflowGraph | None = None) -> dict[str, Any]:
    """Read the topology of the workflow out of its graph.

    Args:
        graph: The graph to project, for example a graph that a test grew
            by one node.  The graph of the course workflow when it is not
            given.

    Returns:
        The topology as a dictionary: the version of the shape, the id and
        the name of the workflow, the phases with the nodes they hold, the
        nodes with the phase they belong to, and the transitions between
        the nodes.  For example
        `{"version": 1, "id": "course", "name": "...",
        "phases": [...], "nodes": [...], "edges": [...]}`.
    """
    the_graph = graph if graph is not None else build_course_graph()
    return {
        "version": SNAPSHOT_VERSION,
        "id": the_graph.id,
        "name": the_graph.name,
        "phases": [_phase_read(stage, the_graph) for stage in the_graph.stages],
        "nodes": [
            {
                "id": node.id,
                "stage": node.stage,
                "title": node.title,
                "description": node.description,
                "position": position,
            }
            for position, node in enumerate(the_graph.nodes)
        ],
        "edges": [
            {"source": edge.source, "target": edge.target}
            for edge in the_graph.edges
        ],
    }


def _phase_read(stage: WorkflowStage, graph: WorkflowGraph) -> dict[str, Any]:
    """Read one phase of the workflow out of the graph.

    Args:
        stage: The stage the phase is about, for example the stage that
            plans the batches.
        graph: The graph the nodes of the phase are read from.

    Returns:
        The phase as a dictionary: the id, the title, the description, what
        the person has to give and what the model answers, and the ids of
        the nodes that belong to the phase.  For example
        `{"id": "...", "title": "...", "description": "...",
        "user_input": "...", "model_output": "...", "nodes": ["..."]}`.
    """
    return {
        "id": stage.id,
        "title": stage.title,
        "description": stage.description,
        "user_input": stage.user_input,
        "model_output": stage.model_output,
        "nodes": [node.id for node in graph.nodes_of(stage.id)],
    }
