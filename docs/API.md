# Local API

This API is for the running local app. It is not a hosted service or a stable public API contract.
The server listens on `127.0.0.1:8764` by default.

## Session checks

The index page supplies a random token for the current Python process.
The UI sends it in the `X-Local-Token` header. Every API request must use the current token.
POST requests must use `Content-Type: application/json`. The body limit is 36 MiB.
The server checks Host and Origin and does not enable cross-origin access.

Do not copy the token into a repository or enable network forwarding to the port.
Restarting the Python process changes the token.

## Common operations

| Method | Path | Input | Result |
| :--- | :--- | :--- | :--- |
| GET | `/api/info` | none | Name, version, paths, and local optional-tool availability. |
| GET | `/api/state` | none | Current application state and recent jobs. |
| GET | `/api/browse` | path, optional | Up to 1,500 visible folder entries. |
| GET | `/api/jobs/ID` | job ID in the path | Status, progress, result, or error. |
| POST | `/api/cancel` | id | Request cooperative job cancellation. |
| POST | `/api/upload` | name, base64 content | Save a new private inbox file. |
| POST | `/api/backup` | none | Write a database-only backup artifact. |

## Application operations

| Method | Path | Input | Result |
| :--- | :--- | :--- | :--- |
| GET | `/api/events` | q, kind, project, after, before, tag, limit; optional | Return the filtered timeline. |
| GET | `/api/graph` | none | Return bounded project and file relationships. |
| GET | `/api/sessions` | none | Return nearby change groups, not work-time measurements. |
| POST | `/api/roots/add` | path; project, patterns, git_enabled, optional | Add a selected folder. |
| POST | `/api/roots/remove` | id | Stop following a root and retain its previous events. |
| POST | `/api/scan` | none | Scan selected roots once. |
| POST | `/api/monitor/start` | seconds | Start interval checks explicitly. |
| POST | `/api/monitor/stop` | none | Stop interval checks. |
| POST | `/api/event/update` | id; note, tags, optional | Annotate an event. |
| POST | `/api/note` | note; project, optional | Add a manual note. |
| POST | `/api/retention` | days | Apply the retention setting. |
| POST | `/api/erase` | confirm: ERASE | Logically clear history and snapshots. |
| POST | `/api/demo` | none | Add eight clearly marked synthetic events. |
| POST | `/api/demo/remove` | none | Remove only demo events. |
| POST | `/api/export` | format: json or csv | Export up to 5,000 recent events. |

### Example request body

Send this JSON to `POST /api/note` with the current session token:

```json
{
  "note": "Checked the output against the source data.",
  "project": "Research"
}
```

Use paths from the computer running Python. Change the example path before sending the request.
A job-start response contains `job_id`. Read `/api/jobs/ID` until its status is terminal.
Read the error field when the job fails. Do not treat a queued response as a completed operation.

An artifact response contains its name, relative output path, and size. The browser download helper requests only paths under the app output directory.
Use `web/common.js` as the reference client for the exact response envelope and download route.

## Version 0.2.0

All routes require the local session token. Use the user interface to review a job before an output operation. The source hash binds a review to the selected source bytes.

`capture/start` requires `consent: true`, an interval, and optional exclusion terms. `capture/stop` ends capture. `browser/import` requires an explicit local database path and `consent: true`. Timeline search accepts `mode: semantic` or keyword search.
