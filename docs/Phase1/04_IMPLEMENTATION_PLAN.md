# Phase 1: Implementation Plan
## Step-by-Step Execution Guide

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Proposal — Pending Approval  
**Total Estimated Effort:** 26–37 hours (7–10 work days)

---

## Table of Contents
1. [Implementation Principles](#implementation-principles)
2. [Prerequisites](#prerequisites)
3. [Sprint Structure](#sprint-structure)
4. [Step-by-Step Build Order](#step-by-step-build-order)
5. [Verification Checkpoints](#verification-checkpoints)
6. [Rollback Strategy](#rollback-strategy)

---

## Implementation Principles

1. **Bottom-up build order** — Build leaves first (models/config), then services, then CLI, then extension
2. **Test immediately** — Every module gets unit tests before moving to the next file
3. **One layer at a time** — Complete all Python backend before starting JavaScript extension
4. **JSON correctness first** — Verify every CLI command produces valid JSON before integrating with extension
5. **Manual QA gate** — Run full test suite between sprints; never proceed with red tests

---

## Prerequisites

Before starting Sprint 1:

| Item | Description | Verification |
|------|-------------|-------------|
| Python 3.10+ | Installed and on PATH | `python --version` |
| Node.js 18+ | Installed | `node --version` |
| VS Code 1.95+ | Required for Chat Participant API | `code --version` |
| pyodbc | `pip install pyodbc` | `python -c "import pyodbc"` |
| MySQL ODBC driver | Local dev | MySQL Connector/ODBC 8.0 |
| pytest | `pip install pytest pytest-cov` | `pytest --version` |
| Git | Repository initialized | `git status` |
| Settings.xml copies | Email + SFTP settings available for testing | File exists |
| App Logs | At least 3 sample log files | Files exist |

### Workspace Preparation

```powershell
cd FRP_Agent
python -m venv .venv
.venv\Scripts\Activate
pip install pyodbc pytest pytest-cov
mkdir -p backend\xml backend\db backend\logs backend\backup backend\common
mkdir -p cli config tests\xml tests\db tests\logs tests\backup tests\cli
```

---

## Sprint Structure

### Sprint 1: Python Data Models & Configuration (3–4 hours)
Files: 8 | Tests: 15+

### Sprint 2: XML Parser & Validator (5–7 hours)
Files: 3 | Tests: 40+

### Sprint 3: XML Writer & Backup Manager (3–4 hours)
Files: 3 | Tests: 20+

### Sprint 4: Database Connector & Deal Repository (4–5 hours)
Files: 6 | Tests: 20+

### Sprint 5: Log Parser & SQLite Indexer (5–7 hours)
Files: 3 | Tests: 30+

### Sprint 6: CLI Entry Point (3–4 hours)
Files: 1 | Tests: 15+

### Sprint 7: VS Code Extension Shell (3–6 hours)
Files: 6 | Tests: 10+

---

## Step-by-Step Build Order

### Sprint 1: Python Data Models & Configuration

**Goal:** Establish all data models, config, and project structure.

#### Step 1.1: Create project skeleton

```
Action: Create all __init__.py files and directory structure
Duration: 15 min
```

Files to create:
```
backend/__init__.py          → empty
backend/xml/__init__.py      → empty
backend/db/__init__.py       → empty
backend/logs/__init__.py     → empty
backend/backup/__init__.py   → empty
backend/common/__init__.py   → empty
cli/__init__.py              → empty
config/__init__.py           → empty
```

Verify: `python -c "import backend; import cli; import config"` ✅

#### Step 1.2: Create shared response model

```
File: backend/common/models.py
Duration: 15 min
Spec: See 03_TECHNICAL_DESIGN.md §2 — CliResponse dataclass
```

Test file: `tests/test_common_models.py`
```python
def test_cli_response_defaults():
    r = CliResponse()
    assert r.success is True
    assert r.command == ""
    assert r.data is None
    assert r.errors == []

def test_cli_response_to_dict():
    r = CliResponse(success=False, command="test", errors=["err1"])
    d = r.to_dict()
    assert d["success"] is False
    assert "err1" in d["errors"]
```

Verify: `pytest tests/test_common_models.py -v` ✅

#### Step 1.3: Create XML data models

```
File: backend/xml/models.py
Duration: 30 min
Spec: See 03_TECHNICAL_DESIGN.md §2 — EmailJob, SftpJob, ValidationResult
```

Test file: `tests/xml/test_models.py`
```python
def test_email_job_matches_name():
    job = EmailJob(name="COOFS_LateMoney", mailbox="a@b.com", folder="Inbox", sme="x@y.com")
    assert job.matches_query("coofs") is True
    assert job.matches_query("zzz") is False

def test_sftp_job_serialization():
    job = SftpJob(name="Ocwen", path="/sftp/ocwen", servicer_id=150, dsn="OcwenSFTP", sme="a@b.com")
    d = job.to_dict()
    assert d["name"] == "Ocwen"
    assert d["servicer_id"] == 150
    assert d["xml_type"] == "sftp"

def test_email_job_filters_search():
    job = EmailJob(name="Test", mailbox="a@b.com", folder="Inbox", sme="x@y.com",
                   filters={"From": "rptEntrust@myco.com"}, parsers={"CMS": "cms.*"})
    assert job.matches_query("rptentrust") is True
    assert job.matches_query("cms") is True

def test_email_job_shelf_level():
    job = EmailJob(name="ShelfJob", mailbox="a@b.com", folder="Inbox", sme="x@y.com",
                   servicer_id=None)
    assert job.servicer_id is None
```

Verify: `pytest tests/xml/test_models.py -v` ✅

#### Step 1.4: Create log data models

```
File: backend/logs/models.py
Duration: 15 min
Spec: See 03_TECHNICAL_DESIGN.md §2 — LogEvent dataclass
```

Test file: `tests/logs/test_models.py`

Verify: `pytest tests/logs/ -v` ✅

#### Step 1.5: Create configuration module

```
File: config/settings.py
Duration: 20 min
Spec: See 03_TECHNICAL_DESIGN.md §12 — FrpConfig dataclass
```

Test: Set env vars, call `FrpConfig.from_env()`, verify values.

Verify: `pytest tests/test_config.py -v` ✅

#### Step 1.6: Create secrets template files

```
Files: config/secrets_mysql.json, config/secrets_mssql.json
Duration: 10 min
Add to .gitignore: config/secrets_*.json
```

Contents: See 03_TECHNICAL_DESIGN.md §5 (connection files).

#### Step 1.7: Create .gitignore

```
File: .gitignore
Duration: 5 min
```

```gitignore
__pycache__/
*.pyc
.venv/
*.egg-info/
config/secrets_*.json
frp_logs.db
*.vsix
node_modules/
out/
bin/
```

**Sprint 1 Gate:** `pytest tests/ -v --tb=short` → All green

---

### Sprint 2: XML Parser & Validator

**Goal:** Parse both email and SFTP Settings.xml files. Validate structure.

#### Step 2.1: Create test fixtures

```
Directory: tests/fixtures/
Duration: 30 min
```

Files to create:
```
tests/fixtures/email_settings_valid.xml     → 3–5 sample email jobs
tests/fixtures/email_settings_empty.xml     → Valid XML, empty MailboxCollection
tests/fixtures/email_settings_invalid.xml   → Malformed XML
tests/fixtures/sftp_settings_valid.xml      → 2–3 sample SFTP jobs
tests/fixtures/email_settings_missing.xml   → Jobs with missing required fields
```

`email_settings_valid.xml` structure:
```xml
<?xml version="1.0" encoding="utf-8"?>
<Settings>
  <DisableJob>False</DisableJob>
  <Server>prod-server</Server>
  <Db>ServicingDB</Db>
  <StagingServer>staging-server</StagingServer>
  <StagingDb>StagingDB</StagingDb>
  <HashiAPI>https://hashi.example.com/v1</HashiAPI>
  <MapDrives>
    <P>\\nas\portfolios</P>
  </MapDrives>
  <Outlook>
    <Email>monitor@example.com</Email>
    <MailboxCollection>
      <TestJob_ValidFull>
        <Mailbox>test@example.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>sme@example.com</SME>
        <LastEmail>2026-01-15_08:30:00</LastEmail>
        <SaveLocation>P:\{DealFolder}\{YYYY}\{M}\Reports</SaveLocation>
        <Filters>
          <From>sender@partner.com</From>
          <Attachments>.xls</Attachments>
          <Subject>Monthly Report</Subject>
        </Filters>
        <Parsers>
          <CMS>cms.*report</CMS>
        </Parsers>
        <ServicerID>150</ServicerID>
        <QueueOneFile>True</QueueOneFile>
        <Templates>
          <FileLoader>Entrust_FileLoader</FileLoader>
        </Templates>
        <DayAdjust>-1</DayAdjust>
      </TestJob_ValidFull>
      <TestJob_ShelfLevel>
        <Mailbox>shelf@example.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>sme2@example.com</SME>
        <SaveLocation>P:\Shelf\Reports</SaveLocation>
        <Filters>
          <Subject>Shelf Report</Subject>
        </Filters>
        <Parsers>
          <MoveFile>.*</MoveFile>
        </Parsers>
      </TestJob_ShelfLevel>
      <TestJob_Minimal>
        <Mailbox>min@example.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>sme3@example.com</SME>
        <SaveLocation>P:\Min</SaveLocation>
        <Parsers>
          <MoveFile>.*</MoveFile>
        </Parsers>
      </TestJob_Minimal>
    </MailboxCollection>
  </Outlook>
</Settings>
```

#### Step 2.2: Implement XML parser core

```
File: backend/xml/parser.py
Duration: 2–3 hours
Spec: See 03_TECHNICAL_DESIGN.md §3 — SettingsXmlParser class
```

Build order within the file:
1. `__init__()` — Read/parse XML
2. `detect_xml_type()` — Detect email vs SFTP
3. `_parse_email_job()` — Single job extraction  
4. `_parse_sftp_job()` — Single SFTP job extraction
5. `get_all_jobs()` — Full job list
6. `search_jobs()` — Filtered search
7. `get_infrastructure()` — Infrastructure settings
8. `get_element_tree()` — Tree access for writer

Test file: `tests/xml/test_parser.py`

Key tests:
```python
class TestSettingsXmlParser:
    def test_detect_email_type(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        assert parser.detect_xml_type() == "email"
    
    def test_detect_sftp_type(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        assert parser.detect_xml_type() == "sftp"
    
    def test_get_all_email_jobs(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        assert len(jobs) == 3
        assert all(isinstance(j, EmailJob) for j in jobs)
    
    def test_email_job_fields(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        full = next(j for j in jobs if j.name == "TestJob_ValidFull")
        assert full.mailbox == "test@example.com"
        assert full.servicer_id == 150
        assert full.queue_one_file is True
        assert full.day_adjust == -1
        assert "CMS" in full.parsers
        assert "FileLoader" in full.templates
    
    def test_shelf_level_job_no_servicerid(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        shelf = next(j for j in jobs if j.name == "TestJob_ShelfLevel")
        assert shelf.servicer_id is None
    
    def test_search_by_mailbox(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("shelf@example")
        assert len(results) == 1
        assert results[0].name == "TestJob_ShelfLevel"
    
    def test_search_shelf_level_keyword(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("shelf-level")
        assert all(j.servicer_id is None for j in results)
    
    def test_search_by_parser(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("cms")
        assert len(results) >= 1
    
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            SettingsXmlParser("/nonexistent/path.xml")
    
    def test_malformed_xml(self, invalid_fixture):
        with pytest.raises(ET.ParseError):
            SettingsXmlParser(invalid_fixture)
    
    def test_get_infrastructure(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        infra = parser.get_infrastructure()
        assert infra["server"] == "prod-server"
        assert infra["db"] == "ServicingDB"
```

Verify: `pytest tests/xml/test_parser.py -v --tb=short` ✅

#### Step 2.3: Implement XML validator

```
Add to: backend/xml/parser.py (validate method)
Duration: 1–2 hours
Spec: See 03_TECHNICAL_DESIGN.md §3 — validate() method with E001–E013, W001–W005, I001–I006
```

Test file: `tests/xml/test_validator.py`

Key tests:
```python
class TestXmlValidation:
    def test_valid_file_no_errors(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate()
        assert result.valid is True
        assert len(result.errors) == 0
    
    def test_missing_required_fields(self, missing_fixture):
        parser = SettingsXmlParser(missing_fixture)
        result = parser.validate()
        assert result.valid is False
        assert any("E004" in e or "E005" in e or "E006" in e for e in result.errors)
    
    def test_duplicate_job_names(self, duplicate_fixture):
        parser = SettingsXmlParser(duplicate_fixture)
        result = parser.validate()
        assert any("E008" in e for e in result.errors)
    
    def test_servicer_cross_reference(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate(db_servicer_ids={150, 200})
        # ServicerID 150 exists, no W001 for that job
        assert result.valid is True
    
    def test_unknown_servicer_warning(self, email_fixture):
        # Pass empty set so ServicerID 150 becomes unknown
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate(db_servicer_ids=set())
        assert any("W001" in w for w in result.warnings)
    
    def test_info_messages(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate()
        assert result.job_count == 3
        assert any("I001" in i for i in result.info)
```

Verify: `pytest tests/xml/ -v --tb=short` ✅

**Sprint 2 Gate:** Parse real Settings.ps1 (copy to .xml) → verified job count matches expected ~48

---

### Sprint 3: XML Writer & Backup Manager

**Goal:** Write modified XML back to disk with automatic backups.

#### Step 3.1: Implement XmlWriter

```
File: backend/xml/writer.py
Duration: 1 hour
Spec: See 03_TECHNICAL_DESIGN.md §4 — XmlWriter class
```

Test file: `tests/xml/test_writer.py`
```python
class TestXmlWriter:
    def test_save_creates_backup(self, email_fixture, tmp_path):
        # Copy fixture to tmp_path
        settings_path = tmp_path / "Settings.xml"
        shutil.copy(email_fixture, settings_path)
        
        parser = SettingsXmlParser(str(settings_path))
        tree = parser.get_element_tree()
        writer = XmlWriter(str(settings_path))
        result = writer.save(tree)
        
        assert result["success"] is True
        assert os.path.exists(result["backup_path"])
        assert "backup" in result["backup_path"]
    
    def test_backup_filename_format(self, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        settings_path.write_text("<Settings></Settings>")
        writer = XmlWriter(str(settings_path))
        fname = writer._generate_backup_filename()
        assert re.match(r'Settings_\d{8}_\d{6}\.xml', fname)
    
    def test_save_preserves_xml_content(self, email_fixture, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        shutil.copy(email_fixture, settings_path)
        
        parser = SettingsXmlParser(str(settings_path))
        tree = parser.get_element_tree()
        writer = XmlWriter(str(settings_path))
        writer.save(tree)
        
        # Re-parse and verify same content
        parser2 = SettingsXmlParser(str(settings_path))
        assert len(parser2.get_all_jobs()) == len(parser.get_all_jobs())
    
    def test_backup_dir_created(self, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        settings_path.write_text("<Settings></Settings>")
        backup_dir = tmp_path / "backup"
        assert not backup_dir.exists()
        
        writer = XmlWriter(str(settings_path))
        tree = ET.parse(str(settings_path))
        writer.save(tree)
        
        assert backup_dir.exists()
```

Verify: `pytest tests/xml/test_writer.py -v` ✅

#### Step 3.2: Implement BackupManager

```
File: backend/backup/manager.py
Duration: 1 hour
Spec: See 03_TECHNICAL_DESIGN.md §4 — BackupManager class
```

Test file: `tests/backup/test_manager.py`
```python
class TestBackupManager:
    def test_list_backups_empty(self, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        settings_path.write_text("<Settings/>")
        mgr = BackupManager(str(settings_path))
        assert mgr.list_backups() == []
    
    def test_list_backups_sorted(self, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        settings_path.write_text("<Settings/>")
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        (backup_dir / "Settings_20260201_100000.xml").write_text("<a/>")
        (backup_dir / "Settings_20260202_100000.xml").write_text("<b/>")
        
        mgr = BackupManager(str(settings_path))
        backups = mgr.list_backups()
        assert len(backups) == 2
        assert "20260202" in backups[0]["filename"]  # newest first
    
    def test_restore_backup(self, email_fixture, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        shutil.copy(email_fixture, settings_path)
        
        # Create a backup
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "Settings_20260201_100000.xml"
        backup_file.write_text("<Settings><Restored/></Settings>")
        
        mgr = BackupManager(str(settings_path))
        result = mgr.restore("Settings_20260201_100000.xml")
        
        assert result["success"] is True
        # Current file should now contain <Restored/>
        content = settings_path.read_text()
        assert "<Restored/>" in content or "Restored" in content
    
    def test_get_backup_count(self, tmp_path):
        settings_path = tmp_path / "Settings.xml"
        settings_path.write_text("<Settings/>")
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        (backup_dir / "Settings_20260201_100000.xml").write_text("<a/>")
        (backup_dir / "Settings_20260202_100000.xml").write_text("<b/>")
        
        mgr = BackupManager(str(settings_path))
        assert mgr.get_backup_count() == 2
```

Verify: `pytest tests/backup/ -v` ✅

**Sprint 3 Gate:** Verify round-trip: parse → modify → save → backup exists → re-parse succeeds

---

### Sprint 4: Database Connector & Deal Repository

**Goal:** Connect to MySQL (dev) or MSSQL (prod), query tblExternalDIDRef.

#### Step 4.1: Create connection modules

```
Files: backend/db/connection.py, backend/db/connection_mysql.py, backend/db/connection_mssql.py
Duration: 1 hour
Spec: See 03_TECHNICAL_DESIGN.md §5
```

#### Step 4.2: Create SQL queries

```
File: backend/db/queries.py
Duration: 20 min
Spec: See 03_TECHNICAL_DESIGN.md §5
```

#### Step 4.3: Implement DealRepository

```
File: backend/db/deal_repo.py
Duration: 1.5 hours
Spec: See 03_TECHNICAL_DESIGN.md §6
```

Test file: `tests/db/test_deal_repo.py`

**Note on testing:** DB tests require either:
- A running MySQL instance with test data, OR
- Mocked pyodbc connections

Recommended approach: **Mock-based tests** for CI, integration tests for manual verification.

```python
class TestDealRepository:
    @patch('backend.db.connection.get_connection')
    def test_servicer_exists_true(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (150,)
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        with DealRepository(prod_mode=False) as repo:
            assert repo.servicer_exists(150) is True
        
        mock_cursor.execute.assert_called_once()
    
    @patch('backend.db.connection.get_connection')
    def test_servicer_exists_false(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        with DealRepository(prod_mode=False) as repo:
            assert repo.servicer_exists(9999) is False
    
    @patch('backend.db.connection.get_connection')
    def test_get_deals_by_company(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.description = [('DID',), ('ImportDID',), ('CompanyID',)]
        mock_cursor.fetchall.return_value = [
            ('DealA', 'IMP001', 150),
            ('DealB', 'IMP002', 150),
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        with DealRepository(prod_mode=False) as repo:
            deals = repo.get_deals_by_company(150)
            assert len(deals) == 2
            assert deals[0]["DID"] == "DealA"
    
    @patch('backend.db.connection.get_connection')
    def test_get_all_servicer_ids(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(150,), (569,), (3722,)]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        with DealRepository(prod_mode=False) as repo:
            ids = repo.get_all_servicer_ids()
            assert ids == {150, 569, 3722}
```

Verify: `pytest tests/db/ -v` ✅

**Sprint 4 Gate:** Run integration test against local MySQL with real tblExternalDIDRef data (manual).

---

### Sprint 5: Log Parser & SQLite Indexer

**Goal:** Parse email monitor logs, store in SQLite, enable fast querying.

#### Step 5.1: Create log parser

```
File: backend/logs/parser.py
Duration: 2–3 hours
Spec: See 03_TECHNICAL_DESIGN.md §7
```

Test fixtures needed: Copy 2–3 real log files to `tests/fixtures/logs/`

Test file: `tests/logs/test_parser.py`
```python
class TestLogFileParser:
    def test_parse_real_log(self, sample_log_path):
        parser = LogFileParser("email")
        events = parser.parse_file(sample_log_path)
        assert len(events) > 0
        assert all(isinstance(e, LogEvent) for e in events)
    
    def test_job_start_event(self, sample_log_path):
        parser = LogFileParser("email")
        events = parser.parse_file(sample_log_path)
        starts = [e for e in events if e.event_type == "job_start"]
        assert len(starts) > 0
        assert starts[0].job_name is not None
    
    def test_did_failure_detection(self, sample_log_with_failures):
        parser = LogFileParser("email")
        events = parser.parse_file(sample_log_with_failures)
        failures = [e for e in events if e.event_type == "did_mapping_failed"]
        assert len(failures) > 0
    
    def test_timestamp_extraction(self):
        parser = LogFileParser("email")
        result = parser._extract_timestamp(
            "2026-02-02 10:20:03.864:\tStarting Outlook download..."
        )
        assert result is not None
        assert result[0] == "2026-02-02 10:20:03.864"
    
    def test_skips_header_lines(self, sample_log_path):
        parser = LogFileParser("email")
        events = parser.parse_file(sample_log_path)
        # No events should have ## prefix content
        assert all("##" not in (e.raw_line or "") for e in events)
```

#### Step 5.2: Implement SQLite indexer

```
File: backend/logs/indexer.py
Duration: 2–3 hours
Spec: See 03_TECHNICAL_DESIGN.md §8
```

Test file: `tests/logs/test_indexer.py`
```python
class TestLogIndexer:
    def test_create_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        indexer = LogIndexer(db_path)
        # Verify tables exist
        cursor = indexer.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "log_events" in tables
        assert "indexed_files" in tables
        assert "index_metadata" in tables
        indexer.close()
    
    def test_sync_indexes_files(self, tmp_path, sample_log_folder):
        db_path = str(tmp_path / "test.db")
        indexer = LogIndexer(db_path)
        result = indexer.sync(sample_log_folder, "email")
        assert result["files_processed"] > 0
        assert result["events_indexed"] > 0
        indexer.close()
    
    def test_sync_skips_already_indexed(self, tmp_path, sample_log_folder):
        db_path = str(tmp_path / "test.db")
        indexer = LogIndexer(db_path)
        r1 = indexer.sync(sample_log_folder, "email")
        r2 = indexer.sync(sample_log_folder, "email")
        assert r2["files_skipped"] == r1["files_processed"]
        assert r2["files_processed"] == 0
        indexer.close()
    
    def test_query_by_job(self, tmp_path, populated_indexer):
        events = populated_indexer.query_events(job_name="COOFS_LateMoney")
        # Assuming test data has this job
        for e in events:
            assert e["job_name"] == "COOFS_LateMoney"
    
    def test_get_sync_status(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        indexer = LogIndexer(db_path)
        status = indexer.get_sync_status()
        assert status["total_events"] == 0
        assert status["schema_version"] == "1.0"
        indexer.close()
    
    def test_retention_purge(self, tmp_path, populated_indexer):
        # Events older than 0 months should be purged (all of them)
        result = populated_indexer.sync(populated_indexer.db_path, "email", retention_months=0)
        status = populated_indexer.get_sync_status()
        # Expect events purged
```

Verify: `pytest tests/logs/ -v` ✅

**Sprint 5 Gate:** Sync real App Logs folder → verify event counts, query results

---

### Sprint 6: CLI Entry Point

**Goal:** Wire all backend modules into the CLI with JSON output.

#### Step 6.1: Implement CLI main

```
File: cli/main.py
Duration: 2–3 hours
Spec: See 03_TECHNICAL_DESIGN.md §9
```

Test file: `tests/cli/test_main.py`
```python
class TestCliMain:
    def test_search_jobs_output(self, email_fixture, capsys):
        sys.argv = [
            "frp-agent", "search_jobs",
            "--query", "test",
            "--settings-path", email_fixture,
        ]
        main()
        output = capsys.readouterr().out
        result = json.loads(output)
        assert result["success"] is True
        assert "jobs" in result["data"]
    
    def test_validate_xml_output(self, email_fixture, capsys):
        sys.argv = [
            "frp-agent", "validate_xml",
            "--settings-path", email_fixture,
        ]
        main()
        output = capsys.readouterr().out
        result = json.loads(output)
        assert result["success"] is True
        assert "valid" in result["data"]
    
    def test_status_command(self, capsys):
        sys.argv = ["frp-agent", "status"]
        main()
        output = capsys.readouterr().out
        result = json.loads(output)
        assert result["success"] is True
    
    def test_unknown_command(self, capsys):
        sys.argv = ["frp-agent", "unknown_cmd"]
        with pytest.raises(SystemExit):
            main()
    
    def test_output_is_valid_json(self, email_fixture, capsys):
        """Critical: ALL stdout must be valid JSON."""
        sys.argv = [
            "frp-agent", "search_jobs",
            "--query", "x",
            "--settings-path", email_fixture,
        ]
        main()
        output = capsys.readouterr().out
        json.loads(output)  # Must not raise
```

**CLI smoke test (manual):**
```powershell
python -m cli.main search_jobs --query "test" --settings-path "tests/fixtures/email_settings_valid.xml" | ConvertFrom-Json
python -m cli.main validate_xml --settings-path "tests/fixtures/email_settings_valid.xml" | ConvertFrom-Json
python -m cli.main status | ConvertFrom-Json
```

Verify: All 3 commands return valid JSON with `success: true` ✅

**Sprint 6 Gate:** `pytest tests/ -v --tb=short` → ALL tests green (100+ tests)

---

### Sprint 7: VS Code Extension Shell

**Goal:** Create the VSIX extension scaffolding with chat participant.

#### Step 7.1: Create extension package.json

```
File: extension/package.json
Duration: 30 min
Spec: See VSCODE_CHAT_AGENT_BOOTSTRAP.md §3 + adapted for FRP
```

Key sections:
- `chatParticipants`: id="frp", name="frp", fullName="FRP Agent"
- `commands`: `/jobs`, `/deals`, `/logs`, `/deploy`, `/triage` (stub), `/analyze` (stub)
- `configuration`: All 8 frpAgent.* settings
- `engines.vscode`: "^1.95.0"

#### Step 7.2: Create extension entry point

```
File: extension/extension.js
Duration: 30 min
```

Responsibilities:
- `activate()`: Create output channel, init backend runner, register participant
- `deactivate()`: Cleanup

#### Step 7.3: Create backend bridge

```
Files: extension/lib/frp_backend.js, extension/copilot/tool.js
Duration: 1 hour
Spec: See 03_TECHNICAL_DESIGN.md §10–11
```

#### Step 7.4: Create chat participant handler

```
File: extension/chat/participant.js
Duration: 2–3 hours
Spec: See 03_TECHNICAL_DESIGN.md §11
```

Phase 1 commands to implement:
- `/jobs` → search (default), validate
- `/deals` → servicer dossier
- `/logs` → sync
- `/deploy` → save, list backups

Stubs for Phase 2+:
- `/triage` → "Coming in Phase 3"
- `/analyze` → "Coming in Phase 4"

#### Step 7.5: Create command handlers

```
Files: extension/commands/sync.js, extension/commands/status.js
Duration: 30 min
```

#### Step 7.6: Test extension manually

```
Method: Press F5 in VS Code to launch Extension Development Host
Test: @frp /jobs search test → should show results
Test: @frp /logs sync → should sync logs
Test: @frp /deploy backups → should list backups
```

**Sprint 7 Gate:** F5 → Extension loads → @frp responds

---

## Verification Checkpoints

| Checkpoint | When | Criteria |
|-----------|------|---------|
| CP-1 | After Sprint 1 | All models serialize to JSON, config loads from env |
| CP-2 | After Sprint 2 | Parse real Settings.ps1 (as .xml), job count matches |
| CP-3 | After Sprint 3 | Round-trip: parse → save → backup → re-parse = identical |
| CP-4 | After Sprint 4 | Query real tblExternalDIDRef via MySQL |
| CP-5 | After Sprint 5 | Sync real App Logs, query events, verify counts |
| CP-6 | After Sprint 6 | All CLI commands return valid JSON |
| CP-7 | After Sprint 7 | F5 extension → @frp responds with real data |
| CP-FINAL | End | All 100+ tests green, F5 demo of all 6 Phase 1 UCs |

---

## Rollback Strategy

| Issue | Rollback |
|-------|----------|
| Bad XML write | Restore from backup/ folder (automatic) |
| Corrupt SQLite | Delete frp_logs.db, re-sync |
| DB connection broken | All non-DB UCs still work (graceful degradation) |
| Extension crash | `code --disable-extensions` + check output panel |
| Python dependency issue | Recreate venv from requirements.txt |

### Disaster Recovery

If a sprint goes wrong:
1. `git stash` current changes
2. Verify previous sprint's tests still pass
3. Investigate the issue
4. `git stash pop` when ready to retry

### Minimum Viable Phase 1

If time is constrained, the absolute minimum deliverable is:

1. **XML Parser** (Sprint 2) — Can search and validate jobs
2. **CLI** (Sprint 6) — Can execute from command line
3. **Extension shell** (Sprint 7) — @frp /jobs works

Everything else (DB, logs, backups) can be deferred.
