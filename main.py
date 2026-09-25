from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
templates.env.globals["current_year"] = datetime.now().year

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

@app.get("/api/posts")
def get_posts():
    return posts


@app.get("/api/posts/{post_id}")
def get_post(post_id: int):
    for post in posts:
        if post.get("id") == post_id:
            return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")