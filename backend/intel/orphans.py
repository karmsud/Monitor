"""Orphan detection — find XML jobs whose ServicerID has no database match."""

from __future__ import annotations

import logging
from typing import List, Optional, Set, Union

from backend.db.deal_repo import DealRepository
from backend.xml.models import EmailJob, SftpJob
from backend.xml.parser import SettingsXmlParser

from .models import OrphanResult

logger = logging.getLogger("frp.intel.orphans")


class OrphanDetector:
    """Detect jobs in Settings.xml that reference nonexistent or empty servicers.

    A job is considered orphaned when:
    * Its ServicerID does not appear in the database at all (``no_db_match``).
    * Its ServicerID exists in the database but has zero deal rows (``no_deal_data``).
    * Its ServicerID is invalid (non-numeric, negative, etc.) (``invalid_servicer_id``).

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

    def detect(self) -> List[OrphanResult]:
        """Scan all jobs and return those identified as orphans.

        Returns
        -------
        list[OrphanResult]
        """
        parser = SettingsXmlParser(self.settings_path)
        all_jobs = parser.get_all_jobs()

        # Pre-fetch all known servicer IDs from the database
        known_ids: Set[int] = self.deal_repo.get_all_servicer_ids()

        orphans: List[OrphanResult] = []

        for job in all_jobs:
            result = self._check_job(job, known_ids)
            if result is not None:
                orphans.append(result)

        logger.info(
            "Orphan scan complete: %d orphan(s) out of %d job(s)",
            len(orphans),
            len(all_jobs),
        )
        return orphans

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _check_job(
        self,
        job: Union[EmailJob, SftpJob],
        known_ids: Set[int],
    ) -> Optional[OrphanResult]:
        """Check a single job for orphan status."""
        raw_sid = getattr(job, "servicer_id", None)

        # Jobs without a servicer_id are not orphans — they're shelf-level
        if raw_sid is None or (isinstance(raw_sid, int) and raw_sid == 0):
            return None

        # Validate the servicer_id
        try:
            sid_int = int(raw_sid)
        except (ValueError, TypeError):
            return OrphanResult(
                job_name=job.name,
                servicer_id=-1,
                reason="invalid_servicer_id",
                xml_type=job.xml_type,
            )

        if sid_int <= 0:
            return OrphanResult(
                job_name=job.name,
                servicer_id=sid_int,
                reason="invalid_servicer_id",
                xml_type=job.xml_type,
            )

        # Check if ServicerID exists in the database
        if sid_int not in known_ids:
            return OrphanResult(
                job_name=job.name,
                servicer_id=sid_int,
                reason="no_db_match",
                xml_type=job.xml_type,
            )

        # ServicerID exists but check if it has actual deal data
        deals = self.deal_repo.get_deals_by_company(sid_int)
        if not deals:
            return OrphanResult(
                job_name=job.name,
                servicer_id=sid_int,
                reason="no_deal_data",
                xml_type=job.xml_type,
            )

        return None
