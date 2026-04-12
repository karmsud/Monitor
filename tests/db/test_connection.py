"""Tests for the database connection factory."""
from unittest.mock import patch, MagicMock

import pytest

from backend.db.connection import get_connection


class TestConnectionFactory:

    @patch("backend.db.connection.get_connection.__module__", "backend.db.connection")
    @patch("backend.db.connection_mysql.get_mysql_connection")
    def test_factory_routes_prod_false(self, mock_mysql):
        """When prod_mode=False the MySQL branch is used."""
        mock_mysql.return_value = MagicMock()
        conn = get_connection(prod_mode=False, secrets_path="dummy.json")
        mock_mysql.assert_called_once_with("dummy.json")

    @patch("backend.db.connection_mssql.get_mssql_connection")
    def test_factory_routes_prod_true(self, mock_mssql):
        """When prod_mode=True the MSSQL branch is used."""
        mock_mssql.return_value = MagicMock()
        conn = get_connection(prod_mode=True, secrets_path="dummy.json",
                              mssql_server="srv", mssql_database="db")
        mock_mssql.assert_called_once_with("dummy.json", server="srv", database="db")

    def test_missing_secrets_file(self):
        """A non-existent secrets file should raise an error."""
        with pytest.raises(Exception):
            get_connection(
                prod_mode=False,
                secrets_path="/nonexistent/path/secrets.json",
            )
