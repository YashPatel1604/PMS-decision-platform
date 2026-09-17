"""Scan Research corpus paths under configured allowlist globs."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from pms_platform.config import settings
from pms_platform.research_paths import research_dir


@dataclass(frozen=True)
class CorpusFile:
    """One candidate file under the research root."""

    absolute_path: Path
    relative_path: str
    source_root: str = "research"


def _split_globs(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_corpus_root(override: Path | None = None) -> Path | None:
    """Return the Research directory used for indexing."""
    if override is not None:
        path = override.expanduser().resolve()
        return path if path.is_dir() else None
    return research_dir()


def iter_corpus_files(
    root: Path | None = None,
    *,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[CorpusFile]:
    """Walk allowlisted files under Research; never writes."""
    base = resolve_corpus_root(root)
    if base is None:
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
                source_root="research",
            )
    return sorted(found.values(), key=lambda item: item.relative_path)
