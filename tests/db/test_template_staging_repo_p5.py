"""Phase 5 tests for TemplateStagingRepository — all database calls mocked."""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from backend.db.template_staging_repo import TemplateStagingRepository


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _mock_cursor(fetchall_val=None, fetchone_val=None, description=None):
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_val or []
    cursor.fetchone.return_value = fetchone_val
    cursor.description = description or [
        ("TemplateProcessID",), ("TemplateName",), ("FilePath",),
        ("DID",), ("Dt",), ("StartTime",), ("EndTime",),
        ("ResultCode",), ("Comments",), ("ServicerID",),
        ("SourceProcess",), ("Job",), ("DataSource",),
        ("Machine",), ("UserName",),
    ]
    return cursor


def _sample_rows(count=3, result_code=0):
    """Generate sample tblTemplateStaging-like tuples."""
    base = datetime(2025, 6, 1, 10, 0, 0)
    rows = []
    for i in range(count):
        st = base + timedelta(hours=i)
        et = st + timedelta(seconds=45 + i * 10)
        rows.append((
            1000 + i,  # TemplateProcessID
            f"TPMT_SPS_{i}",  # TemplateName
            f"M:\\DealFolder\\Data\\file_{i}.xlsx",  # FilePath
            f"DEAL{i:03d}",  # DID
            st.strftime("%Y-%m-%d"),  # Dt
            st,  # StartTime
            et,  # EndTime
            result_code,  # ResultCode
            None if result_code == 0 else "Error occurred",  # Comments
            296,  # ServicerID
            "EmailMonitor",  # SourceProcess
            f"Job_{i}",  # Job
            "EmailMonitor: frpmonitor@usbank.com",  # DataSource
            "SERVER01",  # Machine
            "svcAccount",  # UserName
        ))
    return rows


@pytest.fixture
def repo():
    """Return a TemplateStagingRepository backed by a mocked connection."""
    with patch("backend.db.template_staging_repo.get_connection") as mock_gc:
        mock_conn = MagicMock()
        mock_gc.return_value = mock_conn
        r = TemplateStagingRepository(prod_mode=False)
        r._mock_conn = mock_conn
        yield r


# --------------------------------------------------------------------------- #
# get_recent_by_query
# --------------------------------------------------------------------------- #

class TestGetRecentByQuery:

    def test_finds_by_servicer_id(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(2))
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_recent_by_query("296", days=30)
        assert result["scope"] == "296"
        assert result["total_runs"] == 2
        assert result["successes"] == 2
        assert result["success_rate"] == 100.0
        assert len(result["runs"]) == 2

    def test_finds_by_template_name(self, repo):
        cursor = _mock_cursor()
        # First call (ServicerID attempt) returns empty, second returns data
        cursor.fetchall.side_effect = [
            [],  # ServicerID attempt fails (ValueError path)
            _sample_rows(3),  # template name match
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_recent_by_query("TPMT_SPS", days=30)
        assert result["total_runs"] == 3

    def test_falls_through_to_did(self, repo):
        cursor = _mock_cursor()
        cursor.fetchall.side_effect = [
            [],  # template name — no match
            _sample_rows(1),  # DID match
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_recent_by_query("DEAL001", days=30)
        assert result["total_runs"] == 1

    def test_empty_result(self, repo):
        cursor = _mock_cursor(fetchall_val=[])
        cursor.fetchall.return_value = []
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_recent_by_query("NONEXISTENT", days=30)
        assert result["total_runs"] == 0
        assert result["success_rate"] == 0.0

    def test_custom_days_and_limit(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(5))
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_recent_by_query("296", days=7, limit=5)
        assert result["period_days"] == 7


# --------------------------------------------------------------------------- #
# _build_summary
# --------------------------------------------------------------------------- #

class TestBuildSummary:

    def test_summary_with_mixed_results(self, repo):
        rows = [
            {"ResultCode": 0, "StartTime": "2025-06-01 10:00:00"},
            {"ResultCode": 1, "StartTime": "2025-06-01 11:00:00"},
            {"ResultCode": 0, "StartTime": "2025-06-01 12:00:00"},
            {"ResultCode": 1, "StartTime": "2025-06-01 13:00:00"},
        ]
        summary = repo._build_summary("test", rows, 30)
        assert summary["total_runs"] == 4
        assert summary["successes"] == 2
        assert summary["failures"] == 2
        assert summary["success_rate"] == 50.0
        assert summary["last_success"] == "2025-06-01 10:00:00"
        assert summary["last_failure"] == "2025-06-01 11:00:00"

    def test_summary_all_success(self, repo):
        rows = [{"ResultCode": 0, "StartTime": "2025-06-01 10:00:00"}]
        summary = repo._build_summary("scope", rows, 7)
        assert summary["success_rate"] == 100.0
        assert summary["last_failure"] is None

    def test_summary_empty(self, repo):
        summary = repo._build_summary("empty", [], 30)
        assert summary["total_runs"] == 0
        assert summary["success_rate"] == 0.0


# --------------------------------------------------------------------------- #
# get_failure_summary
# --------------------------------------------------------------------------- #

class TestGetFailureSummary:

    def test_unfiltered(self, repo):
        fail_rows = _sample_rows(2, result_code=1)
        group_rows = [
            ("TPMT_SPS_0", 2, "Error occurred", "DEAL000, DEAL001"),
        ]
        cursor = _mock_cursor()
        cursor.fetchall.side_effect = [fail_rows, group_rows]
        cursor.description = [
            ("TemplateProcessID",), ("TemplateName",), ("FilePath",),
            ("DID",), ("Dt",), ("StartTime",), ("EndTime",),
            ("ResultCode",), ("Comments",), ("ServicerID",),
            ("SourceProcess",), ("Job",), ("DataSource",),
            ("Machine",), ("UserName",),
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_failure_summary(days=30)
        assert result["total_failures"] == 2
        assert result["period_days"] == 30
        assert 296 in result["affected_servicers"]

    def test_filtered_by_template(self, repo):
        cursor = _mock_cursor()
        cursor.fetchall.side_effect = [_sample_rows(1, result_code=1), []]
        cursor.description = [
            ("TemplateProcessID",), ("TemplateName",), ("FilePath",),
            ("DID",), ("Dt",), ("StartTime",), ("EndTime",),
            ("ResultCode",), ("Comments",), ("ServicerID",),
            ("SourceProcess",), ("Job",), ("DataSource",),
            ("Machine",), ("UserName",),
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_failure_summary(template="TPMT")
        assert result["total_failures"] == 1

    def test_filtered_by_did(self, repo):
        cursor = _mock_cursor()
        cursor.fetchall.side_effect = [[], []]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_failure_summary(did="NONEXISTENT")
        assert result["total_failures"] == 0


# --------------------------------------------------------------------------- #
# get_duration_stats
# --------------------------------------------------------------------------- #

class TestGetDurationStats:

    def test_all_templates(self, repo):
        stats_rows = [
            ("TPMT_SPS", 10, 45.5, 12.0, 120.0),
            ("CMBS_Scrub", 5, 30.0, 10.0, 80.0),
        ]
        outlier_rows = [
            (9999, "TPMT_SPS", "M:\\file.xlsx", "DEAL001", 300.5, "2025-06-01"),
        ]
        cursor = _mock_cursor()
        cursor.description = [
            ("TemplateName",), ("total_runs",), ("avg_seconds",),
            ("min_seconds",), ("max_seconds",),
        ]
        cursor.fetchall.side_effect = [stats_rows, outlier_rows]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_duration_stats(days=30)
        assert result["period_days"] == 30
        assert len(result["templates"]) == 2
        assert result["templates"][0]["template_name"] == "TPMT_SPS"
        assert result["templates"][0]["avg_seconds"] == 45.5
        assert len(result["outliers"]) == 1

    def test_filtered_by_template(self, repo):
        cursor = _mock_cursor()
        cursor.description = [
            ("TemplateName",), ("total_runs",), ("avg_seconds",),
            ("min_seconds",), ("max_seconds",),
        ]
        cursor.fetchall.side_effect = [
            [("TPMT_SPS", 5, 45.0, 10.0, 100.0)],
            [],  # no outliers
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_duration_stats(template="TPMT")
        assert len(result["templates"]) == 1


# --------------------------------------------------------------------------- #
# get_manual_queue_stats
# --------------------------------------------------------------------------- #

class TestGetManualQueueStats:

    def test_basic(self, repo):
        cursor = _mock_cursor()
        # get_manual_queue_stats calls fetchall 4 times:
        # 1) GET_SOURCE_PROCESS_BREAKDOWN
        # 2) GET_MANUAL_QUEUE_BY_TEMPLATE
        # 3) GET_MANUAL_QUEUE_BY_DID
        # 4) GET_MANUAL_QUEUE_OPERATORS
        source_rows = [
            ("EmailMonitor", 80),
            ("ManualQueue", 20),
        ]
        template_rows = [
            ("TPMT_SPS", 10),
        ]
        did_rows = [
            ("DEAL001", 5),
        ]
        operator_rows = [
            ("Queued via macro by John Doe", 15),
        ]
        cursor.fetchall.side_effect = [source_rows, template_rows, did_rows, operator_rows]
        cursor.description = [("SourceProcess",), ("run_count",)]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_manual_queue_stats(days=30)
        assert result["period_days"] == 30
        assert result["total_count"] == 100
        assert result["manual_count"] == 20
        assert result["automated_count"] == 80


# --------------------------------------------------------------------------- #
# trace_by_filepath
# --------------------------------------------------------------------------- #

class TestTraceByFilepath:

    def test_found(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(1))
        repo._mock_conn.cursor.return_value = cursor
        result = repo.trace_by_filepath("file_0.xlsx")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_not_found(self, repo):
        cursor = _mock_cursor(fetchall_val=[])
        repo._mock_conn.cursor.return_value = cursor
        result = repo.trace_by_filepath("nonexistent.xlsx")
        assert result == []


# --------------------------------------------------------------------------- #
# get_processing_for_servicer
# --------------------------------------------------------------------------- #

class TestGetProcessingForServicer:

    def test_with_data(self, repo):
        cursor = _mock_cursor()
        # Summary row
        summary_row = ("TPMT_SPS", 10, 8, 2, "2025-06-01 12:00:00")
        # Recent rows
        recent_rows = _sample_rows(3)
        cursor.fetchall.side_effect = [[summary_row], recent_rows]
        cursor.description = [
            ("TemplateName",), ("total_runs",), ("successes",),
            ("failures",), ("last_run",),
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_processing_for_servicer(296)
        assert isinstance(result, dict)


# --------------------------------------------------------------------------- #
# get_pipeline_status
# --------------------------------------------------------------------------- #

class TestGetPipelineStatus:

    def test_basic(self, repo):
        cursor = _mock_cursor()
        # get_pipeline_status calls GET_RECENT_BY_SERVICER → fetchall once
        cursor.fetchall.side_effect = [
            _sample_rows(3),  # 3 recent runs (all result_code=0)
        ]
        repo._mock_conn.cursor.return_value = cursor
        result = repo.get_pipeline_status(296, days=30)
        assert isinstance(result, dict)
        assert "execution_layer" in result
        assert "health_score" in result["execution_layer"]
        assert result["execution_layer"]["total_runs"] == 3


# --------------------------------------------------------------------------- #
# context manager
# --------------------------------------------------------------------------- #

class TestContextManager:

    def test_enter_exit(self, repo):
        with repo as r:
            assert r is repo


# --------------------------------------------------------------------------- #
# ts_models dataclass tests
# --------------------------------------------------------------------------- #

class TestTemplateRun:

    def test_from_row_success(self):
        from backend.db.ts_models import TemplateRun

        row = {
            "TemplateProcessID": 42,
            "TemplateName": "TPMT_SPS",
            "FilePath": "M:\\test.xlsx",
            "DID": "DEAL001",
            "Dt": "2025-06-01",
            "StartTime": datetime(2025, 6, 1, 10, 0, 0),
            "EndTime": datetime(2025, 6, 1, 10, 0, 45),
            "ResultCode": 0,
            "Comments": None,
            "ServicerID": 296,
            "SourceProcess": "EmailMonitor",
            "Job": "Job_01",
            "DataSource": "EmailMonitor: frpmonitor@usbank.com",
            "Machine": "SERVER01",
            "UserName": "svcAccount",
        }
        run = TemplateRun.from_row(row)
        assert run.template_process_id == 42
        assert run.success is True
        assert run.source_type == "email"
        assert run.duration_seconds == 45.0

    def test_from_row_failure(self):
        from backend.db.ts_models import TemplateRun

        row = {
            "TemplateProcessID": 99,
            "TemplateName": "CMBS_Scrub",
            "ResultCode": 1,
            "Comments": "File not found",
        }
        run = TemplateRun.from_row(row)
        assert run.success is False

    def test_source_type_sftp(self):
        from backend.db.ts_models import TemplateRun

        run = TemplateRun(
            template_process_id=1,
            template_name="T",
            data_source="SFTPMonitor: incoming/",
        )
        assert run.source_type == "sftp"

    def test_source_type_manual(self):
        from backend.db.ts_models import TemplateRun

        run = TemplateRun(
            template_process_id=1,
            template_name="T",
            data_source="Queued via macro",
        )
        assert run.source_type == "manual"

    def test_source_type_unknown(self):
        from backend.db.ts_models import TemplateRun

        run = TemplateRun(
            template_process_id=1,
            template_name="T",
            data_source="",
        )
        assert run.source_type == "unknown"

    def test_to_dict(self):
        from backend.db.ts_models import TemplateRun

        run = TemplateRun(
            template_process_id=1,
            template_name="T",
            start_time=datetime(2025, 6, 1, 10, 0),
            end_time=datetime(2025, 6, 1, 10, 1),
            result_code=0,
        )
        d = run.to_dict()
        assert d["success"] is True
        assert d["source_type"] == "unknown"
        assert isinstance(d["start_time"], str)


class TestSummaryModels:

    def test_template_summary(self):
        from backend.db.ts_models import TemplateSummary

        s = TemplateSummary(scope="test", total_runs=10, successes=8, failures=2, success_rate=80.0)
        d = s.to_dict()
        assert d["scope"] == "test"
        assert d["success_rate"] == 80.0

    def test_failure_group(self):
        from backend.db.ts_models import FailureGroup

        fg = FailureGroup(pattern="timeout", count=5, templates=["A", "B"])
        d = fg.to_dict()
        assert d["count"] == 5
        assert len(d["templates"]) == 2

    def test_failure_summary(self):
        from backend.db.ts_models import FailureSummary

        fs = FailureSummary(total_failures=10, period_days=30)
        d = fs.to_dict()
        assert d["total_failures"] == 10

    def test_duration_stats(self):
        from backend.db.ts_models import DurationStats

        ds = DurationStats(template_name="T", total_runs=100, avg_seconds=12.5, min_seconds=1.0, max_seconds=60.0)
        d = ds.to_dict()
        assert d["avg_seconds"] == 12.5

    def test_manual_queue_report(self):
        from backend.db.ts_models import ManualQueueReport

        mqr = ManualQueueReport(automated_count=80, manual_count=20, total_count=100, manual_percentage=20.0)
        d = mqr.to_dict()
        assert d["manual_percentage"] == 20.0

    def test_source_trace_result(self):
        from backend.db.ts_models import SourceTraceResult

        st = SourceTraceResult(file_path="M:\\test.xlsx", source_type="email")
        d = st.to_dict()
        assert d["source_type"] == "email"

    def test_pipeline_layer(self):
        from backend.db.ts_models import PipelineLayer

        pl = PipelineLayer(name="config", status="ok", count=5)
        d = pl.to_dict()
        assert d["name"] == "config"

    def test_pipeline_status(self):
        from backend.db.ts_models import PipelineStatus

        ps = PipelineStatus(query="296", health_score=85.0, gaps=["No execution data"])
        d = ps.to_dict()
        assert d["health_score"] == 85.0
        assert len(d["gaps"]) == 1


# --------------------------------------------------------------------------- #
# filtered_search — generic multi-column filtering
# --------------------------------------------------------------------------- #

class TestFilteredSearch:
    """Tests for the generic multi-column filtered_search method."""

    def test_single_column_filter(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(2))
        repo._mock_conn.cursor.return_value = cursor
        results = repo.filtered_search({"TemplateName": "QueueCMBS_Scrubber_x"})
        assert len(results) == 2
        # Verify SQL was called with a WHERE clause containing the column
        executed_sql = cursor.execute.call_args[0][0]
        assert "TemplateName = ?" in executed_sql

    def test_multi_column_filter(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(1))
        repo._mock_conn.cursor.return_value = cursor
        results = repo.filtered_search({
            "TemplateName": "QueueCMBS_Scrubber_x",
            "DID": "FREMF 2026-KF169",
        })
        assert len(results) == 1
        executed_sql = cursor.execute.call_args[0][0]
        assert "TemplateName = ?" in executed_sql
        assert "DID = ?" in executed_sql
        assert "AND" in executed_sql
        # Params should be the two values + limit
        params = cursor.execute.call_args[0][1]
        assert params[0] == "QueueCMBS_Scrubber_x"
        assert params[1] == "FREMF 2026-KF169"
        assert params[2] == 50  # default limit

    def test_case_insensitive_column_name(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(1))
        repo._mock_conn.cursor.return_value = cursor
        results = repo.filtered_search({"templatename": "Test", "did": "D001"})
        assert len(results) == 1
        executed_sql = cursor.execute.call_args[0][0]
        # Should use canonical column names
        assert "TemplateName = ?" in executed_sql
        assert "DID = ?" in executed_sql

    def test_invalid_column_ignored(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(1))
        repo._mock_conn.cursor.return_value = cursor
        results = repo.filtered_search({
            "TemplateName": "Test",
            "INVALID_COL": "drop table",  # should be silently dropped
        })
        executed_sql = cursor.execute.call_args[0][0]
        assert "INVALID_COL" not in executed_sql
        assert "TemplateName = ?" in executed_sql

    def test_all_invalid_columns_returns_empty(self, repo):
        results = repo.filtered_search({"bogus": "value"})
        assert results == []

    def test_empty_filters_returns_empty(self, repo):
        results = repo.filtered_search({})
        assert results == []

    def test_custom_limit(self, repo):
        cursor = _mock_cursor(fetchall_val=_sample_rows(3))
        repo._mock_conn.cursor.return_value = cursor
        repo.filtered_search({"DID": "FREMF 2026"}, limit=10)
        params = cursor.execute.call_args[0][1]
        assert params[-1] == 10  # last param is the limit

    def test_mssql_adaptation(self):
        """Ensure _adapt_sql rewrites LIMIT → TOP for prod mode."""
        with patch("backend.db.template_staging_repo.get_connection") as mock_gc:
            mock_conn = MagicMock()
            mock_gc.return_value = mock_conn
            r = TemplateStagingRepository(prod_mode=True)
            cursor = _mock_cursor(fetchall_val=_sample_rows(1))
            mock_conn.cursor.return_value = cursor
            r.filtered_search({"TemplateName": "Test"}, limit=5)
            executed_sql = cursor.execute.call_args[0][0]
            # MSSQL: LIMIT should be gone, TOP should be present
            assert "LIMIT" not in executed_sql
            assert "TOP" in executed_sql
            # Table name should be fully qualified
            assert "ToolsHub.ToolsHub.dbo.tblTemplateStaging" in executed_sql
