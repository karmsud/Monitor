"""Tests for XmlWriter."""
import os
import time

import pytest

from backend.xml.parser import SettingsXmlParser
from backend.xml.writer import XmlWriter


class TestXmlWriter:

    def test_save_creates_backup_dir(self, tmp_settings):
        parser = SettingsXmlParser(tmp_settings)
        tree = parser.get_element_tree()
        writer = XmlWriter(tmp_settings)
        writer.save(tree)
        assert os.path.isdir(writer.backup_dir)

    def test_save_creates_backup_file(self, tmp_settings):
        parser = SettingsXmlParser(tmp_settings)
        tree = parser.get_element_tree()
        writer = XmlWriter(tmp_settings)
        writer.save(tree)
        backup_files = os.listdir(writer.backup_dir)
        assert len(backup_files) >= 1

    def test_save_preserves_content(self, tmp_settings):
        parser = SettingsXmlParser(tmp_settings)
        tree = parser.get_element_tree()
        original_count = len(parser.get_all_jobs())

        writer = XmlWriter(tmp_settings)
        writer.save(tree)

        parser2 = SettingsXmlParser(tmp_settings)
        assert len(parser2.get_all_jobs()) == original_count

    def test_save_returns_success(self, tmp_settings):
        parser = SettingsXmlParser(tmp_settings)
        tree = parser.get_element_tree()
        writer = XmlWriter(tmp_settings)
        result = writer.save(tree)
        assert result["success"] is True

    def test_multiple_saves_stack(self, tmp_settings):
        parser = SettingsXmlParser(tmp_settings)
        tree = parser.get_element_tree()
        writer = XmlWriter(tmp_settings)

        for _ in range(3):
            writer.save(tree)
            # Small sleep to ensure unique backup filenames (1-second resolution)
            time.sleep(1.1)

        backup_files = os.listdir(writer.backup_dir)
        assert len(backup_files) == 3
