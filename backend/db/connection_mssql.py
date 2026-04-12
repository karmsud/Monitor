"""MSSQL connection via pyodbc for US Bank production."""
import json
import pyodbc
import logging
import os
from typing import Optional

logger = logging.getLogger("frp.db.mssql")


def get_mssql_connection(
    secrets_path: Optional[str] = None,
    server: Optional[str] = None,
    database: Optional[str] = None,
) -> pyodbc.Connection:
    """Return a pyodbc connection to the configured MSSQL instance.

    Parameters
    ----------
    secrets_path:
        Path to ``secrets_mssql.json`` for driver / auth settings.
    server:
        MSSQL server name from VS Code setting ``frpAgent.mssqlServer``.
    database:
        MSSQL database name from VS Code setting ``frpAgent.mssqlDatabase``.

    Both *server* and *database* are required.  If either is blank the
    function raises ``ValueError`` so the caller can surface a friendly
    message asking the user to fill in the extension settings.
    """
    # ── Validate required VS Code settings ────────────────────── #
    if not server:
        raise ValueError(
            "MSSQL server name is not configured. "
            "Please set 'frpAgent.mssqlServer' in VS Code settings "
            "(e.g. VMCKSA69901M0VX.us-bank-dns.com,49001)."
        )
    if not database:
        raise ValueError(
            "MSSQL database name is not configured. "
            "Please set 'frpAgent.mssqlDatabase' in VS Code settings "
            "(e.g. Servicing)."
        )

    # ── Load auth / driver settings from secrets file ─────────── #
    if not secrets_path:
        secrets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config", "secrets_mssql.json",
        )
    with open(secrets_path) as f:
        secrets = json.load(f)

    driver = secrets.get("driver", "{ODBC Driver 17 for SQL Server}")
    if not driver.startswith("{"):
        driver = "{" + driver + "}"

    # Use the server value as-is from VS Code settings.
    srv = server

    # Auth mode
    trusted = secrets.get("trusted_connection", "no").lower()

    # Build connection string to match the proven working template:
    #   DRIVER={ODBC Driver 17 for SQL Server};SERVER=tcp:HOST,PORT;DATABASE=DB;Trusted_Connection=yes;MultiSubnetFailover=yes;LoginTimeout=60;
    # The tcp: prefix and trailing semicolons are significant for ODBC compatibility.
    if trusted in ("yes", "1", "true"):
        conn_str = (
            f"DRIVER={driver};"
            f"SERVER=tcp:{srv};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
            f"MultiSubnetFailover=yes;"
            f"LoginTimeout=60;"
        )
    else:
        conn_str = (
            f"DRIVER={driver};"
            f"SERVER=tcp:{srv};"
            f"DATABASE={database};"
            f"UID={secrets['uid']};"
            f"PWD={secrets['pwd']};"
            f"MultiSubnetFailover=yes;"
            f"LoginTimeout=60;"
        )

    logger.info("Connecting to MSSQL: %s/%s", server, database)
    logger.info("Connection string: %s", conn_str)
    logger.info("Secrets loaded from: %s", secrets_path)
    return pyodbc.connect(conn_str)
