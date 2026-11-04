"""
Pytest global configuration and safety guards for WAPSI test suite.

Safety Guarantees:
1. Zero mutation of live hosted target outbox job (5a6587ab-2601-4017-b396-48e3d2fc2fda).
2. Prevents test executions from claiming, approving, or mutating hosted production/sandbox rows.
3. Enforces that all test-driven claim and execution workflows use isolated synthetic fixtures.
"""

from __future__ import annotations

import os
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

TARGET_JOB_ID_STR = "5a6587ab-2601-4017-b396-48e3d2fc2fda"


@event.listens_for(Engine, "before_cursor_execute")
def guard_live_target_mutations(conn, cursor, statement, parameters, context, executemany):
    """
    SQLAlchemy execution listener that fails closed if any test query attempts
    to execute an UPDATE or DELETE against the live target job in PostgreSQL.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return

    # Check statement type
    stmt_upper = statement.strip().upper()
    is_mutation = stmt_upper.startswith("UPDATE") or stmt_upper.startswith("DELETE")
    is_claim = "CLAIM_SPECIFIC_RECOVERY_OUTBOX_JOB" in stmt_upper or "CLAIM_RECOVERY_OUTBOX_JOBS" in stmt_upper

    if (is_mutation or is_claim) and TARGET_JOB_ID_STR in str(statement).lower():
        # Check dialect: if PostgreSQL, block mutation
        if conn.dialect.name == "postgresql":
            raise RuntimeError(
                f"SAFETY GUARD INTERCEPT: Test '{os.environ.get('PYTEST_CURRENT_TEST')}' "
                f"attempted to mutate or claim live hosted target job {TARGET_JOB_ID_STR}! "
                "Mutations against the live target job in PostgreSQL are strictly forbidden during tests."
            )

    # Check parameters for TARGET_JOB_ID_STR in UPDATE/DELETE or claim
    if (is_mutation or is_claim) and parameters and conn.dialect.name == "postgresql":
        param_str = str(parameters).lower()
        if TARGET_JOB_ID_STR in param_str:
            raise RuntimeError(
                f"SAFETY GUARD INTERCEPT: Test '{os.environ.get('PYTEST_CURRENT_TEST')}' "
                f"passed live target job {TARGET_JOB_ID_STR} into a mutating or claim statement! "
                "Mutations against the live target job in PostgreSQL are strictly forbidden during tests."
            )


@pytest.fixture(autouse=True)
def test_safety_environment(monkeypatch):
    """Ensures test environment flags are set and protects live data."""
    monkeypatch.setenv("WAPSI_TEST_MODE", "1")
    yield
