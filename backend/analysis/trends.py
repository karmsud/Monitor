"""L-06: Timeline trend analysis.

Aggregates daily log metrics into a trend summary with
period-over-period comparisons and directional indicators.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from backend.analysis.models import TrendDay, TrendSummary

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Produce daily trend summaries from the log-event SQLite database."""

    def __init__(self, analytics) -> None:
        """
        Args:
            analytics: A LogAnalytics instance (Phase 3).
        """
        self._analytics = analytics

    def analyze(
        self, days: int = 14, job_filter: Optional[str] = None
    ) -> TrendSummary:
        """Build a TrendSummary spanning *days* calendar days.

        Args:
            days: Number of calendar days to include (default 14).
            job_filter: If set, limit to this job name.

        Returns:
            TrendSummary with per-day metrics, totals, and comparison.
        """
        if days <= 0 or days > 365:
            raise ValueError(f"days must be 1–365; got {days}")

        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        # Current period
        data = self._query_period(start_date, end_date, job_filter)
        day_list = self._build_day_list(start_date, end_date, data)
        self._add_trend_indicators(day_list)

        # Previous period (same length, for comparison)
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)
        prev_data = self._query_period(prev_start, prev_end, job_filter)

        # Totals
        total_files = sum(d.total_files for d in day_list)
        total_errors = sum(d.total_errors for d in day_list)
        total_did_failures = sum(d.did_failures for d in day_list)

        prev_total_files = sum(v.get("total_files", 0) for v in prev_data.values())
        prev_total_errors = sum(v.get("total_errors", 0) for v in prev_data.values())

        # Avg
        avg_files = total_files / days if days > 0 else 0.0

        # Best / worst day
        best_day = None
        worst_day = None
        if day_list:
            best = min(day_list, key=lambda d: d.total_errors)
            worst = max(day_list, key=lambda d: d.total_errors)
            best_day = best.date
            worst_day = worst.date

        # Staleness warning
        staleness = self._analytics.check_staleness()
        staleness_warning = staleness.get("warning") if staleness else None

        return TrendSummary(
            days=day_list,
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            period_days=days,
            totals={
                "total_files": total_files,
                "total_errors": total_errors,
                "total_did_failures": total_did_failures,
            },
            avg_files_per_day=round(avg_files, 2),
            vs_previous_period={
                "prev_total_files": prev_total_files,
                "prev_total_errors": prev_total_errors,
                "file_change_pct": round(
                    ((total_files - prev_total_files) / prev_total_files * 100)
                    if prev_total_files > 0
                    else 0.0,
                    1,
                ),
                "error_change_pct": round(
                    ((total_errors - prev_total_errors) / prev_total_errors * 100)
                    if prev_total_errors > 0
                    else 0.0,
                    1,
                ),
            },
            worst_day=worst_day,
            best_day=best_day,
            staleness_warning=staleness_warning,
            job_filter=job_filter,
        )

    # ─── Internal ─────────────────────────────────────────────────

    def _query_period(
        self,
        start_date: date,
        end_date: date,
        job_filter: Optional[str] = None,
    ) -> Dict[str, Dict]:
        """Batch SQL query: GROUP BY date(timestamp).

        Returns:
            { "YYYY-MM-DD": {"total_files": N, "total_errors": N, ...}, ... }
        """
        conn = self._analytics._get_conn()
        try:
            sql = """
                SELECT
                    date(timestamp) AS day,
                    SUM(CASE WHEN event_type = 'file_processed' THEN 1 ELSE 0 END) AS total_files,
                    SUM(CASE WHEN event_type IN ('error', 'parse_error') THEN 1 ELSE 0 END) AS total_errors,
                    SUM(CASE WHEN event_type = 'did_failure' THEN 1 ELSE 0 END) AS did_failures,
                    COUNT(DISTINCT job_name) AS job_runs
                FROM log_events
                WHERE date(timestamp) BETWEEN ? AND ?
            """
            params: list = [start_date.isoformat(), end_date.isoformat()]

            if job_filter:
                sql += " AND job_name = ?"
                params.append(job_filter)

            sql += " GROUP BY date(timestamp) ORDER BY day"

            rows = conn.execute(sql, params).fetchall()
            result: Dict[str, Dict] = {}
            for row in rows:
                result[row["day"]] = {
                    "total_files": row["total_files"] or 0,
                    "total_errors": row["total_errors"] or 0,
                    "did_failures": row["did_failures"] or 0,
                    "job_runs": row["job_runs"] or 0,
                }
            return result
        finally:
            conn.close()

    def _build_day_list(
        self,
        start_date: date,
        end_date: date,
        data: Dict[str, Dict],
    ) -> List[TrendDay]:
        """Fill the date range, inserting zero-days for gaps."""
        result: List[TrendDay] = []
        current = start_date
        while current <= end_date:
            iso = current.isoformat()
            metrics = data.get(iso, {})
            result.append(
                TrendDay(
                    date=iso,
                    total_files=metrics.get("total_files", 0),
                    total_errors=metrics.get("total_errors", 0),
                    did_failures=metrics.get("did_failures", 0),
                    job_runs=metrics.get("job_runs", 0),
                )
            )
            current += timedelta(days=1)
        return result

    @staticmethod
    def _add_trend_indicators(days: List[TrendDay]) -> None:
        """Compare consecutive days and set ↑/↓/→ indicators."""
        for i in range(1, len(days)):
            prev = days[i - 1]
            curr = days[i]

            # Files trend
            if curr.total_files > prev.total_files:
                curr.trend_files = "↑"
            elif curr.total_files < prev.total_files:
                curr.trend_files = "↓"
            else:
                curr.trend_files = "→"

            # Errors trend
            if curr.total_errors > prev.total_errors:
                curr.trend_errors = "↑"
            elif curr.total_errors < prev.total_errors:
                curr.trend_errors = "↓"
            else:
                curr.trend_errors = "→"
