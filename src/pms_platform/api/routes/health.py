"""Health check routes."""

from fastapi import APIRouter

from pms_platform.research_paths import describe_research_layout

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Return a simple service health payload."""
    return {"status": "ok"}


@router.get("/health/research")
def health_research() -> dict[str, object]:
    """Show what Research/Portfolio/History the API process can see.

    Useful on Dad's Docker box when History exists in Explorer but
    ``ls /data/research/Portfolio/History`` fails inside the container.
    """
    layout = describe_research_layout()
    layout["status"] = "ok"
    layout["history_visible"] = bool(layout.get("resolved_history_dir"))
    return layout
