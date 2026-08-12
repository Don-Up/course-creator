from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import course_routes, run_routes
from app.api.course_helpers import attach_resumable_creation_run
from app.api.system_routes import router as system_router
from app.db import initialize_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="AI Course Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system_router)
app.include_router(course_routes.build_router())
app.include_router(run_routes.build_router())

# Compatibility exports retained for existing callers and API contract tests.
_attach_resumable_creation_run = attach_resumable_creation_run
create_course = course_routes.create_course
start_run = course_routes.start_run
resolve_approval = run_routes.resolve_approval


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
