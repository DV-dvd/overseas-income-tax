from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import CalculationRequest, EconomicEvent, PendingItem, RawObservation, ReviewStatus


@dataclass(frozen=True)
class IntegrityResult:
    active_events: tuple[EconomicEvent, ...]
    pending_items: tuple[PendingItem, ...]


def validate(request: CalculationRequest) -> IntegrityResult:
    pending: list[PendingItem] = []
    observations = {item.id: item for item in request.observations}

    duplicate_files: dict[str, set[str]] = defaultdict(set)
    for observation in request.observations:
        if observation.evidence.page < 1 or not observation.evidence.locator.strip():
            pending.append(
                PendingItem(
                    "invalid_evidence_location",
                    "证据页码或原文定位无效。",
                    blocking=True,
                )
            )
        duplicate_files[observation.evidence.document_sha256].add(
            observation.evidence.file_name
        )
    for digest, names in duplicate_files.items():
        if len(names) > 1:
            pending.append(
                PendingItem(
                    "duplicate_file_upload",
                    f"检测到内容相同的重复文件：{', '.join(sorted(names))}（{digest[:8]}…）。",
                    blocking=False,
                )
            )

    by_amendment: dict[str, list[EconomicEvent]] = defaultdict(list)
    for event in request.events:
        if event.amendment_key:
            by_amendment[event.amendment_key].append(event)

    superseded_ids: set[str] = set()
    conflicted_ids: set[str] = set()
    for key, versions in by_amendment.items():
        confirmed = [event for event in versions if event.review_status is ReviewStatus.CONFIRMED]
        if len(confirmed) > 1:
            highest = max(event.revision for event in confirmed)
            winners = [event for event in confirmed if event.revision == highest]
            if len(winners) != 1:
                signatures = {
                    (
                        event.category,
                        event.country_or_region,
                        event.currency,
                        event.foreign_tax_currency,
                        event.gross_amount,
                        event.foreign_tax_reported,
                        event.foreign_tax_eligible,
                        event.occurred_on,
                    )
                    for event in winners
                }
                if len(signatures) == 1:
                    retained = min(winners, key=lambda event: event.id)
                    superseded_ids.update(event.id for event in confirmed if event is not retained)
                    pending.append(
                        PendingItem(
                            "duplicate_form_copy_collapsed",
                            f"修订组 {key} 的同版本副本字段一致，仅保留 {retained.id} 计税。",
                            retained.id,
                            blocking=False,
                        )
                    )
                else:
                    conflicted_ids.update(event.id for event in confirmed)
                    pending.append(
                        PendingItem(
                            "amendment_conflict",
                            f"修订组 {key} 存在并列有效版本且字段冲突，整组未进入计税。",
                        )
                    )
                continue
            superseded_ids.update(event.id for event in confirmed if event is not winners[0])

    def aggregation_level(event: EconomicEvent) -> str:
        levels = {
            observations[evidence_id].fields.get("aggregation_level", "")
            for evidence_id in event.evidence_ids
            if evidence_id in observations
        }
        return next((level for level in levels if level), "")

    summary_ids = {
        event.id
        for event in request.events
        if any(observations[evidence_id].is_summary_row for evidence_id in event.evidence_ids if evidence_id in observations)
    }
    detail_events = [
        event
        for event in request.events
        if event.review_status is not ReviewStatus.REJECTED
        and event.id not in superseded_ids | conflicted_ids | summary_ids
        and aggregation_level(event) == "transaction_detail"
    ]
    reconciliation_ids: set[str] = set()
    for aggregate in request.events:
        if (
            aggregate.review_status is ReviewStatus.REJECTED
            or aggregate.id in superseded_ids | conflicted_ids | summary_ids
            or aggregation_level(aggregate) != "form_summary"
        ):
            continue
        overlaps = any(
            detail.category == aggregate.category
            and detail.currency == aggregate.currency
            and (
                not detail.country_or_region
                or not aggregate.country_or_region
                or detail.country_or_region == aggregate.country_or_region
            )
            for detail in detail_events
        )
        if overlaps:
            reconciliation_ids.add(aggregate.id)
            pending.append(
                PendingItem(
                    "aggregate_detail_reconciliation_required",
                    "同时存在汇总表和逐笔明细。请核对覆盖范围后，将该汇总事项标记为“汇总凭证，不重复计税”，或删除重复事项。",
                    aggregate.id,
                )
            )

    active: list[EconomicEvent] = []
    seen_exact_events: dict[tuple[object, ...], str] = {}
    for event in request.events:
        if event.id in superseded_ids or event.id in conflicted_ids or event.id in reconciliation_ids or event.review_status is ReviewStatus.REJECTED:
            continue
        missing_evidence = [evidence_id for evidence_id in event.evidence_ids if evidence_id not in observations]
        if missing_evidence:
            pending.append(
                PendingItem(
                    "missing_evidence",
                    f"经济事项引用了不存在的观察值：{', '.join(missing_evidence)}。",
                    event.id,
                )
            )
        if any(observations[item].is_summary_row for item in event.evidence_ids if item in observations):
            pending.append(
                PendingItem(
                    "summary_row_not_tax_input",
                    "该事项已作为汇总凭证用于勾稽，不重复进入计税明细。",
                    event.id,
                    blocking=False,
                )
            )
            continue
        evidence_signature = tuple(
            sorted(
                (
                    observations[evidence_id].evidence.document_sha256,
                    observations[evidence_id].evidence.page,
                    observations[evidence_id].evidence.locator,
                )
                for evidence_id in event.evidence_ids
                if evidence_id in observations
            )
        )
        exact_signature = (
            event.category,
            event.country_or_region,
            event.currency,
            event.foreign_tax_currency,
            event.gross_amount,
            event.foreign_tax_reported,
            event.foreign_tax_eligible,
            event.occurred_on,
            evidence_signature,
        )
        if evidence_signature and exact_signature in seen_exact_events:
            pending.append(
                PendingItem(
                    "exact_duplicate_collapsed",
                    f"与 {seen_exact_events[exact_signature]} 来自相同文件位置且字段完全一致，未重复计税。",
                    event.id,
                    blocking=False,
                )
            )
            continue
        seen_exact_events[exact_signature] = event.id
        active.append(event)

    # 日期与金额相同并不足以判定重复。仅提示复核，不自动删除。
    signatures: dict[tuple[object, ...], list[str]] = defaultdict(list)
    for event in active:
        signatures[(event.occurred_on, event.gross_amount, event.currency, event.category)].append(event.id)
    for ids in signatures.values():
        if len(ids) > 1:
            pending.append(
                PendingItem(
                    "same_date_amount_review",
                    f"同日同额事项需人工确认，系统未自动去重：{', '.join(ids)}。",
                    blocking=False,
                )
            )

    return IntegrityResult(tuple(active), tuple(pending))
