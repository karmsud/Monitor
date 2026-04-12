"""SQLite-based log-event indexer for FRP monitor logs.

Provides incremental sync (parse new files, skip already-indexed ones),
retention-based purging, and flexible querying of stored events.
"""

from __future__ import annotations

import glob
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from backend.logs.models import LogEvent
from backend.logs.parser import LogFileParser

logger = logging.getLogger("frp.logs.indexer")

# --------------------------------------------------------------------------- #
# Schema constants
# --------------------------------------------------------------------------- #

_SCHEMA_VERSION = "2"

_CREATE_LOG_EVENTS = """
CREATE TABLE IF NOT EXISTS log_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    log_file      TEXT    NOT NULL,
    log_type      TEXT    NOT NULL,
    timestamp     TEXT    NOT NULL,
    job_name      TEXT,
    mailbox       TEXT,
    email_event_id TEXT,
    email_event_index INTEGER,
    event_type    TEXT    NOT NULL,
    emails_found  INTEGER,
    subject       TEXT,
    sender        TEXT,
    parser        TEXT,
    filename      TEXT,
    template      TEXT,
    error_message TEXT,
    raw_line      TEXT
);
"""

_CREATE_LOG_EVENTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_log_events_job       ON log_events(job_name);",
    "CREATE INDEX IF NOT EXISTS idx_log_events_timestamp ON log_events(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_log_events_type      ON log_events(event_type);",
    "CREATE INDEX IF NOT EXISTS idx_log_events_log_file  ON log_events(log_file);",
    "CREATE INDEX IF NOT EXISTS idx_log_events_email_event_id ON log_events(email_event_id);",
]

_LOG_EVENTS_REQUIRED_COLUMNS = {
    "email_event_id": "TEXT",
    "email_event_index": "INTEGER",
}

_CREATE_INDEXED_FILES = """
CREATE TABLE IF NOT EXISTS indexed_files (
    filename    TEXT PRIMARY KEY,
    indexed_at  TEXT    NOT NULL,
    event_count INTEGER NOT NULL,
    file_size   INTEGER
);
"""

_CREATE_INDEX_METADATA = """
CREATE TABLE IF NOT EXISTS index_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_INSERT_EVENT = """
INSERT INTO log_events (
    log_file, log_type, timestamp, job_name, mailbox,
    email_event_id, email_event_index,
    event_type, emails_found, subject, sender, parser,
    filename, template, error_message, raw_line
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_INSERT_INDEXED_FILE = """
INSERT OR REPLACE INTO indexed_files (filename, indexed_at, event_count, file_size)
VALUES (?, ?, ?, ?);
"""


class LogIndexer:
    """Manage a SQLite database of indexed log events."""

    # ------------------------------------------------------------------ #
    # Construction / lifecycle
    # ------------------------------------------------------------------ #

    def __init__(self, db_path: str) -> None:
        """Connect (or create) the SQLite database at *db_path* and ensure
        all required tables and indexes exist.
        """
        self.db_path = db_path
        self._schema_rebuild_required = False
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create_tables()
        logger.info("LogIndexer ready (db=%s)", db_path)

    def _create_tables(self) -> None:
        """Idempotently create the schema."""
        cur = self._conn.cursor()
        cur.execute(_CREATE_LOG_EVENTS)
        cur.execute(_CREATE_INDEXED_FILES)
        cur.execute(_CREATE_INDEX_METADATA)
        self._conn.commit()

        # Seed schema_version if absent
        cur.execute(
            "INSERT OR IGNORE INTO index_metadata (key, value) VALUES (?, ?)",
            ("schema_version", _SCHEMA_VERSION),
        )
        self._ensure_log_event_columns(cur)
        for idx_sql in _CREATE_LOG_EVENTS_INDEXES:
            cur.execute(idx_sql)
        cur.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
            ("schema_version", _SCHEMA_VERSION),
        )
        self._conn.commit()

    def _ensure_log_event_columns(self, cur: sqlite3.Cursor) -> None:
        existing = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(log_events)").fetchall()
        }
        for column_name, column_type in _LOG_EVENTS_REQUIRED_COLUMNS.items():
            if column_name in existing:
                continue
            cur.execute(f"ALTER TABLE log_events ADD COLUMN {column_name} {column_type}")
            self._schema_rebuild_required = True

    # ------------------------------------------------------------------ #
    # Sync
    # ------------------------------------------------------------------ #

    def sync(
        self,
        log_folder: str,
        log_type: str = "email",
        retention_months: int = 3,
    ) -> Dict:
        """Full incremental sync of *log_folder*.

        1. List ``*.log`` files in *log_folder*.
        2. Skip files already present in ``indexed_files``.
        3. Parse each new file and bulk-insert its events.
        4. Purge events older than *retention_months*.
        5. Update ``index_metadata`` timestamps.
        6. Return a summary dict.
        """
        parser = LogFileParser()

        if self._schema_rebuild_required:
            self._reset_index_cache()
            self._schema_rebuild_required = False

        log_files = sorted(glob.glob(os.path.join(log_folder, "*.log")))
        files_processed = 0
        events_indexed = 0
        files_skipped = 0
        files_errored = 0
        errors: List[str] = []

        for filepath in log_files:
            basename = os.path.basename(filepath)

            if self._is_file_indexed(basename):
                files_skipped += 1
                continue

            try:
                events = parser.parse_file(filepath, log_type=log_type)
                self._bulk_insert_events(events)
                file_size = os.path.getsize(filepath)
                self._record_indexed_file(basename, len(events), file_size)
                files_processed += 1
                events_indexed += len(events)
            except Exception as exc:
                files_errored += 1
                msg = f"Error parsing {basename}: {exc}"
                errors.append(msg)
                logger.exception(msg)

        # Purge stale events
        events_purged = self._purge_old_events(retention_months)

        # Update metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        self._set_metadata("last_sync", now_iso)

        total_events = self._count_total_events()
        self._set_metadata("total_events", str(total_events))

        self._conn.commit()

        summary = {
            "files_processed": files_processed,
            "events_indexed": events_indexed,
            "files_skipped": files_skipped,
            "files_errored": files_errored,
            "events_purged": events_purged,
            "errors": errors,
        }
        logger.info("Sync complete: %s", summary)
        return summary

    def _reset_index_cache(self) -> None:
        """Clear derived log cache tables so the next sync fully rebuilds them."""
        self._conn.execute("DELETE FROM log_events")
        self._conn.execute("DELETE FROM indexed_files")
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Querying
    # ------------------------------------------------------------------ #

    def query_events(
        self,
        job_name: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
        job_name_like: Optional[str] = None,
        mailbox: Optional[str] = None,
        sender: Optional[str] = None,
        parser: Optional[str] = None,
        filename: Optional[str] = None,
        subject: Optional[str] = None,
        template: Optional[str] = None,
        log_type: Optional[str] = None,
        event_type_like: Optional[str] = None,
        text: Optional[str] = None,
    ) -> List[Dict]:
        """Return events matching the supplied filters.

        Results are ordered by ``timestamp DESC`` and capped at *limit*.
        Date filters compare against the ``timestamp`` column as text
        (ISO-8601 format allows direct string comparison).

        Use *job_name_like* for partial/substring matching (SQL LIKE).
        *job_name* takes precedence if both are given.
        """
        clauses: List[str] = []
        params: List = []

        if job_name is not None:
            clauses.append("job_name = ?")
            params.append(job_name)
        elif job_name_like is not None:
            clauses.append("job_name LIKE ?")
            params.append(f"%{job_name_like}%")
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        elif event_type_like is not None:
            clauses.append("LOWER(event_type) LIKE ?")
            params.append(f"%{event_type_like.lower()}%")
        if start_date is not None:
            clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("timestamp <= ?")
            params.append(end_date)
        if mailbox is not None:
            clauses.append("LOWER(COALESCE(mailbox, '')) LIKE ?")
            params.append(f"%{mailbox.lower()}%")
        if sender is not None:
            clauses.append("LOWER(COALESCE(sender, '')) LIKE ?")
            params.append(f"%{sender.lower()}%")
        if parser is not None:
            clauses.append("LOWER(COALESCE(parser, '')) LIKE ?")
            params.append(f"%{parser.lower()}%")
        if filename is not None:
            clauses.append("LOWER(COALESCE(filename, '')) LIKE ?")
            params.append(f"%{filename.lower()}%")
        if subject is not None:
            clauses.append("LOWER(COALESCE(subject, '')) LIKE ?")
            params.append(f"%{subject.lower()}%")
        if template is not None:
            clauses.append("LOWER(COALESCE(template, '')) LIKE ?")
            params.append(f"%{template.lower()}%")
        if log_type is not None:
            clauses.append("LOWER(COALESCE(log_type, '')) = ?")
            params.append(log_type.lower())
        if text is not None:
            clauses.append(
                "(" +
                " OR ".join([
                    "LOWER(COALESCE(job_name, '')) LIKE ?",
                    "LOWER(COALESCE(mailbox, '')) LIKE ?",
                    "LOWER(COALESCE(subject, '')) LIKE ?",
                    "LOWER(COALESCE(sender, '')) LIKE ?",
                    "LOWER(COALESCE(parser, '')) LIKE ?",
                    "LOWER(COALESCE(filename, '')) LIKE ?",
                    "LOWER(COALESCE(template, '')) LIKE ?",
                    "LOWER(COALESCE(raw_line, '')) LIKE ?",
                ]) +
                ")"
            )
            pattern = f"%{text.lower()}%"
            params.extend([pattern] * 8)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM log_events{where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def get_job_summary(self, job_name: str) -> Dict:
        """Return aggregate statistics for *job_name*.

        Keys: ``job_name``, ``first_seen``, ``last_seen``, ``total_events``,
        ``total_files_loaded``, ``total_errors``,
        ``total_emails_found``, ``unique_senders``, ``unique_parsers``.
        """
        base = (
            "SELECT "
            "  MIN(timestamp)  AS first_seen, "
            "  MAX(timestamp)  AS last_seen, "
            "  COUNT(*)        AS total_events "
            "FROM log_events WHERE job_name = ?"
        )
        row = self._conn.execute(base, (job_name,)).fetchone()

        files_loaded = self._conn.execute(
            "SELECT COUNT(*) FROM log_events WHERE job_name = ? AND event_type = 'file_load'",
            (job_name,),
        ).fetchone()[0]

        total_errors = self._conn.execute(
            "SELECT COUNT(*) FROM log_events WHERE job_name = ? AND event_type IN ('error', 'did_mapping_failed')",
            (job_name,),
        ).fetchone()[0]

        total_emails = self._conn.execute(
            "SELECT COALESCE(SUM(emails_found), 0) FROM log_events WHERE job_name = ? AND event_type = 'found_count'",
            (job_name,),
        ).fetchone()[0]

        unique_senders = self._conn.execute(
            "SELECT COUNT(DISTINCT sender) FROM log_events WHERE job_name = ? AND sender IS NOT NULL",
            (job_name,),
        ).fetchone()[0]

        unique_parsers = self._conn.execute(
            "SELECT COUNT(DISTINCT parser) FROM log_events WHERE job_name = ? AND parser IS NOT NULL",
            (job_name,),
        ).fetchone()[0]

        return {
            "job_name": job_name,
            "first_seen": row["first_seen"] if row else None,
            "last_seen": row["last_seen"] if row else None,
            "total_events": row["total_events"] if row else 0,
            "total_files_loaded": files_loaded,
            "total_errors": total_errors,
            "total_emails_found": total_emails,
            "unique_senders": unique_senders,
            "unique_parsers": unique_parsers,
        }

    def search_jobs(self, query: str, limit: int = 20) -> List[Dict]:
        """Return job summaries for jobs whose names match *query* (LIKE).

        Uses a single aggregated query instead of per-job lookups to stay
        fast over network-mounted SQLite databases.
        """
        sql = (
            "SELECT "
            "  job_name, "
            "  MIN(timestamp) AS first_seen, "
            "  MAX(timestamp) AS last_seen, "
            "  COUNT(*)       AS total_events, "
            "  SUM(CASE WHEN event_type = 'file_load' THEN 1 ELSE 0 END) AS total_files_loaded, "
            "  SUM(CASE WHEN event_type IN ('error','did_mapping_failed') THEN 1 ELSE 0 END) AS total_errors, "
            "  COALESCE(SUM(CASE WHEN event_type = 'found_count' THEN emails_found ELSE 0 END), 0) AS total_emails_found, "
            "  COUNT(DISTINCT CASE WHEN sender IS NOT NULL THEN sender END) AS unique_senders, "
            "  COUNT(DISTINCT CASE WHEN parser IS NOT NULL THEN parser END) AS unique_parsers "
            "FROM log_events "
            "WHERE job_name LIKE ? "
            "GROUP BY job_name "
            "ORDER BY job_name "
            "LIMIT ?"
        )
        rows = self._conn.execute(sql, (f"%{query}%", limit)).fetchall()
        return [
            {
                "job_name": row["job_name"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "total_events": row["total_events"],
                "total_files_loaded": row["total_files_loaded"],
                "total_errors": row["total_errors"],
                "total_emails_found": row["total_emails_found"],
                "unique_senders": row["unique_senders"],
                "unique_parsers": row["unique_parsers"],
            }
            for row in rows
            if row["job_name"]
        ]

    def get_sync_status(self) -> Dict:
        """Return a dict describing the current state of the index database."""
        total_events = self._count_total_events()

        total_files = self._conn.execute(
            "SELECT COUNT(*) FROM indexed_files"
        ).fetchone()[0]

        last_sync = self._get_metadata("last_sync")
        schema_version = self._get_metadata("schema_version")

        try:
            db_size_bytes = os.path.getsize(self.db_path)
            db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
        except OSError:
            db_size_mb = 0.0

        return {
            "db_path": self.db_path,
            "last_sync": last_sync,
            "total_events": total_events,
            "total_files_indexed": total_files,
            "schema_version": schema_version,
            "db_size_mb": db_size_mb,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _is_file_indexed(self, filename: str) -> bool:
        """Check whether *filename* has already been indexed."""
        row = self._conn.execute(
            "SELECT 1 FROM indexed_files WHERE filename = ?", (filename,)
        ).fetchone()
        return row is not None

    def _record_indexed_file(
        self, filename: str, event_count: int, file_size: int
    ) -> None:
        """Insert or update the ``indexed_files`` record for *filename*."""
        self._conn.execute(
            _INSERT_INDEXED_FILE,
            (filename, datetime.now(timezone.utc).isoformat(), event_count, file_size),
        )
        self._conn.commit()

    def _bulk_insert_events(self, events: List[LogEvent]) -> None:
        """Insert a batch of :class:`LogEvent` rows inside a transaction."""
        cur = self._conn.cursor()
        for ev in events:
            cur.execute(
                _INSERT_EVENT,
                (
                    ev.log_file,
                    ev.log_type,
                    ev.timestamp,
                    ev.job_name,
                    ev.mailbox,
                    ev.email_event_id,
                    ev.email_event_index,
                    ev.event_type,
                    ev.emails_found,
                    ev.subject,
                    ev.sender,
                    ev.parser,
                    ev.filename,
                    ev.template,
                    ev.error_message,
                    ev.raw_line,
                ),
            )
        self._conn.commit()

    def _purge_old_events(self, retention_months: int) -> int:
        """Delete events whose timestamp is older than *retention_months*.

        Returns the number of rows deleted.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_months * 30)
        ).strftime("%Y-%m-%d")
        cur = self._conn.execute(
            "DELETE FROM log_events WHERE timestamp < ?", (cutoff,)
        )
        deleted = cur.rowcount
        if deleted:
            self._conn.commit()
            logger.info("Purged %d events older than %s", deleted, cutoff)
        return deleted

    def _count_total_events(self) -> int:
        """Return the current row count in ``log_events``."""
        return self._conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]

    def _set_metadata(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _get_metadata(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM index_metadata WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    # ------------------------------------------------------------------ #
    # Error detail retrieval
    # ------------------------------------------------------------------ #

    def get_job_errors(
        self,
        job_name: str,
        limit: int = 25,
    ) -> List[Dict]:
        """Return error and DID-mapping-failure events for *job_name*.

        Returns the most recent errors with timestamp, error_message,
        event_type, subject, sender, and raw_line for diagnosis.
        """
        sql = (
            "SELECT timestamp, event_type, error_message, subject, sender, "
            "       filename, template, raw_line "
            "FROM log_events "
            "WHERE job_name = ? AND event_type IN ('error', 'did_mapping_failed', 'did_mapping_failure') "
            "ORDER BY timestamp DESC LIMIT ?"
        )
        cur = self._conn.execute(sql, (job_name, limit))
        return [dict(row) for row in cur.fetchall()]

    def get_job_activity(
        self,
        job_name: str,
        limit: int = 50,
    ) -> List[Dict]:
        """Return only actionable events for *job_name* (no job_start/found_count noise).

        Includes: processing, from, parser_match, file_load, template_queue,
        did_match, did_mapping_failed, error.
        """
        sql = (
            "SELECT timestamp, event_type, error_message, subject, sender, "
            "       filename, template, parser, emails_found, raw_line "
            "FROM log_events "
            "WHERE job_name = ? "
            "  AND event_type NOT IN ('job_start', 'info', 'job_complete') "
            "ORDER BY timestamp DESC LIMIT ?"
        )
        cur = self._conn.execute(sql, (job_name, limit))
        return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------ #
    # Cleanup / context manager
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn is not None:
            try:
                self._conn.close()
                logger.info("LogIndexer connection closed.")
            except Exception:
                logger.debug("SQLite connection already closed.")
            finally:
                self._conn = None

    def __enter__(self) -> "LogIndexer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
