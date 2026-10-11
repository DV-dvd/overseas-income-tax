"""Deterministic, review-first overseas income tax calculator."""

from .engine import calculate
from .models import RULE_SNAPSHOT, CalculationRequest, CalculationResult

__all__ = ["RULE_SNAPSHOT", "CalculationRequest", "CalculationResult", "calculate"]

