# Phase 6: Technical Design
## FRP Agent — SQLite Job Cache + Multi-Agent Framework Retrofit

**Document Version:** 1.0  
**Date:** March 4, 2026  
**Status:** Planning  
**Companion:** [02_SYSTEM_DESIGN.md](02_SYSTEM_DESIGN.md)  
**Est. New Lines:** ~1,350 across 22 new files + 2 modified files

---

## Table of Contents
1. [Work Stream A — XmlJobIndex Module](#1-work-stream-a--xmljobindex-module)  
   1.1 [Schema DDL](#11-schema-ddl)  
   1.2 [SQL Constants](#12-sql-constants)  
   1.3 [XmlJobIndex Class](#13-xmljobindex-class)  
   1.4 [Content Hash Implementation](#14-content-hash-implementation)  
   1.5 [CLI Integration](#15-cli-integration)  
   1.6 [Fallback Strategy](#16-fallback-strategy)  
2. [Work Stream B — Framework Files](#2-work-stream-b--framework-files)  
   2.1 [Layer 1: copilot-instructions.md (Rewrite)](#21-layer-1-copilot-instructionsmd-rewrite)  
   2.2 [Layer 2: AGENTS.md](#22-layer-2-agentsmd)  
   2.3 [Layer 3: Agent Persona Files](#23-layer-3-agent-persona-files)  
   2.4 [Layer 4: SKILL.md Files](#24-layer-4-skillmd-files)  
   2.5 [Layer 5: Prompt Files](#25-layer-5-prompt-files)  
   2.6 [Path-Scoped Instructions](#26-path-scoped-instructions)  
3. [Error Handling Details](#3-error-handling-details)  
4. [Migration Notes](#4-migration-notes)  
5. [File-by-File Manifest](#5-file-by-file-manifest)

---

## 1. Work Stream A — XmlJobIndex Module

### 1.1 Schema DDL

```python
# backend/db/xml_index.py — schema constants

_SCHEMA_VERSION = "1"

_CREATE_EMAIL_JOBS = """
CREATE TABLE IF NOT EXISTS email_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    mailbox         TEXT    NOT NULL DEFAULT '',
    folder          TEXT    NOT NULL DEFAULT '',
    sme             TEXT    NOT NULL DEFAULT '',
    last_email      TEXT,
    save_location   TEXT    NOT NULL DEFAULT '',
    filters_json    TEXT    NOT NULL DEFAULT '{}',
    parsers_json    TEXT    NOT NULL DEFAULT '{}',
    servicer_id     INTEGER,
    queue_one_file  INTEGER,
    templates_json  TEXT    NOT NULL DEFAULT '{}',
    day_adjust      INTEGER,
    sender          TEXT    NOT NULL DEFAULT '',
    scrubber        TEXT    NOT NULL DEFAULT '',
    match_mode      TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_SFTP_JOBS = """
CREATE TABLE IF NOT EXISTS sftp_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    path                TEXT    NOT NULL DEFAULT '',
    servicer_id         INTEGER NOT NULL DEFAULT 0,
    dsn                 TEXT    NOT NULL DEFAULT '',
    sme                 TEXT    NOT NULL DEFAULT '',
    save_location       TEXT    NOT NULL DEFAULT '',
    skip_list           TEXT    NOT NULL DEFAULT '',
    ignore_list         TEXT    NOT NULL DEFAULT '',
    parsers_json        TEXT    NOT NULL DEFAULT '{}',
    zip_content_filter  TEXT    NOT NULL DEFAULT '',
    templates_json      TEXT    NOT NULL DEFAULT '{}',
    day_adjust          INTEGER,
    scrubber            TEXT    NOT NULL DEFAULT '',
    match_mode          TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_CACHE_METADATA = """
CREATE TABLE IF NOT EXISTS cache_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_email_jobs_servicer ON email_jobs(servicer_id);",
    "CREATE INDEX IF NOT EXISTS idx_email_jobs_mailbox  ON email_jobs(mailbox);",
    "CREATE INDEX IF NOT EXISTS idx_email_jobs_sender   ON email_jobs(sender);",
    "CREATE INDEX IF NOT EXISTS idx_sftp_jobs_servicer  ON sftp_jobs(servicer_id);",
    "CREATE INDEX IF NOT EXISTS idx_sftp_jobs_dsn       ON sftp_jobs(dsn);",
]
```

### 1.2 SQL Constants

```python
# Insert statements
_INSERT_EMAIL_JOB = """
INSERT INTO email_jobs (
    name, mailbox, folder, sme, last_email, save_location,
    filters_json, parsers_json, servicer_id, queue_one_file,
    templates_json, day_adjust, sender, scrubber, match_mode
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_INSERT_SFTP_JOB = """
INSERT INTO sftp_jobs (
    name, path, servicer_id, dsn, sme, save_location,
    skip_list, ignore_list, parsers_json, zip_content_filter,
    templates_json, day_adjust, scrubber, match_mode
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

# Search query (LIKE-based, case-insensitive via SQLite default collation)
_SEARCH_EMAIL_JOBS = """
SELECT * FROM email_jobs
WHERE name    LIKE ? COLLATE NOCASE
   OR mailbox LIKE ? COLLATE NOCASE
   OR sender  LIKE ? COLLATE NOCASE
   OR scrubber LIKE ? COLLATE NOCASE
   OR save_location LIKE ? COLLATE NOCASE
   OR sme     LIKE ? COLLATE NOCASE
   OR CAST(servicer_id AS TEXT) LIKE ?
ORDER BY name;
"""

_SEARCH_SFTP_JOBS = """
SELECT * FROM sftp_jobs
WHERE name    LIKE ? COLLATE NOCASE
   OR path    LIKE ? COLLATE NOCASE
   OR dsn     LIKE ? COLLATE NOCASE
   OR scrubber LIKE ? COLLATE NOCASE
   OR save_location LIKE ? COLLATE NOCASE
   OR sme     LIKE ? COLLATE NOCASE
   OR CAST(servicer_id AS TEXT) LIKE ?
ORDER BY name;
"""
```

**Design decision — LIKE vs FTS:**  
We use simple `LIKE '%query%'` instead of SQLite FTS5 because:
1. The dataset is small (~70 jobs total) — LIKE is instant.
2. FTS adds schema complexity and rebuild overhead.
3. The existing `_tokenized_match()` logic handles natural-language queries in code; SQLite just does the substring check.

For multi-token queries, the Python layer applies `_tokenized_match()` on the returned rows (same as current behavior), so search quality is identical.

### 1.3 XmlJobIndex Class

```python
"""SQLite-backed query cache for Settings.xml job configurations."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import copy
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.xml.models import _match_mode, _tokenized_match
from backend.xml.parser import SettingsXmlParser

logger = logging.getLogger("frp.db.xml_index")


class XmlJobIndex:
    """SQLite-backed query cache for Settings.xml job configurations.

    Mirrors the LogIndexer pattern:
    - WAL journal mode for concurrent read safety
    - row_factory = sqlite3.Row for dict-like access
    - Schema versioning via cache_metadata table
    - Context manager support (__enter__/__exit__)

    The XML file remains the source of truth. This class provides:
    - Fast querying without re-parsing XML
    - Content-hash-based staleness detection (excludes last_run_time)
    - Explicit rebuild via rebuild() method
    """

    _SCHEMA_VERSION = "1"

    # ------------------------------------------------------------------ #
    #  Construction / lifecycle
    # ------------------------------------------------------------------ #

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create_tables()
        logger.info("XmlJobIndex ready (db=%s)", db_path)

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(_CREATE_EMAIL_JOBS)
        cur.execute(_CREATE_SFTP_JOBS)
        cur.execute(_CREATE_CACHE_METADATA)
        for idx_sql in _CREATE_INDEXES:
            cur.execute(idx_sql)
        self._conn.commit()
        # Seed schema_version if absent
        cur.execute(
            "INSERT OR IGNORE INTO cache_metadata (key, value) VALUES (?, ?)",
            ("schema_version", _SCHEMA_VERSION),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    #  Rebuild
    # ------------------------------------------------------------------ #

    def rebuild(self, xml_path: str, xml_type: str = "email") -> Dict:
        """Parse XML and repopulate the SQLite cache.

        Performs a full replace (DELETE + INSERT) inside a transaction.

        Args:
            xml_path: Path to Settings.xml
            xml_type: "email" or "sftp"

        Returns:
            Summary dict with job counts and content hash.
        """
        parser = SettingsXmlParser(xml_path)
        jobs = parser.get_all_jobs()
        cur = self._conn.cursor()

        if xml_type == "email":
            cur.execute("DELETE FROM email_jobs")
            for job in jobs:
                cur.execute(
                    _INSERT_EMAIL_JOB,
                    (
                        job.name,
                        job.mailbox,
                        job.folder,
                        job.sme,
                        job.last_email,
                        job.save_location,
                        json.dumps(job.filters),
                        json.dumps(job.parsers),
                        job.servicer_id,
                        1 if job.queue_one_file else (0 if job.queue_one_file is not None else None),
                        json.dumps(job.templates),
                        job.day_adjust,
                        job.filters.get("From", "").strip(),
                        (job.templates.get("Main", "") or next(
                            (v for v in job.templates.values() if v), ""
                        )) if job.templates else "",
                        _match_mode(job.parsers),
                    ),
                )
            count_key = "email_jobs_loaded"
        else:
            cur.execute("DELETE FROM sftp_jobs")
            for job in jobs:
                cur.execute(
                    _INSERT_SFTP_JOB,
                    (
                        job.name,
                        job.path,
                        job.servicer_id,
                        job.dsn,
                        job.sme,
                        job.save_location,
                        job.skip_list,
                        job.ignore_list,
                        json.dumps(job.parsers),
                        job.zip_content_filter,
                        json.dumps(job.templates),
                        job.day_adjust,
                        (job.templates.get("Main", "") or next(
                            (v for v in job.templates.values() if v), ""
                        )) if job.templates else "",
                        _match_mode(job.parsers),
                    ),
                )
            count_key = "sftp_jobs_loaded"

        # Compute and store content hash
        content_hash = _compute_config_hash(xml_path, xml_type)
        now_iso = datetime.now(timezone.utc).isoformat()
        self._set_metadata(f"{xml_type}_hash", content_hash)
        self._set_metadata(f"{xml_type}_xml_path", xml_path)
        self._set_metadata(f"{xml_type}_last_rebuild", now_iso)

        self._conn.commit()

        result = {
            count_key: len(jobs),
            "content_hash": content_hash,
            "xml_path": xml_path,
            "rebuilt_at": now_iso,
        }
        logger.info("Rebuild complete (%s): %s", xml_type, result)
        return result

    # ------------------------------------------------------------------ #
    #  Querying
    # ------------------------------------------------------------------ #

    def search_jobs(self, query: str, xml_type: str = "all") -> List[Dict]:
        """Search cached jobs by free-text query.

        Uses LIKE for SQL-level filtering, then applies _tokenized_match()
        for natural-language refinement (identical to current parser logic).

        Args:
            query: Free-text search query.
            xml_type: "email", "sftp", or "all".

        Returns:
            List of summary dicts matching the query.
        """
        results = []
        like_param = f"%{query}%"
        params = [like_param] * 7  # 7 LIKE clauses in each search query

        if xml_type in ("email", "all"):
            cur = self._conn.execute(_SEARCH_EMAIL_JOBS, params)
            for row in cur.fetchall():
                row_dict = dict(row)
                # Apply tokenized match for NL query refinement
                searchable = [
                    row_dict["name"], row_dict["mailbox"], row_dict["sme"],
                    row_dict["save_location"], row_dict["sender"],
                    row_dict["scrubber"], str(row_dict.get("servicer_id", "")),
                    row_dict["filters_json"], row_dict["parsers_json"],
                    row_dict["templates_json"],
                ]
                if _tokenized_match(query, searchable):
                    results.append(self._email_row_to_summary(row_dict))

        if xml_type in ("sftp", "all"):
            cur = self._conn.execute(_SEARCH_SFTP_JOBS, params)
            for row in cur.fetchall():
                row_dict = dict(row)
                searchable = [
                    row_dict["name"], row_dict["path"], row_dict["dsn"],
                    row_dict["sme"], row_dict["save_location"],
                    row_dict["scrubber"], str(row_dict.get("servicer_id", "")),
                    row_dict["parsers_json"], row_dict["templates_json"],
                    row_dict["skip_list"], row_dict["ignore_list"],
                    row_dict["zip_content_filter"],
                ]
                if _tokenized_match(query, searchable):
                    results.append(self._sftp_row_to_summary(row_dict))

        return results

    def get_job(self, name: str) -> Optional[Dict]:
        """Return full detail for a job by exact name.

        Searches both tables (email_jobs first, then sftp_jobs).
        Returns None if not found.
        """
        row = self._conn.execute(
            "SELECT * FROM email_jobs WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row:
            return self._email_row_to_detail(dict(row))

        row = self._conn.execute(
            "SELECT * FROM sftp_jobs WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row:
            return self._sftp_row_to_detail(dict(row))

        return None

    def get_all_jobs(self, xml_type: str = "all") -> List[Dict]:
        """Return summary dicts for all cached jobs."""
        results = []
        if xml_type in ("email", "all"):
            cur = self._conn.execute("SELECT * FROM email_jobs ORDER BY name")
            results.extend(self._email_row_to_summary(dict(r)) for r in cur)
        if xml_type in ("sftp", "all"):
            cur = self._conn.execute("SELECT * FROM sftp_jobs ORDER BY name")
            results.extend(self._sftp_row_to_summary(dict(r)) for r in cur)
        return results

    # ------------------------------------------------------------------ #
    #  Hash / staleness
    # ------------------------------------------------------------------ #

    def check_hash(self, xml_path: str, xml_type: str = "email") -> Dict:
        """Compare stored content hash vs current XML.

        Returns:
            Dict with stored_hash, current_hash, is_fresh, last_rebuild.
        """
        stored = self._get_metadata(f"{xml_type}_hash")
        current = _compute_config_hash(xml_path, xml_type)
        last_rebuild = self._get_metadata(f"{xml_type}_last_rebuild")
        return {
            "stored_hash": stored,
            "current_hash": current,
            "is_fresh": stored == current,
            "last_rebuild": last_rebuild,
        }

    def get_status(self) -> Dict:
        """Return cache status summary."""
        email_count = self._conn.execute(
            "SELECT COUNT(*) FROM email_jobs"
        ).fetchone()[0]
        sftp_count = self._conn.execute(
            "SELECT COUNT(*) FROM sftp_jobs"
        ).fetchone()[0]

        try:
            db_size_bytes = os.path.getsize(self.db_path)
            db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
        except OSError:
            db_size_mb = 0.0

        return {
            "db_path": self.db_path,
            "email_jobs_cached": email_count,
            "sftp_jobs_cached": sftp_count,
            "email_hash": self._get_metadata("email_hash"),
            "sftp_hash": self._get_metadata("sftp_hash"),
            "email_last_rebuild": self._get_metadata("email_last_rebuild"),
            "sftp_last_rebuild": self._get_metadata("sftp_last_rebuild"),
            "schema_version": self._get_metadata("schema_version"),
            "db_size_mb": db_size_mb,
        }

    # ------------------------------------------------------------------ #
    #  Row → Dict converters
    # ------------------------------------------------------------------ #

    @staticmethod
    def _email_row_to_summary(row: Dict) -> Dict:
        """Convert an email_jobs row to a summary dict matching
        EmailJob.to_summary_dict() output format."""
        from backend.xml.models import _match_mode_description
        return {
            "job_name": row["name"],
            "mailbox": row["mailbox"],
            "sender": row["sender"] or "(not specified)",
            "servicer_id": row["servicer_id"],
            "save_path": row["save_location"],
            "scrubber": row["scrubber"] or "(none)",
            "match_mode": row["match_mode"],
            "match_mode_description": _match_mode_description(row["match_mode"]),
            "queue_one_file": bool(row["queue_one_file"]) if row["queue_one_file"] is not None else None,
            "xml_type": "email",
        }

    @staticmethod
    def _sftp_row_to_summary(row: Dict) -> Dict:
        """Convert an sftp_jobs row to a summary dict matching
        SftpJob.to_summary_dict() output format."""
        from backend.xml.models import _match_mode_description
        return {
            "job_name": row["name"],
            "sftp_path": row["path"],
            "dsn": row["dsn"],
            "servicer_id": row["servicer_id"],
            "save_path": row["save_location"],
            "scrubber": row["scrubber"] or "(none)",
            "match_mode": row["match_mode"],
            "match_mode_description": _match_mode_description(row["match_mode"]),
            "zip_filter": row["zip_content_filter"] or "(none)",
            "xml_type": "sftp",
        }

    @staticmethod
    def _email_row_to_detail(row: Dict) -> Dict:
        """Convert an email_jobs row to a full detail dict matching
        cmd_job_detail output format."""
        from backend.xml.models import _match_mode_description
        return {
            "job_name": row["name"],
            "mailbox": row["mailbox"],
            "folder": row["folder"],
            "sme": row["sme"],
            "last_email": row["last_email"],
            "sender": row["sender"] or "(not specified)",
            "save_path": row["save_location"],
            "servicer_id": row["servicer_id"],
            "scrubber": row["scrubber"] or "(none)",
            "match_mode": row["match_mode"],
            "match_mode_description": _match_mode_description(row["match_mode"]),
            "queue_one_file": bool(row["queue_one_file"]) if row["queue_one_file"] is not None else None,
            "xml_type": "email",
            "filters": json.loads(row["filters_json"]),
            "parsers": json.loads(row["parsers_json"]),
            "templates": json.loads(row["templates_json"]),
            "day_adjust": row["day_adjust"],
        }

    @staticmethod
    def _sftp_row_to_detail(row: Dict) -> Dict:
        """Convert an sftp_jobs row to a full detail dict."""
        from backend.xml.models import _match_mode_description
        return {
            "job_name": row["name"],
            "sftp_path": row["path"],
            "dsn": row["dsn"],
            "servicer_id": row["servicer_id"],
            "sme": row["sme"],
            "save_path": row["save_location"],
            "scrubber": row["scrubber"] or "(none)",
            "match_mode": row["match_mode"],
            "match_mode_description": _match_mode_description(row["match_mode"]),
            "zip_filter": row["zip_content_filter"] or "(none)",
            "xml_type": "sftp",
            "skip_list": row["skip_list"],
            "ignore_list": row["ignore_list"],
            "parsers": json.loads(row["parsers_json"]),
            "templates": json.loads(row["templates_json"]),
            "day_adjust": row["day_adjust"],
        }

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _set_metadata(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache_metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _get_metadata(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM cache_metadata WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    # ------------------------------------------------------------------ #
    #  Cleanup / context manager
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
                logger.info("XmlJobIndex connection closed.")
            except Exception:
                logger.debug("SQLite connection already closed.")
            finally:
                self._conn = None

    def __enter__(self) -> "XmlJobIndex":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# --------------------------------------------------------------------------- #
#  Module-level helpers
# --------------------------------------------------------------------------- #

def _compute_config_hash(xml_path: str, xml_type: str) -> str:
    """Compute SHA-256 hash of config-only XML content.

    Strips <LastRunTime> elements before hashing so that
    PowerShell's periodic updates don't trigger false staleness.
    """
    tree = ET.parse(xml_path)
    root = copy.deepcopy(tree.getroot())

    # Strip last_run_time elements (case-insensitive tag match)
    for elem in list(root.iter()):
        for child in list(elem):
            if child.tag.lower() in ("lastruntime", "last_run_time", "lastrundatetime"):
                elem.remove(child)

    canonical = ET.tostring(root, encoding="unicode")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

### 1.4 Content Hash Implementation

**Algorithm:**
1. Parse XML into ElementTree
2. Deep-copy the root element (don't modify the original)
3. Walk all elements, remove any child whose tag matches `lastruntime`, `last_run_time`, or `lastrundatetime` (case-insensitive)
4. Serialise the cleaned tree to a Unicode string
5. Return SHA-256 hex digest

**Why SHA-256?** Standard library, no dependencies, collision-resistant for this use case. The hash is stored in `cache_metadata` under keys `email_hash` and `sftp_hash`.

**When computed:**
- On `rebuild()`: stored after all jobs are inserted
- On `check_hash()`: computed live and compared with stored value
- On `search_jobs()` / `get_job()`: NOT computed (too expensive per query)

The staleness check in `search_jobs()` is done by comparing the stored hash only — the CLI wrapper calls `check_hash()` once per invocation, not per row.

### 1.5 CLI Integration

#### New helper: `_xml_index_from_args`

```python
def _xml_index_from_args(args) -> Optional["XmlJobIndex"]:
    """Build an XmlJobIndex if a cache DB path is available and the file exists."""
    from backend.db.xml_index import XmlJobIndex

    db_path = getattr(args, "cache_db_path", None)
    if db_path and os.path.exists(db_path):
        return XmlJobIndex(db_path)
    return None
```

#### New helper: `_rebuild_sqlite`

```python
def _rebuild_sqlite(args) -> None:
    """Rebuild the SQLite cache after an XML write operation.

    Called after create_job, edit_job, and rollback to keep cache in sync.
    Failures are logged but do not block the CLI response.
    """
    from backend.db.xml_index import XmlJobIndex

    db_path = getattr(args, "cache_db_path", None)
    if not db_path:
        return
    try:
        index = XmlJobIndex(db_path)
        if getattr(args, "xml_type", "email") in ("email", "all"):
            index.rebuild(args.settings_path, "email")
        sftp_path = getattr(args, "sftp_settings_path", None)
        if sftp_path and getattr(args, "xml_type", "email") in ("sftp", "all"):
            index.rebuild(sftp_path, "sftp")
        index.close()
    except Exception as exc:
        logger.warning("SQLite rebuild failed (non-fatal): %s", exc)
```

#### Modified: `cmd_search_jobs`

```python
def cmd_search_jobs(args: argparse.Namespace) -> CliResponse:
    """Search for jobs across email and/or SFTP XML settings."""
    response = CliResponse(success=True, command="search_jobs")

    # ── Try SQLite cache first ──────────────────────────────────── #
    index = _xml_index_from_args(args)
    if index:
        try:
            all_jobs_dicts = index.search_jobs(args.query, args.xml_type)

            # Staleness check (non-blocking)
            if args.xml_type in ("email", "all"):
                hash_result = index.check_hash(args.settings_path, "email")
                if not hash_result["is_fresh"]:
                    response.add_warning(
                        "Cache may be stale — config hash mismatch. "
                        "Run 'frp xml rebuild-db' to refresh."
                    )

            response.data = {
                "jobs": all_jobs_dicts,
                "total_count": len(all_jobs_dicts),
                "xml_type": args.xml_type,
                "cache_status": "fresh",
            }

            # Grouped summaries for large result sets
            if len(all_jobs_dicts) > 10:
                by_scrubber: Dict[str, int] = {}
                by_source: Dict[str, int] = {}
                for j in all_jobs_dicts:
                    t = j.get("scrubber", "(none)")
                    by_scrubber[t] = by_scrubber.get(t, 0) + 1
                    source = j.get("mailbox") or j.get("dsn") or "(unknown)"
                    by_source[source] = by_source.get(source, 0) + 1
                response.data["groups_by_scrubber"] = by_scrubber
                response.data["groups_by_source"] = by_source

            index.close()
            return response
        except Exception as exc:
            logger.warning("SQLite query failed, falling back to XML: %s", exc)
            index.close()
            # Fall through to XML parsing

    # ── Fallback: parse XML directly (original logic) ───────────── #
    all_jobs = []
    # ... (existing XML parsing code unchanged) ...
```

#### Modified: `cmd_create_job`

```python
def cmd_create_job(args: argparse.Namespace) -> CliResponse:
    """Create a new job from a template."""
    response = CliResponse(success=True, command="create_job")
    from backend.xml.crud import JobCrudEngine
    overrides = {}
    if getattr(args, 'servicer_id', None):
        overrides['servicer_id'] = args.servicer_id
    if getattr(args, 'mailbox', None):
        overrides['mailbox'] = args.mailbox
    if getattr(args, 'import_did', None):
        overrides['import_did'] = args.import_did
    try:
        engine = JobCrudEngine(args.settings_path, args.xml_type)
        result = engine.create_job(args.template_job, args.name, overrides or None)
        response.data = result.to_dict()
        _rebuild_sqlite(args)  # ← NEW: rebuild cache after write
    except (ValueError, FileNotFoundError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response
```

#### Modified: `cmd_edit_job`

```python
def cmd_edit_job(args: argparse.Namespace) -> CliResponse:
    """Edit a field on an existing job."""
    response = CliResponse(success=True, command="edit_job")
    from backend.xml.crud import JobCrudEngine
    try:
        engine = JobCrudEngine(args.settings_path, args.xml_type)
        result = engine.edit_job(args.job_name, args.field, args.value)
        response.data = result.to_dict()
        _rebuild_sqlite(args)  # ← NEW: rebuild cache after write
    except (ValueError, FileNotFoundError) as exc:
        response.success = False
        response.add_error(str(exc))
    return response
```

#### New: `cmd_rebuild_db`

```python
def cmd_rebuild_db(args: argparse.Namespace) -> CliResponse:
    """Rebuild SQLite cache from XML settings files."""
    response = CliResponse(success=True, command="rebuild_db")
    from backend.db.xml_index import XmlJobIndex

    index = XmlJobIndex(args.cache_db_path)
    results = {}

    try:
        if args.xml_type in ("email", "all"):
            results["email"] = index.rebuild(args.settings_path, "email")

        if args.xml_type in ("sftp", "all"):
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path:
                results["sftp"] = index.rebuild(sftp_path, "sftp")
            elif args.xml_type == "sftp":
                response.add_error("--sftp-settings-path is required when xml-type is 'sftp'")
                return response

        results["status"] = index.get_status()
        response.data = results
    except Exception as exc:
        response.success = False
        response.add_error(str(exc))
    finally:
        index.close()

    return response
```

### 1.6 Fallback Strategy

```
 ┌─────────────────────┐
 │ cmd_search_jobs()    │
 └──────────┬──────────┘
            │
    ┌───────▼────────┐
    │ SQLite cache    │──── exists? ──── No ──→ Parse XML (original path)
    │ db file exists? │
    └───────┬────────┘
            │ Yes
    ┌───────▼────────┐
    │ XmlJobIndex    │──── query succeeds? ── No ──→ Parse XML (fallback)
    │ .search_jobs() │
    └───────┬────────┘
            │ Yes
    ┌───────▼────────┐
    │ check_hash()   │──── fresh? ── No ──→ Add warning, return results anyway
    └───────┬────────┘
            │ Yes
    ┌───────▼────────┐
    │ Return results │
    │ cache_status:  │
    │ "fresh"        │
    └────────────────┘
```

**Rules:**
1. If `--cache-db-path` is not provided or the file doesn't exist → XML parsing (no cache)
2. If SQLite query raises an exception → fall back to XML parsing, log warning
3. If hash is stale → return results with a warning, don't block
4. The extension never breaks — it always gets valid JSON regardless of cache state

---

## 2. Work Stream B — Framework Files

### 2.1 Layer 1: copilot-instructions.md (Rewrite)

The current file is 60 lines of descriptive documentation. The rewrite will be ~120 lines of prescriptive rules.

```markdown
# FRP Agent — Copilot Global Rules

## Identity
You are `@frp`, an assistant for managing US Bank financial data processing pipelines.
You operate on email monitoring configurations (Settings.xml), deal reference data
(tblExternalDIDRef), processing logs, and template staging records.

## Architecture Rules
- XML (Settings.xml) is the source of truth for job configs. PowerShell owns `last_run_time`.
- SQLite (`frp_xml_cache.db`) is a read-only query cache. Rebuild after every XML write.
- MySQL (`frp_database`) holds tblExternalDIDRef and tblTemplateStaging.
- MSSQL (prod) is read-only. Never write to MSSQL.

## Command Routing
| Intent | Slash Command | CLI Command |
|---|---|---|
| Search jobs | /jobs | search_jobs |
| Job detail | /jobs | job_detail |
| Create job | /deploy | create_job |
| Edit job | /deploy | edit_job |
| Deal lookup | /deals | deal_lookup |
| Triage email | /triage | triage_verify |
| Coverage gaps | /analyze | coverage_gaps |
| Orphan detection | /analyze | orphan_detection |
| Log sync | /logs | sync_logs |
| Staging lookup | /staging | staging_search |

## Field Ownership
- `last_run_time` → PowerShell only. Never modify in agent code.
- `ServicerID` → Set once during job creation. Change requires approval.
- `SaveLocation` → Uses placeholders `{DealFolder}`, `{YYYY}`, `{M}`.

## Output Rules
- All CLI commands emit JSON on stdout, logs on stderr.
- Never dump raw XML to the user. Use summary dicts.
- Confidence levels for triage: completed > processed > should_process > monitored.

## Testing Contract
- All backend changes require pytest tests.
- All tests use fixtures from conftest.py.
- Never hardcode MySQL credentials — use config/secrets_mysql.json.
```

### 2.2 Layer 2: AGENTS.md

```markdown
# FRP Agent Operating Manual

## Agent Personas

| Agent | Domain | Primary Slash Commands |
|---|---|---|
| config | XML job configs, CRUD, backup/rollback | /jobs, /deploy |
| triage | Email matching, DID cross-reference | /triage |
| intel | Deal coverage, orphans, collisions | /deals, /analyze |
| ops | Log forensics, staging, health | /logs, /staging |

## Cross-Agent Rules
1. Every XML write must trigger a SQLite cache rebuild.
2. Database connections must be closed after use (use `repo.close()` or context managers).
3. ServicerID links jobs to deals — any change requires impact analysis.
4. Template names must match existing processing workflows.
5. SFTP jobs match by filename only — never by email subject.
6. Email jobs can match by subject, filename, or both (see MatchMode).

## Validation Gates
- Before creating a job: check for name collision.
- Before editing ServicerID: verify the new ID exists in tblExternalDIDRef.
- Before rollback: show diff to user and get confirmation.

## Confidence Assessment (Triage)
| Level | Meaning |
|---|---|
| completed | Job found + log shows file_load events |
| processed | Job found + log shows processing activity |
| should_process | Job found + DID matched but no log evidence |
| monitored | Job found but no filter/DID match |

## Error Handling
- CLI errors are returned in `CliResponse.errors[]`, never raised to stdout.
- DB connection errors fallback gracefully — inform user, never crash.
- XML parse errors block the command (invalid XML = no data to work with).
```

### 2.3 Layer 3: Agent Persona Files

#### `.github/agents/config.agent.md`

```markdown
---
name: config
description: Manages Settings.xml job configurations, CRUD operations, backups, and the SQLite query cache.
tools:
  - search_jobs
  - job_detail
  - create_job
  - edit_job
  - template_inventory
  - diff
  - rollback
  - rebuild_db
  - validate
---

# Config Agent

## Role
You manage the XML-based job configuration system for the FRP email/SFTP monitors.
Every job in Settings.xml defines how data arrives from external servicers.

## Rules
1. XML is the source of truth. SQLite is a cache — rebuild after every write.
2. Never modify `last_run_time` — PowerShell owns that field exclusively.
3. `queue_one_file=True` ensures single-file processing — don't disable without reason.
4. To edit a field: use `JobCrudEngine.edit_job()` which creates a backup first.
5. Save locations use placeholders: `{DealFolder}`, `{YYYY}`, `{M}`.
6. Template names (scrubbers) must match existing ActiveBatch/VBA processing workflows.

## Tools & Data Sources
- **SettingsXmlParser**: Parses Settings.xml → EmailJob/SftpJob dataclasses
- **XmlJobIndex**: SQLite cache for fast queries over parsed jobs
- **JobCrudEngine**: Creates/edits jobs with automatic backup
- **BackupManager**: Manages `.bak` files for rollback
- **XmlWriter**: Writes modified XML preserving structure

## Output Format
- Job summaries: `{job_name, mailbox, sender, servicer_id, save_path, scrubber, match_mode}`
- CRUD results: `{operation, job_name, changes[], backup_file}`
- Diff results: `{added[], removed[], modified[], unchanged_count}`

## Example Interactions
- "Search for all fay jobs" → search_jobs(query="fay")
- "Show me CMLTI_Fay_100 details" → job_detail(name="CMLTI_Fay_100")
- "Create a new job like CMLTI_Fay_100 named CMLTI_Fay_200" → create_job(...)
- "Change the servicer ID on TPMT_SLS to 45" → edit_job(...)
- "Rebuild the cache" → rebuild_db(xml_type="all")
```

#### `.github/agents/triage.agent.md`

```markdown
---
name: triage
description: Triages unmatched or suspicious emails by cross-referencing XML configs, logs, and DID references.
tools:
  - triage_verify
---

# Triage Agent

## Role
You investigate whether inbound emails are being properly matched and processed
by the FRP monitor. You cross-reference email metadata against XML job configs,
tblExternalDIDRef deals, log events, and template staging.

## Rules
1. Always check MatchMode — Subject, Filename, or Both.
2. SFTP jobs match by filename only — never by email subject.
3. Confidence levels: completed > processed > should_process > monitored.
4. A missing DID match doesn't mean failure — it means the job is shelf-level.
5. If log_summary has no file_load events, the email was likely not processed.
6. Multiple DID matches for a single servicer are normal (multi-deal servicers).

## Cross-Reference Chain
1. Parse email → extract sender, subject, attachments
2. Find matching XML job by sender domain + filter rules
3. Match DealIDs from tblExternalDIDRef via ServicerID + keyword
4. Look up processing logs for that job + time window
5. Check tblTemplateStaging for scrubber execution
6. Assess confidence based on evidence depth

## Output Format
- `{job, deals[], did_matches[], log_summary, template_status, confidence}`
```

#### `.github/agents/intel.agent.md`

```markdown
---
name: intel
description: Analyses deal coverage, detects orphaned jobs, and identifies configuration collisions.
tools:
  - deal_lookup
  - coverage_gaps
  - orphan_detection
  - collision_detection
---

# Intel Agent

## Role
You provide intelligence about the relationship between XML jobs and database records.
You find gaps, orphans, and collisions that could indicate misconfiguration.

## Rules
1. A coverage gap means a deal exists in tblExternalDIDRef but has no XML job.
2. An orphan is an XML job whose ServicerID doesn't exist in tblExternalDIDRef.
3. A collision is two XML jobs competing for the same emails (same sender + filter).
4. ServicerID=0 or None means "shelf-level" — these are intentionally unlinked.
5. Always report gap/orphan counts alongside details for LLM summarisation.

## Data Sources
- **DealRepository**: Queries tblExternalDIDRef (MySQL or MSSQL)
- **SettingsXmlParser** / **XmlJobIndex**: Job configurations
- **CoverageAnalyzer**: per-servicer gap analysis
- **OrphanDetector**: jobs with invalid ServicerIDs
- **CollisionDetector**: jobs with overlapping filters

## Output Format
- Coverage: `{reports: [{servicer_id, deal_count, job_count, gaps[]}], total_servicers_analyzed}`
- Orphans: `{orphans: [{job_name, servicer_id, reason}], total_orphans}`
- Collisions: `{collisions: [{job_a, job_b, collision_type, overlap}], total_collisions}`
```

#### `.github/agents/ops.agent.md`

```markdown
---
name: ops
description: Operations agent for log forensics, template staging queries, and system health monitoring.
tools:
  - sync_logs
  - log_search
  - log_summary
  - staging_search
  - staging_stats
  - staging_failures
  - staging_compare
  - staging_pipeline
  - health_check
  - analyze_performance
  - analyze_trends
---

# Ops Agent

## Role
You handle operational visibility — log analysis, template staging results,
processing health, and trend detection.

## Rules
1. Log sync uses incremental indexing — already-indexed files are skipped.
2. Template staging queries default to last 30 days unless specified.
3. Health checks combine log analysis + staging success rates.
4. Performance metrics compare current period to baseline.
5. Trend detection looks for pattern changes over time windows.

## Data Sources
- **LogIndexer**: SQLite database of parsed .log file events
- **TemplateStagingRepository**: MySQL queries on tblTemplateStaging
- **HealthAnalyzer**: Combines log + staging for system health
- **PerformanceAnalyzer**: Throughput and latency metrics
- **TrendAnalyzer**: Time-series pattern detection

## Output Format
- Log search: `{events: [...], total}` (LogEvent rows)
- Staging: `{runs: [...], success_rate, total_runs}`
- Health: `{overall_status, job_health: [...], alert_count}`
```

### 2.4 Layer 4: SKILL.md Files

#### `skills/xml-config/SKILL.md`

```markdown
# XML Configuration Management

## Domain Overview
The FRP email/SFTP monitor reads Settings.xml at startup. Each `<JOB_NAME>` element
defines how the monitor processes inbound data from a specific financial servicer.

## Key Concepts
- **EmailJob**: Monitors a mailbox folder, filters by sender, detaches attachments
- **SftpJob**: Monitors an SFTP path, downloads files matching patterns
- **MatchMode**: Subject (keyword in email subject), Filename (keyword in attachment name), Both
- **SaveLocation**: Uses `{DealFolder}`, `{YYYY}`, `{M}` placeholders
- **QueueOneFile**: When True, only one file is queued per scrubber run

## XML Structure
```xml
<root>
  <Outlook>
    <MailboxCollection>
      <JOB_NAME>
        <ServicerID>60</ServicerID>
        <Mailbox>gsfi_llc_dl@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>John.Doe</SME>
        <SaveLocation>M:\{DealFolder}\Data\{YYYY}\{M}\</SaveLocation>
        <Filter><From>reports@servicer.com</From></Filter>
        <Parser><DetachFileSubject><Keyword>monthly</Keyword></DetachFileSubject></Parser>
        <Template><Main>CMLTI_Fay_100</Main></Template>
      </JOB_NAME>
    </MailboxCollection>
  </Outlook>
</root>
```

## Common Patterns
| Pattern | Template Prefix | Example |
|---|---|---|
| CMBS | QueueCMBS_Scrubber_x | Commercial Mortgage-Backed Securities |
| ABS | ABS_Deals_Queuer_x | Asset-Backed Securities |
| CMLTI | CMLTI_Fay_{ID} | Commercial Mortgage Loan Trust (Fay servicer) |
| SCRT | SCRT_Queuer_x | Single-Family Rental Trust |
| TPMT | TPMT_{Servicer} | Third-Party Master Servicer |

## CLI Examples
```bash
frp search_jobs --query "fay" --settings-path Settings.xml
frp job_detail --job-name CMLTI_Fay_100 --settings-path Settings.xml
frp create_job --template-job CMLTI_Fay_100 --name CMLTI_Fay_200 --settings-path Settings.xml
frp rebuild_db --cache-db-path frp_xml_cache.db --settings-path Settings.xml
```

## Troubleshooting
- **Job not found in search**: Check if cache is stale (`rebuild_db`)
- **Validation errors**: Missing ServicerID, empty SaveLocation, no Parser configured
- **MatchMode "(none)"**: No recognisable parser configured — job won't match any emails
```

#### `skills/email-triage/SKILL.md`

```markdown
# Email Triage

## Domain Overview
When emails arrive that may not be properly matched by the monitor, triage
determines whether the email *should* have been processed and what went wrong.

## Key Concepts
- **Sender domain matching**: XML jobs filter by `From` address domain
- **Subject keyword**: `DetachFileSubject` parser matches keywords in subject
- **Filename keyword**: `DetachFile`/`MoveFile` parser matches attachment names
- **DID mapping**: tblExternalDIDRef links ServicerID → DealID via keyword
- **Confidence levels**: completed > processed > should_process > monitored

## Triage Cross-Reference Chain
1. Parse email metadata (sender, subject, attachments)
2. Match sender domain to XML job → get ServicerID
3. Match keywords against tblExternalDIDRef → get DealIDs
4. Query log index for job activity in time window
5. Query template staging for scrubber results
6. Assess confidence based on evidence depth

## CLI Examples
```bash
frp triage_verify --sender "reports@fay.com" --subject "Monthly CMLTI" --settings-path Settings.xml
```
```

#### `skills/deal-intelligence/SKILL.md`

```markdown
# Deal Intelligence

## Domain Overview
tblExternalDIDRef is the master reference table linking financial deals to
servicers, keywords, and processing identifiers. Intelligence queries
cross-reference this data with XML job configs.

## Key Concepts
- **ServicerID**: Links XML jobs to one or more deals in tblExternalDIDRef
- **DealID**: Unique identifier for a financial deal (e.g., JPMCWLT20101)
- **Keyword**: Text pattern used for file/email matching
- **Coverage gap**: A deal exists in DB but has no XML job to monitor it
- **Orphan**: An XML job references a ServicerID not in tblExternalDIDRef
- **Collision**: Two XML jobs match the same emails

## Data Rules
- ServicerID = 0 or None → shelf-level job (intentionally unlinked)
- Multiple deals per ServicerID is normal (multi-deal servicers)
- Keywords are case-insensitive for matching

## CLI Examples
```bash
frp deal_lookup --query "CMLTI" --settings-path Settings.xml --db-mode mysql
frp coverage_gaps --servicer-id all --settings-path Settings.xml --db-mode mysql
frp orphan_detection --settings-path Settings.xml --db-mode mysql
```
```

#### `skills/log-forensics/SKILL.md`

```markdown
# Log Forensics

## Domain Overview
The PowerShell EmailMonitor writes .log files for every execution cycle.
The LogIndexer parses these into a SQLite database for querying.

## Key Concepts
- **Log event types**: found_count, file_load, error, did_mapping_failed, job_start, job_end
- **Incremental sync**: Only new .log files are parsed; already-indexed files are skipped
- **Retention**: Events older than N months are auto-purged
- **Log file naming**: Typically `EmailMonitor_YYYYMMDD_HHMMSS.log`

## Event Fields
| Field | Description |
|---|---|
| job_name | Which XML job generated this event |
| event_type | What happened (found_count, file_load, error) |
| emails_found | Number of matching emails in this cycle |
| subject | Email subject line (if applicable) |
| sender | Email sender address |
| parser | Which parser matched (DetachFileSubject, DetachFile) |
| filename | Attachment filename (if applicable) |
| template | Scrubber template used for processing |

## CLI Examples
```bash
frp sync_logs --log-dir "\\\\server\\logs\\" --db-path frp_logs.db
frp log_search --job-name CMLTI_Fay_100 --event-type file_load --db-path frp_logs.db
frp log_summary --job-name CMLTI_Fay_100 --db-path frp_logs.db
```
```

#### `skills/template-staging/SKILL.md`

```markdown
# Template Staging

## Domain Overview
tblTemplateStaging records the outcome of every scrubber execution.
When the monitor processes a file, it creates a staging record with
status, timestamps, and file metadata.

## Key Concepts
- **TemplateName**: Matches the scrubber/template defined in the XML job
- **Status values**: Completed, Failed, Pending, Processing
- **Success rate**: (completed / total) × 100 over a time window
- **Pipeline view**: Traces a file from email arrival → staging completion

## Table Columns (key fields)
| Column | Description |
|---|---|
| TemplateName | Name of the scrubber template |
| FileName | Input file that was processed |
| Status | Completed / Failed / Pending |
| StartTime | When processing began |
| EndTime | When processing finished |
| ErrorMessage | Failure reason (if any) |

## CLI Examples
```bash
frp staging_search --query "CMLTI_Fay" --db-mode mysql
frp staging_stats --template-name CMLTI_Fay_100 --days 30 --db-mode mysql
frp staging_failures --days 7 --db-mode mysql
frp staging_pipeline --file-name "report_202603.xlsx" --db-mode mysql
```
```

### 2.5 Layer 5: Prompt Files

#### `.github/prompts/search-jobs.prompt.md`

```markdown
---
mode: agent
tools:
  - search_jobs
description: Search for email/SFTP jobs in Settings.xml
---

Search for jobs matching the user's query across email and SFTP configurations.
Use the search_jobs tool with the query provided.
If results are large (>10), summarise by scrubber template and mailbox.
Always show job_name, servicer_id, sender, and match_mode.
```

#### `.github/prompts/triage-email.prompt.md`

```markdown
---
mode: agent
tools:
  - triage_verify
  - search_jobs
  - log_search
description: Triage an unmatched email
---

Investigate whether an email should have been processed by the FRP monitor.
Steps:
1. Match the sender domain against XML job configurations
2. Check for keyword matches in subject/filename
3. Cross-reference with tblExternalDIDRef for deal mapping
4. Query processing logs for evidence of activity
5. Report confidence level: completed, processed, should_process, or monitored
```

#### `.github/prompts/staging-lookup.prompt.md`

```markdown
---
mode: agent
tools:
  - staging_search
  - staging_stats
description: Look up template staging results
---

Query tblTemplateStaging for recent processing results.
Show success rate, failure count, and last run timestamps.
Default to last 30 days unless the user specifies a different window.
```

#### `.github/prompts/deploy-diff.prompt.md`

```markdown
---
mode: agent
tools:
  - diff
  - rollback
description: Compare current config against backup and optionally rollback
---

Show the diff between the current Settings.xml and the most recent backup.
Highlight added/removed/modified jobs with field-level change details.
If the user wants to rollback, confirm before executing.
```

#### `.github/prompts/health-check.prompt.md`

```markdown
---
mode: agent
tools:
  - sync_logs
  - log_summary
  - staging_stats
  - health_check
description: Run a system health check
---

Assess the overall health of the FRP monitoring system:
1. Sync latest logs
2. Check for error spikes
3. Review template staging success rates
4. Report any jobs with declining performance
```

#### `.github/prompts/deal-lookup.prompt.md`

```markdown
---
mode: agent
tools:
  - deal_lookup
  - coverage_gaps
description: Look up deals and check coverage
---

Look up which jobs serve a given deal by cross-referencing tblExternalDIDRef.
If the user asks about gaps, run coverage_gaps to find deals without jobs.
Show ServicerID, DealID, and keyword for each match.
```

### 2.6 Path-Scoped Instructions

#### `backend.instructions.md`

```markdown
# Backend Python Rules

## Conventions
- All modules use `from __future__ import annotations`
- Dataclasses for all models — no plain dicts as return types from classes
- Type hints on all function signatures
- Logging via `logging.getLogger("frp.<module>")`
- Docstrings follow Google style

## Error Handling
- Repository classes raise on connection failure (caller handles)
- CLI command handlers catch all exceptions and return CliResponse with errors
- Never let exceptions propagate to stdout — only JSON on stdout

## Database Access
- MySQL: use `DealRepository` or `TemplateStagingRepository` via `_repo_from_args()`
- SQLite: use `LogIndexer` or `XmlJobIndex` with context managers
- Always close connections: `repo.close()` or `with` statement

## Testing
- All tests in `tests/<module>/` directory
- Fixtures in `conftest.py` — never hardcode credentials
- In-memory SQLite for LogIndexer/XmlJobIndex tests (`:memory:`)
- Mock XML files as `tmp_path` fixtures
```

#### `extension.instructions.md`

```markdown
# Extension JavaScript Rules

## Architecture
- `participant.js` handles all chat interactions via COMMAND_HANDLERS
- `tool.js` defines tool schemas and dispatch
- All backend calls go through `backendCall(command, args)` → spawns CLI subprocess

## Conventions
- backendCall always expects JSON on stdout — any non-JSON is an error
- Handler functions are async — always await backendCall
- Error responses: check `response.success` before accessing `response.data`
- Use `formatRawData()` for fallback display when no custom formatter exists

## Package.json
- chatParticipants define slash commands
- frpAgent settings define paths and connection params
- Never add tools that duplicate existing CLI commands
```

#### `cli.instructions.md`

```markdown
# CLI Rules

## Contract
- Every command handler returns `CliResponse` — never raises to caller
- JSON on stdout, logs on stderr
- `_configure_logging()` is called once at startup

## Argument Patterns
- `--settings-path`: Required for all XML operations
- `--sftp-settings-path`: Optional, needed for SFTP or xml-type=all
- `--db-mode`: "mysql" or "mssql"
- `--cache-db-path`: Optional, enables SQLite cache
- `--secrets-path`: Path to secrets JSON file

## Adding New Commands
1. Create `cmd_<name>()` handler function
2. Add to `COMMAND_HANDLERS` dict
3. Add argparse subparser with arguments
4. Add tests in `tests/cli/`
```

---

## 3. Error Handling Details

### 3.1 SQLite Errors

| Scenario | Handler | User Impact |
|---|---|---|
| DB file doesn't exist | `_xml_index_from_args()` returns None | Falls back to XML parsing — no error shown |
| DB file corrupted | `XmlJobIndex.__init__()` raises | Caught in CLI, falls back to XML, warning logged |
| Table missing | `_create_tables()` creates it | Self-healing — never fails |
| INSERT fails (duplicate) | `rebuild()` DELETEs first | Self-healing — never fails |
| Hash mismatch | `check_hash()` returns `is_fresh=False` | Warning added to response, results still returned |

### 3.2 XML Parse Errors (Unchanged)

| Scenario | Handler | User Impact |
|---|---|---|
| File not found | `FileNotFoundError` raised | CLI returns `success=False` with error message |
| Invalid XML | `ET.ParseError` raised | CLI returns `success=False` with error message |
| Missing collection | `detect_xml_type()` returns "unknown" | CLI returns empty results with warning |

### 3.3 Framework File Errors

Framework files are pure markdown — they cannot cause runtime errors. If a file is malformed, Copilot ignores it. The worst case is Copilot not recognising an agent persona, which has no impact on code execution.

---

## 4. Migration Notes

### 4.1 First-Run Bootstrapping

On first run after Phase 6, the SQLite cache won't exist. The system handles this gracefully:

1. User runs any search/detail command → SQLite not found → XML parsing (existing behavior)
2. User runs `frp xml rebuild-db` → creates and populates SQLite
3. Subsequent commands use SQLite → faster queries

The extension can detect the absence of the cache and suggest running `rebuild-db`.

### 4.2 No Breaking Changes

| Component | Status |
|---|---|
| `SettingsXmlParser` | Still exists, still used by crud/diff/rollback |
| `EmailJob` / `SftpJob` | Still the canonical types |
| All existing CLI commands | Same argparse interface, same JSON output |
| Extension JS | Zero changes |
| PowerShell EmailMonitor | Zero changes — doesn't know SQLite exists |
| All 655 tests | Continue to pass — no interface changes |

### 4.3 SQLite File Location

The default location for the cache database:
- Same directory as Settings.xml: `./frp_xml_cache.db`
- Can be overridden via `--cache-db-path` CLI argument
- Extension can set via `frpAgent.cacheDbPath` setting

---

## 5. File-by-File Manifest

| # | File | Type | Est. Lines | Work Stream |
|---|---|---|---|---|
| 1 | `backend/db/xml_index.py` | New Python | ~250 | WS-A |
| 2 | `tests/db/test_xml_index.py` | New Python | ~350 | WS-A |
| 3 | `cli/main.py` | Modified Python | ~+60 net | WS-A |
| 4 | `.github/copilot-instructions.md` | Rewrite MD | ~120 | WS-B |
| 5 | `AGENTS.md` | New MD | ~100 | WS-B |
| 6 | `.github/agents/config.agent.md` | New MD | ~80 | WS-B |
| 7 | `.github/agents/triage.agent.md` | New MD | ~60 | WS-B |
| 8 | `.github/agents/intel.agent.md` | New MD | ~60 | WS-B |
| 9 | `.github/agents/ops.agent.md` | New MD | ~60 | WS-B |
| 10 | `.github/prompts/search-jobs.prompt.md` | New MD | ~15 | WS-B |
| 11 | `.github/prompts/triage-email.prompt.md` | New MD | ~20 | WS-B |
| 12 | `.github/prompts/staging-lookup.prompt.md` | New MD | ~15 | WS-B |
| 13 | `.github/prompts/deploy-diff.prompt.md` | New MD | ~15 | WS-B |
| 14 | `.github/prompts/health-check.prompt.md` | New MD | ~18 | WS-B |
| 15 | `.github/prompts/deal-lookup.prompt.md` | New MD | ~15 | WS-B |
| 16 | `backend.instructions.md` | New MD | ~40 | WS-B |
| 17 | `extension.instructions.md` | New MD | ~30 | WS-B |
| 18 | `cli.instructions.md` | New MD | ~30 | WS-B |
| 19 | `skills/xml-config/SKILL.md` | New MD | ~80 | WS-B |
| 20 | `skills/email-triage/SKILL.md` | New MD | ~60 | WS-B |
| 21 | `skills/deal-intelligence/SKILL.md` | New MD | ~60 | WS-B |
| 22 | `skills/log-forensics/SKILL.md` | New MD | ~60 | WS-B |
| 23 | `skills/template-staging/SKILL.md` | New MD | ~60 | WS-B |
| **Total** | | | **~1,350** | |
