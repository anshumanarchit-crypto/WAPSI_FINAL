"""
LLM Explainer & Notification Localizer.
Converts mathematical causal decisions, SHAP attributions, and precedents into plain-English
merchant audit rationales and localized customer recovery copy.

RULE: The LLM NEVER decides the recovery action. The causal ML engine decides;
the LLM only formats explainability and generates bounded notification copy.
"""

import html
from typing import Dict, Any, List, Optional
from wapsi.core.taxonomy import RecoveryAction, ACTION_METADATA


class LLMDecisionExplainer:
    """
    Produces deterministic, structured human-readable audit summaries and
    channel-specific localized customer notification messages.
    """

    @classmethod
    def generate_plain_english_rationale(
        cls,
        decision_result: Dict[str, Any],
        shap_result: Dict[str, Any],
        precedent_result: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Produces an auditable plain-English summary of the causal decision.
        """
        action = decision_result.get("recommended_action", RecoveryAction.NO_ACTION.value)
        action_name = html.escape(str(decision_result.get("recommended_action_name", str(action))))
        tau = decision_result.get("individual_treatment_effect_uplift", 0.0)
        baseline_prob = decision_result.get("baseline_organic_recovery_prob", 0.15)
        exp_prob = decision_result.get("expected_action_recovery_prob", min(1.0, baseline_prob + tau))
        net_util = decision_result.get("net_expected_utility_inr", 0.0)
        delay_str = html.escape(str(decision_result.get("timing", {}).get("delay_human_readable", "immediate")))
        
        # Drivers from SHAP
        pos_drivers = shap_result.get("positive_drivers", [])
        driver_str = ""
        if pos_drivers:
            top_drivers = [html.escape(str(d["feature_name"])) for d in pos_drivers[:2]]
            driver_str = f" driven primarily by {', '.join(top_drivers)}"

        if action == RecoveryAction.NO_ACTION.value:
            return (
                f"Recommended NO_ACTION: Organic recovery probability is already {round(baseline_prob * 100, 1)}% "
                f"and expected incremental intervention uplift was insufficient to justify dispatch & friction costs."
            )

        pct_uplift = round(tau * 100, 1)
        rationale = (
            f"Recommended '{action_name}' with optimal engagement delay of {delay_str}. "
            f"Estimated causal uplift is +{pct_uplift}% (from {round(baseline_prob * 100, 1)}% organic to {round(exp_prob * 100, 1)}% with action){driver_str}. "
            f"Expected net revenue contribution is ₹{net_util:.2f} after channel delivery and customer friction costs."
        )

        # Append precedent validation if present
        if precedent_result and precedent_result.get("best_empirical_action"):
            emp_best = precedent_result["best_empirical_action"]
            if emp_best == action:
                rationale += " Historical precedent strongly confirms this recommendation."

        return rationale

    @classmethod
    def generate_customer_copy(
        cls,
        event_dict: Dict[str, Any],
        selected_action: str,
        payment_link: str = "https://rzp.io/r/demo"
    ) -> Dict[str, Any]:
        """
        Generates localized, channel-safe notification text matching the root cause.
        """
        amount = event_dict.get("amount_in_inr", 1000.0)
        raw_merchant = str(event_dict.get("merchant_id", "our store")).replace("merch_", "").replace("_", " ").title()
        merchant = html.escape(raw_merchant)
        err_code = html.escape(str(event_dict.get("error_code", "PAYMENT_FAILED")))
        pay_id = html.escape(str(event_dict.get("payment_id", "pay_xxxx")))
        formatted_link = f"https://rzp.io/r/{pay_id}"

        if selected_action == RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value:
            if "UPI" in err_code:
                msg = (
                    f"Hi! We noticed your ₹{amount:,.2f} UPI payment at {merchant} timed out. "
                    f"No worries — your items are reserved! Tap below to retry in 1 click without re-entering details:\n"
                    f"👉 {formatted_link}"
                )
            elif "OTP" in err_code or "AUTH" in err_code:
                msg = (
                    f"Hi! Your ₹{amount:,.2f} order at {merchant} had an authentication hiccup. "
                    f"Complete your order securely in 1 tap here:\n"
                    f"👉 {formatted_link}"
                )
            else:
                msg = (
                    f"Hi from {merchant}! Complete your pending order of ₹{amount:,.2f} securely with 1 tap:\n"
                    f"👉 {formatted_link}"
                )
            
            return {
                "channel": "whatsapp",
                "template_id": "tpl_rzp_whatsapp_1click_v2",
                "subject": None,
                "body_text": msg,
                "cta_url": formatted_link,
                "action_type": "BUTTON_URL"
            }

        elif selected_action == RecoveryAction.SMS_FALLBACK_LINK.value:
            msg = f"{merchant}: Your ₹{amount:,.2f} payment was incomplete. Tap to complete securely: {formatted_link} (Expires in 15m)"
            return {
                "channel": "sms",
                "template_id": "tpl_rzp_sms_link_v1",
                "subject": None,
                "body_text": msg,
                "cta_url": formatted_link,
                "action_type": "SMS_LINK"
            }

        elif selected_action == RecoveryAction.BNPL_ALTERNATIVE_OFFER.value:
            msg = (
                f"Hi! Having trouble with card payment at {merchant}? "
                f"Split your ₹{amount:,.2f} order into 3 interest-free payments or Pay Later with 1 click:\n"
                f"👉 {formatted_link}?method=bnpl"
            )
            return {
                "channel": "whatsapp",
                "template_id": "tpl_rzp_bnpl_offer_v1",
                "subject": None,
                "body_text": msg,
                "cta_url": f"{formatted_link}?method=bnpl",
                "action_type": "BNPL_SWITCH"
            }

        elif selected_action == RecoveryAction.MERCHANT_DISCOUNT_NUDGE.value:
            msg = (
                f"Special offer from {merchant}! Complete your ₹{amount:,.2f} checkout in the next 10 mins "
                f"and get an instant 5% recovery discount applied automatically:\n"
                f"👉 {formatted_link}?coupon=RECOVER5"
            )
            return {
                "channel": "whatsapp",
                "template_id": "tpl_rzp_micro_incentive_v1",
                "subject": None,
                "body_text": msg,
                "cta_url": f"{formatted_link}?coupon=RECOVER5",
                "action_type": "DISCOUNT_COUPON"
            }

        elif selected_action == RecoveryAction.CALL_ASSIST_IVR.value:
            ivr_script = (
                f"Hello, this is Razorpay calling on behalf of {merchant}. We noticed an issue processing your "
                f"recent order of ₹{amount:,.2f}. Press 1 on your keypad to receive a direct WhatsApp payment link, "
                f"or Press 2 to speak to a payment support specialist."
            )
            return {
                "channel": "ivr",
                "template_id": "tpl_rzp_ivr_voice_assist_v1",
                "subject": None,
                "body_text": ivr_script,
                "cta_url": formatted_link,
                "action_type": "VOICE_PROMPT"
            }

        elif selected_action == RecoveryAction.INSTANT_SMART_RETRY.value:
            return {
                "channel": "gateway_reroute",
                "template_id": "internal_reroute_v1",
                "subject": None,
                "body_text": "Internal acquiring rail switch initiated. Zero customer message required.",
                "cta_url": None,
                "action_type": "AUTOMATED_REROUTE"
            }

        else:
            return {
                "channel": "none",
                "template_id": "none",
                "subject": None,
                "body_text": "No message dispatched.",
                "cta_url": None,
                "action_type": "NO_ACTION"
            }
