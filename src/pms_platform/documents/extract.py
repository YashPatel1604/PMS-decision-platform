"""Extract text from research files (local only; no uploads)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractionResult:
    pages: list[ExtractedPage]
    mime_type: str | None
    title: str | None
    parse_status: str
    parse_error: str | None = None


def file_content_hash(path: Path) -> str:
    """SHA-256 of file bytes for idempotent indexing."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_mtime_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def extract_file(path: Path) -> ExtractionResult:
    """Extract page-level text. Unsupported types are skipped, not rewritten."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".md", ".markdown", ".txt"}:
        return _extract_text(path, mime="text/markdown" if suffix != ".txt" else "text/plain")
    return ExtractionResult(
        pages=[],
        mime_type=None,
        title=path.name,
        parse_status="skipped",
        parse_error=f"unsupported extension: {suffix or '(none)'}",
    )


def _extract_text(path: Path, *, mime: str) -> ExtractionResult:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return ExtractionResult(
            pages=[],
            mime_type=mime,
            title=path.name,
            parse_status="error",
            parse_error=str(exc),
        )
    pages = [ExtractedPage(page_number=1, text=text)] if text else []
    return ExtractionResult(
        pages=pages,
        mime_type=mime,
        title=path.stem,
        parse_status="ok" if pages else "skipped",
        parse_error=None if pages else "empty text file",
    )


def _extract_pdf(path: Path) -> ExtractionResult:
    try:
        import fitz  # type: ignore[import-untyped]  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        return ExtractionResult(
            pages=[],
            mime_type="application/pdf",
            title=path.name,
            parse_status="error",
            parse_error=f"pymupdf unavailable: {exc}",
        )
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 — surface parse failures, do not rewrite file
        return ExtractionResult(
            pages=[],
            mime_type="application/pdf",
            title=path.name,
            parse_status="error",
            parse_error=str(exc),
        )
    pages: list[ExtractedPage] = []
    try:
        for index, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            if text:
                pages.append(ExtractedPage(page_number=index, text=text))
        title = (doc.metadata or {}).get("title") or path.stem
    finally:
        doc.close()
    return ExtractionResult(
        pages=pages,
        mime_type="application/pdf",
        title=title,
        parse_status="ok" if pages else "skipped",
        parse_error=None if pages else "no extractable text",
    )
