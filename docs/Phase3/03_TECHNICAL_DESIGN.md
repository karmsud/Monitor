# Phase 3: Technical Design
## FRP Agent — Log Analytics & Email Triage Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Estimated New/Changed Lines:** ~1,400 Python + ~200 JS = ~1,600 total  
**New Tests:** ~148 tests  

---

## Table of Contents
1. [Log Analytics Models](#1-log-analytics-models)
2. [Log Analytics Engine](#2-log-analytics-engine)
3. [Triage Models](#3-triage-models)
4. [Msg Parser](#4-msg-parser)
5. [Triage Matcher](#5-triage-matcher)
6. [Triage Analyzer](#6-triage-analyzer)
7. [DB Repository Additions](#7-db-repository-additions)
8. [CLI Command Implementations](#8-cli-command-implementations)
9. [Extension Handler Contracts](#9-extension-handler-contracts)
10. [Error Handling](#10-error-handling)
11. [File Manifest](#11-file-manifest)

---

## 1. Log Analytics Models

### backend/logs/models.py (new file)

```python
"""Data models for log analytics results."""

from dataclasses import dataclass, field, asdict


@dataclass
class DealActivity:
    """Single log event for a deal."""
    timestamp: str
    job_name: str
    event_type: str          # job_start, email_processed, did_mapping_failure, error
    detail: str              # Subject line, filename, error text
    log_file: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DIDFailure:
    """Aggregated DID mapping failure record."""
    import_did: str          # The failed keyword
    failure_count: int
    affected_jobs: list[str]
    first_seen: str          # ISO timestamp
    last_seen: str           # ISO timestamp

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JobHealth:
    """Health metrics for a monitoring job."""
    job_name: str
    total_runs: int
    successful_runs: int
    error_count: int
    success_rate: float      # 0.0 - 100.0
    status: str              # "healthy" | "warning" | "critical"
    last_run: str | None
    last_error: str | None
    avg_emails_per_run: float
    common_errors: list[dict] = field(default_factory=list)
    date_range: str = "Last 30 days"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DailySummary:
    """Operational summary for one day."""
    date: str                # YYYY-MM-DD
    total_jobs_run: int
    total_emails_processed: int
    total_files_loaded: int
    total_errors: int
    total_did_failures: int
    top_jobs_by_volume: list[dict] = field(default_factory=list)
    top_error_sources: list[dict] = field(default_factory=list)
    comparison: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)
```

---

## 2. Log Analytics Engine

### backend/logs/analytics.py (new file)

```python
"""Log analytics query engine over SQLite index."""

import sqlite3
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path

from backend.logs.models import DealActivity, DIDFailure, JobHealth, DailySummary

logger = logging.getLogger(__name__)

# Regex to extract ImportDID from "Did not find DID mapping for [KEYWORD]"
DID_FAILURE_RE = re.compile(r"Did not find DID mapping for \[(.+?)\]", re.IGNORECASE)


class LogAnalytics:
    """Query engine over the SQLite log index."""

    def __init__(self, db_path: str):
        """
        Args:
            db_path: Path to frp_logs.db SQLite database
        """
        self._db_path = db_path
        self._validate_db()

    def _validate_db(self) -> None:
        """Verify database exists and has expected tables."""
        if not Path(self._db_path).exists():
            raise FileNotFoundError(f"Log database not found: {self._db_path}")
        conn = sqlite3.connect(self._db_path)
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            required = {"log_events", "log_files", "sync_meta"}
            missing = required - tables
            if missing:
                raise ValueError(f"Missing tables in log database: {missing}")
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def check_staleness(self) -> dict | None:
        """
        Check if the log index is stale (>24h since last sync).
        
        Returns:
            None if fresh, dict with warning message if stale.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM sync_meta WHERE key = 'last_sync'"
            ).fetchone()
            if not row:
                return {"warning": "Log index has never been synced. Run @frp /logs sync first."}
            last_sync = datetime.fromisoformat(row["value"])
            hours_ago = (datetime.now() - last_sync).total_seconds() / 3600
            if hours_ago > 24:
                return {
                    "warning": f"Log index was last synced {int(hours_ago)} hours ago. "
                               f"Run @frp /logs sync for latest data."
                }
            return None
        finally:
            conn.close()

    def deal_activity(
        self, did_identifier: str, days: int = 30, import_did: str | None = None
    ) -> list[DealActivity]:
        """
        Query log events related to a specific deal.

        Args:
            did_identifier: User-provided DID name or number
            days: Number of days to look back
            import_did: Pre-resolved ImportDID keyword (if None, uses did_identifier as keyword)

        Returns:
            List of DealActivity, newest first.
        """
        keyword = import_did or did_identifier
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT timestamp, job_name, event_type, detail, log_file
                FROM log_events
                WHERE detail LIKE ? AND timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (f"%{keyword}%", cutoff)
            ).fetchall()
            return [
                DealActivity(
                    timestamp=r["timestamp"],
                    job_name=r["job_name"] or "unknown",
                    event_type=r["event_type"],
                    detail=r["detail"] or "",
                    log_file=r["log_file"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def did_failures(
        self, days: int = 30, job_filter: str | None = None
    ) -> list[DIDFailure]:
        """
        Aggregate DID mapping failures from logs.

        Args:
            days: Days to look back
            job_filter: Optional job name filter

        Returns:
            List of DIDFailure sorted by failure_count descending.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        params: list = [cutoff]
        job_clause = ""
        if job_filter:
            job_clause = "AND job_name = ?"
            params.append(job_filter)

        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"""
                SELECT detail, COUNT(*) as cnt,
                       GROUP_CONCAT(DISTINCT job_name) as jobs,
                       MIN(timestamp) as first_seen,
                       MAX(timestamp) as last_seen
                FROM log_events
                WHERE event_type = 'did_mapping_failure'
                  AND timestamp >= ?
                  {job_clause}
                GROUP BY detail
                ORDER BY cnt DESC
                """,
                params
            ).fetchall()

            results = []
            for r in rows:
                detail = r["detail"] or ""
                m = DID_FAILURE_RE.search(detail)
                import_did = m.group(1) if m else detail
                results.append(DIDFailure(
                    import_did=import_did,
                    failure_count=r["cnt"],
                    affected_jobs=(r["jobs"] or "").split(","),
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                ))
            return results
        finally:
            conn.close()

    def job_health(self, job_name: str, days: int = 30) -> JobHealth:
        """
        Compute health metrics for a specific job.

        Args:
            job_name: Exact or partial job name
            days: Days to look back

        Returns:
            JobHealth dataclass

        Raises:
            ValueError: If job_name matches 0 or 2+ jobs
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self._get_conn()
        try:
            # Resolve job name
            exact = conn.execute(
                "SELECT DISTINCT job_name FROM log_events WHERE job_name = ?",
                (job_name,)
            ).fetchall()
            if not exact:
                fuzzy = conn.execute(
                    "SELECT DISTINCT job_name FROM log_events WHERE job_name LIKE ?",
                    (f"%{job_name}%",)
                ).fetchall()
                if not fuzzy:
                    raise ValueError(f"No jobs found matching '{job_name}'")
                if len(fuzzy) > 1:
                    names = [r["job_name"] for r in fuzzy]
                    raise ValueError(
                        f"Ambiguous job name '{job_name}'. Matches: {names}"
                    )
                resolved = fuzzy[0]["job_name"]
            else:
                resolved = exact[0]["job_name"]

            # Count runs (distinct log files with job_start)
            total_runs = conn.execute(
                """
                SELECT COUNT(DISTINCT log_file) FROM log_events
                WHERE job_name = ? AND event_type = 'job_start' AND timestamp >= ?
                """,
                (resolved, cutoff)
            ).fetchone()[0]

            # Count errors
            error_count = conn.execute(
                """
                SELECT COUNT(*) FROM log_events
                WHERE job_name = ? AND event_type = 'error' AND timestamp >= ?
                """,
                (resolved, cutoff)
            ).fetchone()[0]

            # Distinct log files with errors = error_runs
            error_runs = conn.execute(
                """
                SELECT COUNT(DISTINCT log_file) FROM log_events
                WHERE job_name = ? AND event_type = 'error' AND timestamp >= ?
                """,
                (resolved, cutoff)
            ).fetchone()[0]

            # Email count
            email_count = conn.execute(
                """
                SELECT COUNT(*) FROM log_events
                WHERE job_name = ? AND event_type = 'email_processed' AND timestamp >= ?
                """,
                (resolved, cutoff)
            ).fetchone()[0]

            # Last run
            last_run_row = conn.execute(
                """
                SELECT MAX(timestamp) FROM log_events
                WHERE job_name = ? AND event_type = 'job_start'
                """,
                (resolved,)
            ).fetchone()
            last_run = last_run_row[0] if last_run_row else None

            # Last error
            last_error_row = conn.execute(
                """
                SELECT detail, timestamp FROM log_events
                WHERE job_name = ? AND event_type = 'error'
                ORDER BY timestamp DESC LIMIT 1
                """,
                (resolved,)
            ).fetchone()
            last_error = (
                f"{last_error_row['detail']} at {last_error_row['timestamp']}"
                if last_error_row else None
            )

            # Common errors
            common = conn.execute(
                """
                SELECT detail, COUNT(*) as cnt FROM log_events
                WHERE job_name = ? AND event_type = 'error' AND timestamp >= ?
                GROUP BY detail ORDER BY cnt DESC LIMIT 5
                """,
                (resolved, cutoff)
            ).fetchall()

            successful = total_runs - error_runs
            rate = (successful / total_runs * 100) if total_runs > 0 else 0.0
            avg_emails = email_count / total_runs if total_runs > 0 else 0.0

            if rate > 95:
                status = "healthy"
            elif rate >= 80:
                status = "warning"
            else:
                status = "critical"

            return JobHealth(
                job_name=resolved,
                total_runs=total_runs,
                successful_runs=successful,
                error_count=error_count,
                success_rate=round(rate, 1),
                status=status,
                last_run=last_run,
                last_error=last_error,
                avg_emails_per_run=round(avg_emails, 1),
                common_errors=[
                    {"error": r["detail"], "count": r["cnt"]} for r in common
                ],
                date_range=f"Last {days} days",
            )
        finally:
            conn.close()

    def daily_summary(self, date: str | None = None) -> DailySummary:
        """
        Generate operational summary for a given date.

        Args:
            date: YYYY-MM-DD string (defaults to today)

        Returns:
            DailySummary dataclass
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        conn = self._get_conn()
        try:
            def count_for_date(d: str, event_type: str | None = None, distinct_job: bool = False) -> int:
                if distinct_job:
                    sql = "SELECT COUNT(DISTINCT job_name) FROM log_events WHERE date(timestamp) = ?"
                elif event_type:
                    sql = f"SELECT COUNT(*) FROM log_events WHERE date(timestamp) = ? AND event_type = ?"
                    return conn.execute(sql, (d, event_type)).fetchone()[0]
                else:
                    sql = "SELECT COUNT(*) FROM log_events WHERE date(timestamp) = ?"
                return conn.execute(sql, (d,)).fetchone()[0]

            jobs_run = count_for_date(date, distinct_job=True)
            emails = count_for_date(date, "email_processed")
            files = count_for_date(date, "email_processed")  # files ≈ emails in this context
            errors = count_for_date(date, "error")
            did_failures = count_for_date(date, "did_mapping_failure")

            # Top 5 jobs by volume
            top_jobs = conn.execute(
                """
                SELECT job_name, COUNT(*) as cnt FROM log_events
                WHERE date(timestamp) = ? AND event_type = 'email_processed'
                GROUP BY job_name ORDER BY cnt DESC LIMIT 5
                """,
                (date,)
            ).fetchall()

            # Top 5 error sources
            top_errors = conn.execute(
                """
                SELECT job_name, COUNT(*) as cnt FROM log_events
                WHERE date(timestamp) = ? AND event_type = 'error'
                GROUP BY job_name ORDER BY cnt DESC LIMIT 5
                """,
                (date,)
            ).fetchall()

            # Comparison with previous day
            prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            prev_emails = count_for_date(prev_date, "email_processed")
            prev_errors = count_for_date(prev_date, "error")
            prev_did = count_for_date(prev_date, "did_mapping_failure")

            comparison = None
            if prev_emails > 0 or prev_errors > 0:
                comparison = {
                    "prev_date": prev_date,
                    "delta_emails": emails - prev_emails,
                    "delta_errors": errors - prev_errors,
                    "delta_did_failures": did_failures - prev_did,
                }

            return DailySummary(
                date=date,
                total_jobs_run=jobs_run,
                total_emails_processed=emails,
                total_files_loaded=files,
                total_errors=errors,
                total_did_failures=did_failures,
                top_jobs_by_volume=[
                    {"job": r["job_name"], "emails": r["cnt"]} for r in top_jobs
                ],
                top_error_sources=[
                    {"job": r["job_name"], "errors": r["cnt"]} for r in top_errors
                ],
                comparison=comparison,
            )
        finally:
            conn.close()
```

---

## 3. Triage Models

### backend/triage/models.py (new file)

```python
"""Data models for email triage pipeline."""

from dataclasses import dataclass, field, asdict


@dataclass
class EmailInfo:
    """Parsed .msg file metadata."""
    sender: str
    sender_name: str
    subject: str
    date: str
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    body_preview: str = ""           # First 500 chars — NEVER sent to LLM
    attachment_names: list[str] = field(default_factory=list)
    file_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_safe_dict(self) -> dict:
        """Return metadata safe for LLM consumption (no body, no full addresses)."""
        return {
            "sender_domain": self.sender.split("@")[-1] if "@" in self.sender else "",
            "sender_name": self.sender_name,
            "subject": self.subject,
            "date": self.date,
            "attachment_count": len(self.attachment_names),
            "attachment_names": self.attachment_names,
        }


@dataclass
class MatchResult:
    """Single job match result for an email."""
    job_name: str
    xml_type: str                    # "email" or "sftp"
    match_type: str                  # "sender", "subject", "both"
    match_confidence: str            # "exact", "partial"
    servicer_id: str | None
    matched_filter: str              # The filter value that matched
    email_field_matched: str         # sender, subject, or both

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def sort_score(self) -> int:
        """Higher score = better match, for sorting."""
        type_score = {"both": 3, "sender": 2, "subject": 1}.get(self.match_type, 0)
        conf_score = {"exact": 2, "partial": 1}.get(self.match_confidence, 0)
        return type_score * 10 + conf_score


@dataclass
class TriageResult:
    """Complete triage analysis result."""
    email_info: EmailInfo
    matches: list[MatchResult] = field(default_factory=list)
    has_match: bool = False
    coverage_status: str | None = None      # "covered", "partial", "no_coverage"
    did_count: int | None = None
    suggested_template: str | None = None   # Phase 2 template name
    suggested_config: dict | None = None    # Recommended field values
    recommendation: str = ""                # LLM-friendly summary

    def to_dict(self) -> dict:
        d = asdict(self)
        d["email_info"] = self.email_info.to_dict()
        d["matches"] = [m.to_dict() for m in self.matches]
        return d
```

---

## 4. Msg Parser

### backend/triage/msg_parser.py (new file)

```python
"""Parse .msg (Outlook) files using extract-msg library."""

import logging
from pathlib import Path
from datetime import datetime

from backend.triage.models import EmailInfo

logger = logging.getLogger(__name__)


class MsgParser:
    """Parse Outlook .msg files into EmailInfo dataclass."""

    SUPPORTED_EXTENSIONS = {".msg"}
    MAX_BODY_PREVIEW = 500

    @staticmethod
    def parse(msg_path: str) -> EmailInfo:
        """
        Parse a .msg file and extract key metadata.

        Args:
            msg_path: Absolute or relative path to .msg file

        Returns:
            EmailInfo with extracted fields

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file is not a .msg file
            RuntimeError: If extract-msg fails to parse
        """
        path = Path(msg_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {msg_path}")
        if path.suffix.lower() not in MsgParser.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {path.suffix}. Expected .msg")

        try:
            import extract_msg
        except ImportError:
            raise RuntimeError(
                "extract-msg is not installed. Run: pip install extract-msg"
            )

        msg = None
        try:
            msg = extract_msg.Message(str(path))

            # Extract sender
            sender = msg.sender or ""
            sender_name = ""
            if hasattr(msg, "senderName"):
                sender_name = msg.senderName or ""

            # Extract subject
            subject = msg.subject or ""

            # Extract date
            date_str = ""
            if msg.date:
                if isinstance(msg.date, str):
                    date_str = msg.date
                elif isinstance(msg.date, datetime):
                    date_str = msg.date.isoformat()
                else:
                    date_str = str(msg.date)

            # Extract recipients
            to_list = []
            cc_list = []
            if hasattr(msg, "recipients") and msg.recipients:
                for r in msg.recipients:
                    email_addr = getattr(r, "email", "") or ""
                    r_type = getattr(r, "type", "to") or "to"
                    if str(r_type).lower() in ("to", "1"):
                        to_list.append(email_addr)
                    elif str(r_type).lower() in ("cc", "2"):
                        cc_list.append(email_addr)

            # Extract body preview
            body = msg.body or ""
            body_preview = body[:MsgParser.MAX_BODY_PREVIEW]

            # Extract attachment filenames
            attachment_names = []
            if hasattr(msg, "attachments") and msg.attachments:
                for att in msg.attachments:
                    name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or "unnamed"
                    attachment_names.append(name)

            return EmailInfo(
                sender=sender,
                sender_name=sender_name,
                subject=subject,
                date=date_str,
                to=to_list,
                cc=cc_list,
                body_preview=body_preview,
                attachment_names=attachment_names,
                file_path=str(path),
            )
        except Exception as e:
            if "extract_msg" not in str(type(e).__module__):
                raise
            raise RuntimeError(f"Failed to parse .msg file: {e}")
        finally:
            if msg:
                try:
                    msg.close()
                except Exception:
                    pass
```

---

## 5. Triage Matcher

### backend/triage/matcher.py (new file)

```python
"""Match email metadata against Settings.xml job filters."""

import logging
from backend.triage.models import EmailInfo, MatchResult

logger = logging.getLogger(__name__)


class TriageMatcher:
    """
    Compare email metadata against all job filter configurations
    to find matching jobs.
    """

    @staticmethod
    def match(email_info: EmailInfo, jobs: list, xml_type: str = "email") -> list[MatchResult]:
        """
        Find jobs whose filters match the given email.

        Args:
            email_info: Parsed email metadata
            jobs: List of EmailJob or SftpJob from SettingsXmlParser
            xml_type: "email" or "sftp"

        Returns:
            List of MatchResult, sorted by sort_score descending (best match first)
        """
        results: list[MatchResult] = []

        for job in jobs:
            matches = TriageMatcher._check_job(email_info, job, xml_type)
            results.extend(matches)

        results.sort(key=lambda m: m.sort_score, reverse=True)
        return results

    @staticmethod
    def _check_job(email_info: EmailInfo, job, xml_type: str) -> list[MatchResult]:
        """Check a single job's filters against the email."""
        sender_match = False
        subject_match = False
        matched_sender_filter = ""
        matched_subject_filter = ""

        # Extract filters from job's parsers
        filters = TriageMatcher._extract_filters(job)

        for f in filters:
            # Check sender filters
            if f.get("sender_filter"):
                sf = f["sender_filter"].lower()
                if sf in email_info.sender.lower() or sf in email_info.sender_name.lower():
                    sender_match = True
                    matched_sender_filter = f["sender_filter"]

            # Check subject filters
            if f.get("subject_filter"):
                subf = f["subject_filter"].lower()
                if subf in email_info.subject.lower():
                    subject_match = True
                    matched_subject_filter = f["subject_filter"]

        if not sender_match and not subject_match:
            return []

        # Determine match type and confidence
        if sender_match and subject_match:
            match_type = "both"
            matched_filter = f"{matched_sender_filter} + {matched_subject_filter}"
            email_field = "both"
        elif sender_match:
            match_type = "sender"
            matched_filter = matched_sender_filter
            email_field = "sender"
        else:
            match_type = "subject"
            matched_filter = matched_subject_filter
            email_field = "subject"

        # Confidence: exact if the filter is a full match of the field
        confidence = TriageMatcher._assess_confidence(
            email_info, matched_sender_filter, matched_subject_filter,
            sender_match, subject_match
        )

        job_name = getattr(job, "name", None) or getattr(job, "job_name", "unknown")
        servicer_id = getattr(job, "servicer_id", None) or getattr(job, "ServicerID", None)

        return [MatchResult(
            job_name=str(job_name),
            xml_type=xml_type,
            match_type=match_type,
            match_confidence=confidence,
            servicer_id=str(servicer_id) if servicer_id else None,
            matched_filter=matched_filter,
            email_field_matched=email_field,
        )]

    @staticmethod
    def _extract_filters(job) -> list[dict]:
        """
        Extract sender/subject filter values from a job's parser config.

        Returns list of dicts: [{"sender_filter": "...", "subject_filter": "..."}, ...]
        """
        filters = []
        parsers = getattr(job, "parsers", None) or []
        if not parsers:
            # Try alternative attribute names
            parsers = getattr(job, "parser_list", None) or []

        for parser in parsers:
            f = {}
            if isinstance(parser, dict):
                f["sender_filter"] = parser.get("SenderFilter", "") or parser.get("sender_filter", "")
                f["subject_filter"] = parser.get("SubjectFilter", "") or parser.get("subject_filter", "")
            else:
                f["sender_filter"] = getattr(parser, "SenderFilter", "") or getattr(parser, "sender_filter", "")
                f["subject_filter"] = getattr(parser, "SubjectFilter", "") or getattr(parser, "subject_filter", "")
            if f.get("sender_filter") or f.get("subject_filter"):
                filters.append(f)

        # If no parser-level filters, check job-level attributes
        if not filters:
            job_sf = getattr(job, "SubjectFilter", "") or getattr(job, "subject_filter", "")
            job_sender = getattr(job, "SenderFilter", "") or getattr(job, "sender_filter", "")
            if job_sf or job_sender:
                filters.append({"sender_filter": job_sender, "subject_filter": job_sf})

        return filters

    @staticmethod
    def _assess_confidence(
        email_info: EmailInfo,
        sender_filter: str,
        subject_filter: str,
        sender_match: bool,
        subject_match: bool,
    ) -> str:
        """
        Assess match confidence: exact or partial.

        Exact: filter == full field value (case-insensitive)
        Partial: filter is a substring of the field
        """
        if sender_match and sender_filter:
            if sender_filter.lower() == email_info.sender.lower():
                return "exact"
        if subject_match and subject_filter:
            if subject_filter.lower() == email_info.subject.lower():
                return "exact"
        return "partial"
```

---

## 6. Triage Analyzer

### backend/triage/analyzer.py (new file)

```python
"""
No-match analysis engine for E-03.
Suggests template and configuration when no existing job matches an email.
"""

import logging
from pathlib import Path

from backend.triage.models import EmailInfo, TriageResult, MatchResult
from backend.triage.msg_parser import MsgParser
from backend.triage.matcher import TriageMatcher
from backend.xml.parser import SettingsXmlParser
from backend.xml.templates import TemplateInventory
from backend.intel.coverage import CoverageAnalyzer
from backend.db.deal_repo import DealRepository

logger = logging.getLogger(__name__)

# Attachment extension → likely parser mapping
ATTACHMENT_PARSER_HINTS = {
    ".csv": "MailToParser",
    ".xlsx": "MailToParser",
    ".xls": "MailToParser",
    ".txt": "MailToFolder",
    ".pdf": "MailToFolder",
    ".zip": "MailToFolder",
}


class TriageAnalyzer:
    """Full triage pipeline: parse, match, analyze, recommend."""

    def __init__(
        self,
        settings_path: str,
        xml_type: str = "email",
        deal_repo: DealRepository | None = None,
    ):
        self._settings_path = settings_path
        self._xml_type = xml_type
        self._deal_repo = deal_repo
        self._parser = SettingsXmlParser(settings_path)

    def verify(self, msg_path: str) -> TriageResult:
        """
        E-01: Parse email, match against jobs, verify DID coverage.

        Args:
            msg_path: Path to .msg file

        Returns:
            TriageResult with matches and coverage status
        """
        email_info = MsgParser.parse(msg_path)
        jobs = self._parser.get_all_jobs()
        matches = TriageMatcher.match(email_info, jobs, self._xml_type)

        result = TriageResult(email_info=email_info)
        result.matches = matches
        result.has_match = len(matches) > 0

        if result.has_match and self._deal_repo:
            top = matches[0]
            if top.servicer_id:
                try:
                    sid = int(top.servicer_id)
                    deals = self._deal_repo.get_deals_by_company(sid)
                    result.did_count = len(deals)
                    if result.did_count > 0:
                        result.coverage_status = "covered"
                    else:
                        result.coverage_status = "partial"
                except (ValueError, Exception) as e:
                    logger.warning(f"Coverage check failed: {e}")
                    result.coverage_status = None

        if result.has_match:
            top = matches[0]
            result.recommendation = (
                f"Email matches job '{top.job_name}' "
                f"({top.match_type} match, {top.match_confidence} confidence)"
                + (f". {result.did_count} DIDs covered." if result.did_count else ".")
            )
        else:
            result.recommendation = (
                "No existing job matches this email. "
                "Use @frp /triage new to analyze and suggest a template."
            )

        return result

    def match_only(self, msg_path: str | None = None,
                   sender: str | None = None,
                   subject: str | None = None) -> TriageResult:
        """
        E-02: Match email against job filters (no DID verification).

        Args:
            msg_path: Path to .msg file (or None if manual input)
            sender: Manual sender override
            subject: Manual subject override

        Returns:
            TriageResult with matches
        """
        if msg_path:
            email_info = MsgParser.parse(msg_path)
        else:
            email_info = EmailInfo(
                sender=sender or "",
                sender_name="",
                subject=subject or "",
                date="",
                file_path="manual_input",
            )

        jobs = self._parser.get_all_jobs()
        matches = TriageMatcher.match(email_info, jobs, self._xml_type)

        result = TriageResult(email_info=email_info)
        result.matches = matches
        result.has_match = len(matches) > 0
        result.recommendation = (
            f"{len(matches)} match(es) found. Review match details and confirm relevance."
            if matches
            else "No matches found. Use @frp /triage new for analysis."
        )
        return result

    def analyze_new(self, msg_path: str) -> TriageResult:
        """
        E-03: Full no-match analysis with template suggestion.

        Args:
            msg_path: Path to .msg file

        Returns:
            TriageResult with suggested template and config
        """
        email_info = MsgParser.parse(msg_path)
        jobs = self._parser.get_all_jobs()
        matches = TriageMatcher.match(email_info, jobs, self._xml_type)

        result = TriageResult(email_info=email_info)
        result.matches = matches
        result.has_match = len(matches) > 0

        # Suggest template based on attachments
        suggested_parser = self._guess_parser(email_info)
        templates = TemplateInventory(self._parser).discover_templates()
        suggested = None
        for t in templates:
            if hasattr(t, "parser_names") and suggested_parser in (t.parser_names or []):
                suggested = t
                break
        if not suggested and templates:
            suggested = templates[0]  # fallback to most common

        if suggested:
            result.suggested_template = (
                getattr(suggested, "pattern_name", None) or str(suggested)
            )

        # Build suggested configuration
        result.suggested_config = {
            "mailbox": email_info.to[0] if email_info.to else "UNKNOWN",
            "subject_filter": self._extract_subject_pattern(email_info.subject),
            "sender_filter": email_info.sender,
            "servicer_id": "UNKNOWN",
        }

        # Try to resolve servicer from sender domain
        if self._deal_repo:
            try:
                result.coverage_status = "no_coverage"
            except Exception as e:
                logger.warning(f"Servicer lookup failed: {e}")

        result.recommendation = (
            f"No matching job found. "
            f"Suggested template: '{result.suggested_template or 'unknown'}'. "
            f"Use @frp /jobs create to get started."
        )

        return result

    def _guess_parser(self, email_info: EmailInfo) -> str:
        """Guess the likely parser type based on attachment extensions."""
        if not email_info.attachment_names:
            return "MailToFolder"
        for name in email_info.attachment_names:
            ext = Path(name).suffix.lower()
            if ext in ATTACHMENT_PARSER_HINTS:
                return ATTACHMENT_PARSER_HINTS[ext]
        return "MailToFolder"

    @staticmethod
    def _extract_subject_pattern(subject: str) -> str:
        """
        Extract a likely filter pattern from an email subject.
        Removes dates and numbers to create a reusable filter.
        """
        import re
        # Remove common date patterns
        pattern = re.sub(
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "", subject
        )
        # Remove standalone numbers
        pattern = re.sub(r"\b\d+\b", "", pattern)
        # Collapse whitespace
        pattern = re.sub(r"\s+", " ", pattern).strip()
        return pattern if pattern else subject
```

---

## 7. DB Repository Additions

### backend/db/deal_repo.py — Phase 3 Addition

```python
# Add to existing DealRepository class:

def resolve_did_by_name(self, did_identifier: str) -> str | None:
    """
    Resolve a DID name/number to its ImportDID keyword.

    Args:
        did_identifier: DID number (e.g., "1234") or name (e.g., "CSFB 2006-HEAT5")

    Returns:
        ImportDID string if found, None otherwise
    """
    conn = self._get_connection()
    try:
        cursor = conn.cursor()
        # Try as DID number first
        try:
            did_num = int(did_identifier)
            cursor.execute(
                "SELECT ImportDID FROM tblExternalDIDRef WHERE DID = ?",
                (did_num,)
            )
            row = cursor.fetchone()
            if row:
                return row[0]
        except ValueError:
            pass  # Not a number, try name search

        # Try as ImportDID keyword (exact)
        cursor.execute(
            "SELECT DISTINCT ImportDID FROM tblExternalDIDRef WHERE ImportDID = ?",
            (did_identifier,)
        )
        row = cursor.fetchone()
        if row:
            return row[0]

        # Try partial match
        cursor.execute(
            "SELECT DISTINCT ImportDID FROM tblExternalDIDRef WHERE ImportDID LIKE ?",
            (f"%{did_identifier}%",)
        )
        rows = cursor.fetchall()
        if len(rows) == 1:
            return rows[0][0]
        return None
    finally:
        conn.close()


def get_companies_by_sender_domain(self, domain: str) -> list[int]:
    """
    Attempt to find companies associated with a sender domain.

    This is a heuristic lookup — ImportDID keywords sometimes contain
    company abbreviations that map to sender domains.

    Args:
        domain: Email domain (e.g., "csmc.com")

    Returns:
        List of CompanyIDs (may be empty)
    """
    # Extract the main part of the domain (before TLD)
    prefix = domain.split(".")[0].upper() if "." in domain else domain.upper()

    conn = self._get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT CompanyID FROM tblExternalDIDRef WHERE ImportDID LIKE ?",
            (f"%{prefix}%",)
        )
        return [r[0] for r in cursor.fetchall()]
    finally:
        conn.close()
```

---

## 8. CLI Command Implementations

### cli/main.py — Phase 3 Additions

```python
# ─── Phase 3 CLI Commands ─────────────────────────────────────────

def cmd_log_deal_activity(args: argparse.Namespace) -> dict:
    """L-02: Query deal activity from log index."""
    from backend.logs.analytics import LogAnalytics

    analytics = LogAnalytics(args.db_path)
    staleness = analytics.check_staleness()

    # Resolve DID if DB available
    import_did = None
    if args.db_mode and args.secrets_path:
        try:
            from backend.db.deal_repo import DealRepository
            from backend.db.connection import create_connection
            conn = create_connection(args.db_mode, args.secrets_path)
            repo = DealRepository(conn)
            import_did = repo.resolve_did_by_name(args.did)
        except Exception as e:
            logger.warning(f"DID resolution failed, using raw identifier: {e}")

    events = analytics.deal_activity(
        did_identifier=args.did,
        days=getattr(args, "days", 30),
        import_did=import_did,
    )

    result = {
        "did_identifier": args.did,
        "resolved_import_did": import_did or args.did,
        "date_range": f"Last {args.days} days",
        "total_events": len(events),
        "events": [e.to_dict() for e in events],
    }
    if staleness:
        result["warning"] = staleness["warning"]
    return {"success": True, "command": "log_deal_activity", "data": result}


def cmd_log_did_failures(args: argparse.Namespace) -> dict:
    """L-03: List DID mapping failures from logs."""
    from backend.logs.analytics import LogAnalytics

    analytics = LogAnalytics(args.db_path)
    staleness = analytics.check_staleness()

    failures = analytics.did_failures(
        days=getattr(args, "days", 30),
        job_filter=getattr(args, "job_filter", None),
    )

    result = {
        "date_range": f"Last {args.days} days",
        "total_unique_failures": len(failures),
        "failures": [f.to_dict() for f in failures],
    }
    if staleness:
        result["warning"] = staleness["warning"]
    return {"success": True, "command": "log_did_failures", "data": result}


def cmd_log_job_health(args: argparse.Namespace) -> dict:
    """L-04: Job health dashboard."""
    from backend.logs.analytics import LogAnalytics

    analytics = LogAnalytics(args.db_path)
    staleness = analytics.check_staleness()

    try:
        health = analytics.job_health(
            job_name=args.job_name,
            days=getattr(args, "days", 30),
        )
        result = health.to_dict()
        if staleness:
            result["warning"] = staleness["warning"]
        return {"success": True, "command": "log_job_health", "data": result}
    except ValueError as e:
        return {"success": False, "command": "log_job_health", "error": str(e)}


def cmd_log_daily_summary(args: argparse.Namespace) -> dict:
    """L-05: Daily operational summary."""
    from backend.logs.analytics import LogAnalytics

    analytics = LogAnalytics(args.db_path)
    staleness = analytics.check_staleness()

    summary = analytics.daily_summary(
        date=getattr(args, "date", None),
    )

    result = summary.to_dict()
    if staleness:
        result["warning"] = staleness["warning"]
    return {"success": True, "command": "log_daily_summary", "data": result}


def cmd_triage_verify(args: argparse.Namespace) -> dict:
    """E-01: Verify email against existing jobs."""
    from backend.triage.analyzer import TriageAnalyzer
    from backend.db.deal_repo import DealRepository
    from backend.db.connection import create_connection

    deal_repo = None
    if args.db_mode and args.secrets_path:
        try:
            conn = create_connection(args.db_mode, args.secrets_path)
            deal_repo = DealRepository(conn)
        except Exception as e:
            logger.warning(f"DB connection failed, running without coverage check: {e}")

    try:
        analyzer = TriageAnalyzer(
            settings_path=args.settings_path,
            xml_type=getattr(args, "xml_type", "email"),
            deal_repo=deal_repo,
        )
        result = analyzer.verify(args.msg_path)
        return {"success": True, "command": "triage_verify", "data": result.to_dict()}
    except (FileNotFoundError, ValueError) as e:
        return {"success": False, "command": "triage_verify", "error": str(e)}


def cmd_triage_match(args: argparse.Namespace) -> dict:
    """E-02: Match email against job filters."""
    from backend.triage.analyzer import TriageAnalyzer

    try:
        analyzer = TriageAnalyzer(
            settings_path=args.settings_path,
            xml_type=getattr(args, "xml_type", "email"),
        )
        result = analyzer.match_only(
            msg_path=getattr(args, "msg_path", None),
            sender=getattr(args, "sender", None),
            subject=getattr(args, "subject", None),
        )
        return {"success": True, "command": "triage_match", "data": result.to_dict()}
    except (FileNotFoundError, ValueError) as e:
        return {"success": False, "command": "triage_match", "error": str(e)}


def cmd_triage_new(args: argparse.Namespace) -> dict:
    """E-03: No-match analysis with template suggestion."""
    from backend.triage.analyzer import TriageAnalyzer
    from backend.db.deal_repo import DealRepository
    from backend.db.connection import create_connection

    deal_repo = None
    if args.db_mode and args.secrets_path:
        try:
            conn = create_connection(args.db_mode, args.secrets_path)
            deal_repo = DealRepository(conn)
        except Exception as e:
            logger.warning(f"DB connection failed: {e}")

    try:
        analyzer = TriageAnalyzer(
            settings_path=args.settings_path,
            xml_type=getattr(args, "xml_type", "email"),
            deal_repo=deal_repo,
        )
        result = analyzer.analyze_new(args.msg_path)
        return {"success": True, "command": "triage_new", "data": result.to_dict()}
    except (FileNotFoundError, ValueError) as e:
        return {"success": False, "command": "triage_new", "error": str(e)}


# ─── Argparse Additions ──────────────────────────────────────────

def add_phase3_commands(subparsers):
    """Register Phase 3 CLI commands."""

    # L-02
    p = subparsers.add_parser("log_deal_activity")
    p.add_argument("--did", required=True, help="DID identifier (name or number)")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--db-path", default="frp_logs.db")
    p.add_argument("--db-mode", default=None)
    p.add_argument("--secrets-path", default=None)
    p.set_defaults(func=cmd_log_deal_activity)

    # L-03
    p = subparsers.add_parser("log_did_failures")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--job-filter", default=None)
    p.add_argument("--db-path", default="frp_logs.db")
    p.set_defaults(func=cmd_log_did_failures)

    # L-04
    p = subparsers.add_parser("log_job_health")
    p.add_argument("--job-name", required=True)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--db-path", default="frp_logs.db")
    p.set_defaults(func=cmd_log_job_health)

    # L-05
    p = subparsers.add_parser("log_daily_summary")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--db-path", default="frp_logs.db")
    p.set_defaults(func=cmd_log_daily_summary)

    # E-01
    p = subparsers.add_parser("triage_verify")
    p.add_argument("--msg-path", required=True)
    p.add_argument("--settings-path", required=True)
    p.add_argument("--xml-type", default="email")
    p.add_argument("--db-mode", default=None)
    p.add_argument("--secrets-path", default=None)
    p.set_defaults(func=cmd_triage_verify)

    # E-02
    p = subparsers.add_parser("triage_match")
    p.add_argument("--msg-path", default=None)
    p.add_argument("--sender", default=None)
    p.add_argument("--subject", default=None)
    p.add_argument("--settings-path", required=True)
    p.add_argument("--xml-type", default="email")
    p.set_defaults(func=cmd_triage_match)

    # E-03
    p = subparsers.add_parser("triage_new")
    p.add_argument("--msg-path", required=True)
    p.add_argument("--settings-path", required=True)
    p.add_argument("--xml-type", default="email")
    p.add_argument("--db-mode", default=None)
    p.add_argument("--secrets-path", default=None)
    p.set_defaults(func=cmd_triage_new)
```

---

## 9. Extension Handler Contracts

### /logs Handler — Phase 3 Additions (participant.js)

```javascript
// Expanded COMMAND_HANDLERS['/logs'] subcommand routing

async function handleLogs(userMessage, stream, token) {
    const parts = userMessage.trim().split(/\s+/);
    const sub = parts[0]?.toLowerCase();

    switch (sub) {
        case 'sync':
            // Phase 1 — unchanged
            return await handleLogSync(parts.slice(1), stream, token);

        case 'deal': {
            // L-02: @frp /logs deal CSFB 2006-HEAT5
            const did = parts.slice(1).join(' ');
            const days = extractDays(userMessage) || 30;
            const data = await backendCall('log_deal_activity', {
                did, days,
                db_path: config.logDbPath(),
                db_mode: config.dbMode(),
                secrets_path: config.secretsPath(),
            });
            return await generateResponse(data, stream, token, 'Format as a timeline of deal activity');
        }

        case 'failures': {
            // L-03: @frp /logs failures --days 7
            const days = extractDays(userMessage) || 30;
            const jobFilter = extractJobFilter(userMessage);
            const data = await backendCall('log_did_failures', {
                days, job_filter: jobFilter,
                db_path: config.logDbPath(),
            });
            return await generateResponse(data, stream, token, 'Format as a failure summary table');
        }

        case 'health': {
            // L-04: @frp /logs health rptent
            const jobName = parts.slice(1).join(' ');
            const days = extractDays(userMessage) || 30;
            const data = await backendCall('log_job_health', {
                job_name: jobName, days,
                db_path: config.logDbPath(),
            });
            return await generateResponse(data, stream, token, 'Format as a health dashboard');
        }

        case 'summary': {
            // L-05: @frp /logs summary 2026-02-20
            const date = parts[1] || null;
            const data = await backendCall('log_daily_summary', {
                date,
                db_path: config.logDbPath(),
            });
            return await generateResponse(data, stream, token, 'Format as a daily operations dashboard');
        }

        default:
            // Natural language fallback for /logs
            return await handleLogNaturalLanguage(userMessage, stream, token);
    }
}
```

### /triage Handler (participant.js — new)

```javascript
async function handleTriage(userMessage, stream, token) {
    const parts = userMessage.trim().split(/\s+/);
    const sub = parts[0]?.toLowerCase();
    const msgPath = extractMsgPath(userMessage);

    switch (sub) {
        case 'verify': {
            // E-01: @frp /triage verify C:\inbox\email.msg
            if (!msgPath) {
                stream.markdown('Please provide a path to a .msg file.\n');
                return;
            }
            const data = await backendCall('triage_verify', {
                msg_path: msgPath,
                settings_path: config.outlookSettingsPath(),
                xml_type: 'email',
                db_mode: config.dbMode(),
                secrets_path: config.secretsPath(),
            });
            return await generateResponse(data, stream, token,
                'Format as an email verification report');
        }

        case 'match': {
            // E-02: @frp /triage match email.msg or --sender --subject
            const sender = extractFlag(userMessage, '--sender');
            const subject = extractFlag(userMessage, '--subject');
            const data = await backendCall('triage_match', {
                msg_path: msgPath,
                sender, subject,
                settings_path: config.outlookSettingsPath(),
                xml_type: 'email',
            });
            return await generateResponse(data, stream, token,
                'Format as a ranked match list');
        }

        case 'new': {
            // E-03: @frp /triage new email.msg
            if (!msgPath) {
                stream.markdown('Please provide a path to a .msg file.\n');
                return;
            }
            const data = await backendCall('triage_new', {
                msg_path: msgPath,
                settings_path: config.outlookSettingsPath(),
                xml_type: 'email',
                db_mode: config.dbMode(),
                secrets_path: config.secretsPath(),
            });
            return await generateResponse(data, stream, token,
                'Format as a new job recommendation with template suggestion');
        }

        default:
            stream.markdown('Usage: `/triage verify|match|new <path.msg>`\n');
    }
}


// Register in COMMAND_HANDLERS
const COMMAND_HANDLERS = {
    '/jobs':    handleJobs,     // Phase 1+2
    '/deals':   handleDeals,    // Phase 1+2
    '/logs':    handleLogs,     // Phase 1+3
    '/deploy':  handleDeploy,   // Phase 1+2
    '/triage':  handleTriage,   // Phase 3
    // '/analyze': Phase 4
};
```

### Stale Index Warning (Extension)

```javascript
// After receiving CLI response for /logs commands
async function generateResponse(data, stream, token, systemHint) {
    // Show staleness warning before results
    if (data?.data?.warning) {
        stream.markdown(`> ⚠️ ${data.data.warning}\n\n`);
    }
    
    // ... existing LLM generation code ...
}
```

---

## 10. Error Handling

### New Error Codes

| Code | Message | Trigger |
|------|---------|---------|
| LOG-001 | Log database not found | frp_logs.db doesn't exist |
| LOG-002 | Log database missing tables | Schema mismatch |
| LOG-003 | No jobs match '{name}' | Job health with invalid name |
| LOG-004 | Ambiguous job name | Job health matches 2+ jobs |
| MSG-001 | File not found: {path} | .msg file doesn't exist |
| MSG-002 | Unsupported file type | Non-.msg file |
| MSG-003 | Failed to parse .msg file | extract-msg error |
| TRIAGE-001 | Settings.xml parse failed | Can't load jobs for matching |

### Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| DB unavailable during triage verify | Skip DID coverage check, show matches only |
| SQLite index empty | Return error: "Run @frp /logs sync first" |
| .msg file unreadable | Return error with MSG-003 code |
| extract-msg not installed | Return clear install instruction |
| No matches found (verify) | Suggest /triage new |
| Ambiguous job name (health) | Return match list for user clarification |

---

## 11. File Manifest

### New Files

| File | Lines (est.) | Tests |
|------|-------------|-------|
| `backend/logs/models.py` | ~80 | 12 |
| `backend/logs/analytics.py` | ~250 | 32 |
| `backend/triage/__init__.py` | ~5 | — |
| `backend/triage/models.py` | ~90 | 15 |
| `backend/triage/msg_parser.py` | ~100 | 14 |
| `backend/triage/matcher.py` | ~150 | 18 |
| `backend/triage/analyzer.py` | ~180 | 16 |
| `cli/main.py` (additions) | ~200 | 14 |
| `extension/chat/participant.js` (additions) | ~200 | 12 manual |

### Changed Files

| File | Changes | Lines (est.) |
|------|---------|-------------|
| `backend/db/deal_repo.py` | +2 methods | ~50 |
| `backend/common/errors.py` | +8 error codes | ~20 |
| `cli/main.py` | +7 commands, +argparse | ~200 |
| `extension/chat/participant.js` | +2 handlers, follow-ups | ~200 |
| `extension/package.json` | +1 slash command (/triage) | ~10 |

### Totals

| Category | Lines | Tests |
|----------|-------|-------|
| New Python | ~855 | 107 |
| Changed Python | ~270 | — |
| New/Changed JS | ~210 | 12 (manual) |
| CLI additions | ~200 | 14 |
| **Total** | **~1,535** | **148** |

---

*Next document: [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)*
