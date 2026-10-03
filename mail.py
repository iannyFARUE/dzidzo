import logging
import smtplib
from email.message import EmailMessage

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings

logger = logging.getLogger(__name__)

# Separate from the page templates so the plain-text parts aren't HTML-escaped.
email_templates = Environment(
    loader=FileSystemLoader("templates/email"),
    autoescape=select_autoescape(["html"]),
)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Send an email over SMTP. Blocking, so call it from a BackgroundTask.

    Failures are logged rather than raised: the response has already gone out, and
    the password-reset flow deliberately never tells the client whether a mail was sent.
    """
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    if html is not None:
        message.add_alternative(html, subtype="html")

    if not settings.smtp_username:
        logger.warning("SMTP_USERNAME not set; printing email instead of sending it")
        print(f"\n----- email to {to} -----\nSubject: {subject}\n\n{text}\n-----\n", flush=True)
        return

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError):
        logger.exception("failed to send email %r to %s", subject, to)


def site_url(path: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}"


def send_templated_email(to: str, subject: str, template: str, context: dict) -> None:
    send_email(
        to,
        subject,
        email_templates.get_template(f"{template}.txt").render(context),
        email_templates.get_template(f"{template}.html").render(context),
    )


def send_password_reset_email(to: str, name: str, token: str) -> None:
    send_templated_email(to, "Reset your Dzidzo password", "password_reset", {
        "name": name,
        "reset_url": site_url(f"/reset-password?token={token}"),
        "expire_minutes": settings.password_reset_expire_minutes,
    })


def send_verification_email(to: str, name: str, token: str) -> None:
    send_templated_email(to, "Confirm your email for Dzidzo", "verify_email", {
        "name": name,
        "verify_url": site_url(f"/verify-email?token={token}"),
        "expire_hours": settings.email_verify_expire_minutes // 60,
    })
