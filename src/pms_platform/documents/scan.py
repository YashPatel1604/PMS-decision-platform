"""Scan research corpus paths (OneDrive Research and/or UI uploads)."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from pms_platform.config import settings
from pms_platform.research_paths import research_dir

_UI_SOURCE = "ui"
_RESEARCH_SOURCE = "research"


@dataclass(frozen=True)
class CorpusFile:
    """One candidate file under a corpus root."""

    absolute_path: Path
    relative_path: str
    source_root: str = _RESEARCH_SOURCE


def _split_globs(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def ui_corpus_dir(*, ensure: bool = False) -> Path:
    """Writable corpus for notes uploaded through the UI (no RESEARCH_DIR needed)."""
    path = Path(settings.upload_dir).expanduser().resolve() / "research_corpus"
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def corpus_roots(override: Path | None = None) -> list[tuple[str, Path]]:
    """Return (source_root, path) pairs to index.

    Local Mac: OneDrive Research when present.
    Cloud / UI-only: ``upload_dir/research_corpus``.
    Both may be indexed together.
    """
    if override is not None:
        path = override.expanduser().resolve()
        return [(_RESEARCH_SOURCE, path)] if path.is_dir() else []

    roots: list[tuple[str, Path]] = []
    rd = research_dir()
    if rd is not None:
        roots.append((_RESEARCH_SOURCE, rd))
    ui = ui_corpus_dir()
    if ui.is_dir():
        roots.append((_UI_SOURCE, ui))
    return roots


def resolve_corpus_root(override: Path | None = None) -> Path | None:
    """Primary corpus root (Research preferred, else UI uploads)."""
    roots = corpus_roots(override)
    return roots[0][1] if roots else None


def iter_corpus_files(
    root: Path | None = None,
    *,
    source_root: str = _RESEARCH_SOURCE,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[CorpusFile]:
    """Walk allowlisted files under one corpus root; never writes."""
    base = root.expanduser().resolve() if root is not None else None
    if base is None or not base.is_dir():
        return []

    includes = include_globs or _split_globs(settings.research_corpus_globs)
    excludes = exclude_globs or _split_globs(settings.research_corpus_exclude_globs)
    if not includes:
        includes = ["**/*.pdf", "**/*.md", "**/*.txt"]

    found: dict[str, CorpusFile] = {}
    for pattern in includes:
        for path in base.glob(pattern):
            if not path.is_file():
                continue
            try:
                rel = path.resolve().relative_to(base.resolve()).as_posix()
            except ValueError:
                continue
            if any(fnmatch.fnmatch(rel, ex) or fnmatch.fnmatch(path.name, ex) for ex in excludes):
                continue
            found[rel] = CorpusFile(
                absolute_path=path.resolve(),
                relative_path=rel,
                source_root=source_root,
            )
    return sorted(found.values(), key=lambda item: item.relative_path)
