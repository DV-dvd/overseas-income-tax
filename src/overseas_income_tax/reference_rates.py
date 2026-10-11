from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ReferenceRate:
    currency: str
    cny_per_unit: Decimal
    rate_date: date
    quote_unit: int
    source: str
    rule_code: str


SOURCE_2025 = (
    "国家外汇管理局人民币汇率中间价（2025-12-31） "
    "https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do"
)


REFERENCE_RATES: dict[int, tuple[ReferenceRate, ...]] = {
    2025: (
        ReferenceRate("USD", Decimal("7.0288"), date(2025, 12, 31), 1, SOURCE_2025, "PIT-REG-32-ANNUAL-BALANCE"),
        ReferenceRate("HKD", Decimal("0.90322"), date(2025, 12, 31), 1, SOURCE_2025, "PIT-REG-32-ANNUAL-BALANCE"),
    ),
}


def rates_for_year(tax_year: int) -> tuple[ReferenceRate, ...]:
    return REFERENCE_RATES.get(tax_year, ())
