"""Provides the location of HTML templates and Static resources to all other python files"""
from pathlib import Path
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles


api_home_dir = Path(__file__).parent.parent
html_templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))
static_files_location = StaticFiles(directory=str(api_home_dir / "view" / "static"))

sdo_location = api_home_dir / "utilities/ttl_files/sdo.ttl"
void_location = api_home_dir / "utilities/ttl_files/void.ttl"
dcat_location = api_home_dir / "utilities/ttl_files/dcat.ttl"