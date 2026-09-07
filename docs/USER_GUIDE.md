# Daily use

## Start

Install Python 3.11 or later. Open the extracted project folder. Run `python bootstrap.py` once, then use `start.bat` on Windows or `sh start.sh` on Linux or macOS. Setup creates a private `.venv` folder. See [Setup](SETUP.md) for local tools and offline installation.

The normal app asks for a vault passphrase with at least 12 characters. Keep that passphrase. No server can reset it. Use `start.bat --demo` or `sh start.sh --demo` to try synthetic data without a persistent database.

The browser connects only to the local Python process. Closing the browser does not stop the worker. Press Ctrl+C in the terminal to stop a foreground worker. Use `run.py --port 0` to select a free port.

## Folder timeline

Load the labeled demo timeline first. Open an event to edit its project, note, or tags. Add a manual note. Use the graph to inspect connections between files and projects. Filter by type or time. Select semantic search to compare the meaning of local event text.

Add folders on the monitoring page. The first scan records a baseline. Later scans record new, changed, or missing files. Folder monitoring records metadata, not file contents. Explicit file-open activity is not inferred from modification times.

Enable monitoring only for folders you intend to record. Review exclusions and retention. Folder monitoring settings can resume after unlocking the vault. Install the optional user-login worker as described in [Background operation](BACKGROUND.md).

## Window-title capture

Select **Enable with consent** to review the window-title option. Read the warning, set the interval and exclusions, and confirm. The app records changes to the foreground window title. It does not record keystrokes, clipboard content, or screen pixels.

Capture requires an unlocked Windows or macOS desktop, or an X11 session on Linux. macOS can require Accessibility permission. The adapter does not bypass Wayland security restrictions. Capture remains off after restart until you confirm again. Select Stop capture to end the current session.

Titles can contain private text. Add exclusions before capture. The default exclusions include password, private browsing, and incognito. These text filters are not a complete private-window detector.

## Browser-history import

Choose the local browser-history import control. Close the browser and select a copy of Chromium's `History` or Firefox's `places.sqlite` file. Confirm the explicit import and choose a record limit. The app never searches browser profiles on its own.

The importer removes URL usernames, passwords, query strings, and fragments. Titles and URL paths can still contain private information. The imported history is local and encrypted with the app database. Repeated imports skip previously recorded entries. The selected browser database is read-only.

## Retention and export

Use the privacy page to remove old events or erase the timeline. Erasing stops active recording and clears stored import keys. CSV and JSON exports are ordinary unencrypted files. Review them before sharing.

## Storage and support

The app stores its database in `.local-data/app.vault`. The database and its backups use authenticated encryption. Uploaded source copies and exported files are not encrypted by this app. Keep them in a protected folder.

Stop the app before copying its whole data folder. Keep the passphrase with a separate protected backup. Do not delete an original file until you have checked its output. Deleting a folder is not secure disk erasure.

When a source changes after review, scan it again. When a parser reports a size, page, or time limit, split the source. Do not publish private examples in a bug report. Include the exact error, app version, operating system, and a synthetic sample instead.
