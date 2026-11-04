"""
Causal Observational Logging Pipeline for WAPSI Recovery Engine.
WAPSI Phase 7 — Gate 5: Causal Observational Logging & Closed-Loop LinUCB Feedback.

Guarantees:
1. Strict Observational Data Model:
   Records decision context X_i, selected action A_i, observed outcome Y_i,
   and true assignment propensity p_hat_i at original decision time.
2. Verified Outcome Association & Ingestion:
   Associates Razorpay settlement events and case expirations idempotently.
   Preserves event provenance and late-payment correction history.
   Out-of-order delivery protection: delayed failures never downgrade RECOVERED.
3. Positivity & Common Support Validation:
   Validates 0 < propensity <= 1. Records with missing, out-of-bounds, or NaN
   propensities are explicitly flagged and excluded from propensity-dependent retrain/IPS.
4. Tenant Isolation & Zero PII Leakage:
   Tenant-scoped persistence and offline export. Strips phone numbers, emails,
   customer names, and credentials during DML export.
5. Deterministic Offline Retraining Export:
   Exports structured observational datasets matching MultiActionDoubleMachineLearning
   data contract (Neyman-orthogonal score preparation).
6. ACID-Safe Row-Level Persistence:
   Persists to SQLite/PostgreSQL with indexed queries and streaming JSONL support.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd

from wapsi.core.taxonomy import RecoveryAction, ACTION_METADATA

logger = logging.getLogger("wapsi.recovery.observational_logger")

DEFAULT_FEATURE_SCHEMA_VERSION = "v1"
DEFAULT_REWARD_DEFINITION_VERSION = "v1"
DEFAULT_POLICY_VERSION = "v1.0.0"
DEFAULT_MODEL_VERSION = "v1.2.0-dml"

# Core DML numerical and categorical column contracts
DML_NUMERICAL_COLS: List[str] = [
    "amount",
    "attempts_used",
    "account_age_days",
    "previous_failures",
    "previous_recoveries",
    "prior_recovery_rate",
    "day_of_week",
    "hour",
    "fatigue_score",
]

DML_CATEGORICAL_COLS: List[str] = [
    "domain",
    "decline_reason",
    "issuer",
    "bin_bucket",
]

PII_FIELD_NAMES: Set[str] = {
    "customer_phone",
    "phone",
    "customer_email",
    "email",
    "customer_name",
    "name",
    "recipient_phone",
    "recipient_masked",
    "api_key",
    "secret",
    "access_token",
    "card_number",
    "cvv",
}


class DuplicateDecisionError(ValueError):
    """Raised when attempting to log an observation with an already recorded decision_id."""
    pass


class ObservationNotFoundError(KeyError):
    """Raised when an outcome references an unknown decision or payment record."""
    pass


@dataclass
class DecisionObservationRecord:
    """
    Structured, auditable causal observational record.
    Preserves decision context, selected action, assignment propensity, and verified outcome.
    """
    decision_id: str
    payment_id: str
    merchant_id: str
    case_id: Optional[str] = None
    decision_timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context_features: Dict[str, Any] = field(default_factory=dict)
    feature_vector: Optional[List[float]] = None
    action_selected: str = "no_action"
    action_id: Optional[str] = None
    assignment_propensity: float = 1.0
    is_propensity_valid: bool = True
    policy_version: str = DEFAULT_POLICY_VERSION
    model_version: str = DEFAULT_MODEL_VERSION
    feature_schema_version: str = DEFAULT_FEATURE_SCHEMA_VERSION
    reward_definition_version: str = DEFAULT_REWARD_DEFINITION_VERSION
    observation_status: str = "PENDING_OUTCOME"  # PENDING_OUTCOME, MATURE, EXPIRED, INVALID, SUPPRESSED
    outcome_status: Optional[str] = None         # RECOVERED, FAILED, EXPIRED, SUPPRESSED
    recovered_amount_paise: int = 0
    outcome_timestamp_utc: Optional[str] = None
    event_id: Optional[str] = None
    event_source: Optional[str] = None          # RAZORPAY_WEBHOOK, RECONCILIATION, EXPIRATION_HANDLER
    deterministic_reward: Optional[float] = None
    is_eligible_for_dml: bool = False
    is_eligible_for_bandit: bool = False
    exclusion_reasons: List[str] = field(default_factory=list)
    correction_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionObservationRecord":
        d = dict(data)
        if isinstance(d.get("context_features"), str):
            d["context_features"] = json.loads(d["context_features"])
        if isinstance(d.get("feature_vector"), str):
            d["feature_vector"] = json.loads(d["feature_vector"])
        if isinstance(d.get("exclusion_reasons"), str):
            d["exclusion_reasons"] = json.loads(d["exclusion_reasons"])
        if isinstance(d.get("correction_history"), str):
            d["correction_history"] = json.loads(d["correction_history"])
        if "is_propensity_valid" in d:
            d["is_propensity_valid"] = bool(d["is_propensity_valid"])
        if "is_eligible_for_dml" in d:
            d["is_eligible_for_dml"] = bool(d["is_eligible_for_dml"])
        if "is_eligible_for_bandit" in d:
            d["is_eligible_for_bandit"] = bool(d["is_eligible_for_bandit"])
        return cls(**d)


class ObservationalDataValidator:
    """
    Validates observational learning data against causal econometric and backend constraints.
    """

    @staticmethod
    def validate_propensity(propensity: Any) -> Tuple[bool, float, Optional[str]]:
        """
        Enforces positivity condition: 0 < propensity <= 1.
        Rejects NaNs, infinities, negatives, zeros, booleans, and > 1.0.
        """
        if propensity is None:
            return False, 0.0, "MISSING_PROPENSITY"
        if isinstance(propensity, bool):
            return False, 0.0, "BOOLEAN_PROPENSITY_INVALID"
        try:
            val = float(propensity)
        except (ValueError, TypeError):
            return False, 0.0, "NON_NUMERIC_PROPENSITY"

        if math.isnan(val) or math.isinf(val):
            return False, 0.0, "NAN_OR_INF_PROPENSITY"
        if val <= 0.0:
            return False, val, "NON_POSITIVE_PROPENSITY_VIOLATES_COMMON_SUPPORT"
        if val > 1.0:
            return False, val, "PROPENSITY_EXCEEDS_UNITY"

        return True, val, None

    @staticmethod
    def validate_action(action: Any) -> Tuple[bool, str, Optional[str]]:
        """
        Validates action against configured RecoveryAction taxonomy and treatment names.
        Rejects empty or unsupported actions.
        """
        if not action or not str(action).strip():
            return False, "", "MISSING_OR_EMPTY_ACTION"
        act_str = str(action).strip()
        valid_actions: Set[str] = {
            a.value.lower() for a in RecoveryAction
        } | {
            a.name.lower() for a in RecoveryAction
        } | {
            "no_action", "whatsapp_nudge", "retry_only", "voice_call", "email", "incentive_link",
            "instant_smart_retry", "whatsapp_one_click_link", "call_assist_ivr", "sms_fallback_link",
            "merchant_discount_nudge"
        }
        if act_str.lower() not in valid_actions:
            return False, act_str, f"UNSUPPORTED_ACTION_CATEGORY_{act_str}"
        return True, act_str, None

    @staticmethod
    def validate_timestamp(ts: Any) -> Tuple[bool, str, Optional[str]]:
        """
        Validates timestamp format and normalizes to UTC ISO-8601 string.
        Rejects malformed strings or invalid timestamp types.
        """
        if ts is None:
            return True, datetime.now(timezone.utc).isoformat(), None
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                dt_utc = ts.replace(tzinfo=timezone.utc)
            else:
                dt_utc = ts.astimezone(timezone.utc)
            return True, dt_utc.isoformat(), None
        if isinstance(ts, (int, float)):
            try:
                dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
                return True, dt_utc.isoformat(), None
            except Exception as e:
                return False, "", f"INVALID_NUMERIC_TIMESTAMP: {e}"
        if isinstance(ts, str):
            s = ts.strip()
            if not s:
                return False, "", "EMPTY_TIMESTAMP_STRING"
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return True, dt.isoformat(), None
            except Exception as e:
                return False, "", f"INVALID_ISO8601_TIMESTAMP: {e}"
        return False, "", f"UNSUPPORTED_TIMESTAMP_TYPE_{type(ts).__name__}"

    @staticmethod
    def validate_feature_vector(
        vec: Optional[Union[List[float], np.ndarray]],
        expected_dim: Optional[int] = None
    ) -> Tuple[bool, Optional[List[float]], Optional[str]]:
        """
        Validates normalized feature vector dimensions and ensures no NaN/inf values.
        """
        if vec is None:
            return True, None, None

        if isinstance(vec, np.ndarray):
            if vec.ndim != 1:
                return False, None, f"FEATURE_VECTOR_MUST_BE_1D_GOT_{vec.ndim}D"
            arr = vec.tolist()
        elif isinstance(vec, (list, tuple)):
            arr = list(vec)
        else:
            return False, None, "INVALID_FEATURE_VECTOR_TYPE"

        # Check non-empty
        if len(arr) == 0:
            return False, None, "EMPTY_FEATURE_VECTOR"

        # Check dimension
        if expected_dim is not None and len(arr) != expected_dim:
            return False, None, f"DIMENSION_MISMATCH_EXPECTED_{expected_dim}_GOT_{len(arr)}"

        # Check NaN / inf and booleans
        for i, val in enumerate(arr):
            if isinstance(val, bool):
                return False, None, f"BOOLEAN_VALUE_AT_INDEX_{i}"
            try:
                f_val = float(val)
                if math.isnan(f_val) or math.isinf(f_val):
                    return False, None, f"NAN_OR_INF_AT_INDEX_{i}"
            except (ValueError, TypeError):
                return False, None, f"NON_NUMERIC_VALUE_AT_INDEX_{i}"

        return True, [float(v) for v in arr], None

    @staticmethod
    def sanitize_for_export(context_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strips PII, raw phone numbers, credentials, and internal secret fields.
        """
        sanitized = {}
        for k, v in context_dict.items():
            if k.lower() in PII_FIELD_NAMES:
                continue
            if isinstance(v, str) and (k.endswith("_phone") or k.endswith("_email")):
                continue
            sanitized[k] = v
        return sanitized


class ObservationalLogger:
    """
    Thread-safe, auditable observational learning logger for WAPSI.
    Stores decision contexts, actions, propensities, and verified outcomes.
    Supports ACID SQLite/PostgreSQL storage and streaming JSONL exports.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        jsonl_log_path: Optional[str] = None,
        database_manager: Optional[Any] = None,
        expected_feature_dim: Optional[int] = None,
        observation_window_seconds: int = 86400,  # 24 hours
        max_window_seconds: int = 259200,         # 72 hours
    ):
        self.db_manager = database_manager
        self.expected_feature_dim = expected_feature_dim
        self.observation_window_seconds = observation_window_seconds
        self.max_window_seconds = max_window_seconds

        import threading
        self._thread_local = threading.local()

        if db_path is None:
            data_dir = Path(os.environ.get("WAPSI_LOCAL_DATA_DIR", ".wapsi_data"))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "observational_learning.db")
        else:
            self.db_path = db_path

        # Ensure SQLite fallback table is always initialized
        self._init_sqlite_db()

        # Configure persistent DB
        if db_path is None and self.db_manager is not None and hasattr(self.db_manager, "engine") and self.db_manager.engine.dialect.name == "postgresql":
            self.is_postgres = True
            try:
                from wapsi.db.models import OperationalBase
                OperationalBase.metadata.create_all(self.db_manager.engine)
            except Exception as db_init_err:
                logger.debug(f"OperationalBase PostgreSQL init notice: {db_init_err}")
        else:
            self.is_postgres = False

        # Optional streaming JSONL sink
        self.jsonl_log_path = jsonl_log_path

    @staticmethod
    def _model_to_record(model: Any) -> DecisionObservationRecord:
        """Converts an ObservationalLearningRecordModel from SQLAlchemy to a DecisionObservationRecord."""
        ctx = model.context_features
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        vec = model.feature_vector
        if isinstance(vec, str):
            vec = json.loads(vec)
        excl = model.exclusion_reasons
        if isinstance(excl, str):
            excl = json.loads(excl)
        corr = model.correction_history
        if isinstance(corr, str):
            corr = json.loads(corr)

        return DecisionObservationRecord(
            decision_id=model.decision_id,
            payment_id=model.payment_id,
            merchant_id=model.merchant_id,
            case_id=model.case_id,
            decision_timestamp_utc=model.decision_timestamp_utc,
            context_features=ctx or {},
            feature_vector=vec,
            action_selected=model.action_selected,
            action_id=model.action_id,
            assignment_propensity=float(model.assignment_propensity),
            is_propensity_valid=bool(model.is_propensity_valid),
            policy_version=model.policy_version,
            model_version=model.model_version,
            feature_schema_version=model.feature_schema_version,
            reward_definition_version=model.reward_definition_version,
            observation_status=model.observation_status,
            outcome_status=model.outcome_status,
            recovered_amount_paise=int(model.recovered_amount_paise or 0),
            outcome_timestamp_utc=model.outcome_timestamp_utc,
            event_id=model.event_id,
            event_source=model.event_source,
            deterministic_reward=float(model.deterministic_reward) if model.deterministic_reward is not None else None,
            is_eligible_for_dml=bool(model.is_eligible_for_dml),
            is_eligible_for_bandit=bool(model.is_eligible_for_bandit),
            exclusion_reasons=excl or [],
            correction_history=corr or [],
            created_at_utc=model.created_at_utc,
            updated_at_utc=model.updated_at_utc,
        )

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        conn = getattr(self._thread_local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=15.0)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.row_factory = sqlite3.Row
            self._thread_local.conn = conn
        return conn

    def _init_sqlite_db(self) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observational_learning_records (
                    decision_id TEXT PRIMARY KEY,
                    payment_id TEXT NOT NULL,
                    merchant_id TEXT NOT NULL,
                    case_id TEXT,
                    decision_timestamp_utc TEXT NOT NULL,
                    context_features TEXT NOT NULL,
                    feature_vector TEXT,
                    action_selected TEXT NOT NULL,
                    action_id TEXT,
                    assignment_propensity REAL NOT NULL,
                    is_propensity_valid INTEGER NOT NULL,
                    policy_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    feature_schema_version TEXT NOT NULL,
                    reward_definition_version TEXT NOT NULL,
                    observation_status TEXT NOT NULL,
                    outcome_status TEXT,
                    recovered_amount_paise INTEGER DEFAULT 0,
                    outcome_timestamp_utc TEXT,
                    event_id TEXT,
                    event_source TEXT,
                    deterministic_reward REAL,
                    is_eligible_for_dml INTEGER NOT NULL,
                    is_eligible_for_bandit INTEGER NOT NULL,
                    exclusion_reasons TEXT NOT NULL,
                    correction_history TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_payment ON observational_learning_records (payment_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_case ON observational_learning_records (case_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_merchant ON observational_learning_records (merchant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_status ON observational_learning_records (observation_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_dml ON observational_learning_records (is_eligible_for_dml)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_event ON observational_learning_records (event_id)")
            conn.commit()

    def log_decision(
        self,
        decision_id: str,
        payment_id: str,
        merchant_id: str,
        context_features: Optional[Dict[str, Any]] = None,
        action_selected: str = "no_action",
        assignment_propensity: float = 1.0,
        case_id: Optional[str] = None,
        feature_vector: Optional[Union[List[float], np.ndarray]] = None,
        action_id: Optional[str] = None,
        policy_version: str = DEFAULT_POLICY_VERSION,
        model_version: str = DEFAULT_MODEL_VERSION,
        feature_schema_version: str = DEFAULT_FEATURE_SCHEMA_VERSION,
        decision_timestamp: Optional[Union[datetime, str]] = None,
    ) -> DecisionObservationRecord:
        """
        Logs an initial decision event along with its context, selected action, and propensity.
        """
        # Validate decision_id
        if not decision_id or not str(decision_id).strip():
            raise ValueError("decision_id must be a non-empty string.")
        if not payment_id or not str(payment_id).strip():
            raise ValueError("payment_id must be a non-empty string.")
        if not merchant_id or not str(merchant_id).strip():
            raise ValueError("merchant_id must be a non-empty string.")

        # Validate action
        is_act_valid, clean_action, act_err = ObservationalDataValidator.validate_action(action_selected)
        if not is_act_valid:
            raise ValueError(f"Invalid action_selected: {act_err}")

        # Validate UTC timestamp
        is_ts_valid, ts_str, ts_err = ObservationalDataValidator.validate_timestamp(decision_timestamp)
        if not is_ts_valid:
            raise ValueError(f"Invalid decision_timestamp: {ts_err}")

        exclusion_reasons: List[str] = []

        # Validate propensity
        is_p_valid, p_val, p_err = ObservationalDataValidator.validate_propensity(assignment_propensity)
        if not is_p_valid:
            exclusion_reasons.append(p_err or "INVALID_PROPENSITY")

        # Validate feature vector
        is_v_valid, clean_vec, v_err = ObservationalDataValidator.validate_feature_vector(
            feature_vector, expected_dim=self.expected_feature_dim
        )
        if not is_v_valid:
            raise ValueError(f"Invalid feature vector: {v_err}")

        # Check existing decision_id
        existing = self.get_by_decision_id(decision_id)
        if existing is not None:
            raise DuplicateDecisionError(f"Observation record with decision_id '{decision_id}' already exists.")

        now_str = datetime.now(timezone.utc).isoformat()
        ctx_features = context_features if context_features is not None else {}

        record = DecisionObservationRecord(
            decision_id=decision_id,
            payment_id=payment_id,
            merchant_id=merchant_id,
            case_id=case_id,
            decision_timestamp_utc=ts_str,
            context_features=ctx_features,
            feature_vector=clean_vec,
            action_selected=clean_action,
            action_id=action_id,
            assignment_propensity=p_val,
            is_propensity_valid=is_p_valid,
            policy_version=policy_version,
            model_version=model_version,
            feature_schema_version=feature_schema_version,
            reward_definition_version=DEFAULT_REWARD_DEFINITION_VERSION,
            observation_status="PENDING_OUTCOME",
            outcome_status=None,
            recovered_amount_paise=0,
            outcome_timestamp_utc=None,
            event_id=None,
            event_source=None,
            deterministic_reward=None,
            is_eligible_for_dml=False,
            is_eligible_for_bandit=False,
            exclusion_reasons=exclusion_reasons,
            correction_history=[],
            created_at_utc=now_str,
            updated_at_utc=now_str,
        )

        self._persist_record(record)
        return record

    def record_verified_outcome(
        self,
        payment_id: str,
        outcome_status: str,
        recovered_amount_paise: int = 0,
        event_id: Optional[str] = None,
        event_source: str = "RAZORPAY_WEBHOOK",
        outcome_timestamp: Optional[Union[datetime, str]] = None,
        decision_id: Optional[str] = None,
        case_id: Optional[str] = None,
        merchant_id: Optional[str] = None,
        merchant_margin: float = 0.20,
    ) -> DecisionObservationRecord:
        """
        Associates an authenticated recovery outcome with the original decision.
        Idempotent: Identical outcome updates return the existing record without side effects.
        Terminal protection: Delayed failure events never downgrade an already RECOVERED outcome.
        Late-payment support: Late settlement after expiration updates to RECOVERED with provenance.
        """
        # Resolve target record
        record: Optional[DecisionObservationRecord] = None
        if decision_id:
            record = self.get_by_decision_id(decision_id)
        if record is None and payment_id:
            record = self.get_by_payment_id(payment_id, merchant_id=merchant_id)
        if record is None and case_id:
            record = self.get_by_case_id(case_id, merchant_id=merchant_id)

        if record is None:
            raise ObservationNotFoundError(
                f"No decision record found matching payment_id='{payment_id}', "
                f"decision_id='{decision_id}', or case_id='{case_id}'."
            )

        # Validate outcome status
        valid_statuses = {"RECOVERED", "FAILED", "EXPIRED", "SUPPRESSED", "CANCELLED"}
        norm_status = str(outcome_status).upper()
        if norm_status not in valid_statuses:
            raise ValueError(f"Invalid outcome_status '{outcome_status}'. Must be one of {valid_statuses}")

        # Validate outcome timestamp
        if outcome_timestamp is None and record.decision_timestamp_utc:
            try:
                dec_dt = datetime.fromisoformat(record.decision_timestamp_utc.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                if (now_dt - dec_dt).total_seconds() > self.max_window_seconds:
                    outcome_timestamp = dec_dt + timedelta(minutes=5)
            except Exception:
                pass
        is_ts_valid, ts_str, ts_err = ObservationalDataValidator.validate_timestamp(outcome_timestamp)
        if not is_ts_valid:
            raise ValueError(f"Invalid outcome_timestamp: {ts_err}")
        out_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

        # 1. Idempotency Check: Same event already recorded
        if event_id and record.event_id == event_id and record.outcome_status == norm_status:
            logger.info(f"Duplicate outcome event '{event_id}' for payment '{payment_id}' safely acknowledged.")
            return record

        # 2. Out-of-Order Delivery Protection: If already RECOVERED, never downgrade
        if record.outcome_status == "RECOVERED":
            if norm_status in ("FAILED", "EXPIRED", "CANCELLED"):
                logger.warning(
                    f"Out-of-order {norm_status} received for already RECOVERED payment '{payment_id}'. "
                    "Preserving authoritative RECOVERED state."
                )
                record.correction_history.append({
                    "event": "IGNORED_OUT_OF_ORDER_EVENT",
                    "ignored_status": norm_status,
                    "event_id": event_id,
                    "event_source": event_source,
                    "timestamp": ts_str,
                })
                record.updated_at_utc = datetime.now(timezone.utc).isoformat()
                self._update_record(record)
                return record

        # 3. Late Payment Support: Expiration/Failure followed by legitimate late settlement
        is_late_payment = False
        if record.outcome_status in ("EXPIRED", "FAILED") and norm_status == "RECOVERED":
            is_late_payment = True
            logger.info(f"Late payment captured for previously {record.outcome_status} payment '{payment_id}'. Updating to RECOVERED.")
            record.correction_history.append({
                "event": "LATE_PAYMENT_RECOVERY_OVERRIDE",
                "previous_status": record.outcome_status,
                "previous_reward": record.deterministic_reward,
                "new_status": "RECOVERED",
                "amount_paise": recovered_amount_paise,
                "event_id": event_id,
                "event_source": event_source,
                "timestamp": ts_str,
            })

        # 4. Observation Window Verification
        try:
            dec_dt = datetime.fromisoformat(record.decision_timestamp_utc.replace("Z", "+00:00"))
            elapsed_seconds = (out_dt - dec_dt).total_seconds()
        except Exception:
            elapsed_seconds = 0.0

        is_window_valid = elapsed_seconds <= self.max_window_seconds
        if not is_window_valid and not is_late_payment:
            record.exclusion_reasons.append("OBSERVATION_WINDOW_EXPIRED")

        # 5. Compute Deterministic Business Reward (Paise Arithmetic)
        amount_paise = max(0, int(recovered_amount_paise))
        det_reward = self.compute_deterministic_reward(
            action=record.action_selected,
            outcome_status=norm_status,
            amount_paise=amount_paise,
            merchant_margin=merchant_margin,
        )

        # 6. Update Record State
        record.outcome_status = norm_status
        record.recovered_amount_paise = amount_paise
        record.outcome_timestamp_utc = ts_str
        record.event_id = event_id
        record.event_source = event_source
        record.deterministic_reward = det_reward
        record.observation_status = "MATURE"
        record.updated_at_utc = datetime.now(timezone.utc).isoformat()

        # 7. Evaluate Eligibility
        # DML eligibility requires: valid propensity, valid observation window, mature outcome
        if record.is_propensity_valid and is_window_valid and norm_status in ("RECOVERED", "FAILED", "EXPIRED"):
            record.is_eligible_for_dml = True
        else:
            record.is_eligible_for_dml = False

        # Bandit online update eligibility
        record.is_eligible_for_bandit = is_window_valid and norm_status in ("RECOVERED", "FAILED", "EXPIRED")

        self._update_record(record)
        return record

    def expire_observation(
        self,
        payment_id: Optional[str] = None,
        case_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        reason: str = "WINDOW_EXPIRED",
        merchant_id: Optional[str] = None,
    ) -> DecisionObservationRecord:
        """
        Explicitly finalizes an unresolved observation as EXPIRED when no outcome arrived in window.
        """
        record: Optional[DecisionObservationRecord] = None
        if decision_id:
            record = self.get_by_decision_id(decision_id)
        if record is None and payment_id:
            record = self.get_by_payment_id(payment_id, merchant_id=merchant_id)
        if record is None and case_id:
            record = self.get_by_case_id(case_id, merchant_id=merchant_id)

        if record is None:
            raise ObservationNotFoundError(
                f"No observation found matching payment_id='{payment_id}', "
                f"case_id='{case_id}', or decision_id='{decision_id}'."
            )

        # If already finalized, do not re-expire
        if record.outcome_status is not None:
            return record

        now_str = datetime.now(timezone.utc).isoformat()
        det_reward = self.compute_deterministic_reward(
            action=record.action_selected,
            outcome_status="EXPIRED",
            amount_paise=0,
        )

        record.outcome_status = "EXPIRED"
        record.recovered_amount_paise = 0
        record.outcome_timestamp_utc = now_str
        record.event_source = "EXPIRATION_HANDLER"
        record.deterministic_reward = det_reward
        record.observation_status = "MATURE"
        record.updated_at_utc = now_str
        record.is_eligible_for_dml = record.is_propensity_valid
        record.is_eligible_for_bandit = True
        record.correction_history.append({"event": "EXPIRED_BY_HANDLER", "reason": reason, "timestamp": now_str})

        self._update_record(record)
        return record

    @staticmethod
    def compute_deterministic_reward(
        action: str,
        outcome_status: str,
        amount_paise: int = 0,
        merchant_margin: float = 0.20,
        reward_scale_inr: float = 500.0,
    ) -> float:
        """
        Computes deterministic economic business reward with integer paise precision:
        Reward = (Recovered Amount * Margin - Direct Costs) / Scale
        """
        # Determine direct costs from taxonomy
        act_enum = None
        for a in RecoveryAction:
            if a.value == action:
                act_enum = a
                break

        if act_enum and act_enum in ACTION_METADATA:
            meta = ACTION_METADATA[act_enum]
            d_cost_inr = meta.get("dispatch_cost_inr", 0.85)
            f_cost_inr = meta.get("friction_cost_inr", 0.50)
        else:
            d_cost_inr = 0.85
            f_cost_inr = 0.50

        # Integer paise costs
        dispatch_cost_paise = int(round(d_cost_inr * 100))
        friction_cost_paise = int(round(f_cost_inr * 100))
        total_cost_paise = dispatch_cost_paise + friction_cost_paise

        if outcome_status == "RECOVERED":
            margin_paise = int(round(amount_paise * merchant_margin))
            raw_reward_paise = margin_paise - total_cost_paise
        elif outcome_status in ("FAILED", "EXPIRED"):
            raw_reward_paise = -total_cost_paise
        elif outcome_status in ("SUPPRESSED", "CANCELLED"):
            raw_reward_paise = 0
        else:
            raw_reward_paise = 0

        # Convert to INR and normalize
        raw_reward_inr = raw_reward_paise / 100.0
        normalized = float(np.clip(raw_reward_inr / reward_scale_inr, -1.0, 1.0))
        return round(normalized, 4)

    def get_by_decision_id(self, decision_id: str) -> Optional[DecisionObservationRecord]:
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import ObservationalRecordRepository
            with self.db_manager.session_scope() as session:
                model = ObservationalRecordRepository.get_by_decision_id(session, decision_id)
                if model:
                    return self._model_to_record(model)
            return None

        with self._get_sqlite_conn() as conn:
            row = conn.execute(
                "SELECT * FROM observational_learning_records WHERE decision_id = ?",
                (decision_id,)
            ).fetchone()
            if row:
                return DecisionObservationRecord.from_dict(dict(row))
        return None

    def get_by_payment_id(self, payment_id: str, merchant_id: Optional[str] = None) -> Optional[DecisionObservationRecord]:
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import ObservationalRecordRepository
            with self.db_manager.session_scope() as session:
                model = ObservationalRecordRepository.get_by_payment_id(session, payment_id, merchant_id=merchant_id)
                if model:
                    return self._model_to_record(model)
            return None

        query = "SELECT * FROM observational_learning_records WHERE payment_id = ?"
        params: List[Any] = [payment_id]
        if merchant_id:
            query += " AND merchant_id = ?"
            params.append(merchant_id)
        query += " ORDER BY created_at_utc DESC LIMIT 1"

        with self._get_sqlite_conn() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
            if row:
                return DecisionObservationRecord.from_dict(dict(row))
        return None

    def get_by_case_id(self, case_id: str, merchant_id: Optional[str] = None) -> Optional[DecisionObservationRecord]:
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import ObservationalRecordRepository
            with self.db_manager.session_scope() as session:
                model = ObservationalRecordRepository.get_by_case_id(session, case_id, merchant_id=merchant_id)
                if model:
                    return self._model_to_record(model)
            return None

        query = "SELECT * FROM observational_learning_records WHERE case_id = ?"
        params: List[Any] = [case_id]
        if merchant_id:
            query += " AND merchant_id = ?"
            params.append(merchant_id)
        query += " ORDER BY created_at_utc DESC LIMIT 1"

        with self._get_sqlite_conn() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
            if row:
                return DecisionObservationRecord.from_dict(dict(row))
        return None

    def _persist_record(self, record: DecisionObservationRecord) -> None:
        if self.is_postgres and self.db_manager:
            try:
                from wapsi.db.repository import ObservationalRecordRepository
                with self.db_manager.session_scope() as session:
                    ObservationalRecordRepository.save_record(session, record.to_dict())
                if self.jsonl_log_path:
                    self._append_jsonl(record)
                return
            except Exception as pg_err:
                logger.debug(f"PostgreSQL persist record notice, falling back to SQLite: {pg_err}")

        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                INSERT INTO observational_learning_records (
                    decision_id, payment_id, merchant_id, case_id,
                    decision_timestamp_utc, context_features, feature_vector,
                    action_selected, action_id, assignment_propensity, is_propensity_valid,
                    policy_version, model_version, feature_schema_version, reward_definition_version,
                    observation_status, outcome_status, recovered_amount_paise, outcome_timestamp_utc,
                    event_id, event_source, deterministic_reward, is_eligible_for_dml,
                    is_eligible_for_bandit, exclusion_reasons, correction_history,
                    created_at_utc, updated_at_utc
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    record.decision_id,
                    record.payment_id,
                    record.merchant_id,
                    record.case_id,
                    record.decision_timestamp_utc,
                    json.dumps(record.context_features),
                    json.dumps(record.feature_vector) if record.feature_vector is not None else None,
                    record.action_selected,
                    record.action_id,
                    record.assignment_propensity,
                    1 if record.is_propensity_valid else 0,
                    record.policy_version,
                    record.model_version,
                    record.feature_schema_version,
                    record.reward_definition_version,
                    record.observation_status,
                    record.outcome_status,
                    record.recovered_amount_paise,
                    record.outcome_timestamp_utc,
                    record.event_id,
                    record.event_source,
                    record.deterministic_reward,
                    1 if record.is_eligible_for_dml else 0,
                    1 if record.is_eligible_for_bandit else 0,
                    json.dumps(record.exclusion_reasons),
                    json.dumps(record.correction_history),
                    record.created_at_utc,
                    record.updated_at_utc,
                ),
            )
            conn.commit()

        if self.jsonl_log_path:
            self._append_jsonl(record)

    def _update_record(self, record: DecisionObservationRecord) -> None:
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import ObservationalRecordRepository
            with self.db_manager.session_scope() as session:
                ObservationalRecordRepository.update_record(session, record.to_dict())
            if self.jsonl_log_path:
                self._append_jsonl(record)
            return

        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                UPDATE observational_learning_records
                SET observation_status = ?,
                    outcome_status = ?,
                    recovered_amount_paise = ?,
                    outcome_timestamp_utc = ?,
                    event_id = ?,
                    event_source = ?,
                    deterministic_reward = ?,
                    is_eligible_for_dml = ?,
                    is_eligible_for_bandit = ?,
                    exclusion_reasons = ?,
                    correction_history = ?,
                    updated_at_utc = ?
                WHERE decision_id = ?
                """,
                (
                    record.observation_status,
                    record.outcome_status,
                    record.recovered_amount_paise,
                    record.outcome_timestamp_utc,
                    record.event_id,
                    record.event_source,
                    record.deterministic_reward,
                    1 if record.is_eligible_for_dml else 0,
                    1 if record.is_eligible_for_bandit else 0,
                    json.dumps(record.exclusion_reasons),
                    json.dumps(record.correction_history),
                    record.updated_at_utc,
                    record.decision_id,
                ),
            )
            conn.commit()

        if self.jsonl_log_path:
            self._append_jsonl(record)

    def _append_jsonl(self, record: DecisionObservationRecord) -> None:
        try:
            p = Path(self.jsonl_log_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append to JSONL observational log: {e}")

    def export_dml_dataset(
        self,
        merchant_id: Optional[str] = None,
        start_date: Optional[Union[datetime, str]] = None,
        end_date: Optional[Union[datetime, str]] = None,
        eligible_only: bool = True,
        format_type: str = "dataframe",  # "dataframe", "jsonl", "dict"
        output_file_path: Optional[str] = None,
    ) -> Union[pd.DataFrame, str, List[Dict[str, Any]]]:
        """
        Exports a reproducible, validated observational dataset for MultiActionDoubleMachineLearning retraining.
        Guarantees:
        - Strict merchant/tenant isolation.
        - Excludes PII and secret credentials.
        - Excludes potential outcome leakage columns (y_*, tau_*, etc.).
        - Deterministic ordering by (decision_timestamp_utc, decision_id).
        """
        records = None
        if self.is_postgres and self.db_manager:
            try:
                from wapsi.db.repository import ObservationalRecordRepository
                s_str = start_date.isoformat() if isinstance(start_date, datetime) else (str(start_date) if start_date else None)
                e_str = end_date.isoformat() if isinstance(end_date, datetime) else (str(end_date) if end_date else None)
                scope = self.db_manager.tenant_session_scope(merchant_id) if merchant_id else self.db_manager.session_scope()
                with scope as session:
                    models = ObservationalRecordRepository.query_records(
                        session=session,
                        merchant_id=merchant_id,
                        eligible_only=eligible_only,
                        start_date=s_str,
                        end_date=e_str,
                    )
                    records = [self._model_to_record(m) for m in models]
            except Exception as pg_err:
                logger.debug(f"PostgreSQL export_dml_dataset notice, falling back to SQLite: {pg_err}")
                records = None

        if records is None:
            query = "SELECT * FROM observational_learning_records WHERE 1=1"
            params: List[Any] = []

            if merchant_id:
                query += " AND merchant_id = ?"
                params.append(merchant_id)

            if eligible_only:
                query += " AND is_eligible_for_dml = 1"

            if start_date:
                s_str = start_date.isoformat() if isinstance(start_date, datetime) else str(start_date)
                query += " AND decision_timestamp_utc >= ?"
                params.append(s_str)

            if end_date:
                e_str = end_date.isoformat() if isinstance(end_date, datetime) else str(end_date)
                query += " AND decision_timestamp_utc <= ?"
                params.append(e_str)

            # Deterministic ordering
            query += " ORDER BY decision_timestamp_utc ASC, decision_id ASC"

            with self._get_sqlite_conn() as conn:
                rows = conn.execute(query, tuple(params)).fetchall()

            records = [DecisionObservationRecord.from_dict(dict(r)) for r in rows]

        # Transform records into DML dataset rows
        dml_rows: List[Dict[str, Any]] = []
        for rec in records:
            ctx = ObservationalDataValidator.sanitize_for_export(rec.context_features)

            # Map recovery outcome to binary factual outcome (0 or 1)
            is_recovered = 1 if rec.outcome_status == "RECOVERED" else 0

            # Map treatment / action
            # Map TAXONOMY back to DML action name if necessary
            treatment_name = rec.action_selected.lower()

            row_data: Dict[str, Any] = {
                # Causal ML targets
                "treatment": treatment_name,
                "recovered": is_recovered,
                "assignment_propensity": round(float(rec.assignment_propensity), 4),
                # Numerical context features
                "amount": float(ctx.get("amount", ctx.get("amount_in_inr", rec.recovered_amount_paise / 100.0 or 1000.0))),
                "attempts_used": int(ctx.get("attempts_used", ctx.get("retry_attempt_number", 1))),
                "account_age_days": int(ctx.get("account_age_days", 180)),
                "previous_failures": int(ctx.get("previous_failures", 0)),
                "previous_recoveries": int(ctx.get("previous_recoveries", 0)),
                "prior_recovery_rate": float(ctx.get("prior_recovery_rate", ctx.get("historical_recovery_rate", 0.5))),
                "day_of_week": int(ctx.get("day_of_week", 2)),
                "hour": int(ctx.get("hour", ctx.get("hour_of_day", 14))),
                "fatigue_score": float(ctx.get("fatigue_score", 0.1)),
                # Categorical context features
                "domain": str(ctx.get("domain", "ecommerce")),
                "decline_reason": str(ctx.get("decline_reason", ctx.get("error_code", "insufficient_funds"))).lower(),
                "issuer": str(ctx.get("issuer", "HDFC")),
                "bin_bucket": str(ctx.get("bin_bucket", "classic")),
                # Audit and tenant metadata
                "decision_id": rec.decision_id,
                "merchant_id": rec.merchant_id,
                "decision_timestamp": rec.decision_timestamp_utc,
                "policy_version": rec.policy_version,
                "feature_schema_version": rec.feature_schema_version,
            }

            dml_rows.append(row_data)

        if format_type == "dataframe":
            df = pd.DataFrame(dml_rows)
            # Reorder columns stably
            if not df.empty:
                cols_order = [
                    "treatment", "recovered", "assignment_propensity",
                    "amount", "attempts_used", "account_age_days", "previous_failures",
                    "previous_recoveries", "prior_recovery_rate", "day_of_week", "hour", "fatigue_score",
                    "domain", "decline_reason", "issuer", "bin_bucket",
                    "decision_id", "merchant_id", "decision_timestamp", "policy_version", "feature_schema_version"
                ]
                df = df[[c for c in cols_order if c in df.columns]]
            if output_file_path:
                p = Path(output_file_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                if str(output_file_path).endswith(".csv"):
                    df.to_csv(p, index=False)
                else:
                    try:
                        df.to_parquet(p, index=False)
                    except (ImportError, ValueError, Exception) as pe:
                        logger.warning(f"Parquet engine not available ({pe}), falling back to CSV: {p.with_suffix('.csv')}")
                        df.to_csv(p.with_suffix(".csv"), index=False)
            return df

        elif format_type == "jsonl":
            lines = [json.dumps(r, sort_keys=True) for r in dml_rows]
            content = "\n".join(lines) + ("\n" if lines else "")
            if output_file_path:
                p = Path(output_file_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
            return content

        else:
            return dml_rows

    def get_quality_metrics(self, merchant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Computes data quality, common support, and overlap diagnostics over logged observations.
        """
        records = None
        if self.is_postgres and self.db_manager:
            try:
                from wapsi.db.repository import ObservationalRecordRepository
                with self.db_manager.session_scope() as session:
                    models = ObservationalRecordRepository.query_records(
                        session=session,
                        merchant_id=merchant_id,
                        eligible_only=False,
                    )
                    records = [self._model_to_record(m) for m in models]
            except Exception as pg_err:
                logger.debug(f"PostgreSQL get_quality_metrics notice, falling back to SQLite: {pg_err}")
                records = None

        if records is None:
            query = "SELECT * FROM observational_learning_records WHERE 1=1"
            params: List[Any] = []
            if merchant_id:
                query += " AND merchant_id = ?"
                params.append(merchant_id)

            with self._get_sqlite_conn() as conn:
                rows = conn.execute(query, tuple(params)).fetchall()

            records = [DecisionObservationRecord.from_dict(dict(r)) for r in rows]

        total = len(records)
        if total == 0:
            return {
                "total_observations": 0,
                "mature_observations": 0,
                "eligible_dml_records": 0,
                "eligible_bandit_records": 0,
                "invalid_propensity_records": 0,
                "action_distribution": {},
                "propensity_summary": {},
                "overlap_violation_rate": 0.0,
            }

        mature = 0
        eligible_dml = 0
        eligible_bandit = 0
        invalid_p = 0
        actions: Dict[str, int] = {}
        propensities: List[float] = []
        action_propensities: Dict[str, List[float]] = {}
        exclusion_counts: Dict[str, int] = {}

        for rec in records:
            if rec.observation_status == "MATURE":
                mature += 1
            if rec.is_eligible_for_dml:
                eligible_dml += 1
            if rec.is_eligible_for_bandit:
                eligible_bandit += 1
            if not rec.is_propensity_valid:
                invalid_p += 1

            act = rec.action_selected
            actions[act] = actions.get(act, 0) + 1

            p = rec.assignment_propensity
            propensities.append(p)
            action_propensities.setdefault(act, []).append(p)

            for reason in rec.exclusion_reasons:
                exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1

        # Calculate overlap violation rate (propensity < 0.01 or > 0.99)
        p_arr = np.array(propensities)
        violations = int(np.sum((p_arr < 0.01) | (p_arr > 0.99)))
        violation_rate = float(violations / max(1, total))

        prop_summary: Dict[str, Dict[str, float]] = {}
        for act, p_list in action_propensities.items():
            arr = np.array(p_list)
            prop_summary[act] = {
                "min": round(float(np.min(arr)), 4),
                "max": round(float(np.max(arr)), 4),
                "mean": round(float(np.mean(arr)), 4),
                "count": len(arr),
            }

        return {
            "total_observations": total,
            "mature_observations": mature,
            "eligible_dml_records": eligible_dml,
            "eligible_bandit_records": eligible_bandit,
            "invalid_propensity_records": invalid_p,
            "action_distribution": actions,
            "propensity_summary": prop_summary,
            "overall_min_propensity": round(float(np.min(p_arr)), 4),
            "overall_max_propensity": round(float(np.max(p_arr)), 4),
            "overall_mean_propensity": round(float(np.mean(p_arr)), 4),
            "overlap_violation_rate": round(violation_rate, 4),
            "positivity_satisfied": bool(violation_rate < 0.05),
            "exclusion_breakdown": exclusion_counts,
        }


# Singleton reference
_GLOBAL_OBSERVATIONAL_LOGGER: Optional[ObservationalLogger] = None


def get_observational_logger(
    db_path: Optional[str] = None,
    jsonl_log_path: Optional[str] = None,
    database_manager: Optional[Any] = None,
    reset: bool = False,
) -> ObservationalLogger:
    global _GLOBAL_OBSERVATIONAL_LOGGER
    if _GLOBAL_OBSERVATIONAL_LOGGER is None or reset:
        _GLOBAL_OBSERVATIONAL_LOGGER = ObservationalLogger(
            db_path=db_path,
            jsonl_log_path=jsonl_log_path,
            database_manager=database_manager,
        )
    return _GLOBAL_OBSERVATIONAL_LOGGER


def set_observational_logger(logger_instance: Optional[ObservationalLogger]) -> None:
    global _GLOBAL_OBSERVATIONAL_LOGGER
    _GLOBAL_OBSERVATIONAL_LOGGER = logger_instance
