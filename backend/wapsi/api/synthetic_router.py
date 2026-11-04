"""
FastAPI Router for Synthetic Data Lab & Integration Health Telemetry.
Razorpay AI Buildathon 2026 - Track 3

Provides endpoints for:
1. /api/v1/integrations/health - Deep live health probe across all integrated services
2. /api/v1/synthetic/jobs/generate-skeleton - Deterministic 10,000-row Monte Carlo skeleton job
3. /api/v1/synthetic/jobs/{id}/enrich - Dual-Agent LLM narrative enrichment
4. /api/v1/synthetic/jobs/{id}/status - Real-time progress and telemetry
5. /api/v1/synthetic/jobs/{id}/preview - Enriched dataset pagination preview
6. /api/v1/synthetic/jobs/{id}/download - CSV / JSON dataset download
7. /api/v1/synthetic/jobs/{id}/cancel - Safe job cancellation
8. /api/v1/synthetic/datasets - Available datasets and manifests
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.integrations.razorpay.client import RazorpayAuthError, RazorpayClient
from wapsi.llm.router import get_llm_router
from wapsi.simulation.hybrid_synthetic import (
    DeterministicSkeletonGenerator,
    SyntheticJobManager,
    SyntheticJobRecord,
    get_synthetic_job_manager,
)

logger = logging.getLogger("wapsi.api.synthetic")

router = APIRouter(tags=["Synthetic Data Lab & Integrations"])


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class SkeletonJobRequest(BaseModel):
    seed: int = Field(default=42, description="Reproducible simulation random seed")
    total_rows: int = Field(default=10000, ge=10, le=50000, description="Target mathematical skeleton row count")


class EnrichmentJobRequest(BaseModel):
    sample_rows: int = Field(default=50, ge=1, le=10000, description="Number of rows to enrich with LLM narratives")
    preferred_provider: Optional[str] = Field(default=None, description="Preferred provider: groq, gemini, ollama, or deterministic_fallback")
    skeleton_dataset_id: Optional[str] = Field(default=None, description="Dataset ID to enrich")


# ==============================================================================
# Integration Health Telemetry
# ==============================================================================
@router.get("/integrations/health")
def get_integrations_health() -> Dict[str, Any]:
    """
    Performs live verification of all external dependencies and returns exact health statuses:
    - FastAPI
    - Supabase / PostgreSQL
    - Razorpay (Test Mode)
    - Meta WhatsApp Cloud API
    - LLM Providers (Groq, Gemini, Ollama, Fallback)
    """
    settings = get_settings()
    llm_router = get_llm_router()
    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.wapsi_env,
        "services": {},
    }

    # 1. FastAPI Gateway
    results["services"]["fastapi"] = {
        "name": "FastAPI Causal Gateway",
        "status": "connected",
        "mode": settings.wapsi_env,
        "version": "1.0.0",
        "message": "Gateway operational with fail-closed security enforcement.",
        "port": settings.port or 8000,
    }

    # 2. Supabase / PostgreSQL
    try:
        db_mgr = DatabaseManager()
        ping_res = db_mgr.ping()
        role_info = db_mgr.check_runtime_role()
        is_conn = ping_res.get("connected", False)
        results["services"]["supabase"] = {
            "name": "Supabase PostgreSQL (ap-south-1)",
            "status": "connected" if is_conn else "temporarily_unavailable",
            "dialect": ping_res.get("dialect", "unknown"),
            "latency_ms": ping_res.get("latency_ms"),
            "mode": "live_hosted" if ping_res.get("dialect") == "postgresql" else "local_fallback",
            "role": role_info.get("role"),
            "is_restricted_role": role_info.get("is_restricted", False),
            "message": "Connected to hosted Supabase PostgreSQL cluster." if is_conn else ping_res.get("error"),
        }
    except Exception as e:
        results["services"]["supabase"] = {
            "name": "Supabase PostgreSQL (ap-south-1)",
            "status": "temporarily_unavailable",
            "message": f"Database ping exception: {type(e).__name__}",
        }

    # 3. Razorpay Payment Gateway
    if not settings.razorpay_key_id:
        results["services"]["razorpay"] = {
            "name": "Razorpay Payment Gateway",
            "status": "not_configured",
            "mode": settings.razorpay_mode,
            "message": "RAZORPAY_KEY_ID not configured.",
        }
    else:
        rzp_client = RazorpayClient()
        try:
            # Safe read-only probe
            rzp_client._request_sync("GET", "/payment_links", params={"count": 1})
            results["services"]["razorpay"] = {
                "name": "Razorpay Payment Gateway",
                "status": "connected",
                "mode": settings.razorpay_mode,
                "masked_key_id": settings.masked_key_id,
                "message": f"Connected to Razorpay API in {settings.razorpay_mode} mode.",
            }
        except RazorpayAuthError as auth_err:
            results["services"]["razorpay"] = {
                "name": "Razorpay Payment Gateway",
                "status": "authentication_failed",
                "mode": settings.razorpay_mode,
                "masked_key_id": settings.masked_key_id,
                "affected_variable": "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET",
                "message": f"Authentication failed (HTTP {auth_err.status_code}). Key credentials rejected by api.razorpay.com.",
            }
        except Exception as e:
            results["services"]["razorpay"] = {
                "name": "Razorpay Payment Gateway",
                "status": "temporarily_unavailable",
                "mode": settings.razorpay_mode,
                "masked_key_id": settings.masked_key_id,
                "message": f"Network error communicating with Razorpay: {type(e).__name__}",
            }

    # 4. Meta WhatsApp Cloud API
    wa_token = settings.get_whatsapp_token_str()
    phone_id = settings.whatsapp_phone_number_id
    waba_id = settings.whatsapp_business_account_id
    api_ver = settings.whatsapp_api_version or "v26.0"

    if not wa_token or not phone_id:
        results["services"]["whatsapp"] = {
            "name": "Meta WhatsApp Cloud API",
            "status": "not_configured",
            "auth_mode": settings.whatsapp_auth_mode,
            "message": "WhatsApp credentials not fully configured in environment.",
        }
    else:
        try:
            probe_url = f"https://graph.facebook.com/{api_ver}/{phone_id}"
            with httpx.Client(timeout=4.0) as client:
                res = client.get(probe_url, headers={"Authorization": f"Bearer {wa_token}"})
                if res.is_success:
                    results["services"]["whatsapp"] = {
                        "name": "Meta WhatsApp Cloud API",
                        "status": "connected",
                        "phone_number_id": phone_id,
                        "waba_id": waba_id,
                        "api_version": api_ver,
                        "auth_mode": settings.whatsapp_auth_mode,
                        "message": "Connected to Meta Graph API gateway.",
                    }
                elif res.status_code == 401 or res.status_code == 403:
                    err_msg = res.json().get("error", {}).get("message", "Token expired or unauthorized.")
                    results["services"]["whatsapp"] = {
                        "name": "Meta WhatsApp Cloud API",
                        "status": "authentication_failed",
                        "phone_number_id": phone_id,
                        "waba_id": waba_id,
                        "api_version": api_ver,
                        "auth_mode": settings.whatsapp_auth_mode,
                        "affected_variable": "WHATSAPP_ACCESS_TOKEN",
                        "message": f"Meta Graph API authentication failed (HTTP {res.status_code}): {err_msg}",
                        "template_status": "external_approval_pending",
                    }
                else:
                    results["services"]["whatsapp"] = {
                        "name": "Meta WhatsApp Cloud API",
                        "status": "temporarily_unavailable",
                        "message": f"Meta Graph API error (HTTP {res.status_code}).",
                    }
        except Exception as e:
            results["services"]["whatsapp"] = {
                "name": "Meta WhatsApp Cloud API",
                "status": "temporarily_unavailable",
                "message": f"Network error contacting Meta Graph API: {type(e).__name__}",
            }

    # 5. LLM Providers
    llm_health = llm_router.check_providers_health()
    results["services"]["llm_providers"] = {
        "name": "Hybrid AI Narrative Providers",
        "providers": llm_health,
        "default_active_pipeline": (
            "groq" if llm_health.get("groq", {}).get("status") == "connected" else (
                "gemini" if llm_health.get("gemini", {}).get("status") == "connected" else (
                    "ollama" if llm_health.get("ollama", {}).get("status") == "connected" else "deterministic_fallback"
                )
            )
        ),
    }

    return results


# ==============================================================================
# Synthetic Lab API Endpoints
# ==============================================================================
@router.post("/synthetic/jobs/generate-skeleton")
def start_skeleton_generation(payload: SkeletonJobRequest = Body(...)) -> Dict[str, Any]:
    """
    Initiates asynchronous generation of exactly `total_rows` (default 10,000)
    mathematical skeleton transaction rows using the deterministic Monte Carlo simulator.
    """
    job_mgr = get_synthetic_job_manager()
    record = job_mgr.create_skeleton_job(seed=payload.seed, total_rows=payload.total_rows)
    job_mgr.run_skeleton_job_async(record.job_id)

    return {
        "status": "initiated",
        "job_id": record.job_id,
        "job_type": record.job_type,
        "seed": record.seed,
        "total_rows": record.total_rows,
        "message": f"Deterministic skeleton generation started for {payload.total_rows} rows with seed={payload.seed}.",
    }


@router.post("/synthetic/jobs/{job_id}/enrich")
def start_narrative_enrichment(
    job_id: str,
    payload: EnrichmentJobRequest = Body(...),
) -> Dict[str, Any]:
    """
    Initiates Agent A (Narrative Generator) -> Agent B (Narrative Critic) -> Deterministic Validator
    enrichment on an existing completed skeleton dataset.
    Explicit operator action: NEVER triggered automatically on startup.
    """
    job_mgr = get_synthetic_job_manager()
    source_job = job_mgr.get_job(job_id)

    # Locate skeleton file
    skeleton_file = None
    if source_job and source_job.skeleton_file and os.path.exists(source_job.skeleton_file):
        skeleton_file = source_job.skeleton_file
    else:
        # Check standard default skeleton
        default_skel = Path(".wapsi_data/synthetic_datasets/wapsi_skeleton_42_10000.jsonl")
        if default_skel.exists():
            skeleton_file = str(default_skel.resolve())

    if not skeleton_file or not os.path.exists(skeleton_file):
        raise HTTPException(
            status_code=400,
            detail=f"Mathematical skeleton file not found. Generate the 10,000 skeleton first.",
        )

    enrich_job = job_mgr.create_enrichment_job(
        skeleton_dataset_id=job_id,
        sample_rows=payload.sample_rows,
        provider=payload.preferred_provider,
    )
    job_mgr.run_enrichment_job_async(
        job_id=enrich_job.job_id,
        skeleton_file=skeleton_file,
        limit_rows=payload.sample_rows,
        preferred_provider=payload.preferred_provider,
    )

    return {
        "status": "initiated",
        "job_id": enrich_job.job_id,
        "job_type": enrich_job.job_type,
        "sample_rows": payload.sample_rows,
        "preferred_provider": payload.preferred_provider or "auto_fallback",
        "message": f"Narrative enrichment pipeline started for {payload.sample_rows} rows.",
    }


@router.get("/synthetic/jobs/{job_id}/status")
def get_synthetic_job_status(job_id: str) -> Dict[str, Any]:
    """Returns real-time progress, retry counts, fallbacks, and completion status."""
    job_mgr = get_synthetic_job_manager()
    record = job_mgr.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    progress_pct = 0.0
    if record.total_rows > 0:
        progress_pct = round((record.rows_processed / record.total_rows) * 100, 1)

    return {
        "job_id": record.job_id,
        "job_type": record.job_type,
        "status": record.status,
        "seed": record.seed,
        "total_rows": record.total_rows,
        "rows_processed": record.rows_processed,
        "progress_percent": progress_pct,
        "retries_count": record.retries_count,
        "fallbacks_count": record.fallbacks_count,
        "provider": record.provider,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "error": record.error,
        "has_enriched_file": bool(record.enriched_file and os.path.exists(record.enriched_file)),
        "has_skeleton_file": bool(record.skeleton_file and os.path.exists(record.skeleton_file)),
    }


@router.post("/synthetic/jobs/{job_id}/cancel")
def cancel_synthetic_job(job_id: str) -> Dict[str, Any]:
    """Safely cancels an in-flight generation or enrichment job."""
    job_mgr = get_synthetic_job_manager()
    cancelled = job_mgr.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return {"status": "cancelled", "job_id": job_id}


@router.get("/synthetic/jobs/{job_id}/preview")
def get_dataset_preview(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    """Returns paginated preview of enriched or skeleton rows."""
    job_mgr = get_synthetic_job_manager()
    record = job_mgr.get_job(job_id)

    target_file = None
    if record and record.enriched_file and os.path.exists(record.enriched_file):
        target_file = record.enriched_file
    elif record and record.skeleton_file and os.path.exists(record.skeleton_file):
        target_file = record.skeleton_file
    else:
        # Fallback to standard 10,000 skeleton if exists
        default_skel = Path(".wapsi_data/synthetic_datasets/wapsi_skeleton_42_10000.jsonl")
        if default_skel.exists():
            target_file = str(default_skel.resolve())

    if not target_file or not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="Dataset file not found.")

    records = []
    total_count = 0
    with open(target_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            total_count += 1
            if offset <= idx < offset + limit:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    return {
        "job_id": job_id,
        "offset": offset,
        "limit": limit,
        "total_records": total_count,
        "records": records,
    }


@router.get("/synthetic/jobs/{job_id}/download")
def download_synthetic_dataset(
    job_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
):
    """Streams dataset download as JSON or CSV."""
    job_mgr = get_synthetic_job_manager()
    record = job_mgr.get_job(job_id)

    target_file = None
    if record and record.enriched_file and os.path.exists(record.enriched_file):
        target_file = record.enriched_file
    elif record and record.skeleton_file and os.path.exists(record.skeleton_file):
        target_file = record.skeleton_file
    else:
        default_skel = Path(".wapsi_data/synthetic_datasets/wapsi_skeleton_42_10000.jsonl")
        if default_skel.exists():
            target_file = str(default_skel.resolve())

    if not target_file or not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="Dataset file not found.")

    if format == "json":
        def iter_json():
            yield "[\n"
            first = True
            with open(target_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not first:
                        yield ",\n"
                    yield line.strip()
                    first = False
            yield "\n]"

        return StreamingResponse(
            iter_json(),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=wapsi_synthetic_{job_id}.json"},
        )
    else:
        # CSV Streaming
        def iter_csv():
            output = io.StringIO()
            writer = None
            with open(target_file, "r", encoding="utf-8") as f:
                for line in f:
                    row = json.loads(line)
                    # Flatten list fields for CSV
                    if isinstance(row.get("narrative_tags"), list):
                        row["narrative_tags"] = "|".join(row["narrative_tags"])
                    if writer is None:
                        writer = csv.DictWriter(output, fieldnames=list(row.keys()))
                        writer.writeheader()
                    writer.writerow(row)
                    yield output.getvalue()
                    output.seek(0)
                    output.truncate(0)

        return StreamingResponse(
            iter_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=wapsi_synthetic_{job_id}.csv"},
        )


@router.get("/synthetic/datasets")
def list_synthetic_datasets() -> Dict[str, Any]:
    """Lists all available synthetic datasets and their cryptographic manifests."""
    data_dir = Path(".wapsi_data/synthetic_datasets")
    manifests = []
    if data_dir.exists():
        for mf in data_dir.glob("*_manifest.json"):
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    manifests.append(json.load(f))
            except Exception:
                pass

    job_mgr = get_synthetic_job_manager()
    jobs = [asdict(j) for j in job_mgr.list_jobs()]

    return {
        "manifests": manifests,
        "jobs": jobs,
        "count": len(manifests),
    }
