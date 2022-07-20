import json
import logging
from pathlib import Path
from typing import AnyStr, Literal, Optional

import fastapi
import uvicorn
from fastapi import HTTPException
from rdflib import Graph
from rdflib import Literal as RdfLiteral
from rdflib import Namespace, URIRef
from rdflib.namespace import DC, DCTERMS, ORG, OWL, RDF, RDFS, SKOS, VOID
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import (JSONResponse, PlainTextResponse,
                                 RedirectResponse, Response)
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from authentication import login
from config import DATA_URI, PORT, SYSTEM_URI
from profiles import dcat, dd, nvs, sdo, skos, vocpub, void
from pyldapi import ContainerRenderer, DisplayProperty, Renderer
from pyldapi.data import RDF_FILE_EXTS
from pyldapi.renderer import RDF_MEDIATYPES
from routes import (about_page, collection_pages, contact_page, index_page,
                    mapping_page, scheme_pages, sparql_pages,
                    standard_name_page)
from utils import (cache_clear, cache_return, exists_triple, get_accepts,
                   get_alt_profile_objects, get_alt_profiles,
                   get_collection_query, get_ontologies, sparql_construct,
                   sparql_query)

#### Initial Setup ####
# NOTE: This should be refactored into a function/Class
api_home_dir = Path(__file__).parent
with open("api_doc_config.json", "r") as config_file:
    doc_config = json.load(config_file)


api_details = doc_config["api_details"]
tags = doc_config["tags"]
paths = doc_config["paths"]

api = fastapi.FastAPI(
    title=api_details["title"],
    description=api_details["description"],
    version=api_details["version"],
    contact=api_details["contact"],
    license_info=api_details["license_info"],
    openapi_tags=tags,
    docs_url=api_details["docs_url"],
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

config = Config(".env")
api.add_middleware(
    SessionMiddleware, max_age=config("MAX_SESSION_LENGTH", cast=int, default=None), secret_key=config("APP_SECRET_KEY")
)

templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))
api.mount(
    "/static",
    StaticFiles(directory=str(api_home_dir / "view" / "static")),
    name="static",
)


acc_dep_map = {
    "accepted": '?c <http://www.w3.org/2002/07/owl#deprecated> "false" .',
    "deprecated": '?c <http://www.w3.org/2002/07/owl#deprecated> "true" .',
    "all": "",
    None: "",
}

#### Add the imported routes to the API ####
# NOTE: To be refactored into a function, or part of a Class.
api.include_router(index_page.router)
api.include_router(about_page.router)
api.include_router(contact_page.router)
api.include_router(collection_pages.router)
api.include_router(login.router)
api.include_router(scheme_pages.router)
api.include_router(sparql_pages.router)
api.include_router(mapping_page.router)
api.include_router(standard_name_page.router)


@api.get("/.well_known/", include_in_schema=False)
@api.head("/.well_known/", include_in_schema=False)
def well_known(request: Request):
    return RedirectResponse(url="/.well_known/void")

@api.get("/.well_known/void", include_in_schema=False)
@api.head("/.well_known/void", include_in_schema=False)
def well_known_void(
    request: Request,
    _profile: Optional[AnyStr] = None,
    _mediatype: Optional[AnyStr] = "text/turtle",
):

    void_file = api_home_dir / "void.ttl"

    class WkRenderer(Renderer):
        def __init__(self):
            super().__init__(
                request,
                f"{DATA_URI}/.well_known/void",
                {"void": void},
                "void",
            )

        def render(self):
            if self.mediatype == "text/turtle":
                return Response(open(void_file).read(), headers={"Content-Type": "text/turtle"})
            else:
                from rdflib import Graph

                g = Graph().parse(void_file, format="turtle")
                return Response(
                    content=g.serialize(format=self.mediatype),
                    headers={"Content-Type": self.mediatype},
                )

    return WkRenderer().render()


@api.get("/cache-clear", include_in_schema=False)
def cache_clr(request: Request):
    cache_clear()
    return PlainTextResponse("Cache cleared")


if __name__ == "__main__":
    uvicorn.run(api, port=PORT, host=SYSTEM_URI)
