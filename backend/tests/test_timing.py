"""
Unit tests for RecoveryTimingModel.
"""

import pytest
import pandas as pd
from wapsi.causal.timing import RecoveryTimingModel
from wapsi.core.taxonomy import RecoveryAction
from wapsi.data.generator import SyntheticRecoveryDataGenerator


def test_timing_model_fit_and_predict():
    gen = SyntheticRecoveryDataGenerator(random_seed=42)
    df, _ = gen.generate_dataset(n_samples=200)

    model = RecoveryTimingModel(random_seed=42)
    model.fit(df)

    event = df.iloc[0].to_dict()
    res_smart = model.predict_optimal_delay(event, RecoveryAction.INSTANT_SMART_RETRY.value)
    res_wa = model.predict_optimal_delay(event, RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value)

    assert "optimal_delay_seconds" in res_smart
    assert res_smart["optimal_delay_seconds"] <= 30  # Smart retry must be very fast
    assert res_wa["optimal_delay_seconds"] >= 30    # WhatsApp has organic wait buffer
