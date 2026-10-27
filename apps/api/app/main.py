from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.course_routes import router as course_router
from app.api.system_routes import router as system_router
from app.config import get_settings


EXAMPLE_COURSE_ROOT = get_settings().courses_root / "advanced-learning-of-obsidian"

app = FastAPI(title="AI Course Studio Scaffold API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system_router)
app.include_router(course_router)
app.mount(
    "/course-example",
    StaticFiles(directory=EXAMPLE_COURSE_ROOT, html=True),
    name="course-example",
)


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
