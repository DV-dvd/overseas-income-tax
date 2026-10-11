from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import IO, Any, Sequence

from .codec import InputError, request_from_dict
from .contract import calculation_request_schema, capabilities
from .engine import calculate
from .exporter import build_xlsx
from .extraction import extract_pdf_bytes
from .models import to_primitive
from .web import create_app


def _read_json(path: str, stdin: IO[str]) -> dict[str, Any]:
    try:
        if path == "-":
            payload = json.load(stdin)
        else:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"无法读取 JSON 输入：{exc}") from exc
    if not isinstance(payload, dict):
        raise InputError("JSON 输入的顶层必须是对象。")
    return payload


def _write_json(payload: dict[str, Any], path: str, stdout: IO[str]) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path == "-":
        stdout.write(content)
    else:
        Path(path).write_text(content, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="overseas-income-tax",
        description="Agent 厂商无关的境外收入范围内测算工具",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="启动本地网页与 HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--debug", action="store_true")

    calculate_command = subparsers.add_parser("calculate", help="从 JSON 读取事实并输出计算结果")
    calculate_command.add_argument("--input", default="-", help="JSON 文件路径；- 表示标准输入")
    calculate_command.add_argument("--output", default="-", help="结果 JSON 路径；- 表示标准输出")

    export_command = subparsers.add_parser("export", help="从同一计算结果生成 Excel")
    export_command.add_argument("--input", default="-", help="JSON 文件路径；- 表示标准输入")
    export_command.add_argument("--output", required=True, help="输出 .xlsx 路径")

    extract_command = subparsers.add_parser("extract", help="提取 PDF 的页级文本，不做税务判断")
    extract_command.add_argument("--input", required=True, help="PDF 文件路径")
    extract_command.add_argument("--output", default="-", help="结果 JSON 路径；- 表示标准输出")

    capability_command = subparsers.add_parser("capabilities", help="输出机器可读能力声明")
    capability_command.add_argument("--output", default="-")

    schema_command = subparsers.add_parser("schema", help="输出计算请求 JSON Schema")
    schema_command.add_argument("--output", default="-")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    command = args.command or "serve"

    try:
        if command == "serve":
            create_app().run(
                host=getattr(args, "host", "127.0.0.1"),
                port=getattr(args, "port", 8765),
                debug=getattr(args, "debug", False),
            )
            return 0
        if command == "capabilities":
            _write_json(capabilities(), args.output, stdout)
            return 0
        if command == "schema":
            _write_json(calculation_request_schema(), args.output, stdout)
            return 0
        if command == "extract":
            source = Path(args.input)
            document = extract_pdf_bytes(source.name, source.read_bytes())
            _write_json(
                {
                    "file_name": document.file_name,
                    "sha256": document.sha256,
                    "pages": [
                        {"page": index, "text": text}
                        for index, text in enumerate(document.pages, start=1)
                    ],
                },
                args.output,
                stdout,
            )
            return 0

        calculation_request = request_from_dict(_read_json(args.input, stdin))
        result = calculate(calculation_request)
        if command == "calculate":
            _write_json(to_primitive(result), args.output, stdout)
            return 0
        if command == "export":
            Path(args.output).write_bytes(build_xlsx(calculation_request, result))
            return 0
    except (InputError, OSError, ValueError) as exc:
        stderr.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
        return 2
    return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
