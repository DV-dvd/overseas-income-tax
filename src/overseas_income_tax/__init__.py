"""Deterministic, review-first overseas income tax calculator."""

from .engine import calculate
from .contract import API_VERSION, CONTRACT_VERSION, capabilities
from .models import RULE_SNAPSHOT, CalculationRequest, CalculationResult

__all__ = [
    "API_VERSION",
    "CONTRACT_VERSION",
    "RULE_SNAPSHOT",
    "CalculationRequest",
    "CalculationResult",
    "calculate",
    "capabilities",
]
