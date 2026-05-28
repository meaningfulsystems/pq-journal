"""Shared Jinja2Templates instance with app-wide globals."""
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def _setup_globals() -> None:
    from app.config import get_settings
    templates.env.globals["ai_mode"] = lambda: get_settings().ai_mode

_setup_globals()
