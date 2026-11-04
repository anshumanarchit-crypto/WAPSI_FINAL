"""
WAPSI Unified Inference Pipeline Demonstration.
Razorpay AI Buildathon 2026 - Track 3

Demonstrates end-to-end execution of wapsi.predict(case) across diverse transaction failures.
Saves:
  - evaluation/sample_inference_response.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inference import wapsi


def run_demo():
    print("=" * 80)
    print("WAPSI UNIFIED INFERENCE PIPELINE DEMONSTRATION")
    print("=" * 80)

    # Example 1: High-value eCommerce OTP Timeout failure
    case_ecom = {
        "case_id": "case_pay_99812",
        "amount": 3499.0,
        "domain": "ecommerce",
        "decline_reason": "upi_pin_timeout",
        "prior_recovery_rate": 0.82,
        "attempts_used": 1,
        "fatigue_score": 0.08,
        "hour": 16,
        "issuer": "HDFC",
        "bin_bucket": "platinum",
        "merchant_id": "merch_trendy_wear"
    }

    print(f"\n[Case 1] Input: {case_ecom['domain']} | Rs. {case_ecom['amount']} | {case_ecom['decline_reason']}")
    res_ecom = wapsi.predict(case_ecom)
    print("\n--- Structured Recommendation Output (Frontend Contract) ---")
    print(json.dumps(res_ecom, indent=2))

    # Save to JSON
    out_file = Path("evaluation") / "sample_inference_response.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(res_ecom, f, indent=2)

    print(f"\nSaved sample response artifact to: {out_file}")

    # Example 2: B2B SaaS Technical Bank Downtime
    case_b2b = {
        "case_id": "case_pay_44120",
        "amount": 55000.0,
        "domain": "b2b_saas",
        "decline_reason": "bank_downtime",
        "prior_recovery_rate": 0.95,
        "attempts_used": 1,
        "fatigue_score": 0.00,
        "hour": 11,
        "issuer": "ICICI",
        "bin_bucket": "corporate",
        "merchant_id": "merch_cloud_suite"
    }

    print(f"\n[Case 2] Input: {case_b2b['domain']} | Rs. {case_b2b['amount']} | {case_b2b['decline_reason']}")
    res_b2b = wapsi.predict(case_b2b)
    print(f"  Recommended Action : {res_b2b['recommended_action']}")
    print(f"  Incremental Uplift : +{res_b2b['uplift']:.2%}")
    print(f"  Recommended Window : {res_b2b['timing']['recommended_window']}")
    print(f"  Conformal Status   : {res_b2b['policy_inputs']['conformal_gate']['calibration_status']}")
    print(f"  Auto-Action Safe   : {res_b2b['policy_inputs']['conformal_gate']['eligible_for_auto_action']}")


if __name__ == "__main__":
    run_demo()
