"""Real subprocess worker persistence with synthetic data and no OS login service."""

from pathlib import Path
import argparse
import hashlib
import secrets
import json
import os
import re
import subprocess
import sys
import time
import urllib.request


def prepare_report_dir(path):
    evidence = path.resolve()
    if evidence.exists():
        evidence = evidence / ("worker-" + secrets.token_hex(6))
    evidence.mkdir(parents=True, exist_ok=False)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    evidence = prepare_report_dir(args.report_dir)
    workspace = evidence / "synthetic input"
    workspace.mkdir()
    data = evidence / "data"
    name = json.loads((root / "project.json").read_text())["repository"]
    prefix = "watch" if name == "FileLens-Desktop" else "monitor"
    process = log = None
    url = token = ""
    starts = 0
    checks = []
    password = secrets.token_urlsafe(32)

    def start():
        nonlocal process, log, url, token, starts
        starts += 1
        logpath = evidence / f"worker-{starts}.log"
        log = logpath.open("w", encoding="utf-8")
        env = dict(
            os.environ, QA_SYNTHETIC_WORKER_KEY=password
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "run.py",
                "worker",
                "--port",
                "0",
                "--data-dir",
                str(data),
                "--passphrase-env",
                "QA_SYNTHETIC_WORKER_KEY",
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            match = re.search(
                r"http://127\.0\.0\.1:\d+", logpath.read_text(encoding="utf-8")
            )
            if match:
                url = match.group()
                with urllib.request.urlopen(url, timeout=5) as response:
                    html = response.read().decode()
                token = re.search(
                    r'name="local-session" content="([^"]+)"', html
                ).group(1)
                return
            if process.poll() is not None:
                raise AssertionError(logpath.read_text())
            time.sleep(0.1)
        raise TimeoutError("worker startup")

    def stop():
        nonlocal process, log
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process = None
        if log:
            log.close()
            log = None

    def api(action, body=None):
        request = urllib.request.Request(
            url + "/api/" + action,
            data=None if body is None else json.dumps(body).encode(),
            headers={"X-Local-Token": token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    try:
        start()
        api("roots/add", {"path": str(workspace), "project": "Synthetic QA"})
        api(prefix + "/start", {"seconds": 15})
        state = api("state")
        key = "watcher" if prefix == "watch" else "monitor"
        assert state[key]["enabled"]
        checks.append("Explicit background selection starts")
        stop()
        start()
        assert api("state")[key]["enabled"]
        checks.append("Enabled settings survive process exit and encrypted restart")
        if name == "ActivityGraph":
            assert not api("state")["capture"]["enabled"]
        source = workspace / "after restart.txt"
        source.write_text("WORKER_CANARY_PUBLIC", encoding="utf-8")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            found = (
                api("search?q=WORKER_CANARY_PUBLIC")["results"]
                if prefix == "watch"
                else [
                    r
                    for r in api("events")["events"]
                    if "after restart.txt" in r["path"]
                ]
            )
            if found:
                break
            time.sleep(0.4)
        else:
            raise AssertionError("Restarted worker did not observe the synthetic file")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        checks.append(
            "Real watched-file event processed after restart without changing source"
        )
        api(prefix + "/stop", {})
        stop()
        start()
        assert not api("state")[key]["enabled"]
        checks.append("Paused settings survive another process restart")
        report = {
            "status": "PASS",
            "checks": checks,
            "passed": len(checks),
            "source_sha256": before,
            "native_login_service_tested": False,
        }
    except Exception:
        import traceback

        report = {
            "status": "FAIL",
            "checks": checks,
            "error": traceback.format_exc(),
            "native_login_service_tested": False,
        }
    finally:
        stop()
    (evidence / "worker-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
