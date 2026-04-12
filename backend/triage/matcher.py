"""TriageMatcher — match an email against configured FRP jobs.

Compares sender / subject / mailbox information from an :class:`EmailInfo`
against the ``filters`` dict on each :class:`EmailJob`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Union

from backend.triage.models import EmailInfo, MatchResult
from backend.xml.models import EmailJob, SftpJob

logger = logging.getLogger("frp.triage.matcher")

_EMAIL_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class TriageMatcher:
    """Static helper that matches an email to configured jobs."""

    @staticmethod
    def match(
        email_info: EmailInfo,
        jobs: List[Union[EmailJob, SftpJob]],
        xml_type: str = "email",
    ) -> List[MatchResult]:
        """Return job matches sorted by relevance (highest first).

        Parameters
        ----------
        email_info : EmailInfo
            Parsed email metadata.
        jobs : list
            All jobs loaded from Settings.xml.
        xml_type : str
            Filter to only consider jobs of this type.
        """
        results: List[MatchResult] = []
        for job in jobs:
            if getattr(job, "xml_type", "email") != xml_type:
                continue
            match = TriageMatcher._check_job(email_info, job, xml_type)
            if match is not None:
                results.append(match)

        results.sort(key=lambda m: m.sort_score, reverse=True)
        return results

    # ------------------------------------------------------------------ #
    #  Internal
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_job(
        email_info: EmailInfo,
        job: Union[EmailJob, SftpJob],
        xml_type: str,
    ) -> Optional[MatchResult]:
        """Check whether *job* matches *email_info*.

        The ``filters`` dict on :class:`EmailJob` uses keys like ``"From"``
        and ``"Subject"`` whose values are the filter regex/substring from
        the ``<Filters>`` element in Settings.xml.
        """
        sender_filter, subject_filter = TriageMatcher._extract_filters(job)
        mailbox = getattr(job, "mailbox", "") or ""
        recipients = list(getattr(email_info, "to", []) or []) + list(getattr(email_info, "cc", []) or [])

        sender_match = False
        mailbox_match = False
        subject_match = False
        mailbox_field = ""

        # Sender / From filter
        if sender_filter:
            sender_match = TriageMatcher._matches(
                sender_filter, email_info.sender, email_info.sender_name
            )

        # Mailbox / To matching
        if mailbox:
            mailbox_field = TriageMatcher._match_mailbox(mailbox, recipients)
            mailbox_match = bool(mailbox_field)

        # Subject filter
        if subject_filter:
            subject_match = TriageMatcher._matches(
                subject_filter, email_info.subject
            )

        if not sender_match and not mailbox_match and not subject_match:
            return None

        # Determine match type
        if (sender_match or mailbox_match) and subject_match:
            match_type = "both"
        elif mailbox_match:
            match_type = "mailbox"
        elif sender_match:
            match_type = "sender"
        else:
            match_type = "subject"

        # Determine confidence
        if mailbox_match and (not sender_match or TriageMatcher._assess_confidence(mailbox, mailbox_field) == "exact"):
            filter_val = mailbox
            field_val = mailbox_field
        elif match_type in ("sender", "both"):
            filter_val = sender_filter
            field_val = email_info.sender
        else:
            filter_val = subject_filter
            field_val = email_info.subject
        confidence = TriageMatcher._assess_confidence(filter_val, field_val)

        if filter_val == mailbox:
            matched_filter = mailbox
            email_field = mailbox_field
        elif sender_match:
            matched_filter = sender_filter
            email_field = email_info.sender
        else:
            matched_filter = subject_filter
            email_field = email_info.subject

        servicer_id = getattr(job, "servicer_id", None)
        return MatchResult(
            job_name=job.name,
            xml_type=xml_type,
            match_type=match_type,
            match_confidence=confidence,
            servicer_id=str(servicer_id) if servicer_id is not None else None,
            matched_filter=matched_filter or "",
            email_field_matched=email_field,
        )

    @staticmethod
    def _extract_filters(
        job: Union[EmailJob, SftpJob],
    ) -> tuple:
        """Extract sender and subject filter strings from the job.

        Returns ``(sender_filter, subject_filter)`` — either may be ``None``.
        """
        filters: Dict[str, Any] = getattr(job, "filters", {}) or {}

        sender_filter: Optional[str] = None
        subject_filter: Optional[str] = None

        # The XML <Filters> element stores "From" and "Subject" keys
        for key, value in filters.items():
            k = key.lower() if isinstance(key, str) else ""
            if k in ("from", "sender", "senderfilter"):
                sender_filter = str(value) if value else None
            elif k in ("subject", "subjectfilter"):
                subject_filter = str(value) if value else None

        return sender_filter, subject_filter

    @staticmethod
    def _matches(filter_value: str, *fields: str) -> bool:
        """Return True if *filter_value* appears (case-insensitive) in any field."""
        fv = filter_value.lower()
        return any(fv in (f or "").lower() for f in fields)

    @staticmethod
    def _match_mailbox(mailbox: str, recipients: List[str]) -> str:
        """Return the matching recipient email for an exact mailbox hit, if any."""
        target = str(mailbox or "").strip().lower()
        if not target:
            return ""

        for recipient in recipients or []:
            text = str(recipient or "").strip()
            if not text:
                continue
            emails = _EMAIL_ADDRESS_RE.findall(text)
            if any(target == email.lower() for email in emails):
                return next(email for email in emails if target == email.lower())

        for recipient in recipients or []:
            text = str(recipient or "").strip()
            if text and target in text.lower():
                return text

        return ""

    @staticmethod
    def _assess_confidence(filter_value: str, field_value: str) -> str:
        """Return ``'exact'`` if the filter matches the full field, else ``'partial'``."""
        if not filter_value or not field_value:
            return "partial"
        if filter_value.strip().lower() == field_value.strip().lower():
            return "exact"
        return "partial"
