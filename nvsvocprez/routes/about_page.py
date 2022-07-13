from starlette.requests import Request
from starlette.templating import Jinja2Templates
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))

@router.get("/about/")
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})