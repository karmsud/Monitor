"""Tests for Phase 4 CLI command handlers — 10 tests."""

import argparse
import pytest
from unittest.mock import patch, MagicMock

from cli.main import (
    cmd_log_trends,
    cmd_log_performance,
    cmd_analyze_consolidation,
    cmd_analyze_impact,
    cmd_analyze_health,
)
from backend.common.models import CliResponse


def _make_args(**kwargs):
    """Create a minimal argparse.Namespace with given attrs."""
    return argparse.Namespace(**kwargs)


class TestCmdLogTrends:
    @patch("backend.analysis.trends.TrendAnalyzer", autospec=True)
    @patch("backend.logs.analytics.LogAnalytics", autospec=True)
    def test_success(self, MockLogAnalytics, MockAnalyzer):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"days": [], "totals": {}}
        MockAnalyzer.return_value.analyze.return_value = mock_result

        args = _make_args(db_path=":memory:", days=7, job=None)
        resp = cmd_log_trends(args)
        assert isinstance(resp, CliResponse)
        assert resp.success is True
        assert resp.command == "log_trends"
        assert resp.data == {"days": [], "totals": {}}

    @patch("backend.analysis.trends.TrendAnalyzer", autospec=True)
    @patch("backend.logs.analytics.LogAnalytics", autospec=True)
    def test_value_error(self, MockLogAnalytics, MockAnalyzer):
        MockAnalyzer.return_value.analyze.side_effect = ValueError("days must be 1-365")
        args = _make_args(db_path=":memory:", days=0, job=None)
        resp = cmd_log_trends(args)
        assert resp.success is False
        assert len(resp.errors) >= 1


class TestCmdLogPerformance:
    @patch("backend.analysis.performance.PerformanceBenchmarker", autospec=True)
    @patch("backend.logs.analytics.LogAnalytics", autospec=True)
    def test_success(self, MockLogAnalytics, MockBenchmarker):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"entries": [], "total_jobs": 0}
        MockBenchmarker.return_value.benchmark.return_value = mock_result

        args = _make_args(db_path=":memory:", sort="success_rate", ascending=True,
                          top=None, days=30, settings_path=None)
        resp = cmd_log_performance(args)
        assert isinstance(resp, CliResponse)
        assert resp.success is True
        assert resp.command == "log_performance"

    @patch("backend.analysis.performance.PerformanceBenchmarker", autospec=True)
    @patch("backend.logs.analytics.LogAnalytics", autospec=True)
    def test_file_not_found(self, MockLogAnalytics, MockBenchmarker):
        MockLogAnalytics.side_effect = FileNotFoundError("DB not found")
        args = _make_args(db_path="/bad/path.db", sort="success_rate", ascending=True,
                          top=None, days=30, settings_path=None)
        resp = cmd_log_performance(args)
        assert resp.success is False


class TestCmdAnalyzeConsolidation:
    @patch("backend.analysis.consolidation.ConsolidationAnalyzer", autospec=True)
    @patch("cli.main.SettingsXmlParser", autospec=True)
    def test_success(self, MockParser, MockAnalyzer):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"groups": [], "total_groups": 0}
        MockAnalyzer.return_value.analyze.return_value = mock_result

        args = _make_args(settings_path="Settings.xml", db_mode=None, secrets_path=None, type="all")
        resp = cmd_analyze_consolidation(args)
        assert isinstance(resp, CliResponse)
        assert resp.success is True
        assert resp.command == "analyze_consolidation"

    @patch("cli.main.SettingsXmlParser", autospec=True)
    def test_settings_not_found(self, MockParser):
        MockParser.side_effect = FileNotFoundError("Settings.xml not found")
        args = _make_args(settings_path="/bad/Settings.xml", db_mode=None, secrets_path=None, type="all")
        resp = cmd_analyze_consolidation(args)
        assert resp.success is False


class TestCmdAnalyzeImpact:
    @patch("backend.analysis.impact.ImpactSimulator", autospec=True)
    @patch("cli.main.SettingsXmlParser", autospec=True)
    def test_success(self, MockParser, MockSimulator):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"change": {}, "affected": [], "risk_level": "low"}
        MockSimulator.return_value.simulate.return_value = mock_result

        args = _make_args(
            settings_path="Settings.xml", change_type="delete_job",
            target_job="Ocwen", target_did=None, target_company_id=None,
            new_value=None, raw_description="", db_mode=None, secrets_path=None,
            db_path=None,
        )
        resp = cmd_analyze_impact(args)
        assert isinstance(resp, CliResponse)
        assert resp.success is True
        assert resp.command == "analyze_impact"

    @patch("backend.analysis.impact.ImpactSimulator", autospec=True)
    @patch("cli.main.SettingsXmlParser", autospec=True)
    def test_value_error_unknown_type(self, MockParser, MockSimulator):
        MockSimulator.return_value.simulate.side_effect = ValueError("Unknown change_type")
        args = _make_args(
            settings_path="Settings.xml", change_type="explode",
            target_job=None, target_did=None, target_company_id=None,
            new_value=None, raw_description="", db_mode=None, secrets_path=None,
            db_path=None,
        )
        resp = cmd_analyze_impact(args)
        assert resp.success is False


class TestCmdAnalyzeHealth:
    @patch("backend.analysis.health.HealthChecker", autospec=True)
    def test_success_minimal(self, MockChecker):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "sections": [], "overall_score": 50.0, "overall_status": "Attention Needed",
        }
        MockChecker.return_value.check.return_value = mock_result

        args = _make_args(settings_path=None, db_mode=None, secrets_path=None,
                          db_path=None, type="all")
        resp = cmd_analyze_health(args)
        assert isinstance(resp, CliResponse)
        assert resp.success is True
        assert resp.command == "analyze_health"
        assert resp.data["overall_status"] == "Attention Needed"

    @patch("backend.analysis.health.HealthChecker", autospec=True)
    def test_health_xml_type_passed(self, MockChecker):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "sections": [], "overall_score": 95.0, "overall_status": "Healthy",
        }
        MockChecker.return_value.check.return_value = mock_result

        args = _make_args(settings_path=None, db_mode=None, secrets_path=None,
                          db_path=None, type="email")
        resp = cmd_analyze_health(args)
        assert resp.success is True
        MockChecker.return_value.check.assert_called_once_with(xml_type="email")
