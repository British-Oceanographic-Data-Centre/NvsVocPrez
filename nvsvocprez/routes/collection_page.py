"""Handle calls to the /collection/ endpoint."""
import json
from pathlib import Path

from fastapi import APIRouter
from pyldapi import ContainerRenderer
from pyldapi.renderer import RDF_MEDIATYPES
from rdflib import Graph
from rdflib import Literal as RdfLiteral
from rdflib import URIRef
from rdflib.namespace import RDF, RDFS
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.templating import Jinja2Templates

from .page_configs import SYSTEM_URI
from .profiles import nvs
from .utils import cache_return, sparql_construct, get_user_status

router = APIRouter()

api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))

config_file_location = Path(__file__).parent.parent / "api_doc_config.json"
with open(config_file_location, "r") as config_file:
    paths = json.load(config_file)["paths"]



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
                            "logged_in_user" : get_user_status(request)
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
                            "logged_in_user" : get_user_status(request)
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
                        graph.add((URIRef(coll["uri"]), RDFS.label, RdfLiteral(collection["label"])))
                    return Response(graph.serialize(format=self.mediatype), media_type=self.mediatype)
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
                            "logged_in_user" : get_user_status(request)
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
