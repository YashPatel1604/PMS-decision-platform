"""Storage capacity report for rehearsal (500 MB planning gate)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MB = 1024 * 1024
_DEFAULT_CEILING_MB = 500


@dataclass
class PathUsage:
    path: str
    bytes: int
    file_count: int

    @property
    def megabytes(self) -> float:
        return round(self.bytes / _MB, 2)


@dataclass
class CapacityReport:
    ceiling_mb: int = _DEFAULT_CEILING_MB
    paths: list[PathUsage] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(p.bytes for p in self.paths)

    @property
    def total_megabytes(self) -> float:
        return round(self.total_bytes / _MB, 2)

    @property
    def within_ceiling(self) -> bool:
        return self.total_megabytes <= self.ceiling_mb

    def as_dict(self) -> dict[str, Any]:
        return {
            "ceiling_mb": self.ceiling_mb,
            "total_bytes": self.total_bytes,
            "total_megabytes": self.total_megabytes,
            "within_ceiling": self.within_ceiling,
            "paths": [
                {
                    "path": p.path,
                    "bytes": p.bytes,
                    "megabytes": p.megabytes,
                    "file_count": p.file_count,
                }
                for p in self.paths
            ],
        }


def _dir_usage(path: Path) -> PathUsage:
    if not path.exists():
        return PathUsage(path=str(path), bytes=0, file_count=0)
    total = 0
    count = 0
    for file in path.rglob("*"):
        if file.is_file():
            try:
                total += file.stat().st_size
                count += 1
            except OSError:
                continue
    return PathUsage(path=str(path.resolve()), bytes=total, file_count=count)


def build_capacity_report(
    *,
    private_storage_dir: Path,
    research_dir: Path | None = None,
    upload_dir: Path | None = None,
    ceiling_mb: int = _DEFAULT_CEILING_MB,
) -> CapacityReport:
    report = CapacityReport(ceiling_mb=ceiling_mb)
    report.paths.append(_dir_usage(private_storage_dir))
    if upload_dir is not None:
        report.paths.append(_dir_usage(upload_dir))
    if research_dir is not None:
        portfolio = research_dir / "Portfolio"
        report.paths.append(_dir_usage(portfolio if portfolio.is_dir() else research_dir))
    return report
