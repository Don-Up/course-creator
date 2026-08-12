from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.agents.protocols import CourseAgent
from app.workflow.node_context import WorkflowContext
from app.workflow.nodes.review import create_review_nodes
from app.workflow.services.context_packs import _projected
from app.workflow.state import CourseAgentState


def build_review_graph(run_id: str, provider: CourseAgent, checkpointer):
    """Compile the focused historical-course review graph."""
    context = WorkflowContext(run_id, provider, get_settings())
    nodes = create_review_nodes(context)
    builder = StateGraph(CourseAgentState)
    builder.add_node("inspect", _projected(run_id, "quality", "历史课程 Review", nodes.inspect, provider))
    builder.add_node("approve_review", nodes.approve_review)
    builder.add_node("finish", nodes.finish)
    builder.add_node("stop", nodes.stop)
    builder.add_edge(START, "inspect")
    builder.add_edge("inspect", "approve_review")
    builder.add_conditional_edges("approve_review", lambda state: "stop" if state.get("approval") == "STOP" else "finish", {"finish": "finish", "stop": "stop"})
    builder.add_edge("finish", END)
    builder.add_edge("stop", END)
    return builder.compile(checkpointer=checkpointer)
