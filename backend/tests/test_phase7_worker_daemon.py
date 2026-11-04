"""
WAPSI Phase 7 — Gate 4: Production Background Worker Daemon & Concurrency Test Suite.

Comprehensive unit, integration, concurrency, and failure injection test suite covering:
1. Daemon lifecycle and configuration validation.
2. Graceful SIGTERM and SIGINT shutdown handling.
3. Atomic heartbeat monitoring (.wapsi_worker_heartbeat).
4. Active lease tracking and expired lease reclamation.
5. Multi-worker concurrency safety (5 simultaneous workers, 50 synthetic jobs).
6. Crash recovery, failure injection, and ambiguous outcome preservation.
7. Operator authorization, cryptographic snapshots, and tenant isolation governance.
8. Performance, latency, and throughput verification.
9. Dedicated PostgreSQL FOR UPDATE SKIP LOCKED concurrency test.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient, WhatsAppDispatchResult
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, compute_approval_hash
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker
from wapsi.recovery.worker_daemon import (
    RecoveryWorkerDaemon,
    WorkerDaemonConfig,
    WorkerHeartbeat,
)

logger = logging.getLogger("wapsi.test.worker_daemon")

TEST_MERCHANT_ID = "00000000-0000-4000-8000-000000000001"
TEST_PHONE_E164 = "919876543210"
MOCK_WAMID = "wamid.HBgLMTkxOTg3NjU0MzIxMBUC"


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provides an isolated directory for databases, heartbeats, and artifacts."""
    d = tmp_path / "worker_daemon_test"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def isolated_outbox(temp_dir: Path) -> DurableOutboxStore:
    """Isolated SQLite outbox database."""
    db_file = temp_dir / "test_outbox.db"
    return DurableOutboxStore(db_path=str(db_file))


@pytest.fixture
def isolated_opt_out(temp_dir: Path) -> PersistentOptOutStore:
    """Isolated SQLite opt-out database."""
    db_file = temp_dir / "test_opt_outs.db"
    return PersistentOptOutStore(db_path=str(db_file))


@pytest.fixture
def isolated_timeline(temp_dir: Path) -> RecoveryTimelineStore:
    """Isolated SQLite timeline database."""
    db_file = temp_dir / "test_timeline.db"
    return RecoveryTimelineStore(db_path=str(db_file))


@pytest.fixture
def mock_wa() -> MagicMock:
    """Mock WhatsApp client returning accepted delivery."""
    wa = MagicMock(spec=WhatsAppClient)
    wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
        success=True,
        message_id=MOCK_WAMID,
        recipient_phone=TEST_PHONE_E164,
        status="accepted",
        timestamp=time.time(),
        raw_response={"messages": [{"id": MOCK_WAMID}]},
    )
    wa.send_prepared_payload.return_value = WhatsAppDispatchResult(
        success=True,
        message_id=MOCK_WAMID,
        recipient_phone=TEST_PHONE_E164,
        status="accepted",
        timestamp=time.time(),
        raw_response={"messages": [{"id": MOCK_WAMID}]},
    )
    return wa


@pytest.fixture
def mock_rzp() -> MagicMock:
    """Mock Razorpay client returning test payment link."""
    rzp = MagicMock(spec=RazorpayClient)
    rzp.create_payment_link.return_value = {
        "id": "plink_daemon_mock_1",
        "short_url": "https://rzp.io/i/plink_daemon_mock_1",
        "status": "created",
        "amount": 1000,
        "currency": "INR",
    }
    rzp.get_payment_link.return_value = {
        "id": "plink_daemon_mock_1",
        "short_url": "https://rzp.io/i/plink_daemon_mock_1",
        "status": "created",
        "amount": 1000,
        "currency": "INR",
        "amount_paid": 0,
        "expired": False,
    }
    return rzp


def helper_create_and_approve_job(
    outbox: DurableOutboxStore,
    case_id: str,
    payment_id: str,
    amount_paise: int = 1500,
    merchant_id: str = TEST_MERCHANT_ID,
    operator_id: str = "op_test_lead",
    channel: str = "WHATSAPP",
    phone: str = TEST_PHONE_E164,
    link_id: Optional[str] = None,
) -> OutboxJob:
    """Creates and approves a valid synthetic outbox job."""
    payload: Dict[str, Any] = {
        "customer_phone": phone,
        "amount_paise": amount_paise,
        "customer_name": "Test Customer",
        "merchant_name": "Test Merchant",
    }
    if link_id:
        payload["payment_link_id"] = link_id
        payload["payment_link_url"] = f"https://rzp.io/i/{link_id}"

    job = outbox.enqueue(
        case_id=case_id,
        payment_id=payment_id,
        idempotency_key=f"idemp_{case_id}_{uuid.uuid4().hex[:6]}",
        action="DISPATCH_RECOVERY_NUDGE",
        channel=channel,
        recipient_masked=f"{phone[:4]}***{phone[-2:]}",
        message_payload=payload,
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    outbox.approve_job(job.id, operator_id=operator_id, merchant_id=merchant_id)
    return outbox.get_job(job.id, merchant_id=merchant_id)


# ==============================================================================
# SECTION 1: DAEMON LIFECYCLE & CONFIGURATION TESTS
# ==============================================================================

def test_01_daemon_config_validation_positive_and_negative(temp_dir: Path):
    """TC-01: Validates WorkerDaemonConfig defaults and rejects invalid parameters."""
    cfg = WorkerDaemonConfig(heartbeat_path=str(temp_dir / "hb.json"))
    assert cfg.poll_interval_seconds == 5.0
    assert cfg.lease_duration_seconds == 60
    assert cfg.heartbeat_interval_seconds == 10.0
    assert cfg.shutdown_grace_period_seconds == 15.0
    assert cfg.batch_size == 10
    assert cfg.max_concurrent_jobs == 10
    assert cfg.reclaim_expired_leases is True

    # Section 3.C canonical aliases and property accessors
    cfg_aliases = WorkerDaemonConfig(
        max_concurrent_jobs=8,
        worker_identity="w_custom_id",
        heartbeat_file_location=str(temp_dir / "hb_alias.json"),
        poll_interval=3.0,
        lease_duration=45,
        heartbeat_interval=7.0,
        shutdown_grace_period=12.0,
    )
    assert cfg_aliases.batch_size == 8
    assert cfg_aliases.max_concurrent_jobs == 8
    assert cfg_aliases.worker_id == "w_custom_id"
    assert cfg_aliases.worker_identity == "w_custom_id"
    assert cfg_aliases.heartbeat_path == str(temp_dir / "hb_alias.json")
    assert cfg_aliases.heartbeat_file_location == str(temp_dir / "hb_alias.json")
    assert cfg_aliases.poll_interval_seconds == 3.0
    assert cfg_aliases.lease_duration_seconds == 45
    assert cfg_aliases.heartbeat_interval_seconds == 7.0
    assert cfg_aliases.shutdown_grace_period_seconds == 12.0

    # Negative / zero poll interval rejected
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(poll_interval_seconds=0.0)
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(poll_interval_seconds=-2.0)

    # Negative lease duration rejected
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(lease_duration_seconds=0)

    # Negative batch size rejected
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(batch_size=0)
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(max_concurrent_jobs=0)

    # Empty heartbeat path rejected
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(heartbeat_path="   ")

    # Extra unknown inputs strictly forbidden
    with pytest.raises(ValidationError):
        WorkerDaemonConfig(forbidden_key_xyz=123)


def test_02_daemon_startup_and_initial_heartbeat(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-02: Daemon initializes, transitions to RUNNING, and creates valid initial heartbeat."""
    hb_file = temp_dir / "worker_heartbeat.json"
    cfg = WorkerDaemonConfig(
        worker_id="worker_alpha_01",
        heartbeat_path=str(hb_file),
        poll_interval_seconds=0.1,
        max_cycles=1,
    )

    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    assert daemon.worker_id == "worker_alpha_01"
    assert not daemon.is_running

    # Run single cycle
    daemon.run_forever()

    assert not daemon.is_running
    assert hb_file.exists()

    hb = WorkerHeartbeat.read(hb_file)
    assert hb is not None
    assert hb.worker_id == "worker_alpha_01"
    assert hb.status == "STOPPED"
    assert hb.completed_job_count == 0


def test_03_daemon_empty_queue_idle_polling(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-03: Empty queue polling sets IDLE status, prevents busy-looping, and returns 0."""
    hb_file = temp_dir / "worker_idle_heartbeat.json"
    cfg = WorkerDaemonConfig(
        worker_id="worker_idle",
        heartbeat_path=str(hb_file),
        poll_interval_seconds=0.05,
    )

    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    processed = daemon.run_cycle()
    assert processed == 0

    hb = WorkerHeartbeat.read(hb_file)
    assert hb is not None
    assert hb.status == "IDLE"
    assert hb.active_lease_count == 0
    assert hb.last_successful_cycle_utc is not None


def test_03b_process_termination_during_idle_polling(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-03b: Process termination during idle polling responds immediately without waiting full sleep interval."""
    hb_file = temp_dir / "worker_idle_term.json"
    cfg = WorkerDaemonConfig(
        worker_id="worker_idle_term",
        heartbeat_path=str(hb_file),
        poll_interval_seconds=10.0,  # 10s idle sleep
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    t = threading.Thread(target=daemon.run_forever)
    t.start()
    time.sleep(0.05)  # Allow daemon to initialize and enter idle sleep

    assert daemon.is_running
    t0 = time.time()
    daemon.request_shutdown()
    t.join(timeout=2.0)
    elapsed = time.time() - t0

    assert not t.is_alive()
    assert not daemon.is_running
    assert elapsed < 1.0  # Woke up and terminated instantly, far before 10s poll interval


def test_04_daemon_context_manager_lifecycle(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-04: Context manager starts daemon and automatically executes graceful shutdown on exit."""
    hb_file = temp_dir / "cm_heartbeat.json"
    cfg = WorkerDaemonConfig(heartbeat_path=str(hb_file))

    with RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    ) as daemon:
        assert daemon.is_running
        hb = WorkerHeartbeat.read(hb_file)
        assert hb is not None
        assert hb.status == "RUNNING"

    # After exit block: daemon is stopped
    assert not daemon.is_running
    hb_after = WorkerHeartbeat.read(hb_file)
    assert hb_after is not None
    assert hb_after.status == "STOPPED"


def test_05_daemon_max_cycles_planned_termination(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-05: Configured max_cycles halts run_forever() cleanly after exact number of cycles."""
    hb_file = temp_dir / "cycles_hb.json"
    cfg = WorkerDaemonConfig(
        heartbeat_path=str(hb_file),
        poll_interval_seconds=0.01,
        max_cycles=4,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    daemon.run_forever()
    assert daemon.cycle_count == 4
    assert not daemon.is_running


# ==============================================================================
# SECTION 2: SIGNAL HANDLING & GRACEFUL SHUTDOWN TESTS
# ==============================================================================

def test_06_signal_handler_requests_shutdown_sigterm(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-06: Simulates SIGTERM signal; verifies shutdown flag set and clean termination."""
    hb_file = temp_dir / "sigterm_hb.json"
    cfg = WorkerDaemonConfig(heartbeat_path=str(hb_file), poll_interval_seconds=0.1)
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    assert not daemon._stop_event.is_set()

    # Simulate SIGTERM arrival
    daemon._signal_handler(signal.SIGTERM, None)

    assert daemon._stop_event.is_set()
    assert daemon._is_shutting_down is True


def test_07_signal_handler_requests_shutdown_sigint(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-07: Simulates SIGINT signal (Ctrl+C); verifies stop event and worker notification."""
    hb_file = temp_dir / "sigint_hb.json"
    cfg = WorkerDaemonConfig(heartbeat_path=str(hb_file))
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    daemon._signal_handler(signal.SIGINT, None)
    assert daemon._stop_event.is_set()
    assert daemon.worker._is_running is False


def test_08_graceful_shutdown_releases_undispatched_batch_leases(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-08: When a worker claims a batch of jobs and receives a shutdown signal mid-batch,
    undispatched jobs are immediately released back to QUEUED rather than left locked.
    """
    hb_file = temp_dir / "batch_release_hb.json"

    # Enqueue and approve 3 jobs
    j1 = helper_create_and_approve_job(isolated_outbox, "case_b1", "pay_b1", link_id="plink_b1")
    j2 = helper_create_and_approve_job(isolated_outbox, "case_b2", "pay_b2", link_id="plink_b2")
    j3 = helper_create_and_approve_job(isolated_outbox, "case_b3", "pay_b3", link_id="plink_b3")

    cfg = WorkerDaemonConfig(
        worker_id="worker_batcher",
        heartbeat_path=str(hb_file),
        batch_size=5,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    orig_process = daemon.worker.process_single_job
    executed_job_id = None

    def intercept_first_job(job):
        nonlocal executed_job_id
        executed_job_id = job.id
        # After executing first job, trigger shutdown before next jobs
        res = orig_process(job)
        daemon.request_shutdown()
        return res

    daemon.worker.process_single_job = intercept_first_job

    # Execute cycle
    daemon.run_cycle()

    # The executed job was completed
    assert executed_job_id is not None
    job_exec_updated = isolated_outbox.get_job(executed_job_id)
    assert job_exec_updated.status == "SENT"

    # The remaining jobs had leases released back to QUEUED
    all_job_ids = {j1.id, j2.id, j3.id}
    remaining_ids = all_job_ids - {executed_job_id}
    assert len(remaining_ids) == 2
    for rem_id in remaining_ids:
        rem_job = isolated_outbox.get_job(rem_id)
        assert rem_job.status == "QUEUED"
        assert rem_job.worker_id is None
        assert rem_job.lease_expires_at is None


def test_09_graceful_shutdown_waits_for_in_flight_job(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-09: Graceful shutdown allows in-flight operation to finish within grace period.
    """
    hb_file = temp_dir / "in_flight_hb.json"
    j1 = helper_create_and_approve_job(isolated_outbox, "case_inflight", "pay_inf", link_id="plink_inf")

    cfg = WorkerDaemonConfig(
        worker_id="worker_inflight",
        heartbeat_path=str(hb_file),
        shutdown_grace_period_seconds=2.0,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    in_flight_started = threading.Event()
    shutdown_called = threading.Event()

    orig_process = daemon.worker.process_single_job

    def slow_process(job):
        in_flight_started.set()
        # Wait until shutdown has been requested
        shutdown_called.wait(timeout=2.0)
        time.sleep(0.1)  # small in-flight work
        return orig_process(job)

    daemon.worker.process_single_job = slow_process

    def run_worker():
        daemon.run_cycle()

    t = threading.Thread(target=run_worker)
    t.start()

    in_flight_started.wait(timeout=2.0)
    # Request shutdown while job is in-flight
    daemon.request_shutdown()
    shutdown_called.set()

    t.join(timeout=3.0)

    # In-flight job completed cleanly
    job_updated = isolated_outbox.get_job(j1.id)
    assert job_updated.status == "SENT"


def test_10_graceful_shutdown_timeout_safety(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-10: Grace period expiration terminates shutdown cleanly without deadlocking."""
    hb_file = temp_dir / "timeout_hb.json"
    cfg = WorkerDaemonConfig(
        worker_id="worker_timeout",
        heartbeat_path=str(hb_file),
        shutdown_grace_period_seconds=0.1,  # very short grace period
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # Artificially hold in-flight lock to simulate stuck job
    daemon._in_flight_job = OutboxJob(
        id=str(uuid.uuid4()), case_id="c", payment_id="p", merchant_id="m",
        idempotency_key="k", action="a", channel="c", recipient_masked="r",
        message_payload={}, status="SENDING", retry_count=0, max_retries=3,
        next_attempt_at=time.time(), lease_expires_at=time.time() + 60,
        worker_id=daemon.worker_id, last_error=None, created_at=time.time(), updated_at=time.time()
    )

    t0 = time.time()
    daemon._perform_graceful_shutdown()
    duration = time.time() - t0

    # Shutdown completed within bounds without hanging
    assert duration < 1.0
    hb = WorkerHeartbeat.read(hb_file)
    assert hb is not None
    assert hb.status == "STOPPED"


def test_10b_graceful_shutdown_timeout_preserves_inflight_lease_and_releases_undispatched(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-10b: Critical Anti-Duplicate Protection.
    When graceful shutdown times out while an in-flight job is active:
    - The in-flight job's active lease is PRESERVED (NOT blindly reset to QUEUED).
    - Other undispatched batch jobs ARE safely released back to QUEUED.
    - Prevents concurrent duplicate dispatch by other workers.
    """
    hb_file = temp_dir / "timeout_protect_hb.json"
    j_inflight = helper_create_and_approve_job(
        isolated_outbox, "case_inflight_protect", "pay_inf_p", link_id="plink_inf_p"
    )
    j_undispatched = helper_create_and_approve_job(
        isolated_outbox, "case_undisp_protect", "pay_undisp_p", link_id="plink_undisp_p"
    )

    cfg = WorkerDaemonConfig(
        worker_id="worker_timeout_protect",
        heartbeat_path=str(hb_file),
        shutdown_grace_period_seconds=0.05,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # Claim both jobs under this worker
    claimed = isolated_outbox.claim_jobs(worker_id=daemon.worker_id, limit=2, lease_duration_seconds=60)
    assert len(claimed) == 2

    # Simulate j_inflight currently executing in background thread
    with daemon._in_flight_lock:
        daemon._in_flight_job = j_inflight

    # Trigger shutdown while j_inflight is in flight
    daemon._perform_graceful_shutdown()

    # Verify j_undispatched was cleanly released to QUEUED
    undisp_state = isolated_outbox.get_job(j_undispatched.id)
    assert undisp_state.status == "QUEUED"
    assert undisp_state.worker_id is None
    assert undisp_state.lease_expires_at is None

    # Verify j_inflight was PRESERVED in SENDING with active lease
    inflight_state = isolated_outbox.get_job(j_inflight.id)
    assert inflight_state.status == "SENDING"
    assert inflight_state.worker_id == daemon.worker_id
    assert inflight_state.lease_expires_at is not None


# ==============================================================================
# SECTION 3: HEARTBEAT MONITORING & HEALTH CHECK TESTS
# ==============================================================================

def test_11_heartbeat_atomic_write_and_read(temp_dir: Path):
    """TC-11: Validates atomic write and deserialization of WorkerHeartbeat."""
    hb_path = temp_dir / "sub" / "heartbeat.json"
    now_iso = datetime.now(timezone.utc).isoformat()

    hb = WorkerHeartbeat(
        worker_id="worker_hb_11",
        pid=os.getpid(),
        timestamp_utc=now_iso,
        status="RUNNING",
        started_at_utc=now_iso,
        active_lease_count=3,
        completed_job_count=12,
        failed_job_count=1,
        last_cycle_duration_seconds=0.045,
        last_error_category=None,
    )

    hb.write_atomic(hb_path)
    assert hb_path.is_file()

    loaded = WorkerHeartbeat.read(hb_path)
    assert loaded is not None
    assert loaded.worker_id == "worker_hb_11"
    assert loaded.active_lease_count == 3
    assert loaded.completed_job_count == 12
    assert loaded.failed_job_count == 1
    assert loaded.status == "RUNNING"


def test_12_heartbeat_atomic_overwrite_preserves_integrity(temp_dir: Path):
    """TC-12: Rapid atomic overwrites leave no corrupted or partial JSON files."""
    hb_path = temp_dir / "rapid_heartbeat.json"

    for i in range(25):
        hb = WorkerHeartbeat(
            worker_id=f"worker_{i}",
            pid=os.getpid(),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            status="PROCESSING" if i % 2 == 0 else "IDLE",
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            completed_job_count=i,
        )
        hb.write_atomic(hb_path)

        read_hb = WorkerHeartbeat.read(hb_path)
        assert read_hb is not None
        assert read_hb.completed_job_count == i


def test_13_heartbeat_stale_detection(temp_dir: Path):
    """TC-13: Detects stale heartbeats exceeding configured threshold."""
    now = datetime.now(timezone.utc)
    fresh_time = now.isoformat()
    stale_time = (now - timedelta(seconds=45)).isoformat()

    fresh_hb = WorkerHeartbeat(
        worker_id="fresh",
        pid=123,
        timestamp_utc=fresh_time,
        status="RUNNING",
        started_at_utc=fresh_time,
    )
    assert fresh_hb.is_stale(stale_threshold_seconds=30.0, current_time=now) is False

    stale_hb = WorkerHeartbeat(
        worker_id="stale",
        pid=456,
        timestamp_utc=stale_time,
        status="RUNNING",
        started_at_utc=stale_time,
    )
    assert stale_hb.is_stale(stale_threshold_seconds=30.0, current_time=now) is True


def test_14_heartbeat_write_failure_resilience(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-14: Filesystem write failures are caught and logged without terminating daemon."""
    # Point heartbeat to an invalid file path that cannot be created as a file
    # (e.g. creating a directory with the same name and trying to open it for write)
    bad_dir = temp_dir / "bad_hb_dir"
    bad_dir.mkdir(parents=True, exist_ok=True)
    # Making bad_dir the heartbeat path itself will cause open(..., 'w') on bad_dir.tmp.* to succeed,
    # but let's mock open or write_atomic to simulate OSError
    cfg = WorkerDaemonConfig(heartbeat_path=str(bad_dir / "hb.json"))
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    with patch.object(WorkerHeartbeat, "write_atomic", side_effect=OSError("Disk full")):
        # Must not raise
        daemon.update_heartbeat(status="RUNNING")


def test_15_heartbeat_sanitization_no_pii_or_credentials(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-15: Asserts heartbeat JSON contains zero tokens, secrets, or customer PII."""
    hb_file = temp_dir / "clean_hb.json"
    cfg = WorkerDaemonConfig(heartbeat_path=str(hb_file))
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    daemon.update_heartbeat(status="PROCESSING")
    with open(hb_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify no sensitive keywords or customer data
    forbidden = ["secret", "token", "password", "Bearer", "919876543210", "key_secret"]
    for word in forbidden:
        assert word not in content


def test_16_deep_health_check_detects_db_failure_independently(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-16: health_check() does not mask DB errors even if heartbeat file exists."""
    hb_file = temp_dir / "health_hb.json"
    cfg = WorkerDaemonConfig(heartbeat_path=str(hb_file))
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # Initial check with healthy DB
    daemon.update_heartbeat(status="RUNNING")
    hc = daemon.health_check()
    assert hc["db_healthy"] is True
    assert hc["heartbeat_healthy"] is True

    # Simulate DB disconnection/error
    with patch.object(isolated_outbox, "get_metrics", side_effect=RuntimeError("DB Connection Lost")):
        hc_bad = daemon.health_check()
        assert hc_bad["db_healthy"] is False
        assert hc_bad["heartbeat_healthy"] is True  # Heartbeat was recent, but DB is flagged as down!


# ==============================================================================
# SECTION 4: EXPIRED LEASE RECLAMATION TESTS
# ==============================================================================

def test_17_expired_lease_reclaimed_by_daemon_sweep(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-17: Expired SENDING leases (lease_expires_at < now) are reclaimed to QUEUED."""
    j1 = helper_create_and_approve_job(isolated_outbox, "case_exp_1", "pay_exp_1", link_id="plink_exp_1")

    # Claim job with 5s lease at t0
    t0 = time.time()
    claimed = isolated_outbox.claim_jobs(worker_id="dead_worker", limit=1, lease_duration_seconds=5, current_time=t0)
    assert len(claimed) == 1
    assert claimed[0].status == "SENDING"

    cfg = WorkerDaemonConfig(
        worker_id="reclaimer_daemon",
        heartbeat_path=str(temp_dir / "hb.json"),
        reclaim_expired_leases=True,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # At t0 + 2s: Lease is still active -> 0 reclaimed
    with patch("time.time", return_value=t0 + 2):
        reclaimed_count = daemon.perform_lease_reclamation()
        assert reclaimed_count == 0

    # At t0 + 10s: Lease expired -> Reclaimed
    with patch("time.time", return_value=t0 + 10):
        reclaimed_count = daemon.perform_lease_reclamation()
        assert reclaimed_count == 1

    # Verified job is back in QUEUED with worker_id cleared
    job_reclaimed = isolated_outbox.get_job(j1.id)
    assert job_reclaimed.status == "QUEUED"
    assert job_reclaimed.worker_id is None
    assert job_reclaimed.lease_expires_at is None


def test_18_active_lease_not_reclaimed(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-18: Active leases (lease_expires_at >= now) are never reclaimed."""
    j1 = helper_create_and_approve_job(isolated_outbox, "case_act", "pay_act", link_id="plink_act")

    t0 = time.time()
    isolated_outbox.claim_jobs(worker_id="active_worker", limit=1, lease_duration_seconds=300, current_time=t0)

    cfg = WorkerDaemonConfig(heartbeat_path=str(temp_dir / "hb.json"))
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    with patch("time.time", return_value=t0 + 30):
        assert daemon.perform_lease_reclamation() == 0

    job_state = isolated_outbox.get_job(j1.id)
    assert job_state.status == "SENDING"
    assert job_state.worker_id == "active_worker"


def test_19_completed_and_terminal_jobs_never_reclaimed(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-19: Terminal status jobs (SENT, DEAD_LETTER, RECONCILIATION_REQUIRED) are immune to reclamation."""
    j1 = helper_create_and_approve_job(isolated_outbox, "case_sent", "pay_sent", link_id="plink_sent")
    isolated_outbox.claim_jobs(worker_id="w1", limit=1)
    isolated_outbox.complete_job(j1.id, worker_id="w1")

    cfg = WorkerDaemonConfig(heartbeat_path=str(temp_dir / "hb.json"))
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    with patch("time.time", return_value=time.time() + 999999):
        assert daemon.perform_lease_reclamation() == 0

    assert isolated_outbox.get_job(j1.id).status == "SENT"


def test_20_tenant_isolated_reclamation(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-20: Tenant scoping limits lease reclamation to the target merchant."""
    m_alpha = str(uuid.uuid4())
    m_beta = str(uuid.uuid4())

    j_alpha = helper_create_and_approve_job(isolated_outbox, "case_ta", "pay_ta", merchant_id=m_alpha, link_id="plink_ta")
    j_beta = helper_create_and_approve_job(isolated_outbox, "case_tb", "pay_tb", merchant_id=m_beta, link_id="plink_tb")

    t0 = time.time()
    isolated_outbox.claim_jobs(worker_id="w_alpha", limit=1, lease_duration_seconds=5, current_time=t0)
    isolated_outbox.claim_jobs(worker_id="w_beta", limit=1, lease_duration_seconds=5, current_time=t0)

    # Reclaim only for tenant Alpha
    cfg_alpha = WorkerDaemonConfig(
        worker_id="reclaimer_alpha",
        heartbeat_path=str(temp_dir / "hb_a.json"),
        merchant_id=m_alpha,
    )
    daemon_alpha = RecoveryWorkerDaemon(
        config=cfg_alpha,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    with patch("time.time", return_value=t0 + 20):
        reclaimed = daemon_alpha.perform_lease_reclamation()
        assert reclaimed == 1

    # Alpha was reclaimed to QUEUED
    assert isolated_outbox.get_job(j_alpha.id).status == "QUEUED"
    # Beta remains untouched in SENDING
    assert isolated_outbox.get_job(j_beta.id).status == "SENDING"


def test_20b_sqlalchemy_repository_tenant_isolation_and_reclaim_limits():
    """
    TC-20b: Validates RecoveryOutboxRepository tenant isolation and max_reclaim limits
    under SQLAlchemy directly across reclaim_expired_leases, release_leases_for_worker, and count_active_leases.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from wapsi.db.models import Base, RecoveryOutboxModel
    from wapsi.db.repository import RecoveryOutboxRepository

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        m1 = uuid.uuid4()
        m2 = uuid.uuid4()
        now = datetime.now(timezone.utc)
        past = now - timedelta(seconds=100)

        # 3 expired jobs for m1, 2 expired jobs for m2
        for i in range(3):
            session.add(RecoveryOutboxModel(
                id=uuid.uuid4(),
                case_id=f"c1_{i}",
                payment_id=f"p1_{i}",
                merchant_id=m1,
                idempotency_key=f"idemp_m1_{i}",
                action="DISPATCH",
                channel="WHATSAPP",
                recipient_masked="91***",
                message_payload={},
                status="SENDING",
                worker_id="w1",
                lease_expires_at=past,
                next_attempt_at=now,
            ))
        for i in range(2):
            session.add(RecoveryOutboxModel(
                id=uuid.uuid4(),
                case_id=f"c2_{i}",
                payment_id=f"p2_{i}",
                merchant_id=m2,
                idempotency_key=f"idemp_m2_{i}",
                action="DISPATCH",
                channel="WHATSAPP",
                recipient_masked="91***",
                message_payload={},
                status="SENDING",
                worker_id="w2",
                lease_expires_at=past,
                next_attempt_at=now,
            ))
        session.commit()

        # 1. Reclaim with max_reclaim=1 for m1 -> exactly 1 reclaimed
        reclaimed_m1 = RecoveryOutboxRepository.reclaim_expired_leases(
            session=session,
            current_time=now,
            max_reclaim=1,
            merchant_id=m1,
        )
        assert reclaimed_m1 == 1

        # 2. Count active remaining SENDING for m1 is 2, m2 is 2
        cnt_m1_sending = session.query(RecoveryOutboxModel).filter_by(merchant_id=m1, status="SENDING").count()
        cnt_m2_sending = session.query(RecoveryOutboxModel).filter_by(merchant_id=m2, status="SENDING").count()
        assert cnt_m1_sending == 2
        assert cnt_m2_sending == 2

        # 3. Test release_leases_for_worker with exclude_job_ids
        m1_sending_jobs = session.query(RecoveryOutboxModel).filter_by(merchant_id=m1, status="SENDING").all()
        preserved_id = m1_sending_jobs[0].id
        released = RecoveryOutboxRepository.release_leases_for_worker(
            session=session,
            worker_id="w1",
            merchant_id=m1,
            exclude_job_ids=[preserved_id],
        )
        assert released == 1
        # Preserved job is still SENDING
        preserved_job = session.query(RecoveryOutboxModel).filter_by(id=preserved_id).first()
        assert preserved_job.status == "SENDING"

    finally:
        session.close()


# ==============================================================================
# SECTION 5: MULTI-WORKER CONCURRENCY TESTS (5 WORKERS, 50 JOBS)
# ==============================================================================

def test_21_multi_worker_5_workers_50_jobs_zero_duplicate_claims(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-21: High-Concurrency Invariant Test.
    5 simultaneous workers process 50 approved synthetic jobs.
    Guarantees:
    - Exactly 50 jobs claimed across all workers.
    - Exactly 0 duplicate executions.
    - Zero active lease collisions.
    - 100% completion rate (50 completed).
    """
    NUM_WORKERS = 5
    NUM_JOBS = 50

    jobs = []
    for i in range(NUM_JOBS):
        j = helper_create_and_approve_job(
            isolated_outbox,
            case_id=f"case_conc_{i:03d}",
            payment_id=f"pay_conc_{i:03d}",
            link_id=f"plink_conc_{i:03d}",
        )
        jobs.append(j)

    assert len(jobs) == NUM_JOBS

    # Create 5 distinct worker daemons
    workers: List[RecoveryWorkerDaemon] = []
    for w in range(NUM_WORKERS):
        cfg = WorkerDaemonConfig(
            worker_id=f"worker_concurrent_{w}",
            heartbeat_path=str(temp_dir / f"hb_w{w}.json"),
            batch_size=5,
            lease_duration_seconds=30,
            poll_interval_seconds=0.01,
        )
        daemon = RecoveryWorkerDaemon(
            config=cfg,
            outbox_store=isolated_outbox,
            opt_out_store=isolated_opt_out,
            timeline_store=isolated_timeline,
            whatsapp_client=mock_wa,
            razorpay_client=mock_rzp,
        )
        workers.append(daemon)

    claimed_by_worker: Dict[str, List[str]] = {w.worker_id: [] for w in workers}
    worker_locks = threading.Lock()

    def run_worker_task(daemon: RecoveryWorkerDaemon):
        completed_local = 0
        while True:
            # Check remaining
            metrics = isolated_outbox.get_metrics()
            if metrics.get("QUEUED", 0) == 0 and metrics.get("SENDING", 0) == 0:
                break
            claimed = daemon.run_cycle()
            completed_local += claimed
            if completed_local >= NUM_JOBS:
                break
            time.sleep(0.005)
        return daemon.worker_id, completed_local

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = [executor.submit(run_worker_task, d) for d in workers]
        results = [f.result() for f in as_completed(futures)]

    elapsed = time.time() - t_start

    # Verify results
    total_completed = sum(r[1] for r in results)
    assert total_completed == NUM_JOBS

    # Verify database status
    metrics = isolated_outbox.get_metrics()
    assert metrics.get("SENT") == NUM_JOBS
    assert metrics.get("QUEUED") == 0
    assert metrics.get("SENDING") == 0

    logger.info(f"Multi-worker test finished in {elapsed:.2f}s ({NUM_JOBS / elapsed:.1f} jobs/sec).")


def test_22_multi_worker_simultaneous_lease_acquisition_no_double_ownership(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-22: Exactly one worker wins when multiple workers race to claim the exact same single job.
    """
    j = helper_create_and_approve_job(isolated_outbox, "case_race_1", "pay_race_1", link_id="plink_race_1")

    claim_results: List[Tuple[str, int]] = []
    barrier = threading.Barrier(5)

    def racer(worker_idx: int):
        barrier.wait()  # Synchronize threads to fire simultaneously
        w_id = f"racer_{worker_idx}"
        claimed = isolated_outbox.claim_jobs(worker_id=w_id, limit=1, lease_duration_seconds=60)
        return w_id, len(claimed)

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(racer, i) for i in range(5)]
        claim_results = [f.result() for f in futures]

    winners = [wid for wid, cnt in claim_results if cnt == 1]
    losers = [wid for wid, cnt in claim_results if cnt == 0]

    assert len(winners) == 1  # Exactly 1 winner
    assert len(losers) == 4   # Remaining 4 get 0 jobs

    job_state = isolated_outbox.get_job(j.id)
    assert job_state.status == "SENDING"
    assert job_state.worker_id == winners[0]


def test_23_multi_worker_cross_tenant_isolation(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-23: Workers operating on specific tenant never claim other tenant's jobs."""
    tenant_1 = str(uuid.uuid4())
    tenant_2 = str(uuid.uuid4())

    j1 = helper_create_and_approve_job(isolated_outbox, "case_t1", "pay_t1", merchant_id=tenant_1, link_id="plink_t1")
    j2 = helper_create_and_approve_job(isolated_outbox, "case_t2", "pay_t2", merchant_id=tenant_2, link_id="plink_t2")

    # Worker for tenant 1 claims by ID under tenant 1 context
    claimed_1 = isolated_outbox.claim_job_by_id(j1.id, worker_id="w_t1", merchant_id=tenant_1)
    assert claimed_1 is not None

    # Worker for tenant 1 attempts to claim tenant 2's job -> Returns None
    claimed_cross = isolated_outbox.claim_job_by_id(j2.id, worker_id="w_t1", merchant_id=tenant_1)
    assert claimed_cross is None


def test_24_multi_worker_concurrent_expired_lease_reclaim(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-24: Multiple concurrent reclaimer threads safely reclaim expired leases without deadlocks."""
    for i in range(10):
        helper_create_and_approve_job(isolated_outbox, f"case_exp_{i}", f"pay_exp_{i}", link_id=f"plink_e_{i}")

    t0 = time.time()
    # Claim all 10 with 5s lease
    isolated_outbox.claim_jobs(worker_id="crashed_all", limit=10, lease_duration_seconds=5, current_time=t0)

    # 4 threads race to reclaim after expiry
    reclaim_counts = []
    barrier = threading.Barrier(4)

    def reclaimer_task(idx: int):
        barrier.wait()
        return isolated_outbox.reclaim_expired_leases(current_time=t0 + 20, max_reclaim=10)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(reclaimer_task, i) for i in range(4)]
        reclaim_counts = [f.result() for f in futures]

    total_reclaimed = sum(reclaim_counts)
    assert total_reclaimed == 10

    # All 10 jobs are back to QUEUED
    metrics = isolated_outbox.get_metrics()
    assert metrics.get("QUEUED") == 10
    assert metrics.get("SENDING") == 0


# ==============================================================================
# SECTION 6: CRASH RECOVERY & FAILURE INJECTION TESTS
# ==============================================================================

def test_25_worker_crash_and_surviving_worker_recovery(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-25: Simulates worker crash mid-lease.
    Surviving worker daemon reclaims the expired lease and completes the recovery job.
    """
    j = helper_create_and_approve_job(isolated_outbox, "case_crash_survive", "pay_cs", link_id="plink_cs")

    t0 = time.time()
    # Crashed worker claims with 5-second lease then dies
    isolated_outbox.claim_jobs(worker_id="worker_crashed_rip", limit=1, lease_duration_seconds=5, current_time=t0)

    cfg = WorkerDaemonConfig(
        worker_id="worker_survivor",
        heartbeat_path=str(temp_dir / "survivor_hb.json"),
        reclaim_expired_leases=True,
        reclaim_interval_seconds=1.0,
    )
    survivor = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # Advance clock past lease expiration
    with patch("time.time", return_value=t0 + 15):
        # Survivor runs cycle: reclaims expired lease and executes it to completion
        survivor.run_cycle()

    job_state = isolated_outbox.get_job(j.id)
    assert job_state.status == "SENT"
    assert survivor.completed_jobs == 1


def test_26_worker_restart_picks_up_remaining_queue(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-26: When daemon stops and restarts, it resumes processing the remaining queue."""
    j1 = helper_create_and_approve_job(isolated_outbox, "case_rest_1", "pay_r1", link_id="plink_r1")
    j2 = helper_create_and_approve_job(isolated_outbox, "case_rest_2", "pay_r2", link_id="plink_r2")

    cfg1 = WorkerDaemonConfig(
        worker_id="worker_node_1",
        heartbeat_path=str(temp_dir / "restart_hb.json"),
        batch_size=1,
        max_cycles=1,  # Runs exactly 1 job then exits
    )
    d1 = RecoveryWorkerDaemon(
        config=cfg1,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )
    d1.run_forever()
    assert d1.completed_jobs == 1

    # Node 1 stopped. Start Node 2 (or Node 1 restart) to process remaining queue
    cfg2 = WorkerDaemonConfig(
        worker_id="worker_node_1_restart",
        heartbeat_path=str(temp_dir / "restart_hb.json"),
        batch_size=5,
        max_cycles=1,
    )
    d2 = RecoveryWorkerDaemon(
        config=cfg2,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )
    d2.run_forever()
    assert d2.completed_jobs == 1

    # Both completed
    assert isolated_outbox.get_job(j1.id).status == "SENT"
    assert isolated_outbox.get_job(j2.id).status == "SENT"


def test_27_ambiguous_dispatch_never_blindly_released_or_retried(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-27: Critical Payment Safety Invariant.
    Socket timeout contacting WhatsApp transitions to RECONCILIATION_REQUIRED.
    Daemon shutdown, restart, and lease reclamation NEVER reset it to QUEUED or blind-retry.
    """
    import httpx

    mock_wa.send_recovery_reminder.side_effect = httpx.TimeoutException("Meta Cloud API Read Timeout")

    j = helper_create_and_approve_job(isolated_outbox, "case_ambig", "pay_ambig", link_id="plink_ambig")

    cfg = WorkerDaemonConfig(
        worker_id="worker_timeout_test",
        heartbeat_path=str(temp_dir / "ambig_hb.json"),
        max_cycles=1,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    daemon.run_forever()

    job_state = isolated_outbox.get_job(j.id)
    assert job_state.status == "RECONCILIATION_REQUIRED"
    assert "Ambiguous network outcome" in job_state.last_error

    # Now run lease reclamation sweep — must NOT touch RECONCILIATION_REQUIRED
    reclaimed = daemon.perform_lease_reclamation()
    assert reclaimed == 0

    job_after = isolated_outbox.get_job(j.id)
    assert job_after.status == "RECONCILIATION_REQUIRED"


def test_28_database_connection_interruption_resilience(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-28: Transient DB failure during polling does not crash the daemon loop."""
    cfg = WorkerDaemonConfig(
        worker_id="worker_db_resilient",
        heartbeat_path=str(temp_dir / "db_res_hb.json"),
        poll_interval_seconds=0.01,
        max_cycles=2,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # First cycle raises DB error, second cycle succeeds
    orig_claim = isolated_outbox.claim_jobs
    calls = 0

    def flaky_claim(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Simulated Database Network Glitch")
        return orig_claim(*args, **kwargs)

    daemon.outbox.claim_jobs = flaky_claim

    # Must survive and complete 2 cycles
    daemon.run_forever()
    assert daemon.cycle_count == 2
    assert daemon.last_error_category == "RuntimeError"


def test_29_job_execution_exception_isolated(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-29: Unhandled exception during one job execution is recorded and does not crash daemon."""
    j1 = helper_create_and_approve_job(isolated_outbox, "case_err_1", "pay_e1", link_id="plink_e1")
    j2 = helper_create_and_approve_job(isolated_outbox, "case_ok_2", "pay_ok2", link_id="plink_ok2")

    cfg = WorkerDaemonConfig(
        worker_id="worker_isolated_err",
        heartbeat_path=str(temp_dir / "err_hb.json"),
        batch_size=5,
        max_cycles=1,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    orig_process = daemon.worker.process_single_job

    def explode_on_first(job):
        if job.id == j1.id:
            raise ValueError("Corrupt In-Memory Object")
        return orig_process(job)

    daemon.worker.process_single_job = explode_on_first

    daemon.run_forever()

    # Job 1 failed, Job 2 completed
    assert daemon.failed_jobs == 1
    assert daemon.completed_jobs == 1
    assert isolated_outbox.get_job(j2.id).status == "SENT"


def test_30_multiple_workers_restart_simultaneously(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-30: Multiple daemons starting at the exact same instant partition work cleanly."""
    for i in range(12):
        helper_create_and_approve_job(isolated_outbox, f"case_sim_{i}", f"pay_sim_{i}", link_id=f"plink_s_{i}")

    def start_worker(idx: int):
        cfg = WorkerDaemonConfig(
            worker_id=f"sim_worker_{idx}",
            heartbeat_path=str(temp_dir / f"sim_hb_{idx}.json"),
            batch_size=4,
            max_cycles=2,
            poll_interval_seconds=0.01,
        )
        d = RecoveryWorkerDaemon(
            config=cfg,
            outbox_store=isolated_outbox,
            opt_out_store=isolated_opt_out,
            timeline_store=isolated_timeline,
            whatsapp_client=mock_wa,
            razorpay_client=mock_rzp,
        )
        d.run_forever()
        return d.completed_jobs

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(start_worker, i) for i in range(3)]
        completed_counts = [f.result() for f in futures]

    assert sum(completed_counts) == 12
    assert isolated_outbox.get_metrics().get("SENT") == 12


# ==============================================================================
# SECTION 7: GOVERNANCE & SECURITY PRESERVATION TESTS
# ==============================================================================

def test_31_unapproved_job_never_claimed_by_daemon(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-31: Mandatory Governance Invariant.
    Jobs in PENDING_APPROVAL status are NEVER claimed by the background worker daemon.
    """
    unapproved = isolated_outbox.enqueue(
        case_id="case_unapproved",
        payment_id="pay_unappr",
        idempotency_key="idemp_unappr",
        action="DISPATCH_RECOVERY_NUDGE",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload={"amount_paise": 5000, "customer_phone": TEST_PHONE_E164},
        requires_operator_approval=True,
    )
    assert unapproved.status == "PENDING_APPROVAL"

    cfg = WorkerDaemonConfig(
        worker_id="daemon_gov_1",
        heartbeat_path=str(temp_dir / "gov_hb.json"),
        max_cycles=1,
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    daemon.run_forever()

    assert daemon.completed_jobs == 0
    refetched = isolated_outbox.get_job(unapproved.id)
    assert refetched.status == "PENDING_APPROVAL"
    assert refetched.worker_id is None


def test_32_tampered_payload_snapshot_fails_authorization(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """
    TC-32: Cryptographic Tamper Invariant.
    Modifying an approved message payload invalidates the SHA-256 snapshot and moves job to DEAD_LETTER.
    """
    j = helper_create_and_approve_job(isolated_outbox, "case_tamper", "pay_tamp", link_id="plink_tamp")

    cfg = WorkerDaemonConfig(
        worker_id="daemon_tamper_check",
        heartbeat_path=str(temp_dir / "tamper_hb.json"),
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # Daemon claims job
    claimed = isolated_outbox.claim_jobs(worker_id=daemon.worker_id, limit=1)
    assert len(claimed) == 1

    # Manually tamper with the payload in database after operator approval
    with isolated_outbox._get_sqlite_connection() as conn:
        conn.execute(
            "UPDATE recovery_outbox SET message_payload = ? WHERE id = ?",
            (json.dumps({"tampered_key": "HACKED_AMOUNT", "customer_phone": TEST_PHONE_E164}), j.id),
        )

    tampered_job = isolated_outbox.get_job(j.id)

    res = daemon.worker.process_single_job(tampered_job)
    assert res.status == "DEAD_LETTER"
    assert "Authorization rejected" in res.error_message

    refetched = isolated_outbox.get_job(j.id)
    assert refetched.status == "DEAD_LETTER"
    assert "AUTHORIZATION_REJECTED" in refetched.last_error


def test_33_opted_out_customer_suppressed_before_dispatch(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-33: Opt-out registered prior to dispatch suppresses the job without contacting recipient."""
    isolated_opt_out.record_opt_out(
        phone=TEST_PHONE_E164,
        reason="USER_REQUEST",
        source="inbound_test",
    )

    j = helper_create_and_approve_job(isolated_outbox, "case_opted", "pay_opt", link_id="plink_opt")

    cfg = WorkerDaemonConfig(
        worker_id="daemon_opt_check",
        heartbeat_path=str(temp_dir / "opt_hb.json"),
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    claimed = isolated_outbox.claim_jobs(worker_id=daemon.worker_id, limit=1)
    assert len(claimed) == 1

    res = daemon.worker.process_single_job(claimed[0])
    assert res.status in ("DEAD_LETTER", "SUPPRESSED")

    mock_wa.send_recovery_reminder.assert_not_called()
    mock_wa.send_prepared_payload.assert_not_called()


def test_34_idempotency_key_preserved_across_reclaim_and_retry(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-34: Unique idempotency keys are strictly maintained during retries and lease reclamation."""
    j = helper_create_and_approve_job(isolated_outbox, "case_idemp_check", "pay_idemp", link_id="plink_idemp")
    original_key = j.idempotency_key

    # Claim and fail with retryable error
    isolated_outbox.claim_jobs(worker_id="w_retry", limit=1)
    isolated_outbox.fail_job(j.id, worker_id="w_retry", error_message="Rate limit", is_retryable=True, backoff_seconds=1)

    refetched = isolated_outbox.get_job(j.id)
    assert refetched.status == "RETRY"
    assert refetched.idempotency_key == original_key
    assert refetched.retry_count == 1


# ==============================================================================
# SECTION 8: PERFORMANCE, BENCHMARK & RELIABILITY TESTS
# ==============================================================================

def test_35_poll_cycle_and_claim_latency_benchmark(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-35: Measures latencies for polling, job claiming, and atomic heartbeat updates."""
    helper_create_and_approve_job(isolated_outbox, "case_bench_1", "pay_b1", link_id="plink_b1")

    cfg = WorkerDaemonConfig(
        worker_id="worker_bench",
        heartbeat_path=str(temp_dir / "bench_hb.json"),
    )
    daemon = RecoveryWorkerDaemon(
        config=cfg,
        outbox_store=isolated_outbox,
        opt_out_store=isolated_opt_out,
        timeline_store=isolated_timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # 1. Heartbeat write latency
    t0 = time.perf_counter()
    daemon.update_heartbeat(status="RUNNING")
    hb_latency_ms = (time.perf_counter() - t0) * 1000

    # 2. Claim and process cycle latency
    t0 = time.perf_counter()
    processed = daemon.run_cycle()
    cycle_latency_ms = (time.perf_counter() - t0) * 1000

    assert processed == 1
    assert hb_latency_ms < 50.0       # Heartbeat write typically < 10ms
    assert cycle_latency_ms < 200.0   # Cycle with mock provider typically < 50ms


def test_36_concurrent_job_throughput_measurement(
    temp_dir: Path, isolated_outbox, isolated_opt_out, isolated_timeline, mock_wa, mock_rzp
):
    """TC-36: Verifies throughput of multiple concurrent workers without thread starvation."""
    TOTAL_JOBS = 20
    for i in range(TOTAL_JOBS):
        helper_create_and_approve_job(isolated_outbox, f"case_tp_{i}", f"pay_tp_{i}", link_id=f"plink_tp_{i}")

    t_start = time.perf_counter()

    def run_worker_batch(wid: int):
        cfg = WorkerDaemonConfig(
            worker_id=f"throughput_worker_{wid}",
            heartbeat_path=str(temp_dir / f"tp_hb_{wid}.json"),
            batch_size=5,
            poll_interval_seconds=0.01,
        )
        d = RecoveryWorkerDaemon(
            config=cfg,
            outbox_store=isolated_outbox,
            opt_out_store=isolated_opt_out,
            timeline_store=isolated_timeline,
            whatsapp_client=mock_wa,
            razorpay_client=mock_rzp,
        )
        cnt = 0
        while cnt < TOTAL_JOBS:
            c = d.run_cycle()
            cnt += c
            if c == 0:
                break
        return cnt

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(run_worker_batch, i) for i in range(4)]
        counts = [f.result() for f in futures]

    total_time = time.perf_counter() - t_start
    total_processed = sum(counts)

    assert total_processed == TOTAL_JOBS
    throughput = total_processed / total_time
    assert throughput > 5.0  # Confirms high-throughput concurrent processing without deadlocks


# ==============================================================================
# SECTION 9: DEDICATED POSTGRESQL CONCURRENCY TEST
# ==============================================================================

def test_37_postgres_concurrency_skip_locked_isolated(mock_wa, mock_rzp):
    """
    TC-37: Dedicated PostgreSQL Concurrency Test using SELECT ... FOR UPDATE SKIP LOCKED.
    Executes against an isolated test PostgreSQL cluster if configured.
    Guarantees:
    - Zero synthetic records written to hosted Supabase (filofxijqmgluuulivxb).
    - Zero interference with protected live target job 5a6587ab-2601-4017-b396-48e3d2fc2fda.
    - Validates FOR UPDATE SKIP LOCKED behavior across concurrent sessions.
    """
    import socket
    test_pg_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not test_pg_url:
        s = socket.socket()
        if s.connect_ex(("127.0.0.1", 5438)) == 0:
            test_pg_url = "postgresql://postgres@localhost:5438/postgres"
        s.close()

    if not test_pg_url:
        pytest.skip(
            "Isolated local PostgreSQL test cluster not active (port 5438 / POSTGRES_TEST_DATABASE_URL). "
            "Zero synthetic records written to hosted Supabase per operational safety mandate."
        )

    from wapsi.db.session import DatabaseManager
    mgr = DatabaseManager(database_url=test_pg_url)
    store = DurableOutboxStore(database_manager=mgr)
    synthetic_merchant = str(uuid.uuid4())
    job_ids = []

    try:
        # Enqueue 10 synthetic jobs under synthetic merchant
        for i in range(10):
            job = store.enqueue(
                case_id=f"case_pg_conc_{i}",
                payment_id=f"pay_pg_conc_{i}",
                idempotency_key=f"idemp_pg_conc_{uuid.uuid4().hex}",
                action="DISPATCH_RECOVERY_NUDGE",
                channel="WHATSAPP",
                recipient_masked="9198***10",
                message_payload={"amount_paise": 1000, "customer_phone": TEST_PHONE_E164},
                merchant_id=synthetic_merchant,
                requires_operator_approval=True,
            )
            store.approve_job(job.id, operator_id="pg_test_op", merchant_id=synthetic_merchant)
            job_ids.append(job.id)

        assert len(job_ids) == 10

        # Concurrent claim with 3 worker threads
        claimed_ids = []
        claim_lock = threading.Lock()

        def pg_claim_worker(wid: str):
            c = store.claim_jobs(worker_id=wid, limit=5, lease_duration_seconds=30)
            with claim_lock:
                claimed_ids.extend([j.id for j in c])
            for job in c:
                store.complete_job(job.id, worker_id=wid, merchant_id=synthetic_merchant)

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [ex.submit(pg_claim_worker, f"pg_worker_{i}") for i in range(3)]
            for f in futures:
                f.result()

        # All 10 jobs claimed with zero duplicates
        assert len(claimed_ids) == 10
        assert len(set(claimed_ids)) == 10  # Zero duplicate claims!

    finally:
        # Clean up synthetic records from PostgreSQL
        try:
            with mgr.session_scope() as session:
                from sqlalchemy import text
                session.execute(
                    text("DELETE FROM recovery_outbox WHERE merchant_id = :mid"),
                    {"mid": synthetic_merchant},
                )
        except Exception as cleanup_err:
            logger.warning(f"Failed to clean up synthetic test data: {cleanup_err}")
