"""Render the mapping page."""
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
from utilities.templates import html_templates, paths

router = APIRouter()


@router.get("/mapping/{int_ext}/{mapping_id}/", **paths["/mapping/{int_ext}/{mapping_id}/"]["get"])
@router.head("/mapping/{int_ext}/{mapping_id}/", include_in_schema=False)
def mapping(request: Request):

    if not exists_triple(request.url.path):
        raise HTTPException(status_code=404)

    class MappingRenderer(Renderer):
        def __init__(self):
            self.instance_uri = f"{DATA_URI}/mapping/" + str(request.url).split("/mapping/")[1].split("?")[0]

            super().__init__(request, self.instance_uri, {"nvs": nvs}, "nvs")

        def render(self):
            if "/I/" not in self.instance_uri and "/E/" not in self.instance_uri:
                return PlainTextResponse(
                    'All requests for Mappings must contain either "I" or "E" in the URI',
                    status_code=400,
                )

            if self.profile == "nvs":
                g = self._get_mapping_rdf()
                if not g:
                    return PlainTextResponse(
                        "There was an error obtaining the Collections RDF from the Triplestore",
                        status_code=500,
                    )
                if len(g) == 0:
                    return PlainTextResponse(
                        "The URI you supplied for the Mapping does not exist",
                        status_code=400,
                    )

                if self.mediatype in RDF_MEDIATYPES or self.mediatype in Renderer.RDF_SERIALIZER_TYPES_MAP:
                    return self._render_nvs_rdf(g)
                else:
                    return self._render_nvs_html(g)

            # try returning alt profile
            response = super().render()
            if response is not None:
                return response

        def _get_mapping_rdf(self):
            r = sparql_construct(f"DESCRIBE <{self.instance_uri}>")
            if r[0]:
                return Graph().parse(r[1])
            else:
                return False

        def _render_nvs_rdf(self, g):
            g.bind("dc", DC)
            REG = Namespace("http://purl.org/linked-data/registry#")
            g.bind("reg", REG)
            g.bind("org", ORG)

            # handle broken Org URI use
            broken = URIRef("http://www.w3.org/ns/org#")
            for s, o in g.subject_objects(predicate=broken):
                g.remove((s, broken, o))
                g.add((s, ORG.Organization, o))

            return self._make_rdf_response(g)

        def _render_nvs_html(self, g):
            mapping = {}
            for p, o in g.predicate_objects(subject=URIRef(self.instance_uri)):
                if str(p) == "http://www.w3.org/1999/02/22-rdf-syntax-ns#subject":
                    mapping["subject"] = str(o)
                elif str(p) == "http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate":
                    mapping["predicate"] = str(o)
                elif str(p) == "http://www.w3.org/1999/02/22-rdf-syntax-ns#object":
                    mapping["object"] = str(o)
                elif str(p) == "http://purl.org/dc/elements/1.1/modified":
                    mapping["modified"] = str(o)
                elif str(p) == "http://purl.org/linked-data/registry#status":
                    mapping["status"] = str(o)
                elif str(p) == "http://purl.org/linked-data/registry#submitter":
                    for p2, o2 in g.predicate_objects(subject=o):
                        if str(p2) == "http://purl.org/linked-data/registry#title":
                            mapping["title"] = str(o2)
                        elif str(p2) == "http://purl.org/linked-data/registry#name":
                            mapping["name"] = str(o2)
                        elif str(p2) == "http://www.w3.org/ns/org#memberOf":
                            mapping["memberof"] = str(o2)

            context = {
                "request": request,
                "uri": self.instance_uri,
                "systemUri": self.instance_uri.replace(DATA_URI, ""),
                "subject": mapping["subject"],
                "subjectSystemUri": mapping["subject"].replace(DATA_URI, ""),
                "predicate": mapping["predicate"],
                "predicateSystemUri": mapping["predicate"].replace(DATA_URI, ""),
                "object": mapping["object"],
                "objectSystemUri": mapping["object"].replace(DATA_URI, ""),
                "modified": mapping["modified"],
                "status": mapping["status"],
                "submitter_title": mapping.get("title"),
                "submitter_name": mapping.get("name"),
                "submitter_memberof": mapping.get("memberof"),
                "profile_token": self.profile,
            }

            return html_templates.TemplateResponse("mapping.html", context=context)

    return MappingRenderer().render()