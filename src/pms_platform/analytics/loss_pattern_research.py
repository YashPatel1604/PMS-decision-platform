"""Future: loss-stock pattern library for early-exit signals on open positions.

Phase D intent (not implemented yet):
- Build a feature vector from closed episodes with loss_hold_pattern set
  (STAYED_UNDERWATER, RODE_WINNER_DOWN, RECOVERED_AFTER_LONG_LOSS): drawdown path, days below cost, benchmark lag, etc.
- Cluster or rule-match historical loss episodes to find recurring pre-exit signatures.
- Monitor open positions for matching signatures and surface sell alerts before full loss.

See also: ownership_metrics loss_hold_pattern, exit_assessment post-exit flags.
"""

from __future__ import annotations

LOSS_PATTERN_RESEARCH_VERSION = "phase-d-stub"
