from __future__ import annotations

import json
from io import StringIO

from openpyxl import load_workbook

from overseas_income_tax.cli import run
from overseas_income_tax.models import to_primitive
from test_engine import event, request


def payload_text() -> str:
    return json.dumps(to_primitive(request(event("one"))), ensure_ascii=False)


def test_capabilities_are_machine_readable_and_vendor_neutral():
    output = StringIO()
    assert run(["capabilities"], stdout=output) == 0
    result = json.loads(output.getvalue())
    assert result["agent_vendor_neutral"] is True
    assert result["runtime"]["model_required"] is False


def test_schema_is_available_from_cli():
    output = StringIO()
    assert run(["schema"], stdout=output) == 0
    result = json.loads(output.getvalue())
    assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_calculate_accepts_stdin_and_returns_json_stdout():
    output = StringIO()
    errors = StringIO()
    exit_code = run(
        ["calculate", "--input", "-", "--output", "-"],
        stdin=StringIO(payload_text()),
        stdout=output,
        stderr=errors,
    )
    assert exit_code == 0
    assert errors.getvalue() == ""
    result = json.loads(output.getvalue())
    assert result["range_supplemental_tax_cny"] == "700.00"


def test_export_writes_same_result_workbook(tmp_path):
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "result.xlsx"
    input_path.write_text(payload_text(), encoding="utf-8")
    assert run(["export", "--input", str(input_path), "--output", str(output_path)]) == 0
    workbook = load_workbook(output_path, data_only=True)
    assert workbook["范围内测算"]["B9"].value == 700


def test_invalid_input_returns_structured_error():
    payload = json.loads(payload_text())
    payload["questionnaire"]["same_country_other_income_reviewed"] = "false"
    errors = StringIO()
    exit_code = run(
        ["calculate"],
        stdin=StringIO(json.dumps(payload)),
        stdout=StringIO(),
        stderr=errors,
    )
    assert exit_code == 2
    assert "布尔值" in json.loads(errors.getvalue())["error"]


def test_audit_review_must_reference_an_event_and_explain_mismatch():
    payload = json.loads(payload_text())
    payload["audit_reviews"] = [
        {"event_id": "missing", "status": "inconsistent", "note": ""}
    ]
    errors = StringIO()
    exit_code = run(
        ["calculate"],
        stdin=StringIO(json.dumps(payload)),
        stdout=StringIO(),
        stderr=errors,
    )
    assert exit_code == 2
    assert "引用当前请求" in json.loads(errors.getvalue())["error"]
