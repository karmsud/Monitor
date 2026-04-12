"""Tests for Phase 2 intel models — CoverageReport, OrphanResult, CollisionResult, IntelSummary."""
import pytest

from backend.intel.models import (
    CoverageReport,
    CollisionResult,
    IntelSummary,
    OrphanResult,
)


class TestCoverageReport:

    def test_serialization(self):
        r = CoverageReport(
            servicer_id=100,
            total_dids=10,
            mapped_dids=7,
            unmapped_dids=[{"did": 3, "import_did": "XYZ"}],
            coverage_percentage=70.0,
            matching_jobs=["Job_A"],
        )
        d = r.to_dict()
        assert d["servicer_id"] == 100
        assert d["total_dids"] == 10
        assert d["mapped_dids"] == 7
        assert d["coverage_percentage"] == 70.0
        assert len(d["unmapped_dids"]) == 1
        assert d["matching_jobs"] == ["Job_A"]

    def test_zero_dids(self):
        r = CoverageReport(
            servicer_id=999,
            total_dids=0,
            mapped_dids=0,
            unmapped_dids=[],
            coverage_percentage=0.0,
            matching_jobs=[],
        )
        assert r.coverage_percentage == 0.0


class TestOrphanResult:

    def test_serialization(self):
        o = OrphanResult(
            job_name="Orphan_Job",
            servicer_id=999,
            reason="no_db_match",
            xml_type="email",
        )
        d = o.to_dict()
        assert d["job_name"] == "Orphan_Job"
        assert d["servicer_id"] == 999
        assert d["reason"] == "no_db_match"
        assert d["xml_type"] == "email"


class TestCollisionResult:

    def test_serialization_high_risk(self):
        c = CollisionResult(
            import_did_keyword="OVERLAP",
            matching_company_ids=[100, 150, 200],
            affected_jobs=["Job_A", "Job_B"],
            risk_level="high",
            deal_counts={100: 5, 150: 3, 200: 1},
        )
        d = c.to_dict()
        assert d["import_did_keyword"] == "OVERLAP"
        assert len(d["matching_company_ids"]) == 3
        assert d["risk_level"] == "high"

    def test_risk_medium(self):
        c = CollisionResult(
            import_did_keyword="PARTIAL",
            matching_company_ids=[100, 150],
            affected_jobs=["Job_A"],
            risk_level="medium",
            deal_counts={100: 2, 150: 4},
        )
        assert c.risk_level == "medium"


class TestIntelSummary:

    def test_aggregation(self):
        cr = CoverageReport(100, 10, 7, [], 70.0, ["J1"])
        orphan = OrphanResult("Orphan_Job", 999, "no_db_match", "email")
        collision = CollisionResult("KEY", [1, 2], ["J_A"], "medium", {1: 1, 2: 1})

        summary = IntelSummary(
            total_jobs_scanned=5,
            jobs_with_servicer=3,
            jobs_without_servicer=2,
            coverage_reports=[cr],
            orphans=[orphan],
            collisions=[collision],
        )
        d = summary.to_dict()
        assert d["total_jobs_scanned"] == 5
        assert len(d["coverage_reports"]) == 1
        assert len(d["orphans"]) == 1
        assert len(d["collisions"]) == 1
