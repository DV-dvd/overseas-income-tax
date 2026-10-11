from __future__ import annotations

import argparse
from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file

from .codec import InputError, request_from_dict
from .engine import calculate
from .exporter import build_xlsx
from .extraction import extract_pdf_bytes
from .models import to_primitive


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=20 * 1024 * 1024)

    @app.after_request
    def privacy_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return {"status": "ok", "storage": "memory-only", "model": "disabled"}

    @app.post("/api/extract")
    def extract():
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"error": "请选择 PDF 文件。"}), 400
        if not uploaded.filename.lower().endswith(".pdf"):
            return jsonify({"error": "当前只接受 PDF 文件。"}), 400
        try:
            document = extract_pdf_bytes(uploaded.filename, uploaded.read())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({
            "file_name": document.file_name,
            "sha256": document.sha256,
            "pages": [
                {"page": index, "text": text[:8000]}
                for index, text in enumerate(document.pages, start=1)
            ],
            "notice": "仅提取文本并返回浏览器；服务端不建立持久存储。请人工确认后再形成经济事项。",
        })

    @app.post("/api/calculate")
    def calculate_api():
        try:
            calculation_request = request_from_dict(request.get_json(force=True))
            result = calculate(calculation_request)
        except InputError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(to_primitive(result))

    @app.post("/api/export.xlsx")
    def export_api():
        try:
            calculation_request = request_from_dict(request.get_json(force=True))
            result = calculate(calculation_request)
        except InputError as exc:
            return jsonify({"error": str(exc)}), 400
        return send_file(
            BytesIO(build_xlsx(calculation_request, result)),
            as_attachment=True,
            download_name=f"境外收入范围内测算_{result.tax_year}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动境外收入税务申报辅助工具")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
