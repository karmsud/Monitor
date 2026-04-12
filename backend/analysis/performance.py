"""L-07: Job performance benchmarking.

Ranks all jobs by success rate using a single batch SQL query.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from backend.analysis.models import PerformanceEntry, PerformanceSummary

logger = logging.getLogger(__name__)

# Status thresholds
HEALTHY_THRESHOLD = 95.0
WARNING_THRESHOLD = 80.0


class PerformanceBenchmarker:
    """Benchmark job performance from log-event data."""

    def __init__(self, analytics, parser=None) -> None:
        """
        Args:
            analytics: LogAnalytics instance (Phase 3).
            parser: SettingsXmlParser instance (Phase 1) — optional.
        """
        self._analytics = analytics
        self._parser = parser

    def benchmark(
        self,
        sort_by: str = "success_rate",
        ascending: bool = True,
        top_n: Optional[int] = None,
        days: int = 30,
    ) -> PerformanceSummary:
        """Produce a ranked performance summary.

        Args:
            sort_by: Field to rank by (default ``success_rate``).
            ascending: Sort direction (default ``True`` = worst first).
            top_n: Limit output to top N entries.
            days: Look-back window in days (default 30).

        Returns:
            PerformanceSummary with ranked entries and counts.
        """
        job_names = self._get_all_job_names()
        if not job_names:
            staleness = self._analytics.check_staleness()
            return PerformanceSummary(
                entries=[],
                total_jobs=0,
                staleness_warning=staleness.get("warning") if staleness else None,
                sort_key=sort_by,
                period_days=days,
            )

        metrics = self._batch_query_metrics(days)

        entries: List[PerformanceEntry] = []
        for name in job_names:
            m = metrics.get(name, {})
            total_files = m.get("total_files", 0)
            total_errors = m.get("total_errors", 0)
            total_events = total_files + total_errors
            total_runs = m.get("total_runs", 0)
            last_run = m.get("last_run")

            success_rate = (
                (total_files / total_events * 100) if total_events > 0 else 100.0
            )

            avg_per_run = (
                (total_files / total_runs) if total_runs > 0 else 0.0
            )

            # Common errors
            common = m.get("common_errors", [])

            # Status classification
            if total_events == 0:
                status = "unknown"
            elif success_rate >= HEALTHY_THRESHOLD:
                status = "healthy"
            elif success_rate >= WARNING_THRESHOLD:
                status = "warning"
            else:
                status = "critical"

            entries.append(
                PerformanceEntry(
                    job_name=name,
                    job_type=self._get_job_type(name),
                    total_runs=total_runs,
                    total_files=total_files,
                    total_errors=total_errors,
                    success_rate=round(success_rate, 2),
                    avg_files_per_run=round(avg_per_run, 2),
                    last_run=last_run,
                    status=status,
                    common_errors=common,
                )
            )

        # Sort
        reverse = not ascending
        entries.sort(key=lambda e: getattr(e, sort_by, 0), reverse=reverse)

        # Rank
        for i, entry in enumerate(entries, 1):
            entry.rank = i

        # Top-N
        if top_n is not None and top_n > 0:
            entries = entries[:top_n]

        # Counts
        healthy = sum(1 for e in entries if e.status == "healthy")
        warning = sum(1 for e in entries if e.status == "warning")
        critical = sum(1 for e in entries if e.status == "critical")
        unknown = sum(1 for e in entries if e.status == "unknown")
        rates = [e.success_rate for e in entries if e.status != "unknown"]
        avg_rate = sum(rates) / len(rates) if rates else 100.0

        staleness = self._analytics.check_staleness()

        return PerformanceSummary(
            entries=entries,
            total_jobs=len(entries),
            healthy_count=healthy,
            warning_count=warning,
            critical_count=critical,
            unknown_count=unknown,
            avg_success_rate=round(avg_rate, 2),
            sort_key=sort_by,
            period_days=days,
            staleness_warning=staleness.get("warning") if staleness else None,
        )

    # ─── Internal ─────────────────────────────────────────────────

    def _get_all_job_names(self) -> List[str]:
        """Union of parser job names and SQLite distinct job_names."""
        names: set[str] = set()

        if self._parser:
            try:
                for job in self._parser.get_all_jobs():
                    name = getattr(job, "name", None)
                    if name:
                        names.add(str(name))
            except Exception as e:
                logger.warning(f"Parser job list failed: {e}")

        conn = self._analytics._get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT job_name FROM log_events"
            ).fetchall()
            for row in rows:
                if row["job_name"]:
                    names.add(row["job_name"])
        except Exception as e:
            logger.warning(f"SQLite job list failed: {e}")
        finally:
            conn.close()

        return sorted(names)

    def _batch_query_metrics(self, days: int) -> Dict[str, Dict]:
        """Single aggregate SQL query grouped by job_name.

        Returns:
            { "JobName": { "total_files": N, "total_errors": N,
                           "total_runs": N, "last_run": "...",
                           "common_errors": [...] }, ... }
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        conn = self._analytics._get_conn()
        result: Dict[str, Dict] = {}
        try:
            rows = conn.execute(
                """
                SELECT
                    job_name,
                    SUM(CASE WHEN event_type = 'file_processed' THEN 1 ELSE 0 END) AS total_files,
                    SUM(CASE WHEN event_type IN ('error', 'parse_error') THEN 1 ELSE 0 END) AS total_errors,
                    COUNT(DISTINCT date(timestamp)) AS total_runs,
                    MAX(timestamp) AS last_run
                FROM log_events
                WHERE date(timestamp) >= ?
                GROUP BY job_name
                """,
                (cutoff,),
            ).fetchall()

            for row in rows:
                name = row["job_name"]
                result[name] = {
                    "total_files": row["total_files"] or 0,
                    "total_errors": row["total_errors"] or 0,
                    "total_runs": row["total_runs"] or 0,
                    "last_run": row["last_run"],
                    "common_errors": [],
                }

            # Common errors per job (top 3)
            error_rows = conn.execute(
                """
                SELECT job_name, error_message, COUNT(*) AS cnt
                FROM log_events
                WHERE event_type IN ('error', 'parse_error')
                  AND date(timestamp) >= ?
                GROUP BY job_name, error_message
                ORDER BY job_name, cnt DESC
                """,
                (cutoff,),
            ).fetchall()

            for erow in error_rows:
                name = erow["job_name"]
                if name in result:
                    errs = result[name]["common_errors"]
                    if len(errs) < 3 and erow["error_message"]:
                        errs.append(erow["error_message"])

        finally:
            conn.close()

        return result

    def _get_job_type(self, job_name: str) -> str:
        """Determine job type from parser data."""
        if not self._parser:
            return "unknown"
        try:
            email_jobs = getattr(self._parser, "email_jobs", [])
            sftp_jobs = getattr(self._parser, "sftp_jobs", [])
            for j in email_jobs:
                if getattr(j, "name", "") == job_name:
                    return "email"
            for j in sftp_jobs:
                if getattr(j, "name", "") == job_name:
                    return "sftp"
        except Exception:
            pass
        return "unknown"
