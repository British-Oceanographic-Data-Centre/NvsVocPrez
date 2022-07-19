"""Authentication functions used in login/logout."""
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter
from urllib.parse import quote_plus, urlencode
from utilities import config
from fastapi import Request


USER_ROLE = "nvs_user"
OAUTH_ROLES_NAMESPACE = "http://data.submissions.app"

router = APIRouter()
config = config.verify_env_file()
oauth = OAuth(config)


oauth.register(
    name="auth0",
    server_metadata_url=config("AUTH0_CONF_URL"),
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login")
@router.get("/login/")
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@router.get("/auth")
@router.get("/auth/")
async def auth(request: Request):
    token = await oauth.auth0.authorize_access_token(request)
    user = token.get("userinfo")
    if user:
        request.session["user"] = user
    # Check that user is valid before proceeding
    if not user.get("email_verified", False):
        return RedirectResponse(url="/")
    roles = user.get(OAUTH_ROLES_NAMESPACE + "/roles", [])
    if USER_ROLE not in roles:
        return RedirectResponse(url="/")
    return RedirectResponse(url="/")


@router.get("/logout")
@router.get("/logout/")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(
        "https://"
        + config("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": request.url_for("index"),
                "client_id": config("AUTH0_CLIENT_ID"),
            },
            quote_via=quote_plus,
        )
    )
