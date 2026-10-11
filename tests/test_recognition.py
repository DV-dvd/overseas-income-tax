from decimal import Decimal

from overseas_income_tax.extraction import ExtractedDocument
from overseas_income_tax.recognition import recognize_document


FORM_TEXT = """
Form 1042-S 2025
Tax year: 2025
Unique Form Identifier: ABC-123
1 Income code 06
2 Gross income 1,000.00
7a Federal tax withheld 90.00
8 Tax withheld by other agents 10.00
9 Overwithheld tax repaid to recipient 0.00
10 Total withholding credit 100.00
"""


def document(*pages: str) -> ExtractedDocument:
    return ExtractedDocument("sample.pdf", "a" * 64, tuple(pages))


def test_1042s_rule_recognition_creates_unconfirmed_candidate_values():
    result = recognize_document(document(FORM_TEXT))
    assert result.document_type.value == "irs_1042_s"
    assert result.tax_year.value == "2025"
    assert result.status == "recognized"
    assert len(result.events) == 1
    candidate = result.events[0]
    assert candidate.category.value == "dividend"
    assert candidate.gross_amount.value == Decimal("1000.00")
    assert candidate.foreign_tax_reported.value == Decimal("100.00")
    assert candidate.foreign_tax_eligible.value is None
    assert candidate.evidence.page == 1
    assert candidate.amendment_key == "ABC-123"


def test_1042s_duplicate_copy_does_not_create_a_second_candidate():
    result = recognize_document(document(FORM_TEXT, FORM_TEXT))
    assert len(result.events) == 1
    assert any("副本" in warning for warning in result.warnings)


def test_unverified_statement_is_classified_but_not_guessed():
    result = recognize_document(document("Brokerage Annual Statement 2025"))
    assert result.document_type.value == "broker_statement"
    assert result.status == "needs_manual_review"
    assert result.events == ()
    assert any("尚未通过" in warning for warning in result.warnings)


def test_amended_1042s_carries_revision_for_supersession():
    amended = FORM_TEXT + "\nX Amended\nAmendment No. 2\n"
    result = recognize_document(document(amended))
    assert result.events[0].amendment_key == "ABC-123"
    assert result.events[0].revision == 2


def test_1042s_split_lines_do_not_consume_the_next_box_number():
    split = """
Form 1042-S 2025
1 Income
code
06
2 Gross income
840.00
7a Federal tax withheld
84.00
8 Tax withheld by other agents
9 Overwithheld tax repaid to recipient
10 Total withholding credit (combine boxes 7a, 8, and 9)
84.00
0 0 1 4 5 6 7 8 9 0 UNIQUE FORM IDENTIFIER AMENDED 0 NO.
"""
    result = recognize_document(document(split))
    candidate = result.events[0]
    assert candidate.foreign_tax_reported.value == Decimal("84.00")
    assert candidate.extracted_fields["box_8_other_agents"] == ""
    assert candidate.extracted_fields["box_9_repaid"] == ""
    assert candidate.amendment_key == "0014567890"


def test_supported_bank_statement_extracts_interest_by_currency_section():
    result = recognize_document(document("""
Statement Savings Account 儲蓄(結單)賬戶
Statement Period 結 單 期 : 05 JUN 2025 - 06 JUL 2025
HKD 05JUN25 Balance B/F 1,000.00
02JUL25 0000 INTEREST 利息收入 8.88 1,008.88
USD 05JUN25 Balance B/F 2,000.00
02JUL25 0000 INTEREST 利息收入 9.99 2,009.99
"""))
    assert result.document_type.value == "bank_savings_statement"
    assert [event.currency.value for event in result.events] == ["HKD", "USD"]
    assert [event.gross_amount.value for event in result.events] == [Decimal("8.88"), Decimal("9.99")]
    assert result.tax_year.value == "2025"
    assert result.coverage_start.value == "2025-06-05"
    assert result.coverage_end.value == "2025-07-06"


def test_time_deposit_uplift_extracts_interest_amount_and_excludes_prior_year_rows():
    result = recognize_document(document("""
Statement Savings Account 儲蓄(結單)賬戶
Statement Period 結 單 期 : 05 DEC 2024 - 06 JAN 2025
TIME DEPOSIT ACCOUNT 定期存款賬戶
Uplift 提取
11DEC24 123456 M01 11NOV24 11DEC24 USD 10,000.00 3.9000% 32.05 10,032.05
Uplift 提取
02JAN25 789012 M01 02DEC24 02JAN25 USD 20,000.00 3.5000% 59.45 20,059.45
"""))
    assert len(result.events) == 1
    event = result.events[0]
    assert event.extracted_fields["transaction_type"] == "time_deposit_maturity_interest"
    assert event.gross_amount.value == Decimal("59.45")
    assert event.occurred_on.value == "2025-01-02"


def test_supported_activity_statement_extracts_detail_not_totals_or_debit_interest():
    result = recognize_document(document("""
活动报表
股息
2025-03-31 FUND(US0000000001) 现金红利 USD 每股 0.10 (常规股息) 12.34
总数 USD 12.34
代扣税款
2025-03-31 FUND(US0000000001) 现金红利 USD 每股 0.10 - US 税收 -1.23
利息
2025-07-03 USD 贷方利息- 六月-2025 45.67
2025-07-03 USD 借方利息- 六月-2025 -1.00
"""))
    assert result.document_type.value == "ibkr_activity_statement"
    assert [event.category.value for event in result.events] == ["dividend", "interest"]
    assert result.events[0].foreign_tax_reported.value == Decimal("1.23")
    assert result.events[1].gross_amount.value == Decimal("45.67")


def test_substitute_dividend_is_visible_and_keeps_result_out_of_scope():
    result = recognize_document(document("""
活动报表
2025-08-01 FUND(US0000000001) 现金红利 PAYMENT IN LIEU OF DIVIDEND USD 4.50
"""))
    assert len(result.events) == 1
    assert result.events[0].category.value == "other"
    assert result.events[0].gross_amount.value == Decimal("4.50")
    assert any("替代股息" in warning for warning in result.warnings)
