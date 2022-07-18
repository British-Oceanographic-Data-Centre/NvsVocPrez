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

# NOTE: Logging removed from this file.


@router.get("/collection/", **paths["/collection/"]["get"])
@router.head("/collection/", include_in_schema=False)
def collections(request: Request):
    class CollectionsRenderer(ContainerRenderer):
        def __init__(self):
            self.instance_uri = SYSTEM_URI
            self.label = "NVS Vocabularies"
            self.comment = (
                "SKOS concept collections held in the NERC Vocabulary Server. A concept collection "
                "is useful where a group of concepts shares something in common, and it is convenient "
                "to group them under a common label. In the NVS, concept collections are synonymous "
                "with controlled vocabularies or code lists. Each collection is associated with its "
                "governance body. An external website link is displayed when applicable."
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
                    '<?xml version="1.0" encoding="UTF-8"?>\n'.encode()
                    + sparql_response[1]
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
                    collections = cache_return(
                        collections_or_conceptschemes="collections"
                    )

                    if request.query_params.get("filter"):

                        def concat_vocab_fields(vocab):
                            return (
                                f"{vocab['id']['value']}"
                                f"{vocab['prefLabel']['value']}"
                                f"{vocab['description']['value']}"
                            )

                        collections = [
                            coll
                            for coll in collections
                            if request.query_params.get("filter")
                            in concat_vocab_fields(coll)
                        ]

                    return templates.TemplateResponse(
                        "collections.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "label": self.label,
                            "comment": self.comment,
                            "collections": collections,
                            "profile_token": self.profile,
                            "logged_in_user": get_user_status(request)
                        },
                    )
                elif self.mediatype in RDF_MEDIATYPES:
                    query = """
                        PREFIX dc: <http://purl.org/dc/terms/>
                        PREFIX grg: <http://www.isotc211.org/schemas/grg/>
                        PREFIX owl: <http://www.w3.org/2002/07/owl#>
                        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                        CONSTRUCT {
                            ?cs a skos:Collection ;
                                dc:alternative ?alternative ;
                                dc:creator ?creator ;
                                dc:date ?date ;
                                dc:description ?description ;
                                dc:publisher ?publisher ;
                                dc:title ?title ;
                                rdfs:comment ?comment ;
                                owl:versionInfo ?version ;
                                skos:altLabel ?al ;
                                skos:narrower ?narrower ;
                                skos:prefLabel ?pl .
                            ?cs
                                grg:RE_RegisterManager ?registermanager ;
                                grg:RE_RegisterOwner ?registerowner .
                            ?cs rdfs:seeAlso ?seeAlso .
                            ?cs dc:conformsTo ?conformsTo .
                        }
                        WHERE {
                            ?cs a skos:Collection ;
                                dc:alternative ?alternative ;
                                dc:creator ?creator ;
                                dc:date ?date ;
                                dc:description ?description ;
                                dc:publisher ?publisher ;
                                dc:title ?title ;
                                rdfs:comment ?comment ;
                                owl:versionInfo ?version ;
                                skos:prefLabel ?pl .
                            OPTIONAL { ?cs skos:altLabel ?al }
                            OPTIONAL { ?cs skos:narrower ?narrower }
                            OPTIONAL {
                                ?cs skos:prefLabel ?pl .
                                FILTER(lang(?pl) = "en" || lang(?pl) = "")
                            }
                            OPTIONAL {
                                ?cs grg:RE_RegisterManager ?registermanager .
                                ?cs grg:RE_RegisterManager ?registerowner .
                            }
                            OPTIONAL { ?cs rdfs:seeAlso ?seeAlso }
                            OPTIONAL { ?cs dc:conformsTo ?conformsTo }
                        } 
                        """
                    return self._render_sparql_response_rdf(
                        sparql_construct(query, self.mediatype)
                    )
            elif self.profile == "mem":
                collections = []
                for coll in cache_return(collections_or_conceptschemes="collections"):
                    collections.append(
                        {
                            "uri": coll["uri"]["value"],
                            "systemUri": coll["systemUri"]["value"],
                            "label": coll["prefLabel"]["value"],
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
                    return [
                        {"uri": coll["uri"], "label": coll["prefLabel"]}
                        for coll in collections
                    ]
                else:  # all other available mediatypes are RDF
                    graph = Graph()
                    container = URIRef(self.instance_uri)
                    graph.add((container, RDF.type, RDF.Bag))
                    graph.add((container, RDFS.label, RdfLiteral(self.label)))
                    for coll in collections:
                        graph.add((container, RDFS.member, URIRef(coll["uri"])))
                        graph.add(
                            (
                                URIRef(coll["uri"]),
                                RDFS.label,
                                RdfLiteral(collection["label"]),
                            )
                        )
                    return Response(
                        graph.serialize(format=self.mediatype),
                        media_type=self.mediatype,
                    )
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
                graph = Graph()
                container = URIRef(self.instance_uri)
                graph.add((container, RDF.type, RDF.Bag))
                graph.add((container, RDFS.label, RdfLiteral(self.label)))
                container_message = (
                    "This object is a container that contains a number of members. See other profiles of this "
                    "object to see those members."
                )
                container_message += self.comment
                graph.add((container, RDFS.comment, RdfLiteral(container_message)))
                return Response(
                    graph.serialize(format=self.mediatype), media_type=self.mediatype
                )

            alt = super().render()
            if alt is not None:
                return alt

    return CollectionsRenderer().render()


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
@router.head(
    "/collection/{collection_id}/current/{acc_dep_or_concept}/", include_in_schema=False
)
def collection(request: Request, collection_id, acc_dep_or_concept: str = None):

    if not exists_triple(request.url.path) and acc_dep_or_concept not in [
        "accepted",
        "deprecated",
        "all",
    ]:
        raise HTTPException(status_code=404)

    if acc_dep_or_concept not in ["accepted", "deprecated", "all", None]:
        # this is a call for a Concept
        return concept(request)

    class CollectionRenderer(Renderer):
        def __init__(self):
            self.alt_profiles = get_alt_profiles()
            self.ontologies = get_ontologies()
            self.instance_uri = f"{DATA_URI}/collection/{collection_id}/current/"

            profiles = {"nvs": nvs, "skos": skos, "vocpub": vocpub, "dd": dd}
            for collection in cache_return(collections_or_conceptschemes="collections"):
                if collection["id"]["value"] == collection_id:
                    if collection.get("conforms_to"):
                        profiles.update(
                            get_alt_profile_objects(
                                collection=collection,
                                alt_profiles=self.alt_profiles,
                                ontologies=self.ontologies,
                            )
                        )

            super().__init__(
                request,
                self.instance_uri,
                profiles,
                "nvs",
            )

        def _render_sparql_response_rdf(self, sparql_response):
            if sparql_response[0]:
                return Response(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'.encode()
                    + sparql_response[1]
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
                if collection["id"]["value"] == collection_id:
                    return collection

        def _get_concepts(self):
            q = """
                PREFIX dcterms: <http://purl.org/dc/terms/>
                PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                SELECT DISTINCT ?c ?systemUri ?id ?pl ?def ?date ?dep
                WHERE {
                        <xxx> skos:member ?c .
                        BIND (STRBEFORE(STRAFTER(STR(?c), "/current/"), "/") AS ?id)
                        BIND (STRAFTER(STR(?c), ".uk") AS ?systemUri)

                        acc_dep
                        
                        OPTIONAL {
                            ?c <http://www.w3.org/2002/07/owl#deprecated> ?dep .
                        }
                        ?c skos:prefLabel ?pl ;
                             skos:definition ?def ;
                             dcterms:date ?date .

                        FILTER(lang(?pl) = "en" || lang(?pl) = "") 
                        FILTER(lang(?def) = "en" || lang(?def) = "")                    
                }
                ORDER BY ?pl
                """.replace(
                "xxx", self.instance_uri
            ).replace(
                "acc_dep", acc_dep_map.get(acc_dep_or_concept)
            )

            sparql_result = sparql_query(q)
            if sparql_result[0]:
                return [
                    {
                        "uri": concept["c"]["value"],
                        "id": concept["id"]["value"],
                        "systemUri": concept["systemUri"]["value"],
                        "prefLabel": concept["pl"]["value"].replace("_", " "),
                        "definition": concept["def"]["value"].replace("_", "_ "),
                        "date": concept["date"]["value"][0:10],
                        "deprecated": True
                        if concept.get("dep") and concept["dep"]["value"] == "true"
                        else False,
                    }
                    for concept in sparql_result[1]
                ]
            else:
                return False

        def render(self):
            current_profile = self.profiles[self.profile]
            alt_profile_tokens = [alt["token"] for alt in self.alt_profiles.values()]

            if self.profile == "nvs":
                if self.mediatype == "text/html":
                    collection = self._get_collection()
                    collection["concepts"] = self._get_concepts()

                    if len(collection["concepts"]) == 0:
                        pass
                    elif not collection["concepts"]:
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
                        "collection.html",
                        {
                            "request": request,
                            "uri": self.instance_uri,
                            "collection": collection,
                            "profile_token": self.profile,
                            "alt_profiles": self.alt_profiles,
                        },
                    )
                elif self.mediatype in RDF_MEDIATYPES:
                    # Get the term for the collection query WHERE clause to filter or accepted or deprecated.
                    # This will be an empty string if neither condition is true.
                    acc_dep_term = acc_dep_map.get(acc_dep_or_concept).replace(
                        "?c", "?m"
                    )
                    query = get_collection_query(
                        current_profile,
                        self.instance_uri,
                        self.ontologies,
                        acc_dep_term,
                    )
                    return self._render_sparql_response_rdf(
                        sparql_construct(query, self.mediatype)
                    )
            elif self.profile == "dd":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    SELECT DISTINCT ?c ?pl
                    WHERE {
                        <xxx> skos:member ?c .
                        acc_dep
                        ?c skos:prefLabel ?pl .
                    }
                    ORDER BY ?pl                
                    """.replace(
                    "xxx", self.instance_uri
                ).replace(
                    "acc_dep", acc_dep_map.get(acc_dep_or_concept)
                )
                r = sparql_query(q)
                return JSONResponse(
                    [
                        {"uri": x["c"]["value"], "prefLabel": x["pl"]["value"]}
                        for x in r[1]
                    ]
                )
            elif self.profile == "skos":
                q = """
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>                    
                    CONSTRUCT {
                        <xxx> 
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
                            skos:member ?c .
                            acc_dep
                        ?c skos:prefLabel ?c_pl .
                    }
                    ORDER BY ?prefLabel
                    """.replace(
                    "xxx", self.instance_uri
                ).replace(
                    "acc_dep", acc_dep_map.get(acc_dep_or_concept)
                )
                return self._render_sparql_response_rdf(
                    sparql_construct(q, self.mediatype)
                )
            elif self.profile == "vocpub":
                q = """
                    PREFIX dcterms: <http://purl.org/dc/terms/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    CONSTRUCT {
                        <xxx>
                            a skos:Collection ;
                            skos:prefLabel ?prefLabel ;
                            skos:definition ?description ;
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
                            dcterms:creator ?creator ;
                            dcterms:publisher ?publisher ;   
                            skos:member ?c .
                            acc_dep
  
                        ?c skos:prefLabel ?c_pl .
                    }
                    """.replace(
                    "xxx", self.instance_uri
                ).replace(
                    "acc_dep", acc_dep_map.get(acc_dep_or_concept)
                )
                return self._render_sparql_response_rdf(
                    sparql_construct(q, self.mediatype)
                )
            elif self.profile in alt_profile_tokens:
                # Get the term for the collection query WHERE clause to filter or accepted or deprecated.
                # This will be an empty string if neither condition is true.
                acc_dep_term = acc_dep_map.get(acc_dep_or_concept).replace("?c", "?m")
                query = get_collection_query(
                    current_profile, self.instance_uri, self.ontologies, acc_dep_term
                )
                return self._render_sparql_response_rdf(
                    sparql_construct(query, self.mediatype)
                )

            alt = super().render()
            if alt is not None:
                return alt

    return CollectionRenderer().render()


@router.get(
    "/collection/{collection_id}/current/{concept_id}/{vnum}/",
    **paths["/collection/{collection_id}/current/{concept_id}/{vnum}/"]["get"],
)
@router.head(
    "/collection/{collection_id}/current/{concept_id}/{vnum}/", include_in_schema=False
)
def concept_with_version(request: Request, collection_id, concept_id, vnum: int):
    return concept(request)


@router.get(
    "/collection/{collection_id}/current/{acc_dep_or_concept}", include_in_schema=False
)
@router.head(
    "/collection/{collection_id}/current/{acc_dep_or_concept}", include_in_schema=False
)
def collection_concept_noslash(request: Request, collection_id, acc_dep_or_concept):
    return RedirectResponse(
        url=f"/collection/{collection_id}/current/{acc_dep_or_concept}/"
    )
