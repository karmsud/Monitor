"""Tests for Phase 2 CLI command handlers."""
import argparse
import os
import shutil

import pytest
from unittest.mock import MagicMock, patch

from cli.main import (
    cmd_clone_apply,
    cmd_clone_prepare,
    cmd_create_job,
    cmd_edit_job,
    cmd_template_inventory,
    cmd_deal_lookup,
    cmd_coverage_gaps,
    cmd_orphan_detection,
    cmd_collision_detection,
    cmd_xml_diff,
    cmd_rollback_xml,
)


def _ns(**kwargs):
    """Build an argparse.Namespace from keyword arguments."""
    return argparse.Namespace(**kwargs)


class TestCmdCreateJob:

    def test_create_job_success(self, tmp_settings_path):
        args = _ns(
            template_job="TestJob_Alpha",
            name="NewCLIJob",
            overrides=None,
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_create_job(args)
        assert response.success is True
        assert response.data["operation"] == "create"

    def test_create_job_template_not_found(self, tmp_settings_path):
        args = _ns(
            template_job="NonExistent_XYZ",
            name="NewJob",
            overrides=None,
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_create_job(args)
        assert response.success is False


class TestCmdEditJob:

    def test_edit_job_success(self, tmp_settings_path):
        args = _ns(
            job_name="TestJob_Alpha",
            field="servicer_id",
            value="999",
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_edit_job(args)
        assert response.success is True

    def test_edit_job_not_found(self, tmp_settings_path):
        args = _ns(
            job_name="NonExistent_XYZ",
            field="servicer_id",
            value="999",
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_edit_job(args)
        assert response.success is False


class TestCmdCloneJob:

    def test_clone_prepare_success(self, tmp_settings_path):
        args = _ns(
            source_servicer_id=150,
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_clone_prepare(args)
        assert response.success is True
        assert response.data["source_job_name"] == "TestJob_Alpha"
        assert response.data["assigned_servicer_id"] == 151

    def test_clone_apply_success(self, tmp_settings_path):
        args = _ns(
            source_servicer_id=150,
            clone_job_name="TestJob_Alpha_151",
            assigned_servicer_id=151,
            overrides_json='{"Filters/From":"clone@example.com"}',
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
            cache_db_path=None,
            xml_type="email",
        )
        response = cmd_clone_apply(args)
        assert response.success is True
        assert response.data["operation"] == "clone"



class TestCmdTemplateInventory:

    def test_template_inventory(self, email_fixture):
        args = _ns(
            filter=None,
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
        )
        response = cmd_template_inventory(args)
        assert response.success is True
        assert isinstance(response.data["templates"], list)

    def test_template_inventory_filter(self, email_fixture):
        args = _ns(
            filter="Conditional",
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
        )
        response = cmd_template_inventory(args)
        assert response.success is True


class TestCmdCoverageGaps:

    @patch("cli.main.DealRepository")
    def test_coverage_gaps_single(self, MockRepo, email_fixture):
        mock_repo = MagicMock()
        mock_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": "TEST", "CompanyID": 150}
        ]
        MockRepo.return_value = mock_repo
        args = _ns(
            servicer_id="150",
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
            db_mode="mysql",
            secrets_path=None,
        )
        response = cmd_coverage_gaps(args)
        assert response.success is True

    @patch("cli.main.DealRepository")
    def test_coverage_gaps_all(self, MockRepo, email_fixture):
        mock_repo = MagicMock()
        mock_repo.get_deals_by_company.return_value = []
        MockRepo.return_value = mock_repo
        args = _ns(
            servicer_id="all",
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
            db_mode="mysql",
            secrets_path=None,
        )
        response = cmd_coverage_gaps(args)
        assert response.success is True


class TestCmdOrphanDetection:

    @patch("cli.main.DealRepository")
    def test_orphan_detection(self, MockRepo, email_fixture):
        mock_repo = MagicMock()
        mock_repo.get_all_servicer_ids.return_value = {150, 200}
        mock_repo.get_deals_by_company.return_value = [{"DID": 1}]
        MockRepo.return_value = mock_repo
        args = _ns(
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
            db_mode="mysql",
            secrets_path=None,
        )
        response = cmd_orphan_detection(args)
        assert response.success is True


class TestCmdCollisionDetection:

    @patch("cli.main.DealRepository")
    def test_collision_detection(self, MockRepo, email_fixture):
        mock_repo = MagicMock()
        mock_repo.get_companies_by_import_did.return_value = [150]
        MockRepo.return_value = mock_repo
        args = _ns(
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
            db_mode="mysql",
            secrets_path=None,
        )
        response = cmd_collision_detection(args)
        assert response.success is True


class TestCmdDealLookup:

    @patch("cli.main._xml_index_from_args")
    @patch("cli.main.DealRepository")
    def test_deal_lookup_filters_json(self, MockRepo, mock_xml_index_from_args, email_fixture):
        mock_repo = MagicMock()
        mock_repo.search_deals_by_filters.return_value = [
            {"DID": "FREMF 2026-KF169", "ImportDID": "KF169", "CompanyID": 569}
        ]
        MockRepo.return_value = mock_repo

        mock_index = MagicMock()
        mock_index.find_jobs_by_servicer_ids.return_value = []
        mock_xml_index_from_args.return_value = mock_index

        args = _ns(
            query="keyword:KF169; company:569",
            filters_json='[{"type":"keyword","value":"KF169"},{"type":"company","value":"569"}]',
            lookup_type="auto",
            xml_type="all",
            settings_path=email_fixture,
            sftp_settings_path=None,
            db_mode="mysql",
            secrets_path=None,
            mssql_server=None,
            mssql_database=None,
            cache_db_path=None,
        )

        response = cmd_deal_lookup(args)

        assert response.success is True
        mock_repo.search_deals_by_filters.assert_called_once_with([
            {"type": "keyword", "value": "KF169"},
            {"type": "company", "value": "569"},
        ])
        assert response.data["deal_count"] == 1
        assert response.data["filters"] == [
            {"type": "keyword", "value": "KF169"},
            {"type": "company", "value": "569"},
        ]

    def test_deal_lookup_invalid_filters_json(self, email_fixture):
        args = _ns(
            query="keyword:KF169",
            filters_json='{"bad": true}',
            lookup_type="keyword",
            xml_type="all",
            settings_path=email_fixture,
            sftp_settings_path=None,
            db_mode="mysql",
            secrets_path=None,
            mssql_server=None,
            mssql_database=None,
            cache_db_path=None,
        )

        response = cmd_deal_lookup(args)

        assert response.success is False
        assert any("filters-json" in error for error in response.errors)


class TestCmdXmlDiff:

    def test_xml_diff_with_backup(self, tmp_settings_path, tmp_backup_path):
        args = _ns(
            backup_file=tmp_backup_path,
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_xml_diff(args)
        assert response.success is True

    def test_xml_diff_no_backups(self, tmp_settings_path):
        args = _ns(
            backup_file=None,
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_xml_diff(args)
        # May succeed with "no backups found" or fail gracefully
        assert isinstance(response.success, bool)


class TestCmdRollbackXml:

    def test_rollback_xml(self, tmp_settings_path, tmp_backup_path):
        args = _ns(
            backup_file=tmp_backup_path,
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_rollback_xml(args)
        assert response.success is True

    def test_rollback_xml_not_found(self, tmp_settings_path):
        args = _ns(
            backup_file="totally_nonexistent_file.xml",
            xml_type="email",
            settings_path=tmp_settings_path,
            sftp_settings_path=None,
        )
        response = cmd_rollback_xml(args)
        assert response.success is False


class TestAllCommandsReturnJson:

    def test_all_commands_return_cli_response(self, tmp_settings_path, tmp_backup_path):
        """All Phase 2 commands should return a CliResponse with success field."""
        from backend.common.models import CliResponse

        commands_and_args = [
            (cmd_create_job, _ns(template_job="TestJob_Alpha", name="JsonTest", overrides=None,
                                 xml_type="email", settings_path=tmp_settings_path, sftp_settings_path=None)),
            (cmd_template_inventory, _ns(filter=None, xml_type="email",
                                          settings_path=tmp_settings_path, sftp_settings_path=None)),
            (cmd_xml_diff, _ns(backup_file=tmp_backup_path, xml_type="email",
                               settings_path=tmp_settings_path, sftp_settings_path=None)),
        ]
        for cmd_fn, args in commands_and_args:
            result = cmd_fn(args)
            assert isinstance(result, CliResponse), f"{cmd_fn.__name__} should return CliResponse"
            assert isinstance(result.success, bool)
