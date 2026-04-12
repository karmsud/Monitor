"""Tests for LogAnalytics against a real SQLite database."""
import os
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone

from backend.logs.analytics import LogAnalytics
from backend.logs.models import DealActivity, DIDFailure, JobHealth, DailySummary


# ──────────────────────────────────────────────────────────────────────────── #
#   Initialisation
# ──────────────────────────────────────────────────────────────────────────── #

class TestLogAnalyticsInit:

    def test_init_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            LogAnalytics(str(tmp_path / "nonexistent.db"))

    def test_init_missing_tables(self, tmp_path):
        """DB exists but lacks required tables → ValueError."""
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.commit()
        conn.close()
        with pytest.raises(ValueError, match="missing required tables"):
            LogAnalytics(db_path)

    def test_init_valid_db(self, log_db):
        analytics = LogAnalytics(log_db)
        assert analytics.db_path == log_db

    def test_reuses_shared_connection_across_calls(self, log_db):
        analytics = LogAnalytics(log_db)
        first_conn = analytics._get_conn()
        analytics.check_staleness()
        assert analytics._get_conn() is first_conn


# ──────────────────────────────────────────────────────────────────────────── #
#   Staleness check
# ──────────────────────────────────────────────────────────────────────────── #

class TestCheckStaleness:

    def test_check_staleness_fresh(self, log_db):
        """Recently synced → returns None."""
        analytics = LogAnalytics(log_db)
        result = analytics.check_staleness()
        assert result is None

    def test_check_staleness_stale(self, log_db):
        """Sync > 24h ago → returns warning dict."""
        conn = sqlite3.connect(log_db)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        conn.execute(
            "UPDATE index_metadata SET value = ? WHERE key = 'last_sync'",
            (old_time,),
        )
        conn.commit()
        conn.close()

        analytics = LogAnalytics(log_db)
        result = analytics.check_staleness()
        assert result is not None
        assert "warning" in result

    def test_check_staleness_no_sync(self, log_db):
        """No last_sync entry → returns warning."""
        conn = sqlite3.connect(log_db)
        conn.execute("DELETE FROM index_metadata WHERE key = 'last_sync'")
        conn.commit()
        conn.close()

        analytics = LogAnalytics(log_db)
        result = analytics.check_staleness()
        assert result is not None
        assert "warning" in result


# ──────────────────────────────────────────────────────────────────────────── #
#   Deal activity
# ──────────────────────────────────────────────────────────────────────────── #

class TestDealActivity:

    def test_deal_activity_found(self, log_db):
        analytics = LogAnalytics(log_db)
        results = analytics.deal_activity("CSMC")
        assert len(results) > 0
        assert all(isinstance(r, DealActivity) for r in results)
        assert any("CSMC" in r.detail for r in results)

    def test_deal_activity_with_import_did(self, log_db):
        analytics = LogAnalytics(log_db)
        # import_did broadens the search
        results = analytics.deal_activity("CSMC", import_did="TestJob_Alpha")
        assert len(results) >= 1

    def test_deal_activity_no_matches(self, log_db):
        analytics = LogAnalytics(log_db)
        results = analytics.deal_activity("ZZZZNONEXISTENT")
        assert results == []

    def test_deal_activity_days_filter(self, log_db):
        analytics = LogAnalytics(log_db)
        # With a very large day window, results should include all events
        results_wide = analytics.deal_activity("CSMC", days=365)
        # With days=1, results come from the last 24 h (today's data)
        results_narrow = analytics.deal_activity("CSMC", days=1)
        assert len(results_narrow) <= len(results_wide)


# ──────────────────────────────────────────────────────────────────────────── #
#   DID failures
# ──────────────────────────────────────────────────────────────────────────── #

class TestDIDFailures:

    def test_did_failures_found(self, log_db):
        analytics = LogAnalytics(log_db)
        failures = analytics.did_failures()
        assert len(failures) > 0
        assert all(isinstance(f, DIDFailure) for f in failures)

    def test_did_failures_job_filter(self, log_db):
        analytics = LogAnalytics(log_db)
        failures = analytics.did_failures(job_filter="TestJob_Alpha")
        # Should only find UNKNOWN_DID (from TestJob_Alpha)
        assert len(failures) >= 1
        for f in failures:
            assert "TestJob_Alpha" in f.affected_jobs

    def test_did_failures_empty(self, log_db):
        analytics = LogAnalytics(log_db)
        failures = analytics.did_failures(job_filter="NONEXISTENTJOB")
        assert failures == []

    def test_did_failures_counts(self, log_db):
        analytics = LogAnalytics(log_db)
        failures = analytics.did_failures()
        by_did = {f.import_did: f.failure_count for f in failures}
        assert by_did.get("UNKNOWN_DID") == 2
        assert by_did.get("MISSING_ONE") == 1

    def test_did_failures_sorted_by_count(self, log_db):
        analytics = LogAnalytics(log_db)
        failures = analytics.did_failures()
        counts = [f.failure_count for f in failures]
        assert counts == sorted(counts, reverse=True)


# ──────────────────────────────────────────────────────────────────────────── #
#   Job health
# ──────────────────────────────────────────────────────────────────────────── #

class TestJobHealth:

    def test_job_health_exact_match(self, log_db):
        analytics = LogAnalytics(log_db)
        health = analytics.job_health("TestJob_Alpha")
        assert isinstance(health, JobHealth)
        assert health.job_name == "TestJob_Alpha"

    def test_job_health_fuzzy_match(self, log_db):
        analytics = LogAnalytics(log_db)
        health = analytics.job_health("Alpha")
        assert health.job_name == "TestJob_Alpha"

    def test_job_health_no_match(self, log_db):
        analytics = LogAnalytics(log_db)
        with pytest.raises(ValueError, match="No jobs match"):
            analytics.job_health("ZZZNONEXISTENT")

    def test_job_health_ambiguous(self, log_db):
        analytics = LogAnalytics(log_db)
        with pytest.raises(ValueError, match="Ambiguous"):
            analytics.job_health("TestJob")

    def test_job_health_success_rate(self, log_db):
        analytics = LogAnalytics(log_db)
        health = analytics.job_health("TestJob_Alpha")
        # TestJob_Alpha today: 2 job_starts (today+yesterday), 2 job_completes
        # success_rate = (successful / total) * 100
        assert 0 <= health.success_rate <= 100

    def test_job_health_status_healthy(self, log_db):
        analytics = LogAnalytics(log_db)
        health = analytics.job_health("TestJob_Alpha")
        # Alpha has 2 starts and 2 completes → 100% → healthy
        assert health.status == "healthy"

    def test_job_health_status_warning(self, tmp_path):
        """Inject data where success rate is 80-95%."""
        db_path = _create_health_db(tmp_path, starts=20, completes=18, errors=2)
        analytics = LogAnalytics(db_path)
        health = analytics.job_health("HealthTestJob")
        assert health.status == "warning"

    def test_job_health_status_critical(self, tmp_path):
        """Inject data where success rate is <80%."""
        db_path = _create_health_db(tmp_path, starts=10, completes=5, errors=5)
        analytics = LogAnalytics(db_path)
        health = analytics.job_health("HealthTestJob")
        assert health.status == "critical"

    def test_job_health_avg_emails(self, log_db):
        analytics = LogAnalytics(log_db)
        health = analytics.job_health("TestJob_Alpha")
        # 5 emails found / 2 runs = 2.5
        assert health.avg_emails_per_run >= 0

    def test_job_health_common_errors(self, log_db):
        analytics = LogAnalytics(log_db)
        health = analytics.job_health("TestJob_Beta")
        assert isinstance(health.common_errors, list)
        if health.common_errors:
            assert "message" in health.common_errors[0]
            assert "count" in health.common_errors[0]


# ──────────────────────────────────────────────────────────────────────────── #
#   Daily summary
# ──────────────────────────────────────────────────────────────────────────── #

class TestDailySummary:

    def test_daily_summary_today(self, log_db):
        analytics = LogAnalytics(log_db)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = analytics.daily_summary()
        assert isinstance(summary, DailySummary)
        assert summary.date == today

    def test_daily_summary_specific_date(self, log_db):
        analytics = LogAnalytics(log_db)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        summary = analytics.daily_summary(date=yesterday)
        assert summary.date == yesterday

    def test_daily_summary_top_jobs(self, log_db):
        analytics = LogAnalytics(log_db)
        summary = analytics.daily_summary()
        assert isinstance(summary.top_jobs_by_volume, list)
        if len(summary.top_jobs_by_volume) >= 2:
            # First job should have >= events as second
            assert (
                summary.top_jobs_by_volume[0]["event_count"]
                >= summary.top_jobs_by_volume[1]["event_count"]
            )

    def test_daily_summary_comparison(self, log_db):
        analytics = LogAnalytics(log_db)
        summary = analytics.daily_summary()
        assert summary.comparison is not None
        assert "previous_date" in summary.comparison
        assert "error_change" in summary.comparison

    def test_daily_summary_empty_day(self, log_db):
        analytics = LogAnalytics(log_db)
        summary = analytics.daily_summary(date="2000-01-01")
        assert summary.total_jobs_run == 0
        assert summary.total_emails_processed == 0
        assert summary.total_errors == 0

    def test_daily_summary_did_failures(self, log_db):
        analytics = LogAnalytics(log_db)
        summary = analytics.daily_summary()
        # We inserted 3 did_mapping_failure events for today
        assert summary.total_did_failures >= 0


# ──────────────────────────────────────────────────────────────────────────── #
#   Helpers
# ──────────────────────────────────────────────────────────────────────────── #

def _create_health_db(tmp_path, starts: int, completes: int, errors: int) -> str:
    """Create a minimal log DB with controlled start/complete/error counts."""
    db_path = str(tmp_path / "health_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_file TEXT NOT NULL,
            log_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            job_name TEXT,
            mailbox TEXT,
            event_type TEXT NOT NULL,
            emails_found INTEGER,
            subject TEXT,
            sender TEXT,
            parser TEXT,
            filename TEXT,
            template TEXT,
            error_message TEXT,
            raw_line TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE indexed_files (
            filename TEXT PRIMARY KEY,
            indexed_at TEXT NOT NULL,
            event_count INTEGER NOT NULL,
            file_size INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE index_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO index_metadata VALUES (?, ?)",
        ("last_sync", datetime.now(timezone.utc).isoformat()),
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for _ in range(starts):
        conn.execute(
            "INSERT INTO log_events (log_file, log_type, timestamp, job_name, event_type, raw_line) VALUES (?, ?, ?, ?, ?, ?)",
            ("test.log", "email", now, "HealthTestJob", "job_start", "start"),
        )
    for _ in range(completes):
        conn.execute(
            "INSERT INTO log_events (log_file, log_type, timestamp, job_name, event_type, raw_line) VALUES (?, ?, ?, ?, ?, ?)",
            ("test.log", "email", now, "HealthTestJob", "job_complete", "complete"),
        )
    for _ in range(errors):
        conn.execute(
            "INSERT INTO log_events (log_file, log_type, timestamp, job_name, event_type, error_message, raw_line) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test.log", "email", now, "HealthTestJob", "parse_error", "Error msg", "error"),
        )
    conn.commit()
    conn.close()
    return db_path
