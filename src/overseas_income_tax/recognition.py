from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .extraction import ExtractedDocument
from .models import EvidenceLocation


@dataclass(frozen=True)
class CandidateField:
    value: Any
    confidence: str
    reason: str


@dataclass(frozen=True)
class CandidateEvent:
    id: str
    category: CandidateField
    country_or_region: CandidateField
    currency: CandidateField
    foreign_tax_currency: CandidateField
    gross_amount: CandidateField
    foreign_tax_reported: CandidateField
    foreign_tax_eligible: CandidateField
    occurred_on: CandidateField
    evidence: EvidenceLocation
    extracted_fields: dict[str, str]
    amendment_key: str | None = None
    revision: int = 0


@dataclass(frozen=True)
class DocumentRecognition:
    document_type: CandidateField
    tax_year: CandidateField
    status: str
    events: tuple[CandidateEvent, ...]
    warnings: tuple[str, ...]


INCOME_CODE_CATEGORIES = {
    "01": ("interest", "1042-S income code 01 仅作为利息候选线索"),
    "02": ("interest", "1042-S income code 02 仅作为利息候选线索"),
    "03": ("interest", "1042-S income code 03 仅作为利息候选线索"),
    "04": ("interest", "1042-S income code 04 仅作为利息候选线索"),
    "06": ("dividend", "1042-S income code 06 仅作为股息候选线索"),
}

MONEY_TOKEN = re.compile(r"-?[0-9][0-9,]*\.[0-9]{2}")
BOX_LABEL = re.compile(r"^(?:box\s*)?(?:[0-9]{1,2}[a-z]?)\b", re.IGNORECASE)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _match(text: str, pattern: str) -> str | None:
    found = re.search(pattern, text, flags=re.IGNORECASE)
    return found.group(1).strip() if found else None


def _money(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def _box_money(lines: list[str], box: str, label: str) -> Decimal | None:
    """Read only a box line or its immediate numeric value line."""
    label_pattern = re.compile(
        rf"^(?:box\s*)?{re.escape(box)}\s*[-:—]?\s*{label}\b",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        found = label_pattern.search(line)
        if not found:
            continue
        on_label = MONEY_TOKEN.search(line[found.end():])
        if on_label:
            return _money(on_label.group(0))
        for following in lines[index + 1:index + 3]:
            if re.fullmatch(r"\$?\s*-?[0-9][0-9,]*\.[0-9]{2}", following):
                return _money(following)
            if BOX_LABEL.match(following):
                break
        return None
    return None


def _income_code(lines: list[str]) -> str | None:
    inline = _match(" ".join(lines), r"(?:box\s*)?1\s*[-:—]?\s*income\s+code\s*[:\-]?\s*([0-9]{2})\b")
    if inline:
        return inline
    for index, line in enumerate(lines):
        if not re.match(r"^(?:box\s*)?1\s+income\b", line, re.IGNORECASE):
            continue
        for following in lines[index + 1:index + 4]:
            if re.fullmatch(r"[0-9]{2}", following):
                return following
            if BOX_LABEL.match(following) and not re.fullmatch(r"1\b.*", following, re.IGNORECASE):
                break
    return None


def _tax_year(text: str) -> str | None:
    explicit = _match(text, r"(?:tax\s+year|calendar\s+year|for\s+the\s+year)\s*[:\-]?\s*(20[0-9]{2})")
    if explicit:
        return explicit
    return _match(text, r"form\s+1042-s.{0,80}?\b(20[0-9]{2})\b")


def _document_type(text: str) -> CandidateField:
    lower = text.lower()
    if "1042-s" in lower or "1042s" in lower:
        return CandidateField("irs_1042_s", "high", "检测到 Form 1042-S 标识")
    if "活动报表" in text and (
        "现金红利" in text
        or "贷方利息" in text
        or "替代股息的付款" in text
        or "payment in lieu of dividend" in lower
    ):
        return CandidateField("ibkr_activity_statement", "high", "检测到券商活动报表及逐笔收益标识")
    if "statement savings account" in lower and "interest" in lower and "statement period" in lower:
        return CandidateField("bank_savings_statement", "high", "检测到储蓄账户月结单及利息交易标识")
    if "brokerage" in lower or "broker statement" in lower or "券商" in text:
        return CandidateField("broker_statement", "medium", "检测到券商报表关键词；该版式尚未验证")
    if "bank statement" in lower or "银行月结单" in text or "银行对账单" in text:
        return CandidateField("bank_statement", "medium", "检测到银行报表关键词；该版式尚未验证")
    return CandidateField("unknown", "low", "未识别到已支持的材料模板")


def _evidence(document: ExtractedDocument, page: int, locator: str, line: str) -> EvidenceLocation:
    return EvidenceLocation(document.sha256, document.file_name, page, locator, _normalized(line)[:600])


def _recognize_1042_s_page(document: ExtractedDocument, page_number: int, text: str) -> tuple[CandidateEvent | None, list[str]]:
    warnings: list[str] = []
    lines = _lines(text)
    income_code = _income_code(lines)
    gross = _box_money(lines, "2", r"gross\s+income")
    box_7a = _box_money(lines, "7a", r"federal\s+tax\s+withheld")
    box_8 = _box_money(lines, "8", r"tax\s+withheld\s+by\s+other\s+agents")
    box_9 = _box_money(lines, "9", r"overwithheld\s+tax(?:\s+repaid\s+to\s+recipient)?")
    box_10 = _box_money(lines, "10", r"total\s+withholding\s+credit")

    before_label = re.search(
        r"^\s*((?:[0-9]\s+){5,}[0-9])\s+UNIQUE\s+(?:FORM\s+)?IDENTIFIER",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    unique_id = re.sub(r"\s+", "", before_label.group(1)) if before_label else _match(
        text,
        r"unique\s+(?:form\s+)?identifier\s*[:#\-]?\s*(?!amended\b)([A-Za-z0-9\-]+)",
    )
    amendment_number = _match(text, r"amend(?:ment|ed)\s+(?:no\.?|number)?\s*[:#\-]?\s*([0-9]+)")
    amended_marked = bool(re.search(r"(?:\[x\]|☒|x)\s*amended|amended\s*[:\-]?\s*(?:yes|x|checked)", text, re.IGNORECASE))
    revision = int(amendment_number) if amendment_number else (1 if amended_marked else 0)

    if gross is None:
        warnings.append(f"第 {page_number} 页未可靠识别 Box 2 Gross income。")
    if income_code is None:
        warnings.append(f"第 {page_number} 页未可靠识别 Box 1 Income code。")
    if gross is None and income_code is None:
        return None, warnings

    category, category_reason = INCOME_CODE_CATEGORIES.get(income_code or "", ("other", "Income code 未在已验证映射内，只整理材料"))
    category_confidence = "medium" if category != "other" else "low"

    if box_10 is not None:
        reported_tax = box_10
        reported_reason = "取自 Box 10 Total withholding credit；仍需核对 7a/8/9"
        reported_confidence = "high"
    elif any(value is not None for value in (box_7a, box_8, box_9)):
        reported_tax = (box_7a or Decimal("0")) + (box_8 or Decimal("0")) - (box_9 or Decimal("0"))
        reported_reason = "由 Box 7a + Box 8 - Box 9 生成候选值，需人工核对"
        reported_confidence = "medium"
    else:
        reported_tax = None
        reported_reason = "未识别报表扣税栏位"
        reported_confidence = "low"

    event_id = f"candidate-{document.sha256[:10]}-{page_number}"
    extracted = {
        key: format(value, "f") if isinstance(value, Decimal) else (value or "")
        for key, value in {
            "income_code": income_code,
            "box_2_gross_income": gross,
            "box_7a_federal_tax_withheld": box_7a,
            "box_8_other_agents": box_8,
            "box_9_repaid": box_9,
            "box_10_total_credit": box_10,
            "unique_form_identifier": unique_id,
            "amendment_number": amendment_number,
            "aggregation_level": "form_summary",
        }.items()
    }
    return CandidateEvent(
        id=event_id,
        category=CandidateField(category, category_confidence, category_reason),
        country_or_region=CandidateField("美国", "medium", "1042-S 是美国来源预扣报表；来源地仍须人工确认"),
        currency=CandidateField("USD", "high", "1042-S 金额以美元填报"),
        foreign_tax_currency=CandidateField("USD", "high", "1042-S 扣税金额以美元填报"),
        gross_amount=CandidateField(gross, "high" if gross is not None else "low", "取自 Box 2 Gross income"),
        foreign_tax_reported=CandidateField(reported_tax, reported_confidence, reported_reason),
        foreign_tax_eligible=CandidateField(None, "low", "中国规则下可抵免金额必须由用户确认，不自动推断"),
        occurred_on=CandidateField(None, "low", "1042-S 通常不提供单笔收款日期，需用户补充"),
        evidence=EvidenceLocation(document.sha256, document.file_name, page_number, f"第{page_number}页 1042-S Boxes 1/2/7a/8/9/10", _normalized(text)[:600]),
        extracted_fields=extracted,
        amendment_key=unique_id,
        revision=revision,
    ), warnings


def _recognize_bank_statement(document: ExtractedDocument) -> tuple[list[CandidateEvent], list[str]]:
    events: list[CandidateEvent] = []
    warnings: list[str] = []
    currency: str | None = None
    sequence = 0
    currency_line = re.compile(r"^(HKD|USD|EUR|GBP|JPY|AUD|CAD|SGD)\s+\d{2}[A-Z]{3}\d{2}\s+Balance B/F\b", re.IGNORECASE)
    interest_line = re.compile(r"^(\d{2}[A-Z]{3}\d{2})\s+0000\s+INTEREST\s+利息收入\s+([0-9,]+\.[0-9]{2})\s+[0-9,]+\.[0-9]{2}\s*$", re.IGNORECASE)
    for page_number, page_text in enumerate(document.pages, start=1):
        for line in _lines(page_text):
            found_currency = currency_line.match(line)
            if found_currency:
                currency = found_currency.group(1).upper()
                continue
            found = interest_line.match(line)
            if not found:
                continue
            sequence += 1
            occurred = datetime.strptime(found.group(1).upper(), "%d%b%y").date()
            event_currency = currency or ""
            confidence = "high" if currency else "low"
            if not currency:
                warnings.append(f"第 {page_number} 页一笔利息未能关联币种，已留空等待确认。")
            events.append(CandidateEvent(
                id=f"candidate-{document.sha256[:10]}-bank-{sequence}",
                category=CandidateField("interest", "high", "逐笔交易标注 INTEREST / 利息收入"),
                country_or_region=CandidateField("中国香港", "medium", "银行月结单归属地候选值，仍需人工确认所得来源地"),
                currency=CandidateField(event_currency, confidence, "取自同一账户分段的币种标题" if currency else "未可靠识别币种"),
                foreign_tax_currency=CandidateField(event_currency, confidence, "与利息收入币种一致；未见单列扣税"),
                gross_amount=CandidateField(_money(found.group(2)), "high", "取自逐笔利息交易金额，未采用余额列"),
                foreign_tax_reported=CandidateField(Decimal("0"), "medium", "该逐笔交易未显示代扣税额，仍需核对"),
                foreign_tax_eligible=CandidateField(Decimal("0"), "medium", "材料未显示已缴境外所得税，仍需人工确认"),
                occurred_on=CandidateField(occurred.isoformat(), "high", "取自逐笔交易日期"),
                evidence=_evidence(document, page_number, f"第{page_number}页 INTEREST / 利息收入", line),
                extracted_fields={"transaction_type": "bank_interest", "aggregation_level": "transaction_detail"},
            ))
    if not events:
        warnings.append("识别到储蓄账户月结单，但未找到可验证的逐笔利息交易。")
    return events, warnings


def _country_from_instrument(instrument_detail: str) -> tuple[str, str]:
    compact = re.sub(r"\s+", "", instrument_detail).upper()
    if compact.startswith("US") or "US" in compact[:6]:
        return "美国", "根据证券标识中的 US 前缀生成来源地候选值，仍需确认"
    if compact.startswith("HK") or "HK" in compact[:6]:
        return "中国香港", "根据证券标识中的 HK 前缀生成来源地候选值，仍需确认"
    return "", "证券标识不足以确定所得来源地"


def _recognize_activity_statement(document: ExtractedDocument) -> tuple[list[CandidateEvent], list[str]]:
    rows = [(page_number, line) for page_number, page_text in enumerate(document.pages, start=1) for line in _lines(page_text)]
    withholding: dict[tuple[str, str, str], Decimal] = {}
    tax_row = re.compile(r"^(20\d{2}-\d{2}-\d{2})\s+([A-Z0-9._-]+)\s*\([^)]*\)\s+现金红利\s+([A-Z]{3})\b.*-\s*(?:US|美国)\s*税收\s+(-?[0-9,]+\.[0-9]{2})\s*$", re.IGNORECASE)
    for _, line in rows:
        found = tax_row.match(line)
        if found:
            withholding[(found.group(1), found.group(2).upper(), found.group(3).upper())] = abs(_money(found.group(4)) or Decimal("0"))

    events: list[CandidateEvent] = []
    warnings: list[str] = []
    sequence = 0
    dividend_row = re.compile(r"^(20\d{2}-\d{2}-\d{2})\s+([A-Z0-9._-]+)\s*\(([^)]*)\)\s+现金红利\s+([A-Z]{3})\b.*(?:常规股息).*?(-?[0-9,]+\.[0-9]{2})\s*$", re.IGNORECASE)
    credit_interest_row = re.compile(r"^(20\d{2}-\d{2}-\d{2})\s+([A-Z]{3})\s+贷方利息\b.*?([0-9,]+\.[0-9]{2})\s*$", re.IGNORECASE)
    substitute_pattern = re.compile(r"PAYMENT\s+IN\s+LIEU\s+OF\s*DIVIDEND|替代股息的付款", re.IGNORECASE)
    substitute_count = 0

    for page_number, line in rows:
        dividend = dividend_row.match(line)
        if dividend:
            day, symbol, detail, currency, amount_text = dividend.groups()
            gross = _money(amount_text)
            if gross is None or gross <= 0:
                continue
            sequence += 1
            country, country_reason = _country_from_instrument(detail)
            tax = withholding.get((day, symbol.upper(), currency.upper()), Decimal("0"))
            events.append(CandidateEvent(
                id=f"candidate-{document.sha256[:10]}-broker-{sequence}",
                category=CandidateField("dividend", "high", "逐笔记录标注现金红利和常规股息"),
                country_or_region=CandidateField(country, "medium" if country else "low", country_reason),
                currency=CandidateField(currency.upper(), "high", "取自逐笔现金红利币种"),
                foreign_tax_currency=CandidateField(currency.upper(), "high", "与同日同证券代扣税记录币种一致"),
                gross_amount=CandidateField(gross, "high", "取自逐笔常规股息金额"),
                foreign_tax_reported=CandidateField(tax, "high" if tax else "medium", "与同日同证券代扣税记录勾稽" if tax else "未匹配到同日同证券代扣税记录"),
                foreign_tax_eligible=CandidateField(None, "low", "实际可抵免额需按完税和税收协定规则确认"),
                occurred_on=CandidateField(day, "high", "取自逐笔记录日期"),
                evidence=_evidence(document, page_number, f"第{page_number}页 现金红利逐笔记录", line),
                extracted_fields={"instrument": symbol, "aggregation_level": "transaction_detail"},
            ))
            continue
        interest = credit_interest_row.match(line)
        if interest:
            day, currency, amount_text = interest.groups()
            gross = _money(amount_text)
            if gross is None or gross <= 0:
                continue
            sequence += 1
            events.append(CandidateEvent(
                id=f"candidate-{document.sha256[:10]}-broker-{sequence}",
                category=CandidateField("interest", "high", "逐笔记录标注贷方利息"),
                country_or_region=CandidateField("", "low", "券商计息实体和所得来源地需人工确认"),
                currency=CandidateField(currency.upper(), "high", "取自贷方利息逐笔记录"),
                foreign_tax_currency=CandidateField(currency.upper(), "medium", "材料未显示该笔利息的单独扣税币种"),
                gross_amount=CandidateField(gross, "high", "取自正数贷方利息；借方利息未作为收入"),
                foreign_tax_reported=CandidateField(Decimal("0"), "medium", "未匹配到该笔利息的代扣税记录"),
                foreign_tax_eligible=CandidateField(Decimal("0"), "medium", "材料未显示该笔利息已缴境外所得税"),
                occurred_on=CandidateField(day, "high", "取自逐笔记录日期"),
                evidence=_evidence(document, page_number, f"第{page_number}页 贷方利息逐笔记录", line),
                extracted_fields={"transaction_type": "credit_interest", "aggregation_level": "transaction_detail"},
            ))
            continue
        if substitute_pattern.search(line):
            dated = re.match(r"^(20\d{2}-\d{2}-\d{2})\b", line)
            if not dated:
                continue
            substitute_count += 1
            sequence += 1
            currency_match = re.search(r"\b(USD|HKD|EUR|GBP|JPY|AUD|CAD|SGD)\b", line, re.IGNORECASE)
            amounts = MONEY_TOKEN.findall(line)
            amount = _money(amounts[-1]) if amounts else None
            event_currency = currency_match.group(1).upper() if currency_match else ""
            events.append(CandidateEvent(
                id=f"candidate-{document.sha256[:10]}-broker-{sequence}",
                category=CandidateField("other", "low", "替代股息付款的中国税务所得性质尚未验证"),
                country_or_region=CandidateField("", "low", "所得来源地需结合证券和付款实体确认"),
                currency=CandidateField(event_currency, "medium" if event_currency else "low", "取自逐笔记录币种" if event_currency else "未可靠识别币种"),
                foreign_tax_currency=CandidateField(event_currency, "low", "该类事项的扣税关系尚未验证"),
                gross_amount=CandidateField(amount, "medium" if amount is not None else "low", "取自替代股息逐笔记录末列，需人工核对"),
                foreign_tax_reported=CandidateField(None, "low", "尚未勾稽该类事项的代扣税"),
                foreign_tax_eligible=CandidateField(None, "low", "该类事项尚未进入可抵免税额模型"),
                occurred_on=CandidateField(dated.group(1), "high", "取自逐笔记录日期"),
                evidence=_evidence(document, page_number, f"第{page_number}页 替代股息付款逐笔记录", line),
                extracted_fields={"transaction_type": "payment_in_lieu_of_dividend", "aggregation_level": "transaction_detail"},
            ))

    if substitute_count:
        warnings.append(f"检测到 {substitute_count} 笔替代股息付款；其所得性质尚未进入已验证税额模型，最终结果保持阻断。")
    if not events:
        warnings.append("识别到券商活动报表，但未找到可验证的常规现金股息或正数贷方利息明细。")
    return events, warnings


def recognize_document(document: ExtractedDocument) -> DocumentRecognition:
    full_text = _normalized(" ".join(document.pages))
    document_type = _document_type(full_text)
    year = _tax_year(full_text)
    events: list[CandidateEvent] = []
    warnings: list[str] = []

    if not full_text:
        warnings.append("PDF 没有可提取的文字，可能是扫描件；当前不会在未验证 OCR 的情况下猜测字段。")
    elif document_type.value == "irs_1042_s":
        seen_forms: set[tuple[str | None, Any, Any, int]] = set()
        for page_number, page_text in enumerate(document.pages, start=1):
            if "1042-s" not in page_text.lower() and "1042s" not in page_text.lower():
                continue
            event, page_warnings = _recognize_1042_s_page(document, page_number, page_text)
            warnings.extend(page_warnings)
            if event is None:
                continue
            signature = (event.amendment_key, event.gross_amount.value, event.foreign_tax_reported.value, event.revision)
            if event.amendment_key and signature in seen_forms:
                warnings.append(f"第 {page_number} 页疑似同一 1042-S 的副本，未重复生成候选事项。")
                continue
            seen_forms.add(signature)
            events.append(event)
    elif document_type.value == "bank_savings_statement":
        bank_events, bank_warnings = _recognize_bank_statement(document)
        events.extend(bank_events)
        warnings.extend(bank_warnings)
    elif document_type.value == "ibkr_activity_statement":
        broker_events, broker_warnings = _recognize_activity_statement(document)
        events.extend(broker_events)
        warnings.extend(broker_warnings)
    elif document_type.value in {"broker_statement", "bank_statement"}:
        warnings.append("已识别材料类型，但该报表版式尚未通过字段级测试，请人工补充事项。")
    else:
        warnings.append("未识别到已支持的材料模板，请人工补充事项。")

    if not year and events:
        event_years = {str(event.occurred_on.value)[:4] for event in events if event.occurred_on.value}
        if len(event_years) == 1:
            year = event_years.pop()
    tax_year = CandidateField(year, "high" if year else "low", "从材料税年或逐笔日期提取" if year else "未可靠识别纳税年度")
    status = "recognized" if events else "needs_manual_review"
    return DocumentRecognition(document_type, tax_year, status, tuple(events), tuple(warnings))
