"""Render the about page."""
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from pathlib import Path
from fastapi import APIRouter
from .utils import get_user_status
from utilities import config

router = APIRouter()
api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))


@router.get("/about/")
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "logged_in_user": get_user_status(request)})
