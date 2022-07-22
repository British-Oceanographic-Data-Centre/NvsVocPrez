"""Render the Well Known Endpoint."""
from typing import AnyStr, Optional

from fastapi import APIRouter
from pyldapi import Renderer
from rdflib import Graph
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from utilities.templates import void_location

from utilities.system_configs import DATA_URI
from utilities.profiles import void

router = APIRouter()


@router.get("/.well_known/", include_in_schema=False)
@router.head("/.well_known/", include_in_schema=False)
def well_known(request: Request):
    return RedirectResponse(url="/.well_known/void")


@router.get("/.well_known/void", include_in_schema=False)
@router.head("/.well_known/void", include_in_schema=False)
def well_known_void(
    request: Request,
    _profile: Optional[AnyStr] = None,
    _mediatype: Optional[AnyStr] = "text/turtle",
):
    class WkRenderer(Renderer):
        def __init__(self):
            super().__init__(
                request,
                f"{DATA_URI}/.well_known/void",
                {"void": void},
                "void",
            )

        def render(self):
            if self.mediatype == "text/turtle":
                return Response(open(void_location).read(), headers={"Content-Type": "text/turtle"})
            else:
                g = Graph().parse(void_file, format="turtle")
                return Response(
                    content=g.serialize(format=self.mediatype),
                    headers={"Content-Type": self.mediatype},
                )

    return WkRenderer().render()
