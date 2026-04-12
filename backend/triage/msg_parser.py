"""MsgParser — extract metadata from Outlook .msg files.

Requires the ``extract-msg`` package (``pip install extract-msg``).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import List

from backend.triage.models import EmailInfo

logger = logging.getLogger("frp.triage.msg_parser")

_EMAIL_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class MsgParser:
    """Static helper for parsing ``.msg`` files into :class:`EmailInfo`."""

    @staticmethod
    def parse(msg_path: str) -> EmailInfo:
        """Parse a ``.msg`` file and return an :class:`EmailInfo` instance.

        Parameters
        ----------
        msg_path : str
            Filesystem path to the ``.msg`` file.

        Raises
        ------
        FileNotFoundError
            If *msg_path* does not exist.
        ValueError
            If the file does not have a ``.msg`` extension.
        RuntimeError
            If the ``extract-msg`` package is not installed or parsing fails.
        """
        if not os.path.exists(msg_path):
            raise FileNotFoundError(f".msg file not found: {msg_path}")

        if not msg_path.lower().endswith(".msg"):
            raise ValueError(f"Unsupported file type (expected .msg): {msg_path}")

        try:
            import extract_msg  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError(
                "The 'extract-msg' package is required for .msg parsing. "
                "Install it with: pip install extract-msg"
            )

        msg = None
        try:
            msg = extract_msg.Message(msg_path)

            # Sender
            sender: str = msg.sender or ""
            sender_name: str = getattr(msg, "senderName", None) or getattr(msg, "sender_name", None) or ""
            # If no explicit sender name, try to extract display name from "Name <email>"
            if not sender_name and sender:
                if "<" in sender:
                    sender_name = sender.split("<")[0].strip().strip('"').strip("'")
                else:
                    sender_name = sender

            # Subject
            subject: str = msg.subject or ""

            # Date
            date_str = ""
            if msg.date:
                try:
                    if isinstance(msg.date, datetime):
                        date_str = msg.date.isoformat()
                    else:
                        date_str = str(msg.date)
                except Exception:
                    date_str = str(msg.date)

            # Recipients
            to: List[str] = _parse_recipients(msg.to)
            cc: List[str] = _parse_recipients(msg.cc)

            # Body preview (first 500 chars)
            body: str = msg.body or ""
            body_preview = body[:500].strip()

            # Attachments
            attachment_names: List[str] = []
            if msg.attachments:
                for att in msg.attachments:
                    name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or ""
                    if name:
                        attachment_names.append(name)

            return EmailInfo(
                sender=sender,
                sender_name=sender_name,
                subject=subject,
                date=date_str,
                to=to,
                cc=cc,
                body_preview=body_preview,
                attachment_names=attachment_names,
                file_path=msg_path,
            )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to parse .msg file: {exc}") from exc
        finally:
            if msg is not None:
                try:
                    msg.close()
                except Exception:
                    pass


def _parse_recipients(raw: object) -> List[str]:
    """Normalise a recipient field into a list of email strings."""
    if not raw:
        return []
    if isinstance(raw, str):
        values = raw.split(";")
    elif isinstance(raw, (list, tuple)):
        values = [str(r) for r in raw if r]
    else:
        values = [str(raw)]

    recipients: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        match = _EMAIL_ADDRESS_RE.search(text)
        recipients.append(match.group(0) if match else text)

    return recipients
