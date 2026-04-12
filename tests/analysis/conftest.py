"""Phase 4 shared fixtures."""
import sqlite3
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock


class _NoCloseConnection:
    """Wrapper around sqlite3.Connection that makes close() a no-op.

    Delegates all attribute access to the underlying connection.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def close(self):
        """No-op — keeps the shared connection alive across multiple calls."""
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def analysis_db():
    """In-memory SQLite with 10 jobs x 14 days of realistic data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            error_message TEXT,
            file_path TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE log_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            service_type TEXT,
            last_modified TEXT,
            indexed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX idx_events_job ON log_events(job_name)")
    conn.execute("CREATE INDEX idx_events_type ON log_events(event_type)")

    jobs = [
        "Ocwen", "PHH", "Shellpoint", "BSI", "LoanCare",
        "Cenlar", "SPS", "FlagStar", "Chase", "WellsFargo",
    ]
    base_date = date(2025, 2, 1)

    for day_offset in range(14):
        d = (base_date + timedelta(days=day_offset)).isoformat()
        for i, job in enumerate(jobs):
            # Successes: varies by job (3-6)
            success_count = 3 + (i % 4)
            for s in range(success_count):
                conn.execute(
                    "INSERT INTO log_events (job_name, event_type, timestamp, error_message) VALUES (?,?,?,?)",
                    (job, "file_processed", f"{d}T08:{s:02d}:00", f"file_{s}.csv"),
                )
            # Failures: Ocwen (i=0), BSI (i=3), FlagStar (i=7) have errors
            if i in (0, 3, 7):
                fail_count = 1 if day_offset % 3 == 0 else 0
                for f in range(fail_count):
                    conn.execute(
                        "INSERT INTO log_events (job_name, event_type, timestamp, error_message) VALUES (?,?,?,?)",
                        (job, "error", f"{d}T09:00:00", "parse failure"),
                    )
            # Warnings: Shellpoint (i=2), Cenlar (i=5)
            if i in (2, 5):
                conn.execute(
                    "INSERT INTO log_events (job_name, event_type, timestamp, error_message) VALUES (?,?,?,?)",
                    (job, "warning", f"{d}T10:00:00", "timeout"),
                )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def empty_db():
    """Empty SQLite -- tests graceful handling of no data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            error_message TEXT,
            file_path TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE log_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            service_type TEXT,
            last_modified TEXT,
            indexed_at TEXT
        )
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mock_parser():
    """Mock SettingsParser with 10 email jobs."""
    parser = MagicMock()
    jobs = []
    for i, name in enumerate([
        "Ocwen", "PHH", "Shellpoint", "BSI", "LoanCare",
        "Cenlar", "SPS", "FlagStar", "Chase", "WellsFargo",
    ]):
        job = MagicMock()
        job.name = name
        job.servicer_id = str(100 + i) if i < 8 else None
        job.mailbox = f"inbox{i // 3}@bank.com"
        job.folder = "Inbox"
        job.email_filter = f"*{name.lower()}*"
        job.did = f"DID{i:03d}"
        job.import_did = f"IMP{i:03d}"
        job.company_id = str(1 + i // 3)
        job.template = f"Template{i % 3}"
        job.queue_one_file = "True" if i % 2 == 0 else "False"
        job.parser_type = "csv" if i % 3 != 2 else "xlsx"
        job.parsers = [{"type": job.parser_type}]
        job.templates = {"default": job.template}
        job.sender_filter = f"sender_{name.lower()}@bank.com" if i % 2 == 0 else None
        job.subject_filter = None
        job.attachment_filter = None
        job.day_adjust = None
        job.xml_type = "email"
        job.type = "email"
        jobs.append(job)

    parser.get_all_jobs.return_value = jobs
    parser.get_job_by_name.side_effect = lambda n: next((j for j in jobs if j.name == n), None)
    parser.type = "email"
    parser.email_jobs = jobs
    parser.sftp_jobs = []
    return parser


@pytest.fixture
def mock_log_analytics(analysis_db):
    """Mock LogAnalytics that exposes the in-memory connection."""
    analytics = MagicMock()
    # Wrap connection so close() is a no-op — survives multiple _get_conn calls
    wrapped = _NoCloseConnection(analysis_db)
    analytics._get_conn.return_value = wrapped
    analytics.check_staleness.return_value = None
    analytics.job_health.return_value = {
        "error_jobs": ["BSI"],
        "warning_jobs": ["Shellpoint"],
    }
    yield analytics


@pytest.fixture
def mock_deal_repo():
    """Mock DealRepository with sample DID mappings."""
    repo = MagicMock()
    repo.get_by_did.side_effect = lambda did: {
        "DID000": [{"DID": "DID000", "ImportDID": "IMP000", "CompanyID": "1", "ItemID": "1001"}],
        "DID001": [{"DID": "DID001", "ImportDID": "IMP001", "CompanyID": "1", "ItemID": "1002"}],
        "DID003": [{"DID": "DID003", "ImportDID": "IMP003", "CompanyID": "2", "ItemID": "1004"}],
    }.get(did, [])
    repo.get_by_import_did.side_effect = lambda imp: {
        "IMP000": [{"DID": "DID000", "ImportDID": "IMP000", "CompanyID": "1"}],
        "IMP001": [{"DID": "DID001", "ImportDID": "IMP001", "CompanyID": "1"}],
    }.get(imp, [])
    repo.get_deals_by_company.side_effect = lambda cid: {
        100: [{"DID": "DID000", "ImportDID": "IMP000", "CompanyID": "100"}],
        101: [{"DID": "DID001", "ImportDID": "IMP001", "CompanyID": "101"}],
        102: [{"DID": "DID002", "ImportDID": "IMP002", "CompanyID": "102"}],
        103: [{"DID": "DID003", "ImportDID": "IMP003", "CompanyID": "103"}],
        104: [{"DID": "DID004", "ImportDID": "IMP004", "CompanyID": "104"}],
    }.get(cid, [])
    repo.get_all.return_value = [
        {"DID": f"DID{i:03d}", "ImportDID": f"IMP{i:03d}", "CompanyID": str(100 + i), "ItemID": str(1001 + i)}
        for i in range(10)
    ]
    return repo
