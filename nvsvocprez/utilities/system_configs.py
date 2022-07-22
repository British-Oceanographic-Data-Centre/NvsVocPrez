"""Added as a test to ensure that the collection_page can use the information here,

If it can, then all information from profiles.py should live in here."""
import os

DEBUG = os.getenv("DEBUG", True)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = os.getenv("PORT", 5000)

SPARQL_ENDPOINT = os.getenv("SPARQL_ENDPOINT", "http://vocab.nerc.ac.uk/sparql/sparql")
SPARQL_USERNAME = os.getenv("SPARQL_USERNAME", "")
SPARQL_PASSWORD = os.getenv("SPARQL_PASSWORD", "")
SYSTEM_URI = os.getenv("SYSTEM_URI", "http://localhost:5007")
DATA_URI = os.getenv("DATA_URI", "http://vocab.nerc.ac.uk")
ORDS_ENDPOINT_URL = os.getenv("ORDS_ENDPOINT_URL")  # BODC ORDS URL.

acc_dep_map = {
    "accepted": '?c <http://www.w3.org/2002/07/owl#deprecated> "false" .',
    "deprecated": '?c <http://www.w3.org/2002/07/owl#deprecated> "true" .',
    "all": "",
    None: "",
}
