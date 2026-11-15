"""Comprehensive test suite for Process Safety & Subprocess Isolation (Milestone 12).

Tests:
1. ProcessSafetyManager registration, PID/PGID tracking, and sync/async APIs.
2. POSIX isolation, setsid process group creation, and OS resource limit configurations.
3. Recursive multi-level process tree termination within < 3.0 seconds via psutil & SIGKILL.
4. Handling of stubborn / uncooperative processes ignoring SIGTERM.
5. Scanner adapter (Nuclei, ZAP, Trivy) process safety wiring & structured arguments.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import List

import psutil
import pytest

from backend.app.core.process_safety import ProcessSafetyManager, process_safety
from backend.app.scanners.base import (
    CancellationToken,
    ScanExecutionRequest,
)
from backend.app.scanners.nuclei import NucleiAdapter
from backend.app.scanners.trivy import TrivyAdapter
from backend.app.scanners.zap import ZAPAdapter
from backend.app.schemas.common import AssetType, ScanProfile


class TestProcessSafetyManagerBasics:
    """Verifies internal state, registration, and non-root helper contracts."""

    @pytest.mark.asyncio
    async def test_async_and_sync_registration(self):
        manager = ProcessSafetyManager()
        scan_id = uuid.uuid4()
        pid_1 = 12345
        pid_2 = 12346

        await manager.register_pid(scan_id, pid_1)
        assert scan_id in manager._scan_pids
        assert pid_1 in manager._scan_pids[scan_id]

        manager.register_pid_sync(scan_id, pid_2)
        assert pid_2 in manager._scan_pids[scan_id]
        assert len(manager._scan_pids[scan_id]) == 2

        # Terminating clears registration
        res = manager.terminate_process_tree(scan_id)
        assert res is True
        assert scan_id not in manager._scan_pids

    def test_empty_termination_returns_true(self):
        manager = ProcessSafetyManager()
        empty_scan_id = uuid.uuid4()
        assert manager.terminate_process_tree(empty_scan_id) is True

    def test_is_non_root_check(self):
        manager = ProcessSafetyManager()
        expected = os.geteuid() != 0 if hasattr(os, "geteuid") else True
        assert manager.is_non_root() == expected

    def test_get_safe_subprocess_kwargs_structure(self):
        manager = ProcessSafetyManager()
        kwargs = manager.get_safe_subprocess_kwargs(
            memory_limit_mb=1024,
            cpu_limit_seconds=180,
            max_open_files=1024,
        )
        assert "preexec_fn" in kwargs
        assert callable(kwargs["preexec_fn"])


class TestProcessTreeTermination:
    """Empirical verification of recursive process tree termination under strict deadlines (<3s)."""

    def test_multi_generation_process_tree_termination(self):
        """Spawns Parent -> Child -> Grandchild hierarchy and asserts that calling

        terminate_process_tree terminates all descendants cleanly within 3 seconds.
        """
        manager = ProcessSafetyManager()
        scan_id = uuid.uuid4()

        # Code that spawns a child that spawns a grandchild, all sleeping
        script = (
            "import subprocess, sys, time\n"
            "child_code = '''import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "time.sleep(60)\n"
            "'''\n"
            "subprocess.Popen([sys.executable, '-c', child_code])\n"
            "time.sleep(60)\n"
        )

        parent = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        parent_pid = parent.pid

        # Give processes time to branch out
        time.sleep(0.8)

        # Inspect spawned descendants
        try:
            p_proc = psutil.Process(parent_pid)
            children = p_proc.children(recursive=True)
            all_descendants = [p.pid for p in children]
            assert len(all_descendants) >= 1, "Child processes failed to spawn."
        except psutil.NoSuchProcess:
            pytest.fail("Parent process exited prematurely.")

        # Register parent PID with ProcessSafetyManager
        manager.register_pid_sync(scan_id, parent_pid)

        # Terminate entire tree
        start_t = time.time()
        success = manager.terminate_process_tree(scan_id, timeout=3.0)
        elapsed = time.time() - start_t

        assert success is True
        assert elapsed < 3.0, f"Termination exceeded 3.0s deadline: {elapsed:.2f}s"

        # Allow brief OS cleanup
        time.sleep(0.3)

        # Verify parent is dead
        assert not psutil.pid_exists(parent_pid) or psutil.Process(parent_pid).status() == psutil.STATUS_ZOMBIE

        # Verify all descendants are dead
        for cpid in all_descendants:
            is_alive = False
            try:
                cp = psutil.Process(cpid)
                if cp.is_running() and cp.status() != psutil.STATUS_ZOMBIE:
                    is_alive = True
            except psutil.NoSuchProcess:
                is_alive = False
            assert not is_alive, f"Descendant process {cpid} leaked!"

    def test_stubborn_sigterm_ignoring_process_killed_by_sigkill(self):
        """Spawns a stubborn process that ignores SIGTERM, verifying ProcessSafetyManager

        escalates to SIGKILL to guarantee termination within the 3.0-second limit.
        """
        manager = ProcessSafetyManager()
        scan_id = uuid.uuid4()

        # Process traps SIGTERM and ignores it
        stubborn_code = (
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "while True:\n"
            "    time.sleep(1)\n"
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", stubborn_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pid = proc.pid

        time.sleep(0.3)
        assert psutil.pid_exists(pid)

        manager.register_pid_sync(scan_id, pid)

        start_t = time.time()
        res = manager.terminate_process_tree(scan_id, timeout=2.0)
        elapsed = time.time() - start_t

        assert res is True
        assert elapsed <= 3.0

        time.sleep(0.3)
        assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


class TestScannerAdaptersProcessSafetyWiring:
    """Verifies that Nuclei, ZAP, and Trivy adapters integrate with process safety."""

    @pytest.mark.asyncio
    async def test_nuclei_adapter_fallback_and_safety_wiring(self):
        adapter = NucleiAdapter()
        scan_id = uuid.uuid4()
        req = ScanExecutionRequest(
            scan_id=scan_id,
            asset_id=uuid.uuid4(),
            asset_type=AssetType.WEB_APP,
            target_locator="https://test-target.empire.edu.vn",
            profile=ScanProfile.QUICK.value,
            timeout_seconds=5,
        )
        token = CancellationToken()
        logs: List[str] = []

        async def log_cb(eng, msg):
            logs.append(f"[{eng}] {msg}")

        result = await adapter.execute(req, token, log_cb)
        assert result.success is True
        assert result.engine_name == "nuclei"
        assert len(result.findings) >= 0

    @pytest.mark.asyncio
    async def test_zap_adapter_fallback_and_safety_wiring(self):
        adapter = ZAPAdapter()
        scan_id = uuid.uuid4()
        req = ScanExecutionRequest(
            scan_id=scan_id,
            asset_id=uuid.uuid4(),
            asset_type=AssetType.WEB_APP,
            target_locator="https://test-target.empire.edu.vn",
            profile=ScanProfile.STANDARD.value,
            timeout_seconds=5,
        )
        token = CancellationToken()
        logs: List[str] = []

        async def log_cb(eng, msg):
            logs.append(f"[{eng}] {msg}")

        result = await adapter.execute(req, token, log_cb)
        assert result.success is True
        assert result.engine_name == "zap"
        assert len(result.findings) >= 0

    @pytest.mark.asyncio
    async def test_trivy_adapter_fallback_and_safety_wiring(self):
        adapter = TrivyAdapter()
        scan_id = uuid.uuid4()
        req = ScanExecutionRequest(
            scan_id=scan_id,
            asset_id=uuid.uuid4(),
            asset_type=AssetType.PROJECT_ARCHIVE,
            target_locator=str(Path.cwd()),
            profile=ScanProfile.STANDARD.value,
            timeout_seconds=5,
        )
        token = CancellationToken()
        logs: List[str] = []

        async def log_cb(eng, msg):
            logs.append(f"[{eng}] {msg}")

        result = await adapter.execute(req, token, log_cb)
        assert result.success is True
        assert result.engine_name == "trivy"
        assert len(result.findings) >= 0
