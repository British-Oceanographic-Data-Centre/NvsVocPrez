"""Render the Cache Clear Endpoint."""
from fastapi import APIRouter
from utilities.utility_functions import cache_clear
from starlette.responses import PlainTextResponse
from starlette.requests import Request

router = APIRouter()



@router.get("/cache-clear", include_in_schema=False)
def cache_clr(request: Request):
    cache_clear()
    return PlainTextResponse("Cache cleared")
