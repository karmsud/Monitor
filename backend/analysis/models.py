"""Phase 4 data models — pure dataclasses, no external dependencies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ─── L-06 Trend Models ───────────────────────────────────────────────────

@dataclass
class TrendDay:
    """One day's aggregated metrics."""
    date: str
    total_files: int = 0
    total_errors: int = 0
    did_failures: int = 0
    job_runs: int = 0
    trend_files: str = "→"     # ↑ / ↓ / →
    trend_errors: str = "→"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrendSummary:
    """Complete output of TrendAnalyzer.analyze()."""
    days: List[TrendDay] = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""
    period_days: int = 0
    totals: Dict[str, int] = field(default_factory=dict)
    avg_files_per_day: float = 0.0
    vs_previous_period: Dict[str, Any] = field(default_factory=dict)
    worst_day: Optional[str] = None
    best_day: Optional[str] = None
    staleness_warning: Optional[str] = None
    job_filter: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["days"] = [day.to_dict() if isinstance(day, TrendDay) else day for day in self.days]
        return d


# ─── L-07 Performance Models ─────────────────────────────────────────────

@dataclass
class PerformanceEntry:
    """One job's performance metrics."""
    job_name: str = ""
    job_type: str = "unknown"
    total_runs: int = 0
    total_files: int = 0
    total_errors: int = 0
    success_rate: float = 100.0
    avg_files_per_run: float = 0.0
    last_run: Optional[str] = None
    status: str = "unknown"       # healthy / warning / critical / unknown
    common_errors: List[str] = field(default_factory=list)
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceSummary:
    """Complete output of PerformanceBenchmarker.benchmark()."""
    entries: List[PerformanceEntry] = field(default_factory=list)
    total_jobs: int = 0
    healthy_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    unknown_count: int = 0
    avg_success_rate: float = 100.0
    sort_key: str = "success_rate"
    period_days: int = 30
    staleness_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["entries"] = [
            e.to_dict() if isinstance(e, PerformanceEntry) else e
            for e in self.entries
        ]
        return d


# ─── A-01 Consolidation Models ───────────────────────────────────────────

@dataclass
class ConsolidationCandidate:
    """One job within a consolidation group."""
    name: str = ""
    servicer_id: Optional[str] = None
    did_count: int = 0
    unique_attributes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConsolidationGroup:
    """A group of jobs sharing the same core configuration."""
    group_id: int = 0
    shared_mailbox: str = ""
    shared_parser: str = ""
    shared_template: str = ""
    jobs: List[ConsolidationCandidate] = field(default_factory=list)
    total_dids_affected: int = 0
    merge_recommendation: str = "review"  # safe / review / risky
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["jobs"] = [
            j.to_dict() if isinstance(j, ConsolidationCandidate) else j
            for j in self.jobs
        ]
        return d


@dataclass
class ConsolidationReport:
    """Complete output of ConsolidationAnalyzer.analyze()."""
    groups: List[ConsolidationGroup] = field(default_factory=list)
    total_groups: int = 0
    total_jobs_affected: int = 0
    total_dids_affected: int = 0
    xml_type_analyzed: str = "all"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["groups"] = [
            g.to_dict() if isinstance(g, ConsolidationGroup) else g
            for g in self.groups
        ]
        return d


# ─── A-02 Impact Models ──────────────────────────────────────────────────

@dataclass
class ChangeSpec:
    """Describes a proposed configuration change."""
    change_type: str = ""       # delete_job / rename_did / change_filter / move_servicer
    target_job: Optional[str] = None
    target_did: Optional[str] = None
    target_company_id: Optional[int] = None
    new_value: Optional[str] = None
    raw_description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeSpec":
        return cls(
            change_type=data.get("change_type", ""),
            target_job=data.get("target_job"),
            target_did=data.get("target_did"),
            target_company_id=data.get("target_company_id"),
            new_value=data.get("new_value"),
            raw_description=data.get("raw_description", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AffectedEntity:
    """One entity impacted by a proposed change."""
    entity_type: str = ""       # deal / job / did_mapping
    identifier: str = ""
    detail: str = ""
    severity: str = "medium"    # high / medium / low

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImpactReport:
    """Complete output of ImpactSimulator.simulate()."""
    change: Optional[ChangeSpec] = None
    affected: List[AffectedEntity] = field(default_factory=list)
    coverage_before: int = 0
    coverage_after: int = 0
    coverage_delta: int = 0
    recent_activity: bool = False
    risk_level: str = "low"      # low / medium / high
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.change:
            d["change"] = self.change.to_dict()
        d["affected"] = [
            a.to_dict() if isinstance(a, AffectedEntity) else a
            for a in self.affected
        ]
        return d


# ─── A-03 Health Models ──────────────────────────────────────────────────

@dataclass
class HealthSection:
    """One section of the health report."""
    name: str = ""
    status: str = "pass"         # pass / warning / fail
    score: float = 100.0         # 0–100
    weight: float = 0.0          # 0–1
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    action_items: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    """Complete output of HealthChecker.check()."""
    sections: List[HealthSection] = field(default_factory=list)
    overall_score: float = 0.0
    overall_status: str = "Healthy"  # Healthy / Attention Needed / Action Required
    generated_at: str = ""
    xml_type: str = "all"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sections"] = [
            s.to_dict() if isinstance(s, HealthSection) else s
            for s in self.sections
        ]
        return d
