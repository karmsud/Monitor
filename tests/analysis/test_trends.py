"""Tests for backend.analysis.trends — 18 tests for TrendAnalyzer."""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from backend.analysis.trends import TrendAnalyzer
from backend.analysis.models import TrendDay, TrendSummary


class TestTrendAnalyzerInit:
    def test_init_stores_analytics(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        assert analyzer._analytics is mock_log_analytics


class TestTrendAnalyzerValidation:
    def test_days_zero_raises(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        with pytest.raises(ValueError, match="days must be 1"):
            analyzer.analyze(days=0)

    def test_days_negative_raises(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        with pytest.raises(ValueError, match="days must be 1"):
            analyzer.analyze(days=-5)

    def test_days_over_365_raises(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        with pytest.raises(ValueError, match="days must be 1"):
            analyzer.analyze(days=400)

    def test_days_boundary_1_accepted(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=1)
        assert isinstance(result, TrendSummary)
        assert result.period_days == 1

    def test_days_boundary_365_accepted(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=365)
        assert isinstance(result, TrendSummary)
        assert result.period_days == 365


class TestTrendAnalyzerAnalyze:
    def test_returns_trend_summary(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=14)
        assert isinstance(result, TrendSummary)

    def test_period_days_matches_input(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=7)
        assert result.period_days == 7

    def test_day_list_length_matches_days(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=10)
        assert len(result.days) == 10

    def test_totals_keys_present(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=14)
        assert "total_files" in result.totals
        assert "total_errors" in result.totals
        assert "total_did_failures" in result.totals

    def test_vs_previous_period_keys(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=14)
        assert "prev_total_files" in result.vs_previous_period
        assert "prev_total_errors" in result.vs_previous_period
        assert "file_change_pct" in result.vs_previous_period
        assert "error_change_pct" in result.vs_previous_period

    def test_job_filter_stored(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=7, job_filter="Ocwen")
        assert result.job_filter == "Ocwen"

    def test_no_staleness_warning_when_none(self, mock_log_analytics):
        mock_log_analytics.check_staleness.return_value = None
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=7)
        assert result.staleness_warning is None

    def test_staleness_warning_propagated(self, mock_log_analytics):
        mock_log_analytics.check_staleness.return_value = {"warning": "Stale data"}
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=7)
        assert result.staleness_warning == "Stale data"

    def test_to_dict_returns_valid_dict(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        result = analyzer.analyze(days=7)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "days" in d
        assert "totals" in d


class TestTrendAnalyzerHelpers:
    def test_build_day_list_fills_gaps(self, mock_log_analytics):
        analyzer = TrendAnalyzer(mock_log_analytics)
        start = date(2025, 2, 1)
        end = date(2025, 2, 5)
        # Only provide data for 2 of 5 days
        data = {
            "2025-02-01": {"total_files": 10, "total_errors": 1, "did_failures": 0, "job_runs": 5},
            "2025-02-03": {"total_files": 8, "total_errors": 0, "did_failures": 0, "job_runs": 3},
        }
        result = analyzer._build_day_list(start, end, data)
        assert len(result) == 5
        assert result[0].total_files == 10
        assert result[1].total_files == 0  # gap filled with zeros
        assert result[2].total_files == 8

    def test_add_trend_indicators(self, mock_log_analytics):
        days = [
            TrendDay(date="2025-02-01", total_files=10, total_errors=2),
            TrendDay(date="2025-02-02", total_files=15, total_errors=2),
            TrendDay(date="2025-02-03", total_files=12, total_errors=5),
        ]
        TrendAnalyzer._add_trend_indicators(days)
        assert days[0].trend_files == "→"  # first day unchanged
        assert days[1].trend_files == "↑"  # 15 > 10
        assert days[1].trend_errors == "→"  # 2 == 2
        assert days[2].trend_files == "↓"  # 12 < 15
        assert days[2].trend_errors == "↑"  # 5 > 2


class TestTrendAnalyzerEmptyDB:
    def test_empty_db_returns_zero_totals(self, empty_db):
        from tests.analysis.conftest import _NoCloseConnection
        analytics = MagicMock()
        wrapped = _NoCloseConnection(empty_db)
        analytics._get_conn.return_value = wrapped
        analytics.check_staleness.return_value = None

        analyzer = TrendAnalyzer(analytics)
        result = analyzer.analyze(days=7)
        assert result.totals["total_files"] == 0
        assert result.totals["total_errors"] == 0
        assert len(result.days) == 7
