from app.workflow.services.repair_rounds import (
    defer_current_round_discoveries,
    upsert_round_chapter_result,
)


def test_round_summary_keeps_only_the_latest_result_for_each_chapter():
    results = [{
        "chapter": 2,
        "passed": False,
        "remaining_issues": ["构建诊断"],
    }]

    updated = upsert_round_chapter_result(
        results,
        {"chapter": 2, "passed": True, "remaining_issues": []},
    )

    assert updated == [{"chapter": 2, "passed": True, "remaining_issues": []}]


def test_new_findings_for_already_processed_chapters_wait_for_next_round():
    immediate, deferred = defer_current_round_discoveries(
        [
            {"chapter": 2, "issues": ["新语义问题"]},
            {"chapter": 4, "issues": ["未处理章节的问题"]},
        ],
        seen_chapters={2},
    )

    assert immediate == [{"chapter": 4, "issues": ["未处理章节的问题"]}]
    assert deferred == [{"chapter": 2, "issues": ["新语义问题"]}]
