"""Reads .env file and sends the config to authentication processes."""

from starlette.config import Config


class MissingKeyError(Exception):
    """Raised when the env file is missing one or more keys."""


expected_config_keys = {
    "LOGIN_ENABLE",
    "AUTH0_CLIENT_ID",
    "AUTH0_CLIENT_SECRET",
    "AUTH0_DOMAIN",
    "APP_SECRET_KEY",
    "OAUTH_BASE_URL",
}


def verify_env_file() -> Config:
    """Verify env file has all required data.

    Values in .env file are checked against the expected keys,
    they are returned if all present, or a MissingKeyError is raised.
    """
    configuration = Config(".env")

    actual_config_keys = set(configuration.file_values.keys())

    if expected_config_keys == actual_config_keys:
        return configuration
    raise MissingKeyError(", ".join(expected_config_keys - actual_config_keys))
