"""Authentication functions used in login/logout."""
from urllib.request import Request
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter
from urllib.parse import quote_plus, urlencode
from utilities import config


router = APIRouter()
config = config.verify_env_file()
oauth = OAuth(config)


CONF_URL = "https://bodc-localhost.eu.auth0.com/.well-known/openid-configuration"
oauth.register(name="auth0", server_metadata_url=CONF_URL, client_kwargs={"scope": "openid email profile"})

@router.get('/login')
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@router.get('/auth')
async def auth(request: Request):
    token = await oauth.auth0.authorize_access_token(request)
    user = token.get("userinfo")
    if user:
        request.session["user"] = user
    return RedirectResponse(url="/")


@router.get('/logout')
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(
        "https://"
        + config("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {"returnTo": request.url_for("index"), "client_id": config("AUTH0_CLIENT_ID")},
            quote_via=quote_plus,
        )
    )
