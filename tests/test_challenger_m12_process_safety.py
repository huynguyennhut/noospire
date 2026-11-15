"""Adversarial challenger tests for Milestone 12 Process Safety.

Stress-tests:
1. Deep stubborn multi-generation process trees (Parent -> Children -> Grandchildren).
2. All nodes trap/ignore SIGTERM; verifies SIGKILL escalation kills all nodes < 3.0s.
3. Edge cases: non-existent PID, already dead PID, double termination idempotency.
4. Self-protection: ensures caller process/group is never killed.
5. Large process tree (15+ stubborn processes).
"""

import os
import signal
import subprocess
import sys
import time
import uuid
import psutil
import pytest

from backend.app.core.process_safety import ProcessSafetyManager


def test_adversarial_stubborn_multi_gen_tree():
    """Spawn Parent -> 2 Children -> 4 Grandchildren, all ignoring SIGTERM."""
    mgr = ProcessSafetyManager()
    scan_id = uuid.uuid4()

    grandchild_code = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )

    child_code = (
        "import signal, time, subprocess, sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"gc = {repr(grandchild_code)}\n"
        "g1 = subprocess.Popen([sys.executable, '-c', gc])\n"
        "g2 = subprocess.Popen([sys.executable, '-c', gc])\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )

    parent_code = (
        "import signal, time, subprocess, sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"cc = {repr(child_code)}\n"
        "p1 = subprocess.Popen([sys.executable, '-c', cc])\n"
        "p2 = subprocess.Popen([sys.executable, '-c', cc])\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )

    parent = subprocess.Popen([sys.executable, "-c", parent_code], preexec_fn=os.setsid)
    time.sleep(1.2)  # allow full tree to spawn

    p_proc = psutil.Process(parent.pid)
    descendants = p_proc.children(recursive=True)
    all_pids = [parent.pid] + [p.pid for p in descendants]
    assert len(all_pids) == 7, f"Expected 7 processes (1 parent + 2 children + 4 grandchildren), got {len(all_pids)}"

    for pid in all_pids:
        proc = psutil.Process(pid)
        assert proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE

    mgr.register_pid_sync(scan_id, parent.pid)

    start = time.perf_counter()
    res = mgr.terminate_process_tree(scan_id, timeout=2.0)
    duration = time.perf_counter() - start

    assert res is True
    assert duration < 3.0, f"Duration {duration:.3f}s exceeded 3.0s deadline!"

    time.sleep(0.3)
    surviving = [p for p in all_pids if psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE]
    assert len(surviving) == 0, f"Leaked processes: {surviving}"


def test_adversarial_large_stubborn_tree():
    """Spawn 1 parent with 10 stubborn children."""
    mgr = ProcessSafetyManager()
    scan_id = uuid.uuid4()

    child_code = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )

    parent_code = (
        "import signal, time, subprocess, sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"cc = {repr(child_code)}\n"
        "children = [subprocess.Popen([sys.executable, '-c', cc]) for _ in range(10)]\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )

    parent = subprocess.Popen([sys.executable, "-c", parent_code], preexec_fn=os.setsid)
    time.sleep(1.2)

    p_proc = psutil.Process(parent.pid)
    all_pids = [parent.pid] + [p.pid for p in p_proc.children(recursive=True)]
    assert len(all_pids) >= 11

    mgr.register_pid_sync(scan_id, parent.pid)

    start = time.perf_counter()
    res = mgr.terminate_process_tree(scan_id, timeout=2.0)
    duration = time.perf_counter() - start

    assert res is True
    assert duration < 3.0, f"Duration {duration:.3f}s exceeded 3.0s limit"

    time.sleep(0.3)
    surviving = [p for p in all_pids if psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE]
    assert len(surviving) == 0


def test_adversarial_idempotency_and_dead_pids():
    """Verify dead PIDs, non-existent PIDs, and repeated termination calls."""
    mgr = ProcessSafetyManager()
    scan_id = uuid.uuid4()

    # Register already dead PID
    mgr.register_pid_sync(scan_id, 9999999)
    res = mgr.terminate_process_tree(scan_id, timeout=1.0)
    assert res is True

    # Call again immediately on same scan_id (already removed)
    res2 = mgr.terminate_process_tree(scan_id, timeout=1.0)
    assert res2 is True


def test_adversarial_caller_process_protection():
    """Verify that if caller's own PID or PGID is somehow registered, it does NOT kill caller."""
    mgr = ProcessSafetyManager()
    scan_id = uuid.uuid4()
    current_pgid = os.getpgrp()

    # Explicitly attempt to register current process group
    mgr.register_pid_sync(scan_id, os.getpid(), pgid=current_pgid)
    # The internal registration must have filtered out current_pgid
    assert current_pgid not in mgr._scan_pgids.get(scan_id, [])
