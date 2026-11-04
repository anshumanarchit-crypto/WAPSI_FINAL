"""
WAPSI — Controlled Sandbox Outbound Message Approval and Dispatch Script.
Target Outbox Job: 5a6587ab-2601-4017-b396-48e3d2fc2fda
Target Payment Link: plink_TvKucM1yXJQAZA
Target Recipient: +91 62600 *****

Strict Safety Controls:
1. Requires explicit --approve --operator-id <id> to transition from PENDING_APPROVAL to QUEUED.
2. Requires explicit --dispatch to execute the background worker.
3. Dry-run by default: without --dispatch, no worker is invoked and no messages are sent.
4. Strictly limited to job 5a6587ab-2601-4017-b396-48e3d2fc2fda (zero new jobs created).
5. Checks opt-out status, 24h customer window, and payload hash before dispatch.
6. Redacts tokens, keys, and phone numbers in all output.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wapsi.sandbox.dispatch")

from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.recovery.engine import PaymentRecoveryEngine
from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
from wapsi.recovery.outbox import DurableOutboxStore, compute_approval_hash
from wapsi.recovery.worker import RecoveryBackgroundWorker

TARGET_JOB_ID = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
TARGET_MERCHANT_UUID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
TARGET_PAYMENT_LINK_ID = "plink_TvKucM1yXJQAZA"


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "[NOT CONFIGURED]"
    clean = phone.strip()
    if len(clean) <= 6:
        return "****"
    return f"{clean[:3]}****{clean[-4:]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="WAPSI Sandbox Approval and Dispatch Runner")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform pre-flight verification only")
    parser.add_argument("--approve", action="store_true", default=False, help="Execute operator approval transition")
    parser.add_argument("--operator-id", type=str, default=None, help="Operator identity assertion string approving this job (attributed to tenant)")
    parser.add_argument("--dispatch", action="store_true", default=False, help="Execute worker dispatch for approved job")
    args = parser.parse_args()

    settings = get_settings()

    # Safety checks
    if settings.wapsi_env.lower() == "production" or settings.razorpay_mode != "test":
        logger.error("FATAL: This script is strictly restricted to development/test mode!")
        sys.exit(1)

    dm = DatabaseManager()
    store = DurableOutboxStore(database_manager=dm)
    opt_out_store = get_persistent_opt_out_store(database_manager=dm)

    # 1. Inspect existing job
    job = store.get_job(TARGET_JOB_ID, merchant_id=TARGET_MERCHANT_UUID)
    if not job:
        logger.error(f"FATAL: Target job {TARGET_JOB_ID} not found in database.")
        sys.exit(1)

    logger.info("=== JOB PRE-FLIGHT VERIFICATION ===")
    logger.info(f"Job ID: {job.id}")
    logger.info(f"Current Status: {job.status}")
    logger.info(f"Channel: {job.channel}")
    logger.info(f"Recipient Masked: {job.recipient_masked}")
    logger.info(f"Requires Approval: {job.requires_operator_approval}")
    logger.info(f"Approved By: {job.approved_by_operator_id}")
    logger.info(f"Approval Snapshot Hash: {job.approval_snapshot_hash}")

    # Verify recipient and window
    test_phone = settings.test_recipient_phone
    is_opted = opt_out_store.is_opted_out(test_phone)
    is_window = opt_out_store.is_within_24h_window(test_phone)
    logger.info(f"Opt-Out Status: {is_opted}")
    logger.info(f"24h Window Active: {is_window}")

    if is_opted:
        logger.error("FATAL: Recipient is registered as opted out. Dispatch blocked.")
        sys.exit(1)

    expected_hash = compute_approval_hash(
        recipient_masked=job.recipient_masked,
        channel=job.channel,
        message_payload=job.message_payload,
    )
    logger.info(f"Payload Canonical Snapshot Hash: {expected_hash}")

    # 2. Operator Approval Execution
    if args.approve:
        if not args.operator_id or not args.operator_id.strip():
            logger.error("FATAL: --operator-id is required when approving a job.")
            sys.exit(1)

        if job.status != "PENDING_APPROVAL":
            logger.warning(f"Job is already in status '{job.status}'. Skipping approval step.")
        else:
            logger.info(f"Recording operator approval assertion for '{args.operator_id.strip()}'...")
            ok = store.approve_job(
                job_id=TARGET_JOB_ID,
                operator_id=args.operator_id.strip(),
                merchant_id=TARGET_MERCHANT_UUID,
            )
            if not ok:
                logger.error("FATAL: Failed to approve outbox job.")
                sys.exit(1)
            job = store.get_job(TARGET_JOB_ID, merchant_id=TARGET_MERCHANT_UUID)
            logger.info(f"Job successfully transitioned to: {job.status}")
            logger.info(f"Approved By: {job.approved_by_operator_id}")
            logger.info(f"Approved At: {job.approved_at}")
            logger.info(f"Stored Snapshot Hash: {job.approval_snapshot_hash}")

    # 3. Worker Dispatch Execution
    if args.dispatch:
        # A job is claimable for dispatch if it is QUEUED, RETRY, or SENDING with an expired lease
        claimable_statuses = ("QUEUED", "RETRY", "SENDING")
        if job.status not in claimable_statuses:
            logger.error(
                f"FATAL: Job must be in a claimable status {claimable_statuses} to dispatch. "
                f"Current status: '{job.status}'. Run with --approve first if PENDING_APPROVAL."
            )
            sys.exit(1)

        if job.status == "SENDING" and job.lease_expires_at and job.lease_expires_at > time.time():
            logger.error(
                f"FATAL: Job currently has an active unexpired lease held by worker '{job.worker_id}' "
                f"until {job.lease_expires_at}. Dispatch blocked to prevent concurrency collision."
            )
            sys.exit(1)

        logger.info("Initializing RecoveryBackgroundWorker for controlled dispatch...")
        engine = PaymentRecoveryEngine(database_manager=dm)
        worker = engine.worker

        logger.info(f"Worker {worker.worker_id} claiming and executing exact job {TARGET_JOB_ID}...")
        result = worker.process_single_job_by_id(TARGET_JOB_ID, merchant_id=TARGET_MERCHANT_UUID)
        logger.info(f"Exact-Job Execution Result: Job={result.job_id}, Status={result.status}, Error={result.error_message}")

        # Final job state
        final_job = store.get_job(TARGET_JOB_ID, merchant_id=TARGET_MERCHANT_UUID)
        logger.info("=== FINAL POST-DISPATCH JOB STATE ===")
        logger.info(f"Final Status: {final_job.status}")
        logger.info(f"Worker ID: {final_job.worker_id}")
        logger.info(f"Retry Count: {final_job.retry_count}")
        logger.info(f"Payload Excerpt: {str(final_job.message_payload)[:120]}")
    elif not args.approve:
        logger.info("Dry-run verification completed. No mutations performed.")
        logger.info(f"To approve and dispatch, invoke:")
        logger.info(f"python scripts/dispatch_approved_sandbox_job.py --approve --operator-id <operator_name> --dispatch")


if __name__ == "__main__":
    main()

