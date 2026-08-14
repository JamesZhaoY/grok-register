import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.web.application import _config_file_snapshot


class ConfigFileSnapshotTests(unittest.TestCase):
    def test_reads_actual_path_and_pretty_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"proxy": "http://proxy", "secret": "value"}), encoding="utf-8")
            with patch("backend.registration.engine.CONFIG_FILE", str(path)):
                snapshot = _config_file_snapshot()
            self.assertEqual(snapshot["path"], str(path.resolve()))
            self.assertTrue(snapshot["exists"])
            self.assertEqual(json.loads(snapshot["content"])["secret"], "value")
            self.assertGreater(snapshot["size"], 0)
            self.assertFalse(snapshot["parse_error"])

    def test_reports_invalid_json_without_hiding_file_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"broken":', encoding="utf-8")
            with patch("backend.registration.engine.CONFIG_FILE", str(path)):
                snapshot = _config_file_snapshot()
            self.assertTrue(snapshot["parse_error"])
            self.assertIn('{"broken":', snapshot["content"])


if __name__ == "__main__":
    unittest.main()
