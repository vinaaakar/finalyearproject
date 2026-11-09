"""Safety tests for the service scripts (scripts/_common.sh, restart_api.sh, start.sh, test.sh, setup.sh).

Nothing here touches a real service:
- `docker` is replaced by a logging mock placed first on PATH;
- the "API" and "storefronts" are tiny local HTTP servers on random free ports;
- restart_api.sh runs with its own temporary run directory (never the project's .run/).
The only test that talks to the real Docker daemon is read-only (`docker inspect`) and is skipped if Docker
or the container is unavailable.

Run: backend/.venv/bin/python -m pytest -q scripts/tests
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
PY = sys.executable

MUTATING_DOCKER = re.compile(r"^(compose|start|stop|restart|rm|run|create|kill|up|down|volume|container|update|pause)\b")

DOCKER_MOCK = r"""#!/bin/bash
# Mock docker: logs every call; emulates `info`, `inspect`, `start`, `compose up` for ensure_postgres.
echo "$*" >> "$MOCK_DOCKER_LOG"
state_file="$MOCK_PG_STATE_FILE"
case "$1" in
  info) [ "${MOCK_DOCKER_DOWN:-}" = 1 ] && exit 1; exit 0 ;;
  inspect)
    st=$(cat "$state_file")
    [ "$st" = missing ] && { echo "Error: No such object" >&2; exit 1; }
    if [ "$st" = running:starting ]; then
      n=$(( $(cat "$state_file.n" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$state_file.n"
      [ "$n" -ge 3 ] && { echo running:healthy > "$state_file"; st=running:healthy; }
    fi
    echo "$st" ;;
  start|compose) echo running:healthy > "$state_file" ;;
esac
exit 0
"""

FAKE_API = r"""
import json, signal, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
port, mode = int(sys.argv[1]), sys.argv[2]
if mode == "crash":
    print("simulated startup failure", flush=True)
    sys.exit(1)
if mode == "ignore_term":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "degraded" if mode == "degraded" else "ok", "mode": mode}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


# ---- helpers -------------------------------------------------------------------------------------
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_listening(port: int, timeout: float = 10) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if listening(port):
            return
        time.sleep(0.1)
    raise AssertionError(f"nothing listening on {port}")


def alive(pid: int) -> bool:
    """Running and not a zombie (processes spawned by this test stay as zombies until reaped)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def listener_pid(port: int) -> int | None:
    out = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


@pytest.fixture
def env(tmp_path):
    """Isolated environment: mock docker first on PATH, temp state files."""
    mockbin = tmp_path / "bin"
    mockbin.mkdir()
    docker = mockbin / "docker"
    docker.write_text(DOCKER_MOCK)
    docker.chmod(0o755)
    e = {k: v for k, v in os.environ.items() if not k.startswith("AVC_")}
    e.update({
        "PATH": f"{mockbin}:{os.environ['PATH']}",
        "MOCK_DOCKER_LOG": str(tmp_path / "docker_calls.log"),
        "MOCK_PG_STATE_FILE": str(tmp_path / "pg_state"),
        "AVC_PG_WAIT_SECONDS": "6",
    })
    (tmp_path / "docker_calls.log").write_text("")
    return e


def docker_calls(env) -> list[str]:
    return [ln for ln in Path(env["MOCK_DOCKER_LOG"]).read_text().splitlines() if ln.strip()]


def run_ensure(env, state: str, **extra) -> subprocess.CompletedProcess:
    Path(env["MOCK_PG_STATE_FILE"]).write_text(state)
    return subprocess.run(["bash", "-c", f'source "{SCRIPTS}/_common.sh"; ensure_postgres'],
                          env={**env, **extra}, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)


# ---- ensure_postgres (used by start.sh, test.sh, setup.sh) -------------------------------------------
def test_healthy_postgres_is_left_untouched(env):
    r = run_ensure(env, "running:healthy")
    assert r.returncode == 0, r.stderr
    assert "left untouched" in r.stdout
    calls = docker_calls(env)
    assert calls and all(c.startswith(("info", "inspect")) for c in calls), calls
    assert not any(MUTATING_DOCKER.match(c) for c in calls)


def test_healthy_postgres_untouched_even_with_approval(env):
    r = run_ensure(env, "running:healthy", AVC_APPROVE_DB_START="1")
    assert r.returncode == 0
    assert not any(MUTATING_DOCKER.match(c) for c in docker_calls(env))


def test_starting_postgres_is_awaited_read_only(env):
    r = run_ensure(env, "running:starting")
    assert r.returncode == 0, r.stderr
    assert not any(MUTATING_DOCKER.match(c) for c in docker_calls(env))


@pytest.mark.parametrize("state", ["running:unhealthy", "running:none", "paused:none", "restarting:none", "dead:none"])
def test_unhealthy_or_odd_state_is_reported_not_touched(env, state):
    r = run_ensure(env, state, AVC_APPROVE_DB_START="1")
    assert r.returncode == 1
    assert "Not touching it" in r.stderr
    assert not any(MUTATING_DOCKER.match(c) for c in docker_calls(env))


def test_docker_down_is_reported(env):
    r = run_ensure(env, "running:healthy", MOCK_DOCKER_DOWN="1")
    assert r.returncode == 1 and "Docker is not running" in r.stderr
    assert not any(MUTATING_DOCKER.match(c) for c in docker_calls(env))


@pytest.mark.parametrize("state", ["exited:none", "missing"])
def test_stopped_or_missing_requires_approval(env, state):
    r = run_ensure(env, state)  # non-interactive, no approval
    assert r.returncode == 1
    assert "Approval needed" in r.stderr
    assert not any(MUTATING_DOCKER.match(c) for c in docker_calls(env))


def test_stopped_container_started_in_place_with_approval(env):
    r = run_ensure(env, "exited:none", AVC_APPROVE_DB_START="1")
    assert r.returncode == 0, r.stderr
    mutating = [c for c in docker_calls(env) if MUTATING_DOCKER.match(c)]
    assert mutating == ["start avc_postgres"]  # the same container; never compose, never recreate


def test_missing_container_created_without_recreate(env):
    r = run_ensure(env, "missing", AVC_APPROVE_DB_START="1")
    assert r.returncode == 0, r.stderr
    mutating = [c for c in docker_calls(env) if MUTATING_DOCKER.match(c)]
    assert mutating == ["compose up -d --no-recreate postgres"]


# ---- static guarantees across all scripts ----------------------------------------------------------
def _code_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def test_restart_api_script_never_uses_docker():
    assert not [ln for ln in _code_lines(SCRIPTS / "restart_api.sh") if "docker" in ln]


def test_no_script_can_recreate_postgres():
    for sh in SCRIPTS.glob("*.sh"):
        for ln in _code_lines(sh):
            if re.search(r"compose\b.*\bup\b", ln):
                assert sh.name == "_common.sh" and "--no-recreate" in ln, f"{sh.name}: {ln.strip()}"
            assert "--force-recreate" not in ln and "compose restart" not in ln, f"{sh.name}: {ln.strip()}"


@pytest.mark.parametrize("name", ["start.sh", "test.sh", "setup.sh"])
def test_startup_scripts_go_through_the_guard(name):
    code = _code_lines(SCRIPTS / name)
    assert any("ensure_postgres" in ln for ln in code)
    assert not [ln for ln in code if "docker " in ln], "must use ensure_postgres instead of calling docker directly"


# ---- restart_api.sh (isolated: fake API + fake storefronts on random ports) ----------------------------
class Stack:
    def __init__(self, tmp_path: Path, env: dict):
        self.tmp, self.env = tmp_path, env
        self.fake_api = tmp_path / "fake_api.py"
        self.fake_api.write_text(FAKE_API)
        self.run_dir = tmp_path / "run"
        self.run_dir.mkdir()
        self.api_port = free_port()
        self.store_ports = [free_port(), free_port()]
        self.procs: list[subprocess.Popen] = []
        self.stores = [self._spawn([PY, "-m", "http.server", str(p), "--bind", "127.0.0.1"], p) for p in self.store_ports]

    def _spawn(self, cmd, port) -> int:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, cwd=self.tmp)
        self.procs.append(p)
        wait_listening(port)
        return p.pid

    def start_old_api(self, mode="ok") -> int:
        pid = self._spawn([PY, str(self.fake_api), str(self.api_port), mode], self.api_port)
        (self.run_dir / "api.pid").write_text(str(pid))
        (self.run_dir / "api.log").write_text("old log line\n")
        return pid

    def restart(self, new_mode="ok", **extra) -> subprocess.CompletedProcess:
        e = {**self.env,
             "AVC_API_PORT": str(self.api_port), "AVC_STORE_PORTS": " ".join(map(str, self.store_ports)),
             "AVC_RUN_DIR": str(self.run_dir), "AVC_API_CMD": f"{PY} {self.fake_api} {self.api_port} {new_mode}",
             "AVC_API_DIR": str(self.tmp), "AVC_API_MATCH": str(self.fake_api), "AVC_PREFLIGHT_CMD": "true",
             "AVC_STOP_TIMEOUT": "3", "AVC_HEALTH_TIMEOUT": "10", **extra}
        return subprocess.run(["bash", str(SCRIPTS / "restart_api.sh")], env=e, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=60)

    def new_pid(self) -> int | None:
        f = self.run_dir / "api.pid"
        return int(f.read_text()) if f.exists() else None

    def cleanup(self):
        pids = [p.pid for p in self.procs] + ([self.new_pid()] if self.new_pid() else [])
        for pid in pids:
            for sig in (signal.SIGKILL,):
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass


@pytest.fixture
def stack(tmp_path, env):
    s = Stack(tmp_path, env)
    yield s
    s.cleanup()


def _stores_unchanged(stack: Stack):
    for pid, port in zip(stack.stores, stack.store_ports):
        assert alive(pid), "storefront process was terminated"
        assert listener_pid(port) == pid, "storefront PID changed"


def test_restart_replaces_only_the_api(stack):
    old = stack.start_old_api()
    r = stack.restart()
    assert r.returncode == 0, r.stdout + r.stderr
    new = stack.new_pid()
    assert new and new != old
    assert not alive(old), "old API still running"
    assert listener_pid(stack.api_port) == new, "port not served by the new PID"
    health = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{stack.api_port}/api/health", timeout=3).read())
    assert health["status"] == "ok"
    assert f"{old} -> {new}" in r.stdout
    _stores_unchanged(stack)
    assert docker_calls(stack.env) == [], "restart_api.sh must never invoke docker"
    backups = list(stack.run_dir.glob("api.log.*"))
    assert len(backups) == 1 and backups[0].read_text() == "old log line\n", "old log not preserved"


def test_restart_when_api_not_running_just_starts_it(stack):
    r = stack.restart()
    assert r.returncode == 0, r.stdout + r.stderr
    assert listener_pid(stack.api_port) == stack.new_pid()
    _stores_unchanged(stack)
    assert docker_calls(stack.env) == []


def test_failed_restart_leaves_other_services_running(stack):
    stack.start_old_api()
    r = stack.restart(new_mode="crash")
    assert r.returncode == 1
    assert "exited during startup" in r.stderr and "simulated startup failure" in r.stderr
    assert "were not touched" in r.stderr
    _stores_unchanged(stack)
    assert docker_calls(stack.env) == []


def test_preflight_failure_keeps_old_api_running(stack):
    old = stack.start_old_api()
    r = stack.restart(AVC_PREFLIGHT_CMD="false")
    assert r.returncode == 1 and "NOT stopped" in r.stderr
    assert alive(old) and listener_pid(stack.api_port) == old
    _stores_unchanged(stack)
    assert docker_calls(stack.env) == []


def test_old_api_that_will_not_exit_is_not_doubled(stack):
    old = stack.start_old_api(mode="ignore_term")
    r = stack.restart()
    assert r.returncode == 1 and "did not exit" in r.stderr
    assert alive(old) and listener_pid(stack.api_port) == old  # still serving; no second copy, no SIGKILL
    assert int((stack.run_dir / "api.pid").read_text()) == old
    _stores_unchanged(stack)
    assert docker_calls(stack.env) == []


def test_foreign_process_on_api_port_is_never_killed(stack):
    foreign = stack._spawn([PY, "-m", "http.server", str(stack.api_port), "--bind", "127.0.0.1"], stack.api_port)
    r = stack.restart()
    assert r.returncode == 1 and "not this project's API" in r.stderr
    assert alive(foreign) and listener_pid(stack.api_port) == foreign
    _stores_unchanged(stack)
    assert docker_calls(stack.env) == []


def test_degraded_health_is_reported(stack):
    stack.start_old_api()
    r = stack.restart(new_mode="degraded")
    assert r.returncode == 3 and "non-ok status" in r.stderr
    _stores_unchanged(stack)


# ---- live, read-only ------------------------------------------------------------------------------
def test_live_postgres_volume_attached_read_only():
    """Read-only check of the real container: its data directory is the named project volume."""
    if not shutil.which("docker"):
        pytest.skip("docker not installed")
    r = subprocess.run(["docker", "inspect", "-f", "{{json .Mounts}}", "avc_postgres"], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        pytest.skip("avc_postgres not available")
    mounts = json.loads(r.stdout)
    data = [m for m in mounts if m["Destination"] == "/var/lib/postgresql/data"]
    assert data and data[0]["Type"] == "volume" and data[0]["Name"] == "ai-voice-commerce_avc_pgdata"
