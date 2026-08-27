"""Write reconciliation JSON and markdown reports."""

from __future__ import annotations

import json
from pathlib import Path

from pms_platform.reconciliation.types import Classification, ReconReport


def write_json_report(report: ReconReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")


def write_markdown_report(report: ReconReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data Reconciliation Report",
        "",
        f"Generated: {report.generated_at}",
        "",
        "## Input manifest",
        "",
        f"- Samir source: `{report.manifest.get('samir_label')}`",
        f"- Julesh source: `{report.manifest.get('julesh_label')}`",
        f"- Research dir: `{report.manifest.get('research_dir') or 'not provided'}`",
        "",
    ]
    research_files = report.manifest.get("research_files") or []
    if research_files:
        lines.append("### Research file checksums (read-only)")
        lines.append("")
        for entry in research_files:
            lines.append(
                f"- `{entry['relative_path']}` — {entry['byte_size']} bytes, "
                f"sha256 `{entry['checksum_sha256'][:16]}…`"
            )
        lines.append("")

    lines.extend(["## Summary by domain", ""])
    for domain, counts in sorted(report.summary.items()):
        total = sum(counts.values())
        conflicts = counts.get(Classification.VALUE_CONFLICT, 0)
        lines.append(f"### {domain} ({total} row-classifications)")
        for cls, n in sorted(counts.items()):
            lines.append(f"- {cls}: {n}")
        if conflicts:
            lines.append(f"- **Unresolved value conflicts: {conflicts}**")
        lines.append("")

    conflicts = [
        r
        for r in report.rows
        if r.classification
        in (Classification.VALUE_CONFLICT, Classification.IDENTITY_CONFLICT)
    ]
    lines.extend(["## Value conflicts (requires human decision)", ""])
    if not conflicts:
        lines.append("No value conflicts detected.")
    else:
        for row in conflicts[:200]:
            lines.append(
                f"- **{row.domain}** `{row.key}`"
                + (f" field `{row.field}`" if row.field else "")
                + f": Samir={row.samir_value!r} vs Julesh={row.julesh_value!r}"
            )
        if len(conflicts) > 200:
            lines.append(f"- … and {len(conflicts) - 200} more (see reconciliation.json)")

    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Do not import unresolved `value_conflict` rows into production.",
            "- `compatible_merge` may be auto-applied when one side is null.",
            "- Research files are inventory-only in this report; full Research row diff is manual.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reports(report: ReconReport, output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / "reconciliation.json"
    md_path = output_dir / "DATA_RECONCILIATION_REPORT.md"
    write_json_report(report, json_path)
    write_markdown_report(report, md_path)
    return json_path, md_path
