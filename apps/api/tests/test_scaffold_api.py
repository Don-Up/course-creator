"""Tests of the routes the scaffold exposes.

The course list is read from the courses root on disk, so the example
course that ships with the repository has to show up in the answer.  The
test does not count the courses: the developer creates real courses in the
same directory, and a growing list must not break the test.
"""

from fastapi.testclient import TestClient

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

    example = next(
        (item for item in courses.items if item.slug == "advanced-learning-of-obsidian"),
        None,
    )
    assert example is not None
    assert example.title
    assert example.description
    assert example.chapters == 9
    assert example.status == "published"


def test_the_course_list_is_answered_over_http():
    with TestClient(app) as client:
        response = client.get("/api/courses")

    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert set(body["items"][0]) == {
        "slug",
        "title",
        "description",
        "chapters",
        "status",
        "duration",
    }


def test_one_course_is_answered_over_http():
    with TestClient(app) as client:
        response = client.get("/api/courses/advanced-learning-of-obsidian")

    assert response.status_code == 200
    assert response.json()["slug"] == "advanced-learning-of-obsidian"


def test_an_unknown_course_is_answered_with_not_found():
    with TestClient(app) as client:
        response = client.get("/api/courses/no-such-course")

    assert response.status_code == 404


def test_an_illegal_slug_is_answered_with_bad_request():
    with TestClient(app) as client:
        response = client.get("/api/courses/Bad-Slug")

    assert response.status_code == 400


def test_application_mounts_the_static_example_course():
    route_names = {getattr(route, "name", None) for route in app.routes}

    assert "course-example" in route_names
