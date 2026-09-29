from datetime import datetime

from fastapi import Request
from fastapi.templating import Jinja2Templates


def current_user_context(request: Request) -> dict:
    return {"current_user": getattr(request.state, "current_user", None)}


templates = Jinja2Templates(directory="templates", context_processors=[current_user_context])
templates.env.globals["current_year"] = datetime.now().year
