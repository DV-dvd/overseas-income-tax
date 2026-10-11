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
