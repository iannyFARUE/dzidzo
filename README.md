# Dzidzo

A Medium-style blogging platform built with FastAPI. People can sign up, write stories with tags and cover images, and edit or delete their own posts. The app has server-rendered pages (Jinja2 + Tailwind CSS) and a JSON REST API.

## Features

- **Accounts**: register, log in with a username or email, soft-delete an account and restore it later
- **Profiles**: edit your name, username and email, and upload a profile photo (animated GIFs stay animated)
- **Stories**: create, edit and delete posts, with automatic slugs, tags and read-time estimates
- **Two front ends on one backend**:
  - HTML pages that use a cookie session
  - A REST API that uses JWT bearer tokens
- **Security**:
  - Argon2 password hashing
  - Login takes the same time whether or not the account exists, so response times don't reveal which usernames are taken
  - Only a post's author can change it, and only a user can change their own account
  - Email addresses are only returned to their owner
  - `?next=` redirects only go to pages on this site

## Tech stack

| Layer | Tools |
| --- | --- |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Database | SQLite via SQLAlchemy 2 (async) + aiosqlite |
| Validation & settings | Pydantic, pydantic-settings |
| Auth | PyJWT, pwdlib (Argon2) |
| Templates | Jinja2 |
| Image processing | Pillow |
| Styling | Tailwind CSS v4 (CLI) |
| Package management | [uv](https://docs.astral.sh/uv/) (Python), npm (CSS build) |

## Getting started

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js and npm (only needed to build the CSS)

### 1. Install dependencies

```bash
uv sync
npm install
```

### 2. Configure the environment

Copy the example file and set a real secret key:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste the output into SECRET_KEY
```

| Variable | Default | Description |
| --- | --- | --- |
| `SECRET_KEY` | *(required)* | Key used to sign JWTs. Use a long random value. |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | How long a login stays valid, for both the API token and the cookie |
| `MEDIA_ROOT` | `media` | Folder where uploaded files are stored |
| `MEDIA_URL` | `/media` | URL path that serves `MEDIA_ROOT` |
| `MAX_AVATAR_BYTES` | `5242880` (5 MB) | Largest profile photo upload allowed |

### 3. Build the CSS

```bash
npm run build:css     # one-off, minified build
npm run watch:css     # rebuild on change while developing
```

The output goes to `static/dist/style.css`. Git ignores it, so you need to build it after cloning.

### 4. Run the server

```bash
uv run fastapi dev main.py
```

Then open:

- http://127.0.0.1:8000: the blog
- http://127.0.0.1:8000/docs: interactive API docs (Swagger UI)

The SQLite database (`blog.db`) and its tables are created automatically on first start.

## Project structure

```
.
├── main.py            # App setup: routers, static/media mounts, table creation on startup
├── config.py          # Settings loaded from .env
├── database.py        # Async engine, session factory, get_db dependency
├── models.py          # SQLAlchemy models: User, Post, Tag
├── schemas.py         # Pydantic request/response schemas
├── auth.py            # Password hashing, JWT creation/validation, current-user dependencies
├── avatars.py         # Profile photo validation, resizing and replacement
├── storage.py         # File storage interface + local-disk implementation
├── errors.py          # JSON errors for /api, HTML error page for everything else
├── templating.py      # Jinja2 setup (injects current_user into every template)
├── routers/
│   ├── users.py       # /api/users
│   ├── posts.py       # /api/posts
│   └── frontend.py    # HTML pages and form handlers
├── templates/         # Jinja2 templates
├── static/src/        # Tailwind input CSS
└── media/             # Default avatars + uploaded profile photos (uploads are git-ignored)
```

## Web pages

| Path | Description | Login required |
| --- | --- | --- |
| `/`, `/posts` | Home feed with all stories and topics | |
| `/posts/{slug}` | Read a story | |
| `/users/{username}` | An author's stories | |
| `/login`, `/register` | Sign in / create an account | |
| `/write` | Write a new story | ✓ |
| `/posts/{slug}/edit` | Edit or delete your story | ✓ (author only) |
| `/profile` | Your details and profile photo (click your avatar in the header) | ✓ |
| `/logout` (POST) | Sign out | |

The pages keep you logged in with an `HttpOnly`, `SameSite=Lax` cookie.

## REST API

All endpoints are under `/api`. For protected endpoints, send `Authorization: Bearer <token>`.

### Getting a token

```bash
curl -X POST http://127.0.0.1:8000/api/users/token \
  -d "username=alice&password=supersecret"
```

`username` can be a username or an email address.

### Users — `/api/users`

| Method | Path | Description | Auth |
| --- | --- | --- | --- |
| POST | `/` | Register | |
| POST | `/token` | Log in and get an access token | |
| GET | `/me` | Your own profile, including your email | ✓ |
| PUT | `/me/avatar` | Upload a profile photo (multipart field `file`) | ✓ |
| DELETE | `/me/avatar` | Reset your profile photo to the default | ✓ |
| GET | `/{user_id}` | Public profile | |
| PATCH | `/{user_id}` | Partially update your profile | ✓ (self) |
| PUT | `/{user_id}` | Replace your profile | ✓ (self) |
| DELETE | `/{user_id}` | Soft-delete your account | ✓ (self) |
| POST | `/{user_id}/restore` | Restore a deleted account with its password | |

### Posts — `/api/posts`

| Method | Path | Description | Auth |
| --- | --- | --- | --- |
| GET | *(no trailing slash)* | List posts, newest first (paginated) | |
| GET | `/{post_id}` | Get one post | |
| GET | `/{user_id}/posts` | A user's posts (paginated) | |
| POST | `/` | Create a post | ✓ |
| PATCH | `/{post_id}` | Partially update a post | ✓ (author) |
| PUT | `/{post_id}` | Replace a post | ✓ (author) |
| DELETE | `/{post_id}` | Delete a post | ✓ (author) |

### Pagination

The post list endpoints take two optional query parameters:
- `page`: starts at 1 (default 1)
- `page_size`: from 1 to 50 (default 10)

They return a page object instead of a plain list:

```json
{
  "items": [ /* posts */ ],
  "total": 24,
  "page": 1,
  "page_size": 10,
  "pages": 3,
  "has_next": true,
  "has_prev": false
}
```

A page past the end returns an empty `items` list. The web pages use the same `?page=` parameter, but show a 404 for a page past the end.

### Uploading a profile photo

```bash
curl -X PUT http://127.0.0.1:8000/api/users/me/avatar \
  -H "Authorization: Bearer <token>" \
  -F "file=@me.jpg"
```

`avatar` can't be set through `PATCH`/`PUT /api/users/{id}`. It changes only through these upload endpoints, so nobody can point their avatar at another user's file.

### Validation rules

- **Username:** 1–50 characters. It can't contain `@`, which is reserved for emails so a username can never be mistaken for an email at login.
- **Email:** must look like `name@domain`, max 120 characters
- **Password:** 8–128 characters
- **Post:** title ≤ 100 characters, subtitle ≤ 200 characters, and up to 10 tags of ≤ 30 characters each
- **Profile photo:**
  - JPEG, PNG, WebP or GIF, up to 5 MB by default
  - Animated images can have up to 200 frames

## Profile photos

- **Processing:** every upload is cropped to a 256×256 square and saved again as WebP. This:
  - removes photo metadata such as GPS location
  - means only real images are stored, never the raw upload
  - keeps transparency and animation
- **Storage:**
  - Each file gets a random name.
  - When a user uploads a new photo, the old file is deleted only after the database points to the new one.
- **Moving to cloud storage (e.g. S3):**
  - [storage.py](storage.py) defines a `Storage` interface with two methods: `save(key, data, content_type)`, which returns the file's public URL, and `delete(url)`.
  - `LocalStorage` writes files to `MEDIA_ROOT`.
  - To use S3, write a class with those two methods and return it from `get_storage()`. No other code needs to change.

## Notes

- **Soft deletes:**
  - A deleted account can't log in, and its tokens stop working.
  - Its username and email become free for others to register.
  - When restoring, you can pick a new username or email if the old one has been taken.
- **No migrations:** tables are created with `create_all` on startup. If you change `models.py`, delete `blog.db` during development, or add Alembic for real schema migrations.
- **Tokens can't be revoked early:** logging out clears the cookie, but a copied JWT stays valid until it expires.
