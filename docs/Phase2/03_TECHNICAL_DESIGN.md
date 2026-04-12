# Phase 2: Technical Design
## FRP Agent — CRUD & Intelligence Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Prerequisite:** Phase 1 Technical Design (Phase1/03_TECHNICAL_DESIGN.md)

---

## Table of Contents
1. [Overview](#1-overview)
2. [New Python Data Models](#2-new-python-data-models)
3. [Job CRUD Engine — backend/xml/crud.py](#3-job-crud-engine)
4. [Template Inventory — backend/xml/templates.py](#4-template-inventory)
5. [Coverage Gap Analysis — backend/intel/coverage.py](#5-coverage-gap-analysis)
6. [Orphan Detection — backend/intel/orphans.py](#6-orphan-detection)
7. [ImportDID Collision Detection — backend/intel/collisions.py](#7-collision-detection)
8. [XML Diff Engine — backend/xml/diff.py](#8-xml-diff-engine)
9. [Rollback Handler — backend/xml/rollback.py](#9-rollback-handler)
10. [CLI Command Additions — cli/main.py](#10-cli-command-additions)
11. [Extension Handler Updates](#11-extension-handler-updates)
12. [DB Repository Additions](#12-db-repository-additions)
13. [Error Handling Strategy](#13-error-handling-strategy)
14. [File Manifest](#14-file-manifest)

---

## 1. Overview

Phase 2 adds **8 new backend modules** (6 Python files, 2 enhanced files) and **8 new CLI commands**. All new modules depend on Phase 1 foundations and follow the same patterns: dataclass models, JSON serialization, CliResponse envelope.

### New Files

| File | Purpose | Estimated Lines |
|------|---------|----------------|
| `backend/xml/crud.py` | Job create/edit engine | ~250 |
| `backend/xml/templates.py` | Template pattern discovery | ~120 |
| `backend/xml/diff.py` | Job-level XML comparison | ~150 |
| `backend/xml/rollback.py` | Rollback with safety backup | ~80 |
| `backend/intel/__init__.py` | Module init | ~5 |
| `backend/intel/models.py` | Intel data models | ~130 |
| `backend/intel/coverage.py` | Coverage gap analysis | ~150 |
| `backend/intel/orphans.py` | Orphan detection | ~100 |
| `backend/intel/collisions.py` | ImportDID collision detection | ~120 |

### Modified Files

| File | Changes |
|------|---------|
| `cli/main.py` | Add 8 new subcommands |
| `backend/db/deal_repo.py` | Add 4 new query methods |
| `backend/db/queries.py` | Add 4 new SQL constants |
| `extension/chat/participant.js` | Add subcommand handlers for create/edit/templates/gaps/orphans/collisions/diff/rollback |
| `extension/copilot/tool.js` | Add new param mappings |

### Total Estimated Lines (Phase 2 new code): ~1,400 Python + ~400 JS = ~1,800

---

## 2. New Python Data Models

### backend/xml/models.py — Additions to Existing File

```python
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class JobTemplate:
    """A discovered template pattern from existing jobs."""
    pattern_name: str
    parser_names: list[str]
    template_names: list[str]
    mailbox_pattern: str
    example_job_name: str
    job_count: int
    has_servicer_id: bool
    sample_fields: dict

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class FieldChange:
    """A single field change in a job."""
    field: str
    old_value: str
    new_value: str

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class JobDiff:
    """Diff of a single job between two XML versions."""
    job_name: str
    change_type: str        # "added" | "removed" | "modified"
    field_changes: list[FieldChange] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_name": self.job_name,
            "change_type": self.change_type,
            "field_changes": [fc.to_dict() for fc in self.field_changes],
        }

@dataclass
class DiffResult:
    """Complete diff between current Settings.xml and a backup."""
    current_file: str
    backup_file: str
    added_jobs: list[JobDiff] = field(default_factory=list)
    removed_jobs: list[JobDiff] = field(default_factory=list)
    modified_jobs: list[JobDiff] = field(default_factory=list)
    unchanged_count: int = 0
    timestamp: str = ""

    @property
    def total_changes(self) -> int:
        return len(self.added_jobs) + len(self.removed_jobs) + len(self.modified_jobs)

    def to_dict(self) -> dict:
        return {
            "current_file": self.current_file,
            "backup_file": self.backup_file,
            "added": [j.to_dict() for j in self.added_jobs],
            "removed": [j.to_dict() for j in self.removed_jobs],
            "modified": [j.to_dict() for j in self.modified_jobs],
            "unchanged_count": self.unchanged_count,
            "total_changes": self.total_changes,
            "timestamp": self.timestamp,
        }

@dataclass
class CrudResult:
    """Result of a create or edit operation."""
    operation: str              # "create" | "edit"
    job_name: str
    changes: list[FieldChange] = field(default_factory=list)
    backup_file: str = ""
    validation: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "job_name": self.job_name,
            "changes": [c.to_dict() for c in self.changes],
            "backup_file": self.backup_file,
            "validation": self.validation,
        }
```

### backend/intel/models.py — New File (Complete)

```python
"""Data models for coverage intelligence analysis."""

from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class CoverageReport:
    """Coverage gap analysis for a single servicer."""
    servicer_id: int
    total_dids: int
    mapped_dids: int
    unmapped_dids: list[dict]    # [{ "did": int, "import_did": str }]
    coverage_percentage: float
    matching_jobs: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class OrphanResult:
    """A job with a ServicerID that has no matching DB records."""
    job_name: str
    servicer_id: int
    reason: str                  # "no_db_match" | "no_deal_data"
    xml_type: str                # "email" | "sftp"

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class CollisionResult:
    """An ImportDID keyword matching multiple CompanyIDs."""
    import_did_keyword: str
    matching_company_ids: list[int]
    affected_jobs: list[str]
    risk_level: str              # "high" (3+) | "medium" (2)
    deal_counts: dict            # { company_id: count }

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class IntelSummary:
    """Aggregate summary from intel analysis operations."""
    total_jobs_scanned: int
    jobs_with_servicer: int
    jobs_without_servicer: int
    coverage_reports: list[CoverageReport] = field(default_factory=list)
    orphans: list[OrphanResult] = field(default_factory=list)
    collisions: list[CollisionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
```

---

## 3. Job CRUD Engine — backend/xml/crud.py

```python
"""Job creation and editing engine for Settings.xml."""

import copy
import logging
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from backend.xml.parser import SettingsXmlParser
from backend.xml.writer import XmlWriter
from backend.xml.models import EmailJob, SftpJob, CrudResult, FieldChange, ValidationResult

logger = logging.getLogger(__name__)

# Fields that can be edited, mapped to XML element paths
EMAIL_FIELD_MAP = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "mailbox": "MailboxAddress",
    "import_did": "ImportDID",
    "subject_filter": "SubjectFilter",
    "sender_filter": "SenderFilter",
    "active": "Active",
}

SFTP_FIELD_MAP = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "path": "RemotePath",
    "import_did": "ImportDID",
    "file_pattern": "FilePattern",
    "active": "Active",
}


class JobCrudEngine:
    """Create and edit jobs in Settings.xml."""

    def __init__(self, settings_path: str, xml_type: str = "email"):
        """
        Args:
            settings_path: Absolute path to Settings.xml
            xml_type: "email" or "sftp"
        """
        self.settings_path = Path(settings_path)
        self.xml_type = xml_type
        self.parser = SettingsXmlParser(settings_path)
        self.field_map = EMAIL_FIELD_MAP if xml_type == "email" else SFTP_FIELD_MAP

    def create_job(
        self,
        template_job_name: str,
        new_job_name: str,
        overrides: Optional[dict] = None,
    ) -> CrudResult:
        """
        Create a new job by deep-copying a template job.

        Args:
            template_job_name: Name of existing job to use as template
            new_job_name: Name for the new job
            overrides: Dict of field_name → new_value to apply after copy

        Returns:
            CrudResult with created job details and validation

        Raises:
            ValueError: If template not found or new name already exists
        """
        tree = self.parser.get_element_tree()
        root = tree.getroot()

        # Find template job element
        template_elem = self._find_job_element(root, template_job_name)
        if template_elem is None:
            raise ValueError(f"Template job '{template_job_name}' not found")

        # Check new name doesn't already exist
        if self._find_job_element(root, new_job_name) is not None:
            raise ValueError(f"Job '{new_job_name}' already exists")

        # Deep copy template
        new_elem = copy.deepcopy(template_elem)

        # Set new name
        name_elem = new_elem.find("Name")
        if name_elem is not None:
            name_elem.text = new_job_name
        else:
            name_elem = ET.SubElement(new_elem, "Name")
            name_elem.text = new_job_name

        # Apply overrides
        changes = [FieldChange(field="name", old_value=template_job_name, new_value=new_job_name)]
        if overrides:
            for field_name, new_value in overrides.items():
                xml_tag = self.field_map.get(field_name)
                if xml_tag is None:
                    logger.warning(f"Unknown field '{field_name}', skipping")
                    continue
                elem = new_elem.find(xml_tag)
                old_value = elem.text if elem is not None else ""
                if elem is None:
                    elem = ET.SubElement(new_elem, xml_tag)
                elem.text = str(new_value)
                changes.append(FieldChange(field=field_name, old_value=old_value, new_value=str(new_value)))

        # Insert into collection
        collection = self._get_collection_element(root)
        collection.append(new_elem)

        # Save with backup
        writer = XmlWriter(str(self.settings_path))
        backup_file = writer.save(tree)

        # Validate
        parser = SettingsXmlParser(str(self.settings_path))
        validation = parser.validate()

        return CrudResult(
            operation="create",
            job_name=new_job_name,
            changes=changes,
            backup_file=backup_file,
            validation=validation.to_dict() if validation else None,
        )

    def edit_job(
        self,
        job_name: str,
        field_name: str,
        new_value: str,
    ) -> CrudResult:
        """
        Edit a single field on an existing job.

        Args:
            job_name: Exact or fuzzy job name
            field_name: Field to edit (must be in field_map)
            new_value: New value for the field

        Returns:
            CrudResult with old→new value and validation

        Raises:
            ValueError: If job not found, field not editable, or ambiguous match
        """
        xml_tag = self.field_map.get(field_name)
        if xml_tag is None:
            editable = ", ".join(self.field_map.keys())
            raise ValueError(f"Field '{field_name}' is not editable. Editable fields: {editable}")

        tree = self.parser.get_element_tree()
        root = tree.getroot()

        # Find job element
        job_elem = self._find_job_element(root, job_name)
        if job_elem is None:
            # Try fuzzy match
            matches = self._fuzzy_find_jobs(root, job_name)
            if len(matches) == 0:
                raise ValueError(f"No job found matching '{job_name}'")
            elif len(matches) > 1:
                names = [m.find("Name").text for m in matches]
                raise ValueError(f"Ambiguous match for '{job_name}'. Matches: {names}")
            else:
                job_elem = matches[0]

        actual_name = job_elem.find("Name").text

        # Get old value
        field_elem = job_elem.find(xml_tag)
        old_value = field_elem.text if field_elem is not None else ""

        # Set new value
        if field_elem is None:
            field_elem = ET.SubElement(job_elem, xml_tag)
        field_elem.text = new_value

        # Save with backup
        writer = XmlWriter(str(self.settings_path))
        backup_file = writer.save(tree)

        # Validate
        parser = SettingsXmlParser(str(self.settings_path))
        validation = parser.validate()

        return CrudResult(
            operation="edit",
            job_name=actual_name,
            changes=[FieldChange(field=field_name, old_value=old_value, new_value=new_value)],
            backup_file=backup_file,
            validation=validation.to_dict() if validation else None,
        )

    def get_job_preview(self, job_name: str) -> dict:
        """
        Get a preview of a job's current configuration for confirmation dialogs.

        Args:
            job_name: Job name (exact or fuzzy)

        Returns:
            Dict with all editable field values
        """
        jobs = self.parser.search_jobs(job_name)
        if not jobs:
            raise ValueError(f"No job found matching '{job_name}'")
        return jobs[0].to_dict()

    def _find_job_element(self, root: ET.Element, name: str) -> Optional[ET.Element]:
        """Find a job element by exact name match."""
        collection = self._get_collection_element(root)
        if collection is None:
            return None
        for job_elem in collection:
            name_elem = job_elem.find("Name")
            if name_elem is not None and name_elem.text == name:
                return job_elem
        return None

    def _fuzzy_find_jobs(self, root: ET.Element, query: str) -> list:
        """Find job elements by case-insensitive substring match."""
        collection = self._get_collection_element(root)
        if collection is None:
            return []
        query_lower = query.lower()
        matches = []
        for job_elem in collection:
            name_elem = job_elem.find("Name")
            if name_elem is not None and query_lower in name_elem.text.lower():
                matches.append(job_elem)
        return matches

    def _get_collection_element(self, root: ET.Element) -> Optional[ET.Element]:
        """Get the job collection parent element."""
        if self.xml_type == "email":
            return root.find(".//MailboxCollection")
        else:
            return root.find(".//SftpJobCollection")
```

---

## 4. Template Inventory — backend/xml/templates.py

```python
"""Discover template patterns from existing jobs."""

import logging
from collections import defaultdict
from typing import Optional

from backend.xml.parser import SettingsXmlParser
from backend.xml.models import JobTemplate, EmailJob, SftpJob

logger = logging.getLogger(__name__)


class TemplateInventory:
    """Analyze jobs to discover reusable template patterns."""

    def __init__(self, settings_path: str, xml_type: str = "email"):
        self.parser = SettingsXmlParser(settings_path)
        self.xml_type = xml_type

    def discover_templates(self, filter_query: Optional[str] = None) -> list[JobTemplate]:
        """
        Discover unique template patterns from all jobs.

        A "template" is a unique combination of:
        - Parser set (sorted)
        - Template file set (sorted)
        - Has ServicerID (bool)

        Args:
            filter_query: Optional filter to narrow results (parser name, template name)

        Returns:
            List of JobTemplate objects sorted by job_count descending
        """
        jobs = self.parser.get_all_jobs()

        # Group by signature
        groups: dict[str, list] = defaultdict(list)
        for job in jobs:
            sig = self._compute_signature(job)
            groups[sig].append(job)

        # Build templates
        templates = []
        for sig, group_jobs in groups.items():
            example = group_jobs[0]
            parsers = sorted(example.parsers.keys()) if hasattr(example, 'parsers') and example.parsers else []
            template_names = sorted(example.templates) if hasattr(example, 'templates') and example.templates else []

            has_servicer = any(
                bool(getattr(j, 'servicer_id', None))
                for j in group_jobs
            )

            # Determine mailbox pattern
            mailboxes = set()
            for j in group_jobs:
                mb = getattr(j, 'mailbox', None) or getattr(j, 'path', '')
                if mb:
                    mailboxes.add(mb)
            mailbox_pattern = list(mailboxes)[0] if len(mailboxes) == 1 else "varies"

            # Compute pattern name
            pattern_name = self._compute_pattern_name(parsers, template_names)

            # Extract sample fields
            sample_fields = self._extract_sample_fields(example)

            template = JobTemplate(
                pattern_name=pattern_name,
                parser_names=parsers,
                template_names=template_names,
                mailbox_pattern=mailbox_pattern,
                example_job_name=example.name,
                job_count=len(group_jobs),
                has_servicer_id=has_servicer,
                sample_fields=sample_fields,
            )
            templates.append(template)

        # Sort by job count descending
        templates.sort(key=lambda t: t.job_count, reverse=True)

        # Apply filter if provided
        if filter_query:
            q = filter_query.lower()
            templates = [
                t for t in templates
                if q in t.pattern_name.lower()
                or any(q in p.lower() for p in t.parser_names)
                or any(q in tn.lower() for tn in t.template_names)
            ]

        return templates

    def _compute_signature(self, job) -> str:
        """Compute a hashable signature for template grouping."""
        parsers = tuple(sorted(job.parsers.keys())) if hasattr(job, 'parsers') and job.parsers else ()
        templates = tuple(sorted(job.templates)) if hasattr(job, 'templates') and job.templates else ()
        has_sid = bool(getattr(job, 'servicer_id', None))
        return f"{parsers}|{templates}|{has_sid}"

    def _compute_pattern_name(self, parsers: list[str], templates: list[str]) -> str:
        """Generate a human-readable pattern name."""
        parser_part = parsers[0] if parsers else "NoParser"
        template_part = templates[0] if templates else "NoTemplate"
        return f"{parser_part} — {template_part}"

    def _extract_sample_fields(self, job) -> dict:
        """Extract key configuration fields from a sample job."""
        fields = {}
        for attr in ['subject_filter', 'sender_filter', 'active', 'import_did']:
            val = getattr(job, attr, None)
            if val is not None:
                fields[attr] = str(val)
        return fields
```

---

## 5. Coverage Gap Analysis — backend/intel/coverage.py

```python
"""Coverage gap analysis: find DIDs not covered by any monitoring job."""

import logging
from typing import Optional

from backend.xml.parser import SettingsXmlParser
from backend.db.deal_repo import DealRepository
from backend.intel.models import CoverageReport

logger = logging.getLogger(__name__)


class CoverageAnalyzer:
    """Analyze coverage gaps between jobs and deal database."""

    def __init__(self, settings_path: str, deal_repo: DealRepository, xml_type: str = "email"):
        self.parser = SettingsXmlParser(settings_path)
        self.deal_repo = deal_repo
        self.xml_type = xml_type

    def analyze(self, servicer_id: Optional[int] = None) -> list[CoverageReport]:
        """
        Analyze coverage gaps for one or all servicers.

        Args:
            servicer_id: Specific CompanyID, or None for all

        Returns:
            List of CoverageReport, one per analyzed servicer

        Algorithm:
            1. Get all jobs with ServicerID from XML
            2. Get all deals from DB for the target servicer(s)
            3. For each DID, check if any job's ImportDID keyword matches
            4. Report unmapped DIDs as coverage gaps
        """
        jobs = self.parser.get_all_jobs()

        # Group jobs by ServicerID
        jobs_by_servicer: dict[int, list] = {}
        for job in jobs:
            sid = getattr(job, 'servicer_id', None)
            if sid:
                try:
                    sid_int = int(sid)
                except (ValueError, TypeError):
                    continue
                if sid_int not in jobs_by_servicer:
                    jobs_by_servicer[sid_int] = []
                jobs_by_servicer[sid_int].append(job)

        # Determine which servicers to analyze
        if servicer_id is not None:
            target_servicers = [servicer_id]
        else:
            target_servicers = list(jobs_by_servicer.keys())

        reports = []
        for sid in target_servicers:
            report = self._analyze_servicer(sid, jobs_by_servicer.get(sid, []))
            reports.append(report)

        return reports

    def _analyze_servicer(self, servicer_id: int, jobs: list) -> CoverageReport:
        """Analyze coverage for a single servicer."""
        # Get deals from DB
        deals = self.deal_repo.get_deals_by_company(servicer_id)
        if not deals:
            return CoverageReport(
                servicer_id=servicer_id,
                total_dids=0,
                mapped_dids=0,
                unmapped_dids=[],
                coverage_percentage=0.0,
                matching_jobs=[j.name for j in jobs],
            )

        # Extract ImportDID keywords from jobs
        job_keywords = []
        for job in jobs:
            keyword = getattr(job, 'import_did', None)
            if keyword:
                job_keywords.append(keyword.strip().upper())

        # Check each DID for coverage
        mapped = []
        unmapped = []
        for deal in deals:
            did = deal.get('DID') or deal.get('did')
            import_did = deal.get('ImportDID') or deal.get('import_did', '')
            if self._is_covered(import_did, job_keywords):
                mapped.append(deal)
            else:
                unmapped.append({"did": did, "import_did": import_did})

        total = len(deals)
        coverage_pct = (len(mapped) / total * 100) if total > 0 else 0.0

        return CoverageReport(
            servicer_id=servicer_id,
            total_dids=total,
            mapped_dids=len(mapped),
            unmapped_dids=unmapped,
            coverage_percentage=round(coverage_pct, 1),
            matching_jobs=[j.name for j in jobs],
        )

    @staticmethod
    def _is_covered(did_import_did: str, job_keywords: list[str]) -> bool:
        """
        Check if a DID's ImportDID value matches any job keyword.
        Mirrors EmailMonitor's matching logic: case-insensitive exact match.

        Args:
            did_import_did: ImportDID value from tblExternalDIDRef
            job_keywords: List of uppercase ImportDID keywords from jobs

        Returns:
            True if any job keyword matches
        """
        if not did_import_did:
            return False
        did_upper = did_import_did.strip().upper()
        return did_upper in job_keywords
```

---

## 6. Orphan Detection — backend/intel/orphans.py

```python
"""Orphan detection: find jobs with ServicerIDs that have no DB match."""

import logging

from backend.xml.parser import SettingsXmlParser
from backend.db.deal_repo import DealRepository
from backend.intel.models import OrphanResult

logger = logging.getLogger(__name__)


class OrphanDetector:
    """Detect jobs whose ServicerID has no matching records in the database."""

    def __init__(self, settings_path: str, deal_repo: DealRepository, xml_type: str = "email"):
        self.parser = SettingsXmlParser(settings_path)
        self.deal_repo = deal_repo
        self.xml_type = xml_type

    def detect(self) -> list[OrphanResult]:
        """
        Find all orphaned jobs.

        A job is orphaned if:
        1. It HAS a ServicerID (non-empty)
        2. AND that ServicerID does not exist as a CompanyID in tblExternalDIDRef
        -- OR --
        3. It HAS a ServicerID that exists but has zero deals

        Jobs WITHOUT a ServicerID are NOT orphans — they are shelf-level/process-level.

        Returns:
            List of OrphanResult for each orphaned job
        """
        jobs = self.parser.get_all_jobs()

        # Get all valid CompanyIDs from DB
        valid_company_ids = set(self.deal_repo.get_all_servicer_ids())

        orphans = []
        for job in jobs:
            sid = getattr(job, 'servicer_id', None)
            if not sid:
                continue  # No ServicerID — not an orphan, skip

            try:
                sid_int = int(sid)
            except (ValueError, TypeError):
                # Non-numeric ServicerID — flag as orphan
                orphans.append(OrphanResult(
                    job_name=job.name,
                    servicer_id=0,
                    reason="invalid_servicer_id",
                    xml_type=self.xml_type,
                ))
                continue

            if sid_int not in valid_company_ids:
                orphans.append(OrphanResult(
                    job_name=job.name,
                    servicer_id=sid_int,
                    reason="no_db_match",
                    xml_type=self.xml_type,
                ))
            else:
                # ServicerID exists — check if it has any deals
                deals = self.deal_repo.get_deals_by_company(sid_int)
                if not deals:
                    orphans.append(OrphanResult(
                        job_name=job.name,
                        servicer_id=sid_int,
                        reason="no_deal_data",
                        xml_type=self.xml_type,
                    ))

        return orphans
```

---

## 7. ImportDID Collision Detection — backend/intel/collisions.py

```python
"""ImportDID collision detection: find keywords matching multiple CompanyIDs."""

import logging
from collections import defaultdict

from backend.xml.parser import SettingsXmlParser
from backend.db.deal_repo import DealRepository
from backend.intel.models import CollisionResult

logger = logging.getLogger(__name__)


class CollisionDetector:
    """Detect ImportDID keywords that match multiple CompanyIDs."""

    def __init__(self, settings_path: str, deal_repo: DealRepository, xml_type: str = "email"):
        self.parser = SettingsXmlParser(settings_path)
        self.deal_repo = deal_repo
        self.xml_type = xml_type

    def detect(self) -> list[CollisionResult]:
        """
        Find ImportDID collisions across all jobs.

        A collision occurs when the SAME ImportDID keyword matches
        deals from DIFFERENT CompanyIDs.

        IMPORTANT: Same ImportDID + same CompanyID + multiple DIDs
        is a legitimate batch pattern, NOT a collision.

        Returns:
            List of CollisionResult, sorted by risk_level descending
        """
        jobs = self.parser.get_all_jobs()

        # Collect unique ImportDID keywords and their source jobs
        keyword_jobs: dict[str, list[str]] = defaultdict(list)
        for job in jobs:
            import_did = getattr(job, 'import_did', None)
            if import_did:
                keyword = import_did.strip().upper()
                if keyword:
                    keyword_jobs[keyword].append(job.name)

        # Check each keyword against the database
        collisions = []
        for keyword, job_names in keyword_jobs.items():
            matching_companies = self.deal_repo.get_companies_by_import_did(keyword)

            if len(matching_companies) > 1:
                # This keyword matches multiple CompanyIDs — collision!
                deal_counts = {}
                for company_id in matching_companies:
                    deals = self.deal_repo.get_deals_by_company(company_id)
                    deal_counts[company_id] = len(deals) if deals else 0

                risk_level = "high" if len(matching_companies) >= 3 else "medium"

                collisions.append(CollisionResult(
                    import_did_keyword=keyword,
                    matching_company_ids=matching_companies,
                    affected_jobs=job_names,
                    risk_level=risk_level,
                    deal_counts=deal_counts,
                ))

        # Sort: high risk first, then by number of affected companies
        collisions.sort(key=lambda c: (0 if c.risk_level == "high" else 1, -len(c.matching_company_ids)))

        return collisions
```

---

## 8. XML Diff Engine — backend/xml/diff.py

```python
"""Job-level XML diff engine for Settings.xml comparison."""

import logging
from datetime import datetime
from pathlib import Path

from backend.xml.parser import SettingsXmlParser
from backend.xml.models import DiffResult, JobDiff, FieldChange

logger = logging.getLogger(__name__)

# Fields to compare between job versions
COMPARE_FIELDS_EMAIL = [
    'name', 'servicer_id', 'mailbox', 'import_did',
    'subject_filter', 'sender_filter', 'active',
]

COMPARE_FIELDS_SFTP = [
    'name', 'servicer_id', 'path', 'import_did',
    'file_pattern', 'active',
]


class XmlDiffEngine:
    """Compare two Settings.xml files at the job level."""

    def __init__(self, xml_type: str = "email"):
        self.xml_type = xml_type
        self.compare_fields = COMPARE_FIELDS_EMAIL if xml_type == "email" else COMPARE_FIELDS_SFTP

    def diff(self, current_path: str, backup_path: str) -> DiffResult:
        """
        Compare current Settings.xml to a backup version.

        Args:
            current_path: Path to current Settings.xml
            backup_path: Path to backup Settings.xml

        Returns:
            DiffResult with added, removed, modified jobs

        Algorithm:
            1. Parse both files
            2. Build name → job maps
            3. Detect added (in current, not in backup)
            4. Detect removed (in backup, not in current)
            5. Detect modified (in both, but different fields)
        """
        current_parser = SettingsXmlParser(current_path)
        backup_parser = SettingsXmlParser(backup_path)

        current_jobs = current_parser.get_all_jobs()
        backup_jobs = backup_parser.get_all_jobs()

        current_map = {j.name: j for j in current_jobs}
        backup_map = {j.name: j for j in backup_jobs}

        current_names = set(current_map.keys())
        backup_names = set(backup_map.keys())

        # Added jobs (new in current)
        added = []
        for name in current_names - backup_names:
            added.append(JobDiff(job_name=name, change_type="added"))

        # Removed jobs (gone from current)
        removed = []
        for name in backup_names - current_names:
            removed.append(JobDiff(job_name=name, change_type="removed"))

        # Modified jobs (exist in both, but changed)
        modified = []
        for name in current_names & backup_names:
            changes = self._compare_jobs(current_map[name], backup_map[name])
            if changes:
                modified.append(JobDiff(
                    job_name=name,
                    change_type="modified",
                    field_changes=changes,
                ))

        unchanged_count = len(current_names & backup_names) - len(modified)

        return DiffResult(
            current_file=str(current_path),
            backup_file=str(backup_path),
            added_jobs=added,
            removed_jobs=removed,
            modified_jobs=modified,
            unchanged_count=unchanged_count,
            timestamp=datetime.now().isoformat(),
        )

    def _compare_jobs(self, current_job, backup_job) -> list[FieldChange]:
        """Compare two jobs field-by-field."""
        changes = []
        for field_name in self.compare_fields:
            current_val = str(getattr(current_job, field_name, '') or '')
            backup_val = str(getattr(backup_job, field_name, '') or '')
            if current_val != backup_val:
                changes.append(FieldChange(
                    field=field_name,
                    old_value=backup_val,
                    new_value=current_val,
                ))

        # Compare parsers (dict comparison)
        current_parsers = sorted(
            (getattr(current_job, 'parsers', None) or {}).keys()
        )
        backup_parsers = sorted(
            (getattr(backup_job, 'parsers', None) or {}).keys()
        )
        if current_parsers != backup_parsers:
            changes.append(FieldChange(
                field="parsers",
                old_value=", ".join(backup_parsers),
                new_value=", ".join(current_parsers),
            ))

        # Compare templates (list comparison)
        current_templates = sorted(getattr(current_job, 'templates', None) or [])
        backup_templates = sorted(getattr(backup_job, 'templates', None) or [])
        if current_templates != backup_templates:
            changes.append(FieldChange(
                field="templates",
                old_value=", ".join(backup_templates),
                new_value=", ".join(current_templates),
            ))

        return changes
```

---

## 9. Rollback Handler — backend/xml/rollback.py

```python
"""Rollback Settings.xml to a previous backup version."""

import logging
import shutil
from pathlib import Path

from backend.xml.parser import SettingsXmlParser
from backend.xml.writer import XmlWriter
from backend.xml.diff import XmlDiffEngine
from backend.xml.models import DiffResult, ValidationResult

logger = logging.getLogger(__name__)


class RollbackHandler:
    """Restore Settings.xml from a backup with safety mechanisms."""

    def __init__(self, settings_path: str, xml_type: str = "email"):
        self.settings_path = Path(settings_path)
        self.xml_type = xml_type

    def preview(self, backup_file: str) -> DiffResult:
        """
        Show what would change if we rollback to this backup.

        Args:
            backup_file: Path to the backup file

        Returns:
            DiffResult showing differences (from backup's perspective)
        """
        diff_engine = XmlDiffEngine(self.xml_type)
        return diff_engine.diff(str(self.settings_path), backup_file)

    def execute(self, backup_file: str) -> dict:
        """
        Rollback Settings.xml to a backup version.

        Safety steps:
        1. Backup current Settings.xml first (safety net)
        2. Copy backup file → Settings.xml
        3. Validate the restored file
        4. Return results

        Args:
            backup_file: Path to the backup file to restore

        Returns:
            Dict with safety_backup, restored_from, validation

        Raises:
            FileNotFoundError: If backup file doesn't exist
            ValueError: If backup file is not valid XML
        """
        backup_path = Path(backup_file)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_file}")

        # Step 1: Safety backup of current state
        writer = XmlWriter(str(self.settings_path))
        safety_backup = writer.save(
            SettingsXmlParser(str(self.settings_path)).get_element_tree()
        )

        # Step 2: Copy backup → current settings
        shutil.copy2(str(backup_path), str(self.settings_path))
        logger.info(f"Restored {self.settings_path} from {backup_file}")

        # Step 3: Validate restored file
        parser = SettingsXmlParser(str(self.settings_path))
        validation = parser.validate()

        return {
            "safety_backup": safety_backup,
            "restored_from": str(backup_path.name),
            "validation": validation.to_dict() if validation else None,
        }
```

---

## 10. CLI Command Additions — cli/main.py

The following subcommands are added to the existing `cli/main.py` argparse structure:

```python
# ── Phase 2 subcommands ──────────────────────────────────────────────

def cmd_create_job(args) -> dict:
    """Create a new job from a template."""
    from backend.xml.crud import JobCrudEngine

    overrides = {}
    if args.servicer_id:
        overrides['servicer_id'] = args.servicer_id
    if args.mailbox:
        overrides['mailbox'] = args.mailbox
    if args.import_did:
        overrides['import_did'] = args.import_did

    engine = JobCrudEngine(args.settings_path, args.xml_type)
    result = engine.create_job(
        template_job_name=args.template_job,
        new_job_name=args.name,
        overrides=overrides if overrides else None,
    )
    return result.to_dict()


def cmd_edit_job(args) -> dict:
    """Edit a field on an existing job."""
    from backend.xml.crud import JobCrudEngine

    engine = JobCrudEngine(args.settings_path, args.xml_type)
    result = engine.edit_job(
        job_name=args.job_name,
        field_name=args.field,
        new_value=args.value,
    )
    return result.to_dict()


def cmd_template_inventory(args) -> dict:
    """Discover template patterns from existing jobs."""
    from backend.xml.templates import TemplateInventory

    inventory = TemplateInventory(args.settings_path, args.xml_type)
    templates = inventory.discover_templates(
        filter_query=getattr(args, 'filter', None),
    )
    return {
        "templates": [t.to_dict() for t in templates],
        "total_templates": len(templates),
        "total_jobs": sum(t.job_count for t in templates),
    }


def cmd_coverage_gaps(args) -> dict:
    """Analyze coverage gaps between jobs and deal database."""
    from backend.intel.coverage import CoverageAnalyzer
    from backend.db.deal_repo import DealRepository

    repo = DealRepository(args.db_mode, args.secrets_path)
    analyzer = CoverageAnalyzer(args.settings_path, repo, args.xml_type)

    servicer_id = int(args.servicer_id) if args.servicer_id and args.servicer_id != 'all' else None
    reports = analyzer.analyze(servicer_id)
    return {
        "reports": [r.to_dict() for r in reports],
        "total_servicers_analyzed": len(reports),
    }


def cmd_orphan_detection(args) -> dict:
    """Detect orphaned jobs with no DB match."""
    from backend.intel.orphans import OrphanDetector
    from backend.db.deal_repo import DealRepository

    repo = DealRepository(args.db_mode, args.secrets_path)
    detector = OrphanDetector(args.settings_path, repo, args.xml_type)
    orphans = detector.detect()
    return {
        "orphans": [o.to_dict() for o in orphans],
        "total_orphans": len(orphans),
    }


def cmd_collision_detection(args) -> dict:
    """Detect ImportDID collisions."""
    from backend.intel.collisions import CollisionDetector
    from backend.db.deal_repo import DealRepository

    repo = DealRepository(args.db_mode, args.secrets_path)
    detector = CollisionDetector(args.settings_path, repo, args.xml_type)
    collisions = detector.detect()
    return {
        "collisions": [c.to_dict() for c in collisions],
        "total_collisions": len(collisions),
    }


def cmd_xml_diff(args) -> dict:
    """Diff current Settings.xml against a backup."""
    from backend.xml.diff import XmlDiffEngine
    from backend.backup.manager import BackupManager

    # Default to latest backup if none specified
    backup_file = args.backup_file
    if not backup_file:
        manager = BackupManager(args.settings_path)
        latest = manager.get_latest_backup()
        if not latest:
            return {"error": "No backups found. Run 'save_xml' first."}
        backup_file = str(latest)

    engine = XmlDiffEngine(args.xml_type)
    result = engine.diff(args.settings_path, backup_file)
    return result.to_dict()


def cmd_rollback_xml(args) -> dict:
    """Rollback Settings.xml to a backup version."""
    from backend.xml.rollback import RollbackHandler

    handler = RollbackHandler(args.settings_path, args.xml_type)
    return handler.execute(args.backup_file)


# ── Argparse additions ──────────────────────────────────────────────

# create_job
p_create = subparsers.add_parser('create_job')
p_create.add_argument('--settings-path', required=True)
p_create.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_create.add_argument('--template-job', required=True, help='Name of template job to copy')
p_create.add_argument('--name', required=True, help='Name for the new job')
p_create.add_argument('--servicer-id', default=None)
p_create.add_argument('--mailbox', default=None)
p_create.add_argument('--import-did', default=None)
p_create.set_defaults(func=cmd_create_job)

# edit_job
p_edit = subparsers.add_parser('edit_job')
p_edit.add_argument('--settings-path', required=True)
p_edit.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_edit.add_argument('--job-name', required=True)
p_edit.add_argument('--field', required=True)
p_edit.add_argument('--value', required=True)
p_edit.set_defaults(func=cmd_edit_job)

# template_inventory
p_templates = subparsers.add_parser('template_inventory')
p_templates.add_argument('--settings-path', required=True)
p_templates.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_templates.add_argument('--filter', default=None)
p_templates.set_defaults(func=cmd_template_inventory)

# coverage_gaps
p_gaps = subparsers.add_parser('coverage_gaps')
p_gaps.add_argument('--settings-path', required=True)
p_gaps.add_argument('--db-mode', default='mysql', choices=['mysql', 'mssql'])
p_gaps.add_argument('--secrets-path', required=True)
p_gaps.add_argument('--servicer-id', default='all')
p_gaps.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_gaps.set_defaults(func=cmd_coverage_gaps)

# orphan_detection
p_orphans = subparsers.add_parser('orphan_detection')
p_orphans.add_argument('--settings-path', required=True)
p_orphans.add_argument('--db-mode', default='mysql', choices=['mysql', 'mssql'])
p_orphans.add_argument('--secrets-path', required=True)
p_orphans.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_orphans.set_defaults(func=cmd_orphan_detection)

# collision_detection
p_collisions = subparsers.add_parser('collision_detection')
p_collisions.add_argument('--settings-path', required=True)
p_collisions.add_argument('--db-mode', default='mysql', choices=['mysql', 'mssql'])
p_collisions.add_argument('--secrets-path', required=True)
p_collisions.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_collisions.set_defaults(func=cmd_collision_detection)

# xml_diff
p_diff = subparsers.add_parser('xml_diff')
p_diff.add_argument('--settings-path', required=True)
p_diff.add_argument('--backup-file', default=None)
p_diff.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_diff.set_defaults(func=cmd_xml_diff)

# rollback_xml
p_rollback = subparsers.add_parser('rollback_xml')
p_rollback.add_argument('--settings-path', required=True)
p_rollback.add_argument('--backup-file', required=True)
p_rollback.add_argument('--xml-type', default='email', choices=['email', 'sftp'])
p_rollback.set_defaults(func=cmd_rollback_xml)
```

---

## 11. Extension Handler Updates

### New backendCall() Parameter Mappings (in tool.js)

```javascript
// Add to existing paramMap in tool.js
const paramMap = {
  // ... existing Phase 1 mappings ...
  
  // Phase 2 additions
  templateJob: '--template-job',
  name: '--name',
  jobName: '--job-name',
  field: '--field',
  value: '--value',
  filter: '--filter',
  backupFile: '--backup-file',
  xmlType: '--xml-type',
};
```

### Subcommand Handler Implementations — Key Patterns

```javascript
// ── /jobs create handler ──────────────────────────────────────────

async function handleJobCreate(vscode, request, stream, token, shared, prompt) {
  // Parse: "create rptent from 'CSMC 2015-1 rptent'"
  const match = prompt.match(/^create\s+(\S+)\s+from\s+["']?(.+?)["']?\s*$/i);
  if (!match) {
    stream.markdown('Usage: `/jobs create <keyword> from "<template_job_name>"`');
    return {};
  }

  const keyword = match[1];
  const templateName = match[2];
  const newName = `New ${keyword} Job`;  // Or derive from template

  // Preview template
  stream.progress('Loading template...');
  const template = await backendCall('search_jobs', { query: templateName }, shared);
  if (!template?.jobs?.length) {
    stream.markdown(`Template job "${templateName}" not found.`);
    return {};
  }

  // Show preview and get confirmation
  const model = await selectModel(vscode, request.model);
  if (model) {
    await generateAnswer(vscode, model, stream, token,
      `Preview template "${templateName}" for creating a new job`,
      template);
  }

  const confirm = await vscode.window.showWarningMessage(
    `Create new job "${newName}" based on "${templateName}"?`,
    { modal: true }, 'Create', 'Cancel');
  if (confirm !== 'Create') {
    stream.markdown('Job creation cancelled.');
    return {};
  }

  // Execute creation
  stream.progress('Creating job...');
  const result = await backendCall('create_job', {
    templateJob: templateName,
    name: newName,
    xmlType: 'email',
  }, shared);

  await generateOrFallback(vscode, request, stream, token, 'Job created', result);
  return { metadata: { followUps: [
    { prompt: `edit "${newName}" set servicer `, command: 'jobs' },
    { prompt: 'validate', command: 'jobs' },
  ]}};
}


// ── /deals gaps handler ───────────────────────────────────────────

async function handleCoverageGaps(vscode, request, stream, token, shared, prompt) {
  const match = prompt.match(/^gaps?\s+(\S+)/i);
  const servicerId = match ? match[1] : 'all';

  stream.progress(`Analyzing coverage gaps${servicerId !== 'all' ? ` for CompanyID ${servicerId}` : ''}...`);
  const data = await backendCall('coverage_gaps', { servicerId }, shared);
  await generateOrFallback(vscode, request, stream, token,
    `Coverage gap analysis for ${servicerId}`, data);

  return { metadata: { followUps: [
    { prompt: 'orphans', command: 'deals' },
    { prompt: 'collisions', command: 'deals' },
  ]}};
}
```

---

## 12. DB Repository Additions

### backend/db/queries.py — New SQL Constants

```python
# Phase 2 additions

GET_COMPANIES_BY_IMPORT_DID = """
    SELECT DISTINCT CompanyID
    FROM tblExternalDIDRef
    WHERE UPPER(ImportDID) = UPPER(?)
"""

GET_ALL_DISTINCT_COMPANY_IDS = """
    SELECT DISTINCT CompanyID
    FROM tblExternalDIDRef
    ORDER BY CompanyID
"""

GET_DEAL_COUNT_BY_COMPANY = """
    SELECT CompanyID, COUNT(*) as deal_count
    FROM tblExternalDIDRef
    WHERE CompanyID = ?
    GROUP BY CompanyID
"""

SEARCH_IMPORT_DID_MATCHES = """
    SELECT DISTINCT CompanyID, ImportDID, COUNT(*) as match_count
    FROM tblExternalDIDRef
    WHERE UPPER(ImportDID) = UPPER(?)
    GROUP BY CompanyID, ImportDID
"""
```

### backend/db/deal_repo.py — New Methods

```python
# Add to existing DealRepository class

def get_companies_by_import_did(self, import_did: str) -> list[int]:
    """
    Get all distinct CompanyIDs that have deals matching an ImportDID value.

    Args:
        import_did: ImportDID keyword to search for

    Returns:
        List of CompanyID integers
    """
    rows = self._execute_query(GET_COMPANIES_BY_IMPORT_DID, [import_did])
    return [row['CompanyID'] for row in rows]

def get_all_distinct_company_ids(self) -> list[int]:
    """
    Get all distinct CompanyIDs in the database.

    Returns:
        Sorted list of CompanyID integers
    """
    rows = self._execute_query(GET_ALL_DISTINCT_COMPANY_IDS, [])
    return [row['CompanyID'] for row in rows]
```

---

## 13. Error Handling Strategy

### Phase 2 Error Categories

| Error | Code | Recovery |
|-------|------|----------|
| Template job not found | CRUD-001 | Return error with "did you mean?" suggestions from fuzzy search |
| Job name already exists | CRUD-002 | Return error, suggest editing instead |
| Field not editable | CRUD-003 | Return error with list of editable fields |
| Ambiguous job match | CRUD-004 | Return error with list of matches for disambiguation |
| No backup found for diff | DIFF-001 | Return error, suggest "save_xml" first |
| Backup file not found for rollback | ROLL-001 | Return error with list of available backups |
| DB unavailable for intel | INTEL-001 | Return partial results with error message |
| XML validation failed after mutation | CRUD-005 | Return mutation result WITH validation errors (don't prevent save) |

### Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| DB unavailable | Coverage/orphan/collision commands return clear error. CRUD commands still work (no DB needed). |
| LLM unavailable | Results formatted as raw markdown tables (fallback formatter). |
| Backup dir not writable | CRUD operations fail with clear error before making changes. |
| XML parse error | All commands fail with parse error details. |

---

## 14. File Manifest

### New Files (Phase 2)

| File | Lines (Est.) | Tests |
|------|-------------|-------|
| `backend/xml/crud.py` | ~250 | 25 |
| `backend/xml/templates.py` | ~120 | 15 |
| `backend/xml/diff.py` | ~150 | 18 |
| `backend/xml/rollback.py` | ~80 | 10 |
| `backend/intel/__init__.py` | ~5 | — |
| `backend/intel/models.py` | ~130 | 12 |
| `backend/intel/coverage.py` | ~150 | 18 |
| `backend/intel/orphans.py` | ~100 | 12 |
| `backend/intel/collisions.py` | ~120 | 14 |
| **Total Python (new)** | **~1,105** | **124** |

### Modified Files (Phase 2)

| File | Changes | Tests Added |
|------|---------|-------------|
| `cli/main.py` | +8 subcommands (~200 lines) | 16 |
| `backend/db/deal_repo.py` | +2 methods (~30 lines) | 6 |
| `backend/db/queries.py` | +4 SQL constants (~20 lines) | — |
| `extension/chat/participant.js` | +8 handlers (~300 lines) | 8 manual |
| `extension/copilot/tool.js` | +6 param mappings (~15 lines) | — |
| **Total changes** | **~565 lines** | **30** |

### Grand Total: ~1,670 lines new/changed, ~154 tests

---

*Next document: [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)*
