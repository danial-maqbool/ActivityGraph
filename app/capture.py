"""Opt-in desktop metadata and explicit local browser-history import.

No keystrokes, clipboard content, screenshots, or browser credentials are read.
Window capture stops when this process closes and needs consent again on restart.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from urllib.parse import quote, urlsplit, urlunsplit

from localdesk.jobs import utcnow
from localdesk.safety import InputError, checked_path, integer


def active_window() -> dict:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        window = user32.GetForegroundWindow()
        text = ctypes.create_unicode_buffer(2049)
        user32.GetWindowTextW(window, text, len(text))
        return {"title": text.value, "application": "Windows foreground window"}
    if sys.platform == "darwin":
        script = 'tell application "System Events"\nset p to first application process whose frontmost is true\nset n to name of p\ntry\nreturn n & " | " & name of front window of p\non error\nreturn n\nend try\nend tell'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode:
            raise InputError(
                "Grant macOS Accessibility permission to read window titles."
            )
        return {
            "title": result.stdout.strip()[:2048],
            "application": "macOS foreground window",
        }
    if not os.environ.get("DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        raise InputError(
            "Window-title capture requires an X11 session on Linux. Wayland is not supported by this adapter."
        )
    from Xlib.display import Display

    display = Display()
    try:
        prop = display.screen().root.get_full_property(
            display.intern_atom("_NET_ACTIVE_WINDOW"), 0
        )
        if prop is None or not len(prop.value):
            return {"title": "", "application": "X11"}
        window = display.create_resource_object("window", int(prop.value[0]))
        title = window.get_full_property(
            display.intern_atom("_NET_WM_NAME"), display.intern_atom("UTF8_STRING")
        )
        value = (
            title.value.decode("utf-8", "replace")
            if title is not None
            else (window.get_wm_name() or "")
        )
        return {"title": str(value)[:2048], "application": "X11 foreground window"}
    finally:
        display.close()


class WindowCapture:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.thread = None
        self.state = {
            "enabled": False,
            "consent_required": True,
            "seconds": 5,
            "last_error": "",
            "recorded": 0,
        }

    def start(self, body):
        if body.get("consent") is not True:
            raise InputError(
                "Explicit consent is required before recording window titles."
            )
        seconds = integer(body.get("seconds", 5), 3, 3600)
        exclusions = body.get("exclude", ["password", "private browsing", "incognito"])
        if not isinstance(exclusions, list) or len(exclusions) > 40:
            raise InputError("Use a list of at most 40 excluded title terms.")
        exclusions = [str(x).casefold()[:100] for x in exclusions if str(x)]
        self.stop()
        if self.thread and self.thread.is_alive():
            raise InputError("The previous capture session is still stopping.")
        # Confirm that the OS adapter works before reporting enabled capture.
        active_window()
        self.stop_event = threading.Event()
        self.state = {
            "enabled": True,
            "consent_required": False,
            "seconds": seconds,
            "last_error": "",
            "recorded": 0,
        }

        def loop():
            previous = ""
            while not self.stop_event.is_set():
                try:
                    info = active_window()
                    title = str(info.get("title", ""))[:2048]
                    if (
                        title
                        and title != previous
                        and not any(x in title.casefold() for x in exclusions)
                    ):
                        self.store.execute(
                            "INSERT INTO events(kind,path,size,mtime,observed,project,note) VALUES(?,?,?,?,?,?,?)",
                            (
                                "window",
                                "",
                                0,
                                0,
                                utcnow(),
                                "Desktop",
                                info.get("application", "Desktop") + ": " + title,
                            ),
                        )
                        self.state["recorded"] += 1
                    previous = title
                    self.state["last_error"] = ""
                except Exception as exc:
                    self.state["last_error"] = str(exc)[:250]
                self.stop_event.wait(seconds)
            self.state["enabled"] = False

        self.thread = threading.Thread(
            target=loop, daemon=True, name="consented-window-metadata"
        )
        self.thread.start()
        return dict(self.state)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)
        self.state["enabled"] = False
        self.state["consent_required"] = True
        return dict(self.state)


def import_browser(store, path, *, consent=False, limit=1000):
    if consent is not True:
        raise InputError(
            "Explicit consent is required to import a browser history database."
        )
    source = checked_path(path)
    maximum = integer(limit, 1, 5000)
    connection = sqlite3.connect(
        "file:" + quote(source.as_posix()) + "?mode=ro", uri=True, timeout=2
    )
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "urls" in tables:
            rows = connection.execute(
                "SELECT url,title,last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT ?",
                (maximum,),
            ).fetchall()
            browser, epoch = "Chromium", datetime(1601, 1, 1, tzinfo=timezone.utc)
        elif "moz_places" in tables:
            rows = connection.execute(
                "SELECT url,title,last_visit_date FROM moz_places WHERE last_visit_date IS NOT NULL ORDER BY last_visit_date DESC LIMIT ?",
                (maximum,),
            ).fetchall()
            browser, epoch = "Firefox", datetime(1970, 1, 1, tzinfo=timezone.utc)
        else:
            raise InputError(
                "Select a Chromium History or Firefox places.sqlite database."
            )
    except sqlite3.DatabaseError as exc:
        raise InputError(
            "Browser history is locked or unreadable. Close the browser and select a local copy."
        ) from exc
    finally:
        connection.close()
    store.execute(
        "CREATE TABLE IF NOT EXISTS browser_imports(key TEXT PRIMARY KEY,event_id INTEGER)"
    )
    added, excluded = 0, 0
    with store.connection() as db:
        for url, title, microseconds in rows:
            try:
                parts = urlsplit(str(url))
                if parts.scheme not in {"http", "https"} or not parts.hostname:
                    excluded += 1
                    continue
                # Do not persist credentials, queries, or fragment tokens.
                host = parts.hostname
                if ":" in host:
                    host = "[" + host + "]"
                if parts.port is not None:
                    host += ":" + str(parts.port)
                cleaned = urlunsplit((parts.scheme, host, parts.path[:1800], "", ""))
                observed = (
                    (epoch + timedelta(microseconds=int(microseconds)))
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )
            except (TypeError, ValueError, OverflowError):
                excluded += 1
                continue
            key = hashlib.sha256(
                (browser + str(source) + str(microseconds) + cleaned).encode()
            ).hexdigest()
            if db.execute(
                "SELECT 1 FROM browser_imports WHERE key=?", (key,)
            ).fetchone():
                continue
            ident = db.execute(
                "INSERT INTO events(kind,path,size,mtime,observed,project,note) VALUES(?,?,?,?,?,?,?)",
                (
                    "browser",
                    cleaned,
                    0,
                    0,
                    observed,
                    "Browser",
                    str(title or "")[:2000],
                ),
            ).lastrowid
            db.execute("INSERT INTO browser_imports VALUES(?,?)", (key, ident))
            added += 1
    return {
        "imported": added,
        "excluded": excluded,
        "browser": browser,
        "source_modified": False,
        "note": "URL credentials, query strings, and fragments were removed. Titles and paths can still contain private information.",
    }
