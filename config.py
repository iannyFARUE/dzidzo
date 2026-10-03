from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    media_root: str = "media"
    media_url: str = "/media"
    max_avatar_bytes: int = 5 * 1024 * 1024
    max_cover_bytes: int = 10 * 1024 * 1024

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


settings = Settings()
