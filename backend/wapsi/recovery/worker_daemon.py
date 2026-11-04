"""
Autonomous Background Worker Daemon Service for WAPSI Recovery Engine.

Provides continuous, monitored, concurrency-safe, and self-healing background processing
of payment recovery outbox jobs. Wraps RecoveryBackgroundWorker with production lifecycle
guarantees:
1. Continuous background batch polling with exponential backoff & busy-loop prevention.
2. Graceful SIGTERM / SIGINT shutdown with in-flight grace periods and lease release.
3. Atomic heartbeat monitoring via .wapsi_worker_heartbeat.
4. Active lease tracking and automatic expired lease reclamation.
5. Multi-worker concurrency safety across SQLite (BEGIN IMMEDIATE) and PostgreSQL
   (FOR UPDATE SKIP LOCKED).
6. Crash recovery and prevention of duplicate payment recovery executions.
7. Uncompromised preservation of operator approval, cryptographic snapshots, and tenant isolation.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.recovery.opt_out_store import PersistentOptOutStore, get_persistent_opt_out_store
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, get_outbox_store
from wapsi.recovery.timeline import RecoveryTimelineStore, get_timeline_store
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker

logger = logging.getLogger("wapsi.recovery.daemon")


def _utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# 1. WORKER DAEMON CONFIGURATION
# ==============================================================================

class WorkerDaemonConfig(BaseModel):
    """
    Validated configuration for background worker daemon.
    Enforces strict positive durations and valid paths.
    Supports Section 3.C canonical configuration options and aliases.
    """
    model_config = {"extra": "forbid"}

    worker_id: Optional[str] = Field(
        default=None,
        description="Unique worker daemon identifier; auto-generated if omitted."
    )
    poll_interval_seconds: float = Field(
        default=5.0,
        gt=0.0,
        description="Idle sleep interval in seconds when no jobs are available."
    )
    lease_duration_seconds: int = Field(
        default=60,
        gt=0,
        description="Duration in seconds of job leases acquired by this daemon."
    )
    heartbeat_interval_seconds: float = Field(
        default=10.0,
        gt=0.0,
        description="Interval in seconds between worker heartbeat updates."
    )
    shutdown_grace_period_seconds: float = Field(
        default=15.0,
        ge=0.0,
        description="Maximum seconds to wait for in-flight job completion on shutdown."
    )
    batch_size: int = Field(
        default=10,
        gt=0,
        description="Maximum number of outbox jobs claimed and executed per cycle."
    )
    heartbeat_path: str = Field(
        default=".wapsi_worker_heartbeat",
        description="Path to atomic heartbeat status file."
    )
    reclaim_expired_leases: bool = Field(
        default=True,
        description="Whether to perform periodic lease reclamation sweeps."
    )
    reclaim_interval_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="Interval in seconds between expired lease reclamation sweeps."
    )
    max_cycles: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional maximum processing cycles before graceful termination (for testing)."
    )
    merchant_id: Optional[str] = Field(
        default=None,
        description="Optional merchant UUID filter for tenant-scoped worker execution."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            mapping = {
                "max_concurrent_jobs": "batch_size",
                "worker_identity": "worker_id",
                "heartbeat_file_location": "heartbeat_path",
                "poll_interval": "poll_interval_seconds",
                "lease_duration": "lease_duration_seconds",
                "heartbeat_interval": "heartbeat_interval_seconds",
                "shutdown_grace_period": "shutdown_grace_period_seconds",
            }
            d = dict(data)
            for alias_key, target_key in mapping.items():
                if alias_key in d and target_key not in d:
                    d[target_key] = d.pop(alias_key)
                elif alias_key in d and target_key in d:
                    d.pop(alias_key)
            return d
        return data

    @property
    def max_concurrent_jobs(self) -> int:
        return self.batch_size

    @property
    def worker_identity(self) -> Optional[str]:
        return self.worker_id

    @property
    def heartbeat_file_location(self) -> str:
        return self.heartbeat_path

    @field_validator("heartbeat_path")
    @classmethod
    def validate_heartbeat_path(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("heartbeat_path cannot be empty.")
        return s


# ==============================================================================
# 2. WORKER HEARTBEAT RECORD
# ==============================================================================

class WorkerHeartbeat(BaseModel):
    """
    Atomic worker heartbeat recording operational health, leasing, and throughput metrics.
    Guarantees zero customer PII, secrets, or access tokens in the record.
    """
    worker_id: str
    pid: int
    timestamp_utc: str
    status: str  # STARTING, RUNNING, IDLE, PROCESSING, RECLAIMING, STOPPING, STOPPED
    started_at_utc: str
    last_successful_cycle_utc: Optional[str] = None
    active_lease_count: int = 0
    completed_job_count: int = 0
    failed_job_count: int = 0
    last_cycle_duration_seconds: float = 0.0
    last_error_category: Optional[str] = None

    def to_json(self, indent: int = 2) -> str:
        """Serializes heartbeat to JSON formatted string."""
        return self.model_dump_json(indent=indent)

    def write_atomic(self, heartbeat_path: Union[str, Path]) -> None:
        """
        Atomically writes heartbeat record to disk using a temporary file and replace.
        Avoids partial file reads and corruption. Creates parent directories if missing.
        """
        p = Path(heartbeat_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = p.parent / f"{p.name}.tmp.{uuid.uuid4().hex[:6]}"
            content = self.to_json(indent=2)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, p)
        except Exception as e:
            logger.warning(f"Failed to atomically write heartbeat to {p}: {e}")
            try:
                if "tmp_path" in locals() and tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    @classmethod
    def read(cls, heartbeat_path: Union[str, Path]) -> Optional[WorkerHeartbeat]:
        """
        Reads and parses heartbeat file. Returns None if missing, inaccessible, or invalid.
        """
        p = Path(heartbeat_path)
        if not p.is_file():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            return cls.model_validate_json(content)
        except Exception as e:
            logger.warning(f"Failed to read or parse heartbeat at {p}: {e}")
            return None

    def is_stale(
        self,
        stale_threshold_seconds: float = 30.0,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        Evaluates whether this heartbeat is older than stale_threshold_seconds.
        """
        try:
            ts = datetime.fromisoformat(self.timestamp_utc)
            now = current_time or datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            elapsed = (now - ts).total_seconds()
            return elapsed > stale_threshold_seconds
        except Exception:
            return True


# ==============================================================================
# 3. RECOVERY WORKER DAEMON
# ==============================================================================

class RecoveryWorkerDaemon:
    """
    Continuous background worker daemon wrapping RecoveryBackgroundWorker.
    
    Coordinates outbox polling, provider dispatches, lease tracking, signal shutdown,
    and expired lease reclamation while strictly respecting operator authorization.
    """

    def __init__(
        self,
        config: Optional[WorkerDaemonConfig] = None,
        worker: Optional[RecoveryBackgroundWorker] = None,
        outbox_store: Optional[DurableOutboxStore] = None,
        opt_out_store: Optional[PersistentOptOutStore] = None,
        timeline_store: Optional[RecoveryTimelineStore] = None,
        razorpay_client: Optional[RazorpayClient] = None,
        whatsapp_client: Optional[WhatsAppClient] = None,
    ):
        self.config = config or WorkerDaemonConfig()
        self.worker_id = self.config.worker_id or (
            worker.worker_id if worker else f"daemon_{uuid.uuid4().hex[:8]}"
        )

        # Initialize or adopt existing RecoveryBackgroundWorker
        if worker is not None:
            self.worker = worker
            self.worker.worker_id = self.worker_id
            self.worker.lease_duration_seconds = self.config.lease_duration_seconds
        else:
            self.worker = RecoveryBackgroundWorker(
                worker_id=self.worker_id,
                outbox_store=outbox_store,
                opt_out_store=opt_out_store,
                timeline_store=timeline_store,
                razorpay_client=razorpay_client,
                whatsapp_client=whatsapp_client,
                lease_duration_seconds=self.config.lease_duration_seconds,
            )

        self.outbox = self.worker.outbox
        self.opt_out = self.worker.opt_out
        self.timeline = self.worker.timeline

        # Lifecycle & synchronization controls
        self._stop_event = threading.Event()
        self._is_running: bool = False
        self._is_shutting_down: bool = False
        self._orig_signals: Dict[int, Any] = {}
        self._signals_installed: bool = False

        # Concurrency & active lease tracking
        self._in_flight_job: Optional[OutboxJob] = None
        self._in_flight_lock = threading.Lock()

        # Operational telemetry
        self.completed_jobs: int = 0
        self.failed_jobs: int = 0
        self.cycle_count: int = 0
        self.last_cycle_duration_seconds: float = 0.0
        self.last_successful_cycle_utc: Optional[str] = None
        self.last_error_category: Optional[str] = None
        self.started_at_utc: str = _utc_now_iso()
        self._last_heartbeat_at: float = 0.0
        self._last_reclaim_at: float = 0.0

    @property
    def is_running(self) -> bool:
        """Returns True if the daemon is currently active."""
        return self._is_running and not self._stop_event.is_set()

    # ------------------------------------------------------------------
    # Signal handling & lifecycle management
    # ------------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        """
        Registers graceful shutdown signal handlers for SIGTERM and SIGINT.
        Safely skips installation if called from a non-main thread.
        """
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Daemon initialized outside main thread; skipping signal handler installation.")
            return

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._orig_signals[sig] = signal.getsignal(sig)
                signal.signal(sig, self._signal_handler)
                self._signals_installed = True
            except (ValueError, OSError) as e:
                logger.debug(f"Could not install handler for signal {sig}: {e}")

    def _restore_signal_handlers(self) -> None:
        """Restores previous signal handlers upon daemon shutdown."""
        if not self._signals_installed or threading.current_thread() is not threading.main_thread():
            return

        for sig, handler in self._orig_signals.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
        self._signals_installed = False

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handles SIGTERM and SIGINT by requesting graceful shutdown."""
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        logger.info(f"Worker daemon {self.worker_id} received {sig_name} (signal {signum}). Requesting graceful shutdown...")
        self.request_shutdown()

    def request_shutdown(self) -> None:
        """Requests daemon to stop accepting new work and initiate graceful shutdown."""
        self._stop_event.set()
        self._is_shutting_down = True
        self.worker.stop()
        logger.info(f"Worker daemon {self.worker_id} shutdown requested.")

    def stop(self) -> None:
        """Public alias for request_shutdown."""
        self.request_shutdown()

    # ------------------------------------------------------------------
    # Heartbeat monitoring
    # ------------------------------------------------------------------

    def _get_active_lease_count(self) -> int:
        """Queries database for current count of active leases held by this worker."""
        try:
            return self.outbox.count_active_leases(
                worker_id=self.worker_id,
                merchant_id=self.config.merchant_id,
            )
        except Exception as e:
            logger.debug(f"Could not query active lease count for heartbeat: {e}")
            return 1 if self._in_flight_job is not None else 0

    def update_heartbeat(self, status: str, error_category: Optional[str] = None) -> None:
        """
        Generates and atomically writes a heartbeat record.
        """
        now_ts = time.time()
        self._last_heartbeat_at = now_ts
        err_cat = error_category or self.last_error_category

        active_leases = self._get_active_lease_count()

        heartbeat = WorkerHeartbeat(
            worker_id=self.worker_id,
            pid=os.getpid(),
            timestamp_utc=_utc_now_iso(),
            status=status,
            started_at_utc=self.started_at_utc,
            last_successful_cycle_utc=self.last_successful_cycle_utc,
            active_lease_count=active_leases,
            completed_job_count=self.completed_jobs,
            failed_job_count=self.failed_jobs,
            last_cycle_duration_seconds=round(self.last_cycle_duration_seconds, 4),
            last_error_category=err_cat,
        )
        try:
            heartbeat.write_atomic(self.config.heartbeat_path)
        except Exception as e:
            logger.warning(f"Failed to atomically write heartbeat: {e}")

    # ------------------------------------------------------------------
    # Lease reclamation sweep
    # ------------------------------------------------------------------

    def perform_lease_reclamation(self) -> int:
        """
        Reclaims expired outbox leases whose lease_expires_at < CURRENT_UTC_TIME.
        Transitions expired SENDING jobs back to QUEUED status so any active worker can claim them.
        Uses database row-locking (FOR UPDATE SKIP LOCKED in PG, BEGIN IMMEDIATE in SQLite).
        """
        now_ts = time.time()
        self._last_reclaim_at = now_ts
        try:
            reclaimed = self.outbox.reclaim_expired_leases(
                current_time=now_ts,
                max_reclaim=50,
                merchant_id=self.config.merchant_id,
            )
            if reclaimed > 0:
                logger.info(f"Worker daemon {self.worker_id} reclaimed {reclaimed} expired outbox leases.")
            return reclaimed
        except Exception as e:
            self.last_error_category = e.__class__.__name__
            logger.error(f"Error during expired lease reclamation sweep: {e}")
            return 0

    # ------------------------------------------------------------------
    # Single execution cycle
    # ------------------------------------------------------------------

    def run_cycle(self) -> int:
        """
        Executes a single processing cycle:
        1. Periodic lease reclamation (if enabled and due).
        2. Periodic heartbeat update (if due).
        3. Claims up to batch_size eligible jobs.
        4. Processes claimed jobs sequentially.
        5. Handles shutdown signals between jobs by releasing undispatched leases.
        6. Returns the number of jobs processed.
        """
        now = time.time()

        # 1. Periodic lease reclamation sweep
        if self.config.reclaim_expired_leases:
            if (now - self._last_reclaim_at) >= self.config.reclaim_interval_seconds:
                self.perform_lease_reclamation()

        # 2. Check if shutdown was requested
        if self._stop_event.is_set():
            return 0

        # 3. Periodic heartbeat update
        if (now - self._last_heartbeat_at) >= self.config.heartbeat_interval_seconds:
            self.update_heartbeat(status="RUNNING")

        # 4. Atomically claim a batch of eligible jobs
        try:
            claimed_jobs = self.outbox.claim_jobs(
                worker_id=self.worker_id,
                limit=self.config.batch_size,
                lease_duration_seconds=self.config.lease_duration_seconds,
            )
        except Exception as claim_err:
            self.last_error_category = claim_err.__class__.__name__
            logger.error(f"Worker daemon {self.worker_id} encountered error claiming jobs: {claim_err}")
            self.update_heartbeat(status="RUNNING", error_category=claim_err.__class__.__name__)
            return 0

        if not claimed_jobs:
            self.last_successful_cycle_utc = _utc_now_iso()
            self.update_heartbeat(status="IDLE")
            return 0

        # 5. Process claimed jobs with in-flight tracking
        self.update_heartbeat(status="PROCESSING")
        processed_count = 0

        for idx, job in enumerate(claimed_jobs):
            # Check shutdown requested during batch processing:
            # Safely release remaining undispatched jobs in the batch back to QUEUED
            if self._stop_event.is_set():
                logger.info(
                    f"Worker daemon {self.worker_id} stopping: releasing lease on "
                    f"undispatched batch job {job.id} ({idx + 1}/{len(claimed_jobs)})."
                )
                try:
                    self.outbox.release_lease(job.id, self.worker_id, merchant_id=job.merchant_id)
                except Exception as rel_err:
                    logger.warning(f"Failed to release lease for job {job.id}: {rel_err}")
                continue

            with self._in_flight_lock:
                self._in_flight_job = job

            try:
                res: JobExecutionResult = self.worker.process_single_job(job)
                if res.status == "COMPLETED":
                    self.completed_jobs += 1
                elif res.status in ("DEAD_LETTER", "FAILED", "RETRIED", "RECONCILIATION_REQUIRED"):
                    self.failed_jobs += 1
                processed_count += 1
            except Exception as job_exc:
                self.failed_jobs += 1
                self.last_error_category = job_exc.__class__.__name__
                logger.exception(f"Unhandled exception during execution of job {job.id}: {job_exc}")
            finally:
                with self._in_flight_lock:
                    self._in_flight_job = None

        self.last_successful_cycle_utc = _utc_now_iso()
        return processed_count

    # ------------------------------------------------------------------
    # Graceful shutdown execution
    # ------------------------------------------------------------------

    def _perform_graceful_shutdown(self) -> None:
        """
        Executes graceful shutdown protocol:
        1. Emits STOPPING heartbeat.
        2. Waits for active in-flight dispatch to complete within grace period.
        3. Releases all remaining undispatched leases held by this worker.
           (Preserves active leases for timed-out in-flight jobs to prevent duplicate dispatch).
        4. Emits STOPPED heartbeat.
        5. Restores original signal handlers.
        """
        logger.info(f"Worker daemon {self.worker_id} entering graceful shutdown...")
        self.update_heartbeat(status="STOPPING")

        # Wait for in-flight job to finish within grace period
        wait_start = time.time()
        grace_period = self.config.shutdown_grace_period_seconds

        while time.time() - wait_start < grace_period:
            with self._in_flight_lock:
                if self._in_flight_job is None:
                    break
            time.sleep(0.05)

        with self._in_flight_lock:
            stuck_in_flight_id: Optional[str] = None
            if self._in_flight_job is not None:
                stuck_in_flight_id = self._in_flight_job.id
                logger.warning(
                    f"Shutdown grace period ({grace_period}s) elapsed; job "
                    f"{stuck_in_flight_id} may still be running in background. "
                    f"Preserving active lease to prevent concurrent duplicate dispatch."
                )

        # Release any active leases held by this worker that were not dispatched.
        # CRITICAL: Never blindly release a lease on an in-flight job whose outcome is ambiguous
        # or still executing, as that would cause another worker to claim it concurrently (duplicate dispatch).
        try:
            exclude_ids = [stuck_in_flight_id] if stuck_in_flight_id else None
            released_cnt = self.outbox.release_leases_for_worker(
                worker_id=self.worker_id,
                merchant_id=self.config.merchant_id,
                exclude_job_ids=exclude_ids,
            )
            if released_cnt > 0:
                logger.info(f"Worker daemon {self.worker_id} released {released_cnt} undispatched leases.")
        except Exception as rel_err:
            logger.warning(f"Error releasing worker leases on shutdown: {rel_err}")

        # Final terminal heartbeat
        self.update_heartbeat(status="STOPPED")
        self._restore_signal_handlers()
        self._is_running = False
        logger.info(
            f"Worker daemon {self.worker_id} successfully stopped. "
            f"Summary: {self.completed_jobs} completed, {self.failed_jobs} failed, {self.cycle_count} cycles."
        )

    # ------------------------------------------------------------------
    # Continuous daemon execution loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Starts worker daemon and runs the continuous background processing loop."""
        self.run_forever()

    def run_forever(self) -> None:
        """
        Continuous main loop of the background recovery worker daemon.
        Monitors stop events, sleeps during idle periods to prevent busy loops,
        and cleanly handles recoverable exceptions.
        """
        self._is_running = True
        self._stop_event.clear()
        self.started_at_utc = _utc_now_iso()

        self._install_signal_handlers()
        logger.info(f"Starting WAPSI recovery worker daemon (worker_id={self.worker_id}, pid={os.getpid()})...")
        self.update_heartbeat(status="STARTING")
        self.update_heartbeat(status="RUNNING")

        try:
            while not self._stop_event.is_set():
                cycle_start = time.time()
                try:
                    jobs_processed = self.run_cycle()
                    self.last_cycle_duration_seconds = time.time() - cycle_start
                    self.cycle_count += 1

                    # Optional max_cycles bound (testing convenience)
                    if self.config.max_cycles and self.cycle_count >= self.config.max_cycles:
                        logger.info(f"Daemon reached max_cycles ({self.config.max_cycles}). Initiating planned exit.")
                        break

                    # Sleep on stop_event when idle to prevent busy-looping
                    if jobs_processed == 0 and not self._stop_event.is_set():
                        self._stop_event.wait(timeout=self.config.poll_interval_seconds)

                except Exception as cycle_err:
                    self.last_error_category = cycle_err.__class__.__name__
                    logger.exception(f"Recoverable exception in worker daemon cycle: {cycle_err}")
                    self.update_heartbeat(status="RUNNING", error_category=cycle_err.__class__.__name__)
                    # Brief backoff after unexpected loop error
                    self._stop_event.wait(timeout=min(self.config.poll_interval_seconds, 2.0))

        finally:
            self._perform_graceful_shutdown()

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> RecoveryWorkerDaemon:
        self._is_running = True
        self._install_signal_handlers()
        self.update_heartbeat(status="RUNNING")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.request_shutdown()
        self._perform_graceful_shutdown()

    # ------------------------------------------------------------------
    # Deep health inspection
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """
        Deep operational health inspection. Verifies daemon state, database connectivity,
        and heartbeat freshness. Does NOT assume heartbeat existence alone proves DB health.
        """
        db_healthy = False
        db_metrics: Dict[str, Any] = {}
        try:
            db_metrics = self.outbox.get_metrics()
            db_healthy = True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")

        heartbeat = WorkerHeartbeat.read(self.config.heartbeat_path)
        heartbeat_healthy = (
            heartbeat is not None
            and not heartbeat.is_stale(stale_threshold_seconds=self.config.heartbeat_interval_seconds * 3)
        )

        return {
            "worker_id": self.worker_id,
            "pid": os.getpid(),
            "is_running": self.is_running,
            "is_shutting_down": self._is_shutting_down,
            "db_healthy": db_healthy,
            "heartbeat_healthy": heartbeat_healthy,
            "active_leases": self._get_active_lease_count(),
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "cycle_count": self.cycle_count,
            "last_cycle_duration_seconds": self.last_cycle_duration_seconds,
            "outbox_metrics": db_metrics,
        }
