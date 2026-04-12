"""Tests for MsgParser — all .msg interactions are mocked."""
import sys
import pytest
from unittest.mock import MagicMock, patch
from backend.triage.msg_parser import MsgParser
from backend.triage.models import EmailInfo


def _patch_extract_msg(mock_msg):
    """Context manager that injects a mock extract_msg module into sys.modules."""
    mock_module = MagicMock()
    mock_module.Message.return_value = mock_msg
    return patch.dict("sys.modules", {"extract_msg": mock_module})


def _patch_extract_msg_error(exc):
    """Context manager: extract_msg.Message raises *exc*."""
    mock_module = MagicMock()
    mock_module.Message.side_effect = exc
    return patch.dict("sys.modules", {"extract_msg": mock_module})


class TestMsgParser:

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            MsgParser.parse("C:\\no\\such\\file.msg")

    def test_wrong_extension(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        with pytest.raises(ValueError, match="expected .msg"):
            MsgParser.parse(str(txt_file))

    def test_extract_msg_not_installed(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00" * 10)
        with patch.dict("sys.modules", {"extract_msg": None}):
            with pytest.raises(RuntimeError, match="extract-msg"):
                MsgParser.parse(str(msg_file))

    def test_parse_success(self, tmp_path):
        msg_file = tmp_path / "sample.msg"
        msg_file.write_bytes(b"\x00" * 10)

        mock_msg = _build_mock_msg(sender="sender@acme.com", sender_name="ACME Sender", subject="Monthly Report")
        mock_msg.to = "to@example.com"
        mock_msg.cc = None
        mock_msg.body = "Body text here"

        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))

        assert isinstance(result, EmailInfo)
        assert result.sender == "sender@acme.com"
        assert result.subject == "Monthly Report"

    def test_parse_sender(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg(sender="reports@beta.org", sender_name="Beta Reports")
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert result.sender == "reports@beta.org"
        assert result.sender_name == "Beta Reports"

    def test_parse_subject(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg(subject="Q4 Financial Summary")
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert result.subject == "Q4 Financial Summary"

    def test_parse_date(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        from datetime import datetime
        mock_msg = _build_mock_msg()
        mock_msg.date = datetime(2025, 3, 15, 14, 30)
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert "2025-03-15" in result.date

    def test_parse_recipients(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg()
        mock_msg.to = "a@x.com; b@x.com"
        mock_msg.cc = "c@x.com"
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert "a@x.com" in result.to
        assert "b@x.com" in result.to
        assert "c@x.com" in result.cc

    def test_parse_recipients_normalizes_display_names(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg()
        mock_msg.to = 'US Bank GSF ABS Mailbox Shared <USBankGSFABSMailboxShared@usbank.com>'
        mock_msg.cc = 'Bayview Team <bayview@usbank.com>'
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert result.to == ["USBankGSFABSMailboxShared@usbank.com"]
        assert result.cc == ["bayview@usbank.com"]

    def test_parse_body_preview(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg()
        mock_msg.body = "X" * 1000
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert len(result.body_preview) <= 500

    def test_parse_attachments(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg()
        att1 = MagicMock()
        att1.longFilename = "report.xlsx"
        att1.shortFilename = "report.xls"
        att2 = MagicMock()
        att2.longFilename = "data.csv"
        att2.shortFilename = "data.csv"
        mock_msg.attachments = [att1, att2]
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert "report.xlsx" in result.attachment_names
        assert "data.csv" in result.attachment_names

    def test_parse_empty_fields(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg(
            sender=None, sender_name=None, subject=None,
        )
        mock_msg.date = None
        mock_msg.to = None
        mock_msg.cc = None
        mock_msg.body = None
        mock_msg.attachments = None
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert result.sender == ""
        assert result.subject == ""
        assert result.to == []

    def test_parse_file_path_stored(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg()
        with _patch_extract_msg(mock_msg):
            result = MsgParser.parse(str(msg_file))
        assert result.file_path == str(msg_file)

    def test_parse_error(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        with _patch_extract_msg_error(Exception("Corrupt file")):
            with pytest.raises(RuntimeError, match="Failed to parse"):
                MsgParser.parse(str(msg_file))

    def test_parse_closes_handle(self, tmp_path):
        msg_file = tmp_path / "test.msg"
        msg_file.write_bytes(b"\x00")
        mock_msg = _build_mock_msg()
        with _patch_extract_msg(mock_msg):
            MsgParser.parse(str(msg_file))
        mock_msg.close.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────── #
#   Helpers
# ──────────────────────────────────────────────────────────────────────────── #

def _build_mock_msg(
    sender="test@example.com",
    sender_name="Test User",
    subject="Test Subject",
):
    mock = MagicMock()
    mock.sender = sender or ""
    mock.senderName = sender_name or ""
    mock.subject = subject or ""
    mock.date = "2025-01-15T10:00:00"
    mock.to = "to@example.com"
    mock.cc = None
    mock.body = "Body preview text."
    mock.attachments = []
    return mock
