"""Log-file parser for FRP EmailMonitor / SFTP monitor logs.

Implements a lightweight state-machine that walks each line, tracks the
current job context, and emits :class:`LogEvent` instances.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

from backend.logs.models import LogEvent

logger = logging.getLogger("frp.logs.parser")

# --------------------------------------------------------------------------- #
# Compiled regex patterns
# --------------------------------------------------------------------------- #

_RE_TIMESTAMP = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}):\t(.*)$"
)
# Email: "Starting Outlook download for JOB (mailbox)"
# SFTP:  "Checking SFTP folder for JOB (path)..."
_RE_JOB_START = re.compile(
    r"(?:Starting Outlook download|Checking SFTP folder) for\s+(\S+)\s+\(([^)]+)\)"
)
_RE_FOUND_COUNT = re.compile(r"found\s+(\d+)", re.IGNORECASE)
# Email: "Processing: [email subject]"  —  SFTP: "Processing: filename"
_RE_PROCESSING = re.compile(r"Processing:\s+\[?(.+?)\]?\s*$")
_RE_FROM = re.compile(r"From:\s+(.+)$")
# Email: "Matched email [...] to [Parser] parser"
# SFTP:  "Matched file to [Parser] parser"
_RE_PARSER_MATCH = re.compile(
    r"Matched\s+(?:email\s+\[.+?\]|file)\s+to\s+\[([^\]]+)\]\s+parser"
)
_RE_FILE_LOAD = re.compile(r"\s*Load\s*>\s*(.+?)\s*\(")
_RE_TEMPLATE_QUEUE = re.compile(
    r"Queue file\s+\[(.+?)\]\s+for\s+\[(.+?)\]\s+template"
)
# SFTP DID success: "Matched DID to [DID] and updated save location to [path]..."
_RE_DID_MATCH = re.compile(
    r"Matched DID to\s+\[(.+?)\]\s+and updated save location to\s+\[(.+?)\]"
)
_RE_DID_MAPPING_FAILED = re.compile(
    r"Did not find DID mapping for\s+\[(.+?)\]"
)
_RE_ERROR = re.compile(
    r"(?:error|exception|failed|cannot|unable)", re.IGNORECASE
)

# Lines starting with ## are header decoration and should be skipped.
_RE_HEADER = re.compile(r"^\s*##")


class LogFileParser:
    """Parse a single FRP monitor log file into a list of :class:`LogEvent`."""

    def parse_file(
        self,
        filepath: str,
        log_type: str = "email",
    ) -> List[LogEvent]:
        """Read *filepath* and return all extracted events.

        Parameters
        ----------
        filepath:
            Absolute or relative path to the ``.log`` file.
        log_type:
            Label stored on each event (``"email"`` or ``"sftp"``).
        """
        log_filename = os.path.basename(filepath)
        events: List[LogEvent] = []

        # State machine context -------------------------------------------
        current_job_name: Optional[str] = None
        current_mailbox: Optional[str] = None
        current_subject: Optional[str] = None
        current_sender: Optional[str] = None
        current_job_run_index = 0
        current_email_event_id: Optional[str] = None
        current_email_event_index: Optional[int] = None

        logger.debug("Parsing %s (type=%s)", filepath, log_type)

        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\n\r")

                # Skip header decoration lines
                if _RE_HEADER.match(line):
                    continue

                # Every meaningful line must start with a timestamp
                ts_match = _RE_TIMESTAMP.match(line)
                if ts_match is None:
                    continue

                timestamp = ts_match.group(1)
                message = ts_match.group(2)

                # ----- classify the message ----- #

                # 1. Job start
                m = _RE_JOB_START.search(message)
                if m:
                    current_job_name = m.group(1)
                    current_mailbox = m.group(2)
                    current_job_run_index += 1
                    # Reset per-email context on new job start
                    current_subject = None
                    current_sender = None
                    current_email_event_id = None
                    current_email_event_index = None
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            event_type="job_start",
                            raw_line=line,
                        )
                    )
                    continue

                # 2. Found count
                m = _RE_FOUND_COUNT.search(message)
                if m:
                    count = int(m.group(1))
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            event_type="found_count",
                            emails_found=count,
                            raw_line=line,
                        )
                    )
                    continue

                # 3. Processing (email subject)
                m = _RE_PROCESSING.search(message)
                if m:
                    current_subject = m.group(1)
                    # Reset sender for the new email being processed
                    current_sender = None
                    current_email_event_index = (current_email_event_index or 0) + 1
                    current_email_event_id = (
                        f"{log_filename}::job{current_job_run_index}::email{current_email_event_index}"
                    )
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="processing",
                            subject=current_subject,
                            raw_line=line,
                        )
                    )
                    continue

                # 4. From (sender)
                m = _RE_FROM.search(message)
                if m:
                    current_sender = m.group(1).strip()
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="from",
                            subject=current_subject,
                            sender=current_sender,
                            raw_line=line,
                        )
                    )
                    continue

                # 5. Parser match
                m = _RE_PARSER_MATCH.search(message)
                if m:
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="parser_match",
                            subject=current_subject,
                            sender=current_sender,
                            parser=m.group(1),
                            raw_line=line,
                        )
                    )
                    continue

                # 6. File load
                m = _RE_FILE_LOAD.search(message)
                if m:
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="file_load",
                            subject=current_subject,
                            sender=current_sender,
                            filename=m.group(1).strip(),
                            raw_line=line,
                        )
                    )
                    continue

                # 7. Template queue
                m = _RE_TEMPLATE_QUEUE.search(message)
                if m:
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="template_queue",
                            subject=current_subject,
                            sender=current_sender,
                            filename=m.group(1),
                            template=m.group(2),
                            raw_line=line,
                        )
                    )
                    continue

                # 9. DID match (success — SFTP logs)
                m = _RE_DID_MATCH.search(message)
                if m:
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="did_match",
                            subject=current_subject,
                            sender=current_sender,
                            filename=m.group(1),  # matched DID name
                            raw_line=line,
                        )
                    )
                    continue

                # 9. DID mapping failure
                m = _RE_DID_MAPPING_FAILED.search(message)
                if m:
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="did_mapping_failed",
                            subject=current_subject,
                            sender=current_sender,
                            error_message=f"Did not find DID mapping for [{m.group(1)}]",
                            raw_line=line,
                        )
                    )
                    continue

                # 10. Error / exception (catch-all)
                m = _RE_ERROR.search(message)
                if m:
                    events.append(
                        LogEvent(
                            log_file=log_filename,
                            log_type=log_type,
                            timestamp=timestamp,
                            job_name=current_job_name,
                            mailbox=current_mailbox,
                            email_event_id=current_email_event_id,
                            email_event_index=current_email_event_index,
                            event_type="error",
                            subject=current_subject,
                            sender=current_sender,
                            error_message=message.strip(),
                            raw_line=line,
                        )
                    )
                    continue

                # 11. Unclassified timestamped line → generic info event
                events.append(
                    LogEvent(
                        log_file=log_filename,
                        log_type=log_type,
                        timestamp=timestamp,
                        job_name=current_job_name,
                        mailbox=current_mailbox,
                        email_event_id=current_email_event_id,
                        email_event_index=current_email_event_index,
                        event_type="info",
                        subject=current_subject,
                        sender=current_sender,
                        raw_line=line,
                    )
                )

        logger.info(
            "Parsed %s: %d events extracted.", filepath, len(events),
        )
        return events
