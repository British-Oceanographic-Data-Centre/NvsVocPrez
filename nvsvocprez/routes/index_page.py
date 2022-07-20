"""Render the home page."""
from pathlib import Path

from fastapi import APIRouter
from rdflib import Graph
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from pyldapi import Renderer

from utilities.system_configs import SYSTEM_URI
from utilities.profiles import dcat, sdo
from utilities.utility_functions import get_user_status
from utilities.templates import sdo_location, dcat_location

router = APIRouter()
api_home_dir = Path(__file__).parent.parent
templates = Jinja2Templates(str(api_home_dir / "view" / "templates"))


@router.get("/", include_in_schema=False)
@router.head("/", include_in_schema=False)
def index(request: Request):
    dcat_file = dcat_location
    sdo_file = sdo_location

    class DatasetRenderer(Renderer):
        def __init__(self):
            self.instance_uri = SYSTEM_URI
            self.label = "NERC Vocabulary Server Content"
            self.comment = (
                "The NVS gives access to standardised and hierarchically-organized vocabularies. It is "
                "managed by the British Oceanographic Data Centre at the National Oceanography Centre "
                "(NOC) in Liverpool and Southampton, and receives funding from the Natural Environment "
                "Research Council (NERC) in the United Kingdom. Major technical developments have also "
                "been funded by European Union's projects notably the Open Service Network for Marine "
                "Environmental Data (NETMAR) programme, and the SeaDataNet and SeaDataCloud projects."
            )
            super().__init__(
                request,
                self.instance_uri,
                {"dcat": dcat, "sdo": sdo},
                "dcat",
            )

        def render(self):
            if self.profile == "dcat":
                if self.mediatype == "text/html":
                    return templates.TemplateResponse(
                        "index.html",
                        {
                            "request": request,
                            "logged_in_user": get_user_status(request),
                        },
                    )
                else:  # all other formats are RDF
                    if self.mediatype == "text/turtle":
                        return Response(
                            open(dcat_file).read().replace("xxx", self.instance_uri),
                            headers={"Content-Type": "text/turtle"},
                        )
                    else:
                        g = Graph().parse(
                            data=open(dcat_file).read().replace("xxx", self.instance_uri),
                            format="turtle",
                        )
                        return Response(
                            content=g.serialize(format=self.mediatype),
                            headers={"Content-Type": self.mediatype},
                        )
            elif self.profile == "sdo":
                if self.mediatype == "text/turtle":
                    return Response(
                        open(sdo_file).read().replace("xxx", self.instance_uri),
                        headers={"Content-Type": "text/turtle"},
                    )
                else:
                    g = Graph().parse(
                        data=open(sdo_file).read().replace("xxx", self.instance_uri),
                        format="turtle",
                    )
                    return Response(
                        content=g.serialize(format=self.mediatype),
                        headers={"Content-Type": self.mediatype},
                    )

            alt = super().render()
            if alt is not None:
                return alt

    return DatasetRenderer().render()
