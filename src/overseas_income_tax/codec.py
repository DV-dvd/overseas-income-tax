from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import (
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
    ReviewStatus,
)


class InputError(ValueError):
    pass


def _decimal(value: Any, field: str, *, optional: bool = False) -> Decimal | None:
    if optional and (value is None or value == ""):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError) as exc:
        raise InputError(f"{field} 必须是有效数字。") from exc


def _date(value: Any, field: str, *, optional: bool = False) -> date | None:
    if optional and not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise InputError(f"{field} 必须使用 YYYY-MM-DD 格式。") from exc


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise InputError(f"{field} 必须是布尔值。")
    return value


def request_from_dict(payload: dict[str, Any]) -> CalculationRequest:
    try:
        questionnaire_payload = payload["questionnaire"]
        q = Questionnaire(
            tax_year=int(questionnaire_payload["tax_year"]),
            residency_status=ResidencyStatus(questionnaire_payload["residency_status"]),
            filing_scenario=FilingScenario(questionnaire_payload["filing_scenario"]),
            same_country_other_income_reviewed=_boolean(questionnaire_payload.get("same_country_other_income_reviewed"), "同国其他所得核对状态"),
            prior_credit_balance_reviewed=_boolean(questionnaire_payload.get("prior_credit_balance_reviewed"), "历史抵免核对状态"),
            refund_or_correction_reviewed=_boolean(questionnaire_payload.get("refund_or_correction_reviewed"), "退税更正核对状态"),
            has_prior_credit_balance=_boolean(questionnaire_payload.get("has_prior_credit_balance", False), "历史抵免余额状态"),
            has_refund_or_correction=_boolean(questionnaire_payload.get("has_refund_or_correction", False), "退税更正状态"),
        )
    except InputError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError("适用性问卷缺少必填项或选项无效。") from exc

    observations: list[RawObservation] = []
    for index, item in enumerate(payload.get("observations", []), start=1):
        try:
            evidence = item["evidence"]
            observations.append(
                RawObservation(
                    id=str(item["id"]),
                    evidence=EvidenceLocation(
                        document_sha256=str(evidence["document_sha256"]),
                        file_name=str(evidence["file_name"]),
                        page=int(evidence["page"]),
                        locator=str(evidence.get("locator", "")),
                        excerpt=str(evidence.get("excerpt", "")),
                    ),
                    fields={str(key): str(value) for key, value in item.get("fields", {}).items()},
                    is_summary_row=_boolean(item.get("is_summary_row", False), "汇总行标记"),
                )
            )
        except InputError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(f"第 {index} 条原始观察值格式无效。") from exc

    events: list[EconomicEvent] = []
    for index, item in enumerate(payload.get("events", []), start=1):
        try:
            income_currency = str(item["currency"]).strip().upper()
            events.append(
                EconomicEvent(
                    id=str(item["id"]),
                    category=IncomeCategory(item["category"]),
                    country_or_region=(str(item["country_or_region"]).strip() or None),
                    currency=(income_currency or None),
                    foreign_tax_currency=(str(item.get("foreign_tax_currency") or income_currency).strip().upper() or None),
                    gross_amount=_decimal(item.get("gross_amount"), "税前收入", optional=True),
                    foreign_tax_reported=_decimal(item.get("foreign_tax_reported"), "报表扣税额", optional=True),
                    foreign_tax_eligible=_decimal(item.get("foreign_tax_eligible"), "符合条件的境外已缴税额", optional=True),
                    occurred_on=_date(item.get("occurred_on"), "收入日期", optional=True),
                    evidence_ids=tuple(str(value) for value in item.get("evidence_ids", [])),
                    review_status=ReviewStatus(item.get("review_status", "candidate")),
                    review_reason=str(item.get("review_reason", "")),
                    source_confirmed=_boolean(item.get("source_confirmed", False), "来源地确认状态"),
                    nature_confirmed=_boolean(item.get("nature_confirmed", False), "所得性质确认状态"),
                    foreign_tax_confirmed=_boolean(item.get("foreign_tax_confirmed", False), "境外税款确认状态"),
                    amendment_key=(str(item["amendment_key"]) if item.get("amendment_key") else None),
                    revision=int(item.get("revision", 0)),
                    supersedes_event_id=(str(item["supersedes_event_id"]) if item.get("supersedes_event_id") else None),
                )
            )
        except InputError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(f"第 {index} 条经济事项格式无效。") from exc

    rates: list[ExchangeRateRecord] = []
    for index, item in enumerate(payload.get("exchange_rates", []), start=1):
        try:
            rates.append(
                ExchangeRateRecord(
                    currency=str(item["currency"]).upper(),
                    cny_per_unit=_decimal(item["cny_per_unit"], "汇率"),
                    rate_date=_date(item["rate_date"], "汇率日期"),
                    quote_unit=int(item.get("quote_unit", 1)),
                    source=str(item["source"]),
                    rule_code=str(item["rule_code"]),
                )
            )
        except InputError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(f"第 {index} 条汇率记录格式无效。") from exc

    audit_reviews: list[AuditReview] = []
    for index, item in enumerate(payload.get("audit_reviews", []), start=1):
        try:
            audit_reviews.append(
                AuditReview(
                    event_id=str(item["event_id"]),
                    status=AuditStatus(item["status"]),
                    note=str(item.get("note", "")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(f"第 {index} 条抽检记录格式无效。") from exc

    observation_ids = [item.id for item in observations]
    event_ids = [item.id for item in events]
    event_id_set = set(event_ids)
    audit_event_ids = [item.event_id for item in audit_reviews]
    if len(observation_ids) != len(set(observation_ids)):
        raise InputError("原始观察值 ID 不能重复。")
    if len(event_ids) != len(set(event_ids)):
        raise InputError("经济事项 ID 不能重复。")
    if len(audit_event_ids) != len(set(audit_event_ids)):
        raise InputError("同一经济事项不能存在多条抽检记录。")
    if any(item.event_id not in event_id_set for item in audit_reviews):
        raise InputError("抽检记录必须引用当前请求中的经济事项。")
    if any(item.status is AuditStatus.INCONSISTENT and not item.note.strip() for item in audit_reviews):
        raise InputError("抽检结果不一致时必须填写备注。")
    return CalculationRequest(
        q,
        tuple(events),
        tuple(observations),
        tuple(rates),
        tuple(audit_reviews),
    )
