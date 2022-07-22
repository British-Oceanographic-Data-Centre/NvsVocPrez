"""Render the about page."""
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from pathlib import Path
from fastapi import APIRouter
from utilities.utility_functions import get_user_status
from utilities.templates import html_templates


router = APIRouter()


@router.get("/about", include_in_schema=False)
@router.get("/about/", include_in_schema=False)
def about(request: Request):
    return html_templates.TemplateResponse(
        "about.html", {"request": request, "logged_in_user": get_user_status(request)}
    )
