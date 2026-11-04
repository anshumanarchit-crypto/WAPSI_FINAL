"""
WAPSI Hybrid Monte Carlo + LLM Synthetic Data Generation Architecture.
Razorpay AI Buildathon 2026 - Track 3

Core Architectural Principle:
- Procedural Monte Carlo simulation creates the mathematical ground truth.
- LLM enriches that ground truth with realistic synthetic narratives.
- THE LLM NEVER GENERATES, ESTIMATES, MODIFIES, OR OVERWRITES THE MATHEMATICAL SKELETON.
- Deterministic programmatic Python validation acts as the authoritative safety layer.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.data_generator import RecoveryDataConfig, WapsiDataGenerator
from wapsi.core.config import get_settings
from wapsi.llm.router import LLMProviderRouter, LLMResponse, get_llm_router

logger = logging.getLogger("wapsi.simulation.hybrid")


# ==============================================================================
# Immutable Mathematical Constants & Field Definitions
# ==============================================================================
MATHEMATICAL_IMMUTABLE_FIELDS = [
    "case_id",
    "merchant_id",
    "customer_id",
    "domain",
    "amount",
    "amount_paise",
    "amount_display",
    "decline_reason",
    "failure_code",
    "attempts_used",
    "account_age_days",
    "previous_failures",
    "previous_recoveries",
    "prior_recovery_rate",
    "day_of_week",
    "hour",
    "issuer",
    "bin_bucket",
    "fatigue_score",
    "treatment",
    "recovered",
    "outcome",
    "time_to_recovery_hours",
    "is_synthetic",
    "dataset_version",
    "simulation_seed",
]

NARRATIVE_FIELDS = [
    "company_name",
    "contact_person",
    "failure_backstory",
    "hinglish_whatsapp_message",
    "narrative_tags",
    "synthetic",
]


# ==============================================================================
# Step 1 — Deterministic Mathematical Skeleton Generator
# ==============================================================================
class DeterministicSkeletonGenerator:
    """
    Extends the existing WAPSI Monte Carlo procedural simulator to generate exactly
    10,000 synthetic transaction rows with bounded batching, streaming disk persistence,
    and cryptographic SHA-256 dataset provenance.
    """

    def __init__(
        self,
        seed: int = 42,
        output_dir: str = ".wapsi_data/synthetic_datasets",
        chunk_size: int = 1000,
    ):
        self.seed = seed
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size

    def generate_skeleton(
        self,
        total_rows: int = 10000,
        timestamp: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[Path, Path, Dict[str, Any]]:
        """
        Generates exactly `total_rows` mathematically sound synthetic rows using bounded batches.
        Does NOT invoke any LLM.
        Returns:
            (skeleton_jsonl_path, manifest_json_path, manifest_dict)
        """
        logger.info(f"Starting deterministic skeleton generation: {total_rows} rows, seed={self.seed}")
        timestamp_str = timestamp or datetime.now(timezone.utc).isoformat()
        dataset_id = f"wapsi_skeleton_{self.seed}_{total_rows}"
        skeleton_file = self.output_dir / f"{dataset_id}.jsonl"
        manifest_file = self.output_dir / f"{dataset_id}_manifest.json"

        # Temporary write file for atomic rename
        temp_file = self.output_dir / f"{dataset_id}.tmp"

        sha256 = hashlib.sha256()
        rows_written = 0

        # Deterministic generator instance with configured seed
        config = RecoveryDataConfig(
            n_samples=total_rows,
            random_seed=self.seed,
            export_parquet=False,
            export_csv=False,
        )
        generator = WapsiDataGenerator(config=config)

        # Generate in memory-efficient chunks if requested or single batch
        # Note: 10,000 tabular rows in pandas is ~5MB RAM, but we stream line by line to JSONL
        df_observed, df_ground_truth = generator.generate(n_samples=total_rows)

        with open(temp_file, "w", encoding="utf-8") as f:
            for idx, row in df_observed.iterrows():
                amt = float(row["amount"])
                amt_paise = int(round(amt * 100))
                amt_display = f"₹{amt:,.2f}"
                rec_val = int(row["recovered"])
                outcome_str = "recovered" if rec_val == 1 else "failed"
                fail_code = str(row["decline_reason"])

                record: Dict[str, Any] = {
                    "case_id": str(row["case_id"]),
                    "merchant_id": str(row["merchant_id"]),
                    "customer_id": str(row["customer_id"]),
                    "domain": str(row["domain"]),
                    "amount": amt,
                    "amount_paise": amt_paise,
                    "amount_display": amt_display,
                    "decline_reason": fail_code,
                    "failure_code": fail_code,
                    "attempts_used": int(row["attempts_used"]),
                    "account_age_days": int(row["account_age_days"]),
                    "previous_failures": int(row["previous_failures"]),
                    "previous_recoveries": int(row["previous_recoveries"]),
                    "prior_recovery_rate": float(row["prior_recovery_rate"]),
                    "day_of_week": int(row["day_of_week"]),
                    "hour": int(row["hour"]),
                    "issuer": str(row["issuer"]),
                    "bin_bucket": str(row["bin_bucket"]),
                    "fatigue_score": float(row["fatigue_score"]),
                    "treatment": str(row["treatment"]),
                    "recovered": rec_val,
                    "outcome": outcome_str,
                    "time_to_recovery_hours": float(row["time_to_recovery_hours"]) if not pd.isna(row["time_to_recovery_hours"]) else None,
                    "is_synthetic": True,
                    "dataset_version": "v1.0-synthetic",
                    "simulation_seed": self.seed,
                    "generation_timestamp": timestamp_str,
                    "narrative_status": "skeleton_only",
                }

                line = json.dumps(record) + "\n"
                f.write(line)
                sha256.update(line.encode("utf-8"))
                rows_written += 1

                if progress_callback and rows_written % 1000 == 0:
                    progress_callback(rows_written, total_rows)

        # Atomic replacement
        if skeleton_file.exists():
            skeleton_file.unlink()
        temp_file.rename(skeleton_file)

        checksum = sha256.hexdigest()

        manifest: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "total_rows": rows_written,
            "seed": self.seed,
            "created_at": timestamp_str,
            "sha256_checksum": checksum,
            "skeleton_file": str(skeleton_file.resolve()),
            "immutable_fields": MATHEMATICAL_IMMUTABLE_FIELDS,
            "status": "skeleton_complete",
            "schema_version": "1.0.0",
        }

        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        if progress_callback:
            progress_callback(rows_written, total_rows)

        logger.info(f"Deterministic skeleton complete: {rows_written} rows. Checksum: {checksum[:16]}")
        return skeleton_file, manifest_file, manifest


# ==============================================================================
# Step 2 — Narrative Generator (Agent A)
# ==============================================================================
class NarrativeGenerator:
    """
    Agent A: The creative narrative engine.
    Enriches mathematically valid simulator rows with realistic synthetic business narratives.
    STRICT RULE: The LLM must NEVER generate, calculate, or alter mathematical fields.
    """

    SYSTEM_PROMPT = """You are a realistic synthetic B2B/B2C payment narrative generator.
You receive one mathematically generated transaction row from a deterministic payment simulation engine.
Your responsibility is to enrich the row with a realistic but entirely synthetic business narrative.

STRICT RULES:
1. Never change transaction amounts.
2. Never change failure codes.
3. Never change treatment assignments.
4. Never change recovery outcomes.
5. Never calculate financial values.
6. Never invent treatment probabilities.
7. Never change potential outcomes.
8. Never claim that a failed transaction was recovered when the supplied outcome says failed.
9. Never claim that a recovered transaction failed.
10. Never change the meaning of the original transaction.
11. Never invent a real person's identity.
12. Never create real customer PII.
13. Never output real phone numbers, credentials, bank details, or payment identifiers.

Generate only these narrative fields:
- company_name: Plausible synthetic company name.
- contact_person: Plausible synthetic point-of-contact name.
- failure_backstory: Exactly two sentences explaining the fictional business context of the payment failure.
- hinglish_whatsapp_message: A natural Hinglish WhatsApp recovery message. If transaction amount is included, copy the supplied formatted amount exactly.
- narrative_tags: List of strings (e.g. failure category, domain tag).
- synthetic: true

Output strictly valid JSON matching this schema:
{
  "company_name": "string",
  "contact_person": "string",
  "failure_backstory": "string",
  "hinglish_whatsapp_message": "string",
  "narrative_tags": ["string"],
  "synthetic": true
}"""

    def __init__(self, router: Optional[LLMProviderRouter] = None):
        self.router = router or get_llm_router()

    def generate_narrative(
        self,
        math_row: Dict[str, Any],
        critic_error_feedback: Optional[str] = None,
        preferred_provider: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], LLMResponse]:
        """
        Invokes Agent A to generate narrative fields for a single mathematical row.
        Attaches critic feedback on retry attempts.
        """
        input_payload = {
            "case_id": math_row.get("case_id"),
            "amount_paise": math_row.get("amount_paise"),
            "amount_display": math_row.get("amount_display"),
            "failure_code": math_row.get("failure_code") or math_row.get("decline_reason"),
            "domain": math_row.get("domain"),
            "treatment": math_row.get("treatment"),
            "outcome": math_row.get("outcome"),
            "hour": math_row.get("hour"),
        }

        user_content = f"Mathematical Transaction Row:\n{json.dumps(input_payload, indent=2)}"
        if critic_error_feedback:
            user_content += f"\n\nCRITICAL FIX REQUIRED (PREVIOUS ATTEMPT REJECTED):\n{critic_error_feedback}\nCorrect this error immediately while strictly maintaining all mathematical fields."

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        llm_resp = self.router.generate_chat_completion(
            messages=messages,
            preferred_provider=preferred_provider,
            row_context=math_row,
        )

        parsed = llm_resp.parsed_json or {}
        return parsed, llm_resp


# ==============================================================================
# Step 3 — Narrative Critic (Agent B)
# ==============================================================================
class NarrativeCritic:
    """
    Agent B: Strict anti-hallucination and narrative consistency reviewer.
    Compares original mathematical transaction data with Agent A's proposed narrative.
    """

    SYSTEM_PROMPT = """You are a strict synthetic transaction narrative validator.
Compare the original mathematical transaction data with the proposed synthetic narrative.

Check whether the narrative:
- Contradicts the supplied failure code.
- Contradicts the treatment.
- Claims recovery when the transaction outcome is failed.
- Claims failure when the transaction outcome is recovered.
- Changes the original amount.
- Introduces inconsistent financial amounts.
- Describes a recovery action unrelated to the specified treatment.
- Introduces real personal or financial information.
- Contains a backstory inconsistent with the supplied transaction.

Do not invent new transaction data.
Do not modify the original simulator row.

Return strictly valid JSON:
{
  "status": "pass",
  "error": null
}
or:
{
  "status": "fail",
  "error": "Specific explanation of the inconsistency"
}"""

    def __init__(self, router: Optional[LLMProviderRouter] = None):
        self.router = router or get_llm_router()

    def evaluate_narrative(
        self,
        math_row: Dict[str, Any],
        proposed_narrative: Dict[str, Any],
        preferred_provider: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], LLMResponse]:
        """
        Agent B checks proposed narrative against the mathematical row.
        Returns: (is_passed: bool, error_message: Optional[str], llm_resp)
        """
        user_content = (
            f"1. Original Mathematical Row:\n{json.dumps(math_row, indent=2)}\n\n"
            f"2. Agent A Proposed Narrative:\n{json.dumps(proposed_narrative, indent=2)}"
        )

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        llm_resp = self.router.generate_chat_completion(
            messages=messages,
            preferred_provider=preferred_provider,
            row_context=math_row,
        )

        parsed = llm_resp.parsed_json or {}
        status = str(parsed.get("status", "pass")).lower()
        error = parsed.get("error")

        if status == "pass" and not error:
            return True, None, llm_resp
        return False, str(error or "Critic flagged narrative inconsistency"), llm_resp


# ==============================================================================
# Step 4 — Deterministic Python Validator & Orchestration Loop
# ==============================================================================
class DeterministicPythonValidator:
    """
    Authoritative safety layer.
    Performs rigorous deterministic validation on Agent A outputs before acceptance.
    """

    @classmethod
    def validate(
        cls,
        math_row: Dict[str, Any],
        proposed_narrative: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates schema integrity, outcome consistency, amount copying, and backstory structure.
        """
        if not isinstance(proposed_narrative, dict):
            return False, "Proposed narrative is not a valid JSON dictionary."

        # 1. Required keys
        required_keys = ["company_name", "contact_person", "failure_backstory", "hinglish_whatsapp_message"]
        for k in required_keys:
            val = proposed_narrative.get(k)
            if not val or not str(val).strip():
                return False, f"Missing required narrative field: '{k}'"

        # 2. Strict synthetic tag
        if not proposed_narrative.get("synthetic"):
            return False, "Narrative must have 'synthetic': true"

        # 3. Two-sentence backstory check
        backstory = str(proposed_narrative.get("failure_backstory", "")).strip()
        # Split on sentence boundary (period, exclamation, or question mark followed by whitespace or end of string, not within numbers)
        sentences = [s.strip() for s in re.split(r"(?<!\d)[\.!\?](?:\s+|$)", backstory) if len(s.strip()) > 3]
        if len(sentences) != 2:
            return False, f"failure_backstory must contain exactly two sentences (found {len(sentences)})."

        # 4. Strict Outcome Consistency Check
        outcome = str(math_row.get("outcome", "")).lower()
        rec_val = math_row.get("recovered")
        msg = str(proposed_narrative.get("hinglish_whatsapp_message", "")).lower()

        if outcome == "failed" or rec_val == 0:
            forbidden_words = ["payment successful", "payment received", "transaction successful", "paise mil gaye", "safalta"]
            for w in forbidden_words:
                if w in msg:
                    return False, f"Contradiction: Transaction failed, but message claims success ('{w}')."

        # 5. Amount exact match check: if any currency amount appears in Hinglish message, it must match
        amt_disp = math_row.get("amount_display", "")
        amt_raw = str(int(math_row.get("amount", 0)))
        # Search for rupee symbols or numbers
        if "₹" in msg and amt_disp.lower() not in msg.lower():
            # Check if digits at least match
            if amt_raw not in msg:
                return False, f"Amount discrepancy: Message contains mismatched amount (expected {amt_disp})."

        # 6. Basic PII safeguard (no real phone numbers like +91 98xxx, no email addresses)
        raw_text = f"{proposed_narrative.get('contact_person', '')} {proposed_narrative.get('hinglish_whatsapp_message', '')}"
        if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", raw_text):
            return False, "PII violation: Real email address pattern detected in synthetic narrative."
        if re.search(r"\b(?:\+91|91)?[6-9]\d{9}\b", raw_text):
            return False, "PII violation: Real 10-digit phone number pattern detected in synthetic narrative."

        return True, None


class HybridEnrichmentOrchestrator:
    """
    Coordinates Agent A -> Agent B -> Deterministic Python Validator with max 3 attempts
    and deterministic fallback.
    """

    MAX_ATTEMPTS = 3

    def __init__(
        self,
        router: Optional[LLMProviderRouter] = None,
        agent_a: Optional[NarrativeGenerator] = None,
        agent_b: Optional[NarrativeCritic] = None,
    ):
        self.router = router or get_llm_router()
        self.agent_a = agent_a or NarrativeGenerator(router=self.router)
        self.agent_b = agent_b or NarrativeCritic(router=self.router)
        self.validator = DeterministicPythonValidator()

    def enrich_single_row(
        self,
        math_row: Dict[str, Any],
        preferred_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the controlled orchestration loop for a single mathematical row:
        1. Agent A generates proposed narrative.
        2. Agent B critic checks narrative.
        3. Deterministic Python validator checks rules.
        4. If rejected, retries Agent A up to 3 total attempts.
        5. If all fail, applies deterministic fallback narrative.
        6. Combines: Immutable Mathematical Row + Validated Narrative Fields.
        """
        # Strictly preserve original mathematical row
        original_math = copy.deepcopy(math_row)

        attempts = 0
        critic_error = None
        final_narrative: Optional[Dict[str, Any]] = None
        narrative_status = "fallback"
        provider_used = "deterministic_fallback"
        model_used = "wapsi-fallback-v1"
        critic_status = "unverified"
        last_failure_reason = None

        while attempts < self.MAX_ATTEMPTS:
            attempts += 1
            proposed, llm_resp_a = self.agent_a.generate_narrative(
                math_row=original_math,
                critic_error_feedback=critic_error,
                preferred_provider=preferred_provider,
            )
            provider_used = llm_resp_a.provider
            model_used = llm_resp_a.model

            # Step B: Critic validation
            critic_pass, critic_err_msg, llm_resp_b = self.agent_b.evaluate_narrative(
                math_row=original_math,
                proposed_narrative=proposed,
                preferred_provider=preferred_provider,
            )

            if not critic_pass:
                critic_error = critic_err_msg
                last_failure_reason = f"Critic rejection (attempt {attempts}): {critic_err_msg}"
                critic_status = "failed_retried"
                logger.warning(f"Row {original_math.get('case_id')} {last_failure_reason}")
                continue

            # Step C: Deterministic programmatic validator
            is_valid, val_err = self.validator.validate(original_math, proposed)
            if not is_valid:
                critic_error = f"Deterministic safety check failed: {val_err}"
                last_failure_reason = f"Validator rejection (attempt {attempts}): {val_err}"
                critic_status = "failed_retried"
                logger.warning(f"Row {original_math.get('case_id')} {last_failure_reason}")
                continue

            # If both pass
            final_narrative = proposed
            narrative_status = "enriched"
            critic_status = "passed"
            break

        # Fallback if exhausted attempts
        if final_narrative is None:
            logger.info(f"Row {original_math.get('case_id')} exhausted {self.MAX_ATTEMPTS} attempts. Using fallback.")
            fb_resp = self.router._generate_deterministic_fallback(
                messages=[],
                row_context=original_math,
                error_reason=last_failure_reason,
            )
            final_narrative = fb_resp.parsed_json or {}
            narrative_status = "fallback"
            provider_used = "deterministic_fallback"
            model_used = "wapsi-fallback-v1"

        # Combine Original Math Row + Validated Narrative
        combined = copy.deepcopy(original_math)
        for k in NARRATIVE_FIELDS:
            combined[k] = final_narrative.get(k)

        # Attach metadata
        combined["narrative_status"] = narrative_status
        combined["narrative_provider"] = provider_used
        combined["narrative_model"] = model_used
        combined["critic_status"] = critic_status
        combined["enrichment_attempts"] = attempts
        combined["validation_error"] = last_failure_reason if narrative_status == "fallback" else None

        # Verify mathematical immutability assertion
        for field_name in MATHEMATICAL_IMMUTABLE_FIELDS:
            if field_name in original_math:
                assert combined[field_name] == original_math[field_name], (
                    f"FATAL INVARIANT VIOLATION: Mathematical field '{field_name}' "
                    f"mutated from {original_math[field_name]} to {combined[field_name]}!"
                )

        return combined


# ==============================================================================
# Step 5 — Synthetic Dataset Job Manager (Background Lifecycle)
# ==============================================================================
@dataclass
class SyntheticJobRecord:
    job_id: str
    job_type: str  # 'skeleton' or 'enrichment'
    status: str    # 'pending', 'running', 'completed', 'failed', 'cancelled'
    seed: int
    total_rows: int
    rows_processed: int = 0
    retries_count: int = 0
    fallbacks_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    skeleton_file: Optional[str] = None
    enriched_file: Optional[str] = None
    manifest_file: Optional[str] = None
    error: Optional[str] = None
    provider: Optional[str] = None


class SyntheticJobManager:
    """
    Manages background execution of skeleton generation and narrative enrichment.
    Maintains persistent status and enforces single active worker execution.
    """

    def __init__(self, data_dir: str = ".wapsi_data/synthetic_datasets"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.data_dir / "jobs_registry.json"
        self._jobs: Dict[str, SyntheticJobRecord] = self._load_jobs()
        self._lock = threading.Lock()
        self._cancel_flags: Dict[str, bool] = {}

    def _load_jobs(self) -> Dict[str, SyntheticJobRecord]:
        if not self.jobs_file.exists():
            return {}
        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: SyntheticJobRecord(**v) for k, v in data.items()}
        except Exception:
            return {}

    def _save_jobs(self):
        try:
            with open(self.jobs_file, "w", encoding="utf-8") as f:
                json.dump({k: asdict(v) for k, v in self._jobs.items()}, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist jobs registry: {e}")

    def create_skeleton_job(self, seed: int = 42, total_rows: int = 10000) -> SyntheticJobRecord:
        job_id = f"job_skel_{uuid.uuid4().hex[:8]}"
        record = SyntheticJobRecord(
            job_id=job_id,
            job_type="skeleton",
            status="pending",
            seed=seed,
            total_rows=total_rows,
        )
        with self._lock:
            self._jobs[job_id] = record
            self._save_jobs()
        return record

    def run_skeleton_job_async(self, job_id: str) -> None:
        """Starts skeleton generation in a daemon thread."""
        thread = threading.Thread(target=self._execute_skeleton_job, args=(job_id,), daemon=True)
        thread.start()

    def _execute_skeleton_job(self, job_id: str):
        record = self._jobs.get(job_id)
        if not record:
            return

        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_jobs()

        generator = DeterministicSkeletonGenerator(seed=record.seed, output_dir=str(self.data_dir))

        def on_progress(done: int, total: int):
            record.rows_processed = done
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_jobs()

        try:
            skel_file, man_file, manifest = generator.generate_skeleton(
                total_rows=record.total_rows,
                progress_callback=on_progress,
            )
            record.skeleton_file = str(skel_file.resolve())
            record.manifest_file = str(man_file.resolve())
            record.status = "completed"
            record.rows_processed = record.total_rows
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_jobs()
            logger.info(f"Skeleton job {job_id} successfully completed.")
        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_jobs()
            logger.error(f"Skeleton job {job_id} failed: {e}")

    def create_enrichment_job(
        self,
        skeleton_dataset_id: str,
        sample_rows: int = 50,
        provider: Optional[str] = None,
    ) -> SyntheticJobRecord:
        job_id = f"job_enrich_{uuid.uuid4().hex[:8]}"
        record = SyntheticJobRecord(
            job_id=job_id,
            job_type="enrichment",
            status="pending",
            seed=42,
            total_rows=sample_rows,
            provider=provider or "groq",
        )
        with self._lock:
            self._jobs[job_id] = record
            self._save_jobs()
        return record

    def run_enrichment_job_async(
        self,
        job_id: str,
        skeleton_file: str,
        limit_rows: int = 50,
        preferred_provider: Optional[str] = None,
    ) -> None:
        thread = threading.Thread(
            target=self._execute_enrichment_job,
            args=(job_id, skeleton_file, limit_rows, preferred_provider),
            daemon=True,
        )
        thread.start()

    def _execute_enrichment_job(
        self,
        job_id: str,
        skeleton_file: str,
        limit_rows: int,
        preferred_provider: Optional[str],
    ):
        record = self._jobs.get(job_id)
        if not record:
            return

        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_jobs()

        orchestrator = HybridEnrichmentOrchestrator()
        enriched_file = self.data_dir / f"enriched_{job_id}.jsonl"

        rows_done = 0
        retries = 0
        fallbacks = 0

        try:
            with open(skeleton_file, "r", encoding="utf-8") as f_in, open(enriched_file, "w", encoding="utf-8") as f_out:
                for line in f_in:
                    if self._cancel_flags.get(job_id, False):
                        record.status = "cancelled"
                        record.updated_at = datetime.now(timezone.utc).isoformat()
                        self._save_jobs()
                        return

                    if rows_done >= limit_rows:
                        break

                    math_row = json.loads(line)
                    enriched_row = orchestrator.enrich_single_row(
                        math_row=math_row,
                        preferred_provider=preferred_provider,
                    )

                    if enriched_row.get("enrichment_attempts", 1) > 1:
                        retries += (enriched_row["enrichment_attempts"] - 1)
                    if enriched_row.get("narrative_status") == "fallback":
                        fallbacks += 1

                    f_out.write(json.dumps(enriched_row) + "\n")
                    rows_done += 1

                    record.rows_processed = rows_done
                    record.retries_count = retries
                    record.fallbacks_count = fallbacks
                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    self._save_jobs()

            record.status = "completed"
            record.enriched_file = str(enriched_file.resolve())
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_jobs()
            logger.info(f"Enrichment job {job_id} finished successfully: {rows_done} rows enriched.")
        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_jobs()
            logger.error(f"Enrichment job {job_id} failed: {e}")

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            self._cancel_flags[job_id] = True
            self._jobs[job_id].status = "cancelled"
            self._save_jobs()
            return True
        return False

    def get_job(self, job_id: str) -> Optional[SyntheticJobRecord]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[SyntheticJobRecord]:
        return list(self._jobs.values())


_job_manager_instance: Optional[SyntheticJobManager] = None


def get_synthetic_job_manager() -> SyntheticJobManager:
    global _job_manager_instance
    if _job_manager_instance is None:
        _job_manager_instance = SyntheticJobManager()
    return _job_manager_instance
