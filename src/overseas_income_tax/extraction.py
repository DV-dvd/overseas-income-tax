from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class ExtractedDocument:
    file_name: str
    sha256: str
    pages: tuple[str, ...]


def extract_pdf_bytes(file_name: str, content: bytes) -> ExtractedDocument:
    pdf_start = content.find(b"%PDF-")
    if pdf_start < 0:
        raise ValueError("文件中没有有效的 PDF 标识。")
    if pdf_start > 4096:
        raise ValueError("PDF 标识位置异常，文件可能已损坏或不是受支持的 PDF。")
    pdf_content = content[pdf_start:]
    try:
        reader = PdfReader(BytesIO(pdf_content))
        if reader.is_encrypted:
            raise ValueError("PDF 已加密，请先在本地解除密码。")
        pages = tuple(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as exc:
        raise ValueError("PDF 无法读取，可能已损坏或使用了不支持的编码。") from exc
    return ExtractedDocument(file_name, hashlib.sha256(content).hexdigest(), pages)
