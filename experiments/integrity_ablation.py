"""Offline integrity-check ablation on synthetic adversarial packages.

This verifies that removing the integrity layer makes known failure cases worse.
It is a regression gate, not evidence of real-world accuracy. Real annotated
taxpayer-year packages remain required before a production claim.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

from overseas_income_tax.engine import calculate
from overseas_income_tax.models import (
    CalculationRequest,
    EconomicEvent,
    EvidenceLocation,
    ExchangeRateRecord,
    FilingScenario,
    IncomeCategory,
    Questionnaire,
    RawObservation,
    ResidencyStatus,
    ResultStatus,
    ReviewStatus,
)


def _event(identifier: str, observation_id: str, **changes) -> EconomicEvent:
    base = EconomicEvent(
        id=identifier,
        category=IncomeCategory.DIVIDEND,
        country_or_region="美国",
        currency="USD",
        foreign_tax_currency="USD",
        gross_amount=Decimal("1000"),
        foreign_tax_reported=Decimal("100"),
        foreign_tax_eligible=Decimal("100"),
        occurred_on=date(2025, 6, 30),
        evidence_ids=(observation_id,),
        review_status=ReviewStatus.CONFIRMED,
        review_reason="synthetic gold review",
        source_confirmed=True,
        nature_confirmed=True,
        foreign_tax_confirmed=True,
    )
    return replace(base, **changes)


def _observation(identifier: str, digest: str, *, summary: bool = False) -> RawObservation:
    return RawObservation(
        identifier,
        EvidenceLocation(digest, f"{identifier}.pdf", 1, "box-2"),
        {"gross": "1000"},
        summary,
    )


def _request(events, observations) -> CalculationRequest:
    return CalculationRequest(
        Questionnaire(
            2025,
            ResidencyStatus.CONFIRMED_CHINA_RESIDENT,
            FilingScenario.ANNUAL_RETURN,
            True,
            True,
            True,
        ),
        tuple(events),
        tuple(observations),
        (
            ExchangeRateRecord(
                "USD",
                Decimal("7"),
                date(2025, 12, 31),
                1,
                "synthetic official rate",
                "PIT-REG-32-ANNUAL-BALANCE",
            ),
        ),
    )


def cases() -> list[tuple[str, CalculationRequest, Decimal | None, bool]]:
    duplicate = _request(
        [_event("e1", "o1"), _event("e2", "o2")],
        [_observation("o1", "same-file"), _observation("o2", "same-file")],
    )
    amended = _request(
        [
            _event("original", "original-observation", amendment_key="form-1", revision=0),
            _event(
                "amended",
                "amended-observation",
                amendment_key="form-1",
                revision=1,
                gross_amount=Decimal("1200"),
                supersedes_event_id="original",
            ),
        ],
        [_observation("original-observation", "old"), _observation("amended-observation", "new")],
    )
    summary = _request(
        [_event("summary-event", "summary-observation")],
        [_observation("summary-observation", "summary", summary=True)],
    )
    return [
        ("duplicate_upload", duplicate, Decimal("7000.00"), False),
        ("amended_replaces_original", amended, Decimal("8400.00"), False),
        ("summary_not_tax_input", summary, None, True),
    ]


def _without_integrity(request: CalculationRequest) -> CalculationRequest:
    observations = tuple(
        replace(
            item,
            evidence=replace(item.evidence, document_sha256=f"unique-{index}"),
            is_summary_row=False,
        )
        for index, item in enumerate(request.observations)
    )
    events = tuple(
        replace(item, amendment_key=None, supersedes_event_id=None, revision=0)
        for item in request.events
    )
    return replace(request, events=events, observations=observations)


def run_ablation() -> dict[str, object]:
    rows = []
    with_integrity_pass = 0
    without_integrity_pass = 0
    for name, request, expected_income, should_block in cases():
        production = calculate(request)
        ablated = calculate(_without_integrity(request))
        production_ok = (
            (should_block and production.status is not ResultStatus.FINAL_RANGE_RESULT)
            or (not should_block and production.taxable_income_cny == expected_income)
        )
        ablated_ok = (
            (should_block and ablated.status is not ResultStatus.FINAL_RANGE_RESULT)
            or (not should_block and ablated.taxable_income_cny == expected_income)
        )
        with_integrity_pass += int(production_ok)
        without_integrity_pass += int(ablated_ok)
        rows.append(
            {
                "case": name,
                "with_integrity": production_ok,
                "without_integrity": ablated_ok,
                "with_status": production.status.value,
                "without_status": ablated.status.value,
            }
        )
    passed = with_integrity_pass == len(rows) and without_integrity_pass < with_integrity_pass
    return {
        "dataset": "synthetic-adversarial-v1",
        "claim_limit": "Regression evidence only; not a real-world accuracy claim.",
        "with_integrity_passed": with_integrity_pass,
        "without_integrity_passed": without_integrity_pass,
        "total": len(rows),
        "gate_passed": passed,
        "cases": rows,
    }


if __name__ == "__main__":
    result = run_ablation()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["gate_passed"] else 1)
