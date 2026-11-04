"""
WAPSI Double Machine Learning (DML) Causal Uplift Estimator (src compatibility shim).
WAPSI Phase 5 — Causal Learning and Decision Intelligence.
"""

from wapsi.causal.dml import (
    MultiActionDoubleMachineLearning,
    DEFAULT_NUMERICAL_COLS,
    DEFAULT_CATEGORICAL_COLS,
)

# Alias for standard naming convention
WAPSIDMLModel = MultiActionDoubleMachineLearning

__all__ = [
    "MultiActionDoubleMachineLearning",
    "WAPSIDMLModel",
    "DEFAULT_NUMERICAL_COLS",
    "DEFAULT_CATEGORICAL_COLS",
]

