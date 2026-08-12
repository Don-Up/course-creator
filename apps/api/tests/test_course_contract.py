import json
from types import SimpleNamespace

import pytest

from app import course_contract


def test_scan_contract_returns_all_structured_diagnostics(monkeypatch):
    payload = {
        "schemaVersion": "1.0",
        "courseRoot": "/repo/courses/test-course",
        "lessons": [],
        "diagnostics": [
            {"code": "REFERENCE_SECTION_MISSING", "path": "lessons/01.md", "line": 8, "severity": "error", "actual": "本章参考文献", "expected": "## 参考文献", "repairCapability": "reference_role_classification", "successCriteria": ["统一标题"], "nodeId": None},
            {"code": "INTRO_NON_CANONICAL", "path": "lessons/02.md", "line": 1, "severity": "error", "actual": "plain", "expected": "blockquote", "repairCapability": "intro_contract", "successCriteria": ["标准章首"], "nodeId": None},
        ],
    }
    monkeypatch.setattr(
        course_contract.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    report = course_contract.scan_course_contract("test-course")
    assert [item.code for item in report.diagnostics] == [
        "REFERENCE_SECTION_MISSING",
        "INTRO_NON_CANONICAL",
    ]


def test_normalize_reference_rejects_path_outside_course():
    with pytest.raises(ValueError, match="课程目录"):
        course_contract.normalize_reference_heading(
            "test-course", "../other.md", "heading:10", "a" * 64
        )
