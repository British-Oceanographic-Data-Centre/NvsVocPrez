"""Entry point for NVS-VocPrez Web Application."""
import fastapi
import uvicorn
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware

from authentication import login
from routes import (about_page, cache_clear_page, collection_pages,
                    contact_page, index_page, mapping_page, scheme_pages,
                    sparql_pages, standard_name_page, well_known_page)
from utilities.env_file_config import verify_env_file
from utilities.system_configs import PORT, SYSTEM_URI
from utilities.templates import static_files_location
from utilities.utility_functions import api_details, doc_config


class NvsVocPrez:
    def __init__(self):
        self.api = fastapi.FastAPI(
            title=doc_config["api_details"]["title"],
            description=api_details["description"],
            version=api_details["version"],
            contact=api_details["contact"],
            license_info=api_details["license_info"],
            openapi_tags=doc_config["tags"],
            docs_url=api_details["docs_url"],
            swagger_ui_parameters={"defaultModelsExpandDepth": -1},
        )
        self.api.mount("/static", static_files_location, name="static")
        self._check_env_file()

    def _check_env_file(self):
        """Checks .env file for correct configuration

        This method is called upon app startup, and calls a function within
        utilities/config. If the checks pass then the webapp will run,
        if not, then the missing or extra fields will be printed.
        """
        self.config = verify_env_file()

    def _add_session_middlware(self) -> None:
        """Adds middleware to the session."""
        self.api.add_middleware(
            SessionMiddleware,
            max_age=self.config("MAX_SESSION_LENGTH", cast=int, default=None),
            secret_key=self.config("APP_SECRET_KEY"),
        )

    def _add_routes_to_api(self) -> None:
        """Adds routes from /routes/ directory to the API."""
        self.api.include_router(index_page.router)
        self.api.include_router(about_page.router)
        self.api.include_router(contact_page.router)
        self.api.include_router(collection_pages.router)
        self.api.include_router(scheme_pages.router)
        self.api.include_router(sparql_pages.router)
        self.api.include_router(mapping_page.router)
        self.api.include_router(standard_name_page.router)
        self.api.include_router(well_known_page.router)
        self.api.include_router(cache_clear_page.router)

    def _determine_login_setup(self) -> None:
        """Add login functionality to API if set to true in .env file"""
        if self.config("LOGIN_ENABLE") == "true":
            self.api.include_router(login.router)

    def run_web_app(self) -> fastapi.applications.FastAPI:
        """Prepares app and return the API object to be ran by Uvicorn."""
        self._add_session_middlware()
        self._add_routes_to_api()
        self._determine_login_setup()
        return self.api


nvs_instance = NvsVocPrez()
api = nvs_instance.run_web_app()
print(type(api))


if __name__ == "__main__":
    uvicorn.run(api, port=PORT, host=SYSTEM_URI)
