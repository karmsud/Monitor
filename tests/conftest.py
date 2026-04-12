"""Shared pytest fixtures for FRP Agent tests."""
import os
import shutil
import pytest
from datetime import datetime, timedelta, timezone

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def email_fixture():
    return os.path.join(FIXTURES_DIR, "email_settings_valid.xml")


@pytest.fixture
def sftp_fixture():
    return os.path.join(FIXTURES_DIR, "sftp_settings_valid.xml")


@pytest.fixture
def sample_log_folder():
    return os.path.join(FIXTURES_DIR, "logs")


@pytest.fixture
def sample_log_path():
    return os.path.join(FIXTURES_DIR, "logs", "EmailMonitor_20250115.log")


@pytest.fixture
def sample_sftp_log_path():
    return os.path.join(FIXTURES_DIR, "logs", "SFTPMonitor_20250115.log")


@pytest.fixture
def tmp_settings(email_fixture, tmp_path):
    dest = tmp_path / "Settings.xml"
    shutil.copy(email_fixture, dest)
    return str(dest)


@pytest.fixture
def tmp_sftp_settings(sftp_fixture, tmp_path):
    dest = tmp_path / "SftpSettings.xml"
    shutil.copy(sftp_fixture, dest)
    return str(dest)


# --------------------------------------------------------------------------- #
#  Phase 2 fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def mock_deal_repo():
    """Mock DealRepository for intel tests."""
    from unittest.mock import MagicMock
    from backend.db.deal_repo import DealRepository

    repo = MagicMock(spec=DealRepository)

    # Default data: 3 companies, some deals
    repo.get_all_servicer_ids.return_value = {100, 150, 200}

    repo.get_deals_by_company.side_effect = lambda cid: {
        100: [
            {"DID": 1001, "ImportDID": "ACME", "CompanyID": 100},
            {"DID": 1002, "ImportDID": "ACME", "CompanyID": 100},
        ],
        150: [
            {"DID": 2001, "ImportDID": "CSMC", "CompanyID": 150},
            {"DID": 2002, "ImportDID": "CSMC", "CompanyID": 150},
            {"DID": 2003, "ImportDID": "CSFB", "CompanyID": 150},
        ],
        200: [],  # exists but no deals
    }.get(cid, [])

    repo.get_companies_by_import_did.side_effect = lambda kw: {
        "ACME": [100],
        "CSMC": [150],
        "CSFB": [150],
        "OVERLAP": [100, 150, 200],
    }.get(kw.upper(), [])

    repo.servicer_exists.side_effect = lambda sid: sid in [100, 150, 200]

    return repo


@pytest.fixture
def tmp_settings_path(tmp_path, email_fixture):
    """Copy sample email Settings.xml to tmp_path for write tests."""
    dest = tmp_path / "Settings.xml"
    shutil.copy(email_fixture, dest)
    return str(dest)


@pytest.fixture
def tmp_sftp_settings_path(tmp_path, sftp_fixture):
    """Copy sample SFTP Settings.xml to tmp_path for write tests."""
    dest = tmp_path / "SftpSettings.xml"
    shutil.copy(sftp_fixture, dest)
    return str(dest)


@pytest.fixture
def tmp_backup_path(tmp_path, email_fixture):
    """Create a backup copy for diff/rollback tests."""
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    backup = backup_dir / "Settings_20260201_120000.xml"
    shutil.copy(email_fixture, backup)
    return str(backup)


# --------------------------------------------------------------------------- #
#  Phase 3 fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def log_db(tmp_path):
    """Create a populated SQLite log database for analytics tests."""
    import sqlite3
    from datetime import datetime, timedelta

    db_path = str(tmp_path / "test_logs.db")
    conn = sqlite3.connect(db_path)

    # Create tables
    conn.execute("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_file TEXT NOT NULL,
            log_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            job_name TEXT,
            mailbox TEXT,
            email_event_id TEXT,
            email_event_index INTEGER,
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

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    # Sync metadata
    conn.execute("INSERT INTO index_metadata VALUES (?, ?)", ("last_sync", now.isoformat()))

    # Test events
    events = [
        # Job starts
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "job_start", None, None, None, None, None, None, None, "Starting job TestJob_Alpha"),
        ("log1.log", "email", today, "TestJob_Beta", None, None, None, "job_start", None, None, None, None, None, None, None, "Starting job TestJob_Beta"),
        # Job complete
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "job_complete", None, None, None, None, None, None, None, "Job complete TestJob_Alpha"),
        # Emails found
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "email_found", 5, None, None, None, None, None, None, "Found 5 emails for TestJob_Alpha"),
        # Errors
        ("log1.log", "email", today, "TestJob_Beta", None, None, None, "parse_error", None, None, None, None, None, None, "Template mismatch", "Error in TestJob_Beta: Template mismatch"),
        # DID failures
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "did_mapping_failure", None, None, None, None, None, None, None, "Did not find DID mapping for [UNKNOWN_DID]"),
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "did_mapping_failure", None, None, None, None, None, None, None, "Did not find DID mapping for [UNKNOWN_DID]"),
        ("log1.log", "email", today, "TestJob_Beta", None, None, None, "did_mapping_failure", None, None, None, None, None, None, None, "Did not find DID mapping for [MISSING_ONE]"),
        # File loaded
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "file_loaded", None, None, None, None, "report.xlsx", None, None, "Loaded file: report.xlsx"),
        # Deal activity keyword
        ("log1.log", "email", today, "TestJob_Alpha", None, None, None, "processing", None, None, None, None, None, None, None, "Processing CSMC deal data for TestJob_Alpha"),
        # One email-level grouped set
        ("log1.log", "email", today, "TestJob_Alpha", "ops@example.com", "log1.log::job1::email1", 1, "processing", None, "Monthly Report", None, None, None, None, None, "Processing: [Monthly Report]"),
        ("log1.log", "email", today, "TestJob_Alpha", "ops@example.com", "log1.log::job1::email1", 1, "from", None, "Monthly Report", "reports@vendor.com", None, None, None, None, "From: reports@vendor.com"),
        ("log1.log", "email", today, "TestJob_Alpha", "ops@example.com", "log1.log::job1::email1", 1, "file_loaded", None, "Monthly Report", "reports@vendor.com", None, "report.xlsx", None, None, "Loaded file: report.xlsx"),
        # Yesterday events for comparison
        ("log0.log", "email", yesterday, "TestJob_Alpha", None, None, None, "job_start", None, None, None, None, None, None, None, "Starting job TestJob_Alpha"),
        ("log0.log", "email", yesterday, "TestJob_Alpha", None, None, None, "job_complete", None, None, None, None, None, None, None, "Job complete TestJob_Alpha"),
        ("log0.log", "email", yesterday, "TestJob_Alpha", None, None, None, "parse_error", None, None, None, None, None, None, "Old error", "Old error in TestJob_Alpha"),
    ]

    conn.executemany(
        "INSERT INTO log_events (log_file, log_type, timestamp, job_name, mailbox, email_event_id, email_event_index, event_type, emails_found, subject, sender, parser, filename, template, error_message, raw_line) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        events,
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def sample_email_info():
    """Sample EmailInfo for triage tests."""
    from backend.triage.models import EmailInfo
    return EmailInfo(
        sender="reports@acme.com",
        sender_name="ACME Reports",
        subject="Monthly Report - January 2025",
        date="2025-01-15T10:00:00",
        to=["frp.test@example.com"],
        cc=[],
        body_preview="Please find attached the monthly report.",
        attachment_names=["report_jan2025.xlsx"],
        file_path="C:\\emails\\sample.msg",
    )


@pytest.fixture
def sample_email_no_match():
    """EmailInfo that should NOT match any test jobs."""
    from backend.triage.models import EmailInfo
    return EmailInfo(
        sender="unknown@random.org",
        sender_name="Random Person",
        subject="Meeting Tomorrow",
        date="2025-01-15T10:00:00",
        to=["someone@elsewhere.com"],
        cc=[],
        body_preview="Let's meet tomorrow.",
        attachment_names=[],
        file_path="C:\\emails\\no_match.msg",
    )


@pytest.fixture
def mock_jobs():
    """List of mock EmailJob objects for triage tests."""
    from backend.xml.models import EmailJob
    return [
        EmailJob(
            name="TestJob_Alpha",
            mailbox="frp.test@example.com",
            folder="Inbox",
            sme="Team",
            filters={"From": "reports@acme.com", "Subject": "Monthly Report"},
            servicer_id=150,
        ),
        EmailJob(
            name="TestJob_Beta",
            mailbox="frp.test@example.com",
            folder="Inbox",
            sme="Team",
            filters={"From": "reports@beta.org"},
            servicer_id=200,
        ),
        EmailJob(
            name="TestJob_NoFilter",
            mailbox="",
            folder="Inbox",
            sme="Team",
            filters={},
        ),
    ]


# --------------------------------------------------------------------------- #
#  Phase 5 fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def mock_ts_repo():
    """Mock TemplateStagingRepository for Phase 5 tests."""
    from unittest.mock import MagicMock
    from backend.db.template_staging_repo import TemplateStagingRepository

    repo = MagicMock(spec=TemplateStagingRepository)

    repo.get_recent_by_query.return_value = {
        "scope": "TPMT_SPS",
        "period_days": 30,
        "total_runs": 5,
        "successes": 4,
        "failures": 1,
        "success_rate": 80.0,
        "last_success": "2025-06-01 12:00:00",
        "last_failure": "2025-05-28 09:00:00",
        "runs": [],
    }

    repo.get_failure_summary.return_value = {
        "total_failures": 3,
        "period_days": 30,
        "top_templates": [{"template_name": "TPMT_SPS", "failure_count": 2}],
        "top_dids": [{"did": "DEAL001", "failure_count": 1}],
        "error_groups": [],
        "affected_servicers": [296],
        "failures": [],
    }

    repo.get_duration_stats.return_value = {
        "period_days": 30,
        "templates": [
            {"template_name": "TPMT_SPS", "total_runs": 10,
             "avg_seconds": 45.0, "min_seconds": 10.0, "max_seconds": 120.0},
        ],
        "outliers": [],
    }

    repo.get_manual_queue_stats.return_value = {
        "total_count": 100,
        "manual_count": 20,
        "automated_count": 80,
        "manual_percentage": 20.0,
        "top_manual_templates": [],
        "manual_operators": [],
        "period_days": 30,
    }

    repo.trace_by_filepath.return_value = [{
        "file_path": "M:\\DealFolder\\Data\\file.xlsx",
        "source_type": "email",
        "template_name": "TPMT_SPS",
        "did": "DEAL001",
        "result_code": 0,
    }]

    repo.search.return_value = [{
        "TemplateProcessID": 42,
        "TemplateName": "TPMT_SPS",
        "DID": "DEAL001",
        "ResultCode": 0,
    }]

    repo.get_processing_for_servicer.return_value = {
        "servicer_id": 296,
        "templates": [{"TemplateName": "TPMT_SPS", "total_runs": 10}],
        "recent_runs": [],
    }

    repo.get_pipeline_status.return_value = {
        "query": "296",
        "config_layer": None,
        "mapping_layer": None,
        "execution_layer": {"total_runs": 10, "success_rate": 80.0},
        "gaps": [],
        "health_score": 80.0,
    }

    repo.close = MagicMock()

    return repo


@pytest.fixture
def sample_template_runs():
    """Sample TemplateRun instances for unit tests."""
    from backend.db.ts_models import TemplateRun
    from datetime import datetime, timedelta

    base = datetime(2025, 6, 1, 10, 0, 0)
    return [
        TemplateRun(
            template_process_id=i,
            template_name=f"TPMT_SPS_{i}",
            file_path=f"M:\\DealFolder\\Data\\file_{i}.xlsx",
            did=f"DEAL{i:03d}",
            start_time=base + timedelta(hours=i),
            end_time=base + timedelta(hours=i, seconds=45),
            result_code=0 if i % 3 != 0 else 1,
            servicer_id=296,
            source_process="EmailMonitor",
            data_source="EmailMonitor: frpmonitor@usbank.com",
        )
        for i in range(1, 6)
    ]
