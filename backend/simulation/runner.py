"""
WAPSI End-to-End Simulation Runner.
Razorpay AI Buildathon 2026 - Track 3

Executes standard scenarios and generates:
  - Clean human-readable terminal output
  - Machine-readable audit log: simulation/simulation_audit_log.json
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Configure UTF-8 stdout for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure workspace root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulation.simulator import WAPSISimulator
from simulation.scenarios import ALL_SCENARIOS


def format_action_name(action: str) -> str:
    """Formats raw action string into human-friendly label."""
    if not action:
        return "None"
    mapping = {
        "no_action": "No Action (Organic Recovery)",
        "retry_only": "Silent Auto-Retry",
        "whatsapp_nudge": "WhatsApp 1-Click Link",
        "voice_call": "Automated IVR / Voice Assist",
        "email": "Email Recovery Link",
        "incentive_link": "Merchant Dynamic Incentive Link"
    }
    return mapping.get(action, action.replace("_", " ").title())


def run_simulation(save_logs: bool = True) -> List[Dict[str, Any]]:
    print("=" * 80)
    print("WAPSI END-TO-END LOCAL SIMULATION (DISCLOSURE: NO REAL COMMUNICATIONS OR MONEY)")
    print("Razorpay AI Buildathon 2026 - Track 3")
    print("=" * 80)

    simulator = WAPSISimulator()
    results: List[Dict[str, Any]] = []

    for i, scenario in enumerate(ALL_SCENARIOS, 1):
        name = scenario["name"]
        print(f"\n[{i}/{len(ALL_SCENARIOS)}] Executing Scenario: {name}")
        
        record = simulator.simulate_case(scenario)
        results.append(record)

        # Format Human-Readable Terminal Block
        case_id = record.get("case_id", "N/A")
        amount = record.get("amount", 0.0)
        failure = record.get("decline_reason", "N/A")
        action = format_action_name(record.get("recommended_action", ""))
        uplift = record.get("uplift", 0.0)
        timing = record.get("timing_window", "N/A")
        confidence = record.get("confidence", 0.0)
        precedent = record.get("precedent_summary", "N/A")
        tee_status = record.get("tee_status", "N/A")
        policy_status = record.get("policy_status", "N/A")
        outcome = record.get("simulated_outcome", record.get("status", "PROCESSED"))
        rec_amount = record.get("recovered_amount", 0.0)

        print("-" * 50)
        print(f"CASE {case_id}")
        print(f"Amount: ₹{amount:,.0f}")
        print(f"Failure: {failure}")
        print()
        if record.get("status") == "DUPLICATE_IGNORED":
            print("Status: DUPLICATE_IGNORED (Anti-Replay Webhook Deduplication)")
        elif record.get("status") == "TEE_ATTESTATION_FAILED":
            print(f"TEE: {tee_status} ({record.get('error', 'Enclave measurement mismatch')})")
            print("Status: BLOCKED_FAIL_CLOSED (Autonomous action refused)")
        else:
            print(f"Recommended action: {action}")
            print(f"Estimated uplift: +{uplift:.1%}")
            print(f"Timing: {timing}")
            print(f"Confidence: {confidence:.0%}")
            print()
            print(f"Precedent: {precedent}")
            print()
            print(f"TEE: {tee_status}")
            print(f"Policy: {policy_status}")
            print()
            print(f"Simulated outcome: {outcome}")
            print(f"Recovered amount: ₹{rec_amount:,.0f}")
            if record.get("audit_block_index") is not None:
                print(f"Audit Ledger Block: #{record['audit_block_index']} (Hash: {record['audit_block_hash'][:16]}...)")
                print(f"Bandit Net Reward: ₹{record.get('net_reward_inr', 0.0):.2f} (Posterior Updated)")
        print("-" * 50)

    # Save Machine-Readable Audit Log
    if save_logs:
        out_paths = [
            Path("simulation") / "simulation_audit_log.json",
            Path("evaluation") / "simulation_audit_log.json"
        ]
        for p in out_paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"\nSaved machine-readable audit log to: {p}")

    # Verify Audit Ledger Integrity
    integrity = simulator.audit_ledger.verify_integrity()
    print(f"\nAudit Ledger Chain Integrity: {'VALID (TAMPER-EVIDENT HASH CHAIN CONFIRMED)' if integrity['is_valid'] else 'INVALID'}")
    print(f"Total Blocks in Ledger: {integrity['total_blocks']}")

    return results


if __name__ == "__main__":
    run_simulation()
