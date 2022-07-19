"""Authentication functions used in login/logout."""
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter
from urllib.parse import quote_plus, urlencode
from utilities import config
from fastapi import Request

router = APIRouter()
config = config.verify_env_file()
oauth = OAuth(config)


oauth.register(
    name="auth0",
    server_metadata_url=config("AUTH0_CONF_URL"),
    client_kwargs={"scope": "openid email profile"},
)


class MissingRoleException(Exception):
    """Exception raised when user lacks the correct role in Auth0."""


class NotVerifiedException(Exception):
    """Exception raised when user hasn't verified their email address."""


@router.get("/login")
@router.get("/login/")
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


async def process_auth(request: Request):
    """Process callback coming from Auth0."""
    # handles response from token endpoint
    token = await oauth.auth0.authorize_access_token(request)
    user = token.get("userinfo")
    # Check that user is valid before proceeding
    if not user.get("email_verified", False):
        raise NotVerifiedException
    roles = user.get(config("OAUTH_ROLES_NAMESPACE") + "/roles", [])
    if config("USER_ROLE") not in roles:
        raise MissingRoleException
    request.session["user"] = user
    return request


@router.get("/auth")
@router.get("/auth/")
async def auth(request: Request):
    error = False
    try:
        request = await process_auth(request)
    except NotVerifiedException:
        error = True
    except MissingRoleException:
        error = True
    except Exception as exc:
        print("exc:", exc)
        error = True
    if error:
        return await logout(request)
    return RedirectResponse("/")


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
