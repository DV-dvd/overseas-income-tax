from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from overseas_income_tax.engine import calculate
from overseas_income_tax.models import (
    AuditReview,
    AuditStatus,
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


def observation(identifier: str, *, digest: str | None = None, summary: bool = False) -> RawObservation:
    return RawObservation(
        id=f"o-{identifier}",
        evidence=EvidenceLocation(digest or f"hash-{identifier}", f"{identifier}.pdf", 1, "box"),
        fields={"gross": "1000"},
        is_summary_row=summary,
    )


def event(identifier: str, **changes) -> EconomicEvent:
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
        evidence_ids=(f"o-{identifier}",),
        review_status=ReviewStatus.CONFIRMED,
        review_reason="与原始材料逐项核对",
        source_confirmed=True,
        nature_confirmed=True,
        foreign_tax_confirmed=True,
    )
    return replace(base, **changes)


def request(*events: EconomicEvent, observations=None) -> CalculationRequest:
    return CalculationRequest(
        questionnaire=Questionnaire(
            tax_year=2025,
            residency_status=ResidencyStatus.CONFIRMED_CHINA_RESIDENT,
            filing_scenario=FilingScenario.ANNUAL_RETURN,
            same_country_other_income_reviewed=True,
            prior_credit_balance_reviewed=True,
            refund_or_correction_reviewed=True,
        ),
        events=tuple(events),
        observations=tuple(observations or [observation(item.id) for item in events]),
        exchange_rates=(
            ExchangeRateRecord(
                "USD",
                Decimal("7"),
                date(2025, 12, 31),
                1,
                "official-source",
                "PIT-REG-32-ANNUAL-BALANCE",
            ),
        ),
    )


def test_deterministic_tax_and_country_credit_account():
    result = calculate(request(event("one")))
    assert result.status is ResultStatus.FINAL_RANGE_RESULT
    assert result.taxable_income_cny == Decimal("7000.00")
    assert result.tax_before_credit_cny == Decimal("1400.00")
    assert result.credit_used_cny == Decimal("700.00")
    assert result.range_supplemental_tax_cny == Decimal("700.00")
    assert result.country_credit_accounts[0].credit_limit_cny == Decimal("1400.00")


def test_out_of_scope_event_blocks_full_year_label_but_keeps_supported_estimate():
    supported = event("supported")
    capital_gain = event("gain", category=IncomeCategory.CAPITAL_GAIN)
    result = calculate(request(supported, capital_gain))
    assert result.status is ResultStatus.RANGE_ESTIMATE_WITH_PENDING
    assert result.included_event_ids == ("supported",)
    assert any(item.event_id == "gain" and item.blocking for item in result.pending_items)


def test_same_date_and_amount_are_not_automatically_deduplicated():
    first = event("first")
    second = event("second")
    result = calculate(request(first, second))
    assert result.taxable_income_cny == Decimal("14000.00")
    assert any(item.code == "same_date_amount_review" and not item.blocking for item in result.pending_items)


def test_amended_event_supersedes_original_with_same_amendment_key():
    original = event("original", amendment_key="form-1", revision=0)
    amended = event(
        "amended",
        amendment_key="form-1",
        revision=1,
        gross_amount=Decimal("1200"),
        supersedes_event_id="original",
    )
    result = calculate(request(original, amended))
    assert result.included_event_ids == ("amended",)
    assert result.taxable_income_cny == Decimal("8400.00")


def test_same_revision_form_copies_with_identical_fields_are_counted_once():
    copy_b = event("copy-b", amendment_key="form-copy", revision=0)
    copy_c = event("copy-c", amendment_key="form-copy", revision=0)
    result = calculate(request(copy_b, copy_c))
    assert result.taxable_income_cny == Decimal("7000.00")
    assert len(result.included_event_ids) == 1
    assert any(item.code == "duplicate_form_copy_collapsed" for item in result.pending_items)


def test_conflicting_same_revision_forms_are_all_excluded():
    first = event("first", amendment_key="form-conflict", revision=1)
    second = event(
        "second",
        amendment_key="form-conflict",
        revision=1,
        gross_amount=Decimal("1200"),
    )
    result = calculate(request(first, second))
    assert result.status is ResultStatus.MATERIALS_ONLY
    assert result.taxable_income_cny == Decimal("0.00")
    assert result.included_event_ids == ()
    assert any(item.code == "amendment_conflict" and item.blocking for item in result.pending_items)


def test_summary_row_is_a_blocking_integrity_issue():
    item = event("summary")
    result = calculate(request(item, observations=[observation("summary", summary=True)]))
    assert result.status is ResultStatus.RANGE_ESTIMATE_WITH_PENDING
    assert any(item.code == "summary_row_not_tax_input" for item in result.pending_items)


def test_duplicate_upload_of_same_evidence_does_not_change_result():
    first = event("first")
    second = event("second")
    observations = [observation("first", digest="same"), observation("second", digest="same")]
    result = calculate(request(first, second, observations=observations))
    assert result.taxable_income_cny == Decimal("7000.00")
    assert any(item.code == "duplicate_file_upload" for item in result.pending_items)
    assert any(item.code == "exact_duplicate_collapsed" for item in result.pending_items)


def test_fingerprint_changes_when_a_fact_changes():
    first = calculate(request(event("one")))
    second = calculate(request(event("one", gross_amount=Decimal("1000.01"))))
    assert first.fingerprint != second.fingerprint


def test_wrong_exchange_rate_date_blocks_calculation():
    calculation_request = request(event("one"))
    bad_rate = replace(calculation_request.exchange_rates[0], rate_date=date(2025, 12, 30))
    result = calculate(replace(calculation_request, exchange_rates=(bad_rate,)))
    assert result.status is ResultStatus.MATERIALS_ONLY
    assert any(item.code == "exchange_rate_unresolved" for item in result.pending_items)


def test_duplicate_currency_rates_are_ambiguous_and_not_calculated():
    calculation_request = request(event("one"))
    second_rate = replace(calculation_request.exchange_rates[0], source="another official record")
    result = calculate(replace(calculation_request, exchange_rates=calculation_request.exchange_rates + (second_rate,)))
    assert result.status is ResultStatus.MATERIALS_ONLY


def test_unconfirmed_candidate_never_enters_calculation():
    candidate = event("candidate", review_status=ReviewStatus.CANDIDATE)
    result = calculate(request(candidate))
    assert result.status is ResultStatus.MATERIALS_ONLY
    assert result.included_event_ids == ()
    assert any(item.event_id == "candidate" and "尚未确认" in item.message for item in result.pending_items)


def test_audit_record_does_not_change_financial_fingerprint():
    calculation_request = request(event("one"))
    before = calculate(calculation_request)
    reviewed = replace(
        calculation_request,
        audit_reviews=(AuditReview("one", AuditStatus.CONSISTENT),),
    )
    after = calculate(reviewed)
    assert after.fingerprint == before.fingerprint
    assert after.range_supplemental_tax_cny == before.range_supplemental_tax_cny


def test_result_contains_reproducible_event_and_summary_derivations():
    result = calculate(request(event("one")))
    assert result.event_derivations[0].formula == "1000 USD × 7 CNY/USD = 7000.00 CNY"
    assert result.event_derivations[0].file_name == "one.pdf"
    assert result.summary_derivations[-1].result_cny == Decimal("700.00")
