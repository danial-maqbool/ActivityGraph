"""Explicit-consent capture and local history import regression tests."""

from datetime import datetime, timezone
import sqlite3
from contextlib import closing
import time
from unittest.mock import patch
from app.capture import import_browser
from localdesk.safety import InputError, digest
from tests.support import AppCase


class CaptureTests(AppCase):
    def chromium(self):
        path = self.workspace / "History"
        microseconds = int(
            (
                datetime.now(timezone.utc) - datetime(1601, 1, 1, tzinfo=timezone.utc)
            ).total_seconds()
            * 1e6
        )
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE urls(url TEXT,title TEXT,last_visit_time INTEGER)")
            db.executemany(
                "INSERT INTO urls VALUES(?,?,?)",
                [
                    (
                        "https://user:password@example.test/report?token=secret#fragment",
                        "Synthetic report",
                        microseconds,
                    ),
                    ("file:///private.txt", "Private file", microseconds),
                ],
            )
        return path

    def test_capture_is_disabled_without_consent(self):
        self.assertFalse(self.app.state()["capture"]["enabled"])
        for consent in [False, "true", 1, None]:
            with self.assertRaises(InputError):
                self.app.post("capture/start", {"consent": consent})
        self.assertEqual(self.app.state()["stats"]["events"], 0)

    def test_capture_records_only_changed_title_and_can_stop(self):
        with patch(
            "app.capture.active_window",
            return_value={"title": "Test document", "application": "Synthetic editor"},
        ):
            self.app.post("capture/start", {"consent": True, "seconds": 3})
            end = time.monotonic() + 2
            while (
                time.monotonic() < end and self.app.state()["capture"]["recorded"] == 0
            ):
                time.sleep(0.01)
            self.app.post("capture/stop", {})
        result = self.app.get("events", {})["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "window")
        self.assertIn("Test document", result[0]["note"])
        self.assertFalse(self.app.state()["capture"]["enabled"])
        self.assertTrue(self.app.state()["capture"]["consent_required"])

    def test_title_exclusions_are_applied(self):
        with patch(
            "app.capture.active_window",
            return_value={"title": "Password manager", "application": "Test"},
        ):
            self.app.post("capture/start", {"consent": True})
            time.sleep(0.05)
            self.app.post("capture/stop", {})
        self.assertEqual(self.app.state()["stats"]["events"], 0)

    def test_os_permission_error_does_not_enable_capture(self):
        with patch(
            "app.capture.active_window", side_effect=InputError("Permission missing")
        ):
            with self.assertRaises(InputError):
                self.app.post("capture/start", {"consent": True})
        self.assertFalse(self.app.state()["capture"]["enabled"])

    def test_browser_import_requires_explicit_consent(self):
        source = self.chromium()
        with self.assertRaises(InputError):
            import_browser(self.app.store, str(source))
        with self.assertRaises(InputError):
            self.app.post("browser/import", {"path": str(source)})

    def test_chromium_import_strips_url_credentials_and_tokens(self):
        source = self.chromium()
        before = digest(source)
        result = self.finish("browser/import", {"path": str(source), "consent": True})
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["excluded"], 1)
        row = self.app.get("events", {"kind": "browser"})["events"][0]
        self.assertEqual(row["path"], "https://example.test/report")
        self.assertNotIn("secret", str(row))
        self.assertEqual(digest(source), before)

    def test_repeated_history_is_not_duplicated(self):
        source = self.chromium()
        self.finish("browser/import", {"path": str(source), "consent": True})
        result = self.finish("browser/import", {"path": str(source), "consent": True})
        self.assertEqual(result["imported"], 0)

    def test_firefox_uses_correct_timestamp(self):
        source = self.workspace / "places.sqlite"
        now = int(datetime.now(timezone.utc).timestamp())
        with closing(sqlite3.connect(source)) as db, db:
            db.execute(
                "CREATE TABLE moz_places(url TEXT,title TEXT,last_visit_date INTEGER)"
            )
            db.execute(
                "INSERT INTO moz_places VALUES(?,?,?)",
                ("https://example.test/", "Synthetic", now * 1000000),
            )
        result = self.finish("browser/import", {"path": str(source), "consent": True})
        self.assertEqual(result["browser"], "Firefox")
        row = self.app.get("events", {})["events"][0]
        self.assertEqual(int(datetime.fromisoformat(row["observed"]).timestamp()), now)

    def test_semantic_search_preserves_event_identity(self):
        self.app.post(
            "note",
            {
                "project": "Study",
                "note": "Neural attention models for language research.",
            },
        )
        self.app.post(
            "note",
            {"project": "Home", "note": "Grocery shopping and household supplies."},
        )
        result = self.app.get("events", {"q": "attention language", "mode": "semantic"})
        self.assertTrue(result["events"])
        self.assertEqual(result["events"][0]["project"], "Study")
        self.assertIn("id", result["events"][0])
        self.assertIn("name", result["events"][0])

    def test_unknown_search_mode_rejected(self):
        with self.assertRaises(InputError):
            self.app.get("events", {"mode": "remote"})

    def test_erase_stops_capture_and_removes_import_keys(self):
        source = self.chromium()
        self.finish("browser/import", {"path": str(source), "consent": True})
        self.app.post("erase", {"confirm": "ERASE"})
        self.assertEqual(self.app.state()["stats"]["events"], 0)
        self.assertFalse(self.app.state()["capture"]["enabled"])
        self.assertEqual(
            self.app.store.one("SELECT COUNT(*) n FROM browser_imports")["n"], 0
        )
