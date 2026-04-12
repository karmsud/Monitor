# Phase 4: Technical Design
## FRP Agent — Advanced Analysis Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Estimated New/Changed Lines:** ~1,200 Python + ~250 JS = ~1,450 total  
**New Tests:** ~120 tests  

---

## Table of Contents
1. [Analysis Data Models](#1-analysis-data-models)
2. [Trend Analyzer](#2-trend-analyzer)
3. [Performance Benchmarker](#3-performance-benchmarker)
4. [Consolidation Analyzer](#4-consolidation-analyzer)
5. [Impact Simulator](#5-impact-simulator)
6. [Health Checker Orchestrator](#6-health-checker-orchestrator)
7. [CLI Command Implementations](#7-cli-command-implementations)
8. [Extension Handler Contracts](#8-extension-handler-contracts)
9. [Error Handling](#9-error-handling)
10. [File Manifest](#10-file-manifest)

---

## 1. Analysis Data Models

### backend/analysis/models.py (new file)

```python
"""Data models for Phase 4 advanced analysis results."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TrendDay:
    """Daily aggregated metrics for trend timeline."""
    date: str                       # "2026-02-24"
    total_files: int                # Files processed that day
    total_errors: int               # Error events that day
    did_failures: int               # DID mapping failures
    job_runs: int                   # Distinct jobs that ran
    trend_files: str = "→"          # "↑", "↓", "→" vs previous day
    trend_errors: str = "→"         # "↑", "↓", "→" vs previous day

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrendSummary:
    """Complete trend analysis result for a time window."""
    days: list[TrendDay]
    period_start: str               # ISO date
    period_end: str                 # ISO date
    period_days: int                # Requested window size
    period_total_files: int
    period_total_errors: int
    period_avg_files_per_day: float
    vs_previous_period: Optional[dict] = None
    # {"files_delta_pct": 12.3, "errors_delta_pct": -5.1,
    #  "prev_total_files": 1372, "prev_total_errors": 19}
    worst_day: Optional[str] = None     # Date with most errors
    best_day: Optional[str] = None      # Date with most files + 0 errors
    staleness_warning: Optional[str] = None
    job_filter: Optional[str] = None    # If filtered to specific job

    def to_dict(self) -> dict:
        d = asdict(self)
        d["days"] = [day.to_dict() for day in self.days]
        return d


@dataclass
class PerformanceEntry:
    """Performance metrics for a single monitoring job."""
    job_name: str
    job_type: str                   # "email" or "sftp"
    total_runs: int                 # Distinct log files with job_start
    total_files: int                # email_processed events
    total_errors: int               # error events
    success_rate: float             # 0.0 – 100.0
    avg_files_per_run: float
    last_run: Optional[str] = None  # ISO timestamp
    status: str = "unknown"         # "healthy", "warning", "critical", "unknown"
    common_errors: list[dict] = field(default_factory=list)
    # [{"error": "Connection timeout", "count": 4}, ...]
    rank: int = 0                   # 1-based rank in sorted results

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PerformanceSummary:
    """Aggregated performance report across all jobs."""
    entries: list[PerformanceEntry]
    total_jobs: int
    healthy_count: int
    warning_count: int
    critical_count: int
    unknown_count: int              # Jobs with no log data
    avg_success_rate: float
    sort_key: str                   # What metric was used for sorting
    period_days: int
    staleness_warning: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entries"] = [e.to_dict() for e in self.entries]
        return d


@dataclass
class ConsolidationCandidate:
    """A single job within a consolidation group."""
    name: str
    servicer_id: Optional[str]
    did_count: int                  # DIDs mapped to this servicer
    unique_attributes: dict         # Attributes that differ from group common
    # e.g., {"SenderFilter": "reports@csmc.com", "SubjectFilter": "CSMC 2015-1"}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConsolidationGroup:
    """Group of jobs sharing identical core configuration."""
    group_id: int
    shared_mailbox: str             # Common mailbox or path
    shared_parser: str              # Common parser type
    shared_template: str            # Common template name (or "none")
    jobs: list[ConsolidationCandidate]
    total_dids_affected: int
    merge_recommendation: str       # "safe", "review", "risky"
    rationale: str                  # Human-readable explanation

    def to_dict(self) -> dict:
        d = asdict(self)
        d["jobs"] = [j.to_dict() for j in self.jobs]
        return d


@dataclass
class ConsolidationReport:
    """Complete consolidation analysis output."""
    groups: list[ConsolidationGroup]
    total_groups: int
    total_jobs_affected: int
    total_dids_affected: int
    xml_type_analyzed: str          # "email", "sftp", "all"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["groups"] = [g.to_dict() for g in self.groups]
        return d


@dataclass
class ChangeSpec:
    """Parsed user intent for a configuration change."""
    change_type: str                # "delete_job", "rename_did", "change_filter", "move_servicer"
    target_job: Optional[str] = None
    target_did: Optional[str] = None        # ImportDID keyword
    target_company_id: Optional[int] = None
    new_value: Optional[str] = None
    raw_description: str = ""       # Original user input

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ChangeSpec":
        """Construct from parsed LLM JSON output."""
        return ChangeSpec(
            change_type=d.get("change_type", "unknown"),
            target_job=d.get("target_job"),
            target_did=d.get("target_did"),
            target_company_id=d.get("target_company_id"),
            new_value=d.get("new_value"),
            raw_description=d.get("raw_description", ""),
        )


@dataclass
class AffectedEntity:
    """An entity impacted by a proposed change."""
    entity_type: str                # "deal", "job", "did_mapping"
    identifier: str                 # DID name, job name, or ImportDID
    detail: str                     # Human-readable impact description
    severity: str                   # "high", "medium", "low"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ImpactReport:
    """Result of change impact simulation."""
    change: ChangeSpec
    affected: list[AffectedEntity]
    coverage_before: int            # DIDs covered before change
    coverage_after: int             # DIDs covered after change (projected)
    coverage_delta: int             # Difference
    recent_activity: bool           # Whether affected jobs had activity in last 7 days
    risk_level: str                 # "low", "medium", "high"
    recommendation: str             # Human-readable recommendation

    def to_dict(self) -> dict:
        d = asdict(self)
        d["change"] = self.change.to_dict()
        d["affected"] = [a.to_dict() for a in self.affected]
        return d


@dataclass
class HealthSection:
    """One section of the health check report."""
    name: str                       # "XML Validation", "Coverage Rate", etc.
    status: str                     # "pass", "warning", "fail"
    score: float                    # 0.0 – 100.0
    weight: float                   # 0.0 – 1.0
    summary: str                    # One-line result summary
    details: dict                   # Section-specific data
    action_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HealthReport:
    """Complete system health check result."""
    sections: list[HealthSection]
    overall_score: float            # 0.0 – 100.0 weighted average
    overall_status: str             # "Healthy", "Attention Needed", "Action Required"
    generated_at: str               # ISO timestamp
    xml_type: str                   # "email", "sftp", "all"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sections"] = [s.to_dict() for s in self.sections]
        return d
```

---

## 2. Trend Analyzer

### backend/analysis/trends.py (new file)

```python
"""
L-06: Timeline trend analysis over SQLite log index.

Aggregates daily event counts into time-series data with directional
trend indicators and optional period-over-period comparison.
"""

import logging
from datetime import datetime, timedelta

from backend.analysis.models import TrendDay, TrendSummary

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Aggregate daily log event counts into time-series trends."""

    def __init__(self, analytics):
        """
        Args:
            analytics: LogAnalytics instance (from Phase 3)
                       Must expose ._db_path and ._get_conn() for direct SQL access.
        """
        self._analytics = analytics

    def analyze(
        self,
        days: int = 14,
        job_filter: str | None = None,
    ) -> TrendSummary:
        """
        Generate a TrendSummary for the requested period.

        Args:
            days: Number of days to analyze (default: 14)
            job_filter: Optional job name filter (exact match)

        Returns:
            TrendSummary with daily breakdowns and period comparison
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days - 1)

        # Check staleness
        staleness = self._analytics.check_staleness()
        staleness_warning = staleness.get("warning") if staleness else None

        # Query current period
        current_data = self._query_period(start_date, end_date, job_filter)

        # Build day-by-day list, filling gaps with zeros
        all_days = self._build_day_list(start_date, end_date, current_data)

        # Add trend indicators
        self._add_trend_indicators(all_days)

        # Calculate period totals
        total_files = sum(d.total_files for d in all_days)
        total_errors = sum(d.total_errors for d in all_days)
        avg_files = total_files / len(all_days) if all_days else 0.0

        # Find best/worst days
        worst_day = None
        best_day = None
        if all_days:
            error_days = [d for d in all_days if d.total_errors > 0]
            if error_days:
                worst_day = max(error_days, key=lambda d: d.total_errors).date
            zero_error_days = [d for d in all_days if d.total_errors == 0 and d.total_files > 0]
            if zero_error_days:
                best_day = max(zero_error_days, key=lambda d: d.total_files).date

        # Period-over-period comparison
        vs_previous = None
        prev_start = start_date - timedelta(days=days)
        prev_end = start_date - timedelta(days=1)
        prev_data = self._query_period(prev_start, prev_end, job_filter)
        if prev_data:
            prev_files = sum(r["total_files"] for r in prev_data.values())
            prev_errors = sum(r["total_errors"] for r in prev_data.values())
            if prev_files > 0 or prev_errors > 0:
                files_delta_pct = (
                    ((total_files - prev_files) / prev_files * 100)
                    if prev_files > 0 else 0.0
                )
                errors_delta_pct = (
                    ((total_errors - prev_errors) / prev_errors * 100)
                    if prev_errors > 0 else 0.0
                )
                vs_previous = {
                    "files_delta_pct": round(files_delta_pct, 1),
                    "errors_delta_pct": round(errors_delta_pct, 1),
                    "prev_total_files": prev_files,
                    "prev_total_errors": prev_errors,
                }

        return TrendSummary(
            days=all_days,
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            period_days=days,
            period_total_files=total_files,
            period_total_errors=total_errors,
            period_avg_files_per_day=round(avg_files, 1),
            vs_previous_period=vs_previous,
            worst_day=worst_day,
            best_day=best_day,
            staleness_warning=staleness_warning,
            job_filter=job_filter,
        )

    def _query_period(
        self,
        start_date,
        end_date,
        job_filter: str | None,
    ) -> dict:
        """
        Query SQLite for daily aggregated event counts.

        Returns:
            dict keyed by date string: {
                "2026-02-24": {
                    "total_files": 123,
                    "total_errors": 2,
                    "did_failures": 1,
                    "job_runs": 48
                }
            }
        """
        conn = self._analytics._get_conn()
        try:
            params = [start_date.isoformat(), end_date.isoformat()]
            job_clause = ""
            if job_filter:
                job_clause = "AND job_name = ?"
                params.append(job_filter)

            rows = conn.execute(
                f"""
                SELECT
                    date(timestamp) AS day,
                    SUM(CASE WHEN event_type = 'email_processed' THEN 1 ELSE 0 END) AS total_files,
                    SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) AS total_errors,
                    SUM(CASE WHEN event_type = 'did_mapping_failure' THEN 1 ELSE 0 END) AS did_failures,
                    COUNT(DISTINCT CASE WHEN event_type = 'job_start' THEN job_name END) AS job_runs
                FROM log_events
                WHERE date(timestamp) >= ? AND date(timestamp) <= ?
                  {job_clause}
                GROUP BY date(timestamp)
                ORDER BY day ASC
                """,
                params
            ).fetchall()

            result = {}
            for r in rows:
                result[r["day"]] = {
                    "total_files": r["total_files"] or 0,
                    "total_errors": r["total_errors"] or 0,
                    "did_failures": r["did_failures"] or 0,
                    "job_runs": r["job_runs"] or 0,
                }
            return result
        finally:
            conn.close()

    def _build_day_list(
        self, start_date, end_date, data: dict
    ) -> list[TrendDay]:
        """Build a contiguous list of TrendDay objects, filling gaps with zeros."""
        result = []
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            day_data = data.get(date_str, {})
            result.append(TrendDay(
                date=date_str,
                total_files=day_data.get("total_files", 0),
                total_errors=day_data.get("total_errors", 0),
                did_failures=day_data.get("did_failures", 0),
                job_runs=day_data.get("job_runs", 0),
            ))
            current += timedelta(days=1)
        return result

    @staticmethod
    def _add_trend_indicators(days: list[TrendDay]) -> None:
        """Add ↑/↓/→ trend indicators by comparing with previous day."""
        for i, day in enumerate(days):
            if i == 0:
                day.trend_files = "→"
                day.trend_errors = "→"
                continue
            prev = days[i - 1]
            day.trend_files = (
                "↑" if day.total_files > prev.total_files
                else "↓" if day.total_files < prev.total_files
                else "→"
            )
            day.trend_errors = (
                "↑" if day.total_errors > prev.total_errors
                else "↓" if day.total_errors < prev.total_errors
                else "→"
            )
```

---

## 3. Performance Benchmarker

### backend/analysis/performance.py (new file)

```python
"""
L-07: Job performance benchmarking across all monitoring jobs.

Ranks jobs by operational metrics (success rate, volume, errors)
using SQLite log index data and Settings.xml job list.
"""

import logging
from datetime import datetime, timedelta

from backend.analysis.models import PerformanceEntry, PerformanceSummary

logger = logging.getLogger(__name__)

# Status thresholds
HEALTHY_THRESHOLD = 95.0
WARNING_THRESHOLD = 80.0


class PerformanceBenchmarker:
    """Rank all monitoring jobs by operational performance metrics."""

    def __init__(self, analytics, parser=None):
        """
        Args:
            analytics: LogAnalytics instance (Phase 3) for SQLite queries
            parser: SettingsXmlParser instance (Phase 1) for job name list.
                    If None, derives job names from SQLite log data only.
        """
        self._analytics = analytics
        self._parser = parser

    def benchmark(
        self,
        sort_by: str = "success_rate",
        ascending: bool = True,
        top_n: int | None = None,
        days: int = 30,
    ) -> PerformanceSummary:
        """
        Generate a ranked performance report for all jobs.

        Args:
            sort_by: Metric to sort by — "success_rate", "total_files",
                     "total_errors", "avg_files_per_run", "last_run"
            ascending: Sort direction (True = worst first for success_rate)
            top_n: Limit results to top N entries (None = all)
            days: Look-back window in days

        Returns:
            PerformanceSummary with ranked entries
        """
        staleness = self._analytics.check_staleness()
        staleness_warning = staleness.get("warning") if staleness else None

        # Get all job names
        all_job_names = self._get_all_job_names()

        # Batch query: aggregate all metrics in one SQL
        metrics = self._batch_query_metrics(days)

        # Build entries
        entries: list[PerformanceEntry] = []
        for job_name in all_job_names:
            m = metrics.get(job_name, {})
            runs = m.get("runs", 0)
            files = m.get("files", 0)
            errors = m.get("errors", 0)
            error_runs = m.get("error_runs", 0)
            last_run = m.get("last_run")

            if runs > 0:
                successful = runs - error_runs
                rate = (successful / runs) * 100
                avg = files / runs
            else:
                rate = 0.0
                avg = 0.0

            # Determine status
            if runs == 0:
                status = "unknown"
            elif rate >= HEALTHY_THRESHOLD:
                status = "healthy"
            elif rate >= WARNING_THRESHOLD:
                status = "warning"
            else:
                status = "critical"

            # Get common errors for this job
            common_errors = m.get("common_errors", [])

            # Determine job_type from parser if available
            job_type = self._get_job_type(job_name)

            entries.append(PerformanceEntry(
                job_name=job_name,
                job_type=job_type,
                total_runs=runs,
                total_files=files,
                total_errors=errors,
                success_rate=round(rate, 1),
                avg_files_per_run=round(avg, 1),
                last_run=last_run,
                status=status,
                common_errors=common_errors,
            ))

        # Sort
        sort_keys = {
            "success_rate": lambda e: e.success_rate,
            "total_files": lambda e: e.total_files,
            "total_errors": lambda e: e.total_errors,
            "avg_files_per_run": lambda e: e.avg_files_per_run,
            "last_run": lambda e: e.last_run or "",
        }
        sort_fn = sort_keys.get(sort_by, sort_keys["success_rate"])
        entries.sort(key=sort_fn, reverse=not ascending)

        # Apply top_n
        if top_n and top_n > 0:
            entries = entries[:top_n]

        # Add ranks
        for i, e in enumerate(entries, 1):
            e.rank = i

        # Aggregate counts
        h = sum(1 for e in entries if e.status == "healthy")
        w = sum(1 for e in entries if e.status == "warning")
        c = sum(1 for e in entries if e.status == "critical")
        u = sum(1 for e in entries if e.status == "unknown")
        all_rates = [e.success_rate for e in entries if e.status != "unknown"]
        avg_rate = sum(all_rates) / len(all_rates) if all_rates else 0.0

        return PerformanceSummary(
            entries=entries,
            total_jobs=len(entries),
            healthy_count=h,
            warning_count=w,
            critical_count=c,
            unknown_count=u,
            avg_success_rate=round(avg_rate, 1),
            sort_key=sort_by,
            period_days=days,
            staleness_warning=staleness_warning,
        )

    def _get_all_job_names(self) -> list[str]:
        """
        Get union of job names from Settings.xml (if parser available)
        and from SQLite log data.
        """
        names = set()

        # From parser
        if self._parser:
            try:
                for job in self._parser.get_all_jobs():
                    name = getattr(job, "name", None) or getattr(job, "job_name", None)
                    if name:
                        names.add(str(name))
            except Exception as e:
                logger.warning(f"Failed to get jobs from parser: {e}")

        # From SQLite (catches jobs that exist in logs but not current XML)
        conn = self._analytics._get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT job_name FROM log_events WHERE job_name IS NOT NULL"
            ).fetchall()
            for r in rows:
                names.add(r["job_name"])
        finally:
            conn.close()

        return sorted(names)

    def _batch_query_metrics(self, days: int) -> dict:
        """
        Single batch query to get all per-job metrics.

        Returns:
            dict: {
                "job_name": {
                    "runs": int,
                    "files": int,
                    "errors": int,
                    "error_runs": int,
                    "last_run": str | None,
                    "common_errors": [{"error": str, "count": int}]
                }
            }
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self._analytics._get_conn()
        try:
            # Main aggregation
            rows = conn.execute(
                """
                SELECT
                    job_name,
                    COUNT(DISTINCT CASE WHEN event_type = 'job_start' THEN log_file END) AS runs,
                    SUM(CASE WHEN event_type = 'email_processed' THEN 1 ELSE 0 END) AS files,
                    SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) AS errors,
                    COUNT(DISTINCT CASE WHEN event_type = 'error' THEN log_file END) AS error_runs,
                    MAX(CASE WHEN event_type = 'job_start' THEN timestamp END) AS last_run
                FROM log_events
                WHERE timestamp >= ? AND job_name IS NOT NULL
                GROUP BY job_name
                """,
                (cutoff,)
            ).fetchall()

            result = {}
            for r in rows:
                result[r["job_name"]] = {
                    "runs": r["runs"] or 0,
                    "files": r["files"] or 0,
                    "errors": r["errors"] or 0,
                    "error_runs": r["error_runs"] or 0,
                    "last_run": r["last_run"],
                    "common_errors": [],
                }

            # Common errors per job (top 3)
            error_rows = conn.execute(
                """
                SELECT job_name, detail, COUNT(*) AS cnt
                FROM log_events
                WHERE event_type = 'error' AND timestamp >= ? AND job_name IS NOT NULL
                GROUP BY job_name, detail
                ORDER BY job_name, cnt DESC
                """,
                (cutoff,)
            ).fetchall()

            # Group and limit to top 3 per job
            from collections import defaultdict
            error_by_job = defaultdict(list)
            for r in error_rows:
                error_by_job[r["job_name"]].append({
                    "error": r["detail"],
                    "count": r["cnt"],
                })

            for job_name, errors in error_by_job.items():
                if job_name in result:
                    result[job_name]["common_errors"] = errors[:3]

            return result
        finally:
            conn.close()

    def _get_job_type(self, job_name: str) -> str:
        """Determine if a job is email or sftp type from the parser."""
        if not self._parser:
            return "unknown"
        try:
            # Check email jobs
            email_jobs = getattr(self._parser, "email_jobs", None)
            if email_jobs:
                for j in email_jobs:
                    name = getattr(j, "name", None) or getattr(j, "job_name", None)
                    if str(name) == job_name:
                        return "email"
            # Check sftp jobs
            sftp_jobs = getattr(self._parser, "sftp_jobs", None)
            if sftp_jobs:
                for j in sftp_jobs:
                    name = getattr(j, "name", None) or getattr(j, "job_name", None)
                    if str(name) == job_name:
                        return "sftp"
        except Exception:
            pass
        return "unknown"
```

---

## 4. Consolidation Analyzer

### backend/analysis/consolidation.py (new file)

```python
"""
A-01: Job consolidation analysis.

Identifies groups of jobs that share identical core configuration
(mailbox, parser type, template) and evaluates merge potential.
"""

import logging
from collections import defaultdict

from backend.analysis.models import (
    ConsolidationCandidate,
    ConsolidationGroup,
    ConsolidationReport,
)

logger = logging.getLogger(__name__)


class ConsolidationAnalyzer:
    """Detect groups of jobs that could potentially be merged."""

    def __init__(self, parser, deal_repo=None):
        """
        Args:
            parser: SettingsXmlParser instance (Phase 1)
            deal_repo: DealRepository instance (Phase 1) — optional,
                       used to count DIDs per ServicerID
        """
        self._parser = parser
        self._deal_repo = deal_repo

    def analyze(self, xml_type: str = "all") -> ConsolidationReport:
        """
        Find consolidation opportunities across all jobs.

        Args:
            xml_type: "email", "sftp", or "all"

        Returns:
            ConsolidationReport with groups of merge candidates
        """
        jobs = self._get_jobs(xml_type)
        if not jobs:
            return ConsolidationReport(
                groups=[], total_groups=0,
                total_jobs_affected=0, total_dids_affected=0,
                xml_type_analyzed=xml_type,
            )

        # Extract signature tuples and group
        groups_by_sig = defaultdict(list)
        for job in jobs:
            sig = self._extract_signature(job)
            groups_by_sig[sig].append(job)

        # Filter to groups with 2+ jobs
        candidate_groups = {
            sig: group for sig, group in groups_by_sig.items()
            if len(group) >= 2
        }

        # Build ConsolidationGroup objects
        result_groups: list[ConsolidationGroup] = []
        for idx, (sig, group_jobs) in enumerate(candidate_groups.items(), 1):
            mailbox, parser_type, template = sig

            # Build candidate list with DID counts
            candidates = []
            total_dids = 0
            for job in group_jobs:
                sid = self._get_servicer_id(job)
                did_count = 0
                if sid and self._deal_repo:
                    try:
                        dids = self._deal_repo.get_deals_by_company(int(sid))
                        did_count = len(dids)
                    except (ValueError, Exception) as e:
                        logger.warning(f"DID lookup failed for ServicerID {sid}: {e}")

                total_dids += did_count
                unique_attrs = self._extract_unique_attributes(job, sig)

                candidates.append(ConsolidationCandidate(
                    name=self._get_job_name(job),
                    servicer_id=sid,
                    did_count=did_count,
                    unique_attributes=unique_attrs,
                ))

            # Determine merge recommendation
            recommendation, rationale = self._assess_merge_safety(
                candidates, sig
            )

            result_groups.append(ConsolidationGroup(
                group_id=idx,
                shared_mailbox=mailbox,
                shared_parser=parser_type,
                shared_template=template,
                jobs=candidates,
                total_dids_affected=total_dids,
                merge_recommendation=recommendation,
                rationale=rationale,
            ))

        # Sort by total_dids_affected descending (largest impact first)
        result_groups.sort(key=lambda g: g.total_dids_affected, reverse=True)

        total_jobs = sum(len(g.jobs) for g in result_groups)
        total_dids = sum(g.total_dids_affected for g in result_groups)

        return ConsolidationReport(
            groups=result_groups,
            total_groups=len(result_groups),
            total_jobs_affected=total_jobs,
            total_dids_affected=total_dids,
            xml_type_analyzed=xml_type,
        )

    def _get_jobs(self, xml_type: str) -> list:
        """Get all jobs from parser, filtered by type."""
        jobs = []
        if xml_type in ("email", "all"):
            email = getattr(self._parser, "email_jobs", None)
            if email:
                jobs.extend(email)
            elif xml_type == "email":
                jobs.extend(self._parser.get_all_jobs())
        if xml_type in ("sftp", "all"):
            sftp = getattr(self._parser, "sftp_jobs", None)
            if sftp:
                jobs.extend(sftp)
        if not jobs and xml_type == "all":
            jobs = self._parser.get_all_jobs()
        return jobs

    def _extract_signature(self, job) -> tuple:
        """
        Extract the grouping signature: (mailbox, parser_class, template_name).

        Jobs with identical signatures are consolidation candidates.
        """
        # Mailbox: could be <Mailbox>, <Folder>, <Path> depending on XML type
        mailbox = (
            getattr(job, "mailbox", None)
            or getattr(job, "folder", None)
            or getattr(job, "path", None)
            or "unknown"
        )

        # Parser class: the top-level parser type (e.g., "DetachFile", "MoveFile2")
        parsers = getattr(job, "parsers", None) or []
        parser_class = "unknown"
        if parsers:
            if isinstance(parsers, list) and len(parsers) > 0:
                first = parsers[0]
                if isinstance(first, dict):
                    parser_class = first.get("type", "unknown")
                else:
                    parser_class = getattr(first, "type", None) or type(first).__name__
            elif isinstance(parsers, dict):
                parser_class = next(iter(parsers.keys()), "unknown")

        # Template name
        templates = getattr(job, "templates", None) or {}
        if isinstance(templates, dict):
            template_name = next(iter(templates.values()), "none") if templates else "none"
        elif isinstance(templates, list) and templates:
            template_name = str(templates[0])
        else:
            template_name = "none"

        return (str(mailbox).lower(), str(parser_class).lower(), str(template_name).lower())

    def _extract_unique_attributes(self, job, sig: tuple) -> dict:
        """Extract attributes that differ from the group's shared signature."""
        attrs = {}

        # Sender filter
        sf = getattr(job, "sender_filter", None) or getattr(job, "SenderFilter", None)
        if sf:
            attrs["SenderFilter"] = sf

        # Subject filter
        subf = getattr(job, "subject_filter", None) or getattr(job, "SubjectFilter", None)
        if subf:
            attrs["SubjectFilter"] = subf

        # Attachment filter
        att = getattr(job, "attachment_filter", None) or getattr(job, "AttachmentFilter", None)
        if att:
            attrs["AttachmentFilter"] = att

        # QueueOneFile
        q = getattr(job, "queue_one_file", None) or getattr(job, "QueueOneFile", None)
        if q:
            attrs["QueueOneFile"] = str(q)

        # DayAdjust
        da = getattr(job, "day_adjust", None) or getattr(job, "DayAdjust", None)
        if da:
            attrs["DayAdjust"] = str(da)

        return attrs

    def _get_job_name(self, job) -> str:
        return str(getattr(job, "name", None) or getattr(job, "job_name", "unknown"))

    def _get_servicer_id(self, job) -> str | None:
        sid = getattr(job, "servicer_id", None) or getattr(job, "ServicerID", None)
        return str(sid) if sid else None

    def _assess_merge_safety(
        self,
        candidates: list[ConsolidationCandidate],
        sig: tuple,
    ) -> tuple[str, str]:
        """
        Evaluate how safe it would be to merge this group.

        Returns:
            (recommendation, rationale) tuple
        """
        unique_attr_sets = [
            frozenset(c.unique_attributes.items()) for c in candidates
        ]

        # Check if all unique attributes are identical
        all_same_attrs = len(set(unique_attr_sets)) <= 1

        # Check for overlapping ServicerIDs
        sids = [c.servicer_id for c in candidates if c.servicer_id]
        unique_sids = set(sids)
        has_sid_overlap = len(sids) != len(unique_sids)

        # Check if any jobs have no ServicerID (process-level)
        has_process_level = any(c.servicer_id is None for c in candidates)

        if has_process_level:
            return (
                "risky",
                f"Group contains process/shelf-level jobs (no ServicerID). "
                f"These serve a different purpose and should not be merged."
            )

        if has_sid_overlap:
            return (
                "risky",
                f"Group has overlapping ServicerIDs — same servicer mapped to "
                f"multiple jobs with identical config. Investigate for duplicates."
            )

        if all_same_attrs:
            return (
                "safe",
                f"All {len(candidates)} jobs share identical parser config. "
                f"Only ServicerID differs. Could be consolidated into a single "
                f"multi-deal job if DID mappings are updated."
            )

        # Attributes differ
        differing = set()
        for c in candidates:
            differing.update(c.unique_attributes.keys())
        return (
            "review",
            f"Jobs share core config but differ in: {', '.join(sorted(differing))}. "
            f"Manual review required to determine if differences are significant."
        )
```

---

## 5. Impact Simulator

### backend/analysis/impact.py (new file)

```python
"""
A-02: Change impact simulation.

Simulates the effect of a proposed configuration change without
modifying any files. Analyzes coverage impact, affected entities,
and recent activity to produce a risk assessment.
"""

import logging
from datetime import datetime, timedelta

from backend.analysis.models import (
    ChangeSpec,
    AffectedEntity,
    ImpactReport,
)

logger = logging.getLogger(__name__)


class ImpactSimulator:
    """Simulate impact of proposed configuration changes."""

    RECENT_ACTIVITY_DAYS = 7

    def __init__(self, parser, deal_repo=None, analytics=None):
        """
        Args:
            parser: SettingsXmlParser instance (Phase 1)
            deal_repo: DealRepository instance (Phase 1) — optional
            analytics: LogAnalytics instance (Phase 3) — optional
        """
        self._parser = parser
        self._deal_repo = deal_repo
        self._analytics = analytics

    def simulate(self, change: ChangeSpec) -> ImpactReport:
        """
        Execute the impact simulation for a given change specification.

        Args:
            change: ChangeSpec describing the proposed change

        Returns:
            ImpactReport with affected entities and risk assessment

        Raises:
            ValueError: If change_type is unknown or target not found
        """
        handler = {
            "delete_job": self._sim_delete_job,
            "rename_did": self._sim_rename_did,
            "change_filter": self._sim_change_filter,
            "move_servicer": self._sim_move_servicer,
        }.get(change.change_type)

        if not handler:
            raise ValueError(
                f"Unknown change_type '{change.change_type}'. "
                f"Supported: delete_job, rename_did, change_filter, move_servicer"
            )

        return handler(change)

    # ─── Delete Job Simulation ────────────────────────────────────

    def _sim_delete_job(self, change: ChangeSpec) -> ImpactReport:
        """
        Simulate deleting a job from Settings.xml.

        Checks:
        1. What ServicerID does this job have?
        2. What DIDs are mapped to that ServicerID?
        3. Are those DIDs covered by any other job?
        4. Was this job recently active?
        """
        if not change.target_job:
            raise ValueError("target_job is required for delete_job")

        # Find the job
        job = self._find_job(change.target_job)
        if not job:
            raise ValueError(f"Job '{change.target_job}' not found in Settings.xml")

        sid = self._get_servicer_id(job)
        affected: list[AffectedEntity] = []
        coverage_before = 0
        coverage_after = 0

        if sid and self._deal_repo:
            # Get all DIDs for this ServicerID
            try:
                dids = self._deal_repo.get_deals_by_company(int(sid))
                coverage_before = len(dids)

                # Check coverage for each DID from other jobs
                all_jobs = self._parser.get_all_jobs()
                other_sids = set()
                for j in all_jobs:
                    j_name = self._get_job_name(j)
                    j_sid = self._get_servicer_id(j)
                    if j_name != change.target_job and j_sid:
                        other_sids.add(j_sid)

                covered_elsewhere = 0
                for did_row in dids:
                    did_name = did_row.get("DID", did_row.get("did", "unknown"))
                    import_did = did_row.get("ImportDID", did_row.get("import_did", ""))

                    # Check if this DID's CompanyID appears in any other job
                    other_coverage = self._check_did_other_coverage(
                        did_row, other_sids
                    )

                    if other_coverage:
                        affected.append(AffectedEntity(
                            entity_type="deal",
                            identifier=str(did_name),
                            detail=f"Also covered by job '{other_coverage}' via another ServicerID",
                            severity="low",
                        ))
                        covered_elsewhere += 1
                    else:
                        affected.append(AffectedEntity(
                            entity_type="deal",
                            identifier=str(did_name),
                            detail=f"Would lose coverage — no other job handles ImportDID '{import_did}'",
                            severity="high",
                        ))

                coverage_after = covered_elsewhere

            except (ValueError, Exception) as e:
                logger.warning(f"DID lookup failed for ServicerID {sid}: {e}")
                affected.append(AffectedEntity(
                    entity_type="job",
                    identifier=change.target_job,
                    detail=f"Could not verify DID coverage: {e}",
                    severity="medium",
                ))
        elif not sid:
            # Process-level job — no ServicerID
            affected.append(AffectedEntity(
                entity_type="job",
                identifier=change.target_job,
                detail="Process/shelf-level job (no ServicerID). "
                       "Deleting affects all emails matched by this job's filters.",
                severity="medium",
            ))

        # Check recent activity
        recent_activity = self._check_recent_activity(change.target_job)

        # Calculate risk
        high_count = sum(1 for a in affected if a.severity == "high")
        risk_level = self._calculate_risk(high_count, recent_activity, coverage_before)

        # Generate recommendation
        recommendation = self._generate_delete_recommendation(
            change.target_job, high_count, coverage_before,
            coverage_after, recent_activity
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            coverage_delta=coverage_after - coverage_before,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Rename DID Simulation ────────────────────────────────────

    def _sim_rename_did(self, change: ChangeSpec) -> ImpactReport:
        """Simulate renaming an ImportDID keyword."""
        if not change.target_did or not change.new_value:
            raise ValueError("target_did and new_value are required for rename_did")

        affected: list[AffectedEntity] = []
        coverage_before = 0
        coverage_after = 0

        if self._deal_repo:
            # Find all rows with the old ImportDID
            try:
                old_rows = self._deal_repo.get_by_import_did(change.target_did)
                coverage_before = len(old_rows)

                for row in old_rows:
                    did = row.get("DID", "unknown")
                    affected.append(AffectedEntity(
                        entity_type="did_mapping",
                        identifier=f"{did} → {change.target_did}",
                        detail=f"ImportDID would change from '{change.target_did}' to '{change.new_value}'",
                        severity="medium",
                    ))

                # Check if new_value collides with existing ImportDIDs
                new_rows = self._deal_repo.get_by_import_did(change.new_value)
                if new_rows:
                    existing_sids = set(
                        str(r.get("CompanyID", "")) for r in new_rows
                    )
                    old_sids = set(
                        str(r.get("CompanyID", "")) for r in old_rows
                    )
                    if existing_sids != old_sids:
                        affected.append(AffectedEntity(
                            entity_type="did_mapping",
                            identifier=change.new_value,
                            detail=f"COLLISION: ImportDID '{change.new_value}' already exists "
                                   f"for CompanyIDs {existing_sids}. Renaming would create ambiguity.",
                            severity="high",
                        ))

                coverage_after = coverage_before  # Rename doesn't remove coverage

            except Exception as e:
                logger.warning(f"DID lookup failed: {e}")

        recent_activity = False
        high_count = sum(1 for a in affected if a.severity == "high")
        risk_level = "high" if high_count > 0 else "low"

        recommendation = (
            f"Renaming ImportDID '{change.target_did}' to '{change.new_value}' "
            f"affects {coverage_before} DID mapping(s). "
            + ("WARNING: Collision detected with existing ImportDID." if high_count > 0 else "No collisions detected.")
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            coverage_delta=0,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Change Filter Simulation ─────────────────────────────────

    def _sim_change_filter(self, change: ChangeSpec) -> ImpactReport:
        """Simulate changing a job's filter configuration."""
        if not change.target_job:
            raise ValueError("target_job is required for change_filter")

        job = self._find_job(change.target_job)
        if not job:
            raise ValueError(f"Job '{change.target_job}' not found")

        affected: list[AffectedEntity] = []
        sid = self._get_servicer_id(job)
        coverage_before = 0

        if sid and self._deal_repo:
            try:
                dids = self._deal_repo.get_deals_by_company(int(sid))
                coverage_before = len(dids)
            except Exception:
                pass

        affected.append(AffectedEntity(
            entity_type="job",
            identifier=change.target_job,
            detail=f"Filter change: '{change.new_value or 'unspecified'}'. "
                   f"This may affect which emails are matched by this job.",
            severity="medium",
        ))

        recent_activity = self._check_recent_activity(change.target_job)
        risk_level = "medium" if recent_activity else "low"

        recommendation = (
            f"Changing filter on '{change.target_job}' "
            + (f"(ServicerID={sid}, {coverage_before} DIDs). " if sid else ". ")
            + ("Job was active recently — test filter change carefully." if recent_activity
               else "No recent activity — lower risk.")
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_before,  # Filter change doesn't remove DID coverage
            coverage_delta=0,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Move Servicer Simulation ─────────────────────────────────

    def _sim_move_servicer(self, change: ChangeSpec) -> ImpactReport:
        """Simulate moving a ServicerID from one job to another."""
        if not change.target_job or not change.target_company_id:
            raise ValueError("target_job and target_company_id required for move_servicer")

        affected: list[AffectedEntity] = []
        coverage_before = 0

        if self._deal_repo:
            try:
                dids = self._deal_repo.get_deals_by_company(change.target_company_id)
                coverage_before = len(dids)
                for d in dids:
                    affected.append(AffectedEntity(
                        entity_type="deal",
                        identifier=str(d.get("DID", "unknown")),
                        detail=f"DID mapping would move from job '{change.target_job}' "
                               f"to '{change.new_value or 'unspecified'}'",
                        severity="medium",
                    ))
            except Exception as e:
                logger.warning(f"DID lookup failed: {e}")

        recent_activity = self._check_recent_activity(change.target_job)

        # Check if destination job exists
        dest_job = None
        if change.new_value:
            dest_job = self._find_job(change.new_value)
            if not dest_job:
                affected.append(AffectedEntity(
                    entity_type="job",
                    identifier=change.new_value,
                    detail="Destination job does not exist — would need to be created first.",
                    severity="high",
                ))

        high_count = sum(1 for a in affected if a.severity == "high")
        risk_level = self._calculate_risk(high_count, recent_activity, coverage_before)

        recommendation = (
            f"Moving ServicerID {change.target_company_id} ({coverage_before} DIDs) "
            f"from '{change.target_job}' to '{change.new_value or 'unspecified'}'. "
            + ("Destination job exists." if dest_job else "Destination job NOT found — create it first.")
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_before,
            coverage_delta=0,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Helper Methods ───────────────────────────────────────────

    def _find_job(self, job_name: str):
        """Find a job by name in the parser's job list."""
        for job in self._parser.get_all_jobs():
            name = self._get_job_name(job)
            if name.lower() == job_name.lower():
                return job
        return None

    def _get_job_name(self, job) -> str:
        return str(getattr(job, "name", None) or getattr(job, "job_name", "unknown"))

    def _get_servicer_id(self, job) -> str | None:
        sid = getattr(job, "servicer_id", None) or getattr(job, "ServicerID", None)
        return str(sid) if sid else None

    def _check_recent_activity(self, job_name: str) -> bool:
        """Check if a job had any log activity in the last 7 days."""
        if not self._analytics:
            return False
        try:
            cutoff = (datetime.now() - timedelta(days=self.RECENT_ACTIVITY_DAYS)).isoformat()
            conn = self._analytics._get_conn()
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM log_events
                    WHERE job_name = ? AND timestamp >= ?
                    """,
                    (job_name, cutoff)
                ).fetchone()
                return (row["cnt"] or 0) > 0
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Recent activity check failed: {e}")
            return False

    def _check_did_other_coverage(self, did_row: dict, other_sids: set) -> str | None:
        """
        Check if a DID is covered by any job other than the one being deleted.

        Returns the covering job's ServicerID if found, None otherwise.
        """
        # A DID is covered by another job if any other job's ServicerID
        # appears in tblExternalDIDRef for the same DID
        if not self._deal_repo:
            return None

        did_name = did_row.get("DID", did_row.get("did"))
        if not did_name:
            return None

        try:
            all_mappings = self._deal_repo.get_by_did(str(did_name))
            for m in all_mappings:
                cid = str(m.get("CompanyID", m.get("company_id", "")))
                if cid in other_sids:
                    return cid
        except Exception:
            pass
        return None

    def _calculate_risk(
        self, high_severity_count: int,
        recent_activity: bool,
        coverage_before: int,
    ) -> str:
        """Calculate overall risk level."""
        if high_severity_count > 0 and recent_activity:
            return "high"
        if high_severity_count > 0 or (recent_activity and coverage_before > 10):
            return "medium"
        return "low"

    def _generate_delete_recommendation(
        self, job_name: str, orphaned_count: int,
        coverage_before: int, coverage_after: int,
        recent_activity: bool,
    ) -> str:
        """Generate human-readable recommendation for job deletion."""
        parts = [f"Deleting job '{job_name}'"]

        if coverage_before > 0:
            parts.append(f"would affect {coverage_before} DID mapping(s)")
            if orphaned_count > 0:
                parts.append(
                    f"— {orphaned_count} DID(s) would lose ALL coverage"
                )
            else:
                parts.append("— all DIDs are covered by other jobs")

        if recent_activity:
            parts.append(
                ". This job processed files in the last 7 days"
            )
        else:
            parts.append(". No recent activity detected")

        if orphaned_count > 0:
            parts.append(
                ". RECOMMENDATION: Migrate affected DIDs before deleting"
            )
        elif not recent_activity and coverage_before == 0:
            parts.append(". Safe to delete — no DIDs and no recent activity")

        return "".join(parts) + "."
```

---

## 6. Health Checker Orchestrator

### backend/analysis/health.py (new file)

```python
"""
A-03: Full system health check.

Orchestrates all diagnostic checks from Phases 1–4 into a single
weighted health report with per-section scores and action items.
"""

import logging
from datetime import datetime

from backend.analysis.models import HealthSection, HealthReport

logger = logging.getLogger(__name__)

# Section weights (must sum to 1.0)
SECTION_WEIGHTS = {
    "xml_validation": 0.15,
    "coverage_rate": 0.20,
    "orphan_dids": 0.10,
    "importdid_collisions": 0.10,
    "template_distribution": 0.05,
    "log_freshness": 0.10,
    "did_failure_rate": 0.10,
    "job_performance": 0.15,
    "recent_errors": 0.05,
}

# Overall status thresholds
HEALTHY_THRESHOLD = 90.0
ATTENTION_THRESHOLD = 70.0


class HealthChecker:
    """Orchestrate all diagnostic checks into a unified health report."""

    def __init__(
        self,
        parser=None,
        deal_repo=None,
        analytics=None,
        coverage_analyzer=None,
        orphan_detector=None,
        collision_detector=None,
        benchmarker=None,
    ):
        """
        All dependencies are injected. Any may be None — the checker
        degrades gracefully by marking unavailable sections as "warning".

        Args:
            parser: SettingsXmlParser (Phase 1) — for J-05 validation
            deal_repo: DealRepository (Phase 1) — for D-01/D-02/D-03
            analytics: LogAnalytics (Phase 3) — for L-03, L-05, staleness
            coverage_analyzer: CoverageAnalyzer (Phase 2) — for D-01
            orphan_detector: OrphanDetector (Phase 2) — for D-02
            collision_detector: CollisionDetector (Phase 2) — for D-03
            benchmarker: PerformanceBenchmarker (Phase 4) — for L-07
        """
        self._parser = parser
        self._deal_repo = deal_repo
        self._analytics = analytics
        self._coverage = coverage_analyzer
        self._orphans = orphan_detector
        self._collisions = collision_detector
        self._benchmarker = benchmarker

    def check(self, xml_type: str = "all") -> HealthReport:
        """
        Run all health checks and produce a unified report.

        Args:
            xml_type: "email", "sftp", or "all"

        Returns:
            HealthReport with per-section scores and overall grade
        """
        sections: list[HealthSection] = []

        # Section 1: XML Validation
        sections.append(self._check_xml_validation(xml_type))

        # Section 2: Coverage Rate
        sections.append(self._check_coverage_rate())

        # Section 3: Orphan DIDs
        sections.append(self._check_orphan_dids())

        # Section 4: ImportDID Collisions
        sections.append(self._check_collisions())

        # Section 5: Template Distribution
        sections.append(self._check_template_distribution())

        # Section 6: Log Freshness
        sections.append(self._check_log_freshness())

        # Section 7: DID Failure Rate
        sections.append(self._check_did_failures())

        # Section 8: Job Performance
        sections.append(self._check_job_performance())

        # Section 9: Recent Errors
        sections.append(self._check_recent_errors())

        # Calculate overall score
        overall_score = sum(s.score * s.weight for s in sections)

        if overall_score >= HEALTHY_THRESHOLD:
            overall_status = "Healthy"
        elif overall_score >= ATTENTION_THRESHOLD:
            overall_status = "Attention Needed"
        else:
            overall_status = "Action Required"

        return HealthReport(
            sections=sections,
            overall_score=round(overall_score, 1),
            overall_status=overall_status,
            generated_at=datetime.now().isoformat(),
            xml_type=xml_type,
        )

    # ─── Section Checkers ─────────────────────────────────────────

    def _check_xml_validation(self, xml_type: str) -> HealthSection:
        """Section 1: XML structural validation (J-05)."""
        weight = SECTION_WEIGHTS["xml_validation"]
        try:
            if not self._parser:
                return self._unavailable_section("XML Validation", weight, "Parser not configured")

            result = self._parser.validate()
            errors = getattr(result, "errors", []) if result else []
            warnings = getattr(result, "warnings", []) if result else []
            error_count = len(errors) if isinstance(errors, list) else 0
            warning_count = len(warnings) if isinstance(warnings, list) else 0

            score = max(0.0, 100.0 - (error_count * 20) - (warning_count * 5))
            actions = []
            if error_count > 0:
                actions.append(f"Fix {error_count} XML validation error(s): @frp /jobs validate")

            return HealthSection(
                name="XML Validation",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{error_count} error(s), {warning_count} warning(s)",
                details={"errors": error_count, "warnings": warning_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("XML Validation", weight, str(e))

    def _check_coverage_rate(self) -> HealthSection:
        """Section 2: Deal coverage analysis (D-01)."""
        weight = SECTION_WEIGHTS["coverage_rate"]
        try:
            if not self._coverage:
                return self._unavailable_section("Coverage Rate", weight, "CoverageAnalyzer not configured")

            result = self._coverage.analyze()
            total = getattr(result, "total_dids", 0)
            covered = getattr(result, "covered_dids", 0)
            rate = (covered / total * 100) if total > 0 else 100.0
            gaps = total - covered

            actions = []
            if gaps > 0:
                actions.append(f"Review {gaps} coverage gap(s): @frp /deals gaps")

            return HealthSection(
                name="Coverage Rate",
                status=self._score_to_status(rate),
                score=round(rate, 1),
                weight=weight,
                summary=f"{covered} of {total} DIDs covered ({rate:.1f}%)",
                details={"covered": covered, "total": total, "gaps": gaps},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Coverage Rate", weight, str(e))

    def _check_orphan_dids(self) -> HealthSection:
        """Section 3: Orphan job detection (D-02)."""
        weight = SECTION_WEIGHTS["orphan_dids"]
        try:
            if not self._orphans:
                return self._unavailable_section("Orphan DIDs", weight, "OrphanDetector not configured")

            result = self._orphans.detect()
            orphan_count = getattr(result, "orphan_count", 0) if result else 0
            score = max(0.0, 100.0 - (orphan_count * 5))

            actions = []
            if orphan_count > 0:
                actions.append(f"Resolve {orphan_count} orphan(s): @frp /deals orphans")

            return HealthSection(
                name="Orphan DIDs",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{orphan_count} orphan DID(s) found",
                details={"orphan_count": orphan_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Orphan DIDs", weight, str(e))

    def _check_collisions(self) -> HealthSection:
        """Section 4: ImportDID collision detection (D-03)."""
        weight = SECTION_WEIGHTS["importdid_collisions"]
        try:
            if not self._collisions:
                return self._unavailable_section("ImportDID Collisions", weight, "CollisionDetector not configured")

            result = self._collisions.detect()
            collision_count = getattr(result, "collision_count", 0) if result else 0
            score = max(0.0, 100.0 - (collision_count * 10))

            actions = []
            if collision_count > 0:
                actions.append(f"Review {collision_count} collision(s): @frp /deals collisions")

            return HealthSection(
                name="ImportDID Collisions",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{collision_count} ImportDID collision(s) detected",
                details={"collision_count": collision_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("ImportDID Collisions", weight, str(e))

    def _check_template_distribution(self) -> HealthSection:
        """Section 5: Template inventory (informational — always passes)."""
        weight = SECTION_WEIGHTS["template_distribution"]
        try:
            if not self._parser:
                return self._unavailable_section("Template Distribution", weight, "Parser not configured")

            # This section is informational — always scores 100
            jobs = self._parser.get_all_jobs()
            template_names = set()
            for job in jobs:
                templates = getattr(job, "templates", None) or {}
                if isinstance(templates, dict):
                    template_names.update(templates.values())
                elif isinstance(templates, list):
                    template_names.update(str(t) for t in templates)

            return HealthSection(
                name="Template Distribution",
                status="pass",
                score=100.0,
                weight=weight,
                summary=f"{len(template_names)} unique template(s) across {len(jobs)} jobs",
                details={
                    "template_count": len(template_names),
                    "job_count": len(jobs),
                },
                action_items=[],
            )
        except Exception as e:
            return self._error_section("Template Distribution", weight, str(e))

    def _check_log_freshness(self) -> HealthSection:
        """Section 6: Log index staleness check."""
        weight = SECTION_WEIGHTS["log_freshness"]
        try:
            if not self._analytics:
                return self._unavailable_section("Log Freshness", weight, "LogAnalytics not configured — run @frp /logs sync")

            staleness = self._analytics.check_staleness()
            if staleness is None:
                return HealthSection(
                    name="Log Freshness",
                    status="pass",
                    score=100.0,
                    weight=weight,
                    summary="Log index is up to date",
                    details={"stale": False},
                    action_items=[],
                )

            # Extract hours from warning message
            warning_msg = staleness.get("warning", "")
            if "never been synced" in warning_msg:
                score = 0.0
            else:
                # Try to extract hours
                import re
                m = re.search(r"(\d+)\s*hours", warning_msg)
                hours = int(m.group(1)) if m else 48
                if hours <= 24:
                    score = 100.0
                elif hours <= 48:
                    score = 50.0
                else:
                    score = 0.0

            return HealthSection(
                name="Log Freshness",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=warning_msg or "Log index stale",
                details={"stale": True, "warning": warning_msg},
                action_items=["Sync logs: @frp /logs sync"],
            )
        except Exception as e:
            return self._error_section("Log Freshness", weight, str(e))

    def _check_did_failures(self) -> HealthSection:
        """Section 7: DID mapping failure rate (L-03)."""
        weight = SECTION_WEIGHTS["did_failure_rate"]
        try:
            if not self._analytics:
                return self._unavailable_section("DID Failure Rate", weight, "LogAnalytics not configured")

            failures = self._analytics.did_failures(days=7)
            failure_count = len(failures)
            total_occurrences = sum(f.failure_count for f in failures)
            score = max(0.0, 100.0 - (total_occurrences * 2))

            actions = []
            if failure_count > 0:
                actions.append(f"Review {failure_count} failing keyword(s): @frp /logs failures")

            return HealthSection(
                name="DID Failure Rate",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{total_occurrences} DID mapping failure(s) across {failure_count} keyword(s) (last 7 days)",
                details={
                    "unique_failures": failure_count,
                    "total_occurrences": total_occurrences,
                },
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("DID Failure Rate", weight, str(e))

    def _check_job_performance(self) -> HealthSection:
        """Section 8: Average job performance (L-07)."""
        weight = SECTION_WEIGHTS["job_performance"]
        try:
            if not self._benchmarker:
                return self._unavailable_section("Job Performance", weight, "PerformanceBenchmarker not configured")

            summary = self._benchmarker.benchmark(days=7)
            avg_rate = summary.avg_success_rate
            critical = summary.critical_count

            actions = []
            if critical > 0:
                actions.append(f"Investigate {critical} critical job(s): @frp /logs performance --sort success_rate")

            return HealthSection(
                name="Job Performance",
                status=self._score_to_status(avg_rate),
                score=avg_rate,
                weight=weight,
                summary=f"Average success rate: {avg_rate:.1f}% ({summary.healthy_count} healthy, "
                        f"{summary.warning_count} warning, {critical} critical)",
                details={
                    "avg_success_rate": avg_rate,
                    "healthy": summary.healthy_count,
                    "warning": summary.warning_count,
                    "critical": critical,
                    "unknown": summary.unknown_count,
                },
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Job Performance", weight, str(e))

    def _check_recent_errors(self) -> HealthSection:
        """Section 9: Errors in the last 24 hours."""
        weight = SECTION_WEIGHTS["recent_errors"]
        try:
            if not self._analytics:
                return self._unavailable_section("Recent Errors", weight, "LogAnalytics not configured")

            summary = self._analytics.daily_summary()
            error_count = summary.total_errors
            score = max(0.0, 100.0 - (error_count * 10))

            actions = []
            if error_count > 0:
                actions.append(f"Review today's errors: @frp /logs summary")

            return HealthSection(
                name="Recent Errors",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{error_count} error(s) today",
                details={"error_count": error_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Recent Errors", weight, str(e))

    # ─── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _score_to_status(score: float) -> str:
        if score >= 90:
            return "pass"
        elif score >= 70:
            return "warning"
        return "fail"

    @staticmethod
    def _unavailable_section(name: str, weight: float, reason: str) -> HealthSection:
        """Create a section for an unavailable dependency."""
        return HealthSection(
            name=name,
            status="warning",
            score=50.0,
            weight=weight,
            summary=f"Unable to check: {reason}",
            details={"unavailable": True, "reason": reason},
            action_items=[],
        )

    @staticmethod
    def _error_section(name: str, weight: float, error: str) -> HealthSection:
        """Create a section for a check that threw an exception."""
        return HealthSection(
            name=name,
            status="fail",
            score=0.0,
            weight=weight,
            summary=f"Check failed: {error}",
            details={"error": error},
            action_items=[],
        )
```

---

## 7. CLI Command Implementations

### cli/main.py — Phase 4 Additions

```python
# ─── Phase 4 CLI Commands ─────────────────────────────────────────

def cmd_log_trends(args: argparse.Namespace) -> dict:
    """L-06: Timeline trend analysis."""
    from backend.logs.analytics import LogAnalytics
    from backend.analysis.trends import TrendAnalyzer

    analytics = LogAnalytics(args.db_path)
    analyzer = TrendAnalyzer(analytics)

    result = analyzer.analyze(
        days=getattr(args, "days", 14),
        job_filter=getattr(args, "job", None),
    )
    return {"success": True, "command": "log_trends", "data": result.to_dict()}


def cmd_log_performance(args: argparse.Namespace) -> dict:
    """L-07: Job performance benchmarking."""
    from backend.logs.analytics import LogAnalytics
    from backend.analysis.performance import PerformanceBenchmarker

    analytics = LogAnalytics(args.db_path)

    # Load parser if settings path provided
    parser = None
    if getattr(args, "settings_path", None):
        from backend.parsing.settings_xml import SettingsXmlParser
        parser = SettingsXmlParser(args.settings_path)

    benchmarker = PerformanceBenchmarker(analytics, parser)
    result = benchmarker.benchmark(
        sort_by=getattr(args, "sort", "success_rate"),
        ascending=getattr(args, "ascending", True),
        top_n=getattr(args, "top", None),
        days=getattr(args, "days", 30),
    )
    return {"success": True, "command": "log_performance", "data": result.to_dict()}


def cmd_analyze_consolidation(args: argparse.Namespace) -> dict:
    """A-01: Job consolidation analysis."""
    from backend.parsing.settings_xml import SettingsXmlParser
    from backend.analysis.consolidation import ConsolidationAnalyzer

    parser = SettingsXmlParser(args.settings_path)

    deal_repo = None
    if getattr(args, "db_mode", None) and getattr(args, "secrets_path", None):
        try:
            from backend.db.connection import create_connection
            from backend.db.deal_repo import DealRepository
            conn = create_connection(args.db_mode, args.secrets_path)
            deal_repo = DealRepository(conn)
        except Exception as e:
            logger.warning(f"DB connection failed, running without DID counts: {e}")

    analyzer = ConsolidationAnalyzer(parser, deal_repo)
    result = analyzer.analyze(
        xml_type=getattr(args, "type", "all"),
    )
    return {"success": True, "command": "analyze_consolidation", "data": result.to_dict()}


def cmd_analyze_impact(args: argparse.Namespace) -> dict:
    """A-02: Change impact simulation."""
    from backend.parsing.settings_xml import SettingsXmlParser
    from backend.analysis.impact import ImpactSimulator
    from backend.analysis.models import ChangeSpec

    parser = SettingsXmlParser(args.settings_path)

    deal_repo = None
    analytics = None
    if getattr(args, "db_mode", None) and getattr(args, "secrets_path", None):
        try:
            from backend.db.connection import create_connection
            from backend.db.deal_repo import DealRepository
            conn = create_connection(args.db_mode, args.secrets_path)
            deal_repo = DealRepository(conn)
        except Exception as e:
            logger.warning(f"DB connection failed: {e}")

    if getattr(args, "db_path", None):
        try:
            from backend.logs.analytics import LogAnalytics
            analytics = LogAnalytics(args.db_path)
        except Exception as e:
            logger.warning(f"Log analytics unavailable: {e}")

    change = ChangeSpec(
        change_type=args.change_type,
        target_job=getattr(args, "target_job", None),
        target_did=getattr(args, "target_did", None),
        target_company_id=getattr(args, "target_company_id", None),
        new_value=getattr(args, "new_value", None),
        raw_description=getattr(args, "raw_description", ""),
    )

    try:
        simulator = ImpactSimulator(parser, deal_repo, analytics)
        result = simulator.simulate(change)
        return {"success": True, "command": "analyze_impact", "data": result.to_dict()}
    except ValueError as e:
        return {"success": False, "command": "analyze_impact", "error": str(e)}


def cmd_analyze_health(args: argparse.Namespace) -> dict:
    """A-03: Full system health check."""
    from backend.analysis.health import HealthChecker

    # Build dependencies — each is optional
    parser = None
    deal_repo = None
    analytics = None
    coverage = None
    orphans = None
    collisions = None
    benchmarker = None

    if getattr(args, "settings_path", None):
        try:
            from backend.parsing.settings_xml import SettingsXmlParser
            parser = SettingsXmlParser(args.settings_path)
        except Exception as e:
            logger.warning(f"Settings parser failed: {e}")

    if getattr(args, "db_mode", None) and getattr(args, "secrets_path", None):
        try:
            from backend.db.connection import create_connection
            from backend.db.deal_repo import DealRepository
            conn = create_connection(args.db_mode, args.secrets_path)
            deal_repo = DealRepository(conn)
        except Exception as e:
            logger.warning(f"DB connection failed: {e}")

    if getattr(args, "db_path", None):
        try:
            from backend.logs.analytics import LogAnalytics
            analytics = LogAnalytics(args.db_path)
        except Exception as e:
            logger.warning(f"Log analytics failed: {e}")

    if parser and deal_repo:
        try:
            from backend.intel.coverage import CoverageAnalyzer
            from backend.intel.orphans import OrphanDetector
            from backend.intel.collisions import CollisionDetector
            coverage = CoverageAnalyzer(parser, deal_repo)
            orphans = OrphanDetector(parser, deal_repo)
            collisions = CollisionDetector(deal_repo)
        except Exception as e:
            logger.warning(f"Intel modules failed: {e}")

    if analytics:
        try:
            from backend.analysis.performance import PerformanceBenchmarker
            benchmarker = PerformanceBenchmarker(analytics, parser)
        except Exception as e:
            logger.warning(f"Benchmarker failed: {e}")

    checker = HealthChecker(
        parser=parser,
        deal_repo=deal_repo,
        analytics=analytics,
        coverage_analyzer=coverage,
        orphan_detector=orphans,
        collision_detector=collisions,
        benchmarker=benchmarker,
    )
    result = checker.check(xml_type=getattr(args, "type", "all"))
    return {"success": True, "command": "analyze_health", "data": result.to_dict()}


# ─── Argparse Additions ──────────────────────────────────────────

def add_phase4_commands(subparsers):
    """Register Phase 4 CLI commands."""

    # L-06
    p = subparsers.add_parser("log_trends")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--job", default=None, help="Filter to specific job")
    p.add_argument("--db-path", default="frp_logs.db")
    p.set_defaults(func=cmd_log_trends)

    # L-07
    p = subparsers.add_parser("log_performance")
    p.add_argument("--sort", default="success_rate",
                   choices=["success_rate", "total_files", "total_errors",
                            "avg_files_per_run", "last_run"])
    p.add_argument("--ascending", type=bool, default=True)
    p.add_argument("--top", type=int, default=None)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--db-path", default="frp_logs.db")
    p.add_argument("--settings-path", default=None)
    p.set_defaults(func=cmd_log_performance)

    # A-01
    p = subparsers.add_parser("analyze_consolidation")
    p.add_argument("--type", default="all", choices=["email", "sftp", "all"])
    p.add_argument("--settings-path", required=True)
    p.add_argument("--db-mode", default=None)
    p.add_argument("--secrets-path", default=None)
    p.set_defaults(func=cmd_analyze_consolidation)

    # A-02
    p = subparsers.add_parser("analyze_impact")
    p.add_argument("--change-type", required=True,
                   choices=["delete_job", "rename_did", "change_filter", "move_servicer"])
    p.add_argument("--target-job", default=None)
    p.add_argument("--target-did", default=None)
    p.add_argument("--target-company-id", type=int, default=None)
    p.add_argument("--new-value", default=None)
    p.add_argument("--raw-description", default="")
    p.add_argument("--settings-path", required=True)
    p.add_argument("--db-mode", default=None)
    p.add_argument("--secrets-path", default=None)
    p.add_argument("--db-path", default=None)
    p.set_defaults(func=cmd_analyze_impact)

    # A-03
    p = subparsers.add_parser("analyze_health")
    p.add_argument("--type", default="all", choices=["email", "sftp", "all"])
    p.add_argument("--settings-path", default=None)
    p.add_argument("--db-mode", default=None)
    p.add_argument("--secrets-path", default=None)
    p.add_argument("--db-path", default=None)
    p.set_defaults(func=cmd_analyze_health)
```

---

## 8. Extension Handler Contracts

### New: extension/handlers/analyze.js

```javascript
/**
 * Phase 4 — /analyze command handler.
 *
 * Routes:
 *   @frp /analyze consolidation  → CLI: analyze_consolidation
 *   @frp /analyze impact <desc>  → LLM parse → CLI: analyze_impact
 *   @frp /analyze health         → CLI: analyze_health
 */

async function handleAnalyze(userMessage, stream, token) {
    const parts = userMessage.trim().split(/\s+/);
    const sub = parts[0]?.toLowerCase();

    switch (sub) {
        case 'consolidation': {
            const xmlType = extractFlag(userMessage, '--type') || 'all';
            const data = await backendCall('analyze_consolidation', {
                type: xmlType,
                settings_path: config.outlookSettingsPath(),
                db_mode: config.dbMode(),
                secrets_path: config.secretsPath(),
            });
            return await generateResponse(data, stream, token,
                'Format this consolidation analysis as a grouped report. '
                + 'For each group, show shared config, individual jobs, DID counts, '
                + 'and merge recommendation.');
        }

        case 'impact': {
            // Natural language change description
            const description = parts.slice(1).join(' ');
            if (!description) {
                stream.markdown('Please describe the change to simulate.\n\n'
                    + 'Examples:\n'
                    + '- `@frp /analyze impact delete job "bonds mailbox"`\n'
                    + '- `@frp /analyze impact rename ImportDID C88 to OCW88`\n'
                    + '- `@frp /analyze impact change filter on "rptent" to "*.csv"`\n');
                return;
            }

            // Use LLM to parse intent → ChangeSpec
            const changeSpec = await parseChangeIntent(description, stream, token);
            if (!changeSpec) {
                stream.markdown('Could not parse the change description. '
                    + 'Try a structured command:\n'
                    + '`@frp /analyze impact --change-type delete_job --target-job "NAME"`\n');
                return;
            }

            const data = await backendCall('analyze_impact', {
                ...changeSpec,
                raw_description: description,
                settings_path: config.outlookSettingsPath(),
                db_mode: config.dbMode(),
                secrets_path: config.secretsPath(),
                db_path: config.logDbPath(),
            });
            return await generateResponse(data, stream, token,
                'Format this impact analysis as a risk assessment. '
                + 'Highlight affected entities, coverage changes, and recommendation.');
        }

        case 'health': {
            const xmlType = extractFlag(userMessage, '--type') || 'all';
            const data = await backendCall('analyze_health', {
                type: xmlType,
                settings_path: config.outlookSettingsPath(),
                db_mode: config.dbMode(),
                secrets_path: config.secretsPath(),
                db_path: config.logDbPath(),
            });
            return await generateResponse(data, stream, token,
                'Format this health report as a dashboard with section scores, '
                + 'status indicators (pass/warning/fail), overall grade, and '
                + 'recommended action items.');
        }

        default:
            stream.markdown('Usage:\n'
                + '- `@frp /analyze consolidation` — Find merge opportunities\n'
                + '- `@frp /analyze impact <description>` — Simulate a change\n'
                + '- `@frp /analyze health` — Full system health check\n');
    }
}


/**
 * Use vscode.lm to parse a natural language change description
 * into a structured ChangeSpec JSON object.
 */
async function parseChangeIntent(description, stream, token) {
    const PARSE_PROMPT = `You are a configuration change parser for an email/SFTP monitoring system.
Parse the user's description into a structured change specification.
Return ONLY valid JSON with these exact fields:
- change_type: one of "delete_job", "rename_did", "change_filter", "move_servicer"
- target_job: job name if applicable (string or null)
- target_did: ImportDID keyword if applicable (string or null)
- target_company_id: CompanyID/ServicerID if applicable (integer or null)
- new_value: new value if applicable (string or null)

User description: "${description}"`;

    try {
        const [model] = await vscode.lm.selectChatModels({
            vendor: 'copilot',
            family: 'gpt-4o',
        });
        if (!model) return null;

        const messages = [
            vscode.LanguageModelChatMessage.User(PARSE_PROMPT),
        ];
        const response = await model.sendRequest(messages, {}, token);

        let text = '';
        for await (const chunk of response.text) {
            text += chunk;
        }

        // Extract JSON from response (may be wrapped in ```json blocks)
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (!jsonMatch) return null;

        return JSON.parse(jsonMatch[0]);
    } catch (e) {
        logger.warn('LLM intent parsing failed:', e);
        return null;
    }
}
```

### Updated: extension/handlers/logs.js — Phase 4 additions

```javascript
// Add to existing switch(sub) in handleLogs():

case 'trends': {
    // L-06: @frp /logs trends --days 30
    const days = extractDays(userMessage) || 14;
    const jobFilter = extractJobName(userMessage);
    const data = await backendCall('log_trends', {
        days,
        job: jobFilter,
        db_path: config.logDbPath(),
    });
    return await generateResponse(data, stream, token,
        'Format these daily trends as a timeline summary. '
        + 'Include trend indicators (↑/↓/→), period totals, '
        + 'comparison with previous period, best and worst days.');
}

case 'performance': {
    // L-07: @frp /logs performance --sort success_rate --top 10
    const sort = extractFlag(userMessage, '--sort') || 'success_rate';
    const top = parseInt(extractFlag(userMessage, '--top')) || null;
    const days = extractDays(userMessage) || 30;
    const data = await backendCall('log_performance', {
        sort, top, days,
        ascending: true,
        db_path: config.logDbPath(),
        settings_path: config.outlookSettingsPath(),
    });
    return await generateResponse(data, stream, token,
        'Format this performance report as a ranked table. '
        + 'Show job name, status indicator, success rate, volume, '
        + 'and common errors for problematic jobs.');
}
```

### Follow-Up Suggestions (Phase 4)

```javascript
const PHASE4_FOLLOWUPS = {
    'log_trends': (data) => {
        const suggestions = [];
        if (data.period_total_errors > 0) {
            suggestions.push({ label: 'View failures', command: '@frp /logs failures' });
        }
        if (data.worst_day) {
            suggestions.push({ label: `Summary for ${data.worst_day}`, command: `@frp /logs summary ${data.worst_day}` });
        }
        suggestions.push({ label: 'Full health check', command: '@frp /analyze health' });
        return suggestions;
    },
    'log_performance': (data) => {
        const suggestions = [];
        const critical = data.entries?.filter(e => e.status === 'critical') || [];
        if (critical.length > 0) {
            suggestions.push({ label: `Health: ${critical[0].job_name}`, command: `@frp /logs health ${critical[0].job_name}` });
        }
        suggestions.push({ label: 'Consolidation', command: '@frp /analyze consolidation' });
        return suggestions;
    },
    'analyze_consolidation': (data) => {
        const suggestions = [];
        if (data.groups?.length > 0) {
            const g = data.groups[0];
            if (g.jobs?.length > 0) {
                suggestions.push({ label: `Servicer ${g.jobs[0].servicer_id}`, command: `@frp /deals servicer ${g.jobs[0].servicer_id}` });
            }
            suggestions.push({ label: 'Impact analysis', command: '@frp /analyze impact' });
        }
        return suggestions;
    },
    'analyze_impact': (data) => {
        const suggestions = [
            { label: 'Full health check', command: '@frp /analyze health' },
        ];
        if (data.risk_level === 'low') {
            if (data.change?.change_type === 'delete_job') {
                suggestions.push({ label: 'Edit job', command: `@frp /jobs edit ${data.change.target_job}` });
            }
        }
        return suggestions;
    },
    'analyze_health': (data) => {
        const suggestions = [];
        for (const section of (data.sections || [])) {
            if (section.action_items?.length > 0) {
                // Parse first action item for a command reference
                const cmdMatch = section.action_items[0].match(/(@frp\s+\/\S+.*)/);
                if (cmdMatch) {
                    suggestions.push({ label: section.name, command: cmdMatch[1] });
                }
            }
        }
        return suggestions.slice(0, 4); // Limit to 4 follow-ups
    },
};
```

### Updated package.json — New Slash Command

```json
{
    "chatParticipants": [{
        "id": "frp-agent",
        "name": "frp",
        "description": "FRP Email & SFTP Monitor Agent",
        "commands": [
            {"name": "jobs", "description": "Search, create, edit, validate jobs"},
            {"name": "deals", "description": "Coverage gaps, orphans, collisions, dossier"},
            {"name": "logs", "description": "Sync, query, health, summary, trends, performance"},
            {"name": "deploy", "description": "Save, diff, rollback, list backups"},
            {"name": "triage", "description": "Verify, match, new email analysis"},
            {"name": "analyze", "description": "Consolidation, impact, health check"}
        ]
    }]
}
```

---

## 9. Error Handling

### New Error Codes

| Code | Message | Trigger |
|------|---------|---------|
| TREND-001 | No log data for requested period | Empty SQLite results for date range |
| TREND-002 | Invalid days parameter | days ≤ 0 or > 365 |
| PERF-001 | No jobs found | Neither parser nor SQLite has job data |
| CONSOL-001 | No consolidation groups found | All jobs have unique signatures |
| IMPACT-001 | Unknown change_type | Unsupported change type string |
| IMPACT-002 | Target not found | Job/DID not in Settings.xml or DB |
| IMPACT-003 | Missing required field | Required ChangeSpec field is None |
| IMPACT-004 | LLM intent parse failed | LLM returned invalid JSON for /analyze impact |
| HEALTH-001 | No dependencies available | All checkers are None |

### Graceful Degradation Rules

| Scenario | Behavior |
|----------|----------|
| DB unavailable (consolidation) | Groups shown without DID counts |
| DB unavailable (impact) | Affected entities shown without coverage data |
| SQLite unavailable (trends/perf) | Return error: "Run @frp /logs sync first" |
| Parser unavailable (performance) | Use job names from SQLite only |
| Any health section throws | Section score=0, status="fail", other sections continue |
| LLM parse fails (impact) | Suggest structured CLI input |
| SQLite stale (any log command) | Include staleness_warning in response |

---

## 10. File Manifest

### New Files

| File | Lines (est.) | Tests |
|------|-------------|-------|
| `backend/analysis/__init__.py` | ~10 | — |
| `backend/analysis/models.py` | ~200 | 25 |
| `backend/analysis/trends.py` | ~150 | 18 |
| `backend/analysis/performance.py` | ~180 | 18 |
| `backend/analysis/consolidation.py` | ~200 | 16 |
| `backend/analysis/impact.py` | ~280 | 22 |
| `backend/analysis/health.py` | ~280 | 18 |
| `extension/handlers/analyze.js` | ~120 | 8 manual |

### Changed Files

| File | Changes | Lines (est.) |
|------|---------|-------------|
| `cli/main.py` | +5 commands, +argparse | ~250 |
| `extension/handlers/logs.js` | +2 subcommands | ~40 |
| `extension/chat/participant.js` | +/analyze route | ~15 |
| `extension/package.json` | +1 slash command (/analyze) | ~5 |
| `backend/common/errors.py` | +9 error codes | ~20 |

### Totals

| Category | Lines | Tests |
|----------|-------|-------|
| New Python | ~1,300 | 117 |
| Changed Python (CLI) | ~250 | — |
| New/Changed JS | ~175 | 8 (manual) |
| **Total** | **~1,725** | **125** |

---

*Next document: [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)*
