"""A-02: Change impact simulation.

Simulates the effect of a proposed configuration change without
modifying any files. Analyzes coverage impact, affected entities,
and recent activity to produce a risk assessment.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from backend.analysis.models import (
    ChangeSpec,
    AffectedEntity,
    ImpactReport,
)

logger = logging.getLogger(__name__)


class ImpactSimulator:
    """Simulate impact of proposed configuration changes."""

    RECENT_ACTIVITY_DAYS = 7

    def __init__(self, parser, deal_repo=None, analytics=None) -> None:
        """
        Args:
            parser: SettingsXmlParser instance (Phase 1)
            deal_repo: DealRepository instance (Phase 1) — optional
            analytics: LogAnalytics instance (Phase 3) — optional
        """
        self._parser = parser
        self._deal_repo = deal_repo
        self._analytics = analytics

    def simulate(self, change: ChangeSpec) -> ImpactReport:
        """Execute the impact simulation for a given change specification.

        Args:
            change: ChangeSpec describing the proposed change

        Returns:
            ImpactReport with affected entities and risk assessment

        Raises:
            ValueError: If change_type is unknown or target not found
        """
        handler = {
            "delete_job": self._sim_delete_job,
            "rename_did": self._sim_rename_did,
            "change_filter": self._sim_change_filter,
            "move_servicer": self._sim_move_servicer,
        }.get(change.change_type)

        if not handler:
            raise ValueError(
                f"Unknown change_type '{change.change_type}'. "
                f"Supported: delete_job, rename_did, change_filter, move_servicer"
            )

        return handler(change)

    # ─── Delete Job Simulation ────────────────────────────────────

    def _sim_delete_job(self, change: ChangeSpec) -> ImpactReport:
        if not change.target_job:
            raise ValueError("target_job is required for delete_job")

        job = self._find_job(change.target_job)
        if not job:
            raise ValueError(f"Job '{change.target_job}' not found in Settings.xml")

        sid = self._get_servicer_id(job)
        affected: List[AffectedEntity] = []
        coverage_before = 0
        coverage_after = 0

        if sid and self._deal_repo:
            try:
                dids = self._deal_repo.get_deals_by_company(int(sid))
                coverage_before = len(dids)

                all_jobs = self._parser.get_all_jobs()
                other_sids = set()
                for j in all_jobs:
                    j_name = self._get_job_name(j)
                    j_sid = self._get_servicer_id(j)
                    if j_name != change.target_job and j_sid:
                        other_sids.add(j_sid)

                covered_elsewhere = 0
                for did_row in dids:
                    did_name = did_row.get("DID", did_row.get("did", "unknown"))
                    import_did = did_row.get("ImportDID", did_row.get("import_did", ""))

                    other_coverage = self._check_did_other_coverage(did_row, other_sids)

                    if other_coverage:
                        affected.append(AffectedEntity(
                            entity_type="deal",
                            identifier=str(did_name),
                            detail=f"Also covered by job '{other_coverage}' via another ServicerID",
                            severity="low",
                        ))
                        covered_elsewhere += 1
                    else:
                        affected.append(AffectedEntity(
                            entity_type="deal",
                            identifier=str(did_name),
                            detail=f"Would lose coverage — no other job handles ImportDID '{import_did}'",
                            severity="high",
                        ))

                coverage_after = covered_elsewhere
            except (ValueError, Exception) as e:
                logger.warning(f"DID lookup failed for ServicerID {sid}: {e}")
                affected.append(AffectedEntity(
                    entity_type="job",
                    identifier=change.target_job,
                    detail=f"Could not verify DID coverage: {e}",
                    severity="medium",
                ))
        elif not sid:
            affected.append(AffectedEntity(
                entity_type="job",
                identifier=change.target_job,
                detail="Process/shelf-level job (no ServicerID). "
                       "Deleting affects all emails matched by this job's filters.",
                severity="medium",
            ))

        recent_activity = self._check_recent_activity(change.target_job)
        high_count = sum(1 for a in affected if a.severity == "high")
        risk_level = self._calculate_risk(high_count, recent_activity, coverage_before)
        recommendation = self._generate_delete_recommendation(
            change.target_job, high_count, coverage_before,
            coverage_after, recent_activity
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            coverage_delta=coverage_after - coverage_before,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Rename DID Simulation ────────────────────────────────────

    def _sim_rename_did(self, change: ChangeSpec) -> ImpactReport:
        if not change.target_did or not change.new_value:
            raise ValueError("target_did and new_value are required for rename_did")

        affected: List[AffectedEntity] = []
        coverage_before = 0
        coverage_after = 0

        if self._deal_repo:
            try:
                old_rows = self._deal_repo.get_by_import_did(change.target_did)
                coverage_before = len(old_rows)

                for row in old_rows:
                    did = row.get("DID", "unknown")
                    affected.append(AffectedEntity(
                        entity_type="did_mapping",
                        identifier=f"{did} → {change.target_did}",
                        detail=f"ImportDID would change from '{change.target_did}' to '{change.new_value}'",
                        severity="medium",
                    ))

                new_rows = self._deal_repo.get_by_import_did(change.new_value)
                if new_rows:
                    existing_sids = set(str(r.get("CompanyID", "")) for r in new_rows)
                    old_sids = set(str(r.get("CompanyID", "")) for r in old_rows)
                    if existing_sids != old_sids:
                        affected.append(AffectedEntity(
                            entity_type="did_mapping",
                            identifier=change.new_value,
                            detail=f"COLLISION: ImportDID '{change.new_value}' already exists "
                                   f"for CompanyIDs {existing_sids}. Renaming would create ambiguity.",
                            severity="high",
                        ))

                coverage_after = coverage_before
            except Exception as e:
                logger.warning(f"DID lookup failed: {e}")

        recent_activity = False
        high_count = sum(1 for a in affected if a.severity == "high")
        risk_level = "high" if high_count > 0 else "low"

        recommendation = (
            f"Renaming ImportDID '{change.target_did}' to '{change.new_value}' "
            f"affects {coverage_before} DID mapping(s). "
            + ("WARNING: Collision detected with existing ImportDID." if high_count > 0 else "No collisions detected.")
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            coverage_delta=0,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Change Filter Simulation ─────────────────────────────────

    def _sim_change_filter(self, change: ChangeSpec) -> ImpactReport:
        if not change.target_job:
            raise ValueError("target_job is required for change_filter")

        job = self._find_job(change.target_job)
        if not job:
            raise ValueError(f"Job '{change.target_job}' not found")

        affected: List[AffectedEntity] = []
        sid = self._get_servicer_id(job)
        coverage_before = 0

        if sid and self._deal_repo:
            try:
                dids = self._deal_repo.get_deals_by_company(int(sid))
                coverage_before = len(dids)
            except Exception:
                pass

        affected.append(AffectedEntity(
            entity_type="job",
            identifier=change.target_job,
            detail=f"Filter change: '{change.new_value or 'unspecified'}'. "
                   f"This may affect which emails are matched by this job.",
            severity="medium",
        ))

        recent_activity = self._check_recent_activity(change.target_job)
        risk_level = "medium" if recent_activity else "low"

        recommendation = (
            f"Changing filter on '{change.target_job}' "
            + (f"(ServicerID={sid}, {coverage_before} DIDs). " if sid else ". ")
            + ("Job was active recently — test filter change carefully." if recent_activity
               else "No recent activity — lower risk.")
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_before,
            coverage_delta=0,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Move Servicer Simulation ─────────────────────────────────

    def _sim_move_servicer(self, change: ChangeSpec) -> ImpactReport:
        if not change.target_job or not change.target_company_id:
            raise ValueError("target_job and target_company_id required for move_servicer")

        affected: List[AffectedEntity] = []
        coverage_before = 0

        if self._deal_repo:
            try:
                dids = self._deal_repo.get_deals_by_company(change.target_company_id)
                coverage_before = len(dids)
                for d in dids:
                    affected.append(AffectedEntity(
                        entity_type="deal",
                        identifier=str(d.get("DID", "unknown")),
                        detail=f"DID mapping would move from job '{change.target_job}' "
                               f"to '{change.new_value or 'unspecified'}'",
                        severity="medium",
                    ))
            except Exception as e:
                logger.warning(f"DID lookup failed: {e}")

        recent_activity = self._check_recent_activity(change.target_job)

        dest_job = None
        if change.new_value:
            dest_job = self._find_job(change.new_value)
            if not dest_job:
                affected.append(AffectedEntity(
                    entity_type="job",
                    identifier=change.new_value,
                    detail="Destination job does not exist — would need to be created first.",
                    severity="high",
                ))

        high_count = sum(1 for a in affected if a.severity == "high")
        risk_level = self._calculate_risk(high_count, recent_activity, coverage_before)

        recommendation = (
            f"Moving ServicerID {change.target_company_id} ({coverage_before} DIDs) "
            f"from '{change.target_job}' to '{change.new_value or 'unspecified'}'. "
            + ("Destination job exists." if dest_job else "Destination job NOT found — create it first.")
        )

        return ImpactReport(
            change=change,
            affected=affected,
            coverage_before=coverage_before,
            coverage_after=coverage_before,
            coverage_delta=0,
            recent_activity=recent_activity,
            risk_level=risk_level,
            recommendation=recommendation,
        )

    # ─── Helper Methods ───────────────────────────────────────────

    def _find_job(self, job_name: str):
        """Find a job by name in the parser's job list."""
        for job in self._parser.get_all_jobs():
            name = self._get_job_name(job)
            if name.lower() == job_name.lower():
                return job
        return None

    def _get_job_name(self, job) -> str:
        return str(getattr(job, "name", None) or getattr(job, "job_name", "unknown"))

    def _get_servicer_id(self, job) -> Optional[str]:
        sid = getattr(job, "servicer_id", None) or getattr(job, "ServicerID", None)
        return str(sid) if sid else None

    def _check_recent_activity(self, job_name: str) -> bool:
        """Check if a job had any log activity in the last 7 days."""
        if not self._analytics:
            return False
        try:
            cutoff = (datetime.now() - timedelta(days=self.RECENT_ACTIVITY_DAYS)).isoformat()
            conn = self._analytics._get_conn()
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM log_events
                    WHERE job_name = ? AND timestamp >= ?
                    """,
                    (job_name, cutoff)
                ).fetchone()
                return (row["cnt"] or 0) > 0
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Recent activity check failed: {e}")
            return False

    def _check_did_other_coverage(self, did_row: dict, other_sids: set) -> Optional[str]:
        """Check if a DID is covered by any job other than the one being deleted."""
        if not self._deal_repo:
            return None

        did_name = did_row.get("DID", did_row.get("did"))
        if not did_name:
            return None

        try:
            all_mappings = self._deal_repo.get_by_did(str(did_name))
            for m in all_mappings:
                cid = str(m.get("CompanyID", m.get("company_id", "")))
                if cid in other_sids:
                    return cid
        except Exception:
            pass
        return None

    def _calculate_risk(
        self, high_severity_count: int,
        recent_activity: bool,
        coverage_before: int,
    ) -> str:
        """Calculate overall risk level."""
        if high_severity_count > 0 and recent_activity:
            return "high"
        if high_severity_count > 0 or (recent_activity and coverage_before > 10):
            return "medium"
        return "low"

    def _generate_delete_recommendation(
        self, job_name: str, orphaned_count: int,
        coverage_before: int, coverage_after: int,
        recent_activity: bool,
    ) -> str:
        """Generate human-readable recommendation for job deletion."""
        parts = [f"Deleting job '{job_name}'"]

        if coverage_before > 0:
            parts.append(f"would affect {coverage_before} DID mapping(s)")
            if orphaned_count > 0:
                parts.append(f"— {orphaned_count} DID(s) would lose ALL coverage")
            else:
                parts.append("— all DIDs are covered by other jobs")

        if recent_activity:
            parts.append(". This job processed files in the last 7 days")
        else:
            parts.append(". No recent activity detected")

        if orphaned_count > 0:
            parts.append(". RECOMMENDATION: Migrate affected DIDs before deleting")
        elif not recent_activity and coverage_before == 0:
            parts.append(". Safe to delete — no DIDs and no recent activity")

        return "".join(parts) + "."
