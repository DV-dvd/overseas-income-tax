from io import BytesIO

import pytest
from pypdf import PdfWriter

from overseas_income_tax.extraction import extract_pdf_bytes


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extract_accepts_bank_wrapper_bytes_before_pdf_header():
    document = extract_pdf_bytes("statement.pdf", b"bank-wrapper" + blank_pdf())
    assert len(document.pages) == 1
    assert document.pages == ("",)


def test_extract_rejects_content_without_pdf_header():
    with pytest.raises(ValueError, match="PDF 标识"):
        extract_pdf_bytes("fake.pdf", b"not a pdf")
