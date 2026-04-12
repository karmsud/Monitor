"""Log analytics — higher-level queries against the SQLite log index.

Provides aggregated views (deal activity, DID failures, job health,
daily summaries) on top of the raw ``log_events`` table populated by
:class:`backend.logs.indexer.LogIndexer`.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from backend.logs.models import DealActivity, DIDFailure, DailySummary, JobHealth

logger = logging.getLogger("frp.logs.analytics")

# Regex to extract DID keyword from failure messages
_DID_FAILURE_RE = re.compile(r"Did not find DID mapping for \[(.+?)\]")


class LogAnalytics:
    """Read-only analytics layer over the log-event SQLite database.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database created by :class:`LogIndexer`.
    """

    # Required tables that must exist in the database
    _REQUIRED_TABLES = {"log_events", "indexed_files", "index_metadata"}

    def __init__(self, db_path: str) -> None:
        self._conn: sqlite3.Connection | None = None
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Log database not found: {db_path}")

        self.db_path = db_path
        self._conn = self._connect()

        # Validate required tables
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing = {row["name"] for row in cursor.fetchall()}
        except Exception:
            self.close()
            raise

        missing = self._REQUIRED_TABLES - existing
        if missing:
            self.close()
            raise ValueError(
                f"Log database missing required tables: {', '.join(sorted(missing))}"
            )

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection with ``Row`` factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """Return the shared connection for this analytics instance."""
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def close(self) -> None:
        """Close the shared SQLite connection if it is still open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "LogAnalytics":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _since_date(self, days: int) -> str:
        """Return an ISO-format date string *days* in the past."""
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------ #
    #  Staleness check
    # ------------------------------------------------------------------ #

    def check_staleness(self) -> Optional[Dict]:
        """Return a warning dict if the last sync is older than 24 h.

        Returns ``None`` when data is fresh.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM index_metadata WHERE key = 'last_sync'"
        ).fetchone()

        if row is None:
            return {"warning": "Log index has never been synced."}

        try:
            last_sync = datetime.fromisoformat(row["value"])
        except (ValueError, TypeError):
            return {"warning": "Unable to parse last sync timestamp."}

        age = datetime.now(timezone.utc) - last_sync
        if age > timedelta(hours=24):
            hours = int(age.total_seconds() // 3600)
            return {
                "warning": (
                    f"Log index is {hours}h old (last sync: {row['value']}). "
                    "Run sync_logs to update."
                )
            }
        return None

    # ------------------------------------------------------------------ #
    #  Deal activity
    # ------------------------------------------------------------------ #

    def deal_activity(
        self,
        did_identifier: str,
        days: int = 30,
        import_did: Optional[str] = None,
    ) -> List[DealActivity]:
        """Return log events mentioning *did_identifier* (or *import_did*).

        Parameters
        ----------
        did_identifier : str
            Primary search keyword (name/number entered by the user).
        days : int
            Look-back window.
        import_did : str, optional
            Resolved ImportDID value to broaden the search.
        """
        since = self._since_date(days)
        keywords = [f"%{did_identifier}%"]
        if import_did and import_did.lower() != did_identifier.lower():
            keywords.append(f"%{import_did}%")

        placeholders = " OR ".join(["raw_line LIKE ?"] * len(keywords))
        sql = (
            f"SELECT timestamp, job_name, event_type, raw_line, log_file "
            f"FROM log_events "
            f"WHERE timestamp >= ? AND ({placeholders}) "
            f"ORDER BY timestamp DESC"
        )
        params = [since] + keywords

        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()

        return [
            DealActivity(
                timestamp=row["timestamp"],
                job_name=row["job_name"] or "",
                event_type=row["event_type"],
                detail=row["raw_line"] or "",
                log_file=row["log_file"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    #  DID failures
    # ------------------------------------------------------------------ #

    def did_failures(
        self,
        days: int = 30,
        job_filter: Optional[str] = None,
    ) -> List[DIDFailure]:
        """Aggregate DID-mapping-failure events.

        Parses the keyword from error messages using a regex, then groups
        by extracted ImportDID keyword.
        """
        since = self._since_date(days)
        sql = (
            "SELECT raw_line, job_name, timestamp FROM log_events "
            "WHERE event_type = 'did_mapping_failure' AND timestamp >= ?"
        )
        params: list = [since]
        if job_filter:
            sql += " AND job_name LIKE ?"
            params.append(f"%{job_filter}%")

        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()

        # Aggregate by keyword
        agg: Dict[str, Dict] = {}
        for row in rows:
            m = _DID_FAILURE_RE.search(row["raw_line"] or "")
            keyword = m.group(1) if m else (row["raw_line"] or "unknown")

            if keyword not in agg:
                agg[keyword] = {
                    "count": 0,
                    "jobs": set(),
                    "first": row["timestamp"],
                    "last": row["timestamp"],
                }
            entry = agg[keyword]
            entry["count"] += 1
            entry["jobs"].add(row["job_name"] or "unknown")
            if row["timestamp"] < entry["first"]:
                entry["first"] = row["timestamp"]
            if row["timestamp"] > entry["last"]:
                entry["last"] = row["timestamp"]

        return sorted(
            [
                DIDFailure(
                    import_did=k,
                    failure_count=v["count"],
                    affected_jobs=sorted(v["jobs"]),
                    first_seen=v["first"],
                    last_seen=v["last"],
                )
                for k, v in agg.items()
            ],
            key=lambda d: d.failure_count,
            reverse=True,
        )

    # ------------------------------------------------------------------ #
    #  Job health
    # ------------------------------------------------------------------ #

    def job_health(self, job_name: str, days: int = 30) -> JobHealth:
        """Compute health metrics for *job_name*.

        Raises
        ------
        ValueError
            If zero or more than one job matches the given name.
        """
        since = self._since_date(days)
        conn = self._get_conn()
        # Resolve job name — exact match first
        exact = conn.execute(
            "SELECT DISTINCT job_name FROM log_events WHERE job_name = ?",
            (job_name,),
        ).fetchall()
        if len(exact) == 1:
            resolved = exact[0]["job_name"]
        else:
            # Fuzzy match
            fuzzy = conn.execute(
                "SELECT DISTINCT job_name FROM log_events WHERE job_name LIKE ?",
                (f"%{job_name}%",),
            ).fetchall()
            if len(fuzzy) == 0:
                raise ValueError(f"No jobs match '{job_name}'")
            if len(fuzzy) > 1:
                names = [r["job_name"] for r in fuzzy]
                raise ValueError(
                    f"Ambiguous job name '{job_name}' — matches: {', '.join(names)}"
                )
            resolved = fuzzy[0]["job_name"]

        total_runs = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE job_name = ? AND event_type = 'job_start' AND timestamp >= ?",
            (resolved, since),
        ).fetchone()["cnt"]
        successful = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE job_name = ? AND event_type = 'job_complete' AND timestamp >= ?",
            (resolved, since),
        ).fetchone()["cnt"]
        error_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE job_name = ? AND event_type LIKE '%error%' AND timestamp >= ?",
            (resolved, since),
        ).fetchone()["cnt"]
        last_run_row = conn.execute(
            "SELECT timestamp FROM log_events "
            "WHERE job_name = ? AND event_type = 'job_start' "
            "ORDER BY timestamp DESC LIMIT 1",
            (resolved,),
        ).fetchone()
        last_run = last_run_row["timestamp"] if last_run_row else None
        last_err_row = conn.execute(
            "SELECT error_message FROM log_events "
            "WHERE job_name = ? AND event_type LIKE '%error%' "
            "ORDER BY timestamp DESC LIMIT 1",
            (resolved,),
        ).fetchone()
        last_error = last_err_row["error_message"] if last_err_row else None
        emails_row = conn.execute(
            "SELECT COALESCE(SUM(emails_found), 0) AS total "
            "FROM log_events "
            "WHERE job_name = ? AND emails_found IS NOT NULL AND timestamp >= ?",
            (resolved, since),
        ).fetchone()
        total_emails = emails_row["total"]
        avg_emails = round(total_emails / total_runs, 2) if total_runs else 0.0
        common_errors_rows = conn.execute(
            "SELECT error_message, COUNT(*) AS cnt FROM log_events "
            "WHERE job_name = ? AND event_type LIKE '%error%' AND timestamp >= ? "
            "GROUP BY error_message ORDER BY cnt DESC LIMIT 5",
            (resolved, since),
        ).fetchall()
        common_errors = [
            {"message": r["error_message"], "count": r["cnt"]}
            for r in common_errors_rows
        ]

        success_rate = round((successful / total_runs) * 100, 1) if total_runs else 0.0
        if success_rate > 95:
            status = "healthy"
        elif success_rate >= 80:
            status = "warning"
        else:
            status = "critical"

        return JobHealth(
            job_name=resolved,
            total_runs=total_runs,
            successful_runs=successful,
            error_count=error_count,
            success_rate=success_rate,
            status=status,
            last_run=last_run,
            last_error=last_error,
            avg_emails_per_run=avg_emails,
            common_errors=common_errors,
            date_range=f"Last {days} days",
        )

    # ------------------------------------------------------------------ #
    #  Daily summary
    # ------------------------------------------------------------------ #

    def daily_summary(self, date: Optional[str] = None) -> DailySummary:
        """Compute a one-day operational summary.

        Parameters
        ----------
        date : str, optional
            ISO date (``YYYY-MM-DD``).  Defaults to today (UTC).
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        date_prefix = f"{date}%"
        conn = self._get_conn()
        total_jobs = conn.execute(
            "SELECT COUNT(DISTINCT job_name) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type = 'job_start'",
            (date_prefix,),
        ).fetchone()["cnt"]
        total_emails = conn.execute(
            "SELECT COALESCE(SUM(emails_found), 0) AS total FROM log_events "
            "WHERE timestamp LIKE ? AND emails_found IS NOT NULL",
            (date_prefix,),
        ).fetchone()["total"]
        total_files = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type = 'file_loaded'",
            (date_prefix,),
        ).fetchone()["cnt"]
        total_errors = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type LIKE '%error%'",
            (date_prefix,),
        ).fetchone()["cnt"]
        total_did_failures = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type = 'did_mapping_failure'",
            (date_prefix,),
        ).fetchone()["cnt"]
        top_jobs = conn.execute(
            "SELECT job_name, COUNT(*) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND job_name IS NOT NULL "
            "GROUP BY job_name ORDER BY cnt DESC LIMIT 5",
            (date_prefix,),
        ).fetchall()
        top_jobs_list = [
            {"job_name": r["job_name"], "event_count": r["cnt"]}
            for r in top_jobs
        ]
        top_errors = conn.execute(
            "SELECT job_name, COUNT(*) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type LIKE '%error%' "
            "AND job_name IS NOT NULL "
            "GROUP BY job_name ORDER BY cnt DESC LIMIT 5",
            (date_prefix,),
        ).fetchall()
        top_error_sources = [
            {"job_name": r["job_name"], "error_count": r["cnt"]}
            for r in top_errors
        ]
        prev_date = (
            datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        prev_prefix = f"{prev_date}%"
        prev_errors = conn.execute(
            "SELECT COUNT(*) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type LIKE '%error%'",
            (prev_prefix,),
        ).fetchone()["cnt"]
        prev_jobs = conn.execute(
            "SELECT COUNT(DISTINCT job_name) AS cnt FROM log_events "
            "WHERE timestamp LIKE ? AND event_type = 'job_start'",
            (prev_prefix,),
        ).fetchone()["cnt"]

        comparison = {
            "previous_date": prev_date,
            "previous_errors": prev_errors,
            "error_change": total_errors - prev_errors,
            "previous_jobs_run": prev_jobs,
        }

        return DailySummary(
            date=date,
            total_jobs_run=total_jobs,
            total_emails_processed=total_emails,
            total_files_loaded=total_files,
            total_errors=total_errors,
            total_did_failures=total_did_failures,
            top_jobs_by_volume=top_jobs_list,
            top_error_sources=top_error_sources,
            comparison=comparison,
        )
