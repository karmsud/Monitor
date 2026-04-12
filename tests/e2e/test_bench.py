"""
FRP Agent — Automated CLI Test Bench (Environment A)
=====================================================

Runs CLI commands via subprocess against the compiled exe (or Python fallback),
evaluates JSON output for correctness, scores each test, and produces a report.

Usage:
    python -m tests.e2e.test_bench                  # Run all tests
    python -m tests.e2e.test_bench --exe             # Force exe mode
    python -m tests.e2e.test_bench --python          # Force python mode
    python -m tests.e2e.test_bench --tag jobs        # Run only tests tagged 'jobs'
    python -m tests.e2e.test_bench --verbose         # Show full JSON output

Exit codes:
    0  — all tests passed
    1  — some tests failed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMAIL_SETTINGS = PROJECT_ROOT / "Email Settings" / "Settings.ps1"
SFTP_SETTINGS = PROJECT_ROOT / "SFTP Settings" / "Settings.ps1"
EMAIL_LOGS = PROJECT_ROOT / "Email Logs"
SFTP_LOGS = PROJECT_ROOT / "SFTP Logs"
EXE_PATH = PROJECT_ROOT / "extension" / "bin" / "win-x64" / "frp-backend" / "frp-backend.exe"
PYTHON_PATH = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
TEMP_DB = PROJECT_ROOT / "tests" / "e2e" / "_test_logs.sqlite"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
class Score(Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass
class TestCase:
    """Definition of a single test scenario."""
    id: str
    name: str
    tags: List[str]
    command: str
    args: Dict[str, Any]
    checks: List[Callable[[dict], tuple[bool, str]]]  # (passed, reason)
    description: str = ""


@dataclass
class TestResult:
    """Outcome of running a single test."""
    test_id: str
    test_name: str
    score: Score
    elapsed_ms: float
    checks_passed: int
    checks_total: int
    details: List[str] = field(default_factory=list)
    raw_output: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Check helpers  (reusable assertion functions)
# ---------------------------------------------------------------------------
def check_success(data: dict) -> tuple[bool, str]:
    ok = data.get("success") is True
    return ok, "success=true" if ok else f"success={data.get('success')}"


def check_has_data(data: dict) -> tuple[bool, str]:
    ok = "data" in data and data["data"] is not None
    return ok, "data present" if ok else "data missing"


def check_jobs_array(data: dict) -> tuple[bool, str]:
    jobs = data.get("data", {}).get("jobs")
    ok = isinstance(jobs, list)
    return ok, f"jobs is list (len={len(jobs) if ok else 'N/A'})" if ok else "jobs not a list"


def check_job_count(expected: int):
    def _check(data: dict) -> tuple[bool, str]:
        jobs = data.get("data", {}).get("jobs", [])
        ok = len(jobs) == expected
        return ok, f"job_count={len(jobs)} (expected {expected})"
    return _check


def check_job_count_min(minimum: int):
    def _check(data: dict) -> tuple[bool, str]:
        jobs = data.get("data", {}).get("jobs", [])
        ok = len(jobs) >= minimum
        return ok, f"job_count={len(jobs)} (expected >={minimum})"
    return _check


def check_job_count_range(lo: int, hi: int):
    def _check(data: dict) -> tuple[bool, str]:
        jobs = data.get("data", {}).get("jobs", [])
        ok = lo <= len(jobs) <= hi
        return ok, f"job_count={len(jobs)} (expected {lo}-{hi})"
    return _check


def check_job_names_contain(*expected_names: str):
    def _check(data: dict) -> tuple[bool, str]:
        jobs = data.get("data", {}).get("jobs", [])
        names = {j.get("name", "") for j in jobs}
        missing = [n for n in expected_names if n not in names]
        ok = len(missing) == 0
        return ok, f"names OK" if ok else f"missing: {missing}"
    return _check


def check_all_jobs_field_contains(field_name: str, substring: str):
    """Every returned job must have `substring` (case-insensitive) in `field_name`."""
    def _check(data: dict) -> tuple[bool, str]:
        jobs = data.get("data", {}).get("jobs", [])
        if not jobs:
            return False, f"no jobs to check field '{field_name}'"
        bad = [j.get("name", "?") for j in jobs
               if substring.lower() not in str(j.get(field_name, "")).lower()]
        ok = len(bad) == 0
        return ok, f"all jobs have '{substring}' in {field_name}" if ok else f"{len(bad)} jobs missing '{substring}' in {field_name}: {bad[:3]}"
    return _check


def check_no_errors(data: dict) -> tuple[bool, str]:
    errs = data.get("errors", [])
    ok = len(errs) == 0
    return ok, "no errors" if ok else f"{len(errs)} errors"


def check_has_validation(data: dict) -> tuple[bool, str]:
    d = data.get("data", {})
    ok = any(k in d for k in ("errors", "warnings", "info", "is_valid", "summary"))
    return ok, "validation fields present" if ok else "no validation fields"


def check_total_count(expected: int):
    def _check(data: dict) -> tuple[bool, str]:
        tc = data.get("data", {}).get("total_count")
        ok = tc == expected
        return ok, f"total_count={tc} (expected {expected})"
    return _check


def check_xml_type(expected: str):
    def _check(data: dict) -> tuple[bool, str]:
        xt = data.get("data", {}).get("xml_type")
        ok = xt == expected
        return ok, f"xml_type={xt} (expected {expected})"
    return _check


def check_field_exists(*field_path: str):
    """Check that a nested field exists in the result data."""
    def _check(data: dict) -> tuple[bool, str]:
        cur = data
        for key in field_path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return False, f"field {'→'.join(field_path)} missing at '{key}'"
        return True, f"field {'→'.join(field_path)} exists"
    return _check


# ---------------------------------------------------------------------------
# Test definitions — Start with 5, will expand to 50, 100, 150+
# ---------------------------------------------------------------------------

def build_test_cases() -> List[TestCase]:
    """Build the full list of test cases."""
    cases: List[TestCase] = []

    # ---------------------------------------------------------------
    # TIER 1: /jobs search — 5 initial tests
    # ---------------------------------------------------------------
    cases.append(TestCase(
        id="A-01", name="search tpmt (keyword)", tags=["jobs", "search", "tier1"],
        command="search_jobs",
        args={"query": "tpmt", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data, check_jobs_array,
                check_job_count(8),
                check_job_names_contain("TOWD_Carrignton_6501", "TPMT_SLS_6601")],
        description="Simple keyword search for TPMT jobs",
    ))

    cases.append(TestCase(
        id="A-02", name="search tpmt (natural language)", tags=["jobs", "search", "nl", "tier1"],
        command="search_jobs",
        args={"query": "list all jobs that have save location tpmt",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data, check_jobs_array,
                check_job_count(8)],
        description="Natural language query — tokenized search",
    ))

    cases.append(TestCase(
        id="A-03", name="search cmbs", tags=["jobs", "search", "tier1"],
        command="search_jobs",
        args={"query": "cmbs", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count(9),
                check_job_names_contain("CMBS_GreyCo", "CMBS_Wells")],
        description="Search for CMBS jobs",
    ))

    cases.append(TestCase(
        id="A-04", name="validate email XML", tags=["validate", "tier1"],
        command="validate_xml",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[check_success, check_has_data, check_has_validation],
        description="Validate email settings XML",
    ))

    cases.append(TestCase(
        id="A-05", name="status check", tags=["status", "tier1"],
        command="status",
        args={},
        checks=[check_success, check_has_data],
        description="Basic status command",
    ))

    # ---------------------------------------------------------------
    # TIER 2: Expanded search tests — 20 more
    # ---------------------------------------------------------------
    cases.append(TestCase(
        id="A-06", name="search by sender domain @fayservicing.com",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "fayservicing", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3),
                check_job_names_contain("Plaza_RTL_Fay_3003_2", "CMLTI_Fay")],
    ))

    cases.append(TestCase(
        id="A-07", name="search by mailbox towdpoint",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "towdpoint", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(5)],
    ))

    cases.append(TestCase(
        id="A-08", name="search by servicer ID 6501",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "6501", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1),
                check_job_names_contain("TOWD_Carrignton_6501")],
    ))

    cases.append(TestCase(
        id="A-09", name="search for Chase jobs",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "chase", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3),
                check_job_names_contain("Chase_EMC_6901", "CSFB_CF_Chase_3712")],
    ))

    cases.append(TestCase(
        id="A-10", name="search by template SCRT_Queuer",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "SCRT_Queuer", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(2),
                check_job_names_contain("FMSCRT_NewRez", "FMSCRT_MrCooper")],
    ))

    cases.append(TestCase(
        id="A-11", name="search COOFS",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "COOFS", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count(4),
                check_job_names_contain("COOFS_LateMoney", "COOFS_MidMonthly")],
    ))

    cases.append(TestCase(
        id="A-12", name="search by SME sudhanwa",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "sudhanwa", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(30)],
        description="Most jobs have sudhanwa as SME",
    ))

    cases.append(TestCase(
        id="A-13", name="search by SME ilya",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "ilya", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(4)],
    ))

    cases.append(TestCase(
        id="A-14", name="NL: show me fay servicing jobs",
        tags=["jobs", "search", "nl", "tier2"],
        command="search_jobs",
        args={"query": "show me fay servicing jobs",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3)],
    ))

    cases.append(TestCase(
        id="A-15", name="NL: which jobs use newrez sender",
        tags=["jobs", "search", "nl", "tier2"],
        command="search_jobs",
        args={"query": "which jobs use newrez sender",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3)],
    ))

    cases.append(TestCase(
        id="A-16", name="search ABS_Deals",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "ABS_Deals", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1),
                check_job_names_contain("ABS_Deals")],
    ))

    cases.append(TestCase(
        id="A-17", name="search Neuberger",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "neuberger", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    cases.append(TestCase(
        id="A-18", name="search by save location EmailExtract",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "EmailExtract", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(10)],
    ))

    cases.append(TestCase(
        id="A-19", name="NL: find all freddie mac related jobs",
        tags=["jobs", "search", "nl", "tier2"],
        command="search_jobs",
        args={"query": "find all freddie mac related jobs",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    cases.append(TestCase(
        id="A-20", name="search for rptent mailbox",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "rptent", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(25)],
    ))

    cases.append(TestCase(
        id="A-21", name="search nonexistent job returns 0",
        tags=["jobs", "search", "negative", "tier2"],
        command="search_jobs",
        args={"query": "zzz_no_such_job_999", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count(0)],
    ))

    cases.append(TestCase(
        id="A-22", name="search email type filter",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "tpmt", "settings_path": str(EMAIL_SETTINGS),
              "xml_type": "email"},
        checks=[check_success, check_jobs_array, check_job_count(8),
                check_xml_type("email")],
    ))

    cases.append(TestCase(
        id="A-23", name="search SFTP settings",
        tags=["jobs", "search", "sftp", "tier2"],
        command="search_jobs",
        args={"query": "Ocwen",
              "settings_path": str(EMAIL_SETTINGS),
              "sftp_settings_path": str(SFTP_SETTINGS),
              "xml_type": "all"},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    cases.append(TestCase(
        id="A-24", name="search by @wellsfargo sender",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "wellsfargo", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3)],
    ))

    cases.append(TestCase(
        id="A-25", name="search CMLTI jobs",
        tags=["jobs", "search", "tier2"],
        command="search_jobs",
        args={"query": "CMLTI", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3),
                check_job_names_contain("CMLTI_Fay", "CMLTI_Fay_1770", "CMLTI_Pennymac_6031")],
    ))

    # ---------------------------------------------------------------
    # TIER 2: Validate & template commands
    # ---------------------------------------------------------------
    cases.append(TestCase(
        id="A-26", name="validate SFTP XML",
        tags=["validate", "sftp", "tier2"],
        command="validate_xml",
        args={"settings_path": str(SFTP_SETTINGS), "xml_type": "sftp"},
        checks=[check_success, check_has_data, check_has_validation],
    ))

    cases.append(TestCase(
        id="A-27", name="template_inventory email",
        tags=["templates", "tier2"],
        command="template_inventory",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-28", name="list_backups email",
        tags=["backups", "tier2"],
        command="list_backups",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[check_success, check_has_data],
    ))

    # ---------------------------------------------------------------
    # TIER 2: Log commands
    # ---------------------------------------------------------------
    cases.append(TestCase(
        id="A-29", name="sync_logs email",
        tags=["logs", "tier2"],
        command="sync_logs",
        args={"log_folder": str(EMAIL_LOGS), "db_path": str(TEMP_DB)},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-30", name="log_daily_summary",
        tags=["logs", "tier2"],
        command="log_daily_summary",
        args={"db_path": str(TEMP_DB)},
        checks=[check_success, check_has_data],
    ))

    # ---------------------------------------------------------------
    # TIER 3: NL search stress — various phrasings
    # ---------------------------------------------------------------
    nl_queries = [
        ("A-31", "NL: jobs from bnymellon", "jobs from bnymellon", 1),
        ("A-32", "NL: what jobs monitor sba.gov emails", "what jobs monitor sba.gov emails", 3),
        ("A-33", "NL: show carrington job details", "show carrington job details", 1),
        ("A-34", "NL: mr cooper jobs", "mr cooper jobs", 2),
        ("A-35", "NL: all jobs sending to BATCH folder", "all jobs sending to BATCH folder", 5),
        ("A-36", "NL: rabs 3723 job details", "rabs 3723 job", 1),
        ("A-37", "NL: find bayview jobs", "find bayview jobs", 1),
        ("A-38", "NL: pennymac related configuration", "pennymac related configuration", 1),
        ("A-39", "NL: list all jobs for selene finance", "list all jobs for selene finance", 2),
        ("A-40", "NL: jobs with servicer 132", "jobs with servicer 132", 2),
        ("A-41", "NL: spservicing sender jobs", "spservicing sender jobs", 3),
        ("A-42", "NL: show freddie RMBS mailbox jobs", "show freddie RMBS mailbox jobs", 2),
        ("A-43", "NL: ghfta mailbox jobs", "ghfta mailbox jobs", 4),
        ("A-44", "NL: jobs configured for Late Money folder", "jobs configured for Late Money folder", 2),
        ("A-45", "NL: Plaza RTL jobs", "Plaza RTL jobs", 3),
        ("A-46", "NL: trimont job configuration", "trimont job configuration", 1),
        ("A-47", "NL: harvest credit fund jobs", "harvest credit jobs", 1),
        ("A-48", "NL: all SLS related TPMT jobs", "SLS TPMT jobs", 2),
        ("A-49", "NL: jpmchase sender configurations", "jpmchase sender configurations", 3),
        ("A-50", "NL: computershare email jobs", "computershare email jobs", 1),
    ]
    for tid, name, query, min_count in nl_queries:
        cases.append(TestCase(
            id=tid, name=name, tags=["jobs", "search", "nl", "tier3"],
            command="search_jobs",
            args={"query": query, "settings_path": str(EMAIL_SETTINGS)},
            checks=[check_success, check_jobs_array, check_job_count_min(min_count)],
        ))

    # ---------------------------------------------------------------
    # TIER 4: Full command coverage — every CLI command gets tested
    # ---------------------------------------------------------------

    # --- servicer_dossier ---
    cases.append(TestCase(
        id="A-51", name="servicer_dossier by job name",
        tags=["dossier", "tier4"],
        command="servicer_dossier",
        args={"job_name": "TPMT_SLS_6601", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data,
                check_field_exists("data", "jobs")],
    ))

    cases.append(TestCase(
        id="A-52", name="servicer_dossier by servicer ID",
        tags=["dossier", "tier4"],
        command="servicer_dossier",
        args={"servicer_id": "6501", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-53", name="servicer_dossier CMBS job",
        tags=["dossier", "tier4"],
        command="servicer_dossier",
        args={"job_name": "CMBS_Wells", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data],
    ))

    # --- xml_diff ---
    cases.append(TestCase(
        id="A-54", name="xml_diff no backup (expected fail)",
        tags=["diff", "tier4"],
        command="xml_diff",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[lambda d: (d.get("success") is False, "expected success=false (no backups)"),
                lambda d: (any("backup" in str(e).lower() for e in d.get("errors", [])),
                           "error mentions backups")],
    ))

    cases.append(TestCase(
        id="A-55", name="xml_diff SFTP (expected fail)",
        tags=["diff", "sftp", "tier4"],
        command="xml_diff",
        args={"settings_path": str(SFTP_SETTINGS), "xml_type": "sftp"},
        checks=[lambda d: (d.get("success") is False, "expected success=false (no backups)"),
                lambda d: (any("backup" in str(e).lower() for e in d.get("errors", [])),
                           "error mentions backups")],
    ))

    # --- log commands with synced DB ---
    cases.append(TestCase(
        id="A-56", name="log_did_failures (empty DB)",
        tags=["logs", "tier4"],
        command="log_did_failures",
        args={"db_path": str(TEMP_DB), "days": "7"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-57", name="log_job_health for TPMT_SLS_6601",
        tags=["logs", "tier4"],
        command="log_job_health",
        args={"job_name": "TPMT_SLS_6601", "db_path": str(TEMP_DB), "days": "7"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-58", name="log_trends default",
        tags=["logs", "tier4"],
        command="log_trends",
        args={"db_path": str(TEMP_DB), "days": "7"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-59", name="log_trends for specific job",
        tags=["logs", "tier4"],
        command="log_trends",
        args={"db_path": str(TEMP_DB), "days": "7", "job": "CMBS_GreyCo"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-60", name="log_performance default",
        tags=["logs", "tier4"],
        command="log_performance",
        args={"db_path": str(TEMP_DB), "days": "7"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-61", name="log_performance sort by total_files",
        tags=["logs", "tier4"],
        command="log_performance",
        args={"db_path": str(TEMP_DB), "sort": "total_files", "top": "5"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-62", name="log_deal_activity",
        tags=["logs", "tier4"],
        command="log_deal_activity",
        args={"did": "TPMT_SLS_6601", "db_path": str(TEMP_DB), "days": "14"},
        checks=[check_success, check_has_data],
    ))

    # --- analyze commands ---
    cases.append(TestCase(
        id="A-63", name="analyze_consolidation email",
        tags=["analyze", "tier4"],
        command="analyze_consolidation",
        args={"settings_path": str(EMAIL_SETTINGS), "type": "email"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-64", name="analyze_health email",
        tags=["analyze", "tier4"],
        command="analyze_health",
        args={"settings_path": str(EMAIL_SETTINGS), "type": "email",
              "db_path": str(TEMP_DB)},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-65", name="analyze_impact delete_job",
        tags=["analyze", "tier4"],
        command="analyze_impact",
        args={"settings_path": str(EMAIL_SETTINGS),
              "change_type": "delete_job",
              "target_job": "ABS_Deals"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-66", name="analyze_impact rename_did",
        tags=["analyze", "tier4"],
        command="analyze_impact",
        args={"settings_path": str(EMAIL_SETTINGS),
              "change_type": "rename_did",
              "target_did": "CMBS_Wells",
              "new_value": "CMBS_Wells_New"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-67", name="analyze_consolidation all types",
        tags=["analyze", "tier4"],
        command="analyze_consolidation",
        args={"settings_path": str(EMAIL_SETTINGS), "type": "all"},
        checks=[check_success, check_has_data],
    ))

    # --- template_inventory ---
    cases.append(TestCase(
        id="A-68", name="template_inventory SFTP",
        tags=["templates", "sftp", "tier4"],
        command="template_inventory",
        args={"settings_path": str(SFTP_SETTINGS), "xml_type": "sftp"},
        checks=[check_success, check_has_data],
    ))

    # --- validate variants ---
    cases.append(TestCase(
        id="A-69", name="validate email XML detailed",
        tags=["validate", "tier4"],
        command="validate_xml",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[check_success, check_has_data, check_has_validation,
                check_xml_type("email")],
    ))

    # --- sync_logs SFTP ---
    cases.append(TestCase(
        id="A-70", name="sync_logs SFTP",
        tags=["logs", "sftp", "tier4"],
        command="sync_logs",
        args={"sftp_log_folder": str(SFTP_LOGS), "db_path": str(TEMP_DB)},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-70b", name="sync_logs dual (email+sftp)",
        tags=["logs", "tier4"],
        command="sync_logs",
        args={"log_folder": str(EMAIL_LOGS), "sftp_log_folder": str(SFTP_LOGS),
              "db_path": str(TEMP_DB)},
        checks=[check_success, check_has_data],
    ))

    # ---------------------------------------------------------------
    # TIER 5: Search edge cases and stress
    # ---------------------------------------------------------------

    # Case-sensitivity
    cases.append(TestCase(
        id="A-71", name="search case insensitive UPPER",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "TPMT", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count(8)],
    ))

    cases.append(TestCase(
        id="A-72", name="search case insensitive lower",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "tpmt", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count(8)],
    ))

    cases.append(TestCase(
        id="A-73", name="search case insensitive mixed",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "TpMt", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count(8)],
    ))

    # Single character / short queries
    cases.append(TestCase(
        id="A-74", name="search single char 'z'",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "z", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array],
    ))

    # Numeric-only queries
    cases.append(TestCase(
        id="A-75", name="search numeric servicer 6601",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "6601", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1),
                check_job_names_contain("TPMT_SLS_6601")],
    ))

    cases.append(TestCase(
        id="A-76", name="search numeric servicer 3712",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "3712", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1),
                check_job_names_contain("CSFB_CF_Chase_3712")],
    ))

    # Queries with special characters
    cases.append(TestCase(
        id="A-77", name="search with @ symbol",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "@fayservicing.com", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(3)],
    ))

    cases.append(TestCase(
        id="A-78", name="search with backslash path",
        tags=["jobs", "search", "edge", "tier5"],
        command="search_jobs",
        args={"query": "TPMT\\Data", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array],
    ))

    # Compound NL queries
    cases.append(TestCase(
        id="A-79", name="NL: how many jobs use mr cooper",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "how many jobs use mr cooper as servicer",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(2)],
    ))

    cases.append(TestCase(
        id="A-80", name="NL: jobs that process CMBS securities",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "jobs that process CMBS securities data",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(5)],
    ))

    cases.append(TestCase(
        id="A-81", name="NL: all rptent mailbox configurations",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "all rptent mailbox configurations with active jobs",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(10)],
    ))

    cases.append(TestCase(
        id="A-82", name="NL: WF Servicing mailbox jobs",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "WFServicing mailbox email monitoring",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    cases.append(TestCase(
        id="A-83", name="NL: find all quarterly report jobs",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "quarterly report processing jobs",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array],
    ))

    # Multiple token matches
    cases.append(TestCase(
        id="A-84", name="NL: SLS servicer TPMT template",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "SLS servicer with TPMT template",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    cases.append(TestCase(
        id="A-85", name="NL: towdpoint plaza jobs",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "towdpoint plaza jobs configuration",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    # Search with long NL prompts
    cases.append(TestCase(
        id="A-86", name="NL: verbose CMBS prompt",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "I need to find all the jobs that are related to CMBS commercial mortgage backed securities data processing in our email monitoring system",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(5)],
    ))

    cases.append(TestCase(
        id="A-87", name="NL: verbose newrez prompt",
        tags=["jobs", "search", "nl", "tier5"],
        command="search_jobs",
        args={"query": "can you show me every job that involves newrez or new residential as the email sender for our file reception portal",
              "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_jobs_array, check_job_count_min(2)],
    ))

    # Validate edge cases
    cases.append(TestCase(
        id="A-88", name="validate nonexistent file",
        tags=["validate", "edge", "tier5"],
        command="validate_xml",
        args={"settings_path": "C:\\nonexistent\\Settings.ps1", "xml_type": "email"},
        checks=[lambda d: (d.get("success") is False or "error" in str(d).lower(),
                           "expected failure for nonexistent file")],
    ))

    # Status variants
    cases.append(TestCase(
        id="A-89", name="status repeated call",
        tags=["status", "edge", "tier5"],
        command="status",
        args={},
        checks=[check_success, check_has_data,
                check_field_exists("data", "version")],
    ))

    # More servicer dossier
    cases.append(TestCase(
        id="A-90", name="dossier by servicer 150 (SFTP)",
        tags=["dossier", "tier5"],
        command="servicer_dossier",
        args={"servicer_id": "150", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-91", name="dossier COOFS_LateMoney",
        tags=["dossier", "tier5"],
        command="servicer_dossier",
        args={"job_name": "COOFS_LateMoney", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-92", name="dossier FMSCRT_NewRez",
        tags=["dossier", "tier5"],
        command="servicer_dossier",
        args={"job_name": "FMSCRT_NewRez", "settings_path": str(EMAIL_SETTINGS)},
        checks=[check_success, check_has_data],
    ))

    # More analyze tests
    cases.append(TestCase(
        id="A-93", name="analyze_impact change_filter",
        tags=["analyze", "tier5"],
        command="analyze_impact",
        args={"settings_path": str(EMAIL_SETTINGS),
              "change_type": "change_filter",
              "target_job": "TPMT_SLS_6601",
              "new_value": "@newdomain.com"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-94", name="analyze_health SFTP",
        tags=["analyze", "sftp", "tier5"],
        command="analyze_health",
        args={"settings_path": str(SFTP_SETTINGS), "type": "sftp",
              "db_path": str(TEMP_DB)},
        checks=[check_success, check_has_data],
    ))

    # More NL search phrasings
    nl_extra = [
        ("A-95", "NL: USBankGSFA shared mailbox", "USBankGSFABSMailboxShared", 1),
        ("A-96", "NL: NBResiFunds email monitoring", "NBResiFunds monitoring", 1),
        ("A-97", "NL: jobs saving to EmailExtract subfolder", "saving EmailExtract subfolder", 5),
        ("A-98", "NL: all queue-one-file true jobs", "QueueOneFile True", 5),
        ("A-100", "NL: which jobs use Scrubber template", "Scrubber template", 5),
    ]
    for tid, name, query, min_count in nl_extra:
        cases.append(TestCase(
            id=tid, name=name, tags=["jobs", "search", "nl", "tier5"],
            command="search_jobs",
            args={"query": query, "settings_path": str(EMAIL_SETTINGS)},
            checks=[check_success, check_jobs_array, check_job_count_min(min_count)],
        ))

    # A-99 standalone — needs SFTP settings since Ocwen is only in SFTP config
    cases.append(TestCase(
        id="A-99", name="NL: Ocwen SFTP job search",
        tags=["jobs", "search", "sftp", "tier5"],
        command="search_jobs",
        args={"query": "Ocwen", "settings_path": str(EMAIL_SETTINGS),
              "sftp_settings_path": str(SFTP_SETTINGS), "xml_type": "all"},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    # ---------------------------------------------------------------
    # TIER 5 continued: Cross-command consistency checks
    # ---------------------------------------------------------------
    cases.append(TestCase(
        id="A-101", name="validate then search same file",
        tags=["validate", "search", "consistency", "tier5"],
        command="validate_xml",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[check_success, check_has_data, check_has_validation],
    ))

    cases.append(TestCase(
        id="A-102", name="list_backups SFTP",
        tags=["backups", "sftp", "tier5"],
        command="list_backups",
        args={"settings_path": str(SFTP_SETTINGS), "xml_type": "sftp"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-103", name="log_performance with settings",
        tags=["logs", "tier5"],
        command="log_performance",
        args={"db_path": str(TEMP_DB), "settings_path": str(EMAIL_SETTINGS),
              "sort": "success_rate", "top": "10"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-104", name="log_daily_summary with date",
        tags=["logs", "tier5"],
        command="log_daily_summary",
        args={"db_path": str(TEMP_DB), "date": "2026-02-10"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-105", name="log_daily_summary future date",
        tags=["logs", "edge", "tier5"],
        command="log_daily_summary",
        args={"db_path": str(TEMP_DB), "date": "2099-01-01"},
        checks=[check_success, check_has_data],
    ))

    # More search with SFTP settings combined
    cases.append(TestCase(
        id="A-106", name="search all types Sweep",
        tags=["jobs", "search", "sftp", "tier5"],
        command="search_jobs",
        args={"query": "Sweep", "settings_path": str(EMAIL_SETTINGS),
              "sftp_settings_path": str(SFTP_SETTINGS), "xml_type": "all"},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    cases.append(TestCase(
        id="A-107", name="search sftp-only type",
        tags=["jobs", "search", "sftp", "tier5"],
        command="search_jobs",
        args={"query": "Ocwen", "settings_path": str(EMAIL_SETTINGS),
              "sftp_settings_path": str(SFTP_SETTINGS), "xml_type": "sftp"},
        checks=[check_success, check_jobs_array, check_job_count_min(1)],
    ))

    # NL queries with punctuation and questions
    nl_questions = [
        ("A-108", "NL: what is CMLTI?", "what is CMLTI", 3),
        ("A-109", "NL: where do chase emails go?", "where do chase emails go", 3),
        ("A-110", "NL: who manages the tpmt jobs?", "who manages tpmt", 5),
        ("A-111", "NL: tell me about COOFS monitoring", "tell about COOFS monitoring", 3),
        ("A-112", "NL: Plaza RTL and Fay servicing overlap", "Plaza RTL Fay servicing", 3),
    ]
    for tid, name, query, min_count in nl_questions:
        cases.append(TestCase(
            id=tid, name=name, tags=["jobs", "search", "nl", "tier5"],
            command="search_jobs",
            args={"query": query, "settings_path": str(EMAIL_SETTINGS)},
            checks=[check_success, check_jobs_array, check_job_count_min(min_count)],
        ))

    # Dossier for every major servicer category
    dossier_jobs = [
        ("A-113", "dossier Chase_EMC_6901", "Chase_EMC_6901"),
        ("A-114", "dossier ABS_Deals", "ABS_Deals"),
        ("A-115", "dossier FMSCRT_MrCooper", "FMSCRT_MrCooper"),
    ]
    for tid, name, jname in dossier_jobs:
        cases.append(TestCase(
            id=tid, name=name, tags=["dossier", "tier5"],
            command="servicer_dossier",
            args={"job_name": jname, "settings_path": str(EMAIL_SETTINGS)},
            checks=[check_success, check_has_data],
        ))

    # More log commands with different parameters
    cases.append(TestCase(
        id="A-116", name="log_job_health CMBS_Wells",
        tags=["logs", "tier5"],
        command="log_job_health",
        args={"job_name": "CMBS_Wells", "db_path": str(TEMP_DB), "days": "30"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-117", name="log_did_failures job filter",
        tags=["logs", "tier5"],
        command="log_did_failures",
        args={"db_path": str(TEMP_DB), "days": "30",
              "job_filter": "TPMT"},
        checks=[check_success, check_has_data],
    ))

    cases.append(TestCase(
        id="A-118", name="log_trends 30 days",
        tags=["logs", "tier5"],
        command="log_trends",
        args={"db_path": str(TEMP_DB), "days": "30"},
        checks=[check_success, check_has_data],
    ))

    # Search with combined xml_type parameter
    cases.append(TestCase(
        id="A-119", name="search email xml_type filter",
        tags=["jobs", "search", "tier5"],
        command="search_jobs",
        args={"query": "chase", "settings_path": str(EMAIL_SETTINGS),
              "xml_type": "email"},
        checks=[check_success, check_jobs_array, check_job_count_min(3),
                check_xml_type("email")],
    ))

    cases.append(TestCase(
        id="A-120", name="template_inventory with settings",
        tags=["templates", "tier5"],
        command="template_inventory",
        args={"settings_path": str(EMAIL_SETTINGS), "xml_type": "email"},
        checks=[check_success, check_has_data],
    ))

    return cases


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class TestRunner:
    """Runs CLI commands via subprocess and evaluates results."""

    def __init__(self, use_exe: bool = True, verbose: bool = False):
        self.verbose = verbose
        if use_exe and EXE_PATH.exists():
            self.cmd_prefix = [str(EXE_PATH)]
            self.cwd = None
            self.mode = "exe"
        elif PYTHON_PATH.exists():
            self.cmd_prefix = [str(PYTHON_PATH), "-m", "cli.main"]
            self.cwd = str(PROJECT_ROOT)
            self.mode = "python"
        else:
            raise RuntimeError("Neither exe nor python venv found")

    def _build_args(self, command: str, args: Dict[str, Any]) -> List[str]:
        """Convert command + dict to CLI arg list."""
        cli_args = [command]
        for key, value in args.items():
            flag = "--" + key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    cli_args.append(flag)
            elif value is not None and value != "":
                cli_args.extend([flag, str(value)])
        return cli_args

    def run(self, test: TestCase) -> TestResult:
        """Execute a single test case and return scored result."""
        cli_args = self._build_args(test.command, test.args)
        full_cmd = self.cmd_prefix + cli_args

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                full_cmd,
                capture_output=True, text=True,
                timeout=30,
                cwd=self.cwd,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            elapsed = (time.perf_counter() - t0) * 1000

            raw = proc.stdout.strip()
            if not raw:
                return TestResult(
                    test_id=test.id, test_name=test.name,
                    score=Score.ERROR, elapsed_ms=elapsed,
                    checks_passed=0, checks_total=len(test.checks),
                    error=f"exit={proc.returncode}, stderr={proc.stderr[:500]}",
                    raw_output=proc.stderr[:500],
                )

            # Parse JSON (take last JSON-like line)
            data = None
            for line in reversed(raw.split("\n")):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

            if data is None:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    return TestResult(
                        test_id=test.id, test_name=test.name,
                        score=Score.ERROR, elapsed_ms=elapsed,
                        checks_passed=0, checks_total=len(test.checks),
                        error="Non-JSON output",
                        raw_output=raw[:500],
                    )

            # Run checks
            details = []
            passed = 0
            for check_fn in test.checks:
                try:
                    ok, reason = check_fn(data)
                    details.append(f"{'✓' if ok else '✗'} {reason}")
                    if ok:
                        passed += 1
                except Exception as e:
                    details.append(f"✗ check raised: {e}")

            total = len(test.checks)
            if passed == total:
                score = Score.PASS
            elif passed > 0:
                score = Score.PARTIAL
            else:
                score = Score.FAIL

            return TestResult(
                test_id=test.id, test_name=test.name,
                score=score, elapsed_ms=elapsed,
                checks_passed=passed, checks_total=total,
                details=details,
                raw_output=raw[:2000] if self.verbose else "",
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - t0) * 1000
            return TestResult(
                test_id=test.id, test_name=test.name,
                score=Score.ERROR, elapsed_ms=elapsed,
                checks_passed=0, checks_total=len(test.checks),
                error="TIMEOUT (30s)",
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return TestResult(
                test_id=test.id, test_name=test.name,
                score=Score.ERROR, elapsed_ms=elapsed,
                checks_passed=0, checks_total=len(test.checks),
                error=str(e),
            )


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def print_report(results: List[TestResult], mode: str):
    """Print a formatted test report."""
    ICONS = {Score.PASS: "✅", Score.PARTIAL: "⚠️", Score.FAIL: "❌", Score.ERROR: "💥"}

    print()
    print("=" * 80)
    print(f"  FRP Agent Test Bench — Environment A ({mode} mode)")
    print("=" * 80)
    print()

    # Table header
    print(f"{'ID':<7} {'Score':<4} {'Checks':<8} {'Time':>8}  {'Name'}")
    print("-" * 80)

    for r in results:
        icon = ICONS[r.score]
        checks = f"{r.checks_passed}/{r.checks_total}"
        time_str = f"{r.elapsed_ms:.0f}ms"
        print(f"{r.test_id:<7} {icon:<4} {checks:<8} {time_str:>8}  {r.test_name}")

        if r.score not in (Score.PASS,):
            for d in r.details:
                if d.startswith("✗"):
                    print(f"        {d}")
            if r.error:
                print(f"        ERROR: {r.error[:120]}")

        if r.raw_output:
            print(f"        OUTPUT: {r.raw_output[:200]}")

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.score == Score.PASS)
    partial = sum(1 for r in results if r.score == Score.PARTIAL)
    failed = sum(1 for r in results if r.score == Score.FAIL)
    errors = sum(1 for r in results if r.score == Score.ERROR)
    avg_ms = sum(r.elapsed_ms for r in results) / total if total else 0

    pct = (passed / total * 100) if total else 0

    print()
    print("=" * 80)
    print(f"  SUMMARY: {passed}/{total} PASS ({pct:.1f}%)  |  "
          f"⚠️ {partial} PARTIAL  |  ❌ {failed} FAIL  |  💥 {errors} ERROR")
    print(f"  Avg time: {avg_ms:.0f}ms  |  Total time: {sum(r.elapsed_ms for r in results)/1000:.1f}s")
    print("=" * 80)
    print()

    # Letter grade
    if pct >= 95:
        grade = "A+"
    elif pct >= 90:
        grade = "A"
    elif pct >= 80:
        grade = "B"
    elif pct >= 70:
        grade = "C"
    elif pct >= 60:
        grade = "D"
    else:
        grade = "F"
    print(f"  GRADE: {grade}  ({pct:.1f}%)")
    print()

    return passed == total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FRP Agent CLI Test Bench")
    parser.add_argument("--exe", action="store_true", help="Force exe mode")
    parser.add_argument("--python", action="store_true", help="Force python mode")
    parser.add_argument("--tag", type=str, help="Run only tests with this tag")
    parser.add_argument("--tier", type=int, help="Run tests up to this tier (1, 2, 3)")
    parser.add_argument("--verbose", action="store_true", help="Show raw JSON output")
    parser.add_argument("--id", type=str, help="Run a specific test by ID (e.g. A-01)")
    args = parser.parse_args()

    use_exe = not args.python  # default to exe unless --python
    if args.exe:
        use_exe = True

    runner = TestRunner(use_exe=use_exe, verbose=args.verbose)
    print(f"[*] Backend mode: {runner.mode}")
    print(f"[*] Exe path: {EXE_PATH}")
    print(f"[*] Email settings: {EMAIL_SETTINGS}")
    print(f"[*] SFTP settings: {SFTP_SETTINGS}")

    cases = build_test_cases()

    # Filter
    if args.id:
        cases = [c for c in cases if c.id == args.id]
    if args.tag:
        cases = [c for c in cases if args.tag in c.tags]
    if args.tier:
        tier_tags = {f"tier{i}" for i in range(1, args.tier + 1)}
        cases = [c for c in cases if any(t in c.tags for t in tier_tags)]

    print(f"[*] Running {len(cases)} test(s)...\n")

    results = []
    for tc in cases:
        r = runner.run(tc)
        results.append(r)
        # Live progress
        icon = {Score.PASS: "✅", Score.PARTIAL: "⚠️", Score.FAIL: "❌", Score.ERROR: "💥"}[r.score]
        sys.stdout.write(f"  {icon} {r.test_id} {r.test_name}\n")
        sys.stdout.flush()

    all_passed = print_report(results, runner.mode)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
