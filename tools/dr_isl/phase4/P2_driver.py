"""Execute the requested base/candidate GPU contexts; bounded durable evidence."""
# PROPOSED_HERE: ports, polling and startup timeout are audit isolation settings,
# not model constants; the file cap is below the user's 50 MB durability limit.
import argparse
from collections import deque
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PACKAGE = Path("attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim")
TARGET = "tests/test_gpu_load_profile.py::test_gpu_load_profile"
SUMMARY = []


def save(name, value):
    data = (json.dumps(value, indent=2) + "\n").encode()
    assert len(data) < 50_000_000
    (OUT / name).write_bytes(data)


def one(version, checkout, port, context):
    label = f"P2_{version}_{context}"
    save("STATUS.json", {"item": "P2", "state": "RUNNING", "context": label,
                         "completed_contexts": len(SUMMARY), "P1": "51 passed"})
    server_lines = deque(maxlen=100)
    server = subprocess.Popen(
        ["env", "PYTEST_CURRENT_TEST=DR-ISL-P2-subprocess", sys.executable,
         "-m", "uvicorn", "api.app:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "error"],
        cwd=checkout / PACKAGE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    def drain():
        for line in server.stdout:
            # Retain bounded startup diagnostics, never entire tick exports.
            server_lines.append(line[:2000])
    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 90
        while True:
            if server.poll() is not None:
                raise RuntimeError("Server startup failed: " + "".join(server_lines))
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=2).close()
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError("Server startup timeout")
                time.sleep(.2)
        command = [
            sys.executable, "-c",
            f"import sys;sys.path.insert(0,{str(OUT)!r});import pytest;"
            "raise SystemExit(pytest.main(sys.argv[1:]))",
            "-p", "P2_observer", "-q", "--tb=short", "--disable-warnings",
            "--p2-output", str(OUT / label), "--p2-port", str(port),
        ]
        if context == "prefix":
            command += ["tests", "--p2-prefix"]
        else:
            command += [TARGET if context.startswith("isolation") else "tests/test_gpu_load_profile.py"]
        started = time.monotonic()
        with (OUT / (label + ".txt")).open("w") as log:
            proc = subprocess.Popen(command, cwd=checkout / PACKAGE, stdout=log,
                                    stderr=subprocess.STDOUT, text=True)
            while proc.poll() is None:
                if log.tell() >= 48_000_000 or (OUT / (label + ".txt")).stat().st_size >= 48_000_000:
                    proc.terminate()
                    raise RuntimeError("STOP: test output approaching 50 MB cap")
                time.sleep(1)
        result_path = OUT / (label + ".results.json")
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        row = {
            "version": version, "checkout": str(checkout), "context": context,
            "port": port, "http_transport_redirect_only": True,
            "exit_code": proc.returncode, "seconds": time.monotonic() - started,
            "gpu_result": result.get("cases", {}).get(TARGET),
            "preceding_failures": [n for n, v in result.get("cases", {}).items()
                                   if v["outcome"] == "failed" and n != TARGET],
        }
        SUMMARY.append(row)
        save("P2_CONTEXT_SUMMARY.json", SUMMARY)
        print(json.dumps(row), flush=True)
        if TARGET not in result.get("cases", {}):
            save("P2_STOP.json", {"reason": "GPU target did not execute", "result": row,
                                "server_tail": list(server_lines)})
            return False
        return True
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    save("P2_PROTOCOL.json", {
        "base": "ae49aaa", "candidate": "working-tree Phase 4 C2(c) + approved TC18",
        "fresh_server_per_context": True, "changes_to_test_files": False,
        "addressing": "httpx loopback port 22126 redirected to isolated 22127/22128 only",
        "server_context": "PYTEST_CURRENT_TEST: built-in pytest startup context; skips unrelated Postgres reference-forecast import, identically at base and candidate",
        "contexts": ["isolation1", "isolation2", "isolation3", "file", "prefix"],
    })
    for version, checkout, port in [("base", args.base, 22127), ("candidate", ROOT, 22128)]:
        for context in ["isolation1", "isolation2", "isolation3", "file", "prefix"]:
            if not one(version, checkout, port, context):
                return 2
    save("STATUS.json", {"item": "P2", "state": "CONTEXT RUNS COMPLETE; classification pending",
                         "contexts": len(SUMMARY), "P3": "NOT STARTED"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
