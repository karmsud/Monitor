"""Tests for DealRepository — all database calls are mocked."""
from unittest.mock import patch, MagicMock

import pytest

from backend.db.deal_repo import DealRepository


def _mock_cursor(fetchone_val=None, fetchall_val=None):
    """Create a mock cursor with preset return values."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_val
    cursor.fetchall.return_value = fetchall_val or []
    cursor.description = [("DID",), ("ImportDID",), ("CompanyID",)]
    return cursor


@pytest.fixture
def repo():
    """Return a DealRepository backed by a mocked connection."""
    with patch("backend.db.deal_repo.get_connection") as mock_gc:
        mock_conn = MagicMock()
        mock_gc.return_value = mock_conn
        r = DealRepository(prod_mode=False)
        r._mock_conn = mock_conn  # stash for tests
        yield r


class TestDealRepository:

    def test_servicer_exists_true(self, repo):
        cursor = _mock_cursor(fetchone_val=(1,))
        repo._mock_conn.cursor.return_value = cursor
        assert repo.servicer_exists(150) is True

    def test_servicer_exists_false(self, repo):
        cursor = _mock_cursor(fetchone_val=(0,))
        repo._mock_conn.cursor.return_value = cursor
        assert repo.servicer_exists(999) is False

    def test_get_deals_by_company(self, repo):
        cursor = _mock_cursor(
            fetchall_val=[
                ("DID001", "IMP001", 150),
                ("DID002", "IMP002", 150),
            ]
        )
        repo._mock_conn.cursor.return_value = cursor
        deals = repo.get_deals_by_company(150)
        assert isinstance(deals, list)
        assert len(deals) == 2

    def test_get_deals_empty(self, repo):
        cursor = _mock_cursor(fetchall_val=[])
        repo._mock_conn.cursor.return_value = cursor
        deals = repo.get_deals_by_company(999)
        assert deals == []

    def test_get_all_servicer_ids(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(1,), (2,), (3,)]
        repo._mock_conn.cursor.return_value = cursor
        ids = repo.get_all_servicer_ids()
        assert ids == {1, 2, 3}

    def test_search_deals_by_filters_combines_conditions(self, repo):
        cursor = _mock_cursor(fetchall_val=[("DID001", "KF169", 569)])
        repo._mock_conn.cursor.return_value = cursor

        deals = repo.search_deals_by_filters([
            {"type": "did", "value": "FREMF"},
            {"type": "keyword", "value": "KF169"},
            {"type": "company", "value": "569"},
        ])

        assert len(deals) == 1
        sql, params = cursor.execute.call_args[0]
        assert "DID LIKE ?" in sql
        assert "ImportDID LIKE ?" in sql
        assert "CompanyID = ?" in sql
        assert params == ("%FREMF%", "%KF169%", 569)

    def test_search_deals_by_filters_supports_servicer_alias(self, repo):
        cursor = _mock_cursor(fetchall_val=[("DID001", "KF169", 569)])
        repo._mock_conn.cursor.return_value = cursor

        deals = repo.search_deals_by_filters([
            {"type": "servicer", "value": "servicer 569"},
        ])

        assert len(deals) == 1
        _, params = cursor.execute.call_args[0]
        assert params == (569,)

    def test_search_deals_by_filters_rejects_duplicate_company_dimension(self, repo):
        with pytest.raises(ValueError, match="Duplicate deal filter type"):
            repo.search_deals_by_filters([
                {"type": "company", "value": "569"},
                {"type": "servicer", "value": "569"},
            ])

    def test_close_idempotent(self, repo):
        repo.close()
        repo.close()  # second call should not raise
