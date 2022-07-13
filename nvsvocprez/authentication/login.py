"""Authentication functions used in login/logout."""
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter

router = APIRouter()

# Read in data from the .env file
config = Config('.env')
oauth = OAuth(config)


CONF_URL = 'https://bodc-localhost.eu.auth0.com/.well-known/openid-configuration'
oauth.register(
    name='auth0',
    server_metadata_url=CONF_URL,
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@router.route('/login')
async def login(request):
    redirect_uri = request.url_for('auth')
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@router.route('/auth')
async def auth(request):
    token = await oauth.auth0.authorize_access_token(request)
    user = token.get('userinfo')
    if user:
        request.session['user'] = user
    return RedirectResponse(url='/')


@router.route('/logout')
async def logout(request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')
