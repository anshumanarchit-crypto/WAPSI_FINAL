"""
Unit tests for PolicyEngine and Guardrails.
"""

import pytest
from wapsi.policy.policy_engine import PolicyEngine
from wapsi.core.taxonomy import RecoveryAction


def test_policy_engine_dnd_override():
    engine = PolicyEngine(dnd_start_hour=21, dnd_end_hour=9)
    
    # Event at 23:00 (11 PM IST)
    event_night = {
        "user_id": "usr_test_1",
        "amount_in_inr": 2000.0,
        "hour_of_day": 23
    }
    
    res = engine.evaluate(
        event_dict=event_night,
        proposed_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        causal_net_utility=150.0
    )
    
    assert res["dnd_active"] is True
    assert res["override_applied"] is True
    # Should override user contact action during DND to instant smart retry
    assert res["authorized_action"] == RecoveryAction.INSTANT_SMART_RETRY.value


def test_policy_engine_frequency_cap():
    engine = PolicyEngine(max_daily_user_nudges=2)
    event_day = {
        "user_id": "usr_spam_target",
        "amount_in_inr": 2500.0,
        "hour_of_day": 14
    }

    # First execution
    engine.record_execution(user_id="usr_spam_target", action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value)
    # Second execution
    engine.record_execution(user_id="usr_spam_target", action=RecoveryAction.SMS_FALLBACK_LINK.value)

    # Third proposed nudge
    res = engine.evaluate(
        event_dict=event_day,
        proposed_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        causal_net_utility=120.0
    )

    assert res["override_applied"] is True
    assert res["authorized_action"] == RecoveryAction.NO_ACTION.value
    assert "Frequency Cap Exceeded" in res["violations"][0]


def test_policy_engine_negative_utility_suppression():
    engine = PolicyEngine()
    event = {"user_id": "usr_99", "amount_in_inr": 100.0, "hour_of_day": 15}

    res = engine.evaluate(
        event_dict=event,
        proposed_action=RecoveryAction.CALL_ASSIST_IVR.value,
        causal_net_utility=-12.50
    )

    assert res["authorized_action"] == RecoveryAction.NO_ACTION.value
