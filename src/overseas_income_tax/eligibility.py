from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from .models import (
    CalculationRequest,
    FilingScenario,
    IncomeCategory,
    PendingItem,
    ResidencyStatus,
    ReviewStatus,
)


@dataclass(frozen=True)
class EligibilityDecision:
    calculable_event_ids: tuple[str, ...]
    pending_items: tuple[PendingItem, ...]

    @property
    def can_label_complete(self) -> bool:
        return bool(self.calculable_event_ids) and not any(
            item.blocking for item in self.pending_items
        )


def assess(request: CalculationRequest) -> EligibilityDecision:
    pending: list[PendingItem] = []
    q = request.questionnaire

    if q.residency_status is not ResidencyStatus.CONFIRMED_CHINA_RESIDENT:
        pending.append(PendingItem("residency_unconfirmed", "居民身份未确认，只整理材料。"))
    if q.filing_scenario is not FilingScenario.ANNUAL_RETURN:
        pending.append(
            PendingItem(
                "filing_scenario_out_of_scope",
                "补报、更正或已有预缴不在 V1 自动测算范围内。",
            )
        )
    if not q.same_country_other_income_reviewed:
        pending.append(PendingItem("country_coverage_unknown", "尚未核对同一国家（地区）的其他所得。"))
    if not q.prior_credit_balance_reviewed or q.has_prior_credit_balance:
        pending.append(PendingItem("prior_credit_unresolved", "历史未抵免余额未确认或需要处理。"))
    if not q.refund_or_correction_reviewed or q.has_refund_or_correction:
        pending.append(PendingItem("refund_correction_unresolved", "境外退税或更正事项未确认或需要处理。"))

    rate_counts = Counter(rate.currency.upper() for rate in request.exchange_rates)
    valid_rates: set[str] = set()
    expected_rate_date = date(q.tax_year, 12, 31)
    for rate in request.exchange_rates:
        currency = rate.currency.upper()
        rate_issues: list[str] = []
        if rate_counts[currency] > 1:
            rate_issues.append("同一币种存在多条汇率记录")
        if rate.cny_per_unit <= 0:
            rate_issues.append("汇率必须大于 0")
        if rate.quote_unit not in (1, 100):
            rate_issues.append("报价单位只能是每 1 或每 100 原币")
        if rate.rule_code != request.rule_snapshot.exchange_rule_code:
            rate_issues.append("汇率规则编号与规则快照不一致")
        if q.filing_scenario is FilingScenario.ANNUAL_RETURN and rate.rate_date != expected_rate_date:
            rate_issues.append(f"正常年度申报应核对 {expected_rate_date.isoformat()} 的适用报价")
        if not rate.source.strip():
            rate_issues.append("汇率缺少来源")
        if rate_issues:
            for issue in rate_issues:
                pending.append(PendingItem("exchange_rate_unresolved", f"{currency}：{issue}。"))
        else:
            valid_rates.add(currency)
    calculable: list[str] = []
    for event in request.events:
        if event.review_status is ReviewStatus.REJECTED:
            continue
        issues: list[str] = []
        if event.review_status is not ReviewStatus.CONFIRMED:
            issues.append("候选事实尚未确认")
        if event.category not in (IncomeCategory.INTEREST, IncomeCategory.DIVIDEND):
            issues.append("所得类别不在 V1 自动计算范围")
        if not event.nature_confirmed:
            issues.append("所得性质未确认")
        if not event.country_or_region or not event.source_confirmed:
            issues.append("来源国家（地区）未确认")
        if not event.currency or event.currency.upper() not in valid_rates:
            issues.append("缺少适用汇率记录")
        if not event.foreign_tax_currency or event.foreign_tax_currency.upper() not in valid_rates:
            issues.append("境外税款币种缺少适用汇率记录")
        if event.gross_amount is None or event.gross_amount < 0:
            issues.append("税前收入金额无效")
        if event.foreign_tax_reported is None or event.foreign_tax_reported < 0:
            issues.append("报表扣税额无效")
        if event.foreign_tax_eligible is not None and event.foreign_tax_eligible < 0:
            issues.append("符合条件的境外已缴税额无效")
        if not event.foreign_tax_confirmed or event.foreign_tax_eligible is None:
            issues.append("符合条件的境外已缴税额未确认")
        if not event.evidence_ids:
            issues.append("缺少证据定位")
        if event.review_status is ReviewStatus.CONFIRMED and not event.review_reason:
            issues.append("确认或修改原因未记录")

        if issues:
            for issue in issues:
                pending.append(PendingItem("event_unresolved", issue, event.id))
        else:
            calculable.append(event.id)

    if not request.events:
        pending.append(PendingItem("no_events", "尚未录入任何经济事项。"))
    return EligibilityDecision(tuple(calculable), tuple(pending))
