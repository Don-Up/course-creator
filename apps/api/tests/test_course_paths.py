"""Behaviour tests for the course workspace path guards and atomic writes.

`app/courses/common.py` owns the only sanctioned way to turn a slug or a
relative path into a real filesystem path, and the only sanctioned way to
persist JSON.  The tests therefore pin behaviour rather than implementation:
illegal slugs and escaping paths must raise, legal ones must resolve inside
the course directory, and a failed atomic write must leave the previous file
untouched and no temporary file behind.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.courses.common import (
    SLUG_PATTERN,
    _safe_child,
    _safe_course_root,
    _write_json_atomic,
    content_hash,
)

INVALID_SLUG_MESSAGE = "课程 slug 不合法"
PATH_ESCAPE_MESSAGE = "文件路径越界"
EMPTY_TEXT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC_TEXT_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_slug_pattern_is_the_single_source_of_truth():
    """The pattern is shared verbatim with the API's slug validation."""
    assert SLUG_PATTERN.pattern == r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


@pytest.mark.parametrize("slug", ["../etc", "a/b", "A", "a_b", "", "a b", "python-101\n"])
def test_safe_course_root_rejects_an_invalid_slug(tmp_path, slug):
    """Only lowercase alphanumeric slugs joined by single dashes are allowed."""
    with pytest.raises(ValueError) as excinfo:
        _safe_course_root(slug, tmp_path)

    assert str(excinfo.value) == INVALID_SLUG_MESSAGE


def test_safe_course_root_accepts_a_normal_slug(tmp_path):
    """A legal slug resolves to its directory inside the courses root."""
    assert _safe_course_root("python-101", tmp_path) == tmp_path / "python-101"


@pytest.mark.parametrize(
    "relative",
    [
        "../x",
        "a/../../b",
        "..\\..\\b",
        "/etc/passwd",
        "C:\\Windows\\system32",
    ],
)
def test_safe_child_rejects_a_path_outside_the_root(tmp_path, relative):
    """Traversal, Windows separators and absolute paths are all refused."""
    with pytest.raises(ValueError) as excinfo:
        _safe_child(tmp_path, relative)

    assert str(excinfo.value) == PATH_ESCAPE_MESSAGE


def test_safe_child_accepts_a_nested_relative_path(tmp_path):
    """A relative path inside the root resolves to that file."""
    resolved = _safe_child(tmp_path, "chapters/01.md")

    assert resolved == (tmp_path / "chapters" / "01.md").resolve()
    assert resolved.is_relative_to(tmp_path.resolve())


def test_write_json_atomic_writes_complete_unescaped_json(tmp_path):
    """The document is valid JSON and Chinese text is stored verbatim."""
    target = tmp_path / "course.json"
    payload = {"title": "中文标题", "chapters": [{"id": 1}]}

    _write_json_atomic(target, payload)

    raw = target.read_text(encoding="utf-8")
    assert raw == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    assert "中文标题" in raw
    assert "\\u" not in raw
    assert json.loads(raw) == payload


def test_write_json_atomic_uses_a_dot_tmp_sibling(tmp_path, monkeypatch):
    """`course.json` is staged as `course.json.tmp`, never as `course.tmp`."""
    target = tmp_path / "course.json"
    staged: list[Path] = []
    real_replace = os.replace

    def spy(src, dst):
        staged.append(Path(src))
        real_replace(src, dst)

    monkeypatch.setattr("app.courses.common.os.replace", spy)
    _write_json_atomic(target, {"a": 1})

    assert staged == [target.with_suffix(target.suffix + ".tmp")]
    assert staged[0].name == "course.json.tmp"
    assert target.exists()


def test_write_json_atomic_keeps_the_old_file_when_replace_fails(tmp_path, monkeypatch):
    """A failed replacement changes nothing and leaves no `.tmp` behind."""

    def boom(src, dst):
        raise OSError("replace failed")

    target = tmp_path / "course.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    monkeypatch.setattr("app.courses.common.os.replace", boom)

    with pytest.raises(OSError):
        _write_json_atomic(target, {"new": True})

    assert target.read_text(encoding="utf-8") == '{"old": true}\n'
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_json_atomic_requires_an_existing_parent_directory(tmp_path):
    """A wrong path surfaces as `FileNotFoundError` instead of a silent mkdir."""
    target = tmp_path / "missing" / "course.json"

    with pytest.raises(FileNotFoundError):
        _write_json_atomic(target, {"a": 1})

    assert not (tmp_path / "missing").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_content_hash_is_the_sha256_of_the_text():
    """The digest is the lowercase sha256 hex of the UTF-8 encoded text."""
    assert content_hash("") == EMPTY_TEXT_SHA256
    assert content_hash("abc") == ABC_TEXT_SHA256
    assert content_hash("中文") == hashlib.sha256("中文".encode("utf-8")).hexdigest()


def test_content_hash_is_stable_and_discriminating():
    """The same text hashes the same way, different texts do not."""
    assert content_hash("课程正文") == content_hash("课程正文")
    assert content_hash("课程正文") != content_hash("课程正文 ")
    assert len(content_hash("课程正文")) == 64
    assert content_hash("课程正文") == content_hash("课程正文").lower()
