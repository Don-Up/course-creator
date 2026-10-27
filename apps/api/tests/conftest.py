"""Shared fixtures for the API test suite.

The database lives in ``.course-agent/agent.db`` and belongs to the
developer's machine, so a test must never touch it.  Every test that wants
SQLite therefore asks for a throwaway file under pytest's ``tmp_path`` and
points the settings object at that file.  The file and the two sidecars
WAL mode leaves behind are removed when the test ends.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest


@pytest.fixture
def temp_database_path(tmp_path: Path) -> Iterator[Path]:
    """Hand out a private database file for one test and remove it afterwards.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Yields:
        The path of the ``.db`` file this test may use.  The file does not
        exist yet; the first ``initialize_database()`` creates it.
    """
    path = tmp_path / "agent.db"
    yield path
    sidecars = (path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm"))
    for candidate in (path, *sidecars):
        candidate.unlink(missing_ok=True)


@pytest.fixture
def use_temp_database(
    temp_database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point the database module at the throwaway file for one test.

    Args:
        temp_database_path: The private database file of this test.
        monkeypatch: pytest's helper, which undoes the patch afterwards.

    Returns:
        The path of the database the module under test opens from now on.
    """
    from app import db

    monkeypatch.setattr(
        db,
        "get_settings",
        lambda: SimpleNamespace(database_path=temp_database_path),
    )
    return temp_database_path
