"""Database connection factory supporting dual-mode operation."""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("frp.db")


def get_connection(
    prod_mode: bool = False,
    secrets_path: Optional[str] = None,
    mssql_server: Optional[str] = None,
    mssql_database: Optional[str] = None,
):
    """
    Get a database connection based on environment mode.
    prod_mode=True → MSSQL, False → MySQL
    secrets_path: path to JSON secrets file. If None, resolve from config/ directory.
    mssql_server / mssql_database: passed through to MSSQL connection (from VS Code settings).
    """
    if prod_mode:
        from .connection_mssql import get_mssql_connection
        return get_mssql_connection(secrets_path, server=mssql_server, database=mssql_database)
    else:
        from .connection_mysql import get_mysql_connection
        return get_mysql_connection(secrets_path)
