import re
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from schemas import PostCreate, PostResponse


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
templates.env.globals["current_year"] = datetime.now().year

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "detail": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = (
        exc.detail
        if exc.detail
        else "An error occurred. Please check your request and try again."
    )
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": message}, status_code=exc.status_code)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exc.status_code, "detail": message, "title": str(exc.status_code)},
        status_code=exc.status_code,
    )




posts = [
    {
        "id": 1,
        "slug": "getting-started-with-fastapi",
        "title": "Getting Started with FastAPI",
        "subtitle": "A modern, fast web framework for building APIs with Python",
        "content": "FastAPI is a modern, fast web framework for building APIs with Python 3.7+ based on standard type hints. In this post we cover installation, your first endpoint, and automatic docs.",
        "cover_image": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97",
        "author": {
            "id": 101,
            "name": "Ian Madhara",
            "username": "ianmadhara",
            "avatar": "https://i.pravatar.cc/150?img=12",
        },
        "tags": ["python", "fastapi", "backend"],
        "claps": 342,
        "comments_count": 12,
        "read_time_minutes": 5,
        "published_at": "2026-08-14T09:30:00Z",
        "updated_at": "2026-08-15T11:00:00Z",
    },
    {
        "id": 2,
        "slug": "why-i-switched-to-python",
        "title": "Why I Switched to Python",
        "subtitle": "Readability and ecosystem make it a joy to work with",
        "content": "After years of juggling multiple languages, Python's clean syntax and vast ecosystem won me over. Here's what changed my mind.",
        "cover_image": "https://images.unsplash.com/photo-1526379095098-d400fd0bf935",
        "author": {
            "id": 102,
            "name": "Jane Doe",
            "username": "janedoe",
            "avatar": "https://i.pravatar.cc/150?img=32",
        },
        "tags": ["python", "career", "opinion"],
        "claps": 189,
        "comments_count": 4,
        "read_time_minutes": 3,
        "published_at": "2026-08-20T14:15:00Z",
        "updated_at": "2026-08-20T14:15:00Z",
    },
    {
        "id": 3,
        "slug": "building-a-medium-clone",
        "title": "Building a Medium Clone",
        "subtitle": "From an empty folder to a working blogging API",
        "content": "In this post we walk through building a blogging platform backend from scratch using FastAPI, covering posts, authors, and tags along the way.",
        "cover_image": "https://images.unsplash.com/photo-1499750310107-5fef28a66643",
        "author": {
            "id": 103,
            "name": "John Smith",
            "username": "johnsmith",
            "avatar": "https://i.pravatar.cc/150?img=5",
        },
        "tags": ["tutorial", "fastapi", "webdev"],
        "claps": 521,
        "comments_count": 27,
        "read_time_minutes": 8,
        "published_at": "2026-09-01T08:00:00Z",
        "updated_at": "2026-09-05T16:45:00Z",
    },
]

@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
def home(request: Request):
    topics = sorted({tag for post in posts for tag in post["tags"]})
    return templates.TemplateResponse(
        request, "home.html", {"posts": posts, "topics": topics, "title": "Home"}
    )

@app.get("/posts/{slug}", include_in_schema=False, name="post_detail")
def post_detail(request: Request, slug: str):
    post = next((p for p in posts if p["slug"] == slug), None)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    more_posts = [p for p in posts if p["slug"] != slug][:2]
    return templates.TemplateResponse(
        request,
        "post.html",
        {"post": post, "more_posts": more_posts, "title": post["title"]},
    )

@app.get("/api/posts", response_model=list[PostResponse])
def get_posts():
    return posts


@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int):
    for post in posts:
        if post.get("id") == post_id:
            return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")


@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(post_in: PostCreate):
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_post = {
        "id": max((p["id"] for p in posts), default=0) + 1,
        "slug": slugify(post_in.title),
        "title": post_in.title,
        "subtitle": post_in.subtitle,
        "content": post_in.content,
        "cover_image": post_in.cover_image,
        "author": posts[0]["author"],
        "tags": post_in.tags,
        "claps": 0,
        "comments_count": 0,
        "read_time_minutes": max(1, len(post_in.content.split()) // 200),
        "published_at": now,
        "updated_at": now,
    }
    posts.append(new_post)
    return new_post