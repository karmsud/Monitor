"""Tests for backend.analysis.impact — 22 tests for ImpactSimulator."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from backend.analysis.impact import ImpactSimulator
from backend.analysis.models import ChangeSpec, AffectedEntity, ImpactReport


class TestImpactSimulatorInit:
    def test_init_stores_all_deps(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        assert sim._parser is mock_parser
        assert sim._deal_repo is mock_deal_repo
        assert sim._analytics is mock_log_analytics

    def test_init_optional_deps(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        assert sim._deal_repo is None
        assert sim._analytics is None


class TestImpactSimulatorUnknownType:
    def test_unknown_change_type_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="explode_everything")
        with pytest.raises(ValueError, match="Unknown change_type"):
            sim.simulate(change)


class TestImpactSimulatorDeleteJob:
    def test_delete_job_returns_impact_report(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="Ocwen")
        result = sim.simulate(change)
        assert isinstance(result, ImpactReport)
        assert result.change is change

    def test_delete_job_missing_target_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="delete_job")
        with pytest.raises(ValueError, match="target_job is required"):
            sim.simulate(change)

    def test_delete_job_not_found_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="delete_job", target_job="NonExistentJob")
        with pytest.raises(ValueError, match="not found"):
            sim.simulate(change)

    def test_delete_job_finds_case_insensitive(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="ocwen")
        result = sim.simulate(change)
        assert isinstance(result, ImpactReport)

    def test_delete_job_affected_entities_populated(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="Ocwen")
        result = sim.simulate(change)
        # Ocwen has servicer_id="100", deal_repo returns 1 DID for company 100
        assert len(result.affected) >= 1

    def test_delete_job_risk_level_set(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="Ocwen")
        result = sim.simulate(change)
        assert result.risk_level in ("low", "medium", "high")

    def test_delete_job_recommendation_populated(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="Ocwen")
        result = sim.simulate(change)
        assert len(result.recommendation) > 0

    def test_delete_job_no_servicer_id(self, mock_parser, mock_deal_repo, mock_log_analytics):
        """Chase (i=8) has servicer_id=None — should produce medium severity entity."""
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="Chase")
        result = sim.simulate(change)
        assert isinstance(result, ImpactReport)
        # Should have a "job" entity about process/shelf-level
        job_entities = [a for a in result.affected if a.entity_type == "job"]
        assert len(job_entities) >= 1


class TestImpactSimulatorRenameDID:
    def test_rename_did_returns_impact_report(self, mock_parser, mock_deal_repo):
        sim = ImpactSimulator(mock_parser, mock_deal_repo)
        change = ChangeSpec(change_type="rename_did", target_did="IMP000", new_value="IMP_NEW")
        result = sim.simulate(change)
        assert isinstance(result, ImpactReport)

    def test_rename_did_missing_target_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="rename_did", new_value="IMP_NEW")
        with pytest.raises(ValueError, match="target_did and new_value are required"):
            sim.simulate(change)

    def test_rename_did_missing_new_value_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="rename_did", target_did="IMP000")
        with pytest.raises(ValueError, match="target_did and new_value are required"):
            sim.simulate(change)

    def test_rename_did_coverage_before_matches(self, mock_parser, mock_deal_repo):
        sim = ImpactSimulator(mock_parser, mock_deal_repo)
        change = ChangeSpec(change_type="rename_did", target_did="IMP000", new_value="IMP_NEW")
        result = sim.simulate(change)
        # IMP000 returns 1 mapping from mock_deal_repo
        assert result.coverage_before == 1

    def test_rename_did_no_collision(self, mock_parser, mock_deal_repo):
        sim = ImpactSimulator(mock_parser, mock_deal_repo)
        change = ChangeSpec(change_type="rename_did", target_did="IMP000", new_value="IMP_UNIQUE")
        result = sim.simulate(change)
        # No collision expected since IMP_UNIQUE doesn't exist
        high_severity = [a for a in result.affected if a.severity == "high"]
        assert len(high_severity) == 0
        assert result.risk_level == "low"


class TestImpactSimulatorChangeFilter:
    def test_change_filter_returns_impact_report(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="change_filter", target_job="Ocwen", new_value="*new_filter*")
        result = sim.simulate(change)
        assert isinstance(result, ImpactReport)

    def test_change_filter_missing_target_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="change_filter")
        with pytest.raises(ValueError, match="target_job is required"):
            sim.simulate(change)

    def test_change_filter_job_not_found_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="change_filter", target_job="FakeJob")
        with pytest.raises(ValueError, match="not found"):
            sim.simulate(change)

    def test_change_filter_affected_includes_job(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="change_filter", target_job="Ocwen", new_value="*new*")
        result = sim.simulate(change)
        job_entities = [a for a in result.affected if a.entity_type == "job"]
        assert len(job_entities) >= 1


class TestImpactSimulatorMoveServicer:
    def test_move_servicer_returns_impact_report(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="move_servicer", target_job="Ocwen",
                            target_company_id=100, new_value="PHH")
        result = sim.simulate(change)
        assert isinstance(result, ImpactReport)

    def test_move_servicer_missing_fields_raises(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        change = ChangeSpec(change_type="move_servicer", target_job="Ocwen")
        with pytest.raises(ValueError, match="target_job and target_company_id required"):
            sim.simulate(change)


class TestImpactSimulatorHelpers:
    def test_calculate_risk_high(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        assert sim._calculate_risk(high_severity_count=2, recent_activity=True, coverage_before=5) == "high"

    def test_calculate_risk_low(self, mock_parser):
        sim = ImpactSimulator(mock_parser)
        assert sim._calculate_risk(high_severity_count=0, recent_activity=False, coverage_before=0) == "low"

    def test_to_dict_returns_valid_dict(self, mock_parser, mock_deal_repo, mock_log_analytics):
        sim = ImpactSimulator(mock_parser, mock_deal_repo, mock_log_analytics)
        change = ChangeSpec(change_type="delete_job", target_job="Ocwen")
        result = sim.simulate(change)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "change" in d
        assert "affected" in d
        assert "risk_level" in d
