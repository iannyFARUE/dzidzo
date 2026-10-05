from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # e.g. postgresql+asyncpg://user:password@localhost:5432/dbname. Percent-encode any
    # special characters in the password ("@" becomes "%40").
    database_url: SecretStr

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    media_root: str = "media"
    media_url: str = "/media"
    max_avatar_bytes: int = 5 * 1024 * 1024
    max_cover_bytes: int = 10 * 1024 * 1024

    # Where uploaded profile photos and covers go: "local" (MEDIA_ROOT) or "s3".
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_region: str = ""
    # Leave both empty to use boto3's usual credential chain (env vars, ~/.aws, IAM role).
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    # Base URL files are served from, e.g. a CloudFront domain. Defaults to the bucket's
    # own https://<bucket>.s3.<region>.amazonaws.com address.
    s3_public_url: str = ""
    # Only for S3-compatible services such as MinIO or LocalStack.
    s3_endpoint_url: str = ""

    # Used to build links in emails. Taken from config rather than the request's Host
    # header, so a forged Host can't point password-reset links at another site.
    app_base_url: str = "http://127.0.0.1:8000"
    password_reset_expire_minutes: int = 30
    email_verify_expire_minutes: int = 24 * 60

    # Defaults point at the Mailtrap sandbox; leave SMTP_USERNAME empty to print
    # emails to the console instead of sending them.
    smtp_host: str = "sandbox.smtp.mailtrap.io"
    smtp_port: int = 2525
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    mail_from: str = "Dzidzo <no-reply@dzidzo.local>"

    @model_validator(mode="after")
    def _s3_needs_bucket_and_region(self) -> Self:
        if self.storage_backend == "s3" and not (self.s3_bucket and self.s3_region):
            raise ValueError("STORAGE_BACKEND=s3 requires S3_BUCKET and S3_REGION")
        return self


settings = Settings()
