from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


class IncomeCategory(StrEnum):
    INTEREST = "interest"
    DIVIDEND = "dividend"
    CAPITAL_GAIN = "capital_gain"
    COMPLEX_PRODUCT = "complex_product"
    OTHER = "other"


class ReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ResidencyStatus(StrEnum):
    CONFIRMED_CHINA_RESIDENT = "confirmed_china_resident"
    UNCERTAIN = "uncertain"
    SPECIAL_NO_DOMICILE = "special_no_domicile"


class FilingScenario(StrEnum):
    ANNUAL_RETURN = "annual_return"
    LATE_PRIOR_YEAR = "late_prior_year"
    PRIOR_PREPAYMENT = "prior_prepayment"
    CORRECTION = "correction"


class ResultStatus(StrEnum):
    FINAL_RANGE_RESULT = "final_range_result"
    RANGE_ESTIMATE_WITH_PENDING = "range_estimate_with_pending"
    MATERIALS_ONLY = "materials_only"


class AuditStatus(StrEnum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"


@dataclass(frozen=True)
class EvidenceLocation:
    document_sha256: str
    file_name: str
    page: int
    locator: str
    excerpt: str = ""


@dataclass(frozen=True)
class RawObservation:
    id: str
    evidence: EvidenceLocation
    fields: dict[str, str]
    is_summary_row: bool = False


@dataclass(frozen=True)
class EconomicEvent:
    id: str
    category: IncomeCategory
    country_or_region: str | None
    currency: str | None
    foreign_tax_currency: str | None
    gross_amount: Decimal | None
    foreign_tax_reported: Decimal | None
    foreign_tax_eligible: Decimal | None
    occurred_on: date | None
    evidence_ids: tuple[str, ...]
    review_status: ReviewStatus = ReviewStatus.CANDIDATE
    review_reason: str = ""
    source_confirmed: bool = False
    nature_confirmed: bool = False
    foreign_tax_confirmed: bool = False
    amendment_key: str | None = None
    revision: int = 0
    supersedes_event_id: str | None = None


@dataclass(frozen=True)
class Questionnaire:
    tax_year: int
    residency_status: ResidencyStatus
    filing_scenario: FilingScenario
    same_country_other_income_reviewed: bool
    prior_credit_balance_reviewed: bool
    refund_or_correction_reviewed: bool
    has_prior_credit_balance: bool = False
    has_refund_or_correction: bool = False


@dataclass(frozen=True)
class ExchangeRateRecord:
    currency: str
    cny_per_unit: Decimal
    rate_date: date
    quote_unit: int
    source: str
    rule_code: str


@dataclass(frozen=True)
class RuleSnapshot:
    version: str
    effective_date: date
    rate: Decimal
    supported_categories: tuple[IncomeCategory, ...]
    exchange_rule_code: str
    source_urls: tuple[str, ...]


RULE_SNAPSHOT = RuleSnapshot(
    version="v1-2026-10-11",
    effective_date=date(2026, 10, 11),
    rate=Decimal("0.20"),
    supported_categories=(IncomeCategory.INTEREST, IncomeCategory.DIVIDEND),
    exchange_rule_code="PIT-REG-32-ANNUAL-BALANCE",
    source_urls=(
        "https://www.chinatax.gov.cn/chinatax/n810219/n810744/n3752930/n3752974/c3963364/content.html",
        "https://12366.chinatax.gov.cn/bzds/082/082-5-4.html",
    ),
)


@dataclass(frozen=True)
class PendingItem:
    code: str
    message: str
    event_id: str | None = None
    blocking: bool = True


@dataclass(frozen=True)
class CountryCreditAccount:
    country_or_region: str
    taxable_income_cny: Decimal
    credit_limit_cny: Decimal
    reported_foreign_tax_cny: Decimal
    eligible_foreign_tax_cny: Decimal
    credit_used_cny: Decimal
    excess_not_used_cny: Decimal


@dataclass(frozen=True)
class EventDerivation:
    event_id: str
    file_name: str
    page: int
    locator: str
    excerpt: str
    gross_amount: Decimal
    currency: str
    cny_per_unit: Decimal
    rate_date: date
    rate_source: str
    gross_cny: Decimal
    foreign_tax_reported: Decimal
    foreign_tax_eligible: Decimal
    foreign_tax_currency: str
    foreign_tax_cny_per_unit: Decimal
    foreign_tax_reported_cny: Decimal
    foreign_tax_eligible_cny: Decimal
    formula: str


@dataclass(frozen=True)
class SummaryDerivation:
    code: str
    label: str
    formula: str
    result_cny: Decimal


@dataclass(frozen=True)
class AuditReview:
    event_id: str
    status: AuditStatus
    note: str = ""


@dataclass(frozen=True)
class CalculationRequest:
    questionnaire: Questionnaire
    events: tuple[EconomicEvent, ...]
    observations: tuple[RawObservation, ...]
    exchange_rates: tuple[ExchangeRateRecord, ...]
    audit_reviews: tuple[AuditReview, ...] = field(default_factory=tuple)
    rule_snapshot: RuleSnapshot = RULE_SNAPSHOT


@dataclass(frozen=True)
class CalculationResult:
    status: ResultStatus
    fingerprint: str
    tax_year: int
    rule_snapshot_version: str
    included_event_ids: tuple[str, ...]
    category_income_cny: dict[str, Decimal]
    category_tax_cny: dict[str, Decimal]
    country_credit_accounts: tuple[CountryCreditAccount, ...]
    taxable_income_cny: Decimal
    tax_before_credit_cny: Decimal
    credit_used_cny: Decimal
    range_supplemental_tax_cny: Decimal | None
    event_derivations: tuple[EventDerivation, ...]
    summary_derivations: tuple[SummaryDerivation, ...]
    pending_items: tuple[PendingItem, ...]


def to_primitive(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, StrEnum)):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    return value
