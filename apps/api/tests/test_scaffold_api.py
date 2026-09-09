from app.api.course_routes import read_courses
from app.api.system_routes import read_health
from app.main import app


def test_health_check_is_available():
    assert read_health().model_dump() == {
        "status": "ok",
        "service": "course-training-scaffold",
    }


def test_catalog_exposes_the_example_course():
    courses = read_courses()

    assert len(courses.items) == 1
    assert courses.items[0].slug == "advanced-learning-of-obsidian"
    assert courses.items[0].href == "/course-example/"


def test_application_mounts_the_static_example_course():
    route_names = {getattr(route, "name", None) for route in app.routes}

    assert "course-example" in route_names
