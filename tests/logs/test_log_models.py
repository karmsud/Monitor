"""Tests for Phase 3 log dataclass models."""
import pytest
from backend.logs.models import DealActivity, DIDFailure, JobHealth, DailySummary


# ──────────────────────────────────────────────────────────────────────────── #
#   DealActivity
# ──────────────────────────────────────────────────────────────────────────── #

class TestDealActivity:

    def test_creation(self):
        da = DealActivity(
            timestamp="2025-01-15T10:00:00",
            job_name="TestJob_Alpha",
            event_type="processing",
            detail="Processing CSMC deal data",
            log_file="log1.log",
        )
        assert da.timestamp == "2025-01-15T10:00:00"
        assert da.job_name == "TestJob_Alpha"
        assert da.event_type == "processing"
        assert da.detail == "Processing CSMC deal data"
        assert da.log_file == "log1.log"

    def test_to_dict(self):
        da = DealActivity(
            timestamp="2025-01-15T10:00:00",
            job_name="TestJob_Alpha",
            event_type="processing",
            detail="Processing CSMC deal data",
            log_file="log1.log",
        )
        d = da.to_dict()
        assert isinstance(d, dict)
        assert d["timestamp"] == "2025-01-15T10:00:00"
        assert d["job_name"] == "TestJob_Alpha"
        assert "detail" in d
        assert "log_file" in d


# ──────────────────────────────────────────────────────────────────────────── #
#   DIDFailure
# ──────────────────────────────────────────────────────────────────────────── #

class TestDIDFailure:

    def test_creation(self):
        df = DIDFailure(
            import_did="UNKNOWN_DID",
            failure_count=5,
            affected_jobs=["TestJob_Alpha", "TestJob_Beta"],
            first_seen="2025-01-10T08:00:00",
            last_seen="2025-01-15T10:00:00",
        )
        assert df.import_did == "UNKNOWN_DID"
        assert df.failure_count == 5

    def test_to_dict(self):
        df = DIDFailure(
            import_did="MISSING",
            failure_count=3,
            affected_jobs=["JobA"],
            first_seen="2025-01-10",
            last_seen="2025-01-15",
        )
        d = df.to_dict()
        assert isinstance(d, dict)
        assert d["import_did"] == "MISSING"
        assert d["failure_count"] == 3

    def test_affected_jobs_list(self):
        df = DIDFailure(
            import_did="TEST",
            failure_count=2,
            affected_jobs=["Alpha", "Beta", "Gamma"],
            first_seen="2025-01-01",
            last_seen="2025-01-15",
        )
        assert len(df.affected_jobs) == 3
        assert "Beta" in df.affected_jobs


# ──────────────────────────────────────────────────────────────────────────── #
#   JobHealth
# ──────────────────────────────────────────────────────────────────────────── #

class TestJobHealth:

    def test_creation(self):
        jh = JobHealth(
            job_name="TestJob_Alpha",
            total_runs=100,
            successful_runs=98,
            error_count=2,
            success_rate=98.0,
            status="healthy",
            last_run="2025-01-15T10:00:00",
            last_error="Template mismatch",
            avg_emails_per_run=5.5,
        )
        assert jh.job_name == "TestJob_Alpha"
        assert jh.total_runs == 100
        assert jh.status == "healthy"

    def test_to_dict(self):
        jh = JobHealth(
            job_name="TestJob",
            total_runs=10,
            successful_runs=9,
            error_count=1,
            success_rate=90.0,
            status="warning",
            last_run="2025-01-15",
            last_error=None,
            avg_emails_per_run=3.0,
        )
        d = jh.to_dict()
        assert isinstance(d, dict)
        assert d["job_name"] == "TestJob"
        assert d["success_rate"] == 90.0
        assert d["status"] == "warning"

    def test_default_common_errors(self):
        jh = JobHealth(
            job_name="X",
            total_runs=1,
            successful_runs=1,
            error_count=0,
            success_rate=100.0,
            status="healthy",
            last_run=None,
            last_error=None,
            avg_emails_per_run=0.0,
        )
        assert jh.common_errors == []

    def test_default_date_range(self):
        jh = JobHealth(
            job_name="X",
            total_runs=1,
            successful_runs=1,
            error_count=0,
            success_rate=100.0,
            status="healthy",
            last_run=None,
            last_error=None,
            avg_emails_per_run=0.0,
        )
        assert jh.date_range == "Last 30 days"

    def test_status_values(self):
        for status in ("healthy", "warning", "critical"):
            jh = JobHealth(
                job_name="X",
                total_runs=1,
                successful_runs=1,
                error_count=0,
                success_rate=100.0,
                status=status,
                last_run=None,
                last_error=None,
                avg_emails_per_run=0.0,
            )
            assert jh.status == status


# ──────────────────────────────────────────────────────────────────────────── #
#   DailySummary
# ──────────────────────────────────────────────────────────────────────────── #

class TestDailySummary:

    def test_creation(self):
        ds = DailySummary(
            date="2025-01-15",
            total_jobs_run=10,
            total_emails_processed=50,
            total_files_loaded=5,
            total_errors=2,
            total_did_failures=3,
        )
        assert ds.date == "2025-01-15"
        assert ds.total_jobs_run == 10

    def test_to_dict(self):
        ds = DailySummary(
            date="2025-01-15",
            total_jobs_run=5,
            total_emails_processed=20,
            total_files_loaded=3,
            total_errors=1,
            total_did_failures=0,
        )
        d = ds.to_dict()
        assert isinstance(d, dict)
        assert d["date"] == "2025-01-15"
        assert "total_did_failures" in d

    def test_default_comparison(self):
        ds = DailySummary(
            date="2025-01-15",
            total_jobs_run=1,
            total_emails_processed=0,
            total_files_loaded=0,
            total_errors=0,
            total_did_failures=0,
        )
        assert ds.comparison is None

    def test_default_top_lists(self):
        ds = DailySummary(
            date="2025-01-15",
            total_jobs_run=1,
            total_emails_processed=0,
            total_files_loaded=0,
            total_errors=0,
            total_did_failures=0,
        )
        assert ds.top_jobs_by_volume == []
        assert ds.top_error_sources == []
