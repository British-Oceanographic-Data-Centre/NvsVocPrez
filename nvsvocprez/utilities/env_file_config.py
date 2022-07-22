"""Reads .env file, checks for correct setup and is then used in the Auth process."""

from starlette.config import Config


class EnvKeyError(Exception):
    """Raised when the env does not have the expected keys"""


expected_config_keys = {
    "LOGIN_ENABLE",
    "AUTH0_CLIENT_ID",
    "AUTH0_CLIENT_SECRET",
    "AUTH0_DOMAIN",
    "APP_SECRET_KEY",
    "OAUTH_BASE_URL",
    "LOGIN_ENABLE",
    "AUTH0_CONF_URL",
    "OAUTH_ROLES_NAMESPACE",
    "USER_ROLE",
}


def verify_env_file() -> Config:
    """Verify env file has all required data.

    Values in .env file are checked against the expected keys,
    they are returned if all present, or a MissingKeyError is raised.
    """
    configuration = Config(".env")
    actual_config_keys = set(configuration.file_values.keys())

    if expected_config_keys == actual_config_keys or (
        expected_config_keys | {"MAX_SESSION_LENGTH"} == actual_config_keys
    ):
        return configuration
    elif len(actual_config_keys) < len(expected_config_keys):
        error_str = " ".join(expected_config_keys - actual_config_keys) + " are missing."
    elif len(actual_config_keys) > len(expected_config_keys):
        error_str = " ".join(actual_config_keys - expected_config_keys) + " are unexpected extra keys."
    raise EnvKeyError(error_str)
