"""Restart the DeerFlow langgraph dev server (native process) the same way serve.sh does."""

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
LOG = REPO / "logs" / "langgraph.log"
UV = r"C:\Users\Dance\.local\bin\uv.exe"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
PORT = 2024


def port_open() -> bool:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        sock.close()


def langgraph_pids() -> list[int]:
    raw = subprocess.run(
        ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
        capture_output=True,
    ).stdout
    text = raw.decode("gbk", errors="replace")
    pids = []
    for line in text.splitlines():
        if "langgraph" in line and "--no-browser" in line:
            match = re.search(r"(\d+)\s*$", line.strip())
            if match:
                pids.append(int(match.group(1)))
    return pids


for pid in langgraph_pids():
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    print("killed langgraph pid", pid)

deadline = time.time() + 25
while time.time() < deadline and port_open():
    time.sleep(0.5)
print("port 2024 free:", not port_open())

env = os.environ.copy()
env["NO_COLOR"] = "1"
log = open(LOG, "ab", buffering=0)
proc = subprocess.Popen(
    # --no-reload: the dev reloader kept firing on data files (thread data,
    # sqlite checkpoints) written during runs, which churned/crashed the server.
    [UV, "run", "langgraph", "dev", "--no-browser", "--allow-blocking", "--no-reload"],
    cwd=str(BACKEND),
    env=env,
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
print("launched langgraph pid", proc.pid)

healthy = False
deadline = time.time() + 90
while time.time() < deadline:
    time.sleep(2)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ok", timeout=3) as resp:
            if resp.status == 200:
                healthy = True
                break
    except Exception:
        continue
print("langgraph healthy:", healthy)
sys.exit(0 if healthy else 1)
