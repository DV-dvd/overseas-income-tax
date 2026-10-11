from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


API_VERSION = "v1"
CONTRACT_VERSION = "1.1.0"


def capabilities() -> dict[str, Any]:
    return {
        "name": "overseas-income-tax",
        "contract_version": CONTRACT_VERSION,
        "api_version": API_VERSION,
        "agent_vendor_neutral": True,
        "interfaces": {
            "python": "overseas_income_tax.calculate",
            "cli": {
                "calculate": "overseas-income-tax calculate --input request.json",
                "export": "overseas-income-tax export --input request.json --output result.xlsx",
                "extract": "overseas-income-tax extract --input statement.pdf",
                "serve": "overseas-income-tax serve",
            },
            "http": {
                "capabilities": "/api/v1/capabilities",
                "schema": "/api/v1/schema/calculation-request",
                "calculate": "/api/v1/calculate",
                "extract": "/api/v1/extract",
                "export": "/api/v1/export.xlsx",
            },
        },
        "runtime": {
            "model_required": False,
            "network_required_for_calculation": False,
            "persistent_storage": False,
            "default_bind": "127.0.0.1",
        },
        "recognition": {
            "mode": "rule_first",
            "supported_templates": ["irs_1042_s"],
            "candidate_values_require_human_confirmation": True,
            "unsupported_templates": "materials_only",
        },
        "scope": {
            "automatic_calculation": ["verified_interest", "verified_ordinary_cash_dividend"],
            "materials_only": [
                "capital_gain",
                "complex_product",
                "uncertain_source",
                "special_residency",
                "late_or_corrected_filing",
            ],
        },
    }


def calculation_request_schema() -> dict[str, Any]:
    resource = files("overseas_income_tax").joinpath(
        "schemas/calculation-request.schema.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))
