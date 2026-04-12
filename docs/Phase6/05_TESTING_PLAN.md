# Phase 6: Testing Plan
## FRP Agent — SQLite Job Cache + Multi-Agent Framework Retrofit

**Document Version:** 1.0  
**Date:** March 4, 2026  
**Status:** Planning  
**Companion:** [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)  
**Existing Tests:** 655 passed  
**Target:** 680–690 passed, 0 failed

---

## Table of Contents
1. [Test Architecture](#test-architecture)  
2. [Test Principles](#test-principles)  
3. [Fixtures](#fixtures)  
4. [Unit Tests — XmlJobIndex](#unit-tests--xmljobindex)  
5. [Integration Tests — CLI Commands](#integration-tests--cli-commands)  
6. [Regression Tests](#regression-tests)  
7. [Manual QA Checklist](#manual-qa-checklist)  
8. [Coverage Targets](#coverage-targets)  
9. [Test Execution Order](#test-execution-order)

---

## Test Architecture

```
tests/
├── conftest.py                        ← shared fixtures (existing)
├── db/
│   ├── test_xml_index.py              ← NEW: ~25–35 tests
│   ├── test_deal_repo.py              ← existing (unchanged)
│   └── test_template_staging_repo_p5.py ← existing (unchanged)
├── cli/
│   ├── test_cli_commands.py           ← existing (unchanged)
│   ├── test_cli_staging.py            ← existing (unchanged)
│   └── test_cli_xml_cache.py          ← NEW: ~8–12 tests (CLI integration)
├── xml/
│   ├── test_parser.py                 ← existing (unchanged)
│   ├── test_writer.py                 ← existing (unchanged)
│   └── test_crud.py                   ← existing (unchanged)
├── triage/
│   ├── test_analyzer.py               ← existing (unchanged)
│   └── test_analyzer_crossref.py      ← existing (unchanged)
└── ... (all other test dirs unchanged)
```

**Key decisions:**
- `test_xml_index.py` tests the `XmlJobIndex` class in isolation (in-memory SQLite)
- `test_cli_xml_cache.py` tests CLI commands with cache enabled (mock/tmp_path)
- All existing tests remain untouched and continue passing
- Framework files (WS-B) are declarative markdown — not testable via pytest

---

## Test Principles

1. **In-memory SQLite for speed.** All `XmlJobIndex` tests use `":memory:"` as `db_path` — no disk I/O.
2. **Mock XML via `tmp_path`.** Create minimal Settings.xml files as test fixtures, not production files.
3. **Same fixtures pattern as existing tests.** Use `conftest.py` for shared fixtures, `@pytest.fixture` for test-specific ones.
4. **Output format parity.** Verify that SQLite-backed responses match XML-backed responses field-for-field.
5. **Test fallback paths.** Verify that commands work when cache is absent, stale, or corrupted.
6. **No external dependencies.** No MySQL, no network, no real Settings.xml in unit tests.

---

## Fixtures

### New conftest fixtures (or local to test files)

```python
# tests/db/test_xml_index.py — local fixtures

import json
import os
import pytest
import xml.etree.ElementTree as ET


@pytest.fixture
def email_xml(tmp_path):
    """Create a minimal email Settings.xml with 3 jobs."""
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <Outlook>
    <MailboxCollection>
      <TestJob_Alpha>
        <ServicerID>10</ServicerID>
        <Mailbox>test@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>John.Doe</SME>
        <SaveLocation>M:\\TestDeal\\Data\\</SaveLocation>
        <LastEmail />
        <QueueOneFile>True</QueueOneFile>
        <Filter><From>reports@alpha.com</From></Filter>
        <Parser><DetachFileSubject><Keyword>monthly</Keyword></DetachFileSubject></Parser>
        <Template><Main>TestScrubber_Alpha</Main></Template>
      </TestJob_Alpha>
      <TestJob_Beta>
        <ServicerID>20</ServicerID>
        <Mailbox>test@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>Jane.Doe</SME>
        <SaveLocation>M:\\BetaDeal\\Data\\</SaveLocation>
        <QueueOneFile>True</QueueOneFile>
        <Filter><From>data@beta.com</From></Filter>
        <Parser><DetachFile><Keyword>report</Keyword></DetachFile></Parser>
        <Template><Main>TestScrubber_Beta</Main></Template>
      </TestJob_Beta>
      <ShelfJob_NoSID>
        <Mailbox>test@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>Jim.Shelf</SME>
        <SaveLocation>M:\\Shelf\\Data\\</SaveLocation>
        <Filter><From>info@shelf.com</From></Filter>
      </ShelfJob_NoSID>
    </MailboxCollection>
  </Outlook>
</root>"""
    xml_file = tmp_path / "email_settings.xml"
    xml_file.write_text(xml_content, encoding="utf-8")
    return str(xml_file)


@pytest.fixture
def sftp_xml(tmp_path):
    """Create a minimal SFTP Settings.xml with 2 jobs."""
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <Outlook>
    <FolderCollection>
      <SftpJob_Gamma>
        <ServicerID>30</ServicerID>
        <RemotePath>/incoming/gamma/</RemotePath>
        <DSN>SFTP_Gamma</DSN>
        <SME>Bob.Sftp</SME>
        <SaveLocation>M:\\GammaDeal\\Data\\</SaveLocation>
        <SkipList>*.tmp</SkipList>
        <Template><Main>SFTP_Gamma_Scrub</Main></Template>
      </SftpJob_Gamma>
      <SftpJob_Delta>
        <ServicerID>40</ServicerID>
        <RemotePath>/incoming/delta/</RemotePath>
        <DSN>SFTP_Delta</DSN>
        <SME>Alice.Sftp</SME>
        <SaveLocation>M:\\DeltaDeal\\Data\\</SaveLocation>
        <Template><Main>SFTP_Delta_Scrub</Main></Template>
      </SftpJob_Delta>
    </FolderCollection>
  </Outlook>
</root>"""
    xml_file = tmp_path / "sftp_settings.xml"
    xml_file.write_text(xml_content, encoding="utf-8")
    return str(xml_file)


@pytest.fixture
def index(tmp_path):
    """Create an XmlJobIndex with an in-memory or tmp_path SQLite DB."""
    from backend.db.xml_index import XmlJobIndex
    db_path = str(tmp_path / "test_cache.db")
    idx = XmlJobIndex(db_path)
    yield idx
    idx.close()
```

---

## Unit Tests — XmlJobIndex

### `tests/db/test_xml_index.py`

#### TestSchemaCreation (3 tests)

| # | Test Name | Verifies |
|---|---|---|
| 1 | `test_tables_created` | `email_jobs`, `sftp_jobs`, `cache_metadata` tables exist |
| 2 | `test_indexes_created` | All 5 indexes exist (`idx_email_jobs_servicer`, etc.) |
| 3 | `test_schema_version_seeded` | `cache_metadata` contains `schema_version = "1"` |

```python
class TestSchemaCreation:
    def test_tables_created(self, index):
        tables = index._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        assert "cache_metadata" in names
        assert "email_jobs" in names
        assert "sftp_jobs" in names

    def test_indexes_created(self, index):
        indexes = index._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        names = {i["name"] for i in indexes}
        assert "idx_email_jobs_servicer" in names
        assert "idx_email_jobs_mailbox" in names
        assert "idx_email_jobs_sender" in names
        assert "idx_sftp_jobs_servicer" in names
        assert "idx_sftp_jobs_dsn" in names

    def test_schema_version_seeded(self, index):
        row = index._conn.execute(
            "SELECT value FROM cache_metadata WHERE key='schema_version'"
        ).fetchone()
        assert row["value"] == "1"
```

#### TestRebuildEmail (5 tests)

| # | Test Name | Verifies |
|---|---|---|
| 4 | `test_rebuild_email_count` | 3 email jobs loaded |
| 5 | `test_rebuild_email_hash_stored` | `email_hash` key exists in metadata |
| 6 | `test_rebuild_email_fields` | Job fields correctly stored (servicer_id, mailbox, sender, scrubber) |
| 7 | `test_rebuild_email_replaces_previous` | Second rebuild replaces all rows (same count) |
| 8 | `test_rebuild_email_computed_columns` | `sender`, `scrubber`, `match_mode` correctly computed |

```python
class TestRebuildEmail:
    def test_rebuild_email_count(self, index, email_xml):
        result = index.rebuild(email_xml, "email")
        assert result["email_jobs_loaded"] == 3

    def test_rebuild_email_hash_stored(self, index, email_xml):
        index.rebuild(email_xml, "email")
        assert index._get_metadata("email_hash") is not None

    def test_rebuild_email_fields(self, index, email_xml):
        index.rebuild(email_xml, "email")
        row = index._conn.execute(
            "SELECT * FROM email_jobs WHERE name='TestJob_Alpha'"
        ).fetchone()
        assert row["mailbox"] == "test@usbank.com"
        assert row["servicer_id"] == 10
        assert row["sme"] == "John.Doe"

    def test_rebuild_email_replaces_previous(self, index, email_xml):
        index.rebuild(email_xml, "email")
        index.rebuild(email_xml, "email")
        count = index._conn.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0]
        assert count == 3  # not 6

    def test_rebuild_email_computed_columns(self, index, email_xml):
        index.rebuild(email_xml, "email")
        row = index._conn.execute(
            "SELECT * FROM email_jobs WHERE name='TestJob_Alpha'"
        ).fetchone()
        assert row["sender"] == "reports@alpha.com"
        assert row["scrubber"] == "TestScrubber_Alpha"
        assert row["match_mode"] == "Subject"
```

#### TestRebuildSftp (3 tests)

| # | Test Name | Verifies |
|---|---|---|
| 9 | `test_rebuild_sftp_count` | 2 SFTP jobs loaded |
| 10 | `test_rebuild_sftp_hash_stored` | `sftp_hash` key exists in metadata |
| 11 | `test_rebuild_sftp_fields` | Job fields correctly stored (path, dsn, servicer_id) |

```python
class TestRebuildSftp:
    def test_rebuild_sftp_count(self, index, sftp_xml):
        result = index.rebuild(sftp_xml, "sftp")
        assert result["sftp_jobs_loaded"] == 2

    def test_rebuild_sftp_hash_stored(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        assert index._get_metadata("sftp_hash") is not None

    def test_rebuild_sftp_fields(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        row = index._conn.execute(
            "SELECT * FROM sftp_jobs WHERE name='SftpJob_Gamma'"
        ).fetchone()
        assert row["path"] == "/incoming/gamma/"
        assert row["dsn"] == "SFTP_Gamma"
        assert row["servicer_id"] == 30
```

#### TestSearchJobs (6 tests)

| # | Test Name | Verifies |
|---|---|---|
| 12 | `test_search_by_name` | `search_jobs("Alpha")` returns 1 result with `job_name=TestJob_Alpha` |
| 13 | `test_search_by_sender` | `search_jobs("alpha.com")` matches sender field |
| 14 | `test_search_by_servicer_id` | `search_jobs("10")` matches servicer_id |
| 15 | `test_search_no_match` | `search_jobs("nonexistent")` returns empty list |
| 16 | `test_search_all_types` | `search_jobs("test", xml_type="all")` includes both email + sftp results |
| 17 | `test_search_summary_format` | Returned dicts have correct keys (job_name, mailbox, sender, etc.) |

```python
class TestSearchJobs:
    def test_search_by_name(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("Alpha", "email")
        assert len(results) == 1
        assert results[0]["job_name"] == "TestJob_Alpha"

    def test_search_by_sender(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("alpha.com", "email")
        assert len(results) == 1

    def test_search_by_servicer_id(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("10", "email")
        assert any(r["servicer_id"] == 10 for r in results)

    def test_search_no_match(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("nonexistent_zzz_xyz", "email")
        assert results == []

    def test_search_all_types(self, index, email_xml, sftp_xml):
        index.rebuild(email_xml, "email")
        index.rebuild(sftp_xml, "sftp")
        results = index.search_jobs("30", "all")
        assert any(r.get("xml_type") == "sftp" for r in results)

    def test_search_summary_format(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("Alpha", "email")
        r = results[0]
        assert "job_name" in r
        assert "mailbox" in r
        assert "sender" in r
        assert "servicer_id" in r
        assert "save_path" in r
        assert "scrubber" in r
        assert "match_mode" in r
        assert "xml_type" in r
```

#### TestGetJob (4 tests)

| # | Test Name | Verifies |
|---|---|---|
| 18 | `test_get_email_job` | Returns full detail dict for email job |
| 19 | `test_get_sftp_job` | Returns full detail dict for SFTP job |
| 20 | `test_get_job_not_found` | Returns None for nonexistent job |
| 21 | `test_get_job_case_insensitive` | `get_job("testjob_alpha")` finds `TestJob_Alpha` |

```python
class TestGetJob:
    def test_get_email_job(self, index, email_xml):
        index.rebuild(email_xml, "email")
        job = index.get_job("TestJob_Alpha")
        assert job is not None
        assert job["job_name"] == "TestJob_Alpha"
        assert "filters" in job
        assert "parsers" in job
        assert "templates" in job

    def test_get_sftp_job(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        job = index.get_job("SftpJob_Gamma")
        assert job is not None
        assert job["sftp_path"] == "/incoming/gamma/"
        assert job["xml_type"] == "sftp"

    def test_get_job_not_found(self, index, email_xml):
        index.rebuild(email_xml, "email")
        assert index.get_job("DoesNotExist") is None

    def test_get_job_case_insensitive(self, index, email_xml):
        index.rebuild(email_xml, "email")
        job = index.get_job("testjob_alpha")
        assert job is not None
        assert job["job_name"] == "TestJob_Alpha"
```

#### TestGetAllJobs (3 tests)

| # | Test Name | Verifies |
|---|---|---|
| 22 | `test_get_all_email` | Returns 3 email jobs |
| 23 | `test_get_all_sftp` | Returns 2 SFTP jobs |
| 24 | `test_get_all_combined` | Returns 5 jobs total when both rebuilt |

```python
class TestGetAllJobs:
    def test_get_all_email(self, index, email_xml):
        index.rebuild(email_xml, "email")
        jobs = index.get_all_jobs("email")
        assert len(jobs) == 3

    def test_get_all_sftp(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        jobs = index.get_all_jobs("sftp")
        assert len(jobs) == 2

    def test_get_all_combined(self, index, email_xml, sftp_xml):
        index.rebuild(email_xml, "email")
        index.rebuild(sftp_xml, "sftp")
        jobs = index.get_all_jobs("all")
        assert len(jobs) == 5
```

#### TestContentHash (4 tests)

| # | Test Name | Verifies |
|---|---|---|
| 25 | `test_hash_is_fresh_after_rebuild` | `check_hash()` returns `is_fresh=True` |
| 26 | `test_hash_detects_config_change` | Modify a config field → `is_fresh=False` |
| 27 | `test_hash_ignores_last_run_time` | Modify `LastRunTime` → `is_fresh=True` (unchanged) |
| 28 | `test_hash_deterministic` | Same XML → same hash |

```python
class TestContentHash:
    def test_hash_is_fresh_after_rebuild(self, index, email_xml):
        index.rebuild(email_xml, "email")
        result = index.check_hash(email_xml, "email")
        assert result["is_fresh"] is True

    def test_hash_detects_config_change(self, index, email_xml):
        index.rebuild(email_xml, "email")
        # Modify the XML (change a ServicerID)
        tree = ET.parse(email_xml)
        root = tree.getroot()
        sid_elem = root.find(".//TestJob_Alpha/ServicerID")
        sid_elem.text = "999"
        tree.write(email_xml)
        result = index.check_hash(email_xml, "email")
        assert result["is_fresh"] is False

    def test_hash_ignores_last_run_time(self, index, email_xml, tmp_path):
        index.rebuild(email_xml, "email")
        # Add a <LastRunTime> element (simulating PowerShell update)
        tree = ET.parse(email_xml)
        root = tree.getroot()
        job_elem = root.find(".//TestJob_Alpha")
        lrt = ET.SubElement(job_elem, "LastRunTime")
        lrt.text = "2026-03-04T14:00:00"
        tree.write(email_xml)
        result = index.check_hash(email_xml, "email")
        assert result["is_fresh"] is True  # last_run_time ignored

    def test_hash_deterministic(self, index, email_xml):
        from backend.db.xml_index import _compute_config_hash
        h1 = _compute_config_hash(email_xml, "email")
        h2 = _compute_config_hash(email_xml, "email")
        assert h1 == h2
```

#### TestGetStatus (2 tests)

| # | Test Name | Verifies |
|---|---|---|
| 29 | `test_status_empty` | Zero counts before rebuild |
| 30 | `test_status_after_rebuild` | Correct counts and hash values |

```python
class TestGetStatus:
    def test_status_empty(self, index):
        status = index.get_status()
        assert status["email_jobs_cached"] == 0
        assert status["sftp_jobs_cached"] == 0

    def test_status_after_rebuild(self, index, email_xml):
        index.rebuild(email_xml, "email")
        status = index.get_status()
        assert status["email_jobs_cached"] == 3
        assert status["email_hash"] is not None
        assert status["schema_version"] == "1"
```

#### TestContextManager (2 tests)

| # | Test Name | Verifies |
|---|---|---|
| 31 | `test_with_statement` | `with XmlJobIndex(...)` works, connection closed on exit |
| 32 | `test_double_close_safe` | Calling `close()` twice doesn't raise |

```python
class TestContextManager:
    def test_with_statement(self, tmp_path):
        from backend.db.xml_index import XmlJobIndex
        db_path = str(tmp_path / "ctx_test.db")
        with XmlJobIndex(db_path) as idx:
            status = idx.get_status()
            assert status["email_jobs_cached"] == 0
        # Connection should be closed

    def test_double_close_safe(self, tmp_path):
        from backend.db.xml_index import XmlJobIndex
        db_path = str(tmp_path / "dbl_close.db")
        idx = XmlJobIndex(db_path)
        idx.close()
        idx.close()  # Should not raise
```

**Total: 32 tests in `test_xml_index.py`**

---

## Integration Tests — CLI Commands

### `tests/cli/test_cli_xml_cache.py`

| # | Test Name | Verifies |
|---|---|---|
| 1 | `test_search_jobs_with_cache` | `cmd_search_jobs` uses SQLite when cache exists |
| 2 | `test_search_jobs_without_cache` | `cmd_search_jobs` falls back to XML when no cache |
| 3 | `test_search_jobs_identical_results` | SQLite and XML paths return identical job lists |
| 4 | `test_job_detail_with_cache` | `cmd_job_detail` uses SQLite when cache exists |
| 5 | `test_job_detail_without_cache` | `cmd_job_detail` falls back to XML when no cache |
| 6 | `test_create_job_triggers_rebuild` | `cmd_create_job` calls `_rebuild_sqlite()` after write |
| 7 | `test_edit_job_triggers_rebuild` | `cmd_edit_job` calls `_rebuild_sqlite()` after write |
| 8 | `test_rebuild_db_command` | `cmd_rebuild_db` creates/refreshes SQLite from XML |
| 9 | `test_stale_cache_warning` | Stale cache adds warning but still returns results |
| 10 | `test_cache_db_path_optional` | Commands work when `--cache-db-path` is omitted |

```python
class TestCliXmlCache:
    def test_search_jobs_with_cache(self, args_with_cache):
        """cmd_search_jobs should prefer SQLite when cache DB exists."""
        response = cmd_search_jobs(args_with_cache)
        assert response.success
        assert response.data["total_count"] > 0

    def test_search_jobs_without_cache(self, args_without_cache):
        """cmd_search_jobs should fall back to XML when no cache."""
        response = cmd_search_jobs(args_without_cache)
        assert response.success
        assert response.data["total_count"] > 0

    def test_search_jobs_identical_results(self, args_with_cache, args_without_cache):
        """SQLite and XML paths should return identical job lists."""
        args_with_cache.query = "Alpha"
        args_without_cache.query = "Alpha"
        r_cache = cmd_search_jobs(args_with_cache)
        r_xml = cmd_search_jobs(args_without_cache)
        # Compare job names
        cache_names = {j["job_name"] for j in r_cache.data["jobs"]}
        xml_names = {j["job_name"] for j in r_xml.data["jobs"]}
        assert cache_names == xml_names

    def test_rebuild_db_command(self, tmp_path, email_xml):
        """cmd_rebuild_db should create SQLite and populate it."""
        args = argparse.Namespace(
            cache_db_path=str(tmp_path / "test.db"),
            settings_path=email_xml,
            xml_type="email",
        )
        response = cmd_rebuild_db(args)
        assert response.success
        assert response.data["email"]["email_jobs_loaded"] == 3
```

**Total: 10 tests in `test_cli_xml_cache.py`**

---

## Regression Tests

### What Must Not Break

| Area | Test File | Count | Verification |
|---|---|---|---|
| XML Parser | `tests/xml/test_parser.py` | ~40 | `pytest tests/xml/ -q` |
| XML CRUD | `tests/xml/test_crud.py` | ~30 | `pytest tests/xml/ -q` |
| Deal Repo | `tests/db/test_deal_repo.py` | ~20 | `pytest tests/db/ -q` |
| Template Staging | `tests/db/test_template_staging_repo_p5.py` | ~33 | `pytest tests/db/ -q` |
| CLI Commands | `tests/cli/` | ~90 | `pytest tests/cli/ -q` |
| Triage | `tests/triage/` | ~60 | `pytest tests/triage/ -q` |
| Intel | `tests/intel/` | ~50 | `pytest tests/intel/ -q` |
| Logs | `tests/logs/` | ~30 | `pytest tests/logs/ -q` |
| Analysis | `tests/analysis/` | ~40 | `pytest tests/analysis/ -q` |
| Backup | `tests/backup/` | ~15 | `pytest tests/backup/ -q` |

### Why Regression Risk Is Low

1. **`XmlJobIndex` is additive.** It doesn't modify `SettingsXmlParser` or any XML model.
2. **CLI fallback.** `cmd_search_jobs`/`cmd_job_detail` retain the original XML parsing code path.
3. **`_rebuild_sqlite()` is fire-and-forget.** If it fails, the CLI command still succeeds.
4. **No interface changes.** The JSON response shape is identical.
5. **Framework files are inert.** Markdown files don't affect Python or JavaScript execution.

---

## Manual QA Checklist

### WS-A: SQLite Cache

| # | Test | Expected Result | Pass? |
|---|---|---|---|
| M-1 | `python -m cli.main rebuild_db --cache-db-path test.db --settings-path Settings.xml --xml-type email` | JSON output with `email_jobs_loaded: N` | [ ] |
| M-2 | `python -m cli.main search_jobs --query "fay" --settings-path Settings.xml --cache-db-path test.db` | Same results as without `--cache-db-path` | [ ] |
| M-3 | `python -m cli.main job_detail --job-name CMLTI_Fay_100 --settings-path Settings.xml --cache-db-path test.db` | Full job detail JSON | [ ] |
| M-4 | Modify a `<ServicerID>` in Settings.xml → run search → check for stale warning | Warning in response.warnings | [ ] |
| M-5 | Modify `<LastRunTime>` in Settings.xml → run search → no stale warning | No warning (hash stable) | [ ] |
| M-6 | Run `rebuild_db` → stale warning clears | `is_fresh: true` | [ ] |
| M-7 | Delete `test.db` → run search → works via XML fallback | Results returned, no crash | [ ] |

### WS-B: Framework Retrofit

| # | Test | Expected Result | Pass? |
|---|---|---|---|
| M-8 | Open VS Code → verify `AGENTS.md` at project root | File renders, describes 4 agents | [ ] |
| M-9 | Open agent selector → verify config, triage, intel, ops appear | Agents listed (if VS Code supports) | [ ] |
| M-10 | Open prompt picker → verify 6 prompt files | All prompts listed | [ ] |
| M-11 | Open `.github/copilot-instructions.md` → verify prescriptive rules | Rules-based, not descriptive | [ ] |
| M-12 | Edit a file under `backend/` → verify `backend.instructions.md` auto-loads | Python rules visible to Copilot | [ ] |
| M-13 | `@frp /jobs search fay` in chat → results returned | Extension still works | [ ] |
| M-14 | `@frp /triage verify` in chat → triage results | Extension still works | [ ] |

---

## Coverage Targets

| Category | Before Phase 6 | After Phase 6 | Delta |
|---|---|---|---|
| Existing tests | 655 passed | 655 passed | 0 |
| New: `test_xml_index.py` | — | ~32 tests | +32 |
| New: `test_cli_xml_cache.py` | — | ~10 tests | +10 |
| **Total** | **655** | **~697** | **+42** |
| Failed | 0 | 0 | 0 |

---

## Test Execution Order

```bash
# 1. Run existing tests first (regression check)
pytest tests/ -q --ignore=tests/db/test_xml_index.py --ignore=tests/cli/test_cli_xml_cache.py
# Expected: 655 passed, 0 failed

# 2. Run new XmlJobIndex tests
pytest tests/db/test_xml_index.py -v
# Expected: ~32 passed, 0 failed

# 3. Run new CLI cache tests
pytest tests/cli/test_cli_xml_cache.py -v
# Expected: ~10 passed, 0 failed

# 4. Full suite
pytest tests/ -q
# Expected: ~697 passed, 0 failed
```
