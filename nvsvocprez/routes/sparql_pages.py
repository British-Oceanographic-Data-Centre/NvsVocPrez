"""Render the Sparql Pages."""
import json
import logging
from pathlib import Path

import fastapi
from pyldapi.renderer import RDF_MEDIATYPES
from pyldapi.data import RDF_FILE_EXTS

from rdflib import Graph
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from .page_configs import SYSTEM_URI
from .utils import get_accepts, get_user_status

router = fastapi.APIRouter()
api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))

config_file_location = Path(__file__).parent.parent / "api_doc_config.json"
with open(config_file_location, "r") as config_file:
    paths = json.load(config_file)["paths"]
logging.basicConfig(level=logging.DEBUG)


@router.get("/sparql", include_in_schema=False)
@router.get("/sparql/", **paths["/sparql/"]["get"])
@router.head("/sparql", include_in_schema=False)
@router.head("/sparql/", include_in_schema=False)
def sparql(request: Request):
    # queries to /sparql with an accept header set to a SPARQL return type or an RDF type
    # are forwarded to /endpoint for a response
    # all others (i.e. with no Accept header, an Accept header HTML or for an unsupported Accept header
    # result in the SPARQL page HTML respose where the query is placed into the YasGUI UI for interactive querying
    SPARQL_RESPONSE_MEDIA_TYPES = [
        "application/sparql-results+json",
        "text/csv",
        "text/tab-separated-values",
    ]
    QUERY_RESPONSE_MEDIA_TYPES = ["text/html"] + SPARQL_RESPONSE_MEDIA_TYPES + RDF_MEDIATYPES
    accepts = get_accepts(request.headers["Accept"])
    accept = [x for x in accepts if x in QUERY_RESPONSE_MEDIA_TYPES][0]

    if accept == "text/html":
        return templates.TemplateResponse(
            "sparql.html", {"request": request, "logged_in_user": get_user_status(request)}
        )
    else:
        return endpoint_get(request)


# the SPARQL endpoint under-the-hood
def _get_sparql_service_description(rdf_fmt="text/turtle"):
    """Return an RDF description of PROMS' read only SPARQL endpoint in a requested format
    :param rdf_fmt: 'turtle', 'n3', 'xml', 'json-ld'
    :return: string of RDF in the requested format
    """
    sd_ttl = """
        @prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix sd:     <http://www.w3.org/ns/sparql-service-description#> .
        @prefix sdf:    <http://www.w3.org/ns/formats/> .
        @prefix void:   <http://rdfs.org/ns/void#> .
        @prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
        <{0}>
            a                       sd:Service ;
            sd:endpoint             <{0}> ;
            sd:supportedLanguage    sd:SPARQL11Query ; # yes, read only, sorry!
            sd:resultFormat         sdf:SPARQL_Results_JSON ;  # yes, we only deliver JSON results, sorry!
            sd:feature sd:DereferencesURIs ;
            sd:defaultDataset [
                a sd:Dataset ;
                sd:defaultGraph [
                    a sd:Graph ;
                    void:triples "100"^^xsd:integer
                ]
            ]
        .
    """.format(
        SYSTEM_URI + "/sparql"
    )
    grf = Graph().parse(data=sd_ttl)
    if rdf_fmt in RDF_MEDIATYPES:
        return grf.serialize(format=rdf_fmt)
    else:
        raise ValueError("Input parameter rdf_format must be one of: " + ", ".join(RDF_MEDIATYPES))


def _sparql_query2(q, mimetype="application/json"):
    """Make a SPARQL query"""
    import httpx
    from config import SPARQL_ENDPOINT, SPARQL_PASSWORD, SPARQL_USERNAME

    data = q
    headers = {
        "Content-Type": "application/sparql-query",
        "Accept": mimetype,
        "Accept-Encoding": "UTF-8",
    }
    if SPARQL_USERNAME is not None and SPARQL_PASSWORD is not None:
        auth = (SPARQL_USERNAME, SPARQL_PASSWORD)
    else:
        auth = None

    try:
        logging.debug("endpoint={}\ndata={}\nheaders={}".format(SPARQL_ENDPOINT, data, headers))
        if auth is not None:
            r = httpx.post(SPARQL_ENDPOINT, auth=auth, data=data, headers=headers, timeout=60)
        else:
            r = httpx.post(SPARQL_ENDPOINT, data=data, headers=headers, timeout=60)
        return r.content.decode()
    except Exception as ex:
        raise ex


@router.post("/sparql/", **paths["/sparql/"]["post"])
@router.post("/sparql", include_in_schema=False)
@router.post("/endpoint", include_in_schema=False)
def endpoint_post(request: Request, query: str = fastapi.Form(...)):
    """
    TESTS
    Form POST:
    curl -X POST -d query="PREFIX%20skos%3A%20%3Chttp%3A%2F%2Fwww.w3.org%2F2004%2F02%2Fskos%2Fcore%23%3E%0ASELECT%20* \
    %20WHERE%20%7B%3Fs%20a%20skos%3AConceptScheme%20.%7D" http://localhost:5000/endpoint
    Raw POST:
    curl -X POST -H 'Content-Type: application/sparql-query' --data-binary @query.sparql http://localhost:5000/endpoint
    using query.sparql:
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT * WHERE {?s a skos:ConceptScheme .}
    GET:
    curl http://localhost:5000/endpoint?query=PREFIX%20skos%3A%20%3Chttp%3A%2F%2Fwww.w3.org%2F2004%2F02%2Fskos%2Fcore \
    %23%3E%0ASELECT%20*%20WHERE%20%7B%3Fs%20a%20skos%3AConceptScheme%20.%7D
    GET CONSTRUCT:
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        CONSTRUCT {?s a rdf:Resource}
        WHERE {?s a skos:ConceptScheme}
    curl -H 'Accept: application/ld+json' http://localhost:5000/endpoint?query=PREFIX%20rdf%3A%20%3Chttp%3A%2F%2F \
    www.w3.org%2F1999%2F02%2F22-rdf-syntax-ns%23%3E%0APREFIX%20skos%3A%20%3Chttp%3A%2F%2Fwww.w3.org%2F2004%2F02%2F \
    skos%2Fco23%3E%0ACONSTRUCT%20%7B%3Fs%20a%20rdf%3AResource%7D%0AWHERE%20%7B%3Fs%20a%20skos%3AConceptScheme%7D
    """
    """Pass on the SPARQL query to the underlying endpoint defined in config"""
    if "application/x-www-form-urlencoded" in request.headers["content-type"]:
        """
        https://www.w3.org/TR/2013/REC-sparql11-protocol-20130321/#query-via-post-urlencoded
        2.1.2 query via POST with URL-encoded parameters
        Protocol clients may send protocol requests via the HTTP POST method by URL encoding the parameters. When
        using this method, clients must URL percent encode all parameters and include them as parameters within the
        request body via the application/x-www-form-urlencoded media type with the name given above. Parameters must
        be separated with the ampersand (&) character. Clients may include the parameters in any order. The content
        type header of the HTTP request must be set to application/x-www-form-urlencoded.
        """

        if query is None or len(query) < 5:
            return PlainTextResponse(
                "Your POST request to the SPARQL endpoint must contain a 'query' parameter if form posting is used.",
                status_code=400,
            )
    elif "application/sparql-query" in request.headers["content-type"]:
        """
        https://www.w3.org/TR/2013/REC-sparql11-protocol-20130321/#query-via-post-direct
        2.1.3 query via POST directly
        Protocol clients may send protocol requests via the HTTP POST method by including the query directly and
        unencoded as the HTTP request message body. When using this approach, clients must include the SPARQL query
        string, unencoded, and nothing else as the message body of the request. Clients must set the content type
        header of the HTTP request to application/sparql-query. Clients may include the optional default-graph-uri
        and named-graph-uri parameters as HTTP query string parameters in the request URI. Note that UTF-8 is the
        only valid charset here.
        """
        query = request.query_params.get("data")  # get the raw request
        if query is None:
            return PlainTextResponse(
                "Your POST request to this SPARQL endpoint must contain the query in plain text in the "
                "POST body if the Content-Type 'application/sparql-query' is used.",
                status_code=400,
            )
    else:
        return PlainTextResponse(
            "Your POST request to this SPARQL endpoint must either the 'application/x-www-form-urlencoded' or"
            "'application/sparql-query' ContentType.",
            status_code=400,
        )

    try:
        if "CONSTRUCT" in query:
            format_mimetype = "text/turtle"
            return Response(
                _sparql_query2(query, request.headers["Accept"]),
                media_type=format_mimetype,
            )
        else:
            return Response(
                _sparql_query2(query, request.headers["Accept"]),
            )
    except ValueError as e:
        return PlainTextResponse(
            "Input error for query {}.\n\nError message: {}".format(query, str(e)),
            status_code=400,
        )
    except ConnectionError as e:
        return PlainTextResponse(str(e), status_code=500)


@router.get("/endpoint", include_in_schema=False)
@router.head("/endpoint", include_in_schema=False)
def endpoint_get(request: Request):
    if request.query_params.get("query") is not None:
        # SPARQL GET request
        """
        https://www.w3.org/TR/2013/REC-sparql11-protocol-20130321/#query-via-get
        2.1.1 query via GET
        Protocol clients may send protocol requests via the HTTP GET method. When using the GET method, clients must
        URL percent encode all parameters and include them as query parameter strings with the names given above.
        HTTP query string parameters must be separated with the ampersand (&) character. Clients may include the
        query string parameters in any order.
        The HTTP request MUST NOT include a message body.
        """
        query = request.query_params.get("query")
        accepts = get_accepts(request.headers["Accept"])
        if "CONSTRUCT" in query or "DESCRIBE" in query:
            accept = [x for x in accepts if x in RDF_MEDIATYPES][0]
            if accept is None:
                return PlainTextResponse(
                    "Accept header must include at least on RDF Media Type:" + ", ".join(RDF_MEDIATYPES) + ".",
                    status_code=400,
                )
            return Response(
                _sparql_query2(query, mimetype=request.headers["Accept"]),
                media_type=accept,
                headers={"Content-Disposition": f"attachment; filename=query_result.{RDF_FILE_EXTS[accept]}"},
            )
        else:
            return Response(_sparql_query2(query), media_type="application/sparql-results+json")
    else:
        # SPARQL Service Description
        """
        https://www.w3.org/TR/sparql11-service-description/#accessing
        SPARQL services made available via the SPARQL Protocol should return a service description document at the
        service endpoint when dereferenced using the HTTP GET operation without any query parameter strings
        provided. This service description must be made available in an RDF serialization, may be embedded in
        (X)HTML by way of RDFa, and should use content negotiation if available in other RDF representations.
        """

        accepts = get_accepts(request.headers["Accept"])
        if accepts[0] in ["application/sparql-results+json", "text/html"]:
            # show the SPARQL query form
            return RedirectResponse(url="/sparql")
        else:
            accept = [x for x in accepts if x in RDF_MEDIATYPES][0]
            if accept is None:
                return PlainTextResponse(
                    "Accept header must include at least on RDF Media Type:" + ", ".join(RDF_MEDIATYPES) + ".",
                    status_code=400,
                )
            return Response(_get_sparql_service_description(accept), media_type=accept)
