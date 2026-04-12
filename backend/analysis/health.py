"""A-03: Full system health check.

Orchestrates all diagnostic checks from Phases 1-4 into a single
weighted health report with per-section scores and action items.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from backend.analysis.models import HealthSection, HealthReport

logger = logging.getLogger(__name__)

# Section weights (must sum to 1.0)
SECTION_WEIGHTS = {
    "xml_validation": 0.15,
    "coverage_rate": 0.20,
    "orphan_dids": 0.10,
    "importdid_collisions": 0.10,
    "template_distribution": 0.05,
    "log_freshness": 0.10,
    "did_failure_rate": 0.10,
    "job_performance": 0.15,
    "recent_errors": 0.05,
}

# Overall status thresholds
HEALTHY_THRESHOLD = 90.0
ATTENTION_THRESHOLD = 70.0


class HealthChecker:
    """Orchestrate all diagnostic checks into a unified health report."""

    def __init__(
        self,
        parser=None,
        deal_repo=None,
        analytics=None,
        coverage_analyzer=None,
        orphan_detector=None,
        collision_detector=None,
        benchmarker=None,
    ) -> None:
        self._parser = parser
        self._deal_repo = deal_repo
        self._analytics = analytics
        self._coverage = coverage_analyzer
        self._orphans = orphan_detector
        self._collisions = collision_detector
        self._benchmarker = benchmarker

    def check(self, xml_type: str = "all") -> HealthReport:
        """Run all health checks and produce a unified report.

        Args:
            xml_type: "email", "sftp", or "all"

        Returns:
            HealthReport with per-section scores and overall grade
        """
        sections: list[HealthSection] = []

        sections.append(self._check_xml_validation(xml_type))
        sections.append(self._check_coverage_rate())
        sections.append(self._check_orphan_dids())
        sections.append(self._check_collisions())
        sections.append(self._check_template_distribution())
        sections.append(self._check_log_freshness())
        sections.append(self._check_did_failures())
        sections.append(self._check_job_performance())
        sections.append(self._check_recent_errors())

        overall_score = sum(s.score * s.weight for s in sections)

        if overall_score >= HEALTHY_THRESHOLD:
            overall_status = "Healthy"
        elif overall_score >= ATTENTION_THRESHOLD:
            overall_status = "Attention Needed"
        else:
            overall_status = "Action Required"

        return HealthReport(
            sections=sections,
            overall_score=round(overall_score, 1),
            overall_status=overall_status,
            generated_at=datetime.now().isoformat(),
            xml_type=xml_type,
        )

    # ─── Section Checkers ─────────────────────────────────────────

    def _check_xml_validation(self, xml_type: str) -> HealthSection:
        weight = SECTION_WEIGHTS["xml_validation"]
        try:
            if not self._parser:
                return self._unavailable_section("XML Validation", weight, "Parser not configured")

            result = self._parser.validate()
            errors = getattr(result, "errors", []) if result else []
            warnings = getattr(result, "warnings", []) if result else []
            error_count = len(errors) if isinstance(errors, list) else 0
            warning_count = len(warnings) if isinstance(warnings, list) else 0

            score = max(0.0, 100.0 - (error_count * 20) - (warning_count * 5))
            actions = []
            if error_count > 0:
                actions.append(f"Fix {error_count} XML validation error(s): @frp /jobs validate")

            return HealthSection(
                name="XML Validation",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{error_count} error(s), {warning_count} warning(s)",
                details={"errors": error_count, "warnings": warning_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("XML Validation", weight, str(e))

    def _check_coverage_rate(self) -> HealthSection:
        weight = SECTION_WEIGHTS["coverage_rate"]
        try:
            if not self._coverage:
                return self._unavailable_section("Coverage Rate", weight, "CoverageAnalyzer not configured")

            result = self._coverage.analyze()
            total = getattr(result, "total_dids", 0)
            covered = getattr(result, "covered_dids", 0)
            rate = (covered / total * 100) if total > 0 else 100.0
            gaps = total - covered

            actions = []
            if gaps > 0:
                actions.append(f"Review {gaps} coverage gap(s): @frp /deals gaps")

            return HealthSection(
                name="Coverage Rate",
                status=self._score_to_status(rate),
                score=round(rate, 1),
                weight=weight,
                summary=f"{covered} of {total} DIDs covered ({rate:.1f}%)",
                details={"covered": covered, "total": total, "gaps": gaps},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Coverage Rate", weight, str(e))

    def _check_orphan_dids(self) -> HealthSection:
        weight = SECTION_WEIGHTS["orphan_dids"]
        try:
            if not self._orphans:
                return self._unavailable_section("Orphan DIDs", weight, "OrphanDetector not configured")

            result = self._orphans.detect()
            orphan_count = getattr(result, "orphan_count", 0) if result else 0
            score = max(0.0, 100.0 - (orphan_count * 5))

            actions = []
            if orphan_count > 0:
                actions.append(f"Resolve {orphan_count} orphan(s): @frp /deals orphans")

            return HealthSection(
                name="Orphan DIDs",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{orphan_count} orphan DID(s) found",
                details={"orphan_count": orphan_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Orphan DIDs", weight, str(e))

    def _check_collisions(self) -> HealthSection:
        weight = SECTION_WEIGHTS["importdid_collisions"]
        try:
            if not self._collisions:
                return self._unavailable_section("ImportDID Collisions", weight, "CollisionDetector not configured")

            result = self._collisions.detect()
            collision_count = getattr(result, "collision_count", 0) if result else 0
            score = max(0.0, 100.0 - (collision_count * 10))

            actions = []
            if collision_count > 0:
                actions.append(f"Review {collision_count} collision(s): @frp /deals collisions")

            return HealthSection(
                name="ImportDID Collisions",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{collision_count} ImportDID collision(s) detected",
                details={"collision_count": collision_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("ImportDID Collisions", weight, str(e))

    def _check_template_distribution(self) -> HealthSection:
        weight = SECTION_WEIGHTS["template_distribution"]
        try:
            if not self._parser:
                return self._unavailable_section("Template Distribution", weight, "Parser not configured")

            jobs = self._parser.get_all_jobs()
            template_names = set()
            for job in jobs:
                templates = getattr(job, "templates", None) or {}
                if isinstance(templates, dict):
                    template_names.update(templates.values())
                elif isinstance(templates, list):
                    template_names.update(str(t) for t in templates)

            return HealthSection(
                name="Template Distribution",
                status="pass",
                score=100.0,
                weight=weight,
                summary=f"{len(template_names)} unique template(s) across {len(jobs)} jobs",
                details={"template_count": len(template_names), "job_count": len(jobs)},
                action_items=[],
            )
        except Exception as e:
            return self._error_section("Template Distribution", weight, str(e))

    def _check_log_freshness(self) -> HealthSection:
        weight = SECTION_WEIGHTS["log_freshness"]
        try:
            if not self._analytics:
                return self._unavailable_section("Log Freshness", weight, "LogAnalytics not configured — run @frp /logs sync")

            staleness = self._analytics.check_staleness()
            if staleness is None:
                return HealthSection(
                    name="Log Freshness",
                    status="pass",
                    score=100.0,
                    weight=weight,
                    summary="Log index is up to date",
                    details={"stale": False},
                    action_items=[],
                )

            warning_msg = staleness.get("warning", "")
            if "never been synced" in warning_msg:
                score = 0.0
            else:
                m = re.search(r"(\d+)\s*hours", warning_msg)
                hours = int(m.group(1)) if m else 48
                if hours <= 24:
                    score = 100.0
                elif hours <= 48:
                    score = 50.0
                else:
                    score = 0.0

            return HealthSection(
                name="Log Freshness",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=warning_msg or "Log index stale",
                details={"stale": True, "warning": warning_msg},
                action_items=["Sync logs: @frp /logs sync"],
            )
        except Exception as e:
            return self._error_section("Log Freshness", weight, str(e))

    def _check_did_failures(self) -> HealthSection:
        weight = SECTION_WEIGHTS["did_failure_rate"]
        try:
            if not self._analytics:
                return self._unavailable_section("DID Failure Rate", weight, "LogAnalytics not configured")

            failures = self._analytics.did_failures(days=7)
            failure_count = len(failures)
            total_occurrences = sum(f.failure_count for f in failures)
            score = max(0.0, 100.0 - (total_occurrences * 2))

            actions = []
            if failure_count > 0:
                actions.append(f"Review {failure_count} failing keyword(s): @frp /logs failures")

            return HealthSection(
                name="DID Failure Rate",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{total_occurrences} DID mapping failure(s) across {failure_count} keyword(s) (last 7 days)",
                details={"unique_failures": failure_count, "total_occurrences": total_occurrences},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("DID Failure Rate", weight, str(e))

    def _check_job_performance(self) -> HealthSection:
        weight = SECTION_WEIGHTS["job_performance"]
        try:
            if not self._benchmarker:
                return self._unavailable_section("Job Performance", weight, "PerformanceBenchmarker not configured")

            summary = self._benchmarker.benchmark(days=7)
            avg_rate = summary.avg_success_rate
            critical = summary.critical_count

            actions = []
            if critical > 0:
                actions.append(f"Investigate {critical} critical job(s): @frp /logs performance --sort success_rate")

            return HealthSection(
                name="Job Performance",
                status=self._score_to_status(avg_rate),
                score=avg_rate,
                weight=weight,
                summary=f"Average success rate: {avg_rate:.1f}% ({summary.healthy_count} healthy, "
                        f"{summary.warning_count} warning, {critical} critical)",
                details={
                    "avg_success_rate": avg_rate,
                    "healthy": summary.healthy_count,
                    "warning": summary.warning_count,
                    "critical": critical,
                    "unknown": summary.unknown_count,
                },
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Job Performance", weight, str(e))

    def _check_recent_errors(self) -> HealthSection:
        weight = SECTION_WEIGHTS["recent_errors"]
        try:
            if not self._analytics:
                return self._unavailable_section("Recent Errors", weight, "LogAnalytics not configured")

            summary = self._analytics.daily_summary()
            error_count = summary.total_errors
            score = max(0.0, 100.0 - (error_count * 10))

            actions = []
            if error_count > 0:
                actions.append(f"Review today's errors: @frp /logs summary")

            return HealthSection(
                name="Recent Errors",
                status=self._score_to_status(score),
                score=score,
                weight=weight,
                summary=f"{error_count} error(s) today",
                details={"error_count": error_count},
                action_items=actions,
            )
        except Exception as e:
            return self._error_section("Recent Errors", weight, str(e))

    # ─── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _score_to_status(score: float) -> str:
        if score >= 90:
            return "pass"
        elif score >= 70:
            return "warning"
        return "fail"

    @staticmethod
    def _unavailable_section(name: str, weight: float, reason: str) -> HealthSection:
        return HealthSection(
            name=name,
            status="warning",
            score=50.0,
            weight=weight,
            summary=f"Unable to check: {reason}",
            details={"unavailable": True, "reason": reason},
            action_items=[],
        )

    @staticmethod
    def _error_section(name: str, weight: float, error: str) -> HealthSection:
        return HealthSection(
            name=name,
            status="fail",
            score=0.0,
            weight=weight,
            summary=f"Check failed: {error}",
            details={"error": error},
            action_items=[],
        )
