"""Phase 5 CLI command tests — all backend calls mocked.

Strategy: patch ``cli.main._ts_repo_from_args`` so it returns a pre-configured
``MagicMock`` that behaves like ``TemplateStagingRepository`` without touching
the database.  This works because ``_ts_repo_from_args`` is a module-level
function even though *it* does a lazy import internally.
"""
import json
from unittest.mock import patch, MagicMock
from io import StringIO

import pytest

# Patch target – module-level helper that builds the repo
_PATCH_TS_REPO = "cli.main._ts_repo_from_args"
_PATCH_DEAL_REPO = "cli.main._repo_from_args"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_mock_repo(**overrides):
    """Create a pre-configured mock TemplateStagingRepository."""
    repo = MagicMock()
    repo.get_recent_by_query.return_value = overrides.get("recent", {
        "scope": "TPMT_SPS", "total_runs": 5, "successes": 4, "failures": 1,
        "success_rate": 80.0, "runs": [],
    })
    repo.get_failure_summary.return_value = overrides.get("failures", {
        "total_failures": 3, "period_days": 30, "top_templates": [],
        "top_dids": [], "error_groups": [], "affected_servicers": [296], "failures": [],
    })
    repo.get_duration_stats.return_value = overrides.get("duration", {
        "period_days": 30,
        "templates": [{"template_name": "TPMT_SPS", "total_runs": 10,
                       "avg_seconds": 45.0, "min_seconds": 10.0, "max_seconds": 120.0}],
        "outliers": [],
    })
    repo.get_manual_queue_stats.return_value = overrides.get("manual", {
        "total_count": 100, "manual_count": 20, "automated_count": 80,
        "manual_percentage": 20.0, "top_manual_templates": [],
        "manual_operators": [], "period_days": 30,
    })
    repo.trace_by_filepath.return_value = overrides.get("trace", [{
        "file_path": "M:\\test.xlsx", "source_type": "email", "template_name": "TPMT_SPS",
    }])
    repo.search.return_value = overrides.get("search", [{
        "TemplateProcessID": 42, "TemplateName": "TPMT_SPS", "DID": "DEAL001", "ResultCode": 0,
    }])
    repo.advanced_search.return_value = overrides.get("advanced", [{
        "TemplateProcessID": 42,
        "TemplateName": "TPMT_SPS",
        "DID": "DEAL001",
        "ServicerID": 296,
        "FilePath": "M:\\Deals\\DEAL001.xlsx",
        "Dt": "2026-01-01",
        "ResultCode": 0,
        "DataSource": "mailbox@example.com: subject",
    }])
    repo.get_distinct_templates.return_value = overrides.get("distinct_templates", [
        {"TemplateName": "TPMT_SPS", "run_count": 4},
        {"TemplateName": "QueueCMBS", "run_count": 2},
    ])
    repo.get_recent_process_level_runs.return_value = overrides.get("process_runs", [
        {"TemplateProcessID": 77, "TemplateName": "QueueCMBS", "ServicerID": 296, "FilePath": "M:\\Queue\\a.xlsx", "Dt": "2026-01-01", "ResultCode": 0},
    ])
    repo.get_recent_filepath_samples.return_value = overrides.get("filepath_samples", [
        {"TemplateProcessID": 88, "TemplateName": "QueueCMBS", "ServicerID": 296, "FilePath": "M:\\Queue\\b.xlsx", "Dt": "2026-01-01", "ResultCode": 1, "DataSource": "SFTPMonitor: M:\\Queue"},
    ])
    repo.get_by_date_range.return_value = []
    repo.get_processing_for_servicer.return_value = {"runs": []}
    repo.get_pipeline_status.return_value = {
        "execution_layer": {"health_score": 100},
        "configuration_layer": {},
        "reference_layer": {},
        "gaps": [],
    }
    repo.close = MagicMock()
    return repo


def _make_mock_deal_repo(**overrides):
    repo = MagicMock()
    repo.get_deals_by_company.return_value = overrides.get("deals", [{
        "DID": "DEAL001",
        "ImportDID": "KEY001",
        "CompanyID": 296,
    }])
    repo.close = MagicMock()
    return repo


def _run_cli(*args):
    """Run the CLI main() with given args, capturing stdout as JSON."""
    from cli.main import main
    import sys

    old_argv = sys.argv
    sys.argv = ["frp"] + list(args)
    buf = StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main()
    except SystemExit:
        pass
    finally:
        sys.stdout = old_stdout
        sys.argv = old_argv

    output = buf.getvalue().strip()
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"raw": output}


# --------------------------------------------------------------------------- #
# template_status  (UC-01)
# --------------------------------------------------------------------------- #

class TestTemplateStatus:

    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "template_status",
            "--query", "TPMT_SPS",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.get_recent_by_query.assert_called_once()

    @patch(_PATCH_TS_REPO)
    def test_with_days(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "template_status",
            "--query", "296",
            "--days", "7",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        call_kwargs = repo.get_recent_by_query.call_args
        assert call_kwargs.kwargs.get("days") == 7 or call_kwargs[1].get("days") == 7


# --------------------------------------------------------------------------- #
# failure_analysis  (UC-03)
# --------------------------------------------------------------------------- #

class TestFailureAnalysis:

    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "failure_analysis",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.get_failure_summary.assert_called_once()

    @patch(_PATCH_TS_REPO)
    def test_with_template_filter(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "failure_analysis",
            "--template", "TPMT",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        call_kwargs = repo.get_failure_summary.call_args
        assert call_kwargs.kwargs.get("template") == "TPMT" or call_kwargs[1].get("template") == "TPMT"


# --------------------------------------------------------------------------- #
# processing_duration  (UC-06)
# --------------------------------------------------------------------------- #

class TestProcessingDuration:

    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "processing_duration",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.get_duration_stats.assert_called_once()


# --------------------------------------------------------------------------- #
# source_trace  (UC-04)
# --------------------------------------------------------------------------- #

class TestSourceTrace:

    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "source_trace",
            "--filepath", "test.xlsx",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.trace_by_filepath.assert_called_once_with(filepath_pattern="test.xlsx", limit=10)


# --------------------------------------------------------------------------- #
# manual_queue_report  (UC-05)
# --------------------------------------------------------------------------- #

class TestManualQueueReport:

    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "manual_queue_report",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.get_manual_queue_stats.assert_called_once()


# --------------------------------------------------------------------------- #
# staging_search  (UC-08)
# --------------------------------------------------------------------------- #

class TestStagingSearch:

    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "staging_search",
            "--query", "TPMT",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.search.assert_called_once()

    @patch(_PATCH_TS_REPO)
    def test_advanced_filters(self, mock_fn):
        repo = _make_mock_repo()
        mock_fn.return_value = repo

        result = _run_cli(
            "staging_search",
            "--query", "QueueCMBS",
            "--filters", '[{"field":"source","value":"manual"}]',
            "--days", "7",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        repo.advanced_search.assert_called_once()


class TestStagingLinkage:

    @patch("cli.main._collect_staging_reference_jobs")
    @patch(_PATCH_DEAL_REPO)
    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_ts_repo, mock_deal_repo, mock_reference_jobs):
        ts_repo = _make_mock_repo()
        deal_repo = _make_mock_deal_repo()
        mock_ts_repo.return_value = ts_repo
        mock_deal_repo.return_value = deal_repo
        mock_reference_jobs.return_value = ([{
            "job_name": "CMBS_GreyCo",
            "xml_type": "email",
            "scrubber": "TPMT_SPS",
            "servicer_id": 296,
            "mailbox": "mailbox@example.com",
            "save_path": "M:\\Deals",
        }], "xml")

        result = _run_cli(
            "staging_linkage",
            "--query", "TPMT_SPS",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        assert result.get("data", {}).get("linked_job_count") == 1
        assert result.get("data", {}).get("linked_deal_count") == 1


class TestStagingAudit:

    @patch("cli.main._collect_staging_reference_jobs")
    @patch(_PATCH_DEAL_REPO)
    @patch(_PATCH_TS_REPO)
    def test_basic(self, mock_ts_repo, mock_deal_repo, mock_reference_jobs):
        ts_repo = _make_mock_repo()
        deal_repo = _make_mock_deal_repo(deals=[])
        mock_ts_repo.return_value = ts_repo
        mock_deal_repo.return_value = deal_repo
        mock_reference_jobs.return_value = ([{
            "job_name": "CMBS_GreyCo",
            "xml_type": "email",
            "scrubber": "TPMT_SPS",
            "servicer_id": 296,
            "mailbox": "mailbox@example.com",
            "save_path": "M:\\OtherRoot",
        }], "xml")

        result = _run_cli(
            "staging_audit",
            "--days", "30",
            "--db-mode", "mysql",
        )
        assert result.get("success") is True
        assert "summary" in result.get("data", {})
        assert ts_repo.get_distinct_templates.called


# --------------------------------------------------------------------------- #
# Import sanity
# --------------------------------------------------------------------------- #

class TestImportSanity:

    def test_cli_imports(self):
        from cli.main import main
        assert callable(main)

    def test_ts_models_import(self):
        from backend.db.ts_models import (
            TemplateRun, TemplateSummary, FailureGroup, FailureSummary,
            DurationStats, ManualQueueReport, SourceTraceResult,
            PipelineLayer, PipelineStatus,
        )
        assert TemplateRun is not None
        assert PipelineStatus is not None

    def test_repo_import(self):
        from backend.db.template_staging_repo import TemplateStagingRepository
        assert TemplateStagingRepository is not None
