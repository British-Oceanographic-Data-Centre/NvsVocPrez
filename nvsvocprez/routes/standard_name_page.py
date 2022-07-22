"""Render the Standard Name page."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pyldapi import Renderer
from pyldapi.renderer import RDF_MEDIATYPES
from rdflib import Graph
from rdflib import Namespace, URIRef
from rdflib.namespace import DC, ORG
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.templating import Jinja2Templates

from utilities.system_configs import DATA_URI
from utilities.profiles import nvs
from utilities.utility_functions import exists_triple, sparql_construct
from utilities import concept_renderer
from utilities.templates import paths

router = APIRouter()


@router.get("/standard_name/", include_in_schema=False)
@router.get("/standard_name/{concept_id}", include_in_schema=False)
@router.get("/standard_name/{concept_id}/", **paths["/standard_name/{concept_id}/"]["get"])
@router.head("/standard_name/", include_in_schema=False)
@router.head("/standard_name/{concept_id}", include_in_schema=False)
@router.head("/standard_name/{concept_id}/", include_in_schema=False)
def standard_name(request: Request, concept_id: str = None):
    acc_dep_or_concept = concept_id

    if not exists_triple(request.url.path) and request.url.path != "/standard_name/":
        raise HTTPException(status_code=404)

    if acc_dep_or_concept not in ["accepted", "deprecated", "all", None]:
        # this is a call for a Standard Name Concept
        return standard_name_concept(request, acc_dep_or_concept)


def standard_name_concept(request: Request, standard_name_concept_id: str):
    c = concept_renderer.ConceptRenderer(request)
    return c.render()
