"""Restart the Next.js dev server the way serve.sh starts it, then wait for it to serve."""

import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(r"E:\DeerFlow")
FRONTEND = REPO / "frontend"
LOG = REPO / "logs" / "frontend.log"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def port_open(port: int) -> bool:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def node_pids() -> list[int]:
    raw = subprocess.run(
        ["wmic", "process", "where", "name='node.exe'", "get", "ProcessId,CommandLine"],
        capture_output=True,
    ).stdout
    text = raw.decode("gbk", errors="replace")
    pids = []
    for line in text.splitlines():
        if re.search(r"next", line, re.I) and re.search(r"dev|next-server", line, re.I):
            match = re.search(r"(\d+)\s*$", line.strip())
            if match:
                pids.append(int(match.group(1)))
    return pids


pnpm = subprocess.run(["where", "pnpm"], capture_output=True).stdout.decode("gbk", errors="replace").splitlines()
pnpm_path = pnpm[0].strip() if pnpm else "pnpm"
# On Windows the npm shim has no extension in `where` output; Popen needs the .cmd.
for candidate in (pnpm_path + ".cmd", pnpm_path):
    if pathlib.Path(candidate).exists():
        pnpm_path = candidate
        break
print("pnpm:", pnpm_path)

for pid in node_pids():
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    print("killed next dev pid", pid)

deadline = time.time() + 25
while time.time() < deadline and port_open(3000):
    time.sleep(0.5)
print("port 3000 free:", not port_open(3000))

env = os.environ.copy()
env["NODE_ENV"] = "development"
log = open(LOG, "ab", buffering=0)
proc = subprocess.Popen(
    [pnpm_path, "run", "dev"],
    cwd=str(FRONTEND),
    env=env,
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
print("launched next dev pid", proc.pid)

ready = False
deadline = time.time() + 180
while time.time() < deadline:
    time.sleep(3)
    try:
        with urllib.request.urlopen("http://127.0.0.1:3000/workspace/chats/new", timeout=10) as resp:
            print("route /workspace/chats/new ->", resp.status, f"({len(resp.read())} bytes)")
            ready = True
            break
    except urllib.error.HTTPError as exc:
        print("route /workspace/chats/new ->", exc.code)
        ready = exc.code < 500
        if ready:
            break
    except Exception:
        continue

print("frontend ready:", ready)
sys.exit(0 if ready else 1)
