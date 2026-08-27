"""Research input manifest (read-only checksums)."""

from __future__ import annotations

from pathlib import Path

from pms_platform.storage.adapter import sha256_hex


def research_file_manifest(research_dir: Path | None) -> list[dict[str, object]]:
    """Inventory key Research workbooks without modifying them."""
    if research_dir is None or not research_dir.is_dir():
        return []
    patterns = (
        "Portfolio/PMS_ClientPortfolio.xlsx",
        "Portfolio/MASTER_TRANSACTIONS_V1.xlsx",
        "Portfolio/SECURITY_MASTER_V1.xlsx",
        "Portfolio/Portfolio_*.xlsx",
    )
    seen: set[Path] = set()
    entries: list[dict[str, object]] = []
    for pattern in patterns:
        for path in sorted(research_dir.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            data = path.read_bytes()
            entries.append(
                {
                    "relative_path": str(path.relative_to(research_dir)),
                    "checksum_sha256": sha256_hex(data),
                    "byte_size": len(data),
                    "mtime": path.stat().st_mtime,
                }
            )
    return entries
