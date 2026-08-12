"""Stable public facade for compiling the supported LangGraph workflows."""

from app.workflow.assembly.course_graph import build_course_graph
from app.workflow.assembly.review_graph import build_review_graph

__all__ = ["build_course_graph", "build_review_graph"]
