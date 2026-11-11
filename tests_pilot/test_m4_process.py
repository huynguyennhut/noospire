"""Milestone 4 · process level, persistent SQLite file, real processes on loopback:
API + gateway, TWO scheduler processes racing for the same slot, then TWO worker processes
draining a controlled internal load (40 synthetic SBOM executions, `*.pilot-test.invalid`,
no network) under an estate-wide cap of 3 running executions.

Prints the measured load figures (used in docs/pilot/M4_HANDOVER.md).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime

from tests_pilot.test_m3_restart import DATA, PY, ROOT, Stack, _client, _port, _wait

N_ASSETS = 40
CAP = 3


def _overlap(intervals) -> int:
    pts = sorted([(s, 1) for s, _ in intervals] + [(e, -1) for _, e in intervals], key=lambda p: (p[0], p[1]))
    cur = best = 0
    for _, d in pts:
        cur += d
        best = max(best, cur)
    return best


def _spawn(st: Stack, name: str, cmd: list, env: dict) -> None:
    log = open(st.tmp / f"{name}.log", "ab")
    st.procs[name] = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)


def _until(fn, timeout: float, step: float = 0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("condition not reached in time")


def test_two_schedulers_one_slot_then_capped_workers_drain_load():
    st = Stack()
    password = "pilot-owner-" + uuid.uuid4().hex
    try:
        boot = subprocess.run([PY, "-m", "backend.app.cli", "bootstrap-owner", "--username", "pilot-owner",
                               "--password-stdin"], cwd=str(ROOT), env=st.env, input=password + "\n",
                              capture_output=True, text=True, timeout=60)
        assert boot.returncode == 0, boot.stderr
        st.start("api", "gateway")
        c = _client(st, password)
        c.post("/api/v1/threat-intel/advisory-snapshots",
               params={"source": "pilot-test synthetic OSV", "version_label": "pilot-v1"},
               content=(DATA / "advisories_pilot_v1.json").read_bytes(), headers={"content-type": "application/json"})
        sbom = (DATA / "sbom_vulnerable.cdx.json").read_bytes()
        for n in range(N_ASSETS):
            a = c.post("/api/v1/assets", json={"name": f"pilot-test-load-{n:02d}",
                                               "target_locator": f"https://load-{n:02d}.pilot-test.invalid/"})
            assert a.status_code == 201, a.text
            r = c.post(f"/api/v1/assets/{a.json()['id']}/artifacts", params={"filename": "bom.json"},
                       content=sbom, headers={"content-type": "application/json"})
            assert r.status_code == 201
        assert c.put("/api/v1/operations/capacity",
                     json={"max_running_executions": CAP, "per_host_hourly_quota": 12}).status_code == 200
        sched = c.post("/api/v1/monitor-schedules", json={"name": "pilot-test hourly load", "engines": ["sbom"],
                                                          "selection": {"kind": "all"}, "max_workers": CAP})
        assert sched.status_code == 201, sched.text
        sid = sched.json()["id"]
        # Make the current hour's slot due: the schedule "existed" 3 hours ago.
        db = sqlite3.connect(st.tmp / "pilot.db")
        db.execute("UPDATE monitor_schedules SET start_after = datetime(start_after, '-3 hours')")
        db.commit()
        db.close()

        # Two scheduler processes tick every 0.5 s against the same DB.
        for name in ("sched-1", "sched-2"):
            port = _port()
            _spawn(st, name, [PY, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
                   {**st.env, "SENTINEL_PROCESS_ROLE": "scheduler", "NOOSPIRE_SCHEDULER_TICK_SECONDS": "0.5"})
            _wait(f"http://127.0.0.1:{port}/healthz/live")
        slots = _until(lambda: c.get(f"/api/v1/monitor-schedules/{sid}/slots").json(), 30)
        time.sleep(4)  # several more ticks from both processes
        slots = c.get(f"/api/v1/monitor-schedules/{sid}/slots").json()
        assert len(slots) == 1, slots
        slot = slots[0]
        assert slot["status"] == "launched" and slot["plan_summary"]["queue"] == N_ASSETS
        # Created "3 h ago": the two slots that never fired are counted, covered by this single launch.
        assert slot["missed_before"] == 2 and slot["coalesced_slots"] == 2
        assert slot["claimed_by"].startswith("scheduler-")
        run = c.get(f"/api/v1/runs/{slot['batch_id']}").json()
        assert run["by_status"] == {"queued": N_ASSETS} and run["correlation_id"] == slot["correlation_id"]

        # Two worker processes drain the load under the estate cap.
        t_start = time.time()
        for name in ("worker-1", "worker-2"):
            _spawn(st, name, [PY, "-m", "backend.app.worker"], {**st.env, "SENTINEL_PROCESS_ROLE": "worker"})
        run = _until(lambda: (lambda r: r if r["finished"] else None)(c.get(f"/api/v1/runs/{slot['batch_id']}").json()),
                     180)
        wall = time.time() - t_start
        assert run["by_status"] == {"succeeded": N_ASSETS}, run["by_status"]

        intervals, workers, attempts = [], set(), 0
        for ex in run["executions"]:
            d = c.get(f"/api/v1/executions/{ex['execution_id']}").json()
            ok = [a for a in d["attempts"] if a["status"] == "succeeded"]
            assert len(ok) == 1  # never committed twice
            attempts += len(d["attempts"])
            a = ok[0]
            workers.add(a["worker_id"])
            intervals.append((datetime.fromisoformat(a["started_at"]), datetime.fromisoformat(a["finished_at"])))
        peak = _overlap(intervals)
        assert peak <= CAP, f"{peak} attempts overlapped; cap is {CAP}"
        span = (max(e for _, e in intervals) - min(s for s, _ in intervals)).total_seconds()

        # Slot result after the drain (schedulers still running).
        s = _until(lambda: (lambda x: x if x["latest_result"]["status"] else None)(
            c.get("/api/v1/monitor-schedules").json()["items"][0]), 30)
        assert s["latest_result"]["status"] == "completed" and s["last_full_success_at"]
        assert len(c.get(f"/api/v1/monitor-schedules/{sid}/slots").json()) == 1

        m = c.get("/api/v1/operations/metrics").json()["engines"]["sbom"]
        ov = c.get("/api/v1/operations/overview").json()
        result = {
            "executions": N_ASSETS, "worker_processes": 2, "workers_used": len(workers), "estate_cap": CAP,
            "attempts_total": attempts, "peak_concurrent_attempts": peak,
            "wall_seconds_from_worker_start": round(wall, 2), "processing_span_seconds": round(span, 3),
            "throughput_per_hour_measured": int(N_ASSETS / max(span, 1e-3) * 3600),
            "duration_p50_s": m["duration_p50_s"], "duration_p95_s": m["duration_p95_s"],
            "slot_p50_s": m["slot_p50_s"], "slot_p95_s": m["slot_p95_s"],
            "queue_delay_p50_s": m["queue_delay_p50_s"], "queue_delay_p95_s": m["queue_delay_p95_s"],
            "cpu_ms_avg": m["cpu_ms_avg"], "rss_bytes_max": m["rss_bytes_max"],
            "input_bytes": m["input_bytes"], "output_bytes": m["output_bytes"],
            "theoretical_hourly_capacity": m["theoretical_hourly_capacity"],
            "workers_online": ov["workers_online"],
        }
        print("\nM4_LOAD_RESULT " + json.dumps(result))
        assert ov["workers_online"] == 2 and ov["engines"]["sbom"]["stale"] is False
    finally:
        st.stop()
