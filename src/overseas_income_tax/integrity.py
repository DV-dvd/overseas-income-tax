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
    for key, versions in by_amendment.items():
        confirmed = [event for event in versions if event.review_status is ReviewStatus.CONFIRMED]
        if len(confirmed) > 1:
            highest = max(event.revision for event in confirmed)
            winners = [event for event in confirmed if event.revision == highest]
            if len(winners) != 1:
                pending.append(PendingItem("amendment_conflict", f"修订组 {key} 存在并列有效版本。"))
                continue
            superseded_ids.update(event.id for event in confirmed if event is not winners[0])

    active: list[EconomicEvent] = []
    seen_exact_events: dict[tuple[object, ...], str] = {}
    for event in request.events:
        if event.id in superseded_ids or event.review_status is ReviewStatus.REJECTED:
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
                    "汇总行只能用于勾稽，不能作为计税明细。",
                    event.id,
                )
            )
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
