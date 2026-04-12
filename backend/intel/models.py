"""Data-class models for intelligence analysis results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class CoverageReport:
    """Coverage analysis result for a single servicer/company."""

    servicer_id: int
    total_dids: int
    mapped_dids: int
    unmapped_dids: list  # [{ "did": int, "import_did": str }]
    coverage_percentage: float
    matching_jobs: list  # [str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OrphanResult:
    """A job that appears orphaned (no valid DB match)."""

    job_name: str
    servicer_id: int
    reason: str  # "no_db_match" | "no_deal_data" | "invalid_servicer_id"
    xml_type: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CollisionResult:
    """An ImportDID keyword that maps to multiple companies."""

    import_did_keyword: str
    matching_company_ids: list  # [int]
    affected_jobs: list  # [str]
    risk_level: str  # "high" | "medium"
    deal_counts: dict  # { company_id: count }

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IntelSummary:
    """Aggregated summary of all intelligence analysis."""

    total_jobs_scanned: int
    jobs_with_servicer: int
    jobs_without_servicer: int
    coverage_reports: list = field(default_factory=list)
    orphans: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_jobs_scanned": self.total_jobs_scanned,
            "jobs_with_servicer": self.jobs_with_servicer,
            "jobs_without_servicer": self.jobs_without_servicer,
            "coverage_reports": [r.to_dict() for r in self.coverage_reports],
            "orphans": [o.to_dict() for o in self.orphans],
            "collisions": [c.to_dict() for c in self.collisions],
            "errors": self.errors,
        }
