"""Regression tests for deterministic log search and linkage commands."""

import argparse
import json
from unittest.mock import MagicMock, patch


def _make_args(**kwargs):
    return argparse.Namespace(**kwargs)


class TestCmdLogSearchDeterministic:

    def test_details_mode_alias_returns_event_rows(self, log_db):
        from cli.main import cmd_log_search

        args = _make_args(
            db_path=log_db,
            query="",
            event_type=None,
            mode="details",
            job_name=None,
            filters=json.dumps({"event": "file_loaded"}),
            days=30,
            start_date=None,
            end_date=None,
            limit=25,
        )

        response = cmd_log_search(args)
        assert response.success is True
        assert response.command == "log_search"
        assert response.data["mode"] == "details"
        assert response.data["event_count"] >= 1
        assert all(event["event_type"] == "file_loaded" for event in response.data["events"])

        def test_parser_accepts_emails_mode(self):
            from cli.main import _build_parser

            parser = _build_parser()
            args = parser.parse_args([
                "log_search",
                "--mode", "emails",
                "--db-path", "frp_logs.db",
            ])

            assert args.mode == "emails"

    def test_filter_only_event_search(self, log_db):
        from cli.main import cmd_log_search

        args = _make_args(
            db_path=log_db,
            query="",
            event_type=None,
            mode="events",
            job_name=None,
            filters=json.dumps({"event": "file_loaded"}),
            days=30,
            start_date=None,
            end_date=None,
            limit=25,
        )

        response = cmd_log_search(args)
        assert response.success is True
        assert response.command == "log_search"
        assert response.data["mode"] == "events"
        assert response.data["event_count"] >= 1
        assert all(event["event_type"] == "file_loaded" for event in response.data["events"])

    def test_structured_event_search(self, log_db):
        from cli.main import cmd_log_search

        args = _make_args(
            db_path=log_db,
            query="report.xlsx",
            event_type=None,
            mode="events",
            job_name=None,
            filters=json.dumps({"event": "file_loaded"}),
            days=30,
            start_date=None,
            end_date=None,
            limit=25,
        )

        response = cmd_log_search(args)
        assert response.success is True
        assert response.command == "log_search"
        assert response.data["mode"] == "events"
        assert response.data["event_count"] >= 1
        assert all(event["event_type"] == "file_loaded" for event in response.data["events"])

    def test_summary_mode_with_structured_job_filter(self, log_db):
        from cli.main import cmd_log_search

        args = _make_args(
            db_path=log_db,
            query="TestJob",
            event_type=None,
            mode="summary",
            job_name="TestJob_Alpha",
            filters=None,
            days=30,
            start_date=None,
            end_date=None,
            limit=25,
        )

        response = cmd_log_search(args)
        assert response.success is True
        assert response.data["mode"] == "summary"
        assert response.data["job_count"] >= 1
        assert any(job["job_name"] == "TestJob_Alpha" for job in response.data["jobs"])

    def test_email_mode_groups_pipeline_rows_by_processing_boundary(self, log_db):
        from cli.main import cmd_log_search

        args = _make_args(
            db_path=log_db,
            query="",
            event_type=None,
            mode="emails",
            job_name=None,
            filters=json.dumps({"subject": "Monthly Report"}),
            days=30,
            start_date=None,
            end_date=None,
            limit=25,
        )

        response = cmd_log_search(args)
        assert response.success is True
        assert response.data["mode"] == "emails"
        assert response.data["email_count"] == 1
        assert response.data["event_count"] == 3
        assert response.data["email_events"][0]["pipeline_event_count"] == 3
        assert response.data["email_events"][0]["subject"] == "Monthly Report"

    def test_structured_job_filters_use_exact_job_name(self):
        from cli.main import cmd_log_search

        args = _make_args(
            db_path="frp_logs.db",
            query="",
            event_type=None,
            mode="emails",
            job_name=None,
            filters=json.dumps({"job": "TestJob_Alpha"}),
            days=30,
            start_date=None,
            end_date=None,
            limit=25,
        )

        with patch("cli.main.LogIndexer") as mock_indexer_class:
            mock_indexer = mock_indexer_class.return_value.__enter__.return_value
            mock_indexer.query_events.return_value = []

            response = cmd_log_search(args)

        assert response.success is True
        kwargs = mock_indexer.query_events.call_args.kwargs
        assert kwargs["job_name"] == "TestJob_Alpha"
        assert kwargs["job_name_like"] is None


class TestCmdLogLinkage:

    @patch("cli.main._ts_repo_from_args")
    @patch("cli.main._repo_from_args")
    @patch("cli.main._collect_staging_reference_jobs")
    def test_linkage_cross_references_jobs_deals_and_staging(
        self,
        mock_collect_jobs,
        mock_repo_from_args,
        mock_ts_repo_from_args,
        log_db,
    ):
        from cli.main import cmd_log_linkage

        mock_collect_jobs.return_value = ([{
            "job_name": "TestJob_Alpha",
            "xml_type": "email",
            "mailbox": "ops@example.com",
            "scrubber": "QueueCMBS",
            "servicer_id": 569,
        }], "xml")

        mock_repo = MagicMock()
        mock_repo.search_deals.return_value = [{"DID": "FREMF 2026-KF169", "ImportDID": "KF169", "CompanyID": 569}]
        mock_repo.get_deals_by_company.return_value = [{"DID": "FREMF 2026-KF169", "ImportDID": "KF169", "CompanyID": 569}]
        mock_repo_from_args.return_value = mock_repo

        mock_ts_repo = MagicMock()
        mock_ts_repo.advanced_search.side_effect = [
            [{
                "TemplateProcessID": 12345,
                "TemplateName": "QueueCMBS",
                "DID": "FREMF 2026-KF169",
                "ServicerID": 569,
                "Dt": "2026-03-10",
                "StartTime": "2026-03-10 08:00:00",
                "EndTime": "2026-03-10 08:01:00",
                "ResultCode": 0,
                "Comments": "Ok",
                "FilePath": "M:\\Deals\\KF169\\report.xlsx",
                "DataSource": "ops@example.com: Monthly report",
                "SourceProcess": "ActiveBatch",
            }],
            [],
            [],
        ]
        mock_ts_repo_from_args.return_value = mock_ts_repo

        args = _make_args(
            db_path=log_db,
            query="TestJob_Alpha",
            filters=None,
            days=30,
            start_date=None,
            end_date=None,
            limit=10,
            settings_path=None,
            sftp_settings_path=None,
            cache_db_path=None,
            xml_type="all",
            db_mode="mysql",
            secrets_path=None,
            mssql_server=None,
            mssql_database=None,
        )

        response = cmd_log_linkage(args)
        assert response.success is True
        assert response.command == "log_linkage"
        assert response.data["linked_job_count"] == 1
        assert response.data["linked_deal_count"] >= 1
        assert len(response.data["recent_staging"]) == 1
        assert response.data["recent_staging"][0]["TemplateProcessID"] == 12345