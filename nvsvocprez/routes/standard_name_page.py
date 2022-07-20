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

from .page_configs import DATA_URI
from .profiles import nvs
from .utils import exists_triple, sparql_construct
from utilities import concept_renderer

router = APIRouter()

api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))

config_file_location = Path(__file__).parent.parent / "api_doc_config.json"
with open(config_file_location, "r") as config_file:
    paths = json.load(config_file)["paths"]


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
    c = concept_renderer.ConceptRenderer(request)
    return c.render()



