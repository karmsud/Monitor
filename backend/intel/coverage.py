"""Coverage gap analysis — cross-reference XML jobs with database records."""

from __future__ import annotations

import logging
from typing import List, Optional, Union

from backend.db.deal_repo import DealRepository
from backend.xml.models import EmailJob, SftpJob
from backend.xml.parser import SettingsXmlParser

from .models import CoverageReport

logger = logging.getLogger("frp.intel.coverage")


def _get_import_did(job: Union[EmailJob, SftpJob]) -> str:
    """Extract the ImportDID keyword from a job, if available.

    Checks for a direct ``import_did`` attribute first, then falls back
    to looking inside the ``filters`` dict for ``ImportDID`` keys.
    """
    # Try direct attribute
    val = getattr(job, "import_did", None)
    if val:
        return str(val).strip()
    # Try filters dict
    filters = getattr(job, "filters", {})
    if isinstance(filters, dict):
        for key in ("ImportDID", "import_did"):
            if filters.get(key):
                return str(filters[key]).strip()
    return ""


class CoverageAnalyzer:
    """Analyse how well XML jobs cover the deals in the database.

    For each servicer (CompanyID), it checks whether each DID/ImportDID
    record in the database is "covered" by at least one XML job whose
    ServicerID matches.

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

    def analyze(
        self, servicer_id: Optional[int] = None
    ) -> List[CoverageReport]:
        """Run coverage analysis for one or all servicers.

        Parameters
        ----------
        servicer_id : int, optional
            If given, analyse only this servicer. Otherwise analyse all
            servicers found in the XML jobs.

        Returns
        -------
        list[CoverageReport]
        """
        parser = SettingsXmlParser(self.settings_path)
        all_jobs = parser.get_all_jobs()

        # Build servicer → jobs mapping
        servicer_jobs: dict[int, list] = {}
        for job in all_jobs:
            sid = self._get_servicer_id(job)
            if sid:
                servicer_jobs.setdefault(sid, []).append(job)

        # Determine which servicers to analyse
        if servicer_id is not None:
            target_ids = [servicer_id]
        else:
            target_ids = sorted(servicer_jobs.keys())

        reports: List[CoverageReport] = []
        for sid in target_ids:
            jobs = servicer_jobs.get(sid, [])
            try:
                report = self._analyze_servicer(sid, jobs)
                reports.append(report)
            except Exception as exc:
                logger.warning("Error analysing servicer %d: %s", sid, exc)

        return reports

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _analyze_servicer(
        self,
        servicer_id: int,
        jobs: list,
    ) -> CoverageReport:
        """Analyse coverage for a single servicer."""
        # Get all DID records for this company from the database
        deals = self.deal_repo.get_deals_by_company(servicer_id)

        # Extract all ImportDID keywords from the jobs
        job_keywords: List[str] = []
        for job in jobs:
            kw = _get_import_did(job)
            if kw:
                job_keywords.append(kw.upper())

        total_dids = len(deals)
        mapped = 0
        unmapped: list = []

        for deal in deals:
            did = deal.get("DID", "")
            import_did = deal.get("ImportDID", "")
            if self._is_covered(import_did, job_keywords):
                mapped += 1
            else:
                unmapped.append({"did": did, "import_did": import_did})

        coverage_pct = (mapped / total_dids * 100) if total_dids > 0 else 0.0

        return CoverageReport(
            servicer_id=servicer_id,
            total_dids=total_dids,
            mapped_dids=mapped,
            unmapped_dids=unmapped,
            coverage_percentage=round(coverage_pct, 2),
            matching_jobs=[j.name for j in jobs],
        )

    @staticmethod
    def _is_covered(import_did: str, job_keywords: List[str]) -> bool:
        """Return True if *import_did* matches any of the *job_keywords*."""
        if not import_did or not job_keywords:
            return False
        import_upper = import_did.strip().upper()
        for keyword in job_keywords:
            if keyword in import_upper or import_upper in keyword:
                return True
        return False

    @staticmethod
    def _get_servicer_id(job: Union[EmailJob, SftpJob]) -> Optional[int]:
        """Extract a usable servicer_id from a job (None/0 → None)."""
        sid = getattr(job, "servicer_id", None)
        if isinstance(sid, int) and sid != 0:
            return sid
        if sid is not None and sid:
            try:
                return int(sid)
            except (ValueError, TypeError):
                return None
        return None
