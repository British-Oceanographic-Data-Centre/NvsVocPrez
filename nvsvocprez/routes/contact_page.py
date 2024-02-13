"""Render the contact page."""

from starlette.requests import Request
from starlette.templating import Jinja2Templates
from pathlib import Path
from fastapi import APIRouter
from .utils import get_user_status

router = APIRouter()

api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))


@router.get("/contact", include_in_schema=False)
@router.get("/contact-us", include_in_schema=False)
@router.get("/contact/", include_in_schema=False)
@router.get("/contact-us/", include_in_schema=False)
@router.head("/contact", include_in_schema=False)
@router.head("/contact-us", include_in_schema=False)
def contact(request: Request):
    return templates.TemplateResponse(
        "contact_us.html",
        {"request": request, "logged_in_user": get_user_status(request)},
    )
