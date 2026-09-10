"""Business rule engine package.

Validates an application's normalized, verified evidence against a
deterministic, explainable ruleset. The rules consume only the canonical values
produced by the normalization module (``normalized_value``) plus the stored
visual detection outcomes, and persist one validation result row per executed
rule into the shared validation results table.
"""

from app.rule_engine.constants import RULE_ENGINE_VERSION
from app.rule_engine.rules import REGISTRY
from app.rule_engine.services import RuleEngineService

__all__ = [
    "REGISTRY",
    "RULE_ENGINE_VERSION",
    "RuleEngineService",
]
