"""Shared Jinja2Templates instance with app-wide globals."""
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

# Expose enable_debug as a callable global so layout.html can read it
# without every route needing to pass it explicitly in context.
def _setup_globals() -> None:
    from app.config import get_settings
    templates.env.globals["enable_debug"] = lambda: get_settings().enable_debug

_setup_globals()
