"""Check materialized source and close the synthetic browser-history fixture."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in [
        "README.md",
        "project.json",
        "app/service.py",
        "app/capture.py",
        "localdesk/vault.py",
        "run.py",
        "web/app.js",
    ]:
        if not (ROOT / name).is_file():
            raise ValueError("Required source is absent: " + name)
    path = ROOT / "tests/test_upgrade.py"
    text = path.read_text(encoding="utf-8")
    old = "with sqlite3.connect(path) as db:"
    if old in text:
        if text.count(old) != 1:
            raise ValueError("Review the changed browser-history fixture.")
        text = text.replace(
            "import sqlite3\n", "import sqlite3\nfrom contextlib import closing\n"
        )
        text = text.replace(old, "with closing(sqlite3.connect(path)) as db, db:")
        path.write_text(text, encoding="utf-8")
    shutil.rmtree(ROOT / "_runtime", ignore_errors=True)
    print("Source checked. The browser-history fixture closes before Windows cleanup.")


if __name__ == "__main__":
    main()
