"""
Unit tests for PrecedentEngine.
"""

import pytest
import pandas as pd
from wapsi.causal.precedent import PrecedentEngine
from wapsi.core.taxonomy import RecoveryAction
from wapsi.data.generator import SyntheticRecoveryDataGenerator


def test_precedent_engine_query():
    gen = SyntheticRecoveryDataGenerator(random_seed=42)
    df, _ = gen.generate_dataset(n_samples=250)

    precedent = PrecedentEngine(n_neighbors=25, random_seed=42)
    precedent.fit(df)

    event = df.iloc[0].to_dict()
    query_res = precedent.query_precedents(event, candidate_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value)

    assert query_res["precedent_count"] == 25
    assert "empirical_recovery_rates" in query_res
    assert "counter_evidence_summary" in query_res
    assert len(query_res["counter_evidence_summary"]) > 10
