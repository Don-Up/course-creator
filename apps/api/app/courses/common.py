from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from app.config import Settings, get_settings

def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)

def _safe_course_root(slug: str, settings: Settings | None = None) -> Path:
    config = settings or get_settings()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("课程 slug 不合法")
    root = (config.courses_root / slug).resolve()
    if root.parent != config.courses_root.resolve():
        raise ValueError("课程目录越界")
    return root


def _safe_child(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if root.resolve() not in target.parents:
        raise ValueError("文件路径越界")
    return target
