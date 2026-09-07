"""Check release source and close both synthetic browser-history databases."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    required = [
        "README.md", "project.json", "app/service.py", "app/capture.py",
        "localdesk/vault.py", "run.py", "web/app.js",
    ]
    for name in required:
        if not (ROOT / name).is_file():
            raise ValueError("Required source is absent: " + name)

    path = ROOT / "tests/test_upgrade.py"
    text = path.read_text(encoding="utf-8")
    # A Connection context commits or rolls back. It does not close the file.
    # Close both browser fixtures so Windows can delete their temporary files.
    for variable in ("path", "source"):
        old = f"with sqlite3.connect({variable}) as db:"
        if text.count(old) > 1:
            raise ValueError("Review the changed browser-history fixtures.")
        text = text.replace(
            old, f"with closing(sqlite3.connect({variable})) as db, db:"
        )
    if "from contextlib import closing" not in text:
        if "import sqlite3\n" not in text:
            raise ValueError("The SQLite fixture import has changed.")
        text = text.replace(
            "import sqlite3\n", "import sqlite3\nfrom contextlib import closing\n", 1
        )
    path.write_text(text, encoding="utf-8")
    shutil.rmtree(ROOT / "_runtime", ignore_errors=True)
    print("Source checked. Both browser-history fixtures close before cleanup.")


if __name__ == "__main__":
    main()
