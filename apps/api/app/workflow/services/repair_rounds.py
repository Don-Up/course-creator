"""Stable reporting and discovery boundaries for one quality-repair round."""
from __future__ import annotations

from typing import Any

from app.workflow.quality_cycle import merge_same_cycle_discoveries

def upsert_round_chapter_result(
    results: list[dict[str, Any]], result: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep one latest outcome per chapter in a user-visible repair round."""
    chapter = int(result.get("chapter") or 0)
    updated = [item for item in results if int(item.get("chapter") or 0) != chapter]
    return [*updated, result]


def defer_current_round_discoveries(
    discoveries: list[dict[str, Any]], *, seen_chapters: set[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Do not requeue a chapter already processed in the current round."""
    immediate: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for item in discoveries:
        chapter = int(item.get("chapter") or 0)
        (deferred if chapter in seen_chapters else immediate).append(item)
    return immediate, deferred


def merge_round_discoveries(
    queue: list[dict[str, Any]],
    discoveries: list[dict[str, Any]],
    *,
    attempts: dict[str, int],
    seen_chapters: set[int],
    discovery_sweeps: int,
    max_discovery_sweeps: int,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[dict[str, Any]], int, bool]:
    """Merge only unseen chapters now and defer repeated chapters to next round."""
    immediate, next_round = defer_current_round_discoveries(
        discoveries, seen_chapters=seen_chapters
    )
    budget_exhausted = bool(immediate) and discovery_sweeps >= max_discovery_sweeps
    merged, added, deferred, next_sweeps = merge_same_cycle_discoveries(
        queue,
        immediate,
        attempts=attempts,
        max_attempts=2,
        discovery_sweeps=discovery_sweeps,
        max_discovery_sweeps=max_discovery_sweeps,
    )
    return merged, added, deferred, next_round, next_sweeps, budget_exhausted
