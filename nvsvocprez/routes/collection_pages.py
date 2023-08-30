"""Render the Collection Endpoints."""
import json
from pathlib import Path
from typing import AnyStr, Literal, Optional, Tuple
import requests as rq
from fastapi import APIRouter, HTTPException
from pyldapi import ContainerRenderer, Renderer, DisplayProperty
from pyldapi.renderer import RDF_MEDIATYPES
from rdflib import Graph
from rdflib import Literal as RdfLiteral, Namespace
from rdflib import URIRef
from rdflib.namespace import DC, DCTERMS, ORG, OWL, RDF, RDFS, SKOS, VOID
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, RedirectResponse, JSONResponse
from starlette.templating import Jinja2Templates

from .page_configs import DATA_URI, ORDS_ENDPOINT_URL, SYSTEM_URI, acc_dep_map
from .profiles import void, nvs, skos, dd, vocpub, dcat, sdo
from .utils import (
    cache_return,
    exists_triple,
    get_alt_profiles,
    get_collection_query,
    get_alt_profile_objects,
    get_ontologies,
    get_user_status,
    sparql_construct,
    sparql_query,
)
import re
from collections import Counter, defaultdict

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
                    collections = cache_return(collections_or_conceptschemes="collections")

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
                            if request.query_params.get("filter") in concat_vocab_fields(coll)
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
                            "logged_in_user": get_user_status(request),
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
                    return self._render_sparql_response_rdf(sparql_construct(query, self.mediatype))
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
                    return [{"uri": coll["uri"], "label": coll["prefLabel"]} for coll in collections]
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
                return Response(graph.serialize(format=self.mediatype), media_type=self.mediatype)

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
@router.head("/collection/{collection_id}/current/{acc_dep_or_concept}/", include_in_schema=False)
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
                        "deprecated": True if concept.get("dep") and concept["dep"]["value"] == "true" else False,
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
                            "logged_in_user": get_user_status(request),
                        },
                    )
                elif self.mediatype in RDF_MEDIATYPES:
                    # Get the term for the collection query WHERE clause to filter or accepted or deprecated.
                    # This will be an empty string if neither condition is true.
                    acc_dep_term = acc_dep_map.get(acc_dep_or_concept).replace("?c", "?m")
                    query = get_collection_query(current_profile, self.instance_uri, self.ontologies)
                    return self._render_sparql_response_rdf(sparql_construct(query, self.mediatype))
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
                return JSONResponse([{"uri": x["c"]["value"], "prefLabel": x["pl"]["value"]} for x in r[1]])
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
                return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
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
                return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))
            elif self.profile in alt_profile_tokens:
                # Get the term for the collection query WHERE clause to filter or accepted or deprecated.
                # This will be an empty string if neither condition is true.
                acc_dep_term = acc_dep_map.get(acc_dep_or_concept).replace("?c", "?m")
                query = get_collection_query(current_profile, self.instance_uri, self.ontologies)
                return self._render_sparql_response_rdf(sparql_construct(query, self.mediatype))

            alt = super().render()
            if alt is not None:
                return alt

    return CollectionRenderer().render()


class ConceptRenderer(Renderer):
    def __init__(self, request):
        self.request = request
        if "collection" in str(request.url):
            self.instance_uri = f"{DATA_URI}/collection/" + str(request.url).split("/collection/")[1].split("?")[0]
        elif "standard_name" in str(request.url):
            self.instance_uri = (
                f"{DATA_URI}/standard_name/" + str(request.url).split("/standard_name/")[1].split("?")[0]
            )

        concept_profiles = {
            "nvs": nvs,
            "skos": skos,
            "vocpub": vocpub,
            "sdo": sdo,
        }

        self.alt_profiles = get_alt_profiles()
        self.ontologies = get_ontologies()
        collection_uri = self.instance_uri.split("/current/")[0] + "/current/"
        for collection in cache_return(collections_or_conceptschemes="collections"):
            if collection["uri"]["value"] == collection_uri:
                concept_profiles.update(
                    get_alt_profile_objects(
                        collection,
                        self.alt_profiles,
                        ontologies=self.ontologies,
                        media_types=["text/html"] + RDF_MEDIATYPES,
                        default_mediatype="text/html",
                    )
                )

        super().__init__(request, self.instance_uri, concept_profiles, "nvs")

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

    def _render_nvs_or_profile_html(self):
        exclude_filters = ""
        prefixes = ""
        if self.profile != "nvs":
            exclude_filters += """
                FILTER ( ?p != skos:broader )
                FILTER ( ?p != skos:narrower )
                FILTER ( ?p != skos:related )
                FILTER ( ?p != owl:sameAs )
            """

        for ontology, data in self.ontologies.items():
            if ontology not in self.profiles[self.profile].ontologies:
                exclude_filters += f'FILTER (!STRSTARTS(STR(?p), "{data["url"]}"))\n'
            else:
                prefixes += f'PREFIX {data["prefix"]}: <{data["url"]}>\n'

        q = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            {prefixes}
            SELECT DISTINCT ?p ?o ?o_label ?o_notation ?collection_uri ?collection_systemUri ?collection_label
            WHERE {{
              BIND (<{self.instance_uri}> AS ?concept)
              ?concept ?p ?o .
            
              FILTER ( ?p != skos:broaderTransitive )
              FILTER ( ?p != skos:narrowerTransitive )
              {exclude_filters}
              FILTER(!isLiteral(?o) || lang(?o) = "en" || lang(?o) = "")
            
              OPTIONAL {{
                ?o skos:prefLabel ?o_label ;
                   skos:notation ?o_notation .
                FILTER(!isLiteral(?o_label) || lang(?o_label) = "en" || lang(?o_label) = "")
              }}
            
              BIND(
                IF(
                  CONTAINS(STR(?concept), "standard_name"), 
                    <{DATA_URI}/standard_name/>,
                    IRI(CONCAT(STRBEFORE(STR(?concept), "/current/"), "/current/"))
                )
                AS ?collection_uri
              )
              BIND (REPLACE(STR(?collection_uri), "{DATA_URI}", "") AS ?collection_systemUri)
              OPTIONAL {{?collection_uri skos:prefLabel ?x }}
              BIND (COALESCE(?x, "Climate and Forecast Standard Names") AS ?collection_label)
            }}         
        """

        r = sparql_query(q)
        if not r[0]:
            return PlainTextResponse(
                "There was an error obtaining the Concept RDF from the Triplestore",
                status_code=500,
            )

        PAV = Namespace("http://purl.org/pav/")
        STATUS = Namespace("http://www.opengis.net/def/metamodel/ogc-na/")

        props = {
            str(DCTERMS.contributor): {"label": "Contributor", "group": "agent"},
            str(DCTERMS.creator): {"label": "Creator", "group": "agent"},
            str(DCTERMS.publisher): {"label": "Publisher", "group": "agent"},
            str(SKOS.notation): {"label": "Identifier", "group": "annotation"},
            # str(DCTERMS.identifier): {"label": "Identifier", "group": "annotation"},
            str(STATUS.status): {"label": "Status", "group": "annotation"},
            str(SKOS.altLabel): {"label": "Alternative Label", "group": "annotation"},
            str(SKOS.note): {"label": "Note", "group": "annotation"},
            str(SKOS.scopeNote): {"label": "Scope Note", "group": "annotation"},
            str(SKOS.historyNote): {"label": "History Note", "group": "annotation"},
            str(SKOS.notation): {"label": "Identifier", "group": "annotation"},
            str(OWL.sameAs): {"label": "Same As", "group": "related"},
            str(SKOS.broader): {"label": "Broader", "group": "related"},
            str(SKOS.related): {"label": "Related", "group": "related"},
            str(SKOS.narrower): {"label": "Narrower", "group": "related"},
            str(SKOS.exactMatch): {"label": "Exact Match", "group": "related"},
            str(SKOS.broadMatch): {"label": "Broad Match", "group": "related"},
            str(SKOS.closeMatch): {"label": "Close Match", "group": "related"},
            str(SKOS.narrowMatch): {"label": "Narrow Match", "group": "related"},
            str(PAV.hasCurrentVersion): {
                "label": "Has Current Version",
                "group": "provenance",
            },
            str(PAV.hasVersion): {"label": "Version", "group": "versions"},
            str(OWL.deprecated): {"label": "Deprecated", "group": "provenance"},
            str(PAV.previousVersion): {
                "label": "Previous Version",
                "group": "previous_versions",
            },
            str(DCTERMS.isVersionOf): {"label": "Is Version Of", "group": "provenance"},
            str(PAV.authoredOn): {"label": "Authored On", "group": "provenance"},
            str(DC.identifier): {"group": "ignore"},
            str(DCTERMS.identifier): {"group": "ignore"},
            str(VOID.inDataset): {"group": "ignore"},
            str(RDF.type): {"group": "ignore"},
            str(OWL.versionInfo): {"group": "ignore"},
            str(PAV.authoredOn): {"group": "ignore"},
        }

        context = {
            "request": self.request,
            "deprecated": False,
            "prefLabel": None,
            "uri": self.instance_uri,
            "collection_systemUri": None,
            "collection_label": None,
            "definition": None,
            "date": None,
            "altLabels": [],
            "profile_properties": [],
            "annotation": [],
            "agent": [],
            "related": [],
            "versions": [],
            "previous_versions": [],
            "provenance": [],
            "other": [],
            "profile_token": self.profile,
            "alt_profiles": self.alt_profiles,
            "profile_properties_for_button": [],
        }

        def make_predicate_label_from_uri(uri):
            return uri.split("#")[-1].split("/")[-1]

        alt_profiles = get_alt_profiles()
        profile_url = None

        for ap in alt_profiles.values():
            if ap["token"] == self.profile:
                profile_url = ap["url"]
                context["profile"] = ap

        for x in r[1]:
            p = x["p"]["value"]
            o = x["o"]["value"]
            o_label = x["o_label"]["value"] if x.get("o_label") is not None else None
            o_notation = x["o_notation"]["value"] if x.get("o_notation") is not None else None

            context["collection_systemUri"] = x["collection_systemUri"]["value"]
            context["collection_label"] = x["collection_label"]["value"]
            if p == str(OWL.deprecated):
                if o == "true":
                    context["deprecated"] = True
            elif p == str(SKOS.prefLabel):
                context["prefLabel"] = o
            elif p == str(SKOS.altLabel):
                if o not in context["altLabels"]:
                    context["altLabels"].append(o)

            elif p == str(SKOS.definition):
                context["definition"] = o
            elif p == str(DCTERMS.date):
                context["date"] = o.replace(" ", "T").rstrip(".0")
            elif p in props.keys():
                if props[p]["group"] != "ignore":
                    context[props[p]["group"]].append(DisplayProperty(p, props[p]["label"], o, o_label, o_notation))
            elif profile_url and p.startswith(profile_url):
                p_label = p[len(profile_url) :]
                if p_label[0] == "#":
                    p_label = p_label[1:]

                context["profile_properties"].append(DisplayProperty(p, p_label, o, o_label, o_notation))
            else:
                context["other"].append(DisplayProperty(p, make_predicate_label_from_uri(p), o, o_label))

        def clean_prop_list_labels(prop_list):
            last_pred_html = None
            for x in prop_list:
                this_predicate_html = x.predicate_html
                if this_predicate_html == last_pred_html:
                    x.predicate_html = ""
                last_pred_html = this_predicate_html

        context["altLabels"].sort()
        context["profile_properties"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["profile_properties"])
        context["agent"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["agent"])
        context["annotation"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["annotation"])
        context["related"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["related"])
        context["provenance"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["provenance"])
        context["other"].sort(key=lambda x: x.predicate_html)
        clean_prop_list_labels(context["other"])
        context["versions"].sort(key=lambda x: int(x.object_value))
        context["previous_versions"].sort(key=lambda x: int(x.object_value))

        q1 = f"""
             PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
             PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
             PREFIX dcterms: <http://purl.org/dc/terms/>
             PREFIX owl: <http://www.w3.org/2002/07/owl#>
        
             SELECT ?id ?systemUri
             (GROUP_CONCAT(?conformsto;SEPARATOR=",") AS ?conforms_to)
             WHERE {{
                ?uri a skos:Collection .             
                BIND (STRAFTER(STRBEFORE(STR(?uri), "/current/"), "/collection/") AS ?id)
                BIND (STRAFTER(STR(?uri), ".uk") AS ?systemUri)
                OPTIONAL {{ ?uri dcterms:conformsTo ?conformsto }}
            }}
            group by ?uri ?id ?systemUri
         """
        r1 = sparql_query(q1)

        q2 = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?p ?o ?o_label ?o_notation ?collection_uri ?collection_systemUri ?collection_label
            WHERE {{
              BIND (<{self.instance_uri}> AS ?concept)
              ?concept ?p ?o .

              FILTER ( ?p != skos:broaderTransitive )
              FILTER ( ?p != skos:narrowerTransitive )
              FILTER ( ?p != skos:broader )
              FILTER ( ?p != skos:narrower )
              FILTER ( ?p != skos:related )
              FILTER ( ?p != owl:sameAs )
              FILTER(!isLiteral(?o) || lang(?o) = "en" || lang(?o) = "")

              OPTIONAL {{
                ?o skos:prefLabel ?o_label ;
                   skos:notation ?o_notation .
                FILTER(!isLiteral(?o_label) || lang(?o_label) = "en" || lang(?o_label) = "")
              }}

              BIND(
                IF(
                  CONTAINS(STR(?concept), "standard_name"),
                    <{DATA_URI}/standard_name/>,
                    IRI(CONCAT(STRBEFORE(STR(?concept), "/current/"), "/current/"))
                )
                AS ?collection_uri
              )
              BIND (REPLACE(STR(?collection_uri), "{DATA_URI}", "") AS ?collection_systemUri)
              OPTIONAL {{?collection_uri skos:prefLabel ?x }}
              BIND (COALESCE(?x, "Climate and Forecast Standard Names") AS ?collection_label)
            }}
        """

        r2 = sparql_query(q2)

        p_keys = [x["p"]["value"] for x in r2[1]]

        context["conforms_to"] = []

        for item in r1[1]:
            if "conforms_to" in item and item["systemUri"]["value"] in context["uri"]:
                c = item["conforms_to"]["value"].split(",")
                for c_item in c:
                    match = any(c_item in s for s in p_keys)
                    if match:
                        context["conforms_to"].append(c_item)

        context["logged_in_user"] = get_user_status(self.request)

        def create_frequency_dict(items: list) -> defaultdict:
            """Group related items into their respective concepts.

            Args:
                items(list): A list of pyldapi objects with the raw HTML.

            Returns:
                defaultdict: A dict in the form of {CollectionNo: [List of associated pyldapi objects]}
            """
            def_dict = defaultdict(list)
            for item in items:
                result = re.search(r'(/">)([A-Z]+\d\d)(</a>)', item.object_html)
                if result and len(result.groups()) == 3:
                    def_dict[result.group(2)].append(item)

            return def_dict

        def _sort_by(item: list) -> Tuple[int, str]:
            """Utility function to dictate sorting logic."""
            return len(item[1]), re.search(r"(<td>)(.+?)(</td>)", item[1][0].object_html).group(2).lower()

        context["related"] = {k: v for k, v in sorted(create_frequency_dict(context["related"]).items(), key=_sort_by)}

        alt_label_query = """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT * WHERE {
          ?x a skos:Collection .
          ?x skos:prefLabel ?label .
        } LIMIT 1000"""

        alt_labels = self._render_sparql_response_rdf(
            sparql_construct(alt_label_query, "application/json")
        ).body.decode("utf8")
        alt_labels_json = json.loads(alt_labels)

        def return_alt_label(collection: str) -> str:
            """Pair collections with their screen friendly labels."""
            for entry in alt_labels_json["results"]["bindings"]:
                if collection in entry["x"]["value"]:
                    return entry["label"]["value"]
            return ""

        context["alt_labels"] = {k: return_alt_label(k) for k in context["related"]}

        return templates.TemplateResponse("concept.html", context=context)

    def _render_nvs_rdf(self):
        exclude_filters = ""
        for ontology in self.ontologies.values():
            exclude_filters += f'FILTER (!STRSTARTS(STR(?p), "{ontology["url"]}"))\n'

        q = f"""
            PREFIX dc: <http://purl.org/dc/terms/>
            PREFIX dce: <http://purl.org/dc/elements/1.1/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX pav: <http://purl.org/pav/>
            PREFIX prov: <https://www.w3.org/ns/prov#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX void: <http://rdfs.org/ns/void#>

            CONSTRUCT {{
              <{self.instance_uri}> ?p ?o .

              # remove provenance, for now
              # ?s ?p2 ?o2 .              
              # ?s rdf:subject <{self.instance_uri}> ;
              #   prov:has_provenance ?m .              
            }}
            WHERE {{
                <{self.instance_uri}> ?p ?o .

                # remove provenance, for now
                # OPTIONAL {{
                #     ?s rdf:subject <{self.instance_uri}> ;
                #        prov:has_provenance ?m .
                #         
                #     # {{ ?s ?p2 ?o2 }}
                # }}

                # exclude altprof properties from NVS view
                {exclude_filters}
            }}
        """
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_skos_rdf(self):
        q = """
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            CONSTRUCT {
              <xxx> ?p ?o .   
              ?s ?p2 <xxx> .  
            }
            WHERE {
              <xxx> ?p ?o .
              ?s ?p2 <xxx> .

              # include only SKOS properties
              FILTER (STRSTARTS(STR(?p), "http://www.w3.org/2004/02/skos/core#"))
              FILTER (STRSTARTS(STR(?p2), "http://www.w3.org/2004/02/skos/core#"))
            }
            """.replace(
            "xxx", self.instance_uri
        )
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_vocpub_rdf(self):
        q = """
            PREFIX dce: <http://purl.org/dc/elements/1.1/>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX pav: <http://purl.org/pav/>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX void: <http://rdfs.org/ns/void#>
            CONSTRUCT {
              <xxx> ?p ?o .   
              ?s ?p2 <xxx> .  
            }
            WHERE {
              <xxx> ?p ?o .
              ?s ?p2 <xxx> .

              FILTER (!STRSTARTS(STR(?p2), "http://www.w3.org/1999/02/22-rdf-syntax-ns#"))
            }
            """.replace(
            "xxx", self.instance_uri
        )
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_sdo_rdf(self):
        q = """
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX sdo: <https://schema.org/>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            CONSTRUCT {
              <DATA_URI/collection/P01/current/SAGEMSFM/>
                a sdo:DefinedTerm ;
                sdo:name ?pl ;
                sdo:alternateName ?al ;
                sdo:description ?def ;
                sdo:identifier ?id ;
                sdo:dateModified ?modified ;
                sdo:version ?versionInfo ;
                sdo:inDefinedTermSet ?collection ;
                sdo:isPartOf ?scheme ;
                sdo:sameAs ?sameAs ;
              .
            }
            WHERE {
              <DATA_URI/collection/P01/current/SAGEMSFM/> 
                skos:prefLabel ?pl ;
                skos:definition ?def ;
                dcterms:identifier ?id ;
                dcterms:date ?date ;
                owl:versionInfo ?versionInfo ;
              .

              BIND (STRDT(REPLACE(STRBEFORE(?date, "."), " ", "T"), xsd:dateTime) AS ?modified)

              ?collection skos:member <DATA_URI/collection/P01/current/SAGEMSFM/>  .

              OPTIONAL {
                <DATA_URI/collection/P01/current/SAGEMSFM/>
                  skos:altLabel ?al ;
                  skos:inScheme ?scheme ;
                  owl:sameAs ?sameAs ;
                .
              }
            }            
            """.replace(
            "DATA_URI", DATA_URI
        )
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def _render_profile_rdf(self):
        exclude_filters = ""
        prefixes = ""

        for ontology, data in self.ontologies.items():
            if ontology not in self.profiles[self.profile].ontologies:
                exclude_filters += f'FILTER (!STRSTARTS(STR(?p), "{data["url"]}"))\n'
            else:
                prefixes += f'PREFIX {data["prefix"]}: <{data["url"]}>\n'

        q = f"""
            PREFIX dc: <http://purl.org/dc/terms/>
            PREFIX dce: <http://purl.org/dc/elements/1.1/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX pav: <http://purl.org/pav/>
            PREFIX prov: <https://www.w3.org/ns/prov#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX void: <http://rdfs.org/ns/void#>
            {prefixes}

            CONSTRUCT {{
              <{self.instance_uri}> ?p ?o .
            }}
            WHERE {{
              <{self.instance_uri}> ?p ?o .
              FILTER ( ?p != skos:broaderTransitive )
              FILTER ( ?p != skos:narrowerTransitive )
              FILTER ( ?p != skos:broader )
              FILTER ( ?p != skos:narrower )
              FILTER ( ?p != skos:related )
              FILTER ( ?p != owl:sameAs )
              # exclude other properties from altprof
              {exclude_filters}
            }}
        """
        return self._render_sparql_response_rdf(sparql_construct(q, self.mediatype))

    def render(self):
        alt_profile_tokens = [alt["token"] for alt in self.alt_profiles.values()]
        if self.profile == "nvs":
            if self.mediatype in RDF_MEDIATYPES or self.mediatype in Renderer.RDF_SERIALIZER_TYPES_MAP:
                return self._render_nvs_rdf()
            else:
                return self._render_nvs_or_profile_html()
        elif self.profile == "skos":
            return self._render_skos_rdf()
        elif self.profile == "vocpub":
            return self._render_vocpub_rdf()
        elif self.profile == "sdo":
            return self._render_sdo_rdf()
        elif self.profile in alt_profile_tokens:
            if self.mediatype in RDF_MEDIATYPES or self.mediatype in Renderer.RDF_SERIALIZER_TYPES_MAP:
                return self._render_profile_rdf()
            else:
                return self._render_nvs_or_profile_html()

        alt = super().render()
        if alt is not None:
            return alt


def concept(request: Request):
    return ConceptRenderer(request).render()


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
