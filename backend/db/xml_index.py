"""SQLite-backed query cache for Settings.xml job configurations.

The XML file remains the source of truth.  This module provides:
- Fast querying of email/SFTP jobs without re-parsing XML every time
- Content-hash-based staleness detection (excludes last_run_time)
- Explicit rebuild via ``XmlJobIndex.rebuild()``

Follows the LogIndexer pattern (WAL mode, row_factory, schema versioning,
context manager).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.xml.models import _match_mode, _match_mode_description, _tokenized_match
from backend.xml.parser import SettingsXmlParser

logger = logging.getLogger("frp.db.xml_index")

# ===================================================================== #
#  Schema constants
# ===================================================================== #

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

# ── DML ─────────────────────────────────────────────────────────────── #

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

# ── Search queries ──────────────────────────────────────────────────── #

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


# ===================================================================== #
#  XmlJobIndex class
# ===================================================================== #

class XmlJobIndex:
    """SQLite-backed query cache for Settings.xml job configurations.

    Mirrors the LogIndexer pattern:
    - WAL journal mode for concurrent read safety
    - ``row_factory = sqlite3.Row`` for dict-like access
    - Schema versioning via ``cache_metadata`` table
    - Context manager support (``__enter__``/``__exit__``)

    The XML file remains the source of truth.  This class provides:
    - Fast querying without re-parsing XML
    - Content-hash-based staleness detection (excludes ``last_run_time``)
    - Explicit rebuild via :meth:`rebuild`
    """

    _SCHEMA_VERSION = "1"

    # ------------------------------------------------------------------ #
    #  Construction / lifecycle
    # ------------------------------------------------------------------ #

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(db_path)
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
            ("schema_version", self._SCHEMA_VERSION),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    #  Rebuild
    # ------------------------------------------------------------------ #

    def rebuild(self, xml_path: str, xml_type: str = "email") -> Dict:
        """Parse XML and repopulate the SQLite cache.

        Performs a full replace (DELETE + INSERT) inside a transaction.

        Args:
            xml_path: Path to Settings.xml.
            xml_type: ``"email"`` or ``"sftp"``.

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
                        1 if job.queue_one_file else (
                            0 if job.queue_one_file is not None else None
                        ),
                        json.dumps(job.templates),
                        job.day_adjust,
                        job.filters.get("From", "").strip(),
                        (
                            job.templates.get("Main", "")
                            or next(
                                (v for v in job.templates.values() if v), ""
                            )
                        ) if job.templates else "",
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
                        (
                            job.templates.get("Main", "")
                            or next(
                                (v for v in job.templates.values() if v), ""
                            )
                        ) if job.templates else "",
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

        Uses LIKE for SQL-level filtering, then applies
        :func:`_tokenized_match` for natural-language refinement
        (identical to current parser logic).

        Args:
            query: Free-text search query.
            xml_type: ``"email"``, ``"sftp"``, or ``"all"``.

        Returns:
            List of summary dicts matching the query.
        """
        results: List[Dict] = []
        like_param = f"%{query}%"
        params = [like_param] * 7  # 7 LIKE clauses in each search query

        if xml_type in ("email", "all"):
            cur = self._conn.execute(_SEARCH_EMAIL_JOBS, params)
            for row in cur.fetchall():
                row_dict = dict(row)
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

        Searches both tables (``email_jobs`` first, then ``sftp_jobs``).
        Returns ``None`` if not found.
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
        results: List[Dict] = []
        if xml_type in ("email", "all"):
            cur = self._conn.execute("SELECT * FROM email_jobs ORDER BY name")
            results.extend(self._email_row_to_summary(dict(r)) for r in cur)
        if xml_type in ("sftp", "all"):
            cur = self._conn.execute("SELECT * FROM sftp_jobs ORDER BY name")
            results.extend(self._sftp_row_to_summary(dict(r)) for r in cur)
        return results

    def find_jobs_by_servicer_ids(
        self, servicer_ids: set, xml_type: str = "all"
    ) -> List[Dict]:
        """Return summary dicts for jobs whose servicer_id is in *servicer_ids*."""
        if not servicer_ids:
            return []
        results: List[Dict] = []
        placeholders = ",".join("?" for _ in servicer_ids)
        ids = list(servicer_ids)
        if xml_type in ("email", "all"):
            cur = self._conn.execute(
                f"SELECT * FROM email_jobs WHERE servicer_id IN ({placeholders})",
                ids,
            )
            results.extend(self._email_row_to_summary(dict(r)) for r in cur)
        if xml_type in ("sftp", "all"):
            cur = self._conn.execute(
                f"SELECT * FROM sftp_jobs WHERE servicer_id IN ({placeholders})",
                ids,
            )
            results.extend(self._sftp_row_to_summary(dict(r)) for r in cur)
        return results

    # ------------------------------------------------------------------ #
    #  Hash / staleness
    # ------------------------------------------------------------------ #

    def check_hash(self, xml_path: str, xml_type: str = "email") -> Dict:
        """Compare stored content hash vs current XML.

        Returns:
            Dict with ``stored_hash``, ``current_hash``, ``is_fresh``,
            ``last_rebuild``.
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
        """Convert an ``email_jobs`` row to a summary dict matching
        ``EmailJob.to_summary_dict()`` output format."""
        return {
            "job_name": row["name"],
            "mailbox": row["mailbox"],
            "sender": row["sender"] or "(not specified)",
            "servicer_id": row["servicer_id"],
            "save_path": row["save_location"],
            "scrubber": row["scrubber"] or "(none)",
            "match_mode": row["match_mode"],
            "match_mode_description": _match_mode_description(row["match_mode"]),
            "queue_one_file": (
                bool(row["queue_one_file"])
                if row["queue_one_file"] is not None
                else None
            ),
            "xml_type": "email",
        }

    @staticmethod
    def _sftp_row_to_summary(row: Dict) -> Dict:
        """Convert an ``sftp_jobs`` row to a summary dict matching
        ``SftpJob.to_summary_dict()`` output format."""
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
        """Convert an ``email_jobs`` row to a full detail dict matching
        ``cmd_job_detail`` output format."""
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
            "queue_one_file": (
                bool(row["queue_one_file"])
                if row["queue_one_file"] is not None
                else None
            ),
            "xml_type": "email",
            "filters": json.loads(row["filters_json"]),
            "parsers": json.loads(row["parsers_json"]),
            "templates": json.loads(row["templates_json"]),
            "day_adjust": row["day_adjust"],
        }

    @staticmethod
    def _sftp_row_to_detail(row: Dict) -> Dict:
        """Convert an ``sftp_jobs`` row to a full detail dict."""
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

    def next_servicer_id(self, base_id: int) -> int:
        """Return the lowest integer >= *base_id* + 1 not already used by any job.

        Checks **both** ``email_jobs`` and ``sftp_jobs`` so that a ServicerID
        already claimed by an SFTP job is never re-issued to an email job (and
        vice-versa).  Walking the gap-free integer sequence guarantees the result
        is a true "next unused" value rather than simply ``max + 1``.

        Args:
            base_id: The ServicerID of the template / series anchor (e.g. 6007).

        Returns:
            First integer > *base_id* that is not present in either jobs table.
        """
        rows = self._conn.execute(
            """
            SELECT servicer_id FROM email_jobs WHERE servicer_id > ?
            UNION
            SELECT servicer_id FROM sftp_jobs  WHERE servicer_id > ?
            ORDER BY servicer_id
            """,
            (base_id, base_id),
        ).fetchall()

        used: set = {row[0] for row in rows if row[0] is not None}
        candidate = base_id + 1
        while candidate in used:
            candidate += 1
        return candidate

    # ------------------------------------------------------------------ #
    #  Cleanup / context manager
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the SQLite connection."""
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


# ===================================================================== #
#  Module-level helpers
# ===================================================================== #

def _compute_config_hash(xml_path: str, xml_type: str) -> str:
    """Compute SHA-256 hash of config-only XML content.

    Strips ``<LastRunTime>`` elements before hashing so that
    PowerShell's periodic updates don't trigger false staleness.
    """
    tree = ET.parse(xml_path)
    root = copy.deepcopy(tree.getroot())

    # Strip last_run_time elements (case-insensitive tag match)
    for elem in list(root.iter()):
        for child in list(elem):
            if child.tag.lower() in (
                "lastruntime", "last_run_time", "lastrundatetime",
            ):
                elem.remove(child)

    canonical = ET.tostring(root, encoding="unicode")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
