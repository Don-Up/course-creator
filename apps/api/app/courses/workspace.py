from __future__ import annotations

import base64
import binascii
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.courses.common import _safe_child, _safe_course_root, content_hash

WORKSPACE_EDITABLE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
WORKSPACE_UPLOAD_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".pdf", ".docx", ".pptx", ".xlsx", ".csv"
}
MAX_WORKSPACE_RESOURCE_BYTES = 20 * 1024 * 1024


def _default_resources_markdown() -> str:
    return (
        "# 课程资源\n\n"
        "## 来源政策\n\n"
        "待课程任务定义确认后写入。\n\n"
        "## 检索范围与使用边界\n\n"
        "- Agent 会围绕课程核心概念、所用框架或工具的当前 API、相关标准或论文、项目实践与部署/安全边界检索资料。\n"
        "- 每一条资料都必须说明其支撑的教学内容；关键事实、API 用法和规范不得只依赖未核验的社区文章。\n"
        "- 资料是否可用以来源政策为准：只有政策允许时，才将社区教程作为补充阅读。\n\n"
        "## Agent 检索与核验\n\n"
        "任务定义确认后，Agent 会在这里写入检索计划、经筛选的资料和仍需人工补充的缺口。\n\n"
        "## 用户补充资源\n\n"
        "可在此登记链接、课程资料说明或上传附件的使用目的。\n"
    )


def _workspace_root(slug: str) -> Path:
    course_root = _safe_course_root(slug)
    if not course_root.is_dir():
        raise FileNotFoundError(slug)
    root = course_root / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_workspace_file(slug: str, relative_path: str) -> Path:
    root = _workspace_root(slug)
    if not relative_path or relative_path.startswith(".agent-history"):
        raise ValueError("Workspace 文件路径不合法")
    return _safe_child(root, relative_path)


def _ensure_workspace_defaults(root: Path) -> None:
    resources = root / "RESOURCES.md"
    if not resources.exists():
        resources.write_text(_default_resources_markdown(), encoding="utf-8")


def list_workspace_files(slug: str) -> list[dict[str, Any]]:
    root = _workspace_root(slug)
    _ensure_workspace_defaults(root)
    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".agent-history" in path.parts:
            continue
        items.append(
            {
                "path": str(path.relative_to(root)),
                "size": path.stat().st_size,
                "editable": path.suffix.lower() in WORKSPACE_EDITABLE_SUFFIXES,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            }
        )
    return items


def get_workspace_file(slug: str, relative_path: str) -> dict[str, Any]:
    path = _safe_workspace_file(slug, relative_path)
    if relative_path == "RESOURCES.md":
        _ensure_workspace_defaults(path.parent)
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    editable = path.suffix.lower() in WORKSPACE_EDITABLE_SUFFIXES
    content = path.read_text(encoding="utf-8") if editable else ""
    return {
        "path": relative_path,
        "content": content,
        "content_hash": content_hash(content) if editable else "",
        "editable": editable,
        "size": path.stat().st_size,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
    }


def update_workspace_file(
    slug: str,
    relative_path: str,
    new_content: str,
    expected_hash: str,
) -> dict[str, Any]:
    current = get_workspace_file(slug, relative_path)
    if not current["editable"]:
        raise ValueError("该文件不支持在线编辑")
    if current["content_hash"] != expected_hash:
        raise RuntimeError("Workspace 文件已发生变化，请刷新后重新编辑")
    root = _workspace_root(slug)
    source = _safe_workspace_file(slug, relative_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = root / ".agent-history" / timestamp / relative_path
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, snapshot)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=source.parent, delete=False
    ) as handle:
        handle.write(new_content)
        temporary = Path(handle.name)
    os.replace(temporary, source)
    result = get_workspace_file(slug, relative_path)
    result["snapshot_path"] = str(snapshot.relative_to(root))
    return result


_REVISION_PATCHABLE_WORKSPACE_FILES = {
    "MISSION.md",
    "COURSE-GENERATION-SPEC.md",
    "RESOURCES.md",
    "NOTES.md",
    "COURSE-BLUEPRINT.md",
}


def apply_workspace_patch_plan(
    slug: str,
    patches: list[dict[str, str]],
    *,
    reason: str,
) -> dict[str, Any]:
    """Safely apply an Agent revision plan after validating every patch.

    The complete plan is verified before writing any file. Each affected file
    receives a snapshot under one revision directory, then is atomically
    replaced. `RESOURCES.md` and `NOTES.md` only permit additive patches.
    """
    if not patches:
        raise ValueError("Workspace 增量修订未包含任何补丁")
    root = _workspace_root(slug)
    prepared: list[tuple[Path, str, str]] = []
    seen_paths: set[str] = set()
    for patch in patches:
        path_name = str(patch.get("path") or "")
        original = str(patch.get("original") or "")
        replacement = str(patch.get("replacement") or "")
        if path_name not in _REVISION_PATCHABLE_WORKSPACE_FILES:
            raise ValueError(f"不允许修改 Workspace 文件：{path_name}")
        if path_name in seen_paths:
            raise RuntimeError(f"同一文件只能包含一个增量补丁：{path_name}")
        if not original or not replacement:
            raise ValueError(f"Workspace 补丁缺少原文或替换文本：{path_name}")
        source = _safe_workspace_file(slug, path_name)
        if not source.is_file():
            raise FileNotFoundError(f"Workspace 文件不存在：{path_name}")
        current = source.read_text(encoding="utf-8")
        if current.count(original) != 1:
            raise RuntimeError(f"Workspace 补丁原文必须唯一命中：{path_name}")
        if path_name in {"RESOURCES.md", "NOTES.md"} and original not in replacement:
            raise RuntimeError(f"{path_name} 增量修订不得删除既有内容")
        prepared.append((source, current, current.replace(original, replacement, 1)))
        seen_paths.add(path_name)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    revision_root = root / ".agent-history" / timestamp
    temporary_files: list[tuple[Path, Path]] = []
    try:
        for source, _current, next_content in prepared:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=source.parent, delete=False
            ) as handle:
                handle.write(next_content)
                temporary_files.append((source, Path(handle.name)))
        for source, current, _next_content in prepared:
            snapshot = revision_root / source.relative_to(root)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_text(current, encoding="utf-8")
        for source, temporary in temporary_files:
            os.replace(temporary, source)
    except Exception:
        for _source, temporary in temporary_files:
            if temporary.exists():
                temporary.unlink()
        raise
    return {
        "changed_files": [str(source.relative_to(root)) for source, _, _ in prepared],
        "snapshot_root": str(revision_root.relative_to(root)),
        "reason": reason,
    }


def upload_workspace_resource(
    slug: str,
    filename: str,
    content_base64: str,
    media_type: str,
) -> dict[str, Any]:
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in WORKSPACE_UPLOAD_SUFFIXES:
        raise ValueError("资源文件名或格式不受支持")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("资源文件内容无效") from None
    if len(content) > MAX_WORKSPACE_RESOURCE_BYTES:
        raise ValueError("单个资源文件不能超过 20 MB")
    root = _workspace_root(slug)
    _ensure_workspace_defaults(root)
    target = _safe_child(root, f"resources/{safe_name}")
    if target.exists():
        raise FileExistsError(safe_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    resources = root / "RESOURCES.md"
    entry = (
        f"\n## 用户补充资源：{safe_name}\n\n"
        f"- 路径：`workspace/resources/{safe_name}`\n"
        f"- 类型：{media_type}\n"
        f"- 大小：{len(content)} bytes\n"
    )
    with resources.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return {
        "path": f"resources/{safe_name}",
        "size": len(content),
        "media_type": media_type,
        "resources_file": "RESOURCES.md",
    }


def append_workspace_resource_note(slug: str, content: str) -> dict[str, Any]:
    root = _workspace_root(slug)
    _ensure_workspace_defaults(root)
    note = content.strip()
    if not note:
        raise ValueError("资源内容不能为空")
    resources = root / "RESOURCES.md"
    with resources.open("a", encoding="utf-8") as handle:
        handle.write("\n" + note.rstrip() + "\n")
    return get_workspace_file(slug, "RESOURCES.md")
