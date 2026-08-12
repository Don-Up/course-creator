from app.workflow.snapshot import workflow_snapshot


def test_snapshot_keeps_seven_product_phases_but_exposes_real_course_nodes():
    snapshot = workflow_snapshot()
    course = next(item for item in snapshot["topologies"] if item["mode"] == "new_course")

    assert len(course["phases"]) == 7
    assert {node["id"] for node in course["nodes"]} >= {
        "draft_mission", "research_sources", "verify_workspace_contract",
        "generate_batch", "repair_batch_chapters", "repair_open_chapters",
        "release_approval",
    }
    assert any(edge == {"from": "release_approval", "to": "prepare_course_quality_review", "label": "继续修复"} for edge in course["edges"])
    assert any(edge == {"from": "intake", "to": "draft_mission", "label": "创建 Run 后执行"} for edge in course["edges"])
    nodes = {node["id"]: node for node in course["nodes"]}
    assert nodes["repair_batch_chapters"]["phase"] == "generation"
    assert nodes["repair_open_chapters"]["phase"] == "quality"


def test_snapshot_declares_execution_mode_for_teaching_topology():
    snapshot = workflow_snapshot()
    course = next(item for item in snapshot["topologies"] if item["mode"] == "new_course")
    nodes = {node["id"]: node for node in course["nodes"]}

    assert nodes["draft_mission"]["execution_mode"] == "llm"
    assert nodes["generate_batch"]["execution_mode"] == "hybrid"
    assert nodes["verify_workspace_contract"]["execution_mode"] == "deterministic"
    assert nodes["release_approval"]["execution_mode"] == "approval"
    assert nodes["finalize"]["execution_mode"] == "system"


def test_snapshot_keeps_workspace_audit_and_stop_routes_in_its_read_model():
    snapshot = workflow_snapshot()
    course = next(item for item in snapshot["topologies"] if item["mode"] == "new_course")
    routes = {(edge["from"], edge["to"], edge["label"]) for edge in course["edges"]}

    assert ("revise_workspace", "verify_workspace_contract", "执行审计") in routes
    assert {
        ("approve_mission", "stop", "停止"),
        ("approve_blueprint", "stop", "停止"),
        ("approve_plan", "stop", "停止"),
        ("request_batch_review", "stop", "停止"),
        ("course_quality_review", "stop", "停止"),
    } <= routes


def test_snapshot_separates_review_flow_and_runtime_manifests():
    snapshot = workflow_snapshot()
    review = next(item for item in snapshot["topologies"] if item["mode"] == "review_course")

    assert [node["id"] for node in review["nodes"] if node["id"] not in {"intake", "stop"}] == ["inspect", "approve_review", "finish"]
    assert {agent["id"] for agent in snapshot["agents"]} >= {"writer.agent", "reviewer.agent", "repair.agent"}
    assert {tool["id"] for tool in snapshot["tools"]} >= {"course.build", "workspace.patch"}
