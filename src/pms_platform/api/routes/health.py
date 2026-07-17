"""Health check routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Return a simple service health payload."""
    return {"status": "ok"}
