import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user

@pytest.mark.anyio
async def test_get_posts_empty(client: AsyncClient):
    response = await client.get("/api/posts")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page_size"] == 10
    assert data["page"] == 1


@pytest.mark.anyio
async def test_get_post_not_found(client: AsyncClient):
    response = await client.get("/api/posts/1111")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "post not found"



## Test Create Post Success
@pytest.mark.anyio
async def test_create_post_success(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.post(
        "/api/posts",
        json={
            "title": "My First Post",
            "subtitle": "A short subtitle",
            "content": "This is the content",
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["title"] == "My First Post"
    assert data["subtitle"] == "A short subtitle"
    assert data["content"] == "This is the content"
    assert data["author"]["id"] == user["id"]
    assert "id" in data
    assert "published_at" in data
    assert data["author"]["username"] == "testuser"

@pytest.mark.anyio
async def test_create_post_unauthorized(client: AsyncClient):
    response = await client.post(
        "api/posts",
                json={
            "title": "My First Post",
            "subtitle": "A short subtitle",
            "content": "This is the content",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
