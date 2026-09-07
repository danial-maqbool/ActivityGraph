"""Consent-scoped file observations, history filters, and privacy controls."""

import json
from datetime import datetime, timezone, timedelta
from app.timeline import stamp
from localdesk.safety import InputError, digest
from tests.support import AppCase, Context


class TimelineTests(AppCase):
    def root(self):
        return self.app.timeline.add_root(str(self.workspace), "Test project")

    def test_monitor_is_paused_on_startup(self):
        self.assertFalse(self.app.monitor["enabled"])

    def test_first_observation_is_discovery_not_creation(self):
        self.file()
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        e = self.app.timeline.events()["events"]
        self.assertEqual(e[0]["kind"], "discovered")

    def test_new_file_produces_created_event(self):
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        self.file()
        self.app.timeline.scan(r["id"], Context())
        self.assertEqual(self.app.timeline.events()["events"][0]["kind"], "created")

    def test_changed_file_produces_modified_event(self):
        p = self.file()
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        p.write_text("new content with another size")
        self.app.timeline.scan(r["id"], Context())
        self.assertEqual(self.app.timeline.events()["events"][0]["kind"], "modified")

    def test_deleted_file_produces_deleted_event(self):
        p = self.file()
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        p.unlink()
        self.app.timeline.scan(r["id"], Context())
        self.assertEqual(self.app.timeline.events()["events"][0]["kind"], "deleted")

    def test_unchanged_scan_does_not_duplicate_events(self):
        self.file()
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        self.app.timeline.scan(r["id"], Context())
        self.assertEqual(len(self.app.timeline.events()["events"]), 1)

    def test_content_is_not_stored(self):
        self.file(content="UNIQUE_PRIVATE_FILE_CONTENT_42")
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        rows = self.app.timeline.events()
        self.assertNotIn("UNIQUE_PRIVATE_FILE_CONTENT_42", json.dumps(rows))
        with self.app.store.connection() as db:
            database_text = "\n".join(db.iterdump())
        self.assertNotIn("UNIQUE_PRIVATE_FILE_CONTENT_42", database_text)

    def test_source_files_remain_unchanged(self):
        p = self.file()
        h = digest(p)
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        self.assertEqual(digest(p), h)

    def test_private_directory_cannot_be_monitored(self):
        with self.assertRaises(InputError):
            self.app.timeline.add_root(str(self.app.data))

    def test_demo_events_are_flagged_and_idempotent(self):
        self.app.post("demo", {})
        self.app.post("demo", {})
        e = self.app.timeline.events()["events"]
        self.assertEqual(len(e), 8)
        self.assertTrue(all(x["is_demo"] for x in e))

    def test_remove_demo_preserves_manual_note(self):
        self.app.post("demo", {})
        self.app.post("note", {"note": "My note"})
        self.app.post("demo/remove", {})
        e = self.app.timeline.events()["events"]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["note"], "My note")

    def test_notes_and_tags_are_editable(self):
        r = self.app.post("note", {"project": "Notes", "note": "First"})
        self.app.post(
            "event/update",
            {"id": r["id"], "note": "Second", "tags": ["review", "review"]},
        )
        e = self.app.timeline.events(tag="review")["events"][0]
        self.assertEqual(e["note"], "Second")
        self.assertEqual(e["tags"], ["review"])

    def test_query_and_kind_filters(self):
        self.app.post("demo", {})
        e = self.app.timeline.events(query="travel", kind="modified")["events"]
        self.assertEqual(len(e), 1)

    def test_invalid_kind_is_rejected(self):
        with self.assertRaises(InputError):
            self.app.timeline.events(kind="keystrokes")

    def test_graph_edges_reference_existing_nodes(self):
        self.app.post("demo", {})
        graph = self.app.timeline.graph()
        nodes = {n["id"] for n in graph["nodes"]}
        self.assertTrue(graph["edges"])
        self.assertTrue(
            all(e["source"] in nodes and e["target"] in nodes for e in graph["edges"])
        )

    def test_change_groups_are_not_work_hours(self):
        self.app.post("demo", {})
        r = self.app.timeline.sessions()
        self.assertEqual(len(r["sessions"]), 2)
        self.assertIn("not measured work time", r["method"])

    def test_retention_deletes_only_old_events(self):
        r = self.app.post("note", {"note": "Old"})
        old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(
            timespec="seconds"
        )
        self.app.store.execute(
            "UPDATE events SET observed=? WHERE id=?", (old, r["id"])
        )
        self.app.post("note", {"note": "New"})
        self.assertEqual(self.app.timeline.prune(30), 1)
        self.assertEqual(len(self.app.timeline.events()["events"]), 1)

    def test_erase_requires_explicit_confirmation(self):
        with self.assertRaises(InputError):
            self.app.post("erase", {"confirm": "yes"})

    def test_erase_removes_history_not_sources(self):
        p = self.file()
        r = self.root()
        self.app.timeline.scan(r["id"], Context())
        self.app.post("erase", {"confirm": "ERASE"})
        self.assertEqual(self.app.timeline.events()["events"], [])
        self.assertTrue(p.exists())

    def test_monitor_requires_selected_folder(self):
        with self.assertRaises(InputError):
            self.app.post("monitor/start", {"seconds": 10})

    def test_monitor_start_and_stop(self):
        self.file()
        self.root()
        result = self.app.post("monitor/start", {"seconds": 5})
        self.wait(result["job_id"])
        self.assertTrue(self.app.monitor["enabled"])
        self.app.post("monitor/stop", {})
        self.assertFalse(self.app.monitor["enabled"])

    def test_iso_dates_are_normalized(self):
        self.assertEqual(stamp("2026-01-01"), "2026-01-01T00:00:00+00:00")
        with self.assertRaises(InputError):
            stamp("yesterday")

    def test_export_is_structured_json(self):
        self.app.post("note", {"note": "Local note"})
        a = self.app.post("export", {"format": "json"})
        self.assertEqual(json.loads(self.output(a))["events"][0]["note"], "Local note")
