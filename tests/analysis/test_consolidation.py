"""Tests for backend.analysis.consolidation — 16 tests for ConsolidationAnalyzer."""

import pytest
from unittest.mock import MagicMock

from backend.analysis.consolidation import ConsolidationAnalyzer
from backend.analysis.models import (
    ConsolidationCandidate,
    ConsolidationGroup,
    ConsolidationReport,
)


class TestConsolidationAnalyzerInit:
    def test_init_stores_parser(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        assert analyzer._parser is mock_parser

    def test_init_deal_repo_optional(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        assert analyzer._deal_repo is None

    def test_init_with_deal_repo(self, mock_parser, mock_deal_repo):
        analyzer = ConsolidationAnalyzer(mock_parser, mock_deal_repo)
        assert analyzer._deal_repo is mock_deal_repo


class TestConsolidationAnalyzerAnalyze:
    def test_returns_consolidation_report(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        assert isinstance(result, ConsolidationReport)

    def test_xml_type_stored(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze(xml_type="email")
        assert result.xml_type_analyzed == "email"

    def test_groups_have_two_or_more_members(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        for group in result.groups:
            assert len(group.jobs) >= 2

    def test_total_groups_matches_groups_list(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        assert result.total_groups == len(result.groups)

    def test_total_jobs_affected_sum(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        expected = sum(len(g.jobs) for g in result.groups)
        assert result.total_jobs_affected == expected

    def test_groups_contain_consolidation_candidates(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        for group in result.groups:
            for job in group.jobs:
                assert isinstance(job, ConsolidationCandidate)

    def test_group_has_shared_config(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        for group in result.groups:
            assert group.shared_mailbox != ""
            assert group.shared_parser != ""

    def test_merge_recommendation_valid(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        valid_recommendations = {"safe", "review", "risky"}
        for group in result.groups:
            assert group.merge_recommendation in valid_recommendations

    def test_to_dict_returns_valid_dict(self, mock_parser):
        analyzer = ConsolidationAnalyzer(mock_parser)
        result = analyzer.analyze()
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "groups" in d
        assert "total_groups" in d


class TestConsolidationAnalyzerWithDealRepo:
    def test_did_counts_populated(self, mock_parser, mock_deal_repo):
        analyzer = ConsolidationAnalyzer(mock_parser, mock_deal_repo)
        result = analyzer.analyze()
        # With deal_repo present, candidates that have servicer_ids
        # will have their did_count looked up
        for group in result.groups:
            for job in group.jobs:
                # did_count is always >= 0 (int)
                assert isinstance(job.did_count, int)
                assert job.did_count >= 0

    def test_total_dids_affected_calculated(self, mock_parser, mock_deal_repo):
        analyzer = ConsolidationAnalyzer(mock_parser, mock_deal_repo)
        result = analyzer.analyze()
        expected = sum(g.total_dids_affected for g in result.groups)
        assert result.total_dids_affected == expected


class TestConsolidationAnalyzerEmptyParser:
    def test_empty_jobs_returns_empty_report(self):
        parser = MagicMock()
        parser.get_all_jobs.return_value = []
        analyzer = ConsolidationAnalyzer(parser)
        result = analyzer.analyze()
        assert result.total_groups == 0
        assert result.groups == []

    def test_single_job_no_groups(self):
        parser = MagicMock()
        job = MagicMock()
        job.name = "OnlyJob"
        job.mailbox = "inbox@bank.com"
        job.parsers = [{"type": "csv"}]
        job.templates = {"default": "Template1"}
        job.xml_type = "email"
        job.type = "email"
        parser.get_all_jobs.return_value = [job]
        analyzer = ConsolidationAnalyzer(parser)
        result = analyzer.analyze()
        assert result.total_groups == 0


class TestConsolidationSignatureExtraction:
    def test_signature_groups_same_mailbox_parser_template(self):
        """Two jobs with identical signatures should be grouped."""
        parser = MagicMock()
        job1 = MagicMock()
        job1.name = "Job1"
        job1.mailbox = "shared@bank.com"
        job1.parsers = [{"type": "csv"}]
        job1.templates = {"default": "TemplateA"}
        job1.xml_type = "email"
        job1.type = "email"
        job1.servicer_id = "100"
        job1.sender_filter = None
        job1.subject_filter = None
        job1.attachment_filter = None
        job1.queue_one_file = None
        job1.day_adjust = None

        job2 = MagicMock()
        job2.name = "Job2"
        job2.mailbox = "shared@bank.com"
        job2.parsers = [{"type": "csv"}]
        job2.templates = {"default": "TemplateA"}
        job2.xml_type = "email"
        job2.type = "email"
        job2.servicer_id = "101"
        job2.sender_filter = None
        job2.subject_filter = None
        job2.attachment_filter = None
        job2.queue_one_file = None
        job2.day_adjust = None

        parser.get_all_jobs.return_value = [job1, job2]
        analyzer = ConsolidationAnalyzer(parser)
        result = analyzer.analyze()
        assert result.total_groups == 1
        assert len(result.groups[0].jobs) == 2
