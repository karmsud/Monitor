"""Tests for Phase 2 DealRepository methods — get_companies_by_import_did, get_all_distinct_company_ids."""
import pytest
from unittest.mock import MagicMock, patch

from backend.db.deal_repo import DealRepository


class TestDealRepoPhase2:

    @pytest.fixture
    def repo(self):
        """Create a DealRepository with mocked connection."""
        with patch("backend.db.deal_repo.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_get_conn.return_value = mock_conn
            r = DealRepository(prod_mode=False)
            yield r

    def test_get_companies_by_import_did_returns_list(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(100,), (200,)]
        repo._conn.cursor.return_value = cursor
        result = repo.get_companies_by_import_did("ACME")
        assert result == [100, 200]

    def test_get_companies_by_import_did_empty(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        repo._conn.cursor.return_value = cursor
        result = repo.get_companies_by_import_did("NOMATCH")
        assert result == []

    def test_get_companies_by_import_did_single(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(150,)]
        repo._conn.cursor.return_value = cursor
        result = repo.get_companies_by_import_did("CSMC")
        assert result == [150]

    def test_get_all_distinct_company_ids_returns_list(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(100,), (150,), (200,)]
        repo._conn.cursor.return_value = cursor
        result = repo.get_all_distinct_company_ids()
        assert result == [100, 150, 200]

    def test_get_all_distinct_company_ids_empty(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        repo._conn.cursor.return_value = cursor
        result = repo.get_all_distinct_company_ids()
        assert result == []

    def test_get_companies_by_import_did_executes_query(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        repo._conn.cursor.return_value = cursor
        repo.get_companies_by_import_did("TEST")
        cursor.execute.assert_called_once()
