"""Classes to renderer either a single collection or all collections."""
from pyldapi.renderer import RDF_MEDIATYPES
from rdflib import Graph
from rdflib import Literal as RdfLiteral
from rdflib import URIRef
from pyldapi import ContainerRenderer, DisplayProperty, Renderer
from rdflib.namespace import DC, DCTERMS, ORG, OWL, RDF, RDFS, SKOS, VOID
from starlette.responses import PlainTextResponse, Response

from utilities.system_configs import DATA_URI, PORT, SYSTEM_URI, acc_dep_map
from utilities.profiles import nvs, skos, vocpub, dd
from utilities.utility_functions import cache_return, get_user_status, get_alt_profiles, sparql_construct, sparql_query
from .templates import html_templates


class CollectionsRenderer(ContainerRenderer):
    def __init__(self, request):
        self.request = request
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

                if self.request.query_params.get("filter"):

                    def concat_vocab_fields(vocab):
                        return (
                            f"{vocab['id']['value']}"
                            f"{vocab['prefLabel']['value']}"
                            f"{vocab['description']['value']}"
                        )

                    collections = [
                        coll
                        for coll in collections
                        if self.request.query_params.get("filter") in concat_vocab_fields(coll)
                    ]

                return html_templates.TemplateResponse(
                    "collections.html",
                    {
                        "request": self.request,
                        "uri": self.instance_uri,
                        "label": self.label,
                        "comment": self.comment,
                        "collections": collections,
                        "profile_token": self.profile,
                        "logged_in_user": get_user_status(self.request),
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
                return html_templates.TemplateResponse(
                    "container_mem.html",
                    {
                        "request": self.request,
                        "uri": self.instance_uri,
                        "label": self.label,
                        "collections": collections,
                        "profile_token": "nvs",
                        "logged_in_user": get_user_status(self.request),
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
                return html_templates.TemplateResponse(
                    "container_contanno.html",
                    {
                        "request": self.request,
                        "uri": self.instance_uri,
                        "label": self.label,
                        "comment": self.comment,
                        "profile_token": "nvs",
                        "logged_in_user": get_user_status(self.request),
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


class CollectionRenderer(Renderer):
    def __init__(self, request, acc_dep_or_concept):
        self.request = request
        self.acc_dep_or_concept = acc_dep_or_concept
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
            "acc_dep", acc_dep_map.get(self.acc_dep_or_concept).replace("?c", "?x")
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
                    return html_templates.TemplateResponse(
                        "error.html",
                        {
                            "request": self.request,
                            "title": "DB Error",
                            "status": "500",
                            "message": "There was an error with accessing the Triplestore",
                        },
                    )

                self.instance_uri = f"{DATA_URI}/standard_name/"

                return html_templates.TemplateResponse(
                    "collection.html",
                    {
                        "request": self.request,
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
