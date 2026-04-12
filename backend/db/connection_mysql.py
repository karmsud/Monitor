"""MySQL connection via pyodbc for local development."""
import json
import logging
import os

import pyodbc

logger = logging.getLogger("frp.db.mysql")


def get_mysql_connection(secrets_path: str = None) -> pyodbc.Connection:
    """Return a pyodbc connection to the configured MySQL instance."""
    if not secrets_path:
        secrets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config", "secrets_mysql.json",
        )
    with open(secrets_path) as f:
        secrets = json.load(f)

    driver = secrets["driver"]
    # Ensure driver name is wrapped in braces for the ODBC conn string
    if not driver.startswith("{"):
        driver = "{" + driver + "}"

    conn_str = (
        f"DRIVER={driver};"
        f"SERVER={secrets['server']};"
        f"PORT={secrets.get('port', 3306)};"
        f"DATABASE={secrets['database']};"
        f"UID={secrets['uid']};"
        f"PWD={secrets['pwd']}"
    )
    logger.info(
        "Connecting to MySQL: %s:%s/%s",
        secrets["server"], secrets.get("port", 3306), secrets["database"],
    )
    return pyodbc.connect(conn_str)
