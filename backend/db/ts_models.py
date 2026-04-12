"""Dataclass models for tblTemplateStaging use cases.

These models are returned by :class:`TemplateStagingRepository` methods
introduced in Phase 5.  Each one represents a structured analysis
result rather than a raw database row.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional


# ------------------------------------------------------------------ #
# Single-row model
# ------------------------------------------------------------------ #


@dataclass
class TemplateRun:
    """One processing run from tblTemplateStaging."""

    template_process_id: int
    template_name: str
    file_path: Optional[str] = None
    did: Optional[str] = None
    dt: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result_code: Optional[int] = None
    comments: Optional[str] = None
    servicer_id: Optional[int] = None
    source_process: Optional[str] = None
    job: Optional[str] = None
    data_source: Optional[str] = None
    machine: Optional[str] = None
    user_name: Optional[str] = None
    duration_seconds: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.result_code == 0

    @property
    def source_type(self) -> str:
        """Parse DataSource to determine origin type."""
        ds = (self.data_source or "").strip()
        if not ds:
            return "unknown"
        if "SFTPMonitor:" in ds:
            return "sftp"
        if "Queued via macro" in ds or "ManualQueue" in (self.source_process or ""):
            return "manual"
        # Default to email for anything else with content
        return "email"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["success"] = self.success
        d["source_type"] = self.source_type
        # Convert datetimes to ISO strings for JSON serialisation
        for key in ("start_time", "end_time"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = val.isoformat()
        return d

    @classmethod
    def from_row(cls, row: Dict) -> "TemplateRun":
        """Construct from a column-keyed dict (as returned by repo helpers)."""
        duration = None
        st = row.get("StartTime")
        et = row.get("EndTime")
        if st and et:
            try:
                if not isinstance(st, datetime):
                    st = datetime.fromisoformat(str(st))
                if not isinstance(et, datetime):
                    et = datetime.fromisoformat(str(et))
                duration = (et - st).total_seconds()
            except (ValueError, TypeError):
                pass

        return cls(
            template_process_id=row.get("TemplateProcessID", 0),
            template_name=row.get("TemplateName", ""),
            file_path=row.get("FilePath"),
            did=row.get("DID"),
            dt=str(row["Dt"]) if row.get("Dt") else None,
            start_time=st if isinstance(st, datetime) else None,
            end_time=et if isinstance(et, datetime) else None,
            result_code=row.get("ResultCode"),
            comments=row.get("Comments"),
            servicer_id=row.get("ServicerID"),
            source_process=row.get("SourceProcess"),
            job=row.get("Job"),
            data_source=row.get("DataSource"),
            machine=row.get("Machine"),
            user_name=row.get("UserName"),
            duration_seconds=duration,
        )


# ------------------------------------------------------------------ #
# Summary / analytics models
# ------------------------------------------------------------------ #


@dataclass
class TemplateSummary:
    """Aggregate stats for a query scope (template, DID, or global)."""

    scope: str  # what was queried (template name, DID, etc.)
    total_runs: int = 0
    successes: int = 0
    failures: int = 0
    success_rate: float = 0.0
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    recent_runs: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FailureGroup:
    """A group of failures sharing a common error pattern."""

    pattern: str
    count: int = 0
    templates: List[str] = field(default_factory=list)
    dids: List[str] = field(default_factory=list)
    sample_comment: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FailureSummary:
    """Complete failure analysis result."""

    total_failures: int = 0
    period_days: int = 30
    top_templates: List[Dict] = field(default_factory=list)
    top_dids: List[Dict] = field(default_factory=list)
    error_groups: List[Dict] = field(default_factory=list)
    affected_servicers: List[int] = field(default_factory=list)
    failures: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DurationStats:
    """Processing duration statistics for a template."""

    template_name: str
    total_runs: int = 0
    avg_seconds: float = 0.0
    min_seconds: float = 0.0
    max_seconds: float = 0.0
    p95_seconds: float = 0.0
    outliers: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ManualQueueReport:
    """Manual vs automated processing breakdown."""

    automated_count: int = 0
    manual_count: int = 0
    total_count: int = 0
    manual_percentage: float = 0.0
    top_manual_templates: List[Dict] = field(default_factory=list)
    top_manual_dids: List[Dict] = field(default_factory=list)
    manual_operators: List[Dict] = field(default_factory=list)
    period_days: int = 30

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SourceTraceResult:
    """Result of tracing a file's origin through the processing pipeline."""

    file_path: str
    source_type: str  # email / sftp / manual / unknown
    data_source_raw: Optional[str] = None
    source_process: Optional[str] = None
    template_name: Optional[str] = None
    did: Optional[str] = None
    result_code: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    comments: Optional[str] = None
    job_config: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PipelineLayer:
    """One layer of a pipeline status view."""

    name: str  # "config" / "mapping" / "execution"
    status: str  # "ok" / "warning" / "missing"
    items: List[Dict] = field(default_factory=list)
    count: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PipelineStatus:
    """End-to-end pipeline visibility for a deal or servicer."""

    query: str
    config_layer: Optional[Dict] = None
    mapping_layer: Optional[Dict] = None
    execution_layer: Optional[Dict] = None
    gaps: List[str] = field(default_factory=list)
    health_score: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)
