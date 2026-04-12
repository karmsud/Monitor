"""Tests for Phase 2 additions to xml/models.py — JobTemplate, FieldChange, JobDiff, DiffResult, CrudResult."""
import pytest

from backend.xml.models import (
    CrudResult,
    DiffResult,
    FieldChange,
    JobDiff,
    JobTemplate,
)


class TestJobTemplate:

    def test_serialization(self):
        t = JobTemplate(
            pattern_name="ConditionalParser [ChecklistTemplate]",
            parser_names=["ConditionalParser"],
            template_names=["ChecklistTemplate"],
            mailbox_pattern="test@example.com",
            example_job_name="TestJob_Alpha",
            job_count=3,
            has_servicer_id=True,
            sample_fields={"mailbox": "test@example.com"},
        )
        d = t.to_dict()
        assert d["pattern_name"] == "ConditionalParser [ChecklistTemplate]"
        assert d["job_count"] == 3
        assert d["has_servicer_id"] is True
        assert "mailbox" in d["sample_fields"]


class TestFieldChange:

    def test_serialization(self):
        fc = FieldChange(field="servicer_id", old_value="100", new_value="200")
        d = fc.to_dict()
        assert d["field"] == "servicer_id"
        assert d["old_value"] == "100"
        assert d["new_value"] == "200"


class TestJobDiff:

    def test_added(self):
        jd = JobDiff(job_name="NewJob", change_type="added")
        d = jd.to_dict()
        assert d["change_type"] == "added"
        assert d["field_changes"] == []

    def test_modified(self):
        fc = FieldChange("servicer_id", "100", "200")
        jd = JobDiff(job_name="ExistingJob", change_type="modified", field_changes=[fc])
        d = jd.to_dict()
        assert d["change_type"] == "modified"
        assert len(d["field_changes"]) == 1
        assert d["field_changes"][0]["field"] == "servicer_id"


class TestDiffResult:

    def test_total_changes(self):
        dr = DiffResult(
            current_file="a.xml",
            backup_file="b.xml",
            added_jobs=[JobDiff("A", "added")],
            removed_jobs=[JobDiff("B", "removed"), JobDiff("C", "removed")],
            modified_jobs=[],
            unchanged_count=10,
        )
        assert dr.total_changes == 3

    def test_serialization(self):
        dr = DiffResult(
            current_file="current.xml",
            backup_file="backup.xml",
            unchanged_count=5,
            timestamp="2026-02-01T12:00:00",
        )
        d = dr.to_dict()
        assert d["current_file"] == "current.xml"
        assert d["unchanged_count"] == 5
        assert d["total_changes"] == 0
        assert d["timestamp"] == "2026-02-01T12:00:00"


class TestCrudResult:

    def test_serialization(self):
        fc = FieldChange("servicer_id", "", "225")
        cr = CrudResult(
            operation="create",
            job_name="NewJob",
            changes=[fc],
            backup_file="backup_20260201.xml",
            validation={"valid": True, "errors": []},
        )
        d = cr.to_dict()
        assert d["operation"] == "create"
        assert d["job_name"] == "NewJob"
        assert len(d["changes"]) == 1
        assert d["validation"]["valid"] is True
