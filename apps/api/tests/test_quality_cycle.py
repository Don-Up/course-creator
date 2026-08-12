import pytest

from app.workflow.quality_cycle import (
    chapter_repair_sweep_tasks,
    detect_quality_regressions,
    merge_same_cycle_discoveries,
    merge_repair_queue,
    refund_legacy_semantic_rollback_attempts,
    mark_task_verified,
    merge_contract_report,
    next_cycle_action,
    plan_escalation,
    start_quality_cycle,
)


def diagnostic(code, path, *, actual="bad", node_id=None, severity="error"):
    return {
        "code": code, "path": path, "actual": actual, "node_id": node_id,
        "severity": severity, "line": 1, "success_criteria": ["rule passes"],
    }


def report(diagnostics, *, hashes=None):
    return {"diagnostics": diagnostics, "lessons": hashes or []}


def test_new_problem_is_added_to_the_current_cycle():
    state = start_quality_cycle("cycle-1", [diagnostic("INTRO_NON_CANONICAL", "lessons/01.md")])
    state = mark_task_verified(
        state,
        state["queue"][0]["id"],
        verification={
            "diagnostic_code": "INTRO_NON_CANONICAL", "outcome": "passed",
            "source_revision": "rev-1", "verified_at": "now",
        },
    )
    merged = merge_contract_report(
        state, report([diagnostic("REFERENCE_SECTION_MISSING", "lessons/04.md")])
    )
    assert merged["cycle_id"] == "cycle-1"
    assert merged["iteration"] == 2
    assert [task["code"] for task in merged["queue"]] == ["REFERENCE_SECTION_MISSING"]
    assert merged["new_issue_count"] == 1


def test_task_cannot_close_before_its_rule_passes():
    state = start_quality_cycle("cycle-1", [diagnostic("REFERENCE_SECTION_MISSING", "04.md")])
    with pytest.raises(ValueError, match="规则复验"):
        mark_task_verified(state, state["queue"][0]["id"], verification=None)


def test_two_identical_no_progress_scans_escalate():
    state = start_quality_cycle("cycle-1", [diagnostic("INTRO_NON_CANONICAL", "01.md")])
    state["no_progress_count"] = 2
    state["escalation_level"] = "deterministic"
    assert next_cycle_action(state) == "escalate"


def test_clean_source_build_and_artifact_gates_release():
    state = start_quality_cycle("cycle-1", [])
    state["source_gate"] = {"passed": True}
    state["build_gate"] = {"passed": True}
    state["artifact_gate"] = {"passed": True}
    assert next_cycle_action(state) == "release"


def test_escalation_is_bounded_and_chapter_rewrite_requires_structural_damage():
    assert plan_escalation({}, previous="deterministic")["level"] == "llm_patch"
    assert plan_escalation({}, previous="llm_patch")["level"] == "section_rewrite"
    assert plan_escalation({}, previous="section_rewrite")["level"] == "pause"
    result = plan_escalation({"structural_damage": True}, previous="section_rewrite")
    assert result["level"] == "chapter_rewrite"
    assert set(result["required_gates"]) == {
        "effective_chars", "humanizer", "semantic", "continuity", "source_contract", "build"
    }


def test_semantic_findings_are_added_to_the_same_persistent_cycle_queue():
    queue, added, deferred = merge_repair_queue(
        [],
        [{
            "chapter": 8,
            "path": "lessons/08.md",
            "issues": ["[minor] 缺少向量检索示例"],
            "task_ids": ["task-new"],
        }],
        attempts={},
        max_attempts=2,
    )

    assert [item["issues"] for item in queue] == [["[minor] 缺少向量检索示例"]]
    assert added == ["task-new"]
    assert deferred == []


def test_same_cycle_discovery_budget_defers_new_tasks_after_two_sweeps():
    queue, added, deferred, sweeps = merge_same_cycle_discoveries(
        [],
        [{
            "chapter": 8,
            "path": "lessons/08.md",
            "issues": ["问题 A"],
            "task_ids": ["task-a"],
        }],
        attempts={},
        max_attempts=2,
        discovery_sweeps=2,
        max_discovery_sweeps=2,
    )

    assert queue == []
    assert added == []
    assert deferred == ["task-a"]
    assert sweeps == 2


def test_same_cycle_queue_deduplicates_findings_and_defers_only_exhausted_tasks():
    current = [{
        "chapter": 8,
        "path": "lessons/08.md",
        "issues": ["问题 A"],
        "task_ids": ["task-a"],
    }]
    queue, added, deferred = merge_repair_queue(
        current,
        [
            {"chapter": 8, "path": "lessons/08.md", "issues": ["问题 A"], "task_ids": ["task-a"]},
            {"chapter": 8, "path": "lessons/08.md", "issues": ["问题 B"], "task_ids": ["task-b"]},
        ],
        attempts={"task-a": 1, "task-b": 2},
        max_attempts=2,
    )

    assert len(queue) == 1
    assert queue[0]["task_ids"] == ["task-a"]
    assert added == []
    assert deferred == ["task-b"]


def test_same_chapter_findings_are_grouped_into_one_repair_sweep():
    queue, added, deferred = merge_repair_queue(
        [],
        [
            {
                "chapter": 8,
                "path": "lessons/08.md",
                "issues": ["问题 A", "问题 B"],
                "task_ids": ["task-a", "task-b"],
                "repair_agents": ["Agent A"],
            },
            {
                "chapter": 8,
                "path": "lessons/08.md",
                "issues": ["问题 C"],
                "task_ids": ["task-c"],
                "repair_agents": ["Agent B"],
            },
            {
                "chapter": 9,
                "path": "lessons/09.md",
                "issues": ["问题 D"],
                "task_ids": ["task-d"],
            },
        ],
        attempts={},
        max_attempts=2,
    )

    assert len(queue) == 2
    assert queue[0]["chapter"] == 8
    assert queue[0]["issues"] == ["问题 A", "问题 B", "问题 C"]
    assert queue[0]["task_ids"] == ["task-a", "task-b", "task-c"]
    assert queue[0]["repair_agents"] == ["Agent A", "Agent B"]
    assert queue[1]["chapter"] == 9
    assert added == ["task-a", "task-b", "task-c", "task-d"]
    assert deferred == []


def test_exhausted_task_is_deferred_without_splitting_other_tasks_in_chapter_sweep():
    queue, added, deferred = merge_repair_queue(
        [],
        [{
            "chapter": 8,
            "path": "lessons/08.md",
            "issues": ["问题 A", "问题 B", "问题 C"],
            "task_ids": ["task-a", "task-b", "task-c"],
        }],
        attempts={"task-b": 2},
        max_attempts=2,
    )

    assert len(queue) == 1
    assert queue[0]["issues"] == ["问题 A", "问题 C"]
    assert queue[0]["task_ids"] == ["task-a", "task-c"]
    assert added == ["task-a", "task-c"]
    assert deferred == ["task-b"]


def test_chapter_repair_sweep_preserves_every_task_and_its_own_issue():
    tasks = chapter_repair_sweep_tasks(
        {
            "issues": ["问题 A", "问题 B", "问题 C"],
            "task_ids": ["task-a", "task-b", "task-c"],
        },
        active_task_ids=["task-a", "task-b", "task-c"],
    )

    assert tasks == [
        {"task_id": "task-a", "issue": "问题 A"},
        {"task_id": "task-b", "issue": "问题 B"},
        {"task_id": "task-c", "issue": "问题 C"},
    ]


def test_previously_passing_gates_cannot_regress_during_targeted_repair():
    regressions = detect_quality_regressions(
        before={
            "effective_chars": 11000,
            "effective_char_min": 10000,
            "humanizer_score": 46,
            "semantic_decision": "ready",
            "contract_codes": [],
        },
        after={
            "effective_chars": 11200,
            "effective_char_min": 10000,
            "humanizer_score": 44,
            "semantic_decision": "ready",
            "contract_codes": ["INTRO_NON_CANONICAL"],
        },
    )

    assert regressions == [
        "Humanizer 从通过回退为未通过（46 → 44）",
        "新增 Markdown 结构违规：INTRO_NON_CANONICAL",
    ]


def test_open_ended_semantic_verdict_is_not_an_atomic_rollback_signal():
    regressions = detect_quality_regressions(
        before={
            "effective_chars": 11000,
            "effective_char_min": 10000,
            "humanizer_score": 47,
            "semantic_decision": "ready",
            "contract_codes": [],
        },
        after={
            "effective_chars": 11200,
            "effective_char_min": 10000,
            "humanizer_score": 47,
            "semantic_decision": "manual_review",
            "contract_codes": [],
        },
    )

    assert regressions == []


def test_legacy_semantic_rollback_attempt_is_refunded_once_for_resume():
    attempts, refunded = refund_legacy_semantic_rollback_attempts(
        {"task-1": 2, "task-2": 1},
        [{
            "id": "task-1",
            "verification": {
                "remaining_issues": [
                    "本次候选修复已回滚；非回归门发现：教学语义与事实审校从通过回退为未通过"
                ]
            },
        }, {
            "id": "task-2",
            "verification": {"remaining_issues": ["Humanizer 44/50，低于 45"]},
        }],
        already_refunded=[],
    )

    assert attempts == {"task-1": 1, "task-2": 1}
    assert refunded == ["task-1"]
