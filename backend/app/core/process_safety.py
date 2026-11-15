"""Noosforge Sentinel Process Safety & Isolation Manager.

Enforces POSIX process isolation, safe execution environments, non-root execution checks,
operating system resource bounds (RLIMIT_AS, RLIMIT_CPU, RLIMIT_NOFILE), and
deterministic < 3.0-second recursive process-tree termination.
"""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import signal
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger("noospire.process_safety")


class ProcessSafetyManager:
    """Tracks PID and PGID trees spawned during security scan jobs and guarantees
    deterministic process-tree termination with strict OS resource bounds.
    """

    def __init__(self) -> None:
        self._scan_pids: Dict[uuid.UUID, List[int]] = {}
        self._scan_pgids: Dict[uuid.UUID, List[int]] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._lock is None:
            self._lock = asyncio.Lock()
        elif current_loop and getattr(self._lock, "_loop", None) is not None and self._lock._loop != current_loop:
            self._lock = asyncio.Lock()
        return self._lock

    async def register_pid(
        self,
        scan_id: uuid.UUID,
        pid: int,
        pgid: Optional[int] = None,
    ) -> None:
        """Asynchronously registers a spawned process ID and its associated process group."""
        async with self._get_lock():
            self._register_pid_internal(scan_id, pid, pgid)

    def register_pid_sync(
        self,
        scan_id: uuid.UUID,
        pid: int,
        pgid: Optional[int] = None,
    ) -> None:
        """Synchronously registers a spawned process ID and its associated process group."""
        self._register_pid_internal(scan_id, pid, pgid)

    def _register_pid_internal(
        self,
        scan_id: uuid.UUID,
        pid: int,
        pgid: Optional[int] = None,
    ) -> None:
        pids = self._scan_pids.setdefault(scan_id, [])
        if pid not in pids:
            pids.append(pid)

        current_pgid = os.getpgrp() if hasattr(os, "getpgrp") else None
        detected_pgid = pgid
        if detected_pgid is None and hasattr(os, "getpgid"):
            try:
                cand = os.getpgid(pid)
                if cand != current_pgid:
                    detected_pgid = cand
            except (OSError, ProcessLookupError):
                pass

        if detected_pgid is not None and detected_pgid != current_pgid:
            pgids = self._scan_pgids.setdefault(scan_id, [])
            if detected_pgid not in pgids:
                pgids.append(detected_pgid)

    def is_non_root(self) -> bool:
        """Verifies if the current process is running under an unprivileged (non-root) user."""
        if hasattr(os, "geteuid"):
            return os.geteuid() != 0
        return True

    def get_safe_subprocess_kwargs(
        self,
        memory_limit_mb: int = 2048,
        cpu_limit_seconds: int = 300,
        max_open_files: int = 2048,
        drop_privileges_if_root: bool = True,
    ) -> Dict[str, Any]:
        """Produces POSIX-isolated execution kwargs for asyncio.create_subprocess_exec / subprocess.Popen.

        Enforces:
        1. Process group isolation via os.setsid (POSIX)
        2. Virtual memory bounds via RLIMIT_AS
        3. CPU execution time caps via RLIMIT_CPU
        4. Open file descriptor constraints via RLIMIT_NOFILE
        5. Non-root user privilege de-escalation if currently running as root.
        """
        def preexec_fn() -> None:
            # 1. Create independent process group / session leader
            if hasattr(os, "setsid"):
                try:
                    os.setsid()
                except OSError as e:
                    logger.debug("os.setsid failed: %s", e)

            # 2. Enforce memory limit (RLIMIT_AS)
            if hasattr(resource, "RLIMIT_AS"):
                try:
                    limit_bytes = memory_limit_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
                except (ValueError, OSError, resource.error) as e:
                    logger.debug("Failed setting RLIMIT_AS: %s", e)

            # 3. Enforce CPU execution limit (RLIMIT_CPU)
            if hasattr(resource, "RLIMIT_CPU"):
                try:
                    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_seconds, cpu_limit_seconds + 10))
                except (ValueError, OSError, resource.error) as e:
                    logger.debug("Failed setting RLIMIT_CPU: %s", e)

            # 4. Enforce open file limit (RLIMIT_NOFILE)
            if hasattr(resource, "RLIMIT_NOFILE"):
                try:
                    cur_soft, cur_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                    target_limit = min(max_open_files, cur_hard) if cur_hard > 0 else max_open_files
                    resource.setrlimit(resource.RLIMIT_NOFILE, (target_limit, cur_hard))
                except (ValueError, OSError, resource.error) as e:
                    logger.debug("Failed setting RLIMIT_NOFILE: %s", e)

            # 5. Non-root privilege drop if executed as root
            if drop_privileges_if_root and hasattr(os, "geteuid") and os.geteuid() == 0:
                try:
                    import pwd
                    pw = pwd.getpwnam("nobody")
                    if hasattr(os, "setgid"):
                        os.setgid(pw.pw_gid)
                    if hasattr(os, "setuid"):
                        os.setuid(pw.pw_uid)
                except Exception as e:
                    logger.warning("Could not drop root privileges to 'nobody': %s", e)

        return {"preexec_fn": preexec_fn}

    def terminate_process_tree(self, scan_id: uuid.UUID, timeout: float = 3.0) -> bool:
        """Terminates all child and descendant processes recursively within `timeout` seconds.

        First attempts graceful SIGTERM on process groups and psutil trees, followed by SIGKILL
        on any surviving processes within the 3.0s deadline.
        """
        pids = self._scan_pids.pop(scan_id, [])
        pgids = self._scan_pgids.pop(scan_id, [])

        if not pids and not pgids:
            return True

        current_pgid = os.getpgrp() if hasattr(os, "getpgrp") else None

        # Phase 1: Send SIGTERM to recorded Process Groups (POSIX killpg)
        if hasattr(os, "killpg"):
            for pgid in pgids:
                if pgid and pgid != current_pgid:
                    try:
                        os.killpg(pgid, signal.SIGTERM)
                    except (ProcessLookupError, OSError):
                        pass

        # Phase 2: Gather all psutil descendant processes
        all_procs: List[psutil.Process] = []
        for pid in pids:
            try:
                parent = psutil.Process(pid)
                descendants = parent.children(recursive=True)
                all_procs.extend(descendants)
                all_procs.append(parent)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # De-duplicate process objects
        unique_procs = {p.pid: p for p in all_procs}

        # Send terminate() to all processes
        for p in unique_procs.values():
            try:
                p.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Phase 3: Wait up to timeout (at most 3.0s)
        wait_deadline = min(max(timeout, 0.5), 3.0)
        _, alive = psutil.wait_procs(list(unique_procs.values()), timeout=wait_deadline)

        # Phase 4: Escalate to SIGKILL for any stubborn survivors
        if alive:
            if hasattr(os, "killpg"):
                for pgid in pgids:
                    if pgid and pgid != current_pgid:
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except (ProcessLookupError, OSError):
                            pass

            for p in alive:
                try:
                    p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            _, still_alive = psutil.wait_procs(alive, timeout=0.5)
            return len(still_alive) == 0

        return True


process_safety = ProcessSafetyManager()
