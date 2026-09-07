# Changes

## 2026-09-07: local acceptance handoff

- Add project-specific acceptance cases, local requirements, and an agent brief.
- Add development setup and prerequisite checks.
- Keep local test reports and recorded media separate from release evidence.
- Record browser run state to prevent stale success reports after a failed run.


## 0.2.0

- Selected folders: Record created, changed, and removed files. Do not record file contents.
- Local Git history: Import commit metadata from selected repositories without contacting a remote.
- Window titles: Enable visible, consent-based capture for the current desktop session. Pause it at any time.
- Browser history import: Choose a local Chromium or Firefox history database. Import it only after explicit consent.
- Timeline search: Search metadata with keywords or a local semantic model. Filter events by project and kind.
- Project graph: Connect observed files and projects. Group related activity into sessions.
- Retention controls: Add notes and tags. Delete periods or erase recorded history without changing source files.
- Encrypted worker: Keep records encrypted. Resume selected-folder monitoring through a user-login worker.

The release also includes encrypted storage, request checks, portable output paths, synthetic examples, test reports, and recorded interface media.
