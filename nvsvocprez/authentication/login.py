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


# Authentication exceptions
class MissingRoleException(Exception):
    """Exception raised when user lacks the correct role in Auth0."""


class NotVerifiedException(Exception):
    """Exception raised when user hasn't verified their email address."""

async def process_auth(request: Request):
    """Process callback coming from Auth0."""
    # handles response from token endpoint
    token = await oauth.auth0.authorize_access_token(request)
    access_token = token["access_token"]
    id_token = token["id_token"]
    user = token.get("userinfo").json()

    # Check that user is valid before proceeding
    if not user.get("email_verified", False):
        raise NotVerifiedException
    roles = user.get(OAUTH_ROLES_NAMESPACE + "/roles", [])
    if USER_ROLE not in roles:
        raise MissingRoleException

    request.session["access_token"] = access_token
    request.session["id_token"] = id_token
    request.session["jwt_payload"] = user
    request.session["profile"] = {"user_id": user["sub"], "name": user["name"], "picture": user["picture"]}

@router.get("/auth")
@router.get("/auth/")
async def auth(request: Request):
    try:
        request = await process_auth(request= Request)
    except NotVerifiedException:
        error_url = "/login-error?error=not_verified"
    except MissingRoleException:
        error_url = "/login-error?error=missing_role"
    except Exception as exc:
        print("Authentication error:")
        print(exc)
        error_url = "/login-error"
    if error_url:
        # this logout step is necessary to clear the session from both app + auth0 sides
        return logout(request)
    return RedirectResponse("/dashboard")


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
