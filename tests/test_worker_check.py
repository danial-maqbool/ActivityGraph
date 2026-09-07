"""Worker checks preserve earlier browser and worker evidence in shared report roots."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("worker_check", ROOT / "scripts/worker_check.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerEvidenceTests(unittest.TestCase):
    def test_existing_browser_evidence_is_preserved_across_worker_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / "browser-report.json"
            old.write_text('{"status":"failed"}')
            first = worker.prepare_report_dir(root)
            marker = first / "worker-report.json"
            marker.write_text('{"status":"failed"}')
            second = worker.prepare_report_dir(root)
            self.assertNotEqual(first, second)
            self.assertEqual(old.read_text(), '{"status":"failed"}')
            self.assertEqual(marker.read_text(), '{"status":"failed"}')
            self.assertEqual(first.parent, root.resolve())
            self.assertEqual(second.parent, root.resolve())

    def test_new_report_directory_is_used_directly(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "new-run"
            self.assertEqual(worker.prepare_report_dir(target), target.resolve())
            self.assertTrue(target.is_dir())
