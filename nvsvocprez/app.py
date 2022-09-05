import logging
import json

from routes import about_page, contact_page, collection_pages, index_page, scheme_pages, sparql_pages
from authentication import login


from typing import Optional, AnyStr, Literal
from pathlib import Path
import fastapi
from fastapi import HTTPException
import uvicorn
from starlette.config import Config
from starlette.requests import Request
from starlette.responses import (
    RedirectResponse,
    Response,
    PlainTextResponse,
    JSONResponse,
)
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from pyldapi.renderer import RDF_MEDIATYPES
from pyldapi.data import RDF_FILE_EXTS
from profiles import void, nvs, skos, dd, vocpub, dcat, sdo
from routes.utils import (
    sparql_query,
    sparql_construct,
    cache_return,
    cache_clear,
    get_accepts,
    exists_triple,
    get_alt_profiles,
    get_alt_profile_objects,
    get_collection_query,
    get_ontologies,
)

from pyldapi import Renderer, ContainerRenderer, DisplayProperty
from config import SYSTEM_URI, DATA_URI, PORT
from rdflib import Graph, URIRef
from rdflib import Literal as RdfLiteral, Namespace
from rdflib.namespace import DC, DCTERMS, ORG, OWL, RDF, RDFS, SKOS, VOID


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


@api.get("/standard_name/", include_in_schema=False)
@api.get("/standard_name/{concept_id}", include_in_schema=False)
@api.get("/standard_name/{concept_id}/", **paths["/standard_name/{concept_id}/"]["get"])
@api.head("/standard_name/", include_in_schema=False)
@api.head("/standard_name/{concept_id}", include_in_schema=False)
@api.head("/standard_name/{concept_id}/", include_in_schema=False)
def standard_name(request: Request, concept_id: str = None):
    acc_dep_or_concept = concept_id

    if not exists_triple(request.url.path) and request.url.path != "/standard_name/":
        raise HTTPException(status_code=404)

    if acc_dep_or_concept not in ["accepted", "deprecated", "all", None]:
        # this is a call for a Standard Name Concept
        return standard_name_concept(request, acc_dep_or_concept)

    class CollectionRenderer(Renderer):
        def __init__(self):
            self.instance_uri = f"{DATA_URI}/collection/P07/current/"
            self.alt_profiles = get_alt_profiles()

            super().__init__(
                request,
                self.instance_uri,
                {"nvs": nvs, "skos": skos, "vocpub": vocpub, "dd": dd},
                "nvs",
            )

        def _render_sparql_response_rdf(self, sparql_response):
            if sparql_response[0]:
                return Response(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'.encode() + sparql_response[1]
                    if "xml" in self.mediatype
                    else sparql_response[1],
                    headers={"Content-Type": self.mediatype},
                )
            else:
                return PlainTextResponse(
                    "There was an error obtaining the Concept RDF from the Triplestore",
                    status_code=500,
                )

        def _get_collection(self):
            for collection in cache_return(collections_or_conceptschemes="collections"):
                if collection["id"]["value"] == "P07":
                    return collection

        def _get_concepts(self):
            q = """
                PREFIX dcterms: <http://purl.org/dc/terms/>
                PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                SELECT DISTINCT ?c ?id ?pl ?def ?date ?dep
                WHERE {
                        <xxx> skos:member ?x .
                        ?x    						
                            skos:prefLabel ?pl ;
                            skos:definition ?def ;
                            dcterms:date ?date ;
                        .
                        BIND (?pl AS ?id)
                        BIND (CONCAT("/standard_name/", ?pl, "/") AS ?c)

                        acc_dep
                        OPTIONAL {
                            ?x <http://www.w3.org/2002/07/owl#deprecated> ?dep .
                        }

                        FILTER(lang(?pl) = "en" || lang(?pl) = "") 
                        FILTER(lang(?def) = "en" || lang(?def) = "")
                }
                ORDER BY ?pl
                """.replace(
                "xxx", self.instance_uri
            ).replace(
                "acc_dep", acc_dep_map.get(acc_dep_or_concept).replace("?c", "?x")
            )

            sparql_result = sparql_query(q)
            if sparql_result[0]:
                return [
                    {
                        "systemUri": concept["c"]["value"],
                        "id": concept["id"]["value"],
                        "prefLabel": concept["pl"]["value"].replace("_", " "),
                        "definition": concept["def"]["value"].replace("_", "_ "),
                        "date": concept["date"]["value"][0:10],
                        "deprecated": True if concept.get("dep") and concept["dep"]["value"] == "true" else False,
                    }
                    for concept in sparql_result[1]
                ]
            else:
                return False

        def render(self):
            if self.profile == "nvs":
                if self.mediatype == "text/html":
                    collection = self._get_collection()
                    collection["concepts"] = self._get_concepts()

                    if not collection["concepts"]:
                        return templates.TemplateResponse(
                            "error.html",
                            {
                                "request": request,
                                "title": "DB Error",
                                "status": "500",
                                "message": "There was an error with accessing the Triplestore",
                            },
                        )

                    self.instance_uri = f"{DATA_URI}/standard_name/"

                    return templates.TemplateResponse(
                        "collection.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "collection": collection,
                            "profile_token": "nvs",
                            "alt_profiles": self.alt_profiles,
                        },
                    )
                elif self.mediatype in RDF_MEDIATYPES:
                    q = """
                        PREFIX dc: <http://purl.org/dc/terms/>
                        PREFIX dce: <http://purl.org/dc/elements/1.1/>
                        PREFIX grg: <http://www.isotc211.org/schemas/grg/>
                        PREFIX owl: <http://www.w3.org/2002/07/owl#>
                        PREFIX pav: <http://purl.org/pav/>
                        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                        PREFIX void: <http://rdfs.org/ns/void#>
                                                
                        CONSTRUCT {
                            <DATA_URI/standard_name/> ?p ?o .                           
                            <DATA_URI/standard_name/> skos:member ?m .                        
                            ?m ?p2 ?o2 .   
                        }
                        WHERE {
                            {
                                <DATA_URI/collection/P07/current/> ?p ?o .                          
                                MINUS { <DATA_URI/collection/P07/current/> skos:member ?o . }
                            }
                          
                            {
                                <DATA_URI/collection/P07/current/> skos:member ?mx .
                                ?mx a skos:Concept ;
                                      skos:prefLabel ?pl ;
                                .
                        
                                FILTER(!isLiteral(?pl) || lang(?pl) = "en" || lang(?pl) = "")  
                        
                                ?mx ?p2 ?o2 .
                                
                                FILTER ( ?p2 != skos:broaderTransitive )
                                FILTER ( ?p2 != skos:narrowerTransitive )
                            }
                          
                            BIND (IRI(CONCAT("DATA_URI/standard_name/", STR(?pl), "/")) AS ?m)
                        }
                        """.replace(
                        "DATA_URI", DATA_URI
                    )
                    return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
            elif self.profile == "dd":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    SELECT DISTINCT ?c ?pl ?b
                    WHERE {
                        <xxx> skos:member ?xc .
                        ?xc skos:prefLabel ?xpl .
                        
                        BIND (CONCAT("DATA_URI/standard_name/", ?xpl, "/") AS ?c)
                        BIND (REPLACE(?xpl, "_", " ") AS ?pl)
                    }
                    ORDER BY ?pl                
                    """.replace(
                    "xxx", self.instance_uri
                ).replace(
                    "DATA_URI", DATA_URI
                )
                r = sparql_query(q)
                return JSONResponse([{"uri": x["c"]["value"], "prefLabel": x["pl"]["value"]} for x in r[1]])
            elif self.profile == "skos":
                q = """
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>                    
                    CONSTRUCT {
                        <DATA_URI/standard_name/> 
                            a skos:Collection ;
                            skos:prefLabel ?prefLabel ;
                            skos:definition ?description ;
                            skos:member ?c .
                        ?c skos:prefLabel ?c_pl .
                    }
                    WHERE {
                        <xxx> 
                            a skos:Collection ;
                            skos:prefLabel ?prefLabel ;
                            <http://purl.org/dc/terms/description> ?description ;
                            skos:member ?xc .
                        ?xc skos:prefLabel ?xc_pl .
                        
                        BIND (CONCAT("DATA_URI/standard_name/", ?xc_pl, "/") AS ?c)
                        BIND (REPLACE(?xc_pl, "_", " ") AS ?c_pl)                        
                    }
                    ORDER BY ?prefLabel
                    """.replace(
                    "xxx", self.instance_uri
                ).replace(
                    "DATA_URI", DATA_URI
                )
                return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
            elif self.profile == "vocpub":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                    CONSTRUCT {
                        <DATA_URI/standard_name/> 
                            a skos:Collection ;
                            skos:prefLabel ?prefLabel ;
                            skos:definition ?description ;
                            dcterms:modified ?modified ;
                            dcterms:creator ?creator ;
                            dcterms:publisher ?publisher ;   
                            dcterms:provenance "Made by NERC and maintained within the NERC Vocabulary Server" ;                            
                            skos:member ?c .
                        ?c skos:prefLabel ?c_pl .
                    }
                    WHERE {
                        <xxx> 
                            a skos:Collection ;
                            skos:prefLabel ?prefLabel ;                            
                            dcterms:description ?description ;
                            dcterms:date ?date ;
                            dcterms:creator ?creator ;
                            dcterms:publisher ?publisher ;                             
                            skos:member ?xc .
                        ?xc skos:prefLabel ?xc_pl .
                        
                        BIND (CONCAT("DATA_URI/standard_name/", ?xc_pl, "/") AS ?c)
                        BIND (REPLACE(?xc_pl, "_", " ") AS ?c_pl)
                        BIND (STRDT(REPLACE(STRBEFORE(?date, "."), " ", "T"), xsd:dateTime) AS ?modified)
                    }
                    ORDER BY ?xc                    
                    """.replace(
                    "xxx", self.instance_uri
                ).replace(
                    "DATA_URI", DATA_URI
                )
                return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

            self.instance_uri = f"{DATA_URI}/standard_name/"
            alt = super().render()
            if alt is not None:
                return alt

    return CollectionRenderer().render()


def standard_name_concept(request: Request, standard_name_concept_id: str):
    c = collection_pages.ConceptRenderer(request)
    return c.render()


@api.get("/mapping/{int_ext}/{mapping_id}/", **paths["/mapping/{int_ext}/{mapping_id}/"]["get"])
@api.head("/mapping/{int_ext}/{mapping_id}/", include_in_schema=False)
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

            return templates.TemplateResponse("mapping.html", context=context)

    return MappingRenderer().render()


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
