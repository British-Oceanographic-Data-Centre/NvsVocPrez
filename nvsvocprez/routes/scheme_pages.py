"""Render the Scheme Pages."""
import json
from pathlib import Path
from typing import AnyStr, Literal, Optional

from fastapi import APIRouter, HTTPException
from pyldapi import ContainerRenderer, Renderer
from pyldapi.renderer import RDF_MEDIATYPES
from rdflib import Graph
from rdflib import Literal as RdfLiteral
from rdflib import URIRef
from rdflib.namespace import RDF, RDFS
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from .page_configs import DATA_URI, SYSTEM_URI, acc_dep_map
from .profiles import dd, nvs, skos, vocpub
from .utils import (
    cache_return,
    exists_triple,
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


@router.get("/scheme/{scheme_id}/current/{acc_dep}", include_in_schema=False)
@router.head("/scheme/{scheme_id}/current/{acc_dep}", include_in_schema=False)
def scheme_concept_noslash(request: Request, scheme_id, acc_dep):
    return RedirectResponse(url=f"/scheme/{scheme_id}/current/{acc_dep}/")


@router.get("/scheme/", **paths["/scheme/"]["get"])
@router.head("/scheme/", include_in_schema=False)
def conceptschemes(request: Request):
    class ConceptSchemeRenderer(ContainerRenderer):
        def __init__(self):
            self.instance_uri = SYSTEM_URI
            self.label = "NVS Thesauri"
            self.comment = (
                "SKOS concept schemes managed by the NERC Vocabulary Server. A concept scheme can be "
                "viewed as an aggregation of one or more SKOS concepts. Semantic relationships (links) "
                "between those concepts may also be viewed as part of a concept scheme. A concept scheme "
                "is therefore useful for containing the concepts registered in multiple concept "
                "collections that relate to each other as a single semantic unit, such as a thesaurus."
            )
            super().__init__(
                request,
                self.instance_uri,
                {"nvs": nvs},
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

        def render(self):
            if self.profile == "nvs":
                if self.mediatype == "text/html":
                    conceptschemes = cache_return(collections_or_conceptschemes="conceptschemes")

                    if request.query_params.get("filter"):

                        def concat_vocab_fields(vocab):
                            return (
                                f"{vocab['id']['value']}"
                                f"{vocab['prefLabel']['value']}"
                                f"{vocab['description']['value']}"
                            )

                        conceptschemes = [
                            x for x in conceptschemes if request.query_params.get("filter") in concat_vocab_fields(x)
                        ]

                    return templates.TemplateResponse(
                        "conceptschemes.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "label": self.label,
                            "comment": self.comment,
                            "conceptschemes": conceptschemes,
                            "profile_token": "nvs",
                            "logged_in_user": get_user_status(request),
                        },
                    )
                elif self.mediatype in RDF_MEDIATYPES:
                    q = """
                        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                        PREFIX dc: <http://purl.org/dc/terms/>
                        PREFIX owl: <http://www.w3.org/2002/07/owl#>
                        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                        
                        CONSTRUCT {
                            ?cs a skos:ConceptScheme ;
                                dc:alternative ?alt ;
                                dc:creator ?creator ;
                                dc:date ?modified ;
                                dc:publisher ?publisher ;
                                dc:title ?title ;
                                owl:versionInfo ?version ;
                                skos:hasTopConcept ?tc ;
                                skos:altLabel ?al ;
                                dc:description ?description ;
                                skos:prefLabel ?pl .
                        }
                        WHERE {
                            ?cs a skos:ConceptScheme ;
                                dc:alternative ?alt ;
                                dc:creator ?creator ;
                                dc:date ?m ;
                                dc:publisher ?publisher ;
                                dc:title ?title ;
                                owl:versionInfo ?version ;
                            .
                            BIND (STRDT(REPLACE(STRBEFORE(?m, "."), " ", "T"), xsd:dateTime) AS ?modified)

                            OPTIONAL {?cs skos:hasTopConcept ?tc .}
                            OPTIONAL { ?cs skos:altLabel ?al . }
                            {
                                ?cs dc:description ?description .
                                FILTER(lang(?description) = "en" || lang(?description) = "")
                            }
                            {
                                ?cs skos:prefLabel ?pl .
                                FILTER(lang(?title) = "en" || lang(?pl) = "")
                            }
                        }
                        """
                    return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
            elif self.profile == "mem":
                collections = []
                for c in cache_return(collections_or_conceptschemes="conceptschemes"):
                    collections.append(
                        {
                            "uri": c["uri"]["value"],
                            "systemUri": c["systemUri"]["value"],
                            "label": c["prefLabel"]["value"],
                        }
                    )

                if self.mediatype == "text/html":
                    return templates.TemplateResponse(
                        "container_mem.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "label": self.label,
                            "collections": collections,
                            "profile_token": "nvs",
                            "logged_in_user": get_user_status(request),
                        },
                    )
                elif self.mediatype == "application/json":
                    return [{"uri": c["uri"], "label": c["prefLabel"]} for c in collections]
                else:  # all other available mediatypes are RDF
                    g = Graph()
                    container = URIRef(self.instance_uri)
                    g.add((container, RDF.type, RDF.Bag))
                    g.add((container, RDFS.label, RdfLiteral(self.label)))
                    for c in collections:
                        g.add((container, RDFS.member, URIRef(c["uri"])))
                        g.add((URIRef(c["uri"]), RDFS.label, RdfLiteral(c["label"])))
                    return Response(g.serialize(format=self.mediatype), media_type=self.mediatype)
            elif self.profile == "contanno":
                if self.mediatype == "text/html":
                    return templates.TemplateResponse(
                        "container_contanno.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "label": self.label,
                            "comment": self.comment,
                            "profile_token": "nvs",
                            "logged_in_user": get_user_status(request),
                        },
                    )
                else:  # all other available mediatypes are RDF
                    g = Graph()
                    container = URIRef(self.instance_uri)
                    g.add((container, RDF.type, RDF.Bag))
                    g.add((container, RDFS.label, RdfLiteral(self.label)))
                    c = (
                        "This object is a container that contains a number of members. See other profiles of this "
                        "object to see those members."
                    )
                    c += self.comment
                    g.add((container, RDFS.comment, RdfLiteral(c)))
                    return Response(g.serialize(format=self.mediatype), media_type=self.mediatype)
            alt = super().render()
            if alt is not None:
                return alt

    return ConceptSchemeRenderer().render()


# NOTE: May not be needed, but included here for clarity
@router.get("/scheme/{scheme_id}/current/{acc_dep}", include_in_schema=False)
@router.head("/scheme/{scheme_id}/current/{acc_dep}", include_in_schema=False)
def scheme_concept_noslash(request: Request, scheme_id, acc_dep):
    return RedirectResponse(url=f"/scheme/{scheme_id}/current/{acc_dep}/")


# NOTE: May not be needed, but included here for clarity
@router.get("/scheme/{scheme_id}", include_in_schema=False)
@router.get("/scheme/{scheme_id}/", include_in_schema=False)
@router.head("/scheme/{scheme_id}", include_in_schema=False)
@router.head("/scheme/{scheme_id}/", include_in_schema=False)
def scheme_no_current(request: Request, scheme_id):
    return RedirectResponse(url=f"/scheme/{scheme_id}/current/")


@router.get("/scheme/{scheme_id}/current/", **paths["/scheme/{scheme_id}/current/"]["get"])
@router.get("/scheme/{scheme_id}/current/{acc_dep}/", include_in_schema=False)
@router.head("/scheme/{scheme_id}/current/", include_in_schema=False)
@router.head("/scheme/{scheme_id}/current/{acc_dep}/", include_in_schema=False)
def scheme(
    request: Request,
    scheme_id,
    acc_dep: Literal["accepted", "deprecated", "all", None] = None,
):

    if not exists_triple(request.url.path):
        raise HTTPException(status_code=404)

    class SchemeRenderer(Renderer):
        def __init__(self):
            self.instance_uri = f"{DATA_URI}/scheme/{scheme_id}/current/"

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

        def _get_scheme(self):
            for scheme in cache_return(collections_or_conceptschemes="conceptschemes"):
                if scheme["id"]["value"] == scheme_id:
                    return scheme

        def _get_concept_hierarchy(self):
            def make_hierarchical_dicts(data):
                children_parents = []
                labels = {}

                for d in data:
                    child = d["c"]["value"]
                    parent = d["broader"]["value"] if d.get("broader") is not None else None
                    children_parents.append((child, parent))
                    labels[child] = d["pl"]["value"].replace("<", "&lt;")

                children_parents.sort(key=lambda x: x[0])
                has_parent = set()
                all_items = {}
                for child, parent in children_parents:
                    if parent not in all_items:
                        all_items[parent] = {}
                    if child not in all_items:
                        all_items[child] = {}
                    all_items[parent][child] = all_items[child]
                    has_parent.add(child)

                hierarchy = {}
                for key, value in all_items.items():
                    if key not in has_parent:
                        hierarchy[key] = value
                return hierarchy, labels

            def make_nested_ul(hierarchy, labels):
                html = ""
                for k, v in hierarchy.items():
                    if v:
                        html += (
                            f'<li><span class="caret"><a href="{k.replace(DATA_URI, "")}">{labels[k]}</a></span>'
                            if k is not None
                            else "None"
                        )
                        html += '<ul class="nested">'
                        html += make_nested_ul(v, labels)
                        html += "</ul>"
                    else:
                        html += f'<li><a href="{k.replace(DATA_URI, "")}">{labels[k]}</a>' if k is not None else "None"
                    html += "</li>"
                return html

            q = """
                PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                SELECT DISTINCT ?c ?pl ?broader
                WHERE {
                  { 
                    ?c skos:inScheme <xxx>  .
                  }
                  UNION
                  { ?c skos:topConceptOf <xxx>  . }
                  UNION
                  { <xxx>  skos:hasTopConcept ?c . }
                
                  ?c skos:prefLabel ?pl .
                  BIND (STRAFTER(STR(?c), ".uk") AS ?systemUri)
                  
                  acc_dep
                  OPTIONAL { 
                    ?c skos:broader ?broader .
                    { ?broader skos:inScheme <xxx>  . }
                    UNION
                    { ?broader skos:topConceptOf <xxx>  . }
                    UNION
                    { <xxx>  skos:hasTopConcept ?broader . }
                  }
                  FILTER(lang(?pl) = "en" || lang(?pl) = "")                                    
                }
                ORDER BY ?pl
                """.replace(
                "xxx", self.instance_uri
            ).replace(
                "acc_dep", acc_dep_map.get(acc_dep)
            )
            try:
                r = sparql_query(q)

                if not r[0]:
                    return None
                else:
                    hier = make_hierarchical_dicts(r[1])
                    hier[1][None] = None
                    return '<ul class="concept-hierarchy">' + make_nested_ul(hier[0], hier[1])[23:-5]
            except RecursionError as e:
                # make a flat list of concepts
                q = """
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    SELECT DISTINCT ?c ?pl
                    WHERE {{
                        ?c skos:inScheme <{vocab_uri}> .              
                        ?c skos:prefLabel ?pl .
                        FILTER(lang(?pl) = "en" || lang(?pl) = "") 
                    }}
                    ORDER BY ?pl
                    """.format(
                    vocab_uri=self.instance_uri
                )

                concepts = [(concept["systemUri"]["value"], concept["pl"]["value"]) for concept in sparql_query(q)]

                concepts_html = "<br />".join(['<a href="{}">{}</a>'.format(c[0], c[1]) for c in concepts])
                return """<p><strong><em>This concept hierarchy cannot be displayed</em></strong><p>
                            <p>The flat list of all this Scheme's Concepts is:</p>
                            <p>{}</p>
                        """.format(
                    concepts_html
                )

        def render(self):
            if self.profile == "nvs":
                if self.mediatype == "text/html":
                    scheme = self._get_scheme()
                    scheme["concept_hierarchy"] = self._get_concept_hierarchy()

                    if not scheme["concept_hierarchy"]:
                        return templates.TemplateResponse(
                            "error.html",
                            {
                                "request": request,
                                "title": "DB Error",
                                "status": "500",
                                "message": "There was an error with accessing the Triplestore",
                            },
                        )

                    return templates.TemplateResponse(
                        "scheme.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "scheme": scheme,
                            "profile_token": "nvs",
                            "logged_in_user": get_user_status(request),
                        },
                    )
                elif self.mediatype in RDF_MEDIATYPES:
                    q = """
                        PREFIX dcterms: <http://purl.org/dc/terms/>
                        PREFIX owl: <http://www.w3.org/2002/07/owl#>
                        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                        
                        CONSTRUCT {
                            <xxx> ?p ?o .
                            
                            ?c skos:inScheme <xxx> .
                            
                            ?c a skos:Concept ;
                                 skos:prefLabel ?pl ;
                                 skos:definition ?def ;
                                 dcterms:date ?date ;
                                 skos:broader ?broader                                  
                            .
                            
                            ?broader skos:narrower ?c .
                        }
                        WHERE {
                            <xxx> ?p ?o .
                            
                            {
                                ?c skos:inScheme <xxx> .
                            }
                            {
                                ?c a skos:Concept ;
                                     skos:prefLabel ?pl ;
                                     skos:definition ?def ;
                                     dcterms:date ?xdate ;
                                .
                                
                                BIND (STRDT(REPLACE(STRBEFORE(?xdate, "."), " ", "T"), xsd:dateTime) AS ?date)
                                
                                FILTER(lang(?pl) = "en" || lang(?pl) = "") 
                            }
                                
                            acc_dep
                            
                            OPTIONAL {
                                {
                                    ?c skos:broader ?broader .
                                    ?broader skos:inScheme <xxx> .
                                }
                                UNION 
                                {
                                    ?broader skos:narrower ?c .
                                    ?broader skos:inScheme <xxx> .
                                }
                            }                            
                        }
                        ORDER BY ?pl
                        """.replace(
                        "xxx", self.instance_uri
                    ).replace(
                        "acc_dep", acc_dep_map.get(acc_dep)
                    )
                    return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
            elif self.profile == "dd":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    SELECT DISTINCT ?c ?pl ?b
                    WHERE {
                        ?c skos:inScheme <xxx> ;
                           skos:prefLabel ?pl .

                        OPTIONAL {
                            ?b skos:inScheme <xxx> .
                            ?c skos:broader ?b .
                        }
                        
                        FILTER(lang(?pl) = "en" || lang(?pl) = "")
                    }
                    ORDER BY ?pl                
                    """.replace(
                    "xxx", self.instance_uri
                )
                r = sparql_query(q)
                return JSONResponse(
                    [
                        {
                            "uri": x["c"]["value"],
                            "prefLabel": x["pl"]["value"],
                            "broader": x["b"]["value"],
                        }
                        if x.get("b") is not None
                        else {"uri": x["c"]["value"], "prefLabel": x["pl"]["value"]}
                        for x in r[1]
                    ]
                )
            elif self.profile == "skos":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    CONSTRUCT {
                        <xxx>
                          a skos:ConceptScheme ;
                          skos:prefLabel ?pl ;
                          skos:defintion ?def ;  
                          skos:hasTopConcept ?tc ;
                        .
                        ?c a skos:Concept ;
                           skos:prefLabel ?c_pl ;
                           skos:defintion ?c_def ; 
                           skos:broader ?broader ;
                           skos:inScheme <xxx> ;
                        .
                        
                        ?tc skos:topConceptOf <xxx> .  
                        ?broader skos:narrower ?c .                        
                    }
                    WHERE {
                        <xxx>
                          skos:prefLabel ?pl ;
                          dcterms:description ?def ;  
                          skos:hasTopConcept ?tc ;
                        .
                    
                        { ?c skos:inScheme <xxx> }
                        UNION
                        { ?c skos:topConceptOf <xxx> }
                        UNION
                        { <xxx>  skos:hasTopConcept ?c }
                    
                        ?c 
                            skos:prefLabel ?c_pl ;
                            skos:definition ?c_def ;
                        .
                    
                        BIND (STRAFTER(STR(?c), ".uk") AS ?systemUri)
                        
                        OPTIONAL { 
                            ?c skos:broader ?broader .
                            { ?broader skos:inScheme <xxx>  . }
                            UNION
                            { ?broader skos:topConceptOf <xxx>  . }
                            UNION
                            { <xxx>  skos:hasTopConcept ?broader . }
                        }
                        FILTER(lang(?pl) = "en" || lang(?pl) = "")
                        FILTER(lang(?def) = "en" || lang(?def) = "")
                        FILTER(lang(?c_pl) = "en" || lang(?c_pl) = "")
                        FILTER(lang(?c_def) = "en" || lang(?c_def) = "")
                    }
                    ORDER BY ?pl
                    """.replace(
                    "xxx", self.instance_uri
                )
                return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
            elif self.profile == "vocpub":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                    
                    CONSTRUCT {
                        <xxx>
                          a skos:ConceptScheme ;
                          skos:prefLabel ?pl ;
                          skos:defintion ?def ;  
                          skos:hasTopConcept ?tc ;
                          dcterms:creator ?creator ;
                          dcterms:publisher ?publisher ;
                          dcterms:modified ?modified ;
                          dcterms:provenance "Made by NERC and maintained within the NERC Vocabulary Server" ; 
                        .                        
                        
                        ?c a skos:Concept ;
                           skos:prefLabel ?c_pl ;
                           skos:defintion ?c_def ; 
                           skos:broader ?broader ;
                           skos:inScheme <xxx> ;
                        .

                        ?tc skos:topConceptOf <xxx> .  
                        ?broader skos:narrower ?c .                        
                    }
                    WHERE {
                        <xxx>
                          skos:prefLabel ?pl ;
                          dcterms:description ?def ;  
                          skos:hasTopConcept ?tc ;
                          dcterms:publisher ?publisher ;
                          dcterms:date ?m ;                                                    
                        .
                        BIND (STRDT(REPLACE(STRBEFORE(?m, "."), " ", "T"), xsd:dateTime) AS ?modified)
                        
                        { ?c skos:inScheme <xxx> }
                        UNION
                        { ?c skos:topConceptOf <xxx> }
                        UNION
                        { <xxx>  skos:hasTopConcept ?c }

                        ?c 
                            skos:prefLabel ?c_pl ;
                            skos:definition ?c_def ;
                        .

                        BIND (STRAFTER(STR(?c), ".uk") AS ?systemUri)

                        OPTIONAL { 
                            ?c skos:broader ?broader .
                            { ?broader skos:inScheme <xxx>  . }
                            UNION
                            { ?broader skos:topConceptOf <xxx>  . }
                            UNION
                            { <xxx>  skos:hasTopConcept ?broader . }
                        }
                        FILTER(lang(?pl) = "en" || lang(?pl) = "")
                        FILTER(lang(?def) = "en" || lang(?def) = "")
                        FILTER(lang(?c_pl) = "en" || lang(?c_pl) = "")
                        FILTER(lang(?c_def) = "en" || lang(?c_def) = "")
                    }
                    ORDER BY ?pl
                    """.replace(
                    "xxx", self.instance_uri
                )
                return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

            alt = super().render()
            if alt is not None:
                return alt

    return SchemeRenderer().render()
