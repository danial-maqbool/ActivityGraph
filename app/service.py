"""Visible, opt-in monitoring controls and timeline operations."""

from __future__ import annotations
import csv
import io
import json
import threading
from localdesk.base import BaseApplication
from localdesk.jobs import utcnow
from localdesk.safety import InputError, integer, unique_write
from .timeline import Timeline, stamp
from .capture import WindowCapture, import_browser
from localdesk.semantic import SearchCache


class Application(BaseApplication):
    def setup(self):
        self.timeline = Timeline(self.store, self.data)
        self.capture = WindowCapture(self.store)
        self.semantic = SearchCache()
        self.scan_lock = threading.Lock()
        self.monitor_stop = threading.Event()
        self.monitor_thread = None
        # Selected-folder monitoring resumes only from explicitly saved settings.
        self.monitor = {
            "enabled": False,
            "seconds": 10,
            "last_error": "",
            "last_job": None,
        }

    def state(self):
        count = self.store.one(
            "SELECT COUNT(*) AS events,COALESCE(SUM(is_demo),0) AS demo FROM events"
        )
        files = self.store.one("SELECT COUNT(DISTINCT path) AS files FROM snapshots")[
            "files"
        ]
        projects = self.store.rows(
            "SELECT DISTINCT project FROM events UNION SELECT DISTINCT project FROM roots ORDER BY project"
        )
        return {
            "stats": {**count, "files": files, "projects": len(projects)},
            "projects": [p["project"] for p in projects],
            "roots": self.store.rows("SELECT * FROM roots ORDER BY project"),
            "monitor": dict(self.monitor),
            "capture": dict(self.capture.state),
            "retention_days": self.store.get("retention_days", 30),
            "jobs": self.jobs.recent(),
        }

    def get(self, action, query):
        if action == "events" and query.get("mode", "keyword") not in {
            "keyword",
            "semantic",
        }:
            raise InputError("Choose keyword or semantic search.")
        if (
            action == "events"
            and query.get("mode") == "semantic"
            and str(query.get("q", "")).strip()
        ):
            base = self.timeline.events(
                kind=query.get("kind", ""),
                project=query.get("project", ""),
                tag=query.get("tag", ""),
                after=query.get("after", ""),
                before=query.get("before", ""),
                limit=5000,
            )
            records = [
                dict(
                    row,
                    text=row["project"]
                    + " "
                    + row["path"]
                    + " "
                    + row["note"]
                    + " "
                    + str(row.get("tags", [])),
                )
                for row in base["events"]
            ]
            result = self.semantic.search(
                records,
                str(query["q"])[:300],
                limit=integer(query.get("limit", 500), 1, 5000),
            )
            return dict(base, events=result["results"], engine=result["engine"])
        if action == "events":
            return self.timeline.events(
                query=str(query.get("q", ""))[:300],
                kind=query.get("kind", ""),
                project=query.get("project", ""),
                tag=query.get("tag", ""),
                after=query.get("after", ""),
                before=query.get("before", ""),
                limit=integer(query.get("limit", 500), 1, 5000),
            )
        if action == "graph":
            return self.timeline.graph()
        if action == "sessions":
            return self.timeline.sessions()
        return super().get(action, query)

    def scan_all(self):
        roots = self.store.rows("SELECT id FROM roots")
        if not roots:
            raise InputError("Add at least one folder before you start monitoring.")

        def work(context):
            results = []
            with self.scan_lock:
                for root in roots:
                    context.check()
                    results.append(self.timeline.scan(root["id"], context))
                removed = self.timeline.prune(self.store.get("retention_days", 30))
            return {
                "folders": results,
                "expired_events_removed": removed,
                "content_recorded": False,
                "clipboard_recorded": False,
            }

        return self.jobs.submit("Observe selected folders", work)

    def stop_monitor(self):
        self.monitor_stop.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=3)
        last = self.monitor.get("last_job")
        if last:
            self.jobs.cancel(last)
        self.monitor["enabled"] = False

    def post(self, action, body):
        if action == "capture/start":
            return self.capture.start(body)
        if action == "capture/stop":
            return self.capture.stop()
        if action == "browser/import":
            if body.get("consent") is not True:
                raise InputError(
                    "Explicit consent is required before browser history import."
                )

            def work(context):
                context.progress(10, "Reading selected browser history with consent.")
                result = import_browser(
                    self.store,
                    body.get("path", ""),
                    consent=True,
                    limit=body.get("limit", 1000),
                )
                self.timeline.prune(self.store.get("retention_days", 30))
                return result

            return {"job_id": self.jobs.submit("Import selected browser history", work)}
        if action == "roots/add":
            return self.timeline.add_root(
                body.get("path", ""),
                body.get("project", ""),
                bool(body.get("git_enabled", False)),
                body.get("patterns"),
            )
        if action == "roots/remove":
            with self.scan_lock, self.store.connection() as db:
                ident = integer(body.get("id"), 1, 10**9)
                db.execute("UPDATE events SET root_id=NULL WHERE root_id=?", (ident,))
                db.execute("DELETE FROM roots WHERE id=?", (ident,))
            return {"forgotten": True, "source_files_changed": False}
        if action == "scan":
            return {"job_id": self.scan_all()}
        if action == "monitor/start":
            self.stop_monitor()
            if self.monitor_thread and self.monitor_thread.is_alive():
                raise InputError("The previous monitor is still stopping.")
            seconds = integer(body.get("seconds", 10), 5, 3600)
            job_id = self.scan_all()
            self.monitor_stop = threading.Event()
            self.monitor = {
                "enabled": True,
                "seconds": seconds,
                "last_error": "",
                "last_job": job_id,
            }

            def loop():
                while (
                    not self.monitor_stop.wait(seconds) and not self.shutdown.is_set()
                ):
                    try:
                        last = self.monitor.get("last_job")
                        if not last or self.jobs.get(last)["status"] not in {
                            "queued",
                            "running",
                        }:
                            self.monitor["last_job"] = self.scan_all()
                        self.monitor["last_error"] = ""
                    except Exception as exc:
                        self.monitor["last_error"] = str(exc)[:250]
                self.monitor["enabled"] = False

            self.monitor_thread = threading.Thread(
                target=loop, daemon=True, name="visible-folder-monitor"
            )
            self.monitor_thread.start()
            return {"monitor": self.monitor, "job_id": job_id}
        if action == "monitor/stop":
            self.stop_monitor()
            return self.monitor
        if action == "event/update":
            ident = integer(body.get("id"), 1, 10**12)
            if not self.store.one("SELECT id FROM events WHERE id=?", (ident,)):
                raise InputError("This event does not exist.")
            tags = body.get("tags", [])
            if isinstance(tags, str):
                tags = tags.split(",")
            if not isinstance(tags, list) or len(tags) > 20:
                raise InputError("Use at most 20 tags.")
            tags = sorted(set(str(t).strip()[:40] for t in tags if str(t).strip()))
            self.store.execute(
                "UPDATE events SET note=?,tags=? WHERE id=?",
                (str(body.get("note", ""))[:2000], json.dumps(tags), ident),
            )
            return {"saved": True}
        if action == "note":
            note = str(body.get("note", "")).strip()
            if not note:
                raise InputError("Enter a note.")
            ident = self.store.execute(
                "INSERT INTO events(kind,path,size,mtime,observed,project,note) VALUES(?,?,?,?,?,?,?)",
                (
                    "note",
                    "",
                    0,
                    0,
                    utcnow(),
                    str(body.get("project", "Notes"))[:80],
                    note[:2000],
                ),
            )
            return {"id": ident}
        if action == "retention":
            days = integer(body.get("days", 30), 1, 3650)
            self.store.set("retention_days", days)
            return {"days": days, "deleted_events": self.timeline.prune(days)}
        if action == "erase":
            if body.get("confirm") != "ERASE":
                raise InputError("Type ERASE to delete timeline history.")
            self.stop_monitor()
            self.capture.stop()
            self.store.set("background_resume", None)
            with self.scan_lock, self.store.connection() as db:
                if body.get("before"):
                    cutoff = stamp(body["before"])
                    count = db.execute(
                        "DELETE FROM events WHERE observed<=?", (cutoff,)
                    ).rowcount
                else:
                    count = db.execute("DELETE FROM events").rowcount
                    if db.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='browser_imports'"
                    ).fetchone():
                        db.execute("DELETE FROM browser_imports")
                    db.execute("DELETE FROM snapshots")
                    db.execute("DELETE FROM git_seen")
                    db.execute("UPDATE roots SET initialized=0,last_scan=NULL")
            return {
                "deleted_events": count,
                "source_files_changed": False,
                "note": "This is logical deletion. It is not secure disk erasure. Existing backups are not changed.",
            }
        if action == "demo":
            return self.timeline.seed_demo(self.root / "examples")
        if action == "demo/remove":
            self.store.execute("DELETE FROM events WHERE is_demo=1")
            return {"deleted": True}
        if action == "export":
            rows = self.timeline.events(limit=5000)
            folder = self.new_output("timeline")
            if body.get("format", "json") == "csv":
                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                fields = [
                    "observed",
                    "kind",
                    "project",
                    "path",
                    "size",
                    "note",
                    "is_demo",
                ]
                writer.writerow(fields)
                for row in rows["events"]:
                    values = [str(row[field]) for field in fields]
                    writer.writerow(
                        [
                            (
                                "'" + v
                                if v.lstrip().startswith(("=", "+", "-", "@"))
                                else v
                            )
                            for v in values
                        ]
                    )
                output = unique_write(
                    folder / "timeline.csv", stream.getvalue().encode("utf-8-sig")
                )
            else:
                output = unique_write(
                    folder / "timeline.json",
                    json.dumps(rows, indent=2, ensure_ascii=False).encode("utf-8"),
                )
            return self.artifact(output)
        return super().post(action, body)

    def close(self):
        self.capture.stop()
        self.stop_monitor()
        super().close()
