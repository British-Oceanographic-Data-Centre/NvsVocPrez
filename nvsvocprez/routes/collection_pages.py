"""Render the Collection Endpoints."""
import json
from pathlib import Path
from typing import AnyStr, Literal, Optional

from fastapi import APIRouter
from pyldapi import ContainerRenderer, Renderer
from pyldapi.renderer import RDF_MEDIATYPES
from rdflib import Graph
from rdflib import Literal as RdfLiteral
from rdflib import URIRef
from rdflib.namespace import RDF, RDFS
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.templating import Jinja2Templates
from utilities import concept_renderer, collection_renderer

from .page_configs import DATA_URI, ORDS_ENDPOINT_URL, SYSTEM_URI, acc_dep_map
from .profiles import dd, nvs, skos, vocpub
from .utils import (
    cache_return,
    exists_triple,
    get_alt_profiles,
    get_ontologies,
    get_user_status,
    sparql_construct,
    sparql_query,
)

router = APIRouter()

api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))

config_file_location = Path(__file__).parent.parent / "api_doc_config.json"
with open(config_file_location, "r") as config_file:
    paths = json.load(config_file)["paths"]


def concept(request: Request):
    return concept_renderer.ConceptRenderer(request).render()


@router.get("/collection/", **paths["/collection/"]["get"])
@router.head("/collection/", include_in_schema=False)
def collections(request: Request):
    return collection_renderer.CollectionsRenderer().render()


@router.get("/collection/{collection_id}", include_in_schema=False)
@router.get("/collection/{collection_id}/", include_in_schema=False)
@router.head("/collection/{collection_id}", include_in_schema=False)
@router.head("/collection/{collection_id}/", include_in_schema=False)
def collection_no_current(request: Request, collection_id):
    return RedirectResponse(url=f"/collection/{collection_id}/current/")


@router.get(
    "/collection/{collection_id}/current/",
    **paths["/collection/{collection_id}/current/"]["get"],
)
@router.get(
    "/collection/{collection_id}/current/{acc_dep_or_concept}/",
    **paths["/collection/{collection_id}/current/{acc_dep_or_concept}/"]["get"],
)
@router.head("/collection/{collection_id}/current/", include_in_schema=False)
@router.head("/collection/{collection_id}/current/{acc_dep_or_concept}/", include_in_schema=False)
def collection(request: Request, collection_id, acc_dep_or_concept: str = None):
    if not exists_triple(request.url.path) and acc_dep_or_concept not in [
        "accepted",
        "deprecated",
        "all",
    ]:
        raise HTTPException(status_code=404)

    if acc_dep_or_concept not in ["accepted", "deprecated", "all", None]:
        return concept(request)

    return collection_renderer.CollectionRenderer().render()


@router.get(
    "/collection/{collection_id}/current/{concept_id}/{vnum}/",
    **paths["/collection/{collection_id}/current/{concept_id}/{vnum}/"]["get"],
)
@router.head("/collection/{collection_id}/current/{concept_id}/{vnum}/", include_in_schema=False)
def concept_with_version(request: Request, collection_id, concept_id, vnum: int):
    return concept(request)


@router.get("/collection/{collection_id}/current/{acc_dep_or_concept}", include_in_schema=False)
@router.head("/collection/{collection_id}/current/{acc_dep_or_concept}", include_in_schema=False)
def collection_concept_noslash(request: Request, collection_id, acc_dep_or_concept):
    return RedirectResponse(url=f"/collection/{collection_id}/current/{acc_dep_or_concept}/")
