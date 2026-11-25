"""Upload checks and text extraction for PDF and DOCX files."""

import io
import re
import zipfile
from dataclasses import dataclass

from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.errors import AppError, PayloadTooLarge

MAX_PAGES = 20
MAX_TEXT_CHARS = 20_000
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class Upload:
    data: bytes
    name: str
    mime: str
    extension: str


def sniff(data: bytes) -> tuple[str, str] | None:
    """File type from content. The name and declared type are never trusted."""
    if data.startswith(b"%PDF-"):
        return PDF_MIME, "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(i.file_size for i in archive.infolist()) > MAX_UNZIPPED_BYTES:
                    return None
                if "word/document.xml" in archive.namelist():
                    return DOCX_MIME, "docx"
        except zipfile.BadZipFile:
            return None
    return None


def safe_name(name: str | None) -> str:
    base = re.split(r"[\\/]", name or "file")[-1]
    return re.sub(r"[^\w. ()-]", "_", base)[:120] or "file"


def read_limited(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(
            f"That file is larger than {get_settings().max_upload_mb} MB. Upload a smaller version."
        )
    if not data:
        raise AppError("That file is empty. Choose another one.", code="empty_file")
    return data


def read_document(file: UploadFile) -> Upload:
    data = read_limited(file)
    kind = sniff(data)
    if kind is None:
        raise AppError("Only PDF and DOCX files can be uploaded.", code="file_type")
    mime, extension = kind
    return Upload(data, safe_name(file.filename), mime, extension)


def extract_text(data: bytes, mime: str) -> str:
    try:
        if mime == PDF_MIME:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
            text = "\n".join(pages)
        else:
            document = Document(io.BytesIO(data))
            lines = [p.text for p in document.paragraphs]
            for table in document.tables:
                lines += [" | ".join(cell.text for cell in row.cells) for row in table.rows]
            text = "\n".join(lines)
    except Exception as exc:
        raise AppError(
            "The file could not be read. It may be damaged or password protected.",
            code="unreadable_file",
        ) from exc
    # Postgres text columns reject NUL, which some PDFs contain.
    text = re.sub(r"\n{3,}", "\n\n", text.replace("\x00", "")).strip()
    if len(text) < 40:
        raise AppError(
            "No readable text was found. If the file is a scan, paste the text instead.",
            code="no_text",
        )
    return text[:MAX_TEXT_CHARS]
