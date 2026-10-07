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
        "/api/posts",
        json={
            "title": "My First Post",
            "subtitle": "A short subtitle",
            "content": "This is the content",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


## Test Update Post Success
@pytest.mark.anyio
async def test_update_post_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.post(
        "/api/posts",
        json={
            "title": "Original Title",
            "subtitle": "Original subtitle",
            "content": "Original content",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    post_id = response.json()["id"]

    response = await client.patch(
        f"/api/posts/{post_id}",
        json={"title": "Updated Title"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["slug"] == "updated-title"
    assert data["subtitle"] == "Original subtitle"
    assert data["content"] == "Original content"


## Test Update Post Wrong User
@pytest.mark.anyio
async def test_update_post_wrong_user(client: AsyncClient):
    await create_test_user(client, username="user1", email="user1@example.com")
    token1 = await login_user(client, email="user1@example.com")

    response = await client.post(
        "/api/posts",
        json={
            "title": "User 1's Post",
            "subtitle": "A post by user 1",
            "content": "Only user 1 can edit this",
        },
        headers=auth_header(token1),
    )
    assert response.status_code == 201, response.text
    post_id = response.json()["id"]

    await create_test_user(client, username="user2", email="user2@example.com")
    token2 = await login_user(client, email="user2@example.com")

    response = await client.patch(
        f"/api/posts/{post_id}",
        json={"title": "Hacked Title"},
        headers=auth_header(token2),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "not the author of this post"

    response = await client.get(f"/api/posts/{post_id}")
    assert response.json()["title"] == "User 1's Post"


## Test Pagination
@pytest.mark.anyio
async def test_get_posts_with_pagination(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    for i in range(5):
        response = await client.post(
            "/api/posts",
            json={
                "title": f"Post {i}",
                "subtitle": f"Subtitle {i}",
                "content": f"Content for post {i}",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

    response = await client.get("/api/posts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    assert data["pages"] == 1
    assert data["has_next"] is False
    assert data["has_prev"] is False

    response = await client.get("/api/posts?page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["pages"] == 3
    assert data["has_next"] is True
    assert data["has_prev"] is False
    # Newest first, so the last post created comes first.
    assert [post["title"] for post in data["items"]] == ["Post 4", "Post 3"]

    response = await client.get("/api/posts?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["has_next"] is True
    assert data["has_prev"] is True
    assert [post["title"] for post in data["items"]] == ["Post 2", "Post 1"]

    response = await client.get("/api/posts?page=3&page_size=2")
    data = response.json()
    assert len(data["items"]) == 1
    assert data["has_next"] is False
