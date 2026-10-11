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
    ResultStatus,
    to_primitive,
)


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _fingerprint(request: CalculationRequest) -> str:
    payload = json.dumps(to_primitive(request), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def calculate(request: CalculationRequest) -> CalculationResult:
    integrity = validate(request)
    scoped_request = CalculationRequest(
        questionnaire=request.questionnaire,
        events=integrity.active_events,
        observations=request.observations,
        exchange_rates=request.exchange_rates,
        rule_snapshot=request.rule_snapshot,
    )
    eligibility = assess(scoped_request)
    allowed_ids = set(eligibility.calculable_event_ids)
    rates = {item.currency.upper(): item for item in request.exchange_rates}

    category_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    country_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    country_reported_tax: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    country_eligible_tax: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

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
    pending = tuple(integrity.pending_items + eligibility.pending_items)
    if not allowed_ids:
        status = ResultStatus.MATERIALS_ONLY
        supplemental = None
    elif any(item.blocking for item in pending):
        status = ResultStatus.RANGE_ESTIMATE_WITH_PENDING
        supplemental = money(max(Decimal("0"), tax_before_credit - credit_used))
    else:
        status = ResultStatus.FINAL_RANGE_RESULT
        supplemental = money(max(Decimal("0"), tax_before_credit - credit_used))

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
        pending_items=pending,
    )
