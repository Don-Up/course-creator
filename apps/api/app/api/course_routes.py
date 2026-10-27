"""The HTTP routes of the course list, of course creation and of the editor.

The routes are thin: they call the course service and turn the answer into
a response.  The service decides what a course is, the route only decides
which status code a failure gets.

The editor routes read and write one chapter or one workspace file.  A
write carries the fingerprint the caller read, and a write whose
fingerprint is out of date is answered with a 409: the person who is
behind has to look at both versions before they decide which one wins.
"""

import uuid

from fastapi import APIRouter, HTTPException

from app.course_service import (
    create_course,
    get_course,
    list_courses,
    list_chapters,
    read_chapter,
    read_workspace_file,
    save_chapter,
    save_workspace_file,
)
from app.courses.common import ConcurrencyConflict
from app.schemas import (
    ChapterList,
    ChapterRead,
    ChapterSave,
    CourseCreated,
    CourseCreate,
    CourseList,
    CourseSummary,
    WorkspaceFileRead,
    WorkspaceFileSave,
)
from app.workflow.repository import create_run_record


router = APIRouter(prefix="/api/courses", tags=["courses"])

# The mode of the run that a course creation opens.  The run of a course
# that is being built from scratch is "guided": it walks the seven stages
# in order.  The mode of a review of an existing course is "review", and
# that one is opened by the review entry of a later phase.
INTAKE_RUN_MODE = "guided"


def _http_error(error: Exception) -> HTTPException:
    """Turn a failure of the course service into the answer of the route.

    Args:
        error: The exception the service raised.

    Returns:
        The error to answer with: a 409 when the file on disk changed after
        the caller read it, a 404 when the course or the file is not there,
        and a 400 for everything else, for example a path that points
        outside the course.
    """
    if isinstance(error, ConcurrencyConflict):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


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

    The course is written first and the run is opened afterwards, so a
    refused creation leaves no run behind: the run of a course that does
    not exist would be a run nobody can continue.  The other way round is
    not true -- when the run cannot be written the course is already on
    the disk, and the answer is a 500 rather than a course without a
    trace of where it came from.

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
    run_id = str(uuid.uuid4())
    create_run_record(
        run_id,
        payload.slug,
        INTAKE_RUN_MODE,
        payload.provider,
        payload.model,
        payload.model_dump(),
        budget_policy={"token_budget_mtokens": payload.token_budget_mtokens},
    )
    return CourseCreated(
        course=summary,
        run_id=run_id,
        status=summary.status,
    )


@router.get("/{slug}/chapters", response_model=ChapterList)
def read_chapters(slug: str) -> ChapterList:
    """Answer with the chapters of a course.

    The list is what the browser needs to show a chapter picker: the
    course summary of the API carries the *number* of chapters, but not
    which ones they are.  The key of every item is the key the single
    chapter route accepts, so an item of this list can be read back
    without a second guess.

    Args:
        slug: The short name of the course, for example "python-101".

    Returns:
        The chapters of the course, in the order of the course file.
    Raises HTTPException(404) when there is no such course, and
        HTTPException(400) when the slug is illegal.
    """
    try:
        chapters = list_chapters(slug)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ChapterList(items=chapters)


@router.get("/{slug}/chapters/{key:path}", response_model=ChapterRead)
def read_one_chapter(slug: str, key: str) -> ChapterRead:
    """Answer with one chapter of a course.

    Args:
        slug: The short name of the course, for example "python-101".
        key: The key of the chapter, for example "01".

    Returns:
        The chapter: the key, the path, the content, the fingerprint of the
        content and the moment it was changed the last time.
        Raises HTTPException(404) when the course or the chapter does not
        exist, and HTTPException(400) when the slug is illegal or the key
        points outside the course.
    """
    try:
        chapter = read_chapter(slug, key)
    except (ValueError, FileNotFoundError) as error:
        raise _http_error(error) from error
    return ChapterRead(**chapter)


@router.put("/{slug}/chapters/{key:path}", response_model=ChapterRead)
def write_one_chapter(slug: str, key: str, payload: ChapterSave) -> ChapterRead:
    """Write one chapter of a course, when nobody else changed it.

    Args:
        slug: The short name of the course, for example "python-101".
        key: The key of the chapter, for example "01".
        payload: The new content and the fingerprint the caller read.

    Returns:
        The chapter as it is after the save, with the path of the snapshot
        of the content that was replaced.
        Raises HTTPException(409) when the fingerprint does not match what
        is on the disk, HTTPException(404) when the course or the chapter
        does not exist, and HTTPException(400) when the slug is illegal
        or the key points outside the course.
    """
    try:
        chapter = save_chapter(
            slug, key, payload.content, payload.expected_hash
        )
    except (ValueError, FileNotFoundError, ConcurrencyConflict) as error:
        raise _http_error(error) from error
    return ChapterRead(**chapter)


@router.get("/{slug}/workspace/files/{name:path}", response_model=WorkspaceFileRead)
def read_one_workspace_file(slug: str, name: str) -> WorkspaceFileRead:
    """Answer with one file of the workspace of a course.

    Args:
        slug: The short name of the course, for example "python-101".
        name: The name of the workspace file, for example "NOTES.md".

    Returns:
        The file: the name, the path, the content, the fingerprint of the
        content, the size of the file and the moment it was changed the
        last time.
        Raises HTTPException(404) when the course or the file does not
        exist, and HTTPException(400) when the slug is illegal or the name
        points outside the workspace.
    """
    try:
        workspace_file = read_workspace_file(slug, name)
    except (ValueError, FileNotFoundError) as error:
        raise _http_error(error) from error
    return WorkspaceFileRead(**workspace_file)


@router.put("/{slug}/workspace/files/{name:path}", response_model=WorkspaceFileRead)
def write_one_workspace_file(
    slug: str, name: str, payload: WorkspaceFileSave
) -> WorkspaceFileRead:
    """Write one file of the workspace, when nobody else changed it.

    Args:
        slug: The short name of the course, for example "python-101".
        name: The name of the workspace file, for example "NOTES.md".
        payload: The new content and the fingerprint the caller read.

    Returns:
        The file as it is after the save, with the path of the snapshot of
        the content that was replaced.
        Raises HTTPException(409) when the fingerprint does not match what
        is on the disk, HTTPException(404) when the course or the file
        does not exist, and HTTPException(400) when the slug is illegal
        or the name points outside the workspace.
    """
    try:
        workspace_file = save_workspace_file(
            slug, name, payload.content, payload.expected_hash
        )
    except (ValueError, FileNotFoundError, ConcurrencyConflict) as error:
        raise _http_error(error) from error
    return WorkspaceFileRead(**workspace_file)
