from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import settings
from database import engine
from errors import register_exception_handlers
from routers import frontend, posts, users


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The schema is managed by Alembic: run `alembic upgrade head` before starting.
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount(settings.media_url, StaticFiles(directory=settings.media_root), name="media")

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])
app.include_router(frontend.router)

register_exception_handlers(app)
