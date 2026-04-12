"""Tests for LogIndexer."""
import os
import sqlite3

import pytest

from backend.logs.indexer import LogIndexer


@pytest.fixture
def db_path(tmp_path):
    """Return path for a temporary SQLite database."""
    return str(tmp_path / "test_index.db")


@pytest.fixture
def synced_indexer(db_path, sample_log_folder):
    """Return a LogIndexer that has already synced the sample log folder."""
    indexer = LogIndexer(db_path)
    # Use a large retention window so fixture data (Jan 2025) is not purged.
    indexer.sync(sample_log_folder, log_type="email", retention_months=120)
    yield indexer
    indexer.close()


class TestLogIndexer:

    # ── Schema / DB creation ─────────────────────────────────────── #

    def test_create_tables(self, db_path):
        indexer = LogIndexer(db_path)
        # Check tables exist by querying sqlite_master
        cur = indexer._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row["name"] for row in cur.fetchall()}
        assert "log_events" in tables
        assert "indexed_files" in tables
        assert "index_metadata" in tables
        indexer.close()

    def test_db_file_created(self, db_path):
        indexer = LogIndexer(db_path)
        assert os.path.isfile(db_path)
        indexer.close()

    def test_existing_v1_db_is_migrated_before_index_creation(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
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
            """
        )
        conn.execute(
            "CREATE TABLE indexed_files (filename TEXT PRIMARY KEY, indexed_at TEXT NOT NULL, event_count INTEGER NOT NULL, file_size INTEGER)"
        )
        conn.execute(
            "CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO index_metadata VALUES (?, ?)", ("schema_version", "1"))
        conn.commit()
        conn.close()

        indexer = LogIndexer(db_path)
        cur = indexer._conn.execute("PRAGMA table_info(log_events)")
        columns = {row["name"] for row in cur.fetchall()}
        assert "email_event_id" in columns
        assert "email_event_index" in columns
        indexer.close()

    # ── Sync ─────────────────────────────────────────────────────── #

    def test_sync_processes_files(self, db_path, sample_log_folder):
        indexer = LogIndexer(db_path)
        result = indexer.sync(sample_log_folder, log_type="email")
        assert result["files_processed"] >= 1
        indexer.close()

    def test_sync_indexes_events(self, db_path, sample_log_folder):
        indexer = LogIndexer(db_path)
        result = indexer.sync(sample_log_folder, log_type="email")
        assert result["events_indexed"] > 0
        indexer.close()

    def test_sync_skips_indexed(self, db_path, sample_log_folder):
        indexer = LogIndexer(db_path)
        indexer.sync(sample_log_folder, log_type="email")
        result2 = indexer.sync(sample_log_folder, log_type="email")
        assert result2["files_skipped"] >= 1
        indexer.close()

    # ── Querying ─────────────────────────────────────────────────── #

    def test_query_all(self, synced_indexer):
        results = synced_indexer.query_events()
        assert len(results) > 0

    def test_query_by_job_name(self, synced_indexer):
        results = synced_indexer.query_events(job_name="TestJob_Alpha")
        assert all(r["job_name"] == "TestJob_Alpha" for r in results)

    def test_query_by_event_type(self, synced_indexer):
        results = synced_indexer.query_events(event_type="error")
        assert all(r["event_type"] == "error" for r in results)

    def test_query_limit(self, synced_indexer):
        results = synced_indexer.query_events(limit=2)
        assert len(results) <= 2

    def test_query_events_include_email_event_grouping(self, synced_indexer):
        results = synced_indexer.query_events(job_name="TestJob_Alpha")
        grouped = [row for row in results if row.get("email_event_id")]
        assert grouped
        assert all(row.get("email_event_index") is not None for row in grouped)

    # ── Summaries ────────────────────────────────────────────────── #

    def test_get_job_summary(self, synced_indexer):
        summary = synced_indexer.get_job_summary("TestJob_Alpha")
        assert isinstance(summary, dict)
        for key in ("job_name", "total_events", "total_files_loaded",
                     "total_errors", "total_emails_found"):
            assert key in summary, f"Missing key: {key}"

    def test_get_sync_status(self, synced_indexer):
        status = synced_indexer.get_sync_status()
        assert "last_sync" in status
        assert "total_events" in status

    # ── Context manager ──────────────────────────────────────────── #

    def test_context_manager(self, db_path):
        with LogIndexer(db_path) as indexer:
            assert indexer is not None
        # After exiting, connection should be closed
        assert indexer._conn is None

    # ── Dual-folder sync (email + SFTP) ──────────────────────────── #

    def test_dual_sync_both_types(self, db_path, tmp_path, sample_log_folder):
        """Syncing email and SFTP folders separately indexes both types."""
        import shutil

        # Set up separate folders (mimics prod layout)
        email_dir = tmp_path / "email_logs"
        sftp_dir = tmp_path / "sftp_logs"
        email_dir.mkdir()
        sftp_dir.mkdir()

        email_src = os.path.join(sample_log_folder, "EmailMonitor_20250115.log")
        sftp_src = os.path.join(sample_log_folder, "SFTPMonitor_20250115.log")
        shutil.copy(email_src, email_dir)
        shutil.copy(sftp_src, sftp_dir)

        indexer = LogIndexer(db_path)
        r1 = indexer.sync(str(email_dir), log_type="email", retention_months=120)
        r2 = indexer.sync(str(sftp_dir), log_type="sftp", retention_months=120)

        assert r1["files_processed"] == 1
        assert r2["files_processed"] == 1

        # Both log_type values should appear in the DB
        cur = indexer._conn.execute(
            "SELECT DISTINCT log_type FROM log_events"
        )
        types = {row["log_type"] for row in cur.fetchall()}
        assert "email" in types
        assert "sftp" in types
        indexer.close()

    # ── Error detail & activity queries ──────────────────────────── #

    def test_get_job_errors(self, synced_indexer):
        """get_job_errors returns only error/did_mapping_failed events."""
        errors = synced_indexer.get_job_errors("TestJob_Alpha")
        for e in errors:
            assert e["event_type"] in ("error", "did_mapping_failed")

    def test_get_job_errors_limit(self, synced_indexer):
        errors = synced_indexer.get_job_errors("TestJob_Alpha", limit=1)
        assert len(errors) <= 1

    def test_get_job_activity_excludes_noise(self, synced_indexer):
        """get_job_activity must not include job_start or info events."""
        events = synced_indexer.get_job_activity("TestJob_Alpha")
        for e in events:
            assert e["event_type"] not in ("job_start", "info")
