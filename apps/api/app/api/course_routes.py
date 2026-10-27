"""The HTTP routes of the course list.

The routes are thin: they call the course service and turn the answer into
a response.  The service decides what a course is, the route only decides
which status code a failure gets.
"""

from fastapi import APIRouter, HTTPException

from app.course_service import get_course, list_courses
from app.schemas import CourseList, CourseSummary


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
