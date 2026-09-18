"""Restart the DeerFlow gateway (native dev process) with a working reload config.

Mirrors scripts/serve.sh:
    (cd backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 ...)
but passes explicit reload includes/excludes, because --reload-include replaces
uvicorn's default *.py pattern (so backend .py edits never hot-reloaded).
"""

import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request

REPO = pathlib.Path(r"E:\DeerFlow")
BACKEND = REPO / "backend"
LOG = REPO / "logs" / "gateway.log"
UV = r"C:\Users\Dance\.local\bin\uv.exe"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

RELOAD_FLAGS = [
    "--reload",
    "--reload-dir=app",
    "--reload-include=*.py",
    "--reload-include=*.yaml",
    "--reload-include=.env",
]
FALLBACK_FLAGS = ["--reload", "--reload-include=*.yaml", "--reload-include=.env"]


def port_open() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", 8001)) == 0
    finally:
        s.close()


def gateway_pids() -> list[int]:
    out = subprocess.run(
        ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
        capture_output=True,
        text=True,
    ).stdout
    pids = []
    for line in out.splitlines():
        if "app.gateway.app:app" in line:
            m = re.search(r"(\d+)\s*$", line.strip())
            if m:
                pids.append(int(m.group(1)))
    return pids


def kill_gateway() -> None:
    for pid in gateway_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        print(f"killed gateway pid {pid}")


def wait_port_free(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_open():
            return True
        time.sleep(0.5)
    return not port_open()


def launch(flags: list[str]) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["NO_COLOR"] = "1"
    log = open(LOG, "ab", buffering=0)
    proc = subprocess.Popen(
        [UV, "run", "uvicorn", "app.gateway.app:app", "--host", "0.0.0.0", "--port", "8001", *flags],
        cwd=str(BACKEND),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(f"launched gateway pid {proc.pid} with flags: {' '.join(flags)}")
    return proc.pid


def wait_healthy(timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False


def main() -> int:
    kill_gateway()
    if not wait_port_free():
        print("ERROR: port 8001 still in use")
        return 1

    launch(RELOAD_FLAGS)
    if not wait_healthy():
        print("reload-config launch failed, falling back to original flags")
        kill_gateway()
        wait_port_free()
        launch(FALLBACK_FLAGS)
        if not wait_healthy():
            print("ERROR: gateway did not come back up")
            return 1

    print("gateway healthy")
    with urllib.request.urlopen("http://127.0.0.1:8001/openapi.json", timeout=5) as resp:
        spec = json.load(resp)
    for path, methods in sorted(spec["paths"].items()):
        if "skills" in path:
            for method in methods:
                print(method.upper(), path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
