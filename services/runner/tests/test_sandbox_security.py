"""Spec §10.2 mandatory sandbox security tests — executed against real Docker."""

import subprocess
import threading
import time

import pytest
from mlforge_runner import grade

pytestmark = pytest.mark.docker

SCRIPT = [{"id": "run", "kind": "script", "visibility": "public", "stdin": ""}]


def run(sandbox, code, job="sec", tests=SCRIPT):
    return sandbox.run(f"{job}-{time.monotonic_ns()}", code, tests)


def obs(outcome):
    assert outcome.status == "completed", outcome
    return outcome.observations[0]


def test_infinite_loop_is_stopped_by_timeout(sandbox):
    started = time.monotonic()
    o = obs(run(sandbox, "while True:\n    pass\n"))
    assert o["status"] == "timeout"
    assert time.monotonic() - started < sandbox.limits.total_budget_s + 10


def test_network_is_unreachable(sandbox):
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
        "    print('CONNECTED')\n"
        "except OSError as e:\n"
        "    print('blocked', type(e).__name__)\n"
        "try:\n"
        "    socket.getaddrinfo('example.com', 80)\n"
        "    print('DNS-OK')\n"
        "except OSError:\n"
        "    print('dns blocked')\n"
    )
    out = obs(run(sandbox, code))["stdout"]
    assert "CONNECTED" not in out and "DNS-OK" not in out
    assert "blocked" in out


def test_host_filesystem_and_secrets_not_visible(sandbox, monkeypatch):
    monkeypatch.setenv("MLFORGE_TEST_SECRET", "super-secret-value")
    code = (
        "import os, getpass\n"
        "print('uid', os.getuid())\n"
        "print('secret' if any('super-secret' in v for v in os.environ.values()) else 'no-secret')\n"
        "print(open('/etc/passwd').read().count('\\n'))\n"
        "print('home', os.path.exists('/root/.ssh'), os.path.exists('/home/user'))\n"
        "print('docker_sock', os.path.exists('/var/run/docker.sock'))\n"
        "try:\n"
        "    open('/opt/escape.txt', 'w').write('x')\n"
        "    print('rootfs-writable')\n"
        "except OSError:\n"
        "    print('rootfs-readonly')\n"
    )
    out = obs(run(sandbox, code))["stdout"]
    assert "uid 10001" in out  # non-root
    assert "no-secret" in out
    assert "home False False" in out
    assert "docker_sock False" in out
    assert "rootfs-readonly" in out
    # /etc/passwd is the image's own minimal file, not the host's
    host_lines = open("/etc/passwd").read().count("\n")
    image_lines = int(out.splitlines()[2])
    assert image_lines < 40 and (image_lines != host_lines or host_lines < 40)


def test_fork_bomb_is_limited(sandbox):
    code = (
        "import os\n"
        "n = 0\n"
        "try:\n"
        "    for _ in range(500):\n"
        "        if os.fork() == 0:\n"
        "            import time; time.sleep(3); os._exit(0)\n"
        "        n += 1\n"
        "except OSError:\n"
        "    pass\n"
        "print('forked', n)\n"
    )
    o = obs(run(sandbox, code))
    forked = int(o["stdout"].split()[-1]) if o.get("stdout") else 0
    assert forked < sandbox.limits.pids


def test_huge_stdout_is_truncated(sandbox):
    o = obs(run(sandbox, "while True:\n    print('x' * 10000)\n"))
    assert o["status"] in ("output_limit", "timeout")
    assert len(o.get("stdout", "")) <= sandbox.limits.max_output_bytes


def test_large_memory_allocation_fails_safely(sandbox):
    o = obs(run(sandbox, "data = bytearray(1024 * 1024 * 1024)\nprint('allocated')\n"))
    assert "allocated" not in o.get("stdout", "")
    assert o["status"] in ("exception", "killed")
    if o["status"] == "exception":
        assert o["exc"]["type"] == "MemoryError"


def _sandbox_containers():
    res = subprocess.run(["docker", "ps", "-aq", "--filter", "label=mlforge.sandbox=1"], capture_output=True, text=True)
    return [x for x in res.stdout.split() if x]


def test_cancel_kills_container_and_leaves_no_orphans(sandbox):
    before = set(_sandbox_containers())
    job_id = f"cancel-{time.monotonic_ns()}"
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("o", sandbox.run(job_id, "while True: pass\n", SCRIPT)))
    t.start()
    time.sleep(1.5)
    assert sandbox.cancel(job_id)
    t.join(timeout=20)
    assert result["o"].status == "cancelled"
    assert set(_sandbox_containers()) - before == set()


def test_neighbouring_runs_are_isolated(sandbox):
    writer = "open('/tmp/shared.txt','w').write('from-a')\nimport time; time.sleep(1.5)\nprint('a-done')\n"
    reader = "import os, time\ntime.sleep(0.5)\nprint('seen' if os.path.exists('/tmp/shared.txt') else 'isolated')\n"
    out = {}
    ta = threading.Thread(target=lambda: out.setdefault("a", run(sandbox, writer, "iso-a")))
    tb = threading.Thread(target=lambda: out.setdefault("b", run(sandbox, reader, "iso-b")))
    ta.start(), tb.start()
    ta.join(30), tb.join(30)
    assert "isolated" in obs(out["b"])["stdout"]


def test_each_test_runs_in_fresh_process(sandbox):
    code = "counter = []\ndef f():\n    counter.append(1)\n    return len(counter)\n"
    tests = [{"id": f"t{i}", "kind": "call", "call": "f()", "expected": "1", "visibility": "public"} for i in range(3)]
    outcome = sandbox.run(f"fresh-{time.monotonic_ns()}", code, tests)
    results, summary = grade(tests, outcome.observations)
    assert summary.passed == 3


def test_expected_values_never_enter_container(sandbox):
    """Hidden expected outputs stay on the host: the payload carries inputs only."""
    tests = [
        {
            "id": "t",
            "kind": "call",
            "call": "f()",
            "expected": "'TOP-SECRET-EXPECTED'",
            "raises": None,
            "expected_stdout": "TOP-SECRET-STDOUT",
            "visibility": "hidden",
        }
    ]
    payload = sandbox.job_payload("n", "def f():\n    return 1\n", tests).decode()
    assert "TOP-SECRET" not in payload
    assert all("TOP-SECRET" not in a for a in sandbox.docker_args("x", "y"))
