"""The HTTP routes of the course list and of course creation.

The routes are thin: they call the course service and turn the answer into
a response.  The service decides what a course is, the route only decides
which status code a failure gets.
"""

import uuid

from fastapi import APIRouter, HTTPException

from app.course_service import create_course, get_course, list_courses
from app.schemas import CourseCreated, CourseCreate, CourseList, CourseSummary


router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("", response_model=CourseList)
def read_courses() -> CourseList:
    """Answer with every course of the courses root.

    Returns:
        The list of the courses, one item per course.
    """
    return CourseList(items=list_courses())


@router.get("/{slug}", response_model=CourseSummary)
def read_course(slug: str) -> CourseSummary:
    """Answer with one course.

    Args:
        slug: The short name of the course, for example "python-101".

    Returns:
        The item of that course.
        Raises HTTPException(404) when no course has this slug, and
        HTTPException(400) when the slug is not a legal course name.
    """
    try:
        course = get_course(slug)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return CourseSummary(**course)


@router.post("", response_model=CourseCreated, status_code=201)
def create_course_from_intake(payload: CourseCreate) -> CourseCreated:
    """Create one course out of the intake form the browser posted.

    The form is checked by Pydantic before this function runs, so an
    illegal slug or an out of range field never reaches the disk.  What is
    left is answered with a status code per failure: 409 when the slug is
    taken, 400 when the path guard refuses the slug.

    Args:
        payload: The intake form the user submitted, for example a
            CourseCreate with the slug "python-101".

    Returns:
        The new course, the id of its intake run and the status of the new
        course, which is "preparing" because it has no chapters yet.
    Raises HTTPException(409) when a course with this slug is already
        there, and HTTPException(400) when the path guard refuses the
        slug.
    """
    try:
        course = create_course(payload)
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail="课程 slug 已存在") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    summary = CourseSummary(**course)
    return CourseCreated(
        course=summary,
        run_id=str(uuid.uuid4()),
        status=summary.status,
    )
