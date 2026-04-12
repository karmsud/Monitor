"""Tests for Phase 3 DealRepository methods — resolve_did_by_name, get_companies_by_sender_domain."""
import pytest
from unittest.mock import MagicMock, patch

from backend.db.deal_repo import DealRepository


class TestDealRepoPhase3:

    @pytest.fixture
    def repo(self):
        """Create a DealRepository with mocked connection."""
        with patch("backend.db.deal_repo.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_get_conn.return_value = mock_conn
            r = DealRepository(prod_mode=False)
            yield r

    # ── resolve_did_by_name ─────────────────────────────────────────── #

    def test_resolve_did_by_number(self, repo):
        """Numeric DID → returns the ImportDID from the matching row."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("ACME",)
        repo._conn.cursor.return_value = cursor
        result = repo.resolve_did_by_name("1001")
        assert result == "ACME"

    def test_resolve_did_by_exact_name(self, repo):
        """Exact ImportDID string → returns it."""
        cursor = MagicMock()
        # First call: numeric lookup misses (ValueError is caught internally
        # because "CSMC" is not int), so we jump to exact match.
        cursor.fetchone.return_value = ("CSMC",)
        repo._conn.cursor.return_value = cursor
        result = repo.resolve_did_by_name("CSMC")
        assert result == "CSMC"

    def test_resolve_did_by_partial_name(self, repo):
        """Single partial match → return that ImportDID."""
        cursor = MagicMock()
        # Numeric won't match, exact won't match, partial returns one row
        call_count = [0]

        def fetchone_side():
            call_count[0] += 1
            if call_count[0] <= 1:
                return None  # exact match returns None
            return None

        def fetchall_side():
            return [("CSMC_TRUST",)]

        cursor.fetchone.side_effect = fetchone_side
        cursor.fetchall.return_value = [("CSMC_TRUST",)]
        repo._conn.cursor.return_value = cursor
        result = repo.resolve_did_by_name("CSMC")
        assert result == "CSMC_TRUST"

    def test_resolve_did_ambiguous(self, repo):
        """2+ partial matches → returns None."""
        cursor = MagicMock()
        cursor.fetchone.return_value = None  # exact fails
        cursor.fetchall.return_value = [("ACME_1",), ("ACME_2",)]
        repo._conn.cursor.return_value = cursor
        result = repo.resolve_did_by_name("ACME")
        assert result is None

    def test_resolve_did_not_found(self, repo):
        """No match at all → None."""
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        repo._conn.cursor.return_value = cursor
        result = repo.resolve_did_by_name("ZZZZZ")
        assert result is None

    # ── get_companies_by_sender_domain ──────────────────────────────── #

    def test_companies_by_sender_domain(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(100,), (150,)]
        repo._conn.cursor.return_value = cursor
        result = repo.get_companies_by_sender_domain("acme.com")
        assert result == [100, 150]

    def test_companies_by_sender_domain_empty(self, repo):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        repo._conn.cursor.return_value = cursor
        result = repo.get_companies_by_sender_domain("nomatch.com")
        assert result == []

    def test_companies_by_sender_domain_extraction(self, repo):
        """Verify the prefix extracted from domain is used in the query."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [(200,)]
        repo._conn.cursor.return_value = cursor
        repo.get_companies_by_sender_domain("bigcorp.com")
        # Should search with BIGCORP prefix
        call_args = cursor.execute.call_args
        assert "BIGCORP" in str(call_args).upper() or "%BIGCORP%" in str(call_args).upper()
