#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 PDF 文本提取（含 Windows 中文编码修复）。

用法:
    python extract_pdf.py <pdf文件路径> [--out <输出txt路径>]

特性:
- 提取所有页文本，用 pypdf
- 大输出自动落盘到 .txt（避免 Windows 控制台 GBK 编码崩溃）
- 加密/损坏 PDF 给出友好错误而非栈崩溃
- 本脚本自身强制 UTF-8 输出

调用方提示: 在 Windows 下，调用此脚本时建议加环境前缀:
    PYTHONUTF8=1 python -X utf8 extract_pdf.py ...
（脚本内部已 reconfigure stdout，但加前缀更稳妥）
"""
import argparse
import os
import sys


def setup_utf8():
    """强制 stdout/stderr 用 UTF-8，避免 Windows GBK 崩溃。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def extract(pdf_path):
    import pypdf  # 延迟导入，依赖由 setup_env.py 安装

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    try:
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            parts = [f"=== {os.path.basename(pdf_path)} ({len(reader.pages)} 页) ===\n"]
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                parts.append(f"\n--- 第 {i + 1} 页 ---\n{text}\n")
        return "".join(parts)
    except pypdf.errors.PdfReadError as e:
        raise RuntimeError(
            f"PDF 解析失败（可能加密或损坏）: {pdf_path}。"
            f"若是加密 PDF 需先解除密码。原始错误: {e}"
        ) from e


def main():
    setup_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="PDF 文件路径")
    parser.add_argument("--out", help="输出 txt 路径（默认同目录 .txt）", default=None)
    args = parser.parse_args()

    try:
        content = extract(args.pdf)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[extract] 错误: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = args.out or os.path.splitext(args.pdf)[0] + ".txt"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 大文件只落盘不打印（避免控制台炸），小文件同时打印。始终输出路径到 stdout 供调用方定位
    if len(content) < 4000:
        print(content)
    else:
        print(f"[extract] 内容较大（{len(content)} 字符），已落盘，请读取该 .txt 文件查看", file=sys.stderr)
    print(out_path)


if __name__ == "__main__":
    main()
