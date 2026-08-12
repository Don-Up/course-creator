from types import SimpleNamespace

from app import db
from app.workflow.repository import create_run_record
from app.workflow.repository import _normalize_legacy_interrupt_artifact
from app.workflow.repair_tasks import (
    classify_quality_finding,
    create_or_refresh_task,
    normalize_quality_issue,
    reconcile_open_tasks,
    refresh_evidence,
    split_quality_issues,
)


def test_operation_failure_is_an_incident_not_a_chapter_repair_finding():
    finding = classify_quality_finding(
        "内容丰富化失败：LLM Gateway 返回了无法解析的响应",
        origin="operation",
    )

    assert finding == {
        "finding_kind": "runtime",
        "blocking": False,
        "disposition": "incident",
    }


def test_minor_semantic_finding_is_advisory():
    finding = classify_quality_finding(
        "[minor] 可移植性建议 | 证据：『tool_call[\"function\"]』",
        origin="semantic",
    )

    assert finding == {
        "finding_kind": "quality",
        "blocking": False,
        "disposition": "advisory",
    }


def test_source_contract_finding_remains_blocking_until_deterministic_verification():
    finding = classify_quality_finding(
        "[INTRO_NON_CANONICAL] 章首未形成标准引用块",
        origin="source_contract",
    )

    assert finding == {
        "finding_kind": "deterministic",
        "blocking": True,
        "disposition": "repair",
    }


def test_runtime_incident_is_excluded_from_repairable_issue_list():
    repairable, advisory, incidents = split_quality_issues(
        [
            "内容丰富化失败：LLM Gateway 返回了无法解析的响应",
            "[minor] 可移植性建议",
            "[INTRO_NON_CANONICAL] 章首未形成标准引用块",
        ]
    )

    assert repairable == ["[INTRO_NON_CANONICAL] 章首未形成标准引用块"]
    assert advisory == ["[minor] 可移植性建议"]
    assert incidents == ["内容丰富化失败：LLM Gateway 返回了无法解析的响应"]


def test_same_live_evidence_reuses_task_and_changed_source_closes_as_stale(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "agent.db"))
    create_run_record(
        "run-1", "demo", "new_course", "test", "test-model", {"scope": "new_course"}
    )
    draft = normalize_quality_issue(
        course_slug="demo",
        run_id="run-1",
        batch_id="m3-08-10",
        chapter=9,
        issue="[minor] 缺少向量检索查询示例",
        path="lessons/09-agentic.md",
        markdown="## 练习\n只演示写入，无任何查询代码。",
    )

    persisted = create_or_refresh_task(draft)

    assert persisted["status"] == "detected"
    assert create_or_refresh_task(draft)["id"] == persisted["id"]
    stale = refresh_evidence(
        persisted["id"],
        "## 练习\n已有 table.search(query).limit(5) 查询示例。",
    )
    assert stale["status"] == "stale_evidence"
    assert stale["verification"]["outcome"] == "stale_evidence"


def test_legacy_interrupt_diagnostic_is_presented_as_a_waiting_approval_record():
    normalized = _normalize_legacy_interrupt_artifact(
        {
            "source": "system",
            "title": "整课质量闭环调用诊断",
            "presentation": {"headline": "整课质量闭环未完成", "issues": ["(Interrupt(value={'type': 'COURSE_QUALITY_REVIEW'})"]},
            "raw_output": {"error": "(Interrupt(value={'type': 'COURSE_QUALITY_REVIEW'})"},
        }
    )

    assert normalized["source"] == "recovered"
    assert normalized["presentation"]["headline"] == "整课质量闭环等待确认"
    assert normalized["presentation"]["issues"] == []


def test_quality_issue_uses_its_grounded_evidence_not_an_unrelated_long_line():
    draft = normalize_quality_issue(
        course_slug="demo", run_id="run-1", batch_id="m1-01-01", chapter=4,
        issue="[minor] 维度未经核实 | 证据：『第 3 章使用的 Embedding 端点，维度 4096』 | 建议：删除数值",
        path="lessons/04.md",
        markdown="一段很长但无关的说明文字，长度远大于审校证据，不能成为 RepairTask 的修改锚点。\n第 3 章使用的 Embedding 端点，维度 4096。",
    )

    assert draft["evidence"]["quoted_source"] == "第 3 章使用的 Embedding 端点，维度 4096"


def test_ungrounded_build_issue_keeps_a_stable_retry_identity_across_body_revisions():
    first = normalize_quality_issue(
        course_slug="demo", run_id="run-1", batch_id="m1-01-01", chapter=2,
        issue="lessons/02.md：确定性构建或校验未通过；需要根据已保留的原始诊断进行章节级定向修复。",
        path="lessons/02.md", markdown="第一次正文中很长的一段内容。",
    )
    second = normalize_quality_issue(
        course_slug="demo", run_id="run-1", batch_id="m1-01-01", chapter=2,
        issue="lessons/02.md：确定性构建或校验未通过；需要根据已保留的原始诊断进行章节级定向修复。",
        path="lessons/02.md", markdown="第二次修订后另一段更长、但无关的正文内容。",
    )

    assert first["id"] == second["id"]
    assert first["evidence"]["quoted_source"] == ""


def test_fresh_course_review_closes_open_tasks_it_no_longer_reproduces(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "agent.db"))
    create_run_record(
        "run-2", "demo", "new_course", "test", "test-model", {"scope": "new_course"}
    )
    old_task = create_or_refresh_task(normalize_quality_issue(
        course_slug="demo", run_id="run-2", batch_id="m1", chapter=1,
        issue="旧构建错误", path="lessons/01.md", markdown="旧证据",
    ))
    live_task = create_or_refresh_task(normalize_quality_issue(
        course_slug="demo", run_id="run-2", batch_id="m2", chapter=2,
        issue="当前问题", path="lessons/02.md", markdown="当前证据",
    ))

    changed = reconcile_open_tasks("run-2", {live_task["id"]})

    assert changed == [old_task["id"]]
    assert refresh_evidence(old_task["id"], "旧证据")["status"] == "stale_evidence"
    assert refresh_evidence(live_task["id"], "当前证据")["status"] == "detected"
