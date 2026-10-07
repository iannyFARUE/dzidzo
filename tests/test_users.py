from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from tests.conftest import auth_header, create_test_user, login_user


@pytest.mark.anyio
async def test_create_user_validation_error(client: AsyncClient):
    response = await client.post(
        "/api/users",
        json={
            "username": "testuser",
        },
    )

    assert response.status_code == 422
    assert "email" in response.text
    assert "password" in response.text


## Test Create User Duplicate Email
@pytest.mark.anyio
async def test_create_user_duplicate_email(client: AsyncClient):
    await create_test_user(client)

    response = await client.post(
        "/api/users",
        json={
            "username": "different_user",
            "name": "Different User",
            "email": "test@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "username or email already registered"


## Test Create User Success
@pytest.mark.anyio
async def test_create_user_success(client: AsyncClient):
    response = await client.post(
        "/api/users",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepassword123",
            "name":"newUser"
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "avatar" in data
    assert "password" not in data
    assert "password_hash" not in data

## Test Upload Profile Picture
@pytest.mark.anyio
async def test_upload_profile_picture(client: AsyncClient, mocked_aws):
    await create_test_user(client)
    token = await login_user(client)

    test_image_path = Path(__file__).parent / "test_image.jpg"
    image_bytes = test_image_path.read_bytes()

    response = await client.put(
        "/api/users/me/avatar",
        files={"file": ("profile.jpg", BytesIO(image_bytes), "image/jpeg")},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    avatar = response.json()["avatar"]
    # Avatars are re-encoded to WebP and stored under a random key.
    assert avatar.startswith("https://test-bucket.s3.us-east-1.amazonaws.com/profile_pics/")
    assert avatar.endswith(".webp")

    s3_objects = mocked_aws.list_objects_v2(Bucket="test-bucket")
    assert len(s3_objects.get("Contents", [])) == 1
    assert avatar.endswith(s3_objects["Contents"][0]["Key"])

## Test Forgot Password Sends Email
@pytest.mark.anyio
async def test_forgot_password_sends_email(client: AsyncClient):
    await create_test_user(client)

    # Patch where it's looked up: the router calls mail.send_password_reset_email.
    # autospec keeps the mock sync and rejects calls that don't fit the real signature.
    with patch("mail.send_password_reset_email", autospec=True) as mock_send:
        response = await client.post(
            "/api/users/forgot-password",
            json={"email": "test@example.com"},
        )

    assert response.status_code == 202
    assert response.json()["detail"] == (
        "If an account uses that email, a password reset link is on its way."
    )
    mock_send.assert_called_once()
    to, name, token = mock_send.call_args.args
    assert to == "test@example.com"
    assert name == "Test User"
    assert isinstance(token, str) and token

## Test Forgot Password Unknown Email
@pytest.mark.anyio
async def test_forgot_password_unknown_email(client: AsyncClient):
    with patch("mail.send_password_reset_email", autospec=True) as mock_send:
        response = await client.post(
            "/api/users/forgot-password",
            json={"email": "nobody@example.com"},
        )

    # Same reply as for a real account, so it doesn't reveal who is registered.
    assert response.status_code == 202
    assert response.json()["detail"] == (
        "If an account uses that email, a password reset link is on its way."
    )
    mock_send.assert_not_called()
