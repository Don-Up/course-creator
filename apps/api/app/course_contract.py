from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import Settings, get_settings


class ContractDiagnostic(BaseModel):
    code: str
    path: str
    node_id: str | None = Field(default=None, alias="nodeId")
    line: int = 1
    actual: str = ""
    expected: str = ""
    severity: Literal["error", "warning"] = "error"
    repair_capability: str = Field(default="", alias="repairCapability")
    success_criteria: list[str] = Field(default_factory=list, alias="successCriteria")
    candidates: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CourseContractReport(BaseModel):
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    course_root: str = Field(default="", alias="courseRoot")
    lessons: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[ContractDiagnostic] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ContractPatchResult(BaseModel):
    changed: bool
    hash: str
    node_id: str = Field(alias="nodeId")

    model_config = {"populate_by_name": True}


def _course_root(slug: str, settings: Settings) -> Path:
    root = (settings.courses_root / slug).resolve()
    courses_root = settings.courses_root.resolve()
    if root.parent != courses_root:
        raise ValueError("目标不在课程目录内")
    return root


def _run(arguments: list[str], settings: Settings) -> dict[str, Any]:
    command = ["node", str(settings.repo_root / "scripts" / "course-structure-contract.mjs"), *arguments]
    result = subprocess.run(
        command,
        cwd=settings.repo_root,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"课程结构契约执行失败：{detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("课程结构契约未返回有效 JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("课程结构契约返回值不是对象")
    return payload


def scan_course_contract(
    slug: str, lesson_paths: list[str] | None = None, *, settings: Settings | None = None
) -> CourseContractReport:
    settings = settings or get_settings()
    root = _course_root(slug, settings)
    arguments = ["scan", "--course", str(root)]
    for path in lesson_paths or []:
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("目标不在课程目录内")
        arguments.extend(["--lesson", path])
    return CourseContractReport.model_validate(_run(arguments, settings))


def normalize_reference_heading(
    slug: str,
    path: str,
    node_id: str,
    expected_hash: str,
    *,
    settings: Settings | None = None,
) -> ContractPatchResult:
    settings = settings or get_settings()
    root = _course_root(slug, settings)
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("目标不在课程目录内")
    payload = _run(
        [
            "normalize-reference", "--course", str(root), "--file", str(target),
            "--node", node_id, "--expected-hash", expected_hash,
        ],
        settings,
    )
    return ContractPatchResult.model_validate(payload)
