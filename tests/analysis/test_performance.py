"""Tests for backend.analysis.performance — 18 tests for PerformanceBenchmarker."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta

from backend.analysis.performance import (
    PerformanceBenchmarker,
    HEALTHY_THRESHOLD,
    WARNING_THRESHOLD,
)
from backend.analysis.models import PerformanceEntry, PerformanceSummary


class TestPerformanceBenchmarkerInit:
    def test_init_stores_analytics_and_parser(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        assert benchmarker._analytics is mock_log_analytics
        assert benchmarker._parser is mock_parser

    def test_init_parser_optional(self, mock_log_analytics):
        benchmarker = PerformanceBenchmarker(mock_log_analytics)
        assert benchmarker._parser is None


class TestPerformanceBenchmarkerBenchmark:
    def test_returns_performance_summary(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        assert isinstance(result, PerformanceSummary)

    def test_entries_are_performance_entries(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        for entry in result.entries:
            assert isinstance(entry, PerformanceEntry)

    def test_default_sort_by_success_rate(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        assert result.sort_key == "success_rate"

    def test_custom_sort_key(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(sort_by="total_files", days=30)
        assert result.sort_key == "total_files"

    def test_period_days_stored(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=7)
        assert result.period_days == 7

    def test_top_n_limits_entries(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(top_n=3, days=30)
        assert len(result.entries) <= 3

    def test_entries_have_ranks(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        if result.entries:
            ranks = [e.rank for e in result.entries]
            assert ranks == sorted(ranks)
            assert ranks[0] >= 1

    def test_status_counts_sum_to_total(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        total = result.healthy_count + result.warning_count + result.critical_count + result.unknown_count
        assert total == result.total_jobs

    def test_staleness_warning_none(self, mock_log_analytics, mock_parser):
        mock_log_analytics.check_staleness.return_value = None
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        assert result.staleness_warning is None

    def test_staleness_warning_propagated(self, mock_log_analytics, mock_parser):
        mock_log_analytics.check_staleness.return_value = {"warning": "Data is 48 hours old"}
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        assert result.staleness_warning == "Data is 48 hours old"

    def test_to_dict_returns_valid_dict(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "entries" in d
        assert "total_jobs" in d

    def test_job_type_email_from_parser(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        ocwen_entries = [e for e in result.entries if e.job_name == "Ocwen"]
        if ocwen_entries:
            assert ocwen_entries[0].job_type == "email"


class TestPerformanceBenchmarkerNoJobs:
    def test_no_jobs_returns_empty_summary(self):
        analytics = MagicMock()
        analytics._get_conn.return_value = MagicMock()
        # Make _get_conn().execute().fetchall() return empty
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        analytics._get_conn.return_value = mock_conn
        analytics.check_staleness.return_value = None

        benchmarker = PerformanceBenchmarker(analytics, parser=None)
        result = benchmarker.benchmark(days=30)
        assert result.total_jobs == 0
        assert result.entries == []


class TestPerformanceThresholds:
    def test_healthy_threshold_value(self):
        assert HEALTHY_THRESHOLD == 95.0

    def test_warning_threshold_value(self):
        assert WARNING_THRESHOLD == 80.0


class TestPerformanceBenchmarkerEmptyDB:
    def test_empty_db_with_parser_jobs(self, empty_db, mock_parser):
        from tests.analysis.conftest import _NoCloseConnection
        analytics = MagicMock()
        wrapped = _NoCloseConnection(empty_db)
        analytics._get_conn.return_value = wrapped
        analytics.check_staleness.return_value = None

        benchmarker = PerformanceBenchmarker(analytics, mock_parser)
        result = benchmarker.benchmark(days=30)
        # Jobs from parser are included even with no DB data
        assert result.total_jobs > 0
        # All jobs should be "unknown" status since no events exist
        for entry in result.entries:
            assert entry.status == "unknown"

    def test_ascending_false_reverses_order(self, mock_log_analytics, mock_parser):
        benchmarker = PerformanceBenchmarker(mock_log_analytics, mock_parser)
        result_asc = benchmarker.benchmark(sort_by="success_rate", ascending=True, days=30)
        result_desc = benchmarker.benchmark(sort_by="success_rate", ascending=False, days=30)
        if len(result_asc.entries) >= 2:
            assert result_asc.entries[0].success_rate <= result_asc.entries[-1].success_rate
            assert result_desc.entries[0].success_rate >= result_desc.entries[-1].success_rate
