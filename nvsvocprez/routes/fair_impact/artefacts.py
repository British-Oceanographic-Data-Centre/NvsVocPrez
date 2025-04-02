"""FAIR-IMPACT endpoints."""

from datetime import date
import math
import os
from pathlib import Path
import re
import json
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse

import httpx

from ..utils import sparql_query

router = APIRouter()

config_file_location = Path(__file__).parent.parent.parent / "api_doc_config.json"
with open(config_file_location, "r") as config_file:
    paths = json.load(config_file)["paths"]

timeout = 60

host = os.getenv("SYSTEM_URI", "https://vocab.nerc.ac.uk")

artefacts_context = {
    "@vocab": "http://purl.org/dc/terms/",
    "acronym": "https://w3id.org/mod#acronym",
    "accessRights": "http://purl.org/dc/terms/accessRights",
    "URI": "https://w3id.org/mod#URI",
    "identifier": "http://purl.org/dc/terms/identifier",
    "creator": "http://purl.org/dc/terms/creator",
    "status": "https://w3id.org/mod#status",
    "license": "http://purl.org/dc/terms/license",
    "rightsHolder": "http://purl.org/dc/terms/rightsHolder",
    "title": "http://purl.org/dc/terms/title",
    "description": "http://purl.org/dc/terms/description",
    "modified": "http://purl.org/dc/terms/modified",
    "landingPage": "http://www.w3.org/ns/dcat#landingPage",
    "bibliographicCitation": "http://purl.org/dc/terms/bibliographicCitation",
    "contactPoint": "http://www.w3.org/ns/dcat#contactPoint",
    "contributor": "http://purl.org/dc/terms/contributor",
    "publisher": "http://purl.org/dc/terms/publisher",
    "createdWith": "http://purl.org/pav/createdWith",
    "includedInDataCatalog": "http://schema.org/includedInDataCatalog",
    "language": "http://purl.org/dc/terms/language",
    "@language": "en",
}

distributions_context = {
    "@vocab": "http://purl.org/dc/terms/",
    "distributionId": "http://data.bioontology.org/metadata/distributionId",
    "title": "http://purl.org/dc/terms/title",
    "hasRepresentationLanguage": "https://w3id.org/mod#hasRepresentationLanguage",
    "hasSyntax": "https://w3id.org/mod#hasSyntax",
    "description": "http://purl.org/dc/terms/description",
    "modified": "http://purl.org/dc/terms/modified",
    "conformsToKnowledgeRepresentationParadigm": "https://w3id.org/mod#conformsToKnowledgeRepresentationParadigm",
    "usedEngineeringMethodology": "https://w3id.org/mod#usedEngineeringMethodology",
    "prefLabelProperty": "https://w3id.org/mod#prefLabelProperty",
    "synonymProperty": "https://w3id.org/mod#synonymProperty",
    "definitionProperty": "https://w3id.org/mod#definitionProperty",
    "accessURL": "http://www.w3.org/ns/dcat#accessURL",
    "downloadURL": "http://www.w3.org/ns/dcat#downloadURL",
    "language": "http://purl.org/dc/terms/language",
    "@language": "en",
}

distributions_meta = {
    "@type": "https://w3id.org/mod#SemanticArtefactDistribution",
    "language": ["http://lexvo.org/id/iso639-1/en"],
    "prefLabelProperty": "http://www.w3.org/2004/02/skos/core#prefLabel",
    "definitionProperty": "http://purl.org/dc/terms/description",
    "hasRepresentationLanguage": "https://www.w3.org/2004/02/skos/",
    "conformsToKnowledgeRepresentationParadigm": "",
    "usedEngineeringMethodology": "",
    "accessURL": f"{host}/sparql/",
    "created": None,
    "synonymProperty": "http://www.w3.org/2004/02/skos/core#altLabel",
    "byteSize": None,
}

distributions_config = [
    {"distributionId": "1", "hasSyntax": "http://www.w3.org/ns/formats/RDF_XML", "mediaType": "application/rdf+xml"},
    {"distributionId": "2", "hasSyntax": "http://www.w3.org/ns/formats/Turtle", "mediaType": "text/turtle"},
    {"distributionId": "3", "hasSyntax": "http://www.w3.org/ns/formats/JSON-LD", "mediaType": "application/ld+json"},
]


@router.get("/artefacts", **paths["/artefacts"]["get"])
@router.head("/artefacts", include_in_schema=False)
def artefacts(request: Request, do_filter="yes", do_pagination="yes"):
    # Collections
    with httpx.Client(follow_redirects=True) as client:
        response = client.get(f"{host}/collection?_mediatype=application/ld+json&_profile=nvs", timeout=timeout)

    data = response.json()
    graph_collection_items = get_collection_graph_items(data)

    # Schemes
    with httpx.Client(follow_redirects=True) as client:
        response = client.get(f"{host}/scheme?_mediatype=application/ld+json&_profile=nvs", timeout=timeout)

    data = response.json()
    graph_scheme_items = get_scheme_graph_items(data)

    json_ld = {"@context": artefacts_context, "@graph": graph_collection_items + graph_scheme_items}

    if do_filter is not None:
        display_param = request.query_params.get("display", "all")
        protected_fields = {"acronym", "@id", "links"}
        filter_fields_in_graph_artefacts(json_ld, display_param, protected_fields)

    if do_pagination is not None:        
        page_size = get_positive_int(request.query_params.get("pagesize"), 5)
        page = get_positive_int(request.query_params.get("page"), 1)

        graph_count = len(json_ld.get("@graph", []))
        page_size = min(page_size, graph_count)
        page_count = math.ceil(graph_count / page_size)

        page = min(page, page_count)
        prev_page = None if page == 1 else max(1, page - 1)
        next_page = None if page == page_count else page + 1

        start_index = (page - 1) * page_size
        end_index = min(page * page_size - 1, graph_count - 1)

        subset_graph = json_ld["@graph"][start_index : end_index + 1]
        paged_json_ld = {"@context": json_ld["@context"], "@graph": subset_graph}

        paged_json_ld = {
            **pagination(page, page_count, page_size, graph_count, prev_page, next_page, str(request.url)),
            **paged_json_ld,
        }

        json_ld = paged_json_ld

    return JSONResponse(content=json_ld, status_code=response.status_code)


@router.get("/artefacts/{artefactID}", **paths["/artefacts/{artefactID}"]["get"])
@router.head("/artefacts/{artefactID}", include_in_schema=False)
def artefactId(request: Request, artefactID: str, do_filter="yes"):

    response = artefacts(request, do_filter, do_pagination=None)

    body = response.body
    data = json.loads(body.decode("utf-8"))

    graph_item = [item for item in data["@graph"] if item.get("acronym") == artefactID]

    if not graph_item:
        return JSONResponse(content={"error": "artefactID not found"}, status_code=404)

    json_ld = {}
    json_ld = {"@context": artefacts_context}
    json_ld.update(graph_item[0])

    return JSONResponse(content=json_ld, status_code=200)


@router.get("/artefacts/{artefactID}/distributions", **paths["/artefacts/{artefactID}/distributions"]["get"])
@router.head("/artefacts/{artefactID}/distributions", include_in_schema=False)
def distributions(request: Request, artefactID: str, do_filter=None):

    response = artefactId(request, artefactID, do_filter)

    if response.status_code != 200:
        return JSONResponse(content={"error": "artefactID not found"}, status_code=404)

    body = response.body
    data = json.loads(body.decode("utf-8"))

    distributions_json_ld = [
        {
            **{"title": data["title"], "description": data["description"], "modified": data["modified"]},
            **item,
            **distributions_meta,
        }
        for item in distributions_config
    ]

    for item in distributions_json_ld:
        item["downloadURL"] = f"{data['identifier']}?_profile=nvs&_mediatype={item['mediaType']}"
        item["@id"] = f"{host}/artefacts/{artefactID.upper()}/distributions/{item['distributionId']}"
        item["byteSize"] = get_response_bytesize(item["downloadURL"])
        del item["mediaType"]

    graph_items = {"@graph": distributions_json_ld}

    json_ld = {"@context": distributions_context}
    json_ld.update(graph_items)

    display_param = request.query_params.get("display", "all")
    protected_fields = {"distributionId", "downloadURL", "@id"}

    filter_fields_in_graph_artefacts(json_ld, display_param, protected_fields)

    return JSONResponse(content=json_ld, status_code=200)


@router.get(
    "/artefacts/{artefactID}/distributions/{distributionID}",
    **paths["/artefacts/{artefactID}/distributions/{distributionID}"]["get"],
)
@router.head("/artefacts/{artefactID}/distributions/{distributionID}", include_in_schema=False)
def distributionsId(request: Request, artefactID: str, distributionID: str):

    response = distributions(request, artefactID)

    if response.status_code != 200:
        return JSONResponse(content={"error": "artefactID not found"}, status_code=404)

    valid_ids = [str(i) for i in range(1, len(distributions_config) + 1)]

    if distributionID not in valid_ids:
        return JSONResponse(content={"error": "distributionID not found"}, status_code=404)

    body = response.body
    data = json.loads(body.decode("utf-8"))

    distribution_item = next(item for item in data["@graph"] if item["distributionId"] == distributionID)

    json_ld = {"@context": distributions_context}
    json_ld.update(distribution_item)

    return JSONResponse(content=json_ld, status_code=200)


@router.get(
    "/search/metadata",
    **paths["/search/metadata"]["get"],
)
@router.head("/search/metadata", include_in_schema=False)
def metadata(request: Request):

    query_param = request.query_params.get("q")

    if query_param is None:
        return JSONResponse(content={"error": "query parameter 'q' not found"}, status_code=404)

    q_count = """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX dc: <http://purl.org/dc/terms/>

        SELECT COUNT(DISTINCT ?x) 
        WHERE { 
            ?x a skos:Collection .
            OPTIONAL { ?x dc:creator ?cre } .
            ?x dc:title ?dt ;
            dc:description ?desc ;
            skos:altLabel ?alt .
            
            FILTER (
                regex(str(?x), "<Q>", "i") || 
                regex(str(?dt), "<Q>", "i") || 
                regex(str(?alt), "<Q>", "i") || 
                regex(str(?desc), "<Q>", "i") || 
                regex(str(?cre), "<Q>", "i")
            )
        }
    """.replace(
        "<Q>", query_param
    )

    sparql_count_result = sparql_query(q_count)
    count = sparql_count_result[1][0][".1"]["value"]

    results_count = int(count)
    sparql_result = []
    if results_count > 0:

        page_size = get_positive_int(request.query_params.get("pagesize"), 5)
        page = get_positive_int(request.query_params.get("page"), 1)

        page_size = min(page_size, results_count)
        page_count = math.ceil(results_count / page_size)

        page = min(page, page_count)
        prev_page = None if page == 1 else max(1, page - 1)
        next_page = None if page == page_count else page + 1

        start_index = (page - 1) * page_size
        pgn = pagination(page, page_count, page_size, results_count, prev_page, next_page, str(request.url))

        q_result = (
            """
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX dc: <http://purl.org/dc/terms/>

            SELECT DISTINCT 
                (?localnam AS ?Collection) 
                (?dt AS ?Title) 
                (?alt AS ?AlternativeLabel) 
                (?desc AS ?Description) 
                (?crex AS ?Governance) 
                (?x AS ?URL) 
            WHERE { 
                ?x a skos:Collection .
                OPTIONAL { ?x dc:creator ?cre } .
                ?x dc:title ?dt ;
                dc:description ?desc ;
                skos:altLabel ?alt .
                
                FILTER (
                    regex(str(?x), "<Q>", "i") || 
                    regex(str(?dt), "<Q>", "i") || 
                    regex(str(?alt), "<Q>", "i") || 
                    regex(str(?desc), "<Q>", "i") || 
                    regex(str(?cre), "<Q>", "i")
                ) .
                
                BIND(REPLACE(str(?x), "<HOST>/collection/", "") AS ?localname)
                BIND(REPLACE(str(?localname), "/current/", "") AS ?localnam)
                BIND(IF(EXISTS { ?x dc:creator ?cre }, ?cre, "") AS ?crex)
            } 
            ORDER BY DESC(?Rank) 
            OFFSET <OFFSET>
            LIMIT <LIMIT>
            """.replace(
                "<Q>", query_param
            )
            .replace("<HOST>", host)
            .replace("<OFFSET>", str(start_index))
            .replace("<LIMIT>", str(page_size))
        )

        sparql_result = sparql_query(q_result)
        sparql_result = {**pgn, "results": sparql_result[1]}

    return sparql_result


@router.get(
    "/search/content",
    **paths["/search/content"]["get"],
)
@router.head("/search/content", include_in_schema=False)
def content(request: Request):

    query_param = request.query_params.get("q")

    if query_param is None:
        return JSONResponse(content={"error": "query parameter 'q' not found"}, status_code=404)

    q_count = """
        PREFIX lang: <http://ontologi.es/lang/core#> 
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#> 
        PREFIX text: <http://jena.apache.org/text#> 
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> 
        PREFIX owl: <http://www.w3.org/2002/07/owl#> 
        PREFIX dc: <http://purl.org/dc/terms/> 

        SELECT COUNT(DISTINCT ?dci) 
        WHERE { 
            ?x text:query ('*<Q>*' 500000) . 
            ?z skos:member ?x . 
            ?x dc:identifier ?dci . 

            OPTIONAL { 
                ?x skos:altLabel ?alt 
                FILTER(langMatches(lang(?alt), "")) 
            } 
            
            OPTIONAL { 
                ?x skos:definition ?def . 
                FILTER(
                    langMatches(lang(?def), "en") || 
                    langMatches(lang(?def), "")
                ) 
            } 
            
            ?x skos:prefLabel ?pl . 
            FILTER(langMatches(lang(?pl), "en")) . 

            ?x owl:deprecated ?depr . 
            FILTER(str(?depr) = "false") 
        }
    """.replace(
        "<Q>", query_param
    )

    sparql_count_result = sparql_query(q_count)
    count = sparql_count_result[1][0][".1"]["value"]

    results_count = int(count)
    sparql_result = []
    if results_count > 0:

        page_size = get_positive_int(request.query_params.get("pagesize"), 5)
        page = get_positive_int(request.query_params.get("page"), 1)

        page_size = min(page_size, results_count)
        page_count = math.ceil(results_count / page_size)

        page = min(page, page_count)
        prev_page = None if page == 1 else max(1, page - 1)
        next_page = None if page == page_count else page + 1

        start_index = (page - 1) * page_size
        pgn = pagination(page, page_count, page_size, results_count, prev_page, next_page, str(request.url))

        q_result = (
            """
            PREFIX lang: <http://ontologi.es/lang/core#> 
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#> 
            PREFIX text: <http://jena.apache.org/text#> 
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> 
            PREFIX owl: <http://www.w3.org/2002/07/owl#> 
            PREFIX dc: <http://purl.org/dc/terms/> 

            SELECT DISTINCT 
                (?dci AS ?Identifier) 
                (?pl AS ?PrefLabel) 
                (?alt AS ?AlternativeLabel) 
                (?def AS ?Definition) 
                (?z AS ?Collection) 
                (?dt AS ?Title) 
            WHERE { 
                ?x text:query ('*<Q>*' 500000) . 
                ?z skos:member ?x . 
                ?x dc:identifier ?dci . 
                
                OPTIONAL { 
                    ?x skos:altLabel ?alt 
                    FILTER(langMatches(lang(?alt), "")) 
                } 
                
                OPTIONAL { 
                    ?x skos:definition ?def . 
                    FILTER(
                        langMatches(lang(?def), "en") || 
                        langMatches(lang(?def), "")
                    ) 
                } 
                
                ?x skos:prefLabel ?pl . 
                FILTER(langMatches(lang(?pl), "en")) . 
                
                ?x owl:deprecated ?depr . 
                FILTER(str(?depr) = "false") 
            }
            ORDER BY DESC(?z) 
            OFFSET <OFFSET>
            LIMIT <LIMIT>
            """.replace(
                "<Q>", query_param
            )
            .replace("<HOST>", host)
            .replace("<OFFSET>", str(start_index))
            .replace("<LIMIT>", str(page_size))
        )

        sparql_result = sparql_query(q_result)
        sparql_result = {**pgn, "results": sparql_result[1]}

    return sparql_result


@router.get("/artefacts/{artefactID}/resources/concepts", **paths["/artefacts/{artefactID}/resources/concepts"]["get"])
@router.head("/artefacts/{artefactID}/resources/concepts", include_in_schema=False)
def concepts_in_collection(request: Request, artefactID: str):

    response = artefactId(request, artefactID)

    if response.status_code != 200:
        return JSONResponse(content={"error": "artefactID not found"}, status_code=404)

    q_count = """
        PREFIX dcterms: <http://purl.org/dc/terms/> 
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#> 
        
        SELECT (COUNT(DISTINCT ?c) AS ?count)
        WHERE { 
            <<HOST>/collection/<artefactID>/current/> skos:member ?c .
            ?c skos:prefLabel ?pl .
            FILTER(LANG(?pl) = "en")

        }  
    """.replace(
        "<artefactID>", artefactID
    ).replace(
        "<HOST>", host
    )

    sparql_count_result = sparql_query(q_count)
    count = sparql_count_result[1][0]["count"]["value"]

    results_count = int(count)
    sparql_result = []
    if results_count > 0:

        page_size = get_positive_int(request.query_params.get("pagesize"), 5)
        page = get_positive_int(request.query_params.get("page"), 1)

        page_size = min(page_size, results_count)
        page_count = math.ceil(results_count / page_size)

        page = min(page, page_count)
        prev_page = None if page == 1 else max(1, page - 1)
        next_page = None if page == page_count else page + 1
        start_index = (page - 1) * page_size
        pgn = pagination(page, page_count, page_size, results_count, prev_page, next_page, str(request.url))

        q_result = (
            """
        PREFIX dcterms: <http://purl.org/dc/terms/>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?c ?pl
        WHERE {
                <<HOST>/collection/<artefactID>/current/> skos:member ?c .
                ?c skos:prefLabel ?pl .
                FILTER(LANG(?pl) = "en")
        }
        OFFSET <OFFSET>
        LIMIT <LIMIT>
        """.replace(
                "<artefactID>", artefactID
            )
            .replace("<HOST>", host)
            .replace("<OFFSET>", str(start_index))
            .replace("<LIMIT>", str(page_size))
        )

        sparql_result = sparql_query(q_result)
        sparql_result = [{"uri": x["c"]["value"], "prefLabel": x["pl"]["value"]} for x in sparql_result[1]]
        sparql_result = {**pgn, "results": sparql_result}

    return sparql_result


def extract_collection_acronym(uri):
    match = re.search(r"/collection/(.*?)/current/", uri)
    return match.group(1)


def extract_scheme_acronym(uri):
    match = re.search(r"/scheme/(.*?)/current/", uri)
    return match.group(1)


def parse_date(date_str):
    try:
        return datetime.strptime(date_str["@value"], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError, KeyError):
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")


def get_collection_graph_items(data: dict):
    graph_items = []

    for item in data.get("@graph", []):
        uri = item.get("@id")

        status = "production"
        if "DEPRECATED" in item.get("skos:prefLabel", "") or "DEPRECATED" in item.get("dc:title", ""):
            status = "deprecated"

        date_str = item.get("dc:date")
        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")

        bibliographic_citation = (
            f"[British Oceanographic Data Centre, year {date_obj.year}, "
            f"{item.get('dc:title')}, version {item.get('owl:versionInfo')}, "
            f"{item.get('dc:publisher')}, "
            f"{uri} accessed on {date.today()}"
            f"]"
        )

        graph_items.append(
            {
                "acronym": extract_collection_acronym(uri),
                "accessRights": "public",
                "URI": uri,
                "creator": [item.get("dc:creator")],
                "identifier": uri,
                "status": status,
                "language": ["http://lexvo.org/id/iso639-1/en"],
                "rightsHolder": item.get("dc:creator"),
                "license": "https://creativecommons.org/licenses/by/4.0/",
                "title": item.get("skos:prefLabel"),
                "description": item.get("dc:description"),
                "modified": date_str,
                "landingPage": uri,
                "bibliographicCitation": bibliographic_citation,
                "contactPoint": ["vocab.services@bodc.ac.uk"],
                "publisher": [item.get("dc:publisher")],
                "createdWith": ["https://github.com/RDFLib/VocPrez"],
                "includedInDataCatalog": [host],
                "@id": uri.replace("collection", "artefacts").replace("/current/", ""),
                "@type": ["https://w3id.org/mod#SemanticArtefact", "http://www.w3.org/2004/02/skos/core#Collection"],
                "links": {
                    "distributions": uri.replace("collection", "artefacts").replace("/current/", "/distributions"),
                },
                "subject": [],
                "versionIRI": None,
                "keyword": [],
                "contributor": [],
                "coverage": [],
                "accrualMethod": [],
                "accrualPeriodicity": None,
                "competencyQuestion": [],
                "wasGeneratedBy": [],
                "hasFormat": [],
                "includedInDataCatalog": [],
                "semanticArtefactRelation": [],
            }
        )

    return graph_items


def get_scheme_graph_items(data: dict):
    graph_items = []

    for item in data.get("@graph", []):
        uri = item.get("@id")
        date_obj = parse_date(item.get("dc:date"))

        bibliographic_citation = (
            f"[British Oceanographic Data Centre, year {date_obj.year}, "
            f"{item.get('dc:title')}, version {item.get('owl:versionInfo')}, "
            f"{item.get('dc:publisher')}, "
            f"{uri} accessed on {date.today()}"
            f"]"
        )

        graph_items.append(
            {
                "acronym": extract_scheme_acronym(uri),
                "accessRights": "public",
                "URI": uri,
                "creator": [item.get("dc:creator")],
                "identifier": uri,
                "status": "production",
                "language": ["http://lexvo.org/id/iso639-1/en"],
                "rightsHolder": item.get("dc:creator"),
                "title": item.get("skos:prefLabel"),
                "description": item.get("dc:description"),
                "modified": item.get("dc:date"),
                "landingPage": uri,
                "bibliographicCitation": bibliographic_citation,
                "contactPoint": ["vocab.services@bodc.ac.uk"],
                "publisher": [item.get("dc:publisher")],
                "createdWith": ["https://github.com/RDFLib/VocPrez"],
                "includedInDataCatalog": [host],
                "@id": uri.replace("scheme", "artefacts").replace("/current/", ""),
                "@type": ["https://w3id.org/mod#SemanticArtefact", "http://www.w3.org/2004/02/skos/core#ConceptScheme"],
                "links": {
                    "distributions": uri.replace("scheme", "artefacts").replace("/current/", "/distributions"),
                },
                "subject": [],
                "versionIRI": None,
                "keyword": [],
                "contributor": [],
                "coverage": [],
                "accrualMethod": [],
                "accrualPeriodicity": None,
                "competencyQuestion": [],
                "wasGeneratedBy": [],
                "hasFormat": [],
                "includedInDataCatalog": [],
                "semanticArtefactRelation": [],
            }
        )

    return graph_items


def get_response_bytesize(url):
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()
        return len(response.content)


def filter_fields_in_graph_artefacts(json_data: dict, fields_to_display: str, protected_fields: str) -> str:

    fields_to_display = [field.strip() for field in fields_to_display.split(",")]

    if "all" in fields_to_display:
        return

    for item in json_data.get("@graph", []):
        keys_to_remove = [key for key in item if key not in fields_to_display and key not in protected_fields]
        for key in keys_to_remove:
            item.pop(key, None)


def get_positive_int(value, default):
    try:
        return max(int(value), default)
    except (ValueError, TypeError):
        return default


def pagination(page: int, page_count: int, page_size: int, total_count: int, prev_page: int, next_page: int, url: str):
    next_page_link = None if not next_page else update_url_pagination(url, next_page, page_size)
    prev_page_link = None if not prev_page else update_url_pagination(url, prev_page, page_size)

    page_links = {
        "page": page,
        "pageCount": page_count,
        "pageSize": page_size,
        "totalCount": total_count,
        "prevPage": prev_page,
        "nextPage": next_page,
        "links": {"nextPage": next_page_link, "prevPage": prev_page_link},
    }
    return page_links


def update_url_pagination(url: str, page: int, page_size: int) -> str:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    if "pagesize" in query_params and "page" in query_params:
        query_params["page"] = [str(page)]
    else:
        query_params["pagesize"] = [str(page_size)]
        query_params["page"] = [str(page)]

    new_query = urlencode(query_params, doseq=True)
    modified_url = urlunparse(parsed_url._replace(query=new_query))

    return modified_url
