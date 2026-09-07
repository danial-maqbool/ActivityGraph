"""Consent-scoped file metadata history. This module never reads file contents."""

from __future__ import annotations
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from localdesk.jobs import utcnow
from localdesk.safety import (
    DEFAULT_EXCLUDES,
    InputError,
    checked_path,
    walk_files,
    within,
)

EVENT_KINDS = {
    "discovered",
    "created",
    "modified",
    "deleted",
    "git_commit",
    "note",
    "window",
    "browser",
}


def stamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise InputError("Use an ISO date or date-time value.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


class Timeline:
    def __init__(self, store, private_data: Path):
        self.store, self.private_data = store, private_data
        with store.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS roots(
                    id INTEGER PRIMARY KEY,path TEXT UNIQUE,project TEXT,patterns TEXT,
                    git_enabled INTEGER DEFAULT 0,initialized INTEGER DEFAULT 0,last_scan TEXT);
                CREATE TABLE IF NOT EXISTS snapshots(
                    root_id INTEGER REFERENCES roots(id) ON DELETE CASCADE,path TEXT,
                    size INTEGER,mtime INTEGER,PRIMARY KEY(root_id,path));
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY,root_id INTEGER REFERENCES roots(id) ON DELETE CASCADE,
                    kind TEXT,path TEXT,size INTEGER,mtime INTEGER,observed TEXT,project TEXT,
                    note TEXT DEFAULT '',tags TEXT DEFAULT '[]',is_demo INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS events_time ON events(observed);
                CREATE INDEX IF NOT EXISTS events_root ON events(root_id);
                CREATE TABLE IF NOT EXISTS git_seen(
                    root_id INTEGER REFERENCES roots(id) ON DELETE CASCADE,sha TEXT,
                    PRIMARY KEY(root_id,sha));
            """
            )

    def add_root(
        self, path: str, project: str = "", git_enabled: bool = False, patterns=None
    ):
        folder = checked_path(path, directory=True)
        if within(folder, self.private_data):
            raise InputError("Do not monitor the app data directory.")
        project = (str(project).strip() or folder.name or "Local folder")[:80]
        patterns = patterns or []
        if not isinstance(patterns, list) or len(patterns) > 80:
            raise InputError("Use at most 80 exclusion patterns.")
        patterns = list(
            dict.fromkeys([*DEFAULT_EXCLUDES, *(str(p)[:150] for p in patterns)])
        )
        self.store.execute(
            "INSERT INTO roots(path,project,patterns,git_enabled) VALUES(?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET project=excluded.project,patterns=excluded.patterns,git_enabled=excluded.git_enabled",
            (str(folder), project, json.dumps(patterns), int(git_enabled)),
        )
        return self.store.one("SELECT * FROM roots WHERE path=?", (str(folder),))

    def scan(self, ident: int, context) -> dict:
        root = self.store.one("SELECT * FROM roots WHERE id=?", (ident,))
        if root is None:
            raise InputError("This monitored folder does not exist.")
        folder = checked_path(root["path"], directory=True)
        current = {}
        context.progress(5, "Reading file names, sizes, and modification times.")
        for p in walk_files(folder, patterns=json.loads(root["patterns"])):
            context.check()
            if within(p, self.private_data):
                continue
            stat = p.stat()
            current[str(p)] = {"size": stat.st_size, "mtime": stat.st_mtime_ns}
        previous = {
            r["path"]: r
            for r in self.store.rows(
                "SELECT * FROM snapshots WHERE root_id=?", (ident,)
            )
        }
        events, observed = [], utcnow()
        for path, info in current.items():
            old = previous.get(path)
            if not old:
                kind = "created" if root["initialized"] else "discovered"
            elif (old["size"], old["mtime"]) != (info["size"], info["mtime"]):
                kind = "modified"
            else:
                continue
            events.append(
                (
                    ident,
                    kind,
                    path,
                    info["size"],
                    info["mtime"],
                    observed,
                    root["project"],
                )
            )
        for path, old in previous.items():
            if path not in current:
                events.append(
                    (
                        ident,
                        "deleted",
                        path,
                        old["size"],
                        old["mtime"],
                        observed,
                        root["project"],
                    )
                )
        context.check()
        with self.store.connection() as db:
            db.executemany(
                "INSERT INTO events(root_id,kind,path,size,mtime,observed,project) VALUES(?,?,?,?,?,?,?)",
                events,
            )
            db.execute("DELETE FROM snapshots WHERE root_id=?", (ident,))
            db.executemany(
                "INSERT INTO snapshots VALUES(?,?,?,?)",
                [(ident, p, v["size"], v["mtime"]) for p, v in current.items()],
            )
            db.execute(
                "UPDATE roots SET initialized=1,last_scan=? WHERE id=?",
                (observed, ident),
            )
        git_events, git_warning = (
            self.read_git(root) if root["git_enabled"] else (0, "")
        )
        return {
            "folder": str(folder),
            "files": len(current),
            "events": len(events),
            "git_events": git_events,
            "warning": git_warning,
            "note": "Times show when the app observed a change. They are not exact user-action times.",
        }

    def read_git(self, root: dict) -> tuple[int, str]:
        binary = shutil.which("git")
        if not binary:
            return 0, "Git is not installed. File metadata monitoring still works."
        folder = Path(root["path"])
        if not (folder / ".git").exists():
            return 0, "No Git repository exists at the selected root."
        try:
            result = subprocess.run(
                [
                    binary,
                    "--no-pager",
                    "--no-optional-locks",
                    "-c",
                    "core.fsmonitor=false",
                    "-C",
                    str(folder),
                    "log",
                    "-20",
                    "--format=%H%x1f%cI%x1f%s",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 0, "The read-only Git log command could not finish."
        if result.returncode:
            return 0, "Git history was not readable. The folder may have no commits."
        count = 0
        with self.store.connection() as db:
            for line in result.stdout[:32_000].splitlines():
                parts = line.split("\x1f", 2)
                if len(parts) != 3:
                    continue
                sha, commit_time, subject = parts
                if db.execute(
                    "SELECT 1 FROM git_seen WHERE root_id=? AND sha=?",
                    (root["id"], sha),
                ).fetchone():
                    continue
                db.execute("INSERT INTO git_seen VALUES(?,?)", (root["id"], sha))
                db.execute(
                    "INSERT INTO events(root_id,kind,path,size,mtime,observed,project,note) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        root["id"],
                        "git_commit",
                        str(folder),
                        0,
                        0,
                        utcnow(),
                        root["project"],
                        f"{sha[:12]} | Commit time: {commit_time} | {subject[:300]}",
                    ),
                )
                count += 1
        return count, ""

    def events(
        self,
        *,
        query: str = "",
        kind: str = "",
        project: str = "",
        tag: str = "",
        after: str = "",
        before: str = "",
        limit: int = 500,
    ):
        clauses, args = [], []
        if query:
            escaped = (
                query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            clauses.append(
                "(path LIKE ? ESCAPE '\\' OR note LIKE ? ESCAPE '\\' OR project LIKE ? ESCAPE '\\')"
            )
            args.extend(["%" + escaped + "%"] * 3)
        if kind:
            if kind not in EVENT_KINDS:
                raise InputError("This event type does not exist.")
            clauses.append("kind=?")
            args.append(kind)
        if project:
            clauses.append("project=?")
            args.append(project)
        if after:
            clauses.append("observed>=?")
            args.append(stamp(after))
        if before:
            clauses.append("observed<=?")
            args.append(stamp(before))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.store.rows(
            "SELECT * FROM events" + where + " ORDER BY observed DESC,id DESC LIMIT ?",
            (*args, limit),
        )
        for row in rows:
            row["tags"] = json.loads(row["tags"])
            row["name"] = (
                row["note"][:70]
                if row["kind"] == "window"
                else (Path(row["path"]).name if row["path"] else "Manual note")
            )
        if tag:
            rows = [row for row in rows if tag in row["tags"]]
        return {"events": rows, "limited": len(rows) >= limit, "limit": limit}

    def sessions(self) -> dict:
        rows = list(reversed(self.events(limit=2000)["events"]))
        groups = []
        for row in rows:
            if (
                not groups
                or (
                    datetime.fromisoformat(row["observed"])
                    - datetime.fromisoformat(groups[-1]["end"])
                ).total_seconds()
                > 20 * 60
            ):
                groups.append(
                    {
                        "start": row["observed"],
                        "end": row["observed"],
                        "events": 0,
                        "projects": set(),
                        "files": set(),
                    }
                )
            group = groups[-1]
            group["end"], group["events"] = row["observed"], group["events"] + 1
            group["projects"].add(row["project"])
            if row["path"]:
                group["files"].add(row["path"])
        for group in groups:
            group["projects"] = sorted(group["projects"])
            group["files"] = len(group["files"])
        return {
            "sessions": list(reversed(groups)),
            "method": "Events separated by no more than 20 minutes form one group. These are observed changes, not measured work time.",
        }

    def graph(self) -> dict:
        rows = self.events(limit=500)["events"]
        nodes, edges = {}, {}
        for row in rows:
            project_id = "project:" + row["project"]
            nodes.setdefault(
                project_id,
                {
                    "id": project_id,
                    "label": row["project"],
                    "kind": "project",
                    "count": 0,
                },
            )["count"] += 1
            if not row["path"]:
                continue
            file_id = "file:" + row["path"]
            nodes.setdefault(
                file_id,
                {
                    "id": file_id,
                    "label": Path(row["path"]).name,
                    "kind": "file",
                    "path": row["path"],
                    "count": 0,
                },
            )["count"] += 1
            edges[(project_id, file_id)] = {
                "source": project_id,
                "target": file_id,
                "relation": "observed in",
            }
        projects = [n for n in nodes.values() if n["kind"] == "project"][:12]
        files = sorted(
            (n for n in nodes.values() if n["kind"] == "file"),
            key=lambda n: -n["count"],
        )[:45]
        kept = {n["id"] for n in [*projects, *files]}
        return {
            "nodes": [*projects, *files],
            "edges": [
                e for e in edges.values() if e["source"] in kept and e["target"] in kept
            ],
            "note": "The graph shows up to 45 files and 12 projects from the last 500 events.",
        }

    def prune(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="seconds"
        )
        with self.store.connection() as db:
            cursor = db.execute("DELETE FROM events WHERE observed<?", (cutoff,))
            return cursor.rowcount

    def seed_demo(self, example_root: Path):
        if self.store.one("SELECT id FROM events WHERE is_demo=1 LIMIT 1"):
            return {"added": 0}
        now = datetime.now(timezone.utc)
        samples = [
            (
                120,
                "discovered",
                "project-notes.md",
                "Research",
                "Initial demo file list",
            ),
            (112, "modified", "project-notes.md", "Research", "Added evaluation notes"),
            (105, "created", "results.csv", "Research", "New experiment results"),
            (
                98,
                "git_commit",
                "research-project",
                "Research",
                "Demo commit: document evaluation steps",
            ),
            (
                35,
                "created",
                "travel-checklist.txt",
                "Personal",
                "Created a travel checklist",
            ),
            (
                29,
                "modified",
                "travel-checklist.txt",
                "Personal",
                "Added reminder items",
            ),
            (
                12,
                "created",
                "invoice-register.csv",
                "Office",
                "Exported invoice register",
            ),
            (4, "note", "", "Office", "Check the supplier totals before the review"),
        ]
        with self.store.connection() as db:
            for minutes, kind, filename, project, note in samples:
                db.execute(
                    "INSERT INTO events(kind,path,size,mtime,observed,project,note,tags,is_demo) VALUES(?,?,?,?,?,?,?,?,1)",
                    (
                        kind,
                        str(example_root / filename) if filename else "",
                        0,
                        0,
                        (now - timedelta(minutes=minutes)).isoformat(
                            timespec="seconds"
                        ),
                        project,
                        note + " [simulated demo]",
                        '["demo"]',
                    ),
                )
        return {
            "added": len(samples),
            "note": "These are simulated demo events, not recorded computer activity.",
        }
