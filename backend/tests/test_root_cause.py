"""
Unit tests for RootCauseClassifier.
"""

import pytest
from wapsi.core.root_cause import RootCauseClassifier
from wapsi.core.taxonomy import ErrorCategory


def test_root_cause_classification_known_codes():
    res_upi = RootCauseClassifier.classify("UPI_APP_TIMEOUT")
    assert res_upi["error_category"] == ErrorCategory.FRICTION_OTP_UX.value

    res_gw = RootCauseClassifier.classify("GATEWAY_ERROR")
    assert res_gw["error_category"] == ErrorCategory.TECHNICAL_GATEWAY.value

    res_bal = RootCauseClassifier.classify("INSUFFICIENT_FUNDS")
    assert res_bal["error_category"] == ErrorCategory.FINANCIAL_BALANCE.value

    res_cancel = RootCauseClassifier.classify("USER_CANCELLED")
    assert res_cancel["error_category"] == ErrorCategory.ABANDONMENT_INTENT.value


def test_root_cause_classification_fallback():
    res = RootCauseClassifier.classify("CUSTOM_BANK_LATENCY_ERROR", error_description="Bank switch timeout")
    assert res["error_category"] == ErrorCategory.TECHNICAL_GATEWAY.value
