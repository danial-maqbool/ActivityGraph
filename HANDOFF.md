# ActivityGraph: local testing handoff

Handoff revision: 1. Prepared on 2026-09-07. Application version: 0.2.0.

## Status

The application source is published. This handoff prepares a repeatable local acceptance pass.
It does not certify the user PC, native permissions, every input file, or optional neural weights.
Do not remove documented processing boundaries to change the completion status.

The prior release evidence was recorded at `77b1eb620eb7aafc32e6105ffad81d62e18375e5`.
It reports 121 passing full Linux test executions and 18 browser checks.
Those counts are historical. Shared tests occur in each repository. Native-tool and OS-specific skips are recorded separately.
Use current GitHub Actions and new local reports to verify the handoff commit. Do not present the prior counts as a new run.

## Changes in this handoff

`bootstrap.py --dev` installs test tools into this project .venv.
`scripts/preflight.py` checks Python, direct package pins, SQLite FTS5, and applicable native-tool availability.
`--report-dir` keeps local test reports and media separate from committed release evidence.
Browser reports now distinguish started, failed, and completed runs. An interrupted run cannot keep a stale pass report.
Ten handoff regression tests check setup, requirement handling, and report isolation.

## Read order

Read `AGENTS.md`, this file, `handoff.json`, and `docs/LOCAL_TESTING.md` first.
Then read `docs/SETUP.md`, `docs/LIMITS.md`, `SECURITY.md`, and `docs/VERIFICATION.md`.
The full agent brief is in `docs/LOCAL_AGENT_PROMPT.md`.
Use `docs/LOCAL_TEST_RESULTS.template.md` for the sanitized final report.

## Start and verify

Windows PowerShell, from this repository root:

```powershell
py -3 bootstrap.py
.\.venv\Scripts\python.exe scripts/preflight.py --report-dir artifacts/local-qa/runtime
.\start.bat --demo
```

Stop the demo. Then follow the full runtime-only and development-install checks in `docs/LOCAL_TESTING.md`.
The default local port is `8764`. Use `--port 0 --no-browser` for a temporary server on an available port.
Use a unique `--data-dir` for persistence tests. `--demo` uses temporary data and does not prove persistent vault behavior.
Normal startup needs a vault passphrase. Do not put a real passphrase in a command, script, commit, or report.

## Project acceptance scope

| ID | Area | Required evidence |
| :--- | :--- | :--- |
| AG-01 | Folder history | Observe a selected synthetic folder. Check discovery, creation, modification, rename behavior, and removal. Do not label initial discovery as file creation. |
| AG-02 | No content collection | Insert a unique string inside a fixture document. Confirm event metadata does not store document content. Verify folder exclusions and polling limits. |
| AG-03 | Timeline and graph | Add notes and tags. Search and filter events. Verify graph edges reference existing nodes. Session grouping must not claim measured work hours. |
| AG-04 | Window-title consent | On a supported disposable desktop, confirm capture is off by default, needs explicit consent, respects excluded titles, and stops when paused or the process exits. Restart must require consent again. |
| AG-05 | Browser import | Create separate synthetic Chromium and Firefox history databases. Verify explicit consent, timestamps, duplicate prevention, and removal of URL credentials, queries, and fragments. Do not read the user real browser profile. |
| AG-06 | Retention and erase | Test retention cutoffs and explicit erase confirmation. Erase recorded history and browser-import keys without deleting monitored source files. |
| AG-07 | Background operation | Test saved folder monitoring across process restart and native login-service installation/removal in a disposable OS profile. Do not enable sensitive title capture through the service. |
| AG-08 | Local privacy | Test vault persistence, wrong password, altered bytes, concurrent writer rejection, and offline semantic search. A sleeping or stopped computer cannot record events. |

## Work that requires the local machine

Test the relevant native adapters on the actual target OS. Do not infer their behavior from mocked tests.
Install required native tools and language data. Check actual outputs with independent parsers or viewers.
Test a clean runtime-only environment, paths with spaces and Unicode, offline operation, and the existing app data migration path when applicable.
Measure local performance with synthetic fixtures. No universal hardware benchmark is claimed.
Use a disposable OS profile for service and credential-store checks. Do not alter the user active desktop without local consent.

## Evidence and Git rules

Keep raw logs, resolved dependency lists, screenshots, and temporary outputs under ignored `artifacts/`.
The committed `docs/test-report.json`, `docs/browser-report.json`, and `docs/platforms/` remain historical release evidence.
New local reports must identify their actual commit and environment. Review evidence before publishing it.
Never commit user documents, browser history, vaults, passwords, API tokens, model weights, or .venv.
Work on main and push only main. Preserve existing changes. Never force-push or reset user work. Keep exactly one remote branch, main; preserve tags.

If a shared `localdesk/` defect is fixed, compare all five copies and apply only the relevant patch.
Run each affected repository suite. The apps must remain independently cloneable and runnable.
Do not run `scripts/prepare_release.py` as an installer. Use `bootstrap.py`.
Update source-manifest hashes only after reviewing changes. Preserve real tests and security controls.

## Acceptance decision

Local-machine acceptance: **NOT RUN HERE**.
Use PASS, FAIL, BLOCKED, NOT RUN, or NOT APPLICABLE for each case.
Only state that local acceptance is complete when every applicable gate has evidence.
If a permission blocks one test, record that requirement and continue unrelated tests.

## Local PC acceptance: 2026-09-07

Decision: PARTIAL. See [the current local acceptance report](docs/LOCAL_ACCEPTANCE_REPORT.md).

Tested source `6f8b2abbbd929bc6be0b8650b2e0019f238b8916` on Windows 11 AMD64, Python 3.14.3. Runtime-only setup and real samples completed before dev installation. Windows suite: 135 run, 132 passed, 3 skipped, no failures/errors; strict exits 1. Direct-browser checks: 20 passed with actual downloads. Network-disabled Linux container on this PC: 135 tests, no skips, 20 browser checks.

Windows manifest and browser synchronization checks were repaired with retained regressions. Evidence is ignored under `artifacts/local-qa/20260907-acceptance-01/`. Historical release reports remain historical. Native-session and symlink limits are detailed in the report. Worker CI report-directory reuse was repaired with two preservation regressions.

## Current target-PC follow-up: 2026-09-08

Status: BLOCKED. Current report: [local acceptance](docs/LOCAL_ACCEPTANCE_REPORT.md). Tested main `191a807fc1b6dc48a4407a202aad06014c0c4122`. Fresh source/vault symlink probe failed with WinError 1314; exact tests remain two skips. The user confirmed no disposable Windows session is available. No native service or desktop controls were used in the personal profile.

Runtime source is unchanged from the earlier tested revision. Its 132 passing Windows tests and 20 browser checks remain dated evidence, not reruns. Only remaining symlink capability checks were invoked this run.

Current ignored evidence: `artifacts/local-qa/20260908-final-acceptance-01/`. No new application fix or regression test was needed in this run. Git policy: main only locally/remotely, no temporary remote branches, no force-push or tag rewrite.
