"""A-01: Job consolidation analysis.

Groups jobs by shared configuration signature (mailbox, parser, template)
and identifies merge candidates with safety assessments.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from backend.analysis.models import (
    ConsolidationCandidate,
    ConsolidationGroup,
    ConsolidationReport,
)

logger = logging.getLogger(__name__)


class ConsolidationAnalyzer:
    """Identify jobs that share configuration and could be consolidated."""

    def __init__(self, parser, deal_repo=None) -> None:
        """
        Args:
            parser: SettingsXmlParser instance (Phase 1).
            deal_repo: DealRepository instance (Phase 1) — optional.
        """
        self._parser = parser
        self._deal_repo = deal_repo

    def analyze(self, xml_type: str = "all") -> ConsolidationReport:
        """
        Group jobs by configuration signature and produce a report.

        Args:
            xml_type: "email", "sftp", or "all".

        Returns:
            ConsolidationReport with consolidation groups.
        """
        jobs = self._get_jobs(xml_type)
        if not jobs:
            return ConsolidationReport(xml_type_analyzed=xml_type)

        # Group by signature
        sig_map: Dict[Tuple, List] = defaultdict(list)
        for job in jobs:
            sig = self._extract_signature(job)
            sig_map[sig].append(job)

        # Filter to groups with 2+ members
        groups: List[ConsolidationGroup] = []
        group_id = 0
        for sig, job_list in sig_map.items():
            if len(job_list) < 2:
                continue

            group_id += 1
            mailbox, parser_class, template_name = sig

            # Build candidates
            candidates: List[ConsolidationCandidate] = []
            for job in job_list:
                jname = self._get_job_name(job)
                sid = self._get_servicer_id(job)
                did_count = 0
                if sid and self._deal_repo:
                    try:
                        dids = self._deal_repo.get_deals_by_company(int(sid))
                        did_count = len(dids)
                    except Exception:
                        pass

                candidates.append(
                    ConsolidationCandidate(
                        name=jname,
                        servicer_id=sid,
                        did_count=did_count,
                        unique_attributes=self._extract_unique_attributes(job, sig),
                    )
                )

            # Assess merge safety
            recommendation, rationale = self._assess_merge_safety(candidates, sig)
            total_dids = sum(c.did_count for c in candidates)

            groups.append(
                ConsolidationGroup(
                    group_id=group_id,
                    shared_mailbox=mailbox,
                    shared_parser=parser_class,
                    shared_template=template_name,
                    jobs=candidates,
                    total_dids_affected=total_dids,
                    merge_recommendation=recommendation,
                    rationale=rationale,
                )
            )

        # Sort by total_dids_affected descending
        groups.sort(key=lambda g: g.total_dids_affected, reverse=True)

        return ConsolidationReport(
            groups=groups,
            total_groups=len(groups),
            total_jobs_affected=sum(len(g.jobs) for g in groups),
            total_dids_affected=sum(g.total_dids_affected for g in groups),
            xml_type_analyzed=xml_type,
        )

    # ─── Internal ─────────────────────────────────────────────────

    def _get_jobs(self, xml_type: str) -> List:
        """Get filtered job list from parser."""
        try:
            all_jobs = self._parser.get_all_jobs()
        except Exception as e:
            logger.warning(f"Failed to get jobs from parser: {e}")
            return []

        if xml_type == "all":
            return list(all_jobs)

        result = []
        for job in all_jobs:
            jtype = getattr(job, "xml_type", None) or getattr(job, "type", "email")
            if str(jtype).lower() == xml_type.lower():
                result.append(job)
        return result

    def _extract_signature(self, job) -> Tuple[str, str, str]:
        """Extract (mailbox, parser_class, template_name) tuple."""
        # Mailbox / path
        mailbox = (
            getattr(job, "mailbox", None)
            or getattr(job, "folder", None)
            or getattr(job, "path", None)
            or "unknown"
        )

        # Parser class
        parsers = getattr(job, "parsers", None) or []
        parser_class = "unknown"
        if parsers:
            if isinstance(parsers, list) and len(parsers) > 0:
                first = parsers[0]
                if isinstance(first, dict):
                    parser_class = first.get("type", "unknown")
                else:
                    parser_class = getattr(first, "type", None) or type(first).__name__
            elif isinstance(parsers, dict):
                parser_class = next(iter(parsers.keys()), "unknown")

        # Template name
        templates = getattr(job, "templates", None) or {}
        if isinstance(templates, dict):
            template_name = next(iter(templates.values()), "none") if templates else "none"
        elif isinstance(templates, list) and templates:
            template_name = str(templates[0])
        else:
            template_name = "none"

        return (str(mailbox).lower(), str(parser_class).lower(), str(template_name).lower())

    def _extract_unique_attributes(self, job, sig: Tuple) -> Dict[str, str]:
        """Extract attributes that differ from the group's shared signature."""
        attrs: Dict[str, str] = {}

        sf = getattr(job, "sender_filter", None) or getattr(job, "SenderFilter", None)
        if sf:
            attrs["SenderFilter"] = str(sf)

        subf = getattr(job, "subject_filter", None) or getattr(job, "SubjectFilter", None)
        if subf:
            attrs["SubjectFilter"] = str(subf)

        att = getattr(job, "attachment_filter", None) or getattr(job, "AttachmentFilter", None)
        if att:
            attrs["AttachmentFilter"] = str(att)

        q = getattr(job, "queue_one_file", None) or getattr(job, "QueueOneFile", None)
        if q:
            attrs["QueueOneFile"] = str(q)

        da = getattr(job, "day_adjust", None) or getattr(job, "DayAdjust", None)
        if da:
            attrs["DayAdjust"] = str(da)

        return attrs

    def _get_job_name(self, job) -> str:
        return str(getattr(job, "name", None) or getattr(job, "job_name", "unknown"))

    def _get_servicer_id(self, job) -> Optional[str]:
        sid = getattr(job, "servicer_id", None) or getattr(job, "ServicerID", None)
        return str(sid) if sid else None

    def _assess_merge_safety(
        self,
        candidates: List[ConsolidationCandidate],
        sig: Tuple,
    ) -> Tuple[str, str]:
        """Evaluate how safe it would be to merge this group.

        Returns:
            (recommendation, rationale) tuple
        """
        unique_attr_sets = [
            frozenset(c.unique_attributes.items()) for c in candidates
        ]

        all_same_attrs = len(set(unique_attr_sets)) <= 1

        sids = [c.servicer_id for c in candidates if c.servicer_id]
        unique_sids = set(sids)
        has_sid_overlap = len(sids) != len(unique_sids)

        has_process_level = any(c.servicer_id is None for c in candidates)

        if has_process_level:
            return (
                "risky",
                f"Group contains process/shelf-level jobs (no ServicerID). "
                f"These serve a different purpose and should not be merged.",
            )

        if has_sid_overlap:
            return (
                "risky",
                f"Group has overlapping ServicerIDs — same servicer mapped to "
                f"multiple jobs with identical config. Investigate for duplicates.",
            )

        if all_same_attrs:
            return (
                "safe",
                f"All {len(candidates)} jobs share identical parser config. "
                f"Only ServicerID differs. Could be consolidated into a single "
                f"multi-deal job if DID mappings are updated.",
            )

        differing = set()
        for c in candidates:
            differing.update(c.unique_attributes.keys())
        return (
            "review",
            f"Jobs share core config but differ in: {', '.join(sorted(differing))}. "
            f"Manual review required to determine if differences are significant.",
        )
