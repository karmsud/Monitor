"""Collision detection — find ImportDID keywords that map to multiple companies."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Union

from backend.db.deal_repo import DealRepository
from backend.xml.models import EmailJob, SftpJob
from backend.xml.parser import SettingsXmlParser

from .models import CollisionResult

logger = logging.getLogger("frp.intel.collisions")


def _get_import_did(job: Union[EmailJob, SftpJob]) -> str:
    """Extract the ImportDID keyword from a job, if available."""
    val = getattr(job, "import_did", None)
    if val:
        return str(val).strip()
    filters = getattr(job, "filters", {})
    if isinstance(filters, dict):
        for key in ("ImportDID", "import_did"):
            if filters.get(key):
                return str(filters[key]).strip()
    return ""


class CollisionDetector:
    """Detect ImportDID keywords that map to more than one CompanyID.

    A collision indicates that a given ImportDID value appears in the
    database under multiple companies, which can cause mis-routing.

    Parameters
    ----------
    settings_path : str
        Path to the Settings.xml file.
    deal_repo : DealRepository
        An open database repository instance.
    xml_type : str
        Either ``'email'`` or ``'sftp'``.
    """

    def __init__(
        self,
        settings_path: str,
        deal_repo: DealRepository,
        xml_type: str = "email",
    ) -> None:
        self.settings_path = settings_path
        self.deal_repo = deal_repo
        self.xml_type = xml_type

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def detect(self) -> List[CollisionResult]:
        """Scan jobs and check each ImportDID keyword for multi-company matches.

        Returns
        -------
        list[CollisionResult]
        """
        parser = SettingsXmlParser(self.settings_path)
        all_jobs = parser.get_all_jobs()

        # Collect unique import_did keywords → affected jobs
        keyword_jobs: Dict[str, List[str]] = defaultdict(list)
        for job in all_jobs:
            kw = _get_import_did(job)
            if kw:
                keyword_jobs[kw].append(job.name)

        collisions: List[CollisionResult] = []

        for keyword, job_names in keyword_jobs.items():
            try:
                collision = self._check_keyword(keyword, job_names)
                if collision is not None:
                    collisions.append(collision)
            except Exception as exc:
                logger.warning(
                    "Error checking keyword '%s': %s", keyword, exc
                )

        logger.info(
            "Collision scan complete: %d collision(s) from %d keyword(s)",
            len(collisions),
            len(keyword_jobs),
        )
        return collisions

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _check_keyword(
        self,
        keyword: str,
        job_names: List[str],
    ) -> Optional[CollisionResult]:
        """Check whether *keyword* maps to multiple companies."""
        matching_companies = self.deal_repo.get_companies_by_import_did(keyword)

        if len(matching_companies) <= 1:
            return None

        # Determine risk level
        risk = "high" if len(matching_companies) >= 3 else "medium"

        # Get deal counts per company
        deal_counts: Dict[int, int] = {}
        for cid in matching_companies:
            deals = self.deal_repo.get_deals_by_company(cid)
            deal_counts[cid] = len(deals)

        return CollisionResult(
            import_did_keyword=keyword,
            matching_company_ids=matching_companies,
            affected_jobs=job_names,
            risk_level=risk,
            deal_counts=deal_counts,
        )
