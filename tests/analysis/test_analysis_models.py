"""Tests for backend.analysis.models — 25 tests covering all 12 dataclasses."""

import pytest
from dataclasses import asdict

from backend.analysis.models import (
    TrendDay,
    TrendSummary,
    PerformanceEntry,
    PerformanceSummary,
    ConsolidationCandidate,
    ConsolidationGroup,
    ConsolidationReport,
    ChangeSpec,
    AffectedEntity,
    ImpactReport,
    HealthSection,
    HealthReport,
)


# ─── TrendDay ────────────────────────────────────────────────────────

class TestTrendDay:
    def test_defaults(self):
        td = TrendDay(date="2025-02-01")
        assert td.date == "2025-02-01"
        assert td.total_files == 0
        assert td.total_errors == 0
        assert td.did_failures == 0
        assert td.job_runs == 0
        assert td.trend_files == "→"
        assert td.trend_errors == "→"

    def test_custom_values(self):
        td = TrendDay(date="2025-02-01", total_files=10, total_errors=2, did_failures=1, job_runs=5)
        assert td.total_files == 10
        assert td.total_errors == 2

    def test_to_dict(self):
        td = TrendDay(date="2025-02-01", total_files=5, trend_files="↑")
        d = td.to_dict()
        assert isinstance(d, dict)
        assert d["date"] == "2025-02-01"
        assert d["total_files"] == 5
        assert d["trend_files"] == "↑"


# ─── TrendSummary ────────────────────────────────────────────────────

class TestTrendSummary:
    def test_defaults(self):
        ts = TrendSummary()
        assert ts.days == []
        assert ts.period_start == ""
        assert ts.period_end == ""
        assert ts.period_days == 0
        assert ts.totals == {}
        assert ts.avg_files_per_day == 0.0
        assert ts.vs_previous_period == {}
        assert ts.worst_day is None
        assert ts.best_day is None
        assert ts.staleness_warning is None
        assert ts.job_filter is None

    def test_to_dict_with_trend_days(self):
        day1 = TrendDay(date="2025-02-01", total_files=10)
        day2 = TrendDay(date="2025-02-02", total_files=20)
        ts = TrendSummary(
            days=[day1, day2],
            period_start="2025-02-01",
            period_end="2025-02-02",
            period_days=2,
            totals={"total_files": 30},
            avg_files_per_day=15.0,
        )
        d = ts.to_dict()
        assert len(d["days"]) == 2
        assert d["days"][0]["total_files"] == 10
        assert d["avg_files_per_day"] == 15.0


# ─── PerformanceEntry ────────────────────────────────────────────────

class TestPerformanceEntry:
    def test_defaults(self):
        pe = PerformanceEntry()
        assert pe.job_name == ""
        assert pe.job_type == "unknown"
        assert pe.total_runs == 0
        assert pe.success_rate == 100.0
        assert pe.status == "unknown"
        assert pe.common_errors == []
        assert pe.rank == 0

    def test_to_dict(self):
        pe = PerformanceEntry(job_name="Ocwen", success_rate=95.5, status="healthy", rank=1)
        d = pe.to_dict()
        assert d["job_name"] == "Ocwen"
        assert d["success_rate"] == 95.5
        assert d["rank"] == 1


# ─── PerformanceSummary ──────────────────────────────────────────────

class TestPerformanceSummary:
    def test_defaults(self):
        ps = PerformanceSummary()
        assert ps.entries == []
        assert ps.total_jobs == 0
        assert ps.healthy_count == 0
        assert ps.avg_success_rate == 100.0
        assert ps.sort_key == "success_rate"
        assert ps.period_days == 30
        assert ps.staleness_warning is None

    def test_to_dict_with_entries(self):
        e1 = PerformanceEntry(job_name="Ocwen", rank=1)
        e2 = PerformanceEntry(job_name="PHH", rank=2)
        ps = PerformanceSummary(entries=[e1, e2], total_jobs=2, healthy_count=2)
        d = ps.to_dict()
        assert len(d["entries"]) == 2
        assert d["entries"][0]["job_name"] == "Ocwen"


# ─── ConsolidationCandidate ─────────────────────────────────────────

class TestConsolidationCandidate:
    def test_defaults(self):
        cc = ConsolidationCandidate()
        assert cc.name == ""
        assert cc.servicer_id is None
        assert cc.did_count == 0
        assert cc.unique_attributes == {}

    def test_to_dict(self):
        cc = ConsolidationCandidate(name="Ocwen", servicer_id="100", did_count=5,
                                     unique_attributes={"SenderFilter": "ocwen@bank.com"})
        d = cc.to_dict()
        assert d["name"] == "Ocwen"
        assert d["unique_attributes"]["SenderFilter"] == "ocwen@bank.com"


# ─── ConsolidationGroup ─────────────────────────────────────────────

class TestConsolidationGroup:
    def test_defaults(self):
        cg = ConsolidationGroup()
        assert cg.group_id == 0
        assert cg.shared_mailbox == ""
        assert cg.jobs == []
        assert cg.merge_recommendation == "review"

    def test_to_dict_with_candidates(self):
        c1 = ConsolidationCandidate(name="Ocwen")
        c2 = ConsolidationCandidate(name="PHH")
        cg = ConsolidationGroup(group_id=1, shared_mailbox="inbox@bank.com",
                                 jobs=[c1, c2], total_dids_affected=10)
        d = cg.to_dict()
        assert d["group_id"] == 1
        assert len(d["jobs"]) == 2


# ─── ConsolidationReport ────────────────────────────────────────────

class TestConsolidationReport:
    def test_defaults(self):
        cr = ConsolidationReport()
        assert cr.groups == []
        assert cr.total_groups == 0
        assert cr.xml_type_analyzed == "all"

    def test_to_dict(self):
        g = ConsolidationGroup(group_id=1, jobs=[ConsolidationCandidate(name="A")])
        cr = ConsolidationReport(groups=[g], total_groups=1, total_jobs_affected=1)
        d = cr.to_dict()
        assert d["total_groups"] == 1


# ─── ChangeSpec ──────────────────────────────────────────────────────

class TestChangeSpec:
    def test_defaults(self):
        cs = ChangeSpec()
        assert cs.change_type == ""
        assert cs.target_job is None
        assert cs.target_did is None
        assert cs.target_company_id is None
        assert cs.new_value is None
        assert cs.raw_description == ""

    def test_from_dict(self):
        data = {
            "change_type": "delete_job",
            "target_job": "Ocwen",
            "raw_description": "Remove old job",
        }
        cs = ChangeSpec.from_dict(data)
        assert cs.change_type == "delete_job"
        assert cs.target_job == "Ocwen"
        assert cs.raw_description == "Remove old job"
        assert cs.target_did is None

    def test_from_dict_empty(self):
        cs = ChangeSpec.from_dict({})
        assert cs.change_type == ""
        assert cs.target_job is None

    def test_to_dict(self):
        cs = ChangeSpec(change_type="rename_did", target_did="DID001", new_value="DID999")
        d = cs.to_dict()
        assert d["change_type"] == "rename_did"
        assert d["target_did"] == "DID001"
        assert d["new_value"] == "DID999"

    def test_from_dict_roundtrip(self):
        original = ChangeSpec(change_type="move_servicer", target_job="BSI",
                              target_company_id=103, new_value="NewJob")
        d = original.to_dict()
        restored = ChangeSpec.from_dict(d)
        assert restored.change_type == original.change_type
        assert restored.target_job == original.target_job
        assert restored.target_company_id == original.target_company_id
        assert restored.new_value == original.new_value


# ─── AffectedEntity ─────────────────────────────────────────────────

class TestAffectedEntity:
    def test_defaults(self):
        ae = AffectedEntity()
        assert ae.entity_type == ""
        assert ae.identifier == ""
        assert ae.detail == ""
        assert ae.severity == "medium"

    def test_to_dict(self):
        ae = AffectedEntity(entity_type="deal", identifier="DID001",
                             detail="Would lose coverage", severity="high")
        d = ae.to_dict()
        assert d["entity_type"] == "deal"
        assert d["severity"] == "high"


# ─── ImpactReport ───────────────────────────────────────────────────

class TestImpactReport:
    def test_defaults(self):
        ir = ImpactReport()
        assert ir.change is None
        assert ir.affected == []
        assert ir.coverage_before == 0
        assert ir.coverage_after == 0
        assert ir.coverage_delta == 0
        assert ir.recent_activity is False
        assert ir.risk_level == "low"

    def test_to_dict_with_change(self):
        cs = ChangeSpec(change_type="delete_job", target_job="Ocwen")
        ae = AffectedEntity(entity_type="deal", identifier="DID000", severity="high")
        ir = ImpactReport(change=cs, affected=[ae], coverage_before=5, risk_level="high")
        d = ir.to_dict()
        assert d["change"]["change_type"] == "delete_job"
        assert len(d["affected"]) == 1
        assert d["risk_level"] == "high"


# ─── HealthSection ──────────────────────────────────────────────────

class TestHealthSection:
    def test_defaults(self):
        hs = HealthSection()
        assert hs.name == ""
        assert hs.status == "pass"
        assert hs.score == 100.0
        assert hs.weight == 0.0
        assert hs.summary == ""
        assert hs.details == {}
        assert hs.action_items == []

    def test_to_dict(self):
        hs = HealthSection(name="XML Validation", status="warning", score=75.0,
                            weight=0.15, summary="2 errors", action_items=["Fix errors"])
        d = hs.to_dict()
        assert d["name"] == "XML Validation"
        assert d["score"] == 75.0
        assert len(d["action_items"]) == 1


# ─── HealthReport ───────────────────────────────────────────────────

class TestHealthReport:
    def test_defaults(self):
        hr = HealthReport()
        assert hr.sections == []
        assert hr.overall_score == 0.0
        assert hr.overall_status == "Healthy"
        assert hr.generated_at == ""
        assert hr.xml_type == "all"

    def test_to_dict_with_sections(self):
        s1 = HealthSection(name="Coverage", score=90.0, weight=0.2)
        s2 = HealthSection(name="Performance", score=80.0, weight=0.15)
        hr = HealthReport(sections=[s1, s2], overall_score=85.0,
                           overall_status="Attention Needed")
        d = hr.to_dict()
        assert len(d["sections"]) == 2
        assert d["overall_score"] == 85.0
        assert d["overall_status"] == "Attention Needed"
