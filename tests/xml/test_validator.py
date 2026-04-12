"""Tests for the validate() method of SettingsXmlParser."""
import os
import pytest

from backend.xml.parser import SettingsXmlParser

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
MISSING_FIXTURE = os.path.join(FIXTURES_DIR, "email_settings_missing.xml")
DUPLICATE_FIXTURE = os.path.join(FIXTURES_DIR, "email_settings_duplicate.xml")


# ── Helpers ──────────────────────────────────────────────────────────── #

def _write_xml(tmp_path, content: str) -> str:
    """Write XML *content* to a temp file and return its path."""
    p = tmp_path / "test_settings.xml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _has_code(messages: list, code: str) -> bool:
    """Return True if any message string starts with *code*."""
    return any(m.startswith(code) for m in messages)


# ── Valid files ──────────────────────────────────────────────────────── #

class TestValidFiles:

    def test_valid_email_no_errors(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate()
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_sftp_no_errors(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        result = parser.validate()
        assert result.valid is True
        assert len(result.errors) == 0


# ── Structural errors ────────────────────────────────────────────────── #

class TestStructuralErrors:

    def test_e002_missing_outlook(self, tmp_path):
        """No <Outlook> wrapper AND no collection at root → E003."""
        xml = "<Settings><Root/></Settings>"
        path = _write_xml(tmp_path, xml)
        parser = SettingsXmlParser(path)
        result = parser.validate()
        assert result.valid is False
        assert _has_code(result.errors, "E003")

    def test_e003_missing_collection(self, tmp_path):
        xml = "<Settings><Outlook></Outlook></Settings>"
        path = _write_xml(tmp_path, xml)
        parser = SettingsXmlParser(path)
        result = parser.validate()
        assert result.valid is False
        assert _has_code(result.errors, "E003")


# ── Per-job field errors ─────────────────────────────────────────────── #

class TestFieldErrors:

    def test_e004_missing_mailbox(self):
        parser = SettingsXmlParser(MISSING_FIXTURE)
        result = parser.validate()
        assert _has_code(result.errors, "E004")

    def test_e005_missing_sme(self):
        parser = SettingsXmlParser(MISSING_FIXTURE)
        result = parser.validate()
        assert _has_code(result.errors, "E005")

    def test_e006_missing_parsers(self):
        parser = SettingsXmlParser(MISSING_FIXTURE)
        result = parser.validate()
        assert _has_code(result.errors, "E006")

    def test_e007_missing_save_location(self):
        parser = SettingsXmlParser(MISSING_FIXTURE)
        result = parser.validate()
        assert _has_code(result.errors, "E007")


# ── Duplicate names ──────────────────────────────────────────────────── #

class TestDuplicateNames:

    def test_e008_duplicate_names(self):
        parser = SettingsXmlParser(DUPLICATE_FIXTURE)
        result = parser.validate()
        assert _has_code(result.errors, "E008")


# ── Warnings ─────────────────────────────────────────────────────────── #

class TestWarnings:

    def test_w001_unknown_servicer(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        # Provide a set that does NOT contain 150 or 200
        result = parser.validate(db_servicer_ids={999})
        w001s = [w for w in result.warnings if w.startswith("W001")]
        # Both TestJob_Alpha (150) and TestJob_Beta (200) should trigger
        assert len(w001s) >= 2

    def test_w001_skipped_without_db(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate(db_servicer_ids=None)
        w001s = [w for w in result.warnings if w.startswith("W001")]
        assert len(w001s) == 0

    def test_w003_no_tokens(self, tmp_path):
        xml = """<Settings>
            <Outlook>
                <MailboxCollection>
                    <NoTokenJob>
                        <Mailbox>a@b.com</Mailbox>
                        <Folder>Inbox</Folder>
                        <SME>sme@b.com</SME>
                        <SaveLocation>C:\\plain\\path\\</SaveLocation>
                        <Parsers><StandardParser>.*</StandardParser></Parsers>
                    </NoTokenJob>
                </MailboxCollection>
            </Outlook>
        </Settings>"""
        path = _write_xml(tmp_path, xml)
        parser = SettingsXmlParser(path)
        result = parser.validate()
        assert _has_code(result.warnings, "W003")


# ── Info codes ───────────────────────────────────────────────────────── #

class TestInfoCodes:

    def test_i001_job_count(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate()
        assert _has_code(result.info, "I001")
        # Info should mention the count
        i001 = next(i for i in result.info if i.startswith("I001"))
        assert "3" in i001


# ── valid flag semantics ─────────────────────────────────────────────── #

class TestValidFlag:

    def test_valid_false_when_errors(self):
        parser = SettingsXmlParser(MISSING_FIXTURE)
        result = parser.validate()
        assert result.valid is False
        assert len(result.errors) > 0

    def test_valid_true_with_warnings(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        result = parser.validate(db_servicer_ids={999})
        # Has warnings (W001) but no errors → still valid
        assert result.valid is True
        assert len(result.warnings) > 0
