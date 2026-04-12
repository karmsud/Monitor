"""TriageAnalyzer — high-level email triage workflows.

Provides three operations:
- **verify** (E-01): parse + match + coverage check + DID matching + log/staging cross-ref
- **match_only** (E-02): match without .msg file (sender/subject text)
- **analyze_new** (E-03): suggest template for an unmatched email
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.triage.matcher import TriageMatcher
from backend.triage.models import DIDMatch, EmailInfo, MatchResult, TriageResult
from backend.triage.msg_parser import MsgParser
from backend.xml.models import _match_mode
from backend.xml.parser import SettingsXmlParser
from backend.xml.templates import TemplateInventory

logger = logging.getLogger("frp.triage.analyzer")

# Regex to strip date/number tokens from subjects for pattern extraction
_DATE_NUM_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"  # dates like 01/15/2025
    r"|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"    # ISO dates
    r"|\b\d{4,}\b"                           # long numbers
)


class TriageAnalyzer:
    """Orchestrate email triage: parse → match → analyze.

    Parameters
    ----------
    settings_path : str
        Path to the Settings.xml file.
    xml_type : str
        ``'email'`` or ``'sftp'``.
    deal_repo : object, optional
        An open :class:`DealRepository` for coverage lookups.
    log_indexer : object, optional
        An open :class:`LogIndexer` for log cross-reference.
    ts_repo : object, optional
        An open :class:`TemplateStagingRepository` for template run lookups.
    """

    def __init__(
        self,
        settings_path: str,
        xml_type: str = "email",
        deal_repo: object = None,
        log_indexer: object = None,
        ts_repo: object = None,
    ) -> None:
        self._settings_path = settings_path
        self._xml_type = xml_type
        self._deal_repo = deal_repo
        self._log_indexer = log_indexer
        self._ts_repo = ts_repo

        # Parse the settings once
        try:
            self._parser = SettingsXmlParser(settings_path)
            self._jobs = self._parser.get_all_jobs()
        except Exception as exc:
            raise ValueError(f"Failed to parse settings XML: {exc}") from exc

    # ------------------------------------------------------------------ #
    #  E-01: verify
    # ------------------------------------------------------------------ #

    def verify(self, msg_path: str) -> TriageResult:
        """Parse a .msg file and check if it matches an existing job.

        When optional services are available (deal_repo, log_indexer,
        ts_repo) the result includes:

        * **deals** / **did_matches** — ImportDID keyword matches against
          the email subject or attachment filenames.
        * **log_summary** — recent execution stats from the log index.
        * **template_status** — last template-staging runs for the job's
          scrubber template.
        * **confidence** — overall pipeline health assessment.

        Parameters
        ----------
        msg_path : str
            Path to the ``.msg`` file.

        Returns
        -------
        TriageResult
        """
        email_info = MsgParser.parse(msg_path)
        matches = TriageMatcher.match(email_info, self._jobs, self._xml_type)

        result = TriageResult(
            email_info=email_info,
            matches=matches,
            has_match=len(matches) > 0,
        )

        if not matches:
            result.recommendation = (
                "No existing jobs match this email. Consider creating a new job."
            )
            return result

        best = matches[0]
        result.recommendation = (
            f"Email matches {len(matches)} existing job(s). "
            f"Best match: {best.job_name}"
        )

        # Locate the job object for the best match
        job = self._find_job(best.job_name)

        # --- Gap 2A: DID keyword matching -------------------------------- #
        if self._deal_repo is not None and best.servicer_id is not None:
            try:
                sid = int(best.servicer_id)
                deals = self._deal_repo.get_deals_by_company(sid)
                result.deals = deals
                result.did_count = len(deals)
                result.coverage_status = "covered" if deals else "no_deals"

                if deals and job is not None:
                    mode = _match_mode(job.parsers)
                    result.did_matches = self._match_dids_to_email(
                        deals, email_info, mode,
                    )
            except (ValueError, Exception) as exc:
                logger.debug("Coverage / DID matching failed: %s", exc)

        # --- Gap 4: Log cross-reference --------------------------------- #
        if self._log_indexer is not None:
            try:
                result.log_summary = self._log_indexer.get_job_summary(
                    best.job_name,
                )
            except Exception as exc:
                logger.debug("Log summary lookup failed: %s", exc)

        # --- Gap 5: Template-staging cross-reference --------------------- #
        if self._ts_repo is not None and job is not None:
            template_name = self._get_template_name(job)
            if template_name:
                try:
                    result.template_status = self._ts_repo.get_recent_by_query(
                        template_name,
                    )
                except Exception as exc:
                    logger.debug("Template staging lookup failed: %s", exc)

        # --- Confidence assessment --------------------------------------- #
        result.confidence = self._assess_confidence(result)

        return result

    # ------------------------------------------------------------------ #
    #  E-02: match_only
    # ------------------------------------------------------------------ #

    def match_only(
        self,
        msg_path: Optional[str] = None,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> TriageResult:
        """Match by .msg file or raw sender/subject strings.

        At least one of *msg_path*, *sender*, or *subject* must be provided.

        Returns
        -------
        TriageResult
        """
        if msg_path:
            email_info = MsgParser.parse(msg_path)
        elif sender or subject:
            email_info = EmailInfo(
                sender=sender or "",
                sender_name="",
                subject=subject or "",
                date="",
            )
        else:
            raise ValueError(
                "Provide --msg-path, --sender, or --subject for matching."
            )

        matches = TriageMatcher.match(email_info, self._jobs, self._xml_type)

        result = TriageResult(
            email_info=email_info,
            matches=matches,
            has_match=len(matches) > 0,
        )

        if matches:
            result.recommendation = (
                f"Matched {len(matches)} job(s). Best: {matches[0].job_name}"
            )
        else:
            result.recommendation = "No jobs matched the provided criteria."

        return result

    # ------------------------------------------------------------------ #
    #  E-03: analyze_new
    # ------------------------------------------------------------------ #

    def analyze_new(self, msg_path: str) -> TriageResult:
        """Analyze an email for new-job creation.

        Suggests a template and configuration based on the email content.

        Returns
        -------
        TriageResult
        """
        email_info = MsgParser.parse(msg_path)
        matches = TriageMatcher.match(email_info, self._jobs, self._xml_type)
        exact_matches = self._filter_exact_detail_matches(matches, email_info)

        result = TriageResult(
            email_info=email_info,
            matches=exact_matches,
            has_match=len(exact_matches) > 0,
        )

        if exact_matches:
            result.recommendation = (
                f"Email already matches {len(exact_matches)} existing job(s). "
                f"Best match: {exact_matches[0].job_name}"
            )
            return result

        # Template suggestion
        parser_guess = self._guess_parser(email_info)
        subject_pattern = self._extract_subject_pattern(email_info.subject)

        # Find closest template
        try:
            inventory = TemplateInventory(self._settings_path, self._xml_type)
            templates = inventory.discover_templates(parser_guess)
            if templates:
                best_template = templates[0]
                result.suggested_template = best_template.pattern_name
        except Exception as exc:
            logger.debug("Template discovery failed: %s", exc)

        # Build suggested config
        sender_domain = ""
        if "@" in email_info.sender:
            sender_domain = email_info.sender.split("@")[-1]

        result.suggested_config = {
            "suggested_parser": parser_guess,
            "subject_pattern": subject_pattern,
            "sender_domain": sender_domain,
            "attachment_types": self._get_extensions(email_info.attachment_names),
        }

        # Coverage via deal_repo
        if self._deal_repo is not None and sender_domain:
            try:
                companies = self._deal_repo.get_companies_by_sender_domain(sender_domain)
                if companies:
                    result.suggested_config["potential_servicer_ids"] = companies
            except Exception as exc:
                logger.debug("Sender domain lookup failed: %s", exc)

        result.recommendation = (
            f"No existing jobs match. Suggested parser: {parser_guess}. "
            f"Subject pattern: '{subject_pattern}'."
        )

        return result

    # ------------------------------------------------------------------ #
    #  Private helpers
    # ------------------------------------------------------------------ #

    def _find_job(self, job_name: str):
        """Return the EmailJob/SftpJob object with the given name, or None."""
        for job in self._jobs:
            if job.name == job_name:
                return job
        return None

    @staticmethod
    def _filter_exact_detail_matches(
        matches: List[MatchResult],
        email_info: EmailInfo,
    ) -> List[MatchResult]:
        """Keep only exact mailbox-backed matches for detail-email triage."""
        mailboxes = {
            str(value or "").strip().lower()
            for value in list(getattr(email_info, "to", []) or []) + list(getattr(email_info, "cc", []) or [])
            if "@" in str(value or "")
        }
        if not mailboxes:
            return []

        exact_matches: List[MatchResult] = []
        for match in matches:
            matched_filter = str(getattr(match, "matched_filter", "") or "").strip().lower()
            matched_field = str(getattr(match, "email_field_matched", "") or "").strip().lower()
            if matched_filter in mailboxes or matched_field in mailboxes:
                exact_matches.append(match)
        return exact_matches

    @staticmethod
    def _get_template_name(job) -> str:
        """Extract the primary scrubber/template name from a job."""
        if not job.templates:
            return ""
        return job.templates.get("Main", "") or next(
            (v for v in job.templates.values() if v), ""
        )

    @staticmethod
    def _match_dids_to_email(
        deals: List[Dict],
        email_info: EmailInfo,
        match_mode: str,
    ) -> List[DIDMatch]:
        """Check each deal's ImportDID keyword against the email.

        Parameters
        ----------
        deals : list[dict]
            Rows from ``tblExternalDIDRef`` with keys ``DID``, ``ImportDID``,
            ``CompanyID``.
        email_info : EmailInfo
            Parsed email metadata (subject, attachment_names).
        match_mode : str
            ``"Subject"``, ``"Filename"``, ``"Both"``, or ``"(none)"``.

        Returns
        -------
        list[DIDMatch]
        """
        def _normalize_probe(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        results: List[DIDMatch] = []

        check_subject = match_mode in ("Subject", "Both")
        check_filename = match_mode in ("Filename", "Both")

        subject_lower = email_info.subject.lower() if check_subject else ""
        subject_normalized = _normalize_probe(email_info.subject) if check_subject else ""
        filenames_lower = (
            [f.lower() for f in email_info.attachment_names]
            if check_filename
            else []
        )
        filenames_normalized = (
            [_normalize_probe(f) for f in email_info.attachment_names]
            if check_filename
            else []
        )

        for deal in deals:
            keyword = deal.get("ImportDID", "")
            if not keyword:
                continue
            kw_lower = keyword.lower()
            kw_normalized = _normalize_probe(keyword)
            did = deal.get("DID", "")

            if check_subject and (
                kw_lower in subject_lower
                or (kw_normalized and kw_normalized in subject_normalized)
            ):
                results.append(DIDMatch(
                    did=did,
                    import_did=keyword,
                    matched_in="subject",
                    matched_value=email_info.subject,
                ))
                continue  # no need to also check filenames for same DID

            if check_filename:
                for fname, fname_normalized in zip(filenames_lower, filenames_normalized):
                    if kw_lower in fname or (kw_normalized and kw_normalized in fname_normalized):
                        # Use original filename for display
                        orig = next(
                            (f for f in email_info.attachment_names
                             if f.lower() == fname),
                            fname,
                        )
                        results.append(DIDMatch(
                            did=did,
                            import_did=keyword,
                            matched_in="filename",
                            matched_value=orig,
                        ))
                        break  # one match per DID is enough

        return results

    @staticmethod
    def _assess_confidence(result: TriageResult) -> str:
        """Derive a confidence label from the evidence in *result*.

        Levels (best to worst):
        * ``completed`` — matched, DID hits, template ran successfully
        * ``processed`` — matched, DID hits, log activity exists
        * ``should_process`` — matched with DID coverage but no run evidence
        * ``monitored`` — matched job but no DID or log evidence
        """
        if not result.has_match:
            return ""

        has_dids = bool(result.did_matches)
        has_logs = (
            result.log_summary is not None
            and result.log_summary.get("total_events", 0) > 0
        )
        has_template_run = (
            result.template_status is not None
            and result.template_status.get("summary", {}).get("total_runs", 0) > 0
        )

        if has_dids and has_template_run:
            return "completed"
        if has_dids and has_logs:
            return "processed"
        if has_dids:
            return "should_process"
        return "monitored"

    @staticmethod
    def _guess_parser(email_info: EmailInfo) -> str:
        """Guess the parser type based on attachment extensions."""
        extensions = TriageAnalyzer._get_extensions(email_info.attachment_names)
        if not extensions:
            return "generic"

        ext_set = {e.lower() for e in extensions}

        if ext_set & {".xlsx", ".xls"}:
            return "excel"
        if ext_set & {".csv"}:
            return "csv"
        if ext_set & {".pdf"}:
            return "pdf"
        if ext_set & {".zip", ".rar", ".7z"}:
            return "archive"
        if ext_set & {".txt", ".dat"}:
            return "text"
        return "generic"

    @staticmethod
    def _extract_subject_pattern(subject: str) -> str:
        """Remove dates and long numbers to derive a reusable pattern."""
        if not subject:
            return ""
        cleaned = _DATE_NUM_RE.sub("*", subject)
        # Collapse multiple wildcards
        cleaned = re.sub(r"\*[\s*]+", "* ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _get_extensions(filenames: List[str]) -> List[str]:
        """Extract unique file extensions from a list of filenames."""
        import os as _os
        exts: List[str] = []
        seen: set = set()
        for name in filenames:
            _, ext = _os.path.splitext(name)
            if ext and ext.lower() not in seen:
                seen.add(ext.lower())
                exts.append(ext.lower())
        return exts
