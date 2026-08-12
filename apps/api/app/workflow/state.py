from __future__ import annotations

from typing import Any, TypedDict


class CourseAgentState(TypedDict, total=False):
    run_id: str
    course_slug: str
    scope: str
    request: dict[str, Any]
    feedback: str
    global_change_requests: list[dict[str, Any]]
    workspace_consistency: dict[str, Any]
    consistency_retry_count: int
    approval: str
    mission_markdown: str
    mission_assumptions: list[str]
    workspace_revision: dict[str, Any]
    research: dict[str, Any]
    blueprint: dict[str, Any]
    batches: list[dict[str, Any]]
    current_batch_index: int
    continuity_ledger: list[dict[str, Any]]
    batch_results: list[dict[str, Any]]
    retry_count: int
    quality_repair_queue: list[dict[str, Any]]
    quality_repair_active: bool
    # Batch production and the all-course closure use the same chapter-local
    # repair node, but their queues must never share scope.  Keeping an
    # explicit batch queue prevents a batch build failure from being confused
    # with the course-wide quality cycle in persisted checkpoints.
    batch_repair_queue: list[dict[str, Any]]
    batch_repair_active: bool
    batch_repair_batch_id: str | None
    quality_repair_round: int
    quality_repair_round_results: list[dict[str, Any]]
    quality_repair_history: list[dict[str, Any]]
    repair_task_ids: list[str]
    active_repair_task_id: str | None
    repair_scope: str
    repair_round_summary: dict[str, Any]
    course_quality_report: dict[str, Any]
    quality_cycle: dict[str, Any]
    quality_cycle_id: str
    quality_cycle_iteration: int
    quality_cycle_queue: list[dict[str, Any]]
    quality_cycle_attempts: dict[str, int]
    quality_cycle_discovery_sweeps: int
    quality_refunded_legacy_tasks: list[str]
    quality_cycle_progress_hash: str
    quality_cycle_no_progress_count: int
    quality_override: bool
    review_result: dict[str, Any]
    quality_blocked: bool
    release_review: dict[str, Any]
    final_status: str
