from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from .eligibility import assess
from .integrity import validate
from .models import (
    CalculationRequest,
    CalculationResult,
    CountryCreditAccount,
    EventDerivation,
    ResultStatus,
    SummaryDerivation,
    to_primitive,
)


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _fingerprint(request: CalculationRequest) -> str:
    primitive = to_primitive(request)
    primitive.pop("audit_reviews", None)
    payload = json.dumps(primitive, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def calculate(request: CalculationRequest) -> CalculationResult:
    integrity = validate(request)
    scoped_request = CalculationRequest(
        questionnaire=request.questionnaire,
        events=integrity.active_events,
        observations=request.observations,
        exchange_rates=request.exchange_rates,
        audit_reviews=request.audit_reviews,
        rule_snapshot=request.rule_snapshot,
    )
    eligibility = assess(scoped_request)
    allowed_ids = set(eligibility.calculable_event_ids)
    rates = {item.currency.upper(): item for item in request.exchange_rates}

    category_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    country_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    country_reported_tax: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    country_eligible_tax: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    observations = {item.id: item for item in request.observations}
    event_derivations: list[EventDerivation] = []

    for event in integrity.active_events:
        if event.id not in allowed_ids:
            continue
        rate = rates[event.currency.upper()]  # eligibility guarantees presence
        gross_cny = money(event.gross_amount * rate.cny_per_unit)
        tax_rate = rates[event.foreign_tax_currency.upper()]
        reported_cny = money((event.foreign_tax_reported or Decimal("0")) * tax_rate.cny_per_unit)
        eligible_cny = money((event.foreign_tax_eligible or Decimal("0")) * tax_rate.cny_per_unit)
        category_income[event.category.value] += gross_cny
        country_income[event.country_or_region] += gross_cny
        country_reported_tax[event.country_or_region] += reported_cny
        country_eligible_tax[event.country_or_region] += eligible_cny
        evidence = next(
            (observations[item].evidence for item in event.evidence_ids if item in observations),
            None,
        )
        event_derivations.append(
            EventDerivation(
                event_id=event.id,
                file_name=evidence.file_name if evidence else "",
                page=evidence.page if evidence else 0,
                locator=evidence.locator if evidence else "",
                excerpt=evidence.excerpt if evidence else "",
                gross_amount=event.gross_amount,
                currency=event.currency,
                cny_per_unit=rate.cny_per_unit,
                rate_date=rate.rate_date,
                rate_source=rate.source,
                gross_cny=gross_cny,
                foreign_tax_reported=event.foreign_tax_reported or Decimal("0"),
                foreign_tax_eligible=event.foreign_tax_eligible or Decimal("0"),
                foreign_tax_currency=event.foreign_tax_currency,
                foreign_tax_cny_per_unit=tax_rate.cny_per_unit,
                foreign_tax_reported_cny=reported_cny,
                foreign_tax_eligible_cny=eligible_cny,
                formula=(
                    f"{event.gross_amount} {event.currency} × {rate.cny_per_unit} "
                    f"CNY/{event.currency} = {gross_cny} CNY"
                ),
            )
        )

    category_income = {key: money(value) for key, value in category_income.items()}
    category_tax = {
        key: money(value * request.rule_snapshot.rate) for key, value in category_income.items()
    }
    accounts: list[CountryCreditAccount] = []
    for country in sorted(country_income):
        income = money(country_income[country])
        limit = money(income * request.rule_snapshot.rate)
        eligible = money(country_eligible_tax[country])
        used = min(eligible, limit)
        accounts.append(
            CountryCreditAccount(
                country_or_region=country,
                taxable_income_cny=income,
                credit_limit_cny=limit,
                reported_foreign_tax_cny=money(country_reported_tax[country]),
                eligible_foreign_tax_cny=eligible,
                credit_used_cny=money(used),
                excess_not_used_cny=money(max(Decimal("0"), eligible - used)),
            )
        )

    taxable_income = money(sum(category_income.values(), Decimal("0")))
    tax_before_credit = money(sum(category_tax.values(), Decimal("0")))
    credit_used = money(sum((item.credit_used_cny for item in accounts), Decimal("0")))
    supplemental_value = money(max(Decimal("0"), tax_before_credit - credit_used))
    summary_derivations = (
        SummaryDerivation(
            "tax_before_credit",
            "范围内应纳税额",
            f"{taxable_income} × {request.rule_snapshot.rate} = {tax_before_credit} CNY",
            tax_before_credit,
        ),
        SummaryDerivation(
            "credit_used",
            "本次采用的境外抵免",
            "按国家（地区）分别取符合条件已缴税额与抵免限额的较小值后求和",
            credit_used,
        ),
        SummaryDerivation(
            "supplemental_tax",
            "范围内预计补税",
            f"max(0, {tax_before_credit} - {credit_used}) = {supplemental_value} CNY",
            supplemental_value,
        ),
    ) if allowed_ids else ()
    pending = tuple(integrity.pending_items + eligibility.pending_items)
    if not allowed_ids:
        status = ResultStatus.MATERIALS_ONLY
        supplemental = None
    elif any(item.blocking for item in pending):
        status = ResultStatus.RANGE_ESTIMATE_WITH_PENDING
        supplemental = supplemental_value
    else:
        status = ResultStatus.FINAL_RANGE_RESULT
        supplemental = supplemental_value

    return CalculationResult(
        status=status,
        fingerprint=_fingerprint(request),
        tax_year=request.questionnaire.tax_year,
        rule_snapshot_version=request.rule_snapshot.version,
        included_event_ids=tuple(sorted(allowed_ids)),
        category_income_cny=category_income,
        category_tax_cny=category_tax,
        country_credit_accounts=tuple(accounts),
        taxable_income_cny=taxable_income,
        tax_before_credit_cny=tax_before_credit,
        credit_used_cny=credit_used,
        range_supplemental_tax_cny=supplemental,
        event_derivations=tuple(event_derivations),
        summary_derivations=summary_derivations,
        pending_items=pending,
    )
