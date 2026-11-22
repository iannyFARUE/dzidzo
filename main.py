from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from database import engine
from errors import register_exception_handlers
from routers import frontend, posts, users
from typing import Annotated
from database import get_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The schema is managed by Alembic: run `alembic upgrade head` before starting.
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health_check(db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        ) from exc
    return {"status":"healthy"}




app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount(settings.media_url, StaticFiles(directory=settings.media_root), name="media")

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])
app.include_router(frontend.router)

register_exception_handlers(app)
