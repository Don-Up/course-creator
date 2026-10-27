"""Tests of the workflow topology that is exported out of the graph.

The topology of the workflow is written down in exactly one place: the
graph of `app.workflow.graph`.  The snapshot is what the outside world
reads, so the tests here watch two things: that the snapshot follows the
graph, and that it never grows a second, hand written copy of the
topology of its own.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.workflow import snapshot as snapshot_module
from app.workflow.definitions import STEP_ORDER
from app.workflow.graph import GraphEdge, GraphNode, build_course_graph
from app.workflow.snapshot import workflow_snapshot


def test_snapshot_phases_are_the_seven_stages_of_the_contract():
    """The phases are the seven stages, in the order of the contract.

    The number seven and the order are a product contract, so they are
    pinned instead of being derived from the graph in the test.
    """
    snapshot = workflow_snapshot()

    assert len(snapshot["phases"]) == 7
    assert [phase["id"] for phase in snapshot["phases"]] == STEP_ORDER


def test_snapshot_nodes_come_from_the_graph_and_not_from_a_constant():
    """Every node of the snapshot is a node of the graph."""
    graph = build_course_graph()
    snapshot = workflow_snapshot(graph)

    assert [node["id"] for node in snapshot["nodes"]] == [
        node.id for node in graph.nodes
    ]
    assert [node["stage"] for node in snapshot["nodes"]] == [
        node.stage for node in graph.nodes
    ]
    assert [(edge["source"], edge["target"]) for edge in snapshot["edges"]] == [
        (edge.source, edge.target) for edge in graph.edges
    ]


def test_snapshot_follows_a_node_that_is_added_to_the_graph():
    """A node the graph grows shows up in the snapshot as well.

    This is the test that proves the snapshot is exported rather than
    written out: the node below exists nowhere but in the graph, and the
    snapshot still carries it.
    """
    graph = build_course_graph()
    graph.add_node(
        GraphNode(
            id="quality.report",
            stage="quality",
            title="质量汇总",
            description="把各批次的未达标项汇总成一份结论",
        )
    )
    snapshot = workflow_snapshot(graph)

    assert "quality.report" in [node["id"] for node in snapshot["nodes"]]
    phase = next(
        item for item in snapshot["phases"] if item["id"] == "quality"
    )
    assert "quality.report" in phase["nodes"]
    assert len(snapshot["phases"]) == 7


def test_snapshot_follows_an_edge_that_is_added_to_the_graph():
    """A transition the graph grows shows up in the snapshot as well."""
    graph = build_course_graph()
    graph.add_edge(GraphEdge(source="quality", target="generation"))
    snapshot = workflow_snapshot(graph)

    assert {"source": "quality", "target": "generation"} in snapshot["edges"]


def test_graph_refuses_a_node_of_an_unknown_stage():
    """A node that belongs to no phase of the graph is refused."""
    graph = build_course_graph()

    try:
        graph.add_node(
            GraphNode(
                id="orphan",
                stage="nowhere",
                title="没有阶段",
                description="不属于任何阶段的节点",
            )
        )
    except ValueError as error:
        assert "nowhere" in str(error)
    else:
        raise AssertionError("一个不属于任何阶段的节点应当被拒绝")


def test_snapshot_module_names_no_phase_of_its_own():
    """The snapshot module does not write the topology down a second time.

    The check reads the source of the module: a hand written copy of the
    topology would have to name the stages, and the snapshot may not.
    """
    source = Path(snapshot_module.__file__).read_text(encoding="utf-8")

    for stage_id in STEP_ORDER:
        assert f'"{stage_id}"' not in source
        assert f"'{stage_id}'" not in source

    assert "STEP_ORDER" not in source


def test_workflow_api_answers_with_the_snapshot_of_the_graph():
    """The answer of the API is the snapshot of the graph."""
    client = TestClient(app)

    answer = client.get("/api/workflow")

    assert answer.status_code == 200
    body = answer.json()
    assert len(body["phases"]) == 7
    assert [phase["id"] for phase in body["phases"]] == STEP_ORDER
    assert [node["id"] for node in body["nodes"]] == [
        node.id for node in build_course_graph().nodes
    ]
    assert len(body["edges"]) == len(body["nodes"]) - 1
