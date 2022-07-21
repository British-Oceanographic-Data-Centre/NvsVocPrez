"""Provides the location of HTML templates and resources to all other python files"""
import json
from pathlib import Path
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles


api_home_dir = Path(__file__).parent.parent
html_templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))
static_files_location = StaticFiles(directory=str(api_home_dir / "view" / "static"))

sdo_location = api_home_dir / "utilities/ttl_files/sdo.ttl"
void_location = api_home_dir / "utilities/ttl_files/void.ttl"
dcat_location = api_home_dir / "utilities/ttl_files/dcat.ttl"


config_file_location = Path(__file__).parent.parent / "api_doc_config.json"
with open(config_file_location, "r") as config_file:
    paths = json.load(config_file)["paths"]