"""
Demonstration script for WAPSI Recovery Router.
Evaluates 5 canonical payment failure cases across different domains, failure types,
and customer segments, highlighting why causal uplift outperforms raw probability classification.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from src.model_registry import ModelRegistry
from src.recovery_router import WAPSIRecoveryRouter, get_deterministic_example_cases


def main():
    print("=" * 80)
    print("WAPSI — Multi-Action Causal Recovery Router Live Demonstration")
    print("Razorpay AI Buildathon 2026 — Track 3")
    print("=" * 80)

    # 1. Load production model from registry
    registry = ModelRegistry(registry_dir="models")
    model = registry.get_model(model_name="wapsi_t_learner", version="production")
    router = WAPSIRecoveryRouter(model=model, enable_eligibility_rules=True)

    examples = get_deterministic_example_cases()
    print(f"\nLoaded {len(examples)} Canonical Evaluation Cases from recovery_router.py:\n")

    for i, ex in enumerate(examples, start=1):
        print("=" * 80)
        print(f"CASE {i}: {ex['case_id'].upper()}")
        print(f"Scenario: {ex['scenario_description']}")
        print("-" * 80)
        
        # Case summary features
        print(f"  Domain: {ex['domain']:<14} | Amount: INR {ex['amount']:>8,.2f} | Reason: {ex['decline_reason']}")
        print(f"  Issuer: {ex['issuer']:<14} | Attempts: {ex['attempts_used']}           | Prior Rec Rate: {ex['prior_recovery_rate']*100:.1f}%")
        print(f"  Hour:   {ex['hour']:02d}:00 IST      | Fatigue: {ex['fatigue_score']:.2f}")

        # Run Router Decision
        decision = router.route(ex)

        print("\nDecision Output (API Contract):")
        print(f"  Recommended Action:            [{decision['recommended_action'].upper()}]")
        print(f"  Estimated Incremental Uplift:  +{decision['uplift']*100:.2f}% (tau)")
        print(f"  Baseline Organic Probability:   {decision['baseline_outcome_probability']*100:.2f}% (P(Y|no_action))")
        print(f"  Expected Action Probability:    {decision['predicted_outcome_probability']*100:.2f}% (P(Y|action))")

        print("\nAction Scores & Causal Rankings:")
        print(f"  {'Rank':<5} | {'Action':<18} | {'Incremental Uplift':<20} | {'Outcome Prob':<14} | {'Eligible?'}")
        print("  " + "-" * 70)
        for item in decision["action_rankings"]:
            elig_str = "YES" if item["is_eligible"] else f"NO ({', '.join(item['ineligibility_reasons'])})"
            is_winner = " -> [WINNER]" if item["action"] == decision["recommended_action"] and decision["recommended_action"] != "no_action" else ""
            print(f"  #{item['rank']:<4} | {item['action']:<18} | {item['incremental_uplift']*100:>+17.2f}% | {item['predicted_outcome_probability']*100:>12.2f}% | {elig_str}{is_winner}")

        print(f"\nRationale:\n  {decision['rationale']}")

    print("\n" + "=" * 80)
    print("Demonstration completed successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
