"""FAIR-IMPACT artefacts endpoint."""

from datetime import date
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

artefacts_context = {
    "@vocab": ["http://vocab.nerc.ac.uk/collection/", "http://vocab.nerc.ac.uk/scheme/"],
    "acronym": "https://w3id.org/mod#acronym",
    "accessRights": "http://purl.org/dc/terms/accessRights",
    "subject": "http://purl.org/dc/terms/subject",
    "URI": "https://w3id.org/mod#URI",
    "identifier": "http://purl.org/dc/terms/identifier",
    "creator": "http://purl.org/dc/terms/creator",
    "status": "https://w3id.org/mod#status",
    "language": "http://purl.org/dc/terms/language",
    "license": "http://purl.org/dc/terms/license",
    "rightsHolder": "http://purl.org/dc/terms/rightsHolder",
    "description": "http://purl.org/dc/terms/description",
    "landingPage": "http://www.w3.org/ns/dcat#landingPage",
    "keyword": "http://www.w3.org/ns/dcat#keyword",
    "bibliographicCitation": "http://purl.org/dc/terms/bibliographicCitation",
    "contactPoint": "http://www.w3.org/ns/dcat#contactPoint",
    "contributor": "http://purl.org/dc/terms/contributor",
    "publisher": "http://purl.org/dc/terms/publisher",
    "createdWith": "http://purl.org/pav/createdWith",
    "accrualPeriodicity": "http://purl.org/dc/terms/accrualPeriodicity",
    "includedInDataCatalog": "http://schema.org/includedInDataCatalog",
    "@language": "en",
}


@router.get("/artefacts", **paths["/artefacts"]["get"])
@router.head("/artefacts", include_in_schema=False)
def artefacts(request: Request):

    graph_items = []

    # Collections
    with httpx.Client(follow_redirects=True) as client:
        response = client.get("http://vocab.nerc.ac.uk/collection?_mediatype=application/ld+json&_profile=nvs")

    data = response.json()

    graph_collection_items = get_collection_graph_items(data)

    # for item in data.get("@graph", []):
    #     uri = item.get('@id')

    #      # Determine status
    #     status = "production"
    #     if "DEPRECATED" in item.get("skos:prefLabel", "") or "DEPRECATED" in item.get("dc:title", ""):
    #         status = "deprecated"

    #     date_str = item.get("dc:date")
    #     date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")

    #     bibliographic_citation = (
    #         f"[British Oceanographic Data Centre, year {date_obj.year}, "
    #         f"{item.get('dc:title')}, version {item.get('owl:versionInfo')}, "
    #         f"{item.get('dc:publisher')}, "
    #         f"{uri} accessed on {date.today()}"
    #         f"]"
    #     )

    #     graph_items.append(
    #     {
    #         "@acronym": extract_collection_acronym(uri),
    #         "accessRights": "public",
    #         "subject": ["TBD"],
    #         "URI": uri,
    #         "creator": [item.get('dc:creator')],
    #         "identifier": uri,
    #         "status": status,
    #         "language": ["en"],
    #         "rightsHolder": item.get('dc:creator'),
    #         "license": "https://creativecommons.org/licenses/by/4.0/",
    #         "description": item.get('dc:description'),
    #         "landingPage": uri,
    #         "keyword": [""],
    #         "bibliographicCitation": bibliographic_citation,
    #         "contactPoint": ["vocab.services@bodc.ac.uk"],
    #         "publisher": [item.get('dc:publisher')],
    #         "createdWith": ["https://github.com/RDFLib/VocPrez"],
    #         "accrualPeriodicity": "http://purl.org/cld/freq/daily",
    #         "includedInDataCatalog": ["http://vocab.nerc.ac.uk/"],
    #         "@id": uri,
    #         "@type": ["https://w3id.org/mod#SemanticArtefact","http://www.w3.org/2004/02/skos/core#Collection"],
    #         "links": {
    #             "distributions": uri.replace("collection","artefacts").replace("/current/","/distributions"),
    #             }
    #         }
    #     )

    # Schemes
    with httpx.Client(follow_redirects=True) as client:
        response = client.get("http://vocab.nerc.ac.uk/scheme?_mediatype=application/ld+json&_profile=nvs")

    data = response.json()

    graph_scheme_items = get_scheme_graph_items(data)

    # for item in data.get("@graph", []):
    #     uri = item.get('@id')

    #     date_str = item.get("dc:date")
    #     date_obj = datetime.strptime(date_str["@value"], "%Y-%m-%dT%H:%M:%S")

    #     bibliographic_citation = (
    #         f"[British Oceanographic Data Centre, year {date_obj.year}, "
    #         f"{item.get('dc:title')}, version {item.get('owl:versionInfo')}, "
    #         f"{item.get('dc:publisher')}, "
    #         f"{uri} accessed on {date.today()}"
    #         f"]"
    #     )

    #     graph_items.append(
    #     {
    #         "acronym": extract_scheme_acronym(uri),
    #         "accessRights": "public",
    #         "subject": [],
    #         "URI": uri,
    #         "creator": [item.get('dc:creator')],
    #         "identifier": [uri],
    #         "status": "production",
    #         "language": ["en"],
    #         "rightsHolder": item.get('dc:creator'),
    #         "description": item.get('dc:description'),
    #         "landingPage": uri,
    #         "keyword": [""],
    #         "bibliographicCitation": bibliographic_citation,
    #         "contactPoint": ["vocab.services@bodc.ac.uk"],
    #         "publisher": [item.get('dc:publisher')],
    #         "createdWith": ["https://github.com/RDFLib/VocPrez"],
    #         "includedInDataCatalog": ["http://vocab.nerc.ac.uk/"],
    #         "@id": uri,
    #         "@type": ["https://w3id.org/mod#SemanticArtefact","http://www.w3.org/2004/02/skos/core#ConceptScheme"],
    #         "links": {
    #         "distributions": uri.replace("scheme","artefacts").replace("/current/","/distributions"),
    #         }
    #     }
    #     )

    print(type(graph_scheme_items))
    print(type(graph_collection_items))

    json_ld = {"@context": artefacts_context, "@graph": graph_collection_items + graph_scheme_items}

    return JSONResponse(content=json_ld, status_code=response.status_code)


@router.get("/artefacts/{artefactID}", **paths["/artefacts/{artefactID}"]["get"])
@router.head("/artefacts/{artefactID}", include_in_schema=False)
def artefactId(request: Request, artefactID: str):

    collection_uri = f"http://vocab.nerc.ac.uk/collection/{artefactID.upper()}/current/"
    scheme_uri = f"http://vocab.nerc.ac.uk/scheme/{artefactID.upper()}/current/"

    with httpx.Client(follow_redirects=True) as client:
        response_collection = client.get(f"{collection_uri}?_mediatype=application/ld+json&_profile=nvs")

    with httpx.Client(follow_redirects=True) as client:
        response_scheme = client.get(f"{scheme_uri}?_mediatype=application/ld+json&_profile=nvs")

    if response_collection.status_code != 200 and response_scheme.status_code != 200:
        return JSONResponse(content={"error": "artefactID not found"}, status_code=404)

    a_context = artefacts_context

    json_ld = {}
    graph_items = []

    if response_collection.status_code == 200:
        a_context["@vocab"] = collection_uri

        data = response_collection.json()
        graph_items = get_collection_graph_items(data)
        graph_item = next((item for item in graph_items if item["@id"] == collection_uri), None)

        json_ld = {"@context": a_context}
        json_ld.update(graph_item)

    else:
        print("A Scheme")
        a_context["@vocab"] = "http://vocab.nerc.ac.uk/scheme/"

    return JSONResponse(content=json_ld, status_code=200)


def extract_collection_acronym(url):
    match = re.search(r"/collection/(.*?)/current/", url)
    return match.group(1)


def extract_scheme_acronym(url):
    match = re.search(r"/scheme/(.*?)/current/", url)
    return match.group(1)


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
                "@acronym": extract_collection_acronym(uri),
                "accessRights": "public",
                "subject": ["TBD"],
                "URI": uri,
                "creator": [item.get("dc:creator")],
                "identifier": uri,
                "status": status,
                "language": ["en"],
                "rightsHolder": item.get("dc:creator"),
                "license": "https://creativecommons.org/licenses/by/4.0/",
                "description": item.get("dc:description"),
                "landingPage": uri,
                "keyword": [""],
                "bibliographicCitation": bibliographic_citation,
                "contactPoint": ["vocab.services@bodc.ac.uk"],
                "publisher": [item.get("dc:publisher")],
                "createdWith": ["https://github.com/RDFLib/VocPrez"],
                "accrualPeriodicity": "http://purl.org/cld/freq/daily",
                "includedInDataCatalog": ["http://vocab.nerc.ac.uk/"],
                "@id": uri,
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

        date_str = item.get("dc:date")
        date_obj = datetime.strptime(date_str["@value"], "%Y-%m-%dT%H:%M:%S")

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
                "subject": [],
                "URI": uri,
                "creator": [item.get("dc:creator")],
                "identifier": [uri],
                "status": "production",
                "language": ["en"],
                "rightsHolder": item.get("dc:creator"),
                "description": item.get("dc:description"),
                "landingPage": uri,
                "keyword": [""],
                "bibliographicCitation": bibliographic_citation,
                "contactPoint": ["vocab.services@bodc.ac.uk"],
                "publisher": [item.get("dc:publisher")],
                "createdWith": ["https://github.com/RDFLib/VocPrez"],
                "includedInDataCatalog": ["http://vocab.nerc.ac.uk/"],
                "@id": uri,
                "@type": ["https://w3id.org/mod#SemanticArtefact", "http://www.w3.org/2004/02/skos/core#ConceptScheme"],
                "links": {
                    "distributions": uri.replace("scheme", "artefacts").replace("/current/", "/distributions"),
                },
            }
        )

    return graph_items
