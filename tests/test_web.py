from io import BytesIO

from openpyxl import load_workbook
from pypdf import PdfWriter

from overseas_income_tax.models import to_primitive
from overseas_income_tax.web import create_app
from test_engine import event, request


def test_health_declares_privacy_defaults():
    client = create_app().test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "storage": "memory-only", "model": "disabled"}


def test_calculation_endpoint():
    client = create_app().test_client()
    payload = to_primitive(request(event("one")))
    response = client.post("/api/calculate", json=payload)
    assert response.status_code == 200
    assert response.json["range_supplemental_tax_cny"] == "700.00"
    assert response.headers["Cache-Control"] == "no-store"


def test_api_rejects_string_boolean_instead_of_treating_it_as_true():
    client = create_app().test_client()
    payload = to_primitive(request(event("one")))
    payload["questionnaire"]["same_country_other_income_reviewed"] = "false"
    response = client.post("/api/calculate", json=payload)
    assert response.status_code == 400
    assert "布尔值" in response.json["error"]


def test_api_rejects_non_finite_amount():
    client = create_app().test_client()
    payload = to_primitive(request(event("one")))
    payload["events"][0]["gross_amount"] = "NaN"
    response = client.post("/api/calculate", json=payload)
    assert response.status_code == 400


def test_pdf_extraction_is_request_scoped():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    content = BytesIO()
    writer.write(content)
    client = create_app().test_client()
    response = client.post(
        "/api/extract",
        data={"file": (BytesIO(content.getvalue()), "sample.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["file_name"] == "sample.pdf"
    assert len(response.json["sha256"]) == 64
    assert response.json["pages"] == [{"page": 1, "text": ""}]


def test_export_endpoint_returns_same_result_workbook():
    client = create_app().test_client()
    payload = to_primitive(request(event("one")))
    response = client.post("/api/export.xlsx", json=payload)
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.data), data_only=True)
    assert workbook.sheetnames == ["范围内测算", "已核验经济事项", "分国抵免账", "待核验与规则"]
