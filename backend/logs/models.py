"""Data-class models for parsed log events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LogEvent:
    """A single parsed event extracted from an FRP log file."""

    log_file: str
    log_type: str
    timestamp: str
    job_name: Optional[str] = None
    mailbox: Optional[str] = None
    email_event_id: Optional[str] = None
    email_event_index: Optional[int] = None
    event_type: str = ""
    emails_found: Optional[int] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    parser: Optional[str] = None
    filename: Optional[str] = None
    template: Optional[str] = None
    error_message: Optional[str] = None
    raw_line: Optional[str] = None

    # -- helpers ---------------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for JSON serialisation."""
        return asdict(self)


# --------------------------------------------------------------------------- #
#  Phase 3: Log analytics models
# --------------------------------------------------------------------------- #

@dataclass
class DealActivity:
    """A single deal-related event from the log index."""

    timestamp: str
    job_name: str
    event_type: str
    detail: str
    log_file: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DIDFailure:
    """Aggregated DID-mapping-failure statistics."""

    import_did: str
    failure_count: int
    affected_jobs: list
    first_seen: str
    last_seen: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JobHealth:
    """Health metrics for a single job over a time window."""

    job_name: str
    total_runs: int
    successful_runs: int
    error_count: int
    success_rate: float  # 0.0-100.0
    status: str  # "healthy"|"warning"|"critical"
    last_run: Optional[str]
    last_error: Optional[str]
    avg_emails_per_run: float
    common_errors: list = field(default_factory=list)
    date_range: str = "Last 30 days"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailySummary:
    """One-day operational summary."""

    date: str
    total_jobs_run: int
    total_emails_processed: int
    total_files_loaded: int
    total_errors: int
    total_did_failures: int
    top_jobs_by_volume: list = field(default_factory=list)
    top_error_sources: list = field(default_factory=list)
    comparison: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
