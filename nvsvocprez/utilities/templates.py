"""Provides the location of HTML templates to all other python files"""
from pathlib import Path
from starlette.templating import Jinja2Templates


api_home_dir = Path(__file__).parent.parent
html_templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))

