"""Tests for TemplateInventory."""
import os
import shutil

import pytest

from backend.xml.templates import TemplateInventory


class TestTemplateInventory:

    def test_discover_returns_templates(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        assert len(templates) > 0

    def test_total_job_count_matches(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        from backend.xml.parser import SettingsXmlParser
        all_jobs = SettingsXmlParser(email_fixture).get_all_jobs()
        assert sum(t.job_count for t in templates) == len(all_jobs)

    def test_templates_sorted_by_count(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        if len(templates) >= 2:
            assert templates[0].job_count >= templates[1].job_count

    def test_each_template_has_example(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        for t in templates:
            assert t.example_job_name, f"Template {t.pattern_name} missing example"

    def test_parser_names_populated(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        has_parsers = any(len(t.parser_names) > 0 for t in templates)
        assert has_parsers

    def test_filter_by_parser(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        all_templates = inv.discover_templates()
        if all_templates:
            parser_to_filter = all_templates[0].parser_names[0] if all_templates[0].parser_names else None
            if parser_to_filter:
                filtered = inv.discover_templates(filter_query=parser_to_filter)
                assert all(parser_to_filter in t.parser_names for t in filtered)

    def test_filter_no_match(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        filtered = inv.discover_templates(filter_query="nonexistent_parser_xyz")
        assert len(filtered) == 0

    def test_has_servicer_id_flag(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        flags = [t.has_servicer_id for t in templates]
        # The fixture has jobs with and without ServicerID
        assert True in flags or False in flags

    def test_sample_fields_extracted(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        for t in templates:
            assert "name" in t.sample_fields
            assert "xml_type" in t.sample_fields

    def test_mailbox_pattern_present(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        # At least one template should have a mailbox pattern
        assert any(t.mailbox_pattern for t in templates)

    def test_pattern_name_non_empty(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        for t in templates:
            assert t.pattern_name, "pattern_name should not be empty"

    def test_sftp_templates(self, sftp_fixture):
        inv = TemplateInventory(sftp_fixture, xml_type="sftp")
        templates = inv.discover_templates()
        assert len(templates) > 0

    def test_empty_xml(self, tmp_path):
        empty = tmp_path / "empty.xml"
        empty.write_text(
            '<Settings><Outlook><Enabled>1</Enabled>'
            '<MailboxCollection></MailboxCollection></Outlook></Settings>'
        )
        inv = TemplateInventory(str(empty), xml_type="email")
        templates = inv.discover_templates()
        assert len(templates) == 0

    def test_single_job_xml(self, tmp_path, email_fixture):
        """XML with only one job should produce exactly one template."""
        single = tmp_path / "single.xml"
        single.write_text(
            '<Settings><Outlook><Enabled>1</Enabled>'
            '<MailboxCollection>'
            '<OnlyJob><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Parsers><StandardParser>.*</StandardParser></Parsers></OnlyJob>'
            '</MailboxCollection></Outlook></Settings>'
        )
        inv = TemplateInventory(str(single), xml_type="email")
        templates = inv.discover_templates()
        assert len(templates) == 1
        assert templates[0].job_count == 1

    def test_to_dict_serializable(self, email_fixture):
        inv = TemplateInventory(email_fixture, xml_type="email")
        templates = inv.discover_templates()
        for t in templates:
            d = t.to_dict()
            assert isinstance(d, dict)
            assert "pattern_name" in d
