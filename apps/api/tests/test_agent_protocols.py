"""Contract tests for the `CourseAgent` protocol.

The protocol freezes the agent capability boundary: the method set is a
contract rather than an implementation detail, so the tests pin the exact
attribute names instead of merely checking that the class exists.  P1.2
introduces `name` plus ten methods; the remaining seven methods arrive in
P3.8 together with their output schemas, and until then the attribute set
must stay at eleven entries.
"""

from __future__ import annotations

from typing import Protocol

from app.agents.protocols import CourseAgent

EXPECTED_METHODS = frozenset(
    {
        "create_mission",
        "create_blueprint",
        "plan_research",
        "curate_research",
        "generate_chapter",
        "humanize",
        "semantic_review",
        "extract_continuity",
        "plan_repair",
        "present_output",
    }
)

EXPECTED_PROTOCOL_ATTRS = {"name"} | EXPECTED_METHODS


def test_course_agent_is_a_protocol():
    """`CourseAgent` describes a capability boundary, it is not a base class."""
    assert issubclass(CourseAgent, Protocol)
    assert getattr(CourseAgent, "_is_protocol", False) is True


def test_course_agent_exposes_exactly_the_agreed_attributes():
    """Only `name` and the ten P1.2 methods exist at this phase."""
    assert CourseAgent.__protocol_attrs__ == EXPECTED_PROTOCOL_ATTRS
    assert len(CourseAgent.__protocol_attrs__) == 11


def test_course_agent_declares_every_expected_method():
    """Each agreed method is declared by the protocol itself."""
    for method_name in EXPECTED_METHODS:
        assert method_name in CourseAgent.__protocol_attrs__
        assert callable(getattr(CourseAgent, method_name))
