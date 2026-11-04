"""
WAPSI End-to-End Simulation Package.
Razorpay AI Buildathon 2026 - Track 3
"""

from simulation.simulator import WAPSISimulator
from simulation.scenarios import (
    ALL_SCENARIOS,
    SCENARIO_RECOVERED,
    SCENARIO_NOT_RECOVERED,
    SCENARIO_DUPLICATE_EVENT,
    SCENARIO_POLICY_BLOCKED,
    SCENARIO_TEE_ATTESTATION_FAILURE,
    SCENARIO_LOW_CONFIDENCE,
    SCENARIO_HIGH_COUNTER_EVIDENCE
)
from simulation.runner import run_simulation

__all__ = [
    "WAPSISimulator",
    "ALL_SCENARIOS",
    "SCENARIO_RECOVERED",
    "SCENARIO_NOT_RECOVERED",
    "SCENARIO_DUPLICATE_EVENT",
    "SCENARIO_POLICY_BLOCKED",
    "SCENARIO_TEE_ATTESTATION_FAILURE",
    "SCENARIO_LOW_CONFIDENCE",
    "SCENARIO_HIGH_COUNTER_EVIDENCE",
    "run_simulation"
]
