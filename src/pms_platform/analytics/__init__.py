"""Episode performance and sell-analysis calculations.

Analytics modules are intentionally imported lazily so read-only API routes do
not pay the SciPy startup cost required only by XIRR calculations.
"""

from typing import Any

__all__ = [
    "CALCULATION_VERSION",
    "analyze_closed_episodes",
    "analyze_post_exit_performance",
    "compute_xirr",
    "run_full_episode_analysis",
]


def __getattr__(name: str) -> Any:
    if name in {"CALCULATION_VERSION", "analyze_closed_episodes"}:
        from pms_platform.analytics import episode_performance

        return getattr(episode_performance, name)
    if name == "analyze_post_exit_performance":
        from pms_platform.analytics.post_exit import analyze_post_exit_performance

        return analyze_post_exit_performance
    if name == "compute_xirr":
        from pms_platform.analytics.xirr import compute_xirr

        return compute_xirr
    if name == "run_full_episode_analysis":
        from pms_platform.analytics.service import run_full_episode_analysis

        return run_full_episode_analysis
    raise AttributeError(name)
