# Dzidzo

A Medium-style blogging platform built with FastAPI. People can sign up, write stories with tags and cover images, and edit or delete their own posts. The app has server-rendered pages (Jinja2 + Tailwind CSS) and a JSON REST API.

## Features

- **Accounts**: register, log in with a username or email, confirm their email address, reset a forgotten password by email, soft-delete an account and restore it later
- **Profiles**: edit your name, username and email, and upload a profile photo (animated GIFs stay animated)
- **Stories**: create, edit and delete posts, with an optional uploaded cover image, automatic slugs, tags and read-time estimates
- **Two front ends on one backend**:
  - HTML pages that use a cookie session
  - A REST API that uses JWT bearer tokens
- **Security**:
  - Argon2 password hashing
  - Login takes the same time whether or not the account exists, so response times don't reveal which usernames are taken
  - Only a post's author can change it, and only a user can change their own account
  - Email addresses are only returned to their owner
  - `?next=` redirects only go to pages on this site
  - Password reset never reveals whether an email has an account, and reset links work only once

## Tech stack

| Layer | Tools |
| --- | --- |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Database | PostgreSQL via SQLAlchemy 2 (async) + asyncpg |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) |
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
- PostgreSQL, with a database and a user that owns it
- Node.js and npm (only needed to build the CSS)

### 1. Install dependencies

```bash
uv sync
npm install
```

### 2. Configure the environment

Copy the example file, then set your database connection and a real secret key:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste the output into SECRET_KEY
```

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | *(required)* | PostgreSQL connection, e.g. `postgresql+asyncpg://user:password@localhost:5432/dzidzodb`. Percent-encode special characters in the password: `@` becomes `%40`, `:` becomes `%3A`, `/` becomes `%2F`. |
| `SECRET_KEY` | *(required)* | Key used to sign JWTs. Use a long random value. |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | How long a login stays valid, for both the API token and the cookie |
| `MEDIA_ROOT` | `media` | Folder where uploaded files are stored |
| `MEDIA_URL` | `/media` | URL path that serves `MEDIA_ROOT` |
| `MAX_AVATAR_BYTES` | `5242880` (5 MB) | Largest profile photo upload allowed |
| `MAX_COVER_BYTES` | `10485760` (10 MB) | Largest cover image upload allowed |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | Public address of the site, used to build links in emails |
| `PASSWORD_RESET_EXPIRE_MINUTES` | `30` | How long a password reset link stays valid |
| `EMAIL_VERIFY_EXPIRE_MINUTES` | `1440` (24 hours) | How long an email confirmation link stays valid |
| `SMTP_HOST` | `sandbox.smtp.mailtrap.io` | SMTP server |
| `SMTP_PORT` | `2525` | SMTP port |
| `SMTP_USERNAME` | *(empty)* | SMTP username. If empty, emails are printed to the console instead of sent. |
| `SMTP_PASSWORD` | *(empty)* | SMTP password |
| `SMTP_STARTTLS` | `true` | Upgrade the connection with STARTTLS |
| `MAIL_FROM` | `Dzidzo <no-reply@dzidzo.local>` | Sender address on outgoing email |

#### Email in development (Mailtrap)

Development email goes to a [Mailtrap](https://mailtrap.io) sandbox inbox, which catches every message so nothing reaches a real inbox.

1. Sign up and open **Email Testing → Inboxes → My Inbox**.
2. Under **SMTP Settings**, copy the username and password into `SMTP_USERNAME` and `SMTP_PASSWORD` in `.env`. The host and port defaults already point at the sandbox.
3. Restart the server. Emails such as confirmation and password reset links now show up in that Mailtrap inbox.

If you skip this, emails are printed to the server console, which also works for local testing.

### 3. Create the database tables

```bash
uv run alembic upgrade head
```

Run this again whenever you pull changes that add a migration. The app doesn't create or change tables itself.

### 4. Build the CSS

```bash
npm run build:css     # one-off, minified build
npm run watch:css     # rebuild on change while developing
```

The output goes to `static/dist/style.css`. Git ignores it, so you need to build it after cloning.

### 5. Run the server

```bash
uv run fastapi dev main.py
```

Then open:

- http://127.0.0.1:8000: the blog
- http://127.0.0.1:8000/docs: interactive API docs (Swagger UI)

## Project structure

```
.
├── main.py            # App setup: routers, static/media mounts, table creation on startup
├── config.py          # Settings loaded from .env
├── database.py        # Async engine, session factory, get_db dependency
├── alembic.ini        # Alembic settings (the database URL comes from .env)
├── migrations/        # Alembic environment and migration scripts (versions/)
├── models.py          # SQLAlchemy models: User, Post, Tag
├── schemas.py         # Pydantic request/response schemas
├── auth.py            # Password hashing, JWT creation/validation, current-user dependencies
├── mail.py            # SMTP email sending (Mailtrap in dev)
├── images.py          # Shared image validation and WebP re-encoding (Pillow)
├── avatars.py         # Profile photo resizing and replacement
├── covers.py          # Post cover image resizing and replacement
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
| `/forgot-password` | Request a password reset email | |
| `/reset-password?token=…` | Choose a new password (link from the email) | |
| `/verify-email?token=…` | Confirm your email address (link from the email) | |
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
| POST | `/forgot-password` | Email a password reset link (`{"email": ...}`). Always returns 202. | |
| POST | `/reset-password` | Set a new password (`{"token": ..., "new_password": ...}`) | |
| POST | `/verify-email` | Confirm an email address (`{"token": ...}`) | |
| GET | `/me` | Your own profile, including your email and `email_verified_at` | ✓ |
| POST | `/me/verify-email` | Send a new confirmation email (409 if already confirmed) | ✓ |
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
| DELETE | `/{post_id}` | Delete a post and its cover image | ✓ (author) |
| PUT | `/{post_id}/cover` | Upload a cover image (multipart field `file`) | ✓ (author) |
| DELETE | `/{post_id}/cover` | Remove the cover image | ✓ (author) |

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

### Uploading a cover image

```bash
curl -X PUT http://127.0.0.1:8000/api/posts/1/cover   -H "Authorization: Bearer <token>"   -F "file=@cover.jpg"
```

The same rule applies to covers: `cover_image` is read-only in the post JSON and changes only through `PUT`/`DELETE /api/posts/{id}/cover`. It is `null` when a post has no cover.

### Validation rules

- **Username:** 1–50 characters. It can't contain `@`, which is reserved for emails so a username can never be mistaken for an email at login.
- **Email:** must look like `name@domain`, max 120 characters
- **Password:** 8–128 characters
- **Post:** title ≤ 100 characters, subtitle ≤ 200 characters, and up to 10 tags of ≤ 30 characters each
- **Profile photo and cover image:**
  - JPEG, PNG, WebP or GIF, up to 5 MB (photo) or 10 MB (cover) by default
  - Animated images can have up to 200 frames

## Profile photos and cover images

- **Processing:** every upload is saved again as WebP. Profile photos are cropped to a 256×256 square. Cover images keep their shape and are scaled down to fit within 1600×1600 (never scaled up). Re-encoding:
  - removes photo metadata such as GPS location
  - means only real images are stored, never the raw upload
  - keeps transparency and animation
- **Storage:**
  - Each file gets a random name.
  - Profile photos go in `MEDIA_ROOT/profile_pics/`, cover images in `MEDIA_ROOT/covers/`.
  - When a photo or cover is replaced or removed, the old file is deleted only after the database points to the new one. Deleting a post also deletes its cover.
- **Moving to cloud storage (e.g. S3):**
  - [storage.py](storage.py) defines a `Storage` interface with two methods: `save(key, data, content_type)`, which returns the file's public URL, and `delete(url)`.
  - `LocalStorage` writes files to `MEDIA_ROOT`.
  - To use S3, write a class with those two methods and return it from `get_storage()`. No other code needs to change.

## Email verification

- **When links are sent:** on registration, and whenever an account's email changes (profile page, `PATCH`/`PUT /api/users/{id}`, or restoring an account with a new email). Changing the email also marks it unconfirmed again.
- **Optional:** an unconfirmed account can still do everything. It sees a banner asking it to confirm, and the profile page has a "Resend link" button. The API exposes `email_verified_at` (`null` until confirmed), so you can require a confirmed email for an action later if you want.
- **The link:** contains a signed token naming the address it was sent to. It can only confirm that address, so if the email changes, earlier links stop working. Opening a link again is harmless.
- **Separate from other tokens:** confirmation tokens have their own JWT audience, so they can't be used to log in or to reset a password.

## Password reset

- **Requesting a link:** `/forgot-password` returns the same message whether or not the email has an account. The email is sent after the response, so response times don't give it away either.
- **The link:** contains a signed token that expires after `PASSWORD_RESET_EXPIRE_MINUTES`. It is built from `APP_BASE_URL`, not the request's `Host` header, so a forged header can't point reset links at another site.
- **Single use:** the token carries a fingerprint of the current password hash. Once the password changes, every earlier reset link stops working. Nothing extra is stored in the database.
- **Kept separate from login tokens:** reset tokens have their own JWT audience, so a reset token can't be used as an access token, and an access token can't be used to reset a password.
- **Existing sessions:** resetting a password doesn't log out existing sessions. Those tokens stay valid until they expire (see below).

## Notes

- **Soft deletes:**
  - A deleted account can't log in, and its tokens stop working.
  - Its username and email become free for others to register.
  - When restoring, you can pick a new username or email if the old one has been taken.
- **Schema changes go through Alembic.** After changing `models.py`:
  1. `uv run alembic revision --autogenerate -m "describe the change"` writes a migration to `migrations/versions/`.
  2. Read the generated file before applying it. Autogenerate can't detect everything; renamed columns, for example, come out as drop + add, which would lose data.
  3. `uv run alembic upgrade head` applies it. `uv run alembic downgrade -1` undoes the last one.
  4. `uv run alembic check` confirms the models and the database match.
- **Tokens can't be revoked early:** logging out clears the cookie, but a copied JWT stays valid until it expires.
