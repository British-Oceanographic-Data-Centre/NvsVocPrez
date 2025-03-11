"""FAIR-IMPACT artefacts endpoint."""

from datetime import date
import os
from pathlib import Path
import re
import json
from datetime import datetime
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse

import httpx

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
}

distributions_config = [
    {"distributionId": "1", "hasSyntax": "http://www.w3.org/ns/formats/RDF_XML", "mediaType": "application/rdf+xml"},
    {"distributionId": "2", "hasSyntax": "http://www.w3.org/ns/formats/Turtle", "mediaType": "text/turtle"},
    {"distributionId": "3", "hasSyntax": "http://www.w3.org/ns/formats/JSON-LD", "mediaType": "application/ld+json"},
]


@router.get("/artefacts", **paths["/artefacts"]["get"])
@router.head("/artefacts", include_in_schema=False)
def artefacts(request: Request):
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

    return JSONResponse(content=json_ld, status_code=response.status_code)


@router.get("/artefacts/{artefactID}", **paths["/artefacts/{artefactID}"]["get"])
@router.head("/artefacts/{artefactID}", include_in_schema=False)
def artefactId(request: Request, artefactID: str):

    response = artefacts(request)

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
def distributions(request: Request, artefactID: str):

    response = artefactId(request, artefactID)

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
        item["downloadURL"] = (
            f"{host}/collection/{artefactID.upper()}/current/?_profile=nvs&_mediatype={item['mediaType']}"
        )
        item["@id"] = f"{host}/artefacts/{artefactID.upper()}/distributions/{item['distributionId']}"
        del item["mediaType"]

    graph_items = {"@graph": distributions_json_ld}

    json_ld = {"@context": distributions_context}
    json_ld.update(graph_items)

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
                "identifier": [uri],
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
            }
        )

    return graph_items
