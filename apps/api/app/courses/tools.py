from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.course_contract import scan_course_contract
from app.courses.common import _safe_course_root, content_hash
from app.db import utcnow

def _build_command(slug: str) -> list[str]:
    if slug == "rag-from-beginner-to-expert":
        return ["node", "scripts/build-course.mjs"]
    if slug == "harness-engineering":
        return ["node", "scripts/build-harness-course.mjs"]
    if slug == "java-web-backend-from-beginner-to-advanced":
        return ["node", "scripts/build-java-web-course.mjs"]
    if slug == "langchain-langgraph-from-beginner-to-advanced":
        return ["/opt/homebrew/bin/python3.12", "build.py"]
    return ["node", "scripts/build-static-course.mjs", slug]


def _batch_markdown_paths(root: Path, chapter_numbers: list[int]) -> list[str]:
    """Resolve the Markdown sources that belong to one production batch."""
    metadata_path = root / "course.json"
    try:
        lessons = json.loads(metadata_path.read_text(encoding="utf-8")).get("lessons", [])
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("无法读取批次课程元数据") from error
    requested = {int(number) for number in chapter_numbers}
    paths = {
        int(lesson["number"]): str(lesson["markdown"])
        for lesson in lessons
        if isinstance(lesson, dict)
        and lesson.get("number") is not None
        and isinstance(lesson.get("markdown"), str)
    }
    missing = sorted(requested - paths.keys())
    if missing:
        raise ValueError(f"批次章节缺少 Markdown 产物：{', '.join(map(str, missing))}")
    return [paths[number] for number in sorted(requested)]


def run_course_tool(
    slug: str,
    action: str,
    *,
    chapter_numbers: list[int] | None = None,
) -> dict[str, Any]:
    """Run a course tool, optionally scoped to one autonomous batch.

    Batch quality must never inherit failures from chapters that have not yet
    been produced (or belong to a different batch).  A full-course invocation
    remains available to the final quality closure and release gate.
    """
    settings = get_settings()
    root = _safe_course_root(slug)
    if not root.exists():
        raise FileNotFoundError(slug)
    batch_numbers = sorted({int(number) for number in chapter_numbers or []})
    if action == "source_contract":
        lesson_paths = _batch_markdown_paths(root, batch_numbers) if batch_numbers else None
        report = scan_course_contract(slug, lesson_paths)
        payload = report.model_dump(mode="json", by_alias=False)
        hashes = [str(item.get("hash") or "") for item in payload.get("lessons", [])]
        source_revision = hashes[0] if len(hashes) == 1 else content_hash("|".join(hashes))
        diagnostics = payload.get("diagnostics", [])
        return {
            "action": action,
            "scope": {"chapter_numbers": batch_numbers} if batch_numbers else {"scope": "course"},
            "source_revision": source_revision,
            "build_revision": None,
            "diagnostics": diagnostics,
            "report": payload,
            "succeeded": not any(item.get("severity", "error") == "error" for item in diagnostics),
        }
    if action == "build":
        command = _build_command(slug)
        if batch_numbers:
            # New Agent-created courses use the generic static builder. Its
            # chapter selector renders only this batch while leaving the
            # course-level index and glossary intact.
            if command[:2] == ["node", "scripts/build-static-course.mjs"]:
                command = [*command, "--chapters", ",".join(map(str, batch_numbers))]
            else:
                raise ValueError("该历史课程构建器暂不支持按批次构建")
        cwd = (
            root
            if slug == "langchain-langgraph-from-beginner-to-advanced"
            else settings.repo_root
        )
    elif action in {"validate", "validate_artifacts"}:
        command = [
            "node",
            ".agents/skills/teach-generator/scripts/validate-course.mjs",
            str(root),
        ]
        if action == "validate_artifacts":
            try:
                course = json.loads((root / "course.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("无法读取课程元数据以验证构建产物") from exc
            generated = ["index.html"]
            for lesson in course.get("lessons", []):
                if batch_numbers and int(lesson.get("number") or 0) not in batch_numbers:
                    continue
                href = lesson.get("href")
                if isinstance(href, str) and (root / href).exists():
                    generated.append(href)
            for path in generated:
                command.extend(["--include", path])
            command.append("--no-write")
        elif batch_numbers:
            for path in _batch_markdown_paths(root, batch_numbers):
                command.extend(["--include", path])
            # Batch reports are persisted by the workflow under their own
            # batch id; never overwrite the course-wide deterministic report.
            command.append("--no-write")
        cwd = settings.repo_root
    else:
        raise ValueError("不支持的课程工具")
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    source_files = _batch_markdown_paths(root, batch_numbers) if batch_numbers else [
        str(path.relative_to(root)) for path in sorted((root / "lessons").glob("*.md"))
    ] if (root / "lessons").exists() else []
    source_revision = content_hash("|".join(
        content_hash((root / path).read_text(encoding="utf-8"))
        for path in source_files if (root / path).exists()
    ))
    return {
        "action": action,
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
        "succeeded": result.returncode == 0,
        "source_revision": source_revision,
        "build_revision": utcnow() if action == "build" and result.returncode == 0 else None,
        "diagnostics": [],
        "scope": {"chapter_numbers": batch_numbers} if batch_numbers else {"scope": "course"},
    }
