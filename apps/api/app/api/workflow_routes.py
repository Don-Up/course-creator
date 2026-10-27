"""The HTTP route that hands out the topology of the workflow.

The route is thin: it reads the snapshot out of the graph of the workflow
and turns it into an answer.  The topology is not written down here, and
the browser does not write it down either -- both read the same graph.
"""

from fastapi import APIRouter

from app.schemas import WorkflowSnapshotRead
from app.workflow.snapshot import workflow_snapshot

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.get("", response_model=WorkflowSnapshotRead)
def read_workflow() -> WorkflowSnapshotRead:
    """Answer with the topology of the course production workflow.

    Returns:
        The phases of the workflow, the nodes they hold and the transitions
        between the nodes, as the graph of the workflow says.  The answer
        is the same every time it is asked: the graph does not change
        while the program runs.
    """
    return WorkflowSnapshotRead(**workflow_snapshot())
