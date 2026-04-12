"""Tests for backend.analysis.health — 18 tests for HealthChecker."""

import pytest
from unittest.mock import MagicMock

from backend.analysis.health import (
    HealthChecker,
    SECTION_WEIGHTS,
    HEALTHY_THRESHOLD,
    ATTENTION_THRESHOLD,
)
from backend.analysis.models import HealthSection, HealthReport


class TestHealthCheckerInit:
    def test_init_all_none(self):
        checker = HealthChecker()
        assert checker._parser is None
        assert checker._deal_repo is None
        assert checker._analytics is None

    def test_init_stores_all_deps(self, mock_parser, mock_deal_repo, mock_log_analytics):
        benchmarker = MagicMock()
        checker = HealthChecker(
            parser=mock_parser,
            deal_repo=mock_deal_repo,
            analytics=mock_log_analytics,
            benchmarker=benchmarker,
        )
        assert checker._parser is mock_parser
        assert checker._analytics is mock_log_analytics
        assert checker._benchmarker is benchmarker


class TestHealthCheckerCheck:
    def test_returns_health_report(self):
        checker = HealthChecker()
        result = checker.check()
        assert isinstance(result, HealthReport)

    def test_report_has_9_sections(self):
        checker = HealthChecker()
        result = checker.check()
        assert len(result.sections) == 9

    def test_overall_status_is_valid(self):
        checker = HealthChecker()
        result = checker.check()
        assert result.overall_status in ("Healthy", "Attention Needed", "Action Required")

    def test_generated_at_populated(self):
        checker = HealthChecker()
        result = checker.check()
        assert result.generated_at != ""

    def test_xml_type_default_all(self):
        checker = HealthChecker()
        result = checker.check()
        assert result.xml_type == "all"

    def test_xml_type_custom(self):
        checker = HealthChecker()
        result = checker.check(xml_type="email")
        assert result.xml_type == "email"

    def test_to_dict_returns_valid_dict(self):
        checker = HealthChecker()
        result = checker.check()
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "sections" in d
        assert "overall_score" in d
        assert "overall_status" in d


class TestHealthCheckerUnavailableSections:
    def test_no_parser_yields_unavailable_xml_validation(self):
        checker = HealthChecker()
        result = checker.check()
        xml_section = next(s for s in result.sections if s.name == "XML Validation")
        assert xml_section.status == "warning"
        assert xml_section.score == 50.0

    def test_no_analytics_yields_unavailable_log_freshness(self):
        checker = HealthChecker()
        result = checker.check()
        log_section = next(s for s in result.sections if s.name == "Log Freshness")
        assert log_section.status == "warning"
        assert log_section.score == 50.0

    def test_no_benchmarker_yields_unavailable_performance(self):
        checker = HealthChecker()
        result = checker.check()
        perf_section = next(s for s in result.sections if s.name == "Job Performance")
        assert perf_section.status == "warning"
        assert perf_section.score == 50.0


class TestHealthCheckerWithDeps:
    def test_parser_validation_errors_reduce_score(self, mock_parser):
        validation_result = MagicMock()
        validation_result.errors = ["Error1", "Error2"]
        validation_result.warnings = ["Warn1"]
        mock_parser.validate.return_value = validation_result

        checker = HealthChecker(parser=mock_parser)
        result = checker.check()
        xml_section = next(s for s in result.sections if s.name == "XML Validation")
        # 100 - (2*20) - (1*5) = 55
        assert xml_section.score == 55.0
        assert xml_section.status == "fail"  # < 70

    def test_benchmarker_integrated(self, mock_parser):
        benchmarker = MagicMock()
        bench_result = MagicMock()
        bench_result.avg_success_rate = 92.0
        bench_result.critical_count = 0
        bench_result.healthy_count = 8
        bench_result.warning_count = 2
        bench_result.unknown_count = 0
        benchmarker.benchmark.return_value = bench_result

        checker = HealthChecker(parser=mock_parser, benchmarker=benchmarker)
        result = checker.check()
        perf_section = next(s for s in result.sections if s.name == "Job Performance")
        assert perf_section.score == 92.0
        assert perf_section.status == "pass"

    def test_analytics_staleness_none_gives_pass(self, mock_log_analytics):
        mock_log_analytics.check_staleness.return_value = None
        checker = HealthChecker(analytics=mock_log_analytics)
        result = checker.check()
        log_section = next(s for s in result.sections if s.name == "Log Freshness")
        assert log_section.status == "pass"
        assert log_section.score == 100.0

    def test_analytics_staleness_warning_reduces_score(self, mock_log_analytics):
        mock_log_analytics.check_staleness.return_value = {"warning": "Data is 72 hours old"}
        checker = HealthChecker(analytics=mock_log_analytics)
        result = checker.check()
        log_section = next(s for s in result.sections if s.name == "Log Freshness")
        # 72 hours > 48, so score = 0.0
        assert log_section.score == 0.0
        assert log_section.status == "fail"


class TestHealthCheckerThresholds:
    def test_healthy_threshold(self):
        assert HEALTHY_THRESHOLD == 90.0

    def test_attention_threshold(self):
        assert ATTENTION_THRESHOLD == 70.0


class TestHealthCheckerHelpers:
    def test_score_to_status_pass(self):
        assert HealthChecker._score_to_status(95.0) == "pass"

    def test_score_to_status_warning(self):
        assert HealthChecker._score_to_status(75.0) == "warning"

    def test_score_to_status_fail(self):
        assert HealthChecker._score_to_status(60.0) == "fail"

    def test_score_to_status_boundary_90(self):
        assert HealthChecker._score_to_status(90.0) == "pass"

    def test_score_to_status_boundary_70(self):
        assert HealthChecker._score_to_status(70.0) == "warning"


class TestHealthCheckerWeights:
    def test_weights_sum_to_one(self):
        total = sum(SECTION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_section_names_present(self):
        expected = {
            "xml_validation", "coverage_rate", "orphan_dids",
            "importdid_collisions", "template_distribution",
            "log_freshness", "did_failure_rate", "job_performance",
            "recent_errors",
        }
        assert set(SECTION_WEIGHTS.keys()) == expected
