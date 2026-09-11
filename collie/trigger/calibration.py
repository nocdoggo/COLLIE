"""The frozen trigger calibration (Task 18.2, R1.9).

Every value here is an output of ``tools/calibrate_triggers.py``, computed from the dev and cal
twin episodes (36 + 24 stationary paths, horizon 50, registered stationary-IID law) and frozen.
Test data never entered the procedure. ``uv run python -m tools.calibrate_triggers --check``
recomputes and compares; a test in ``tests/test_triggers.py`` runs the same comparison so drift
fails the suite, not just a manual step.

The rule (research notes §2): per-episode null maximum of the raw two-sided statistic, nearest-rank
95% quantile over the 60 maxima. ``cusum_h`` is in sigma units (decision interval ``H = h *
sigma0``); ``ph_threshold`` is in raw demand units. Both leave 3/60 = 5% of null episodes firing,
which the <=2-proposal cap and the refractory window then bound further.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FROZEN", "TriggerCalibration"]


@dataclass(frozen=True, slots=True)
class TriggerCalibration:
    """Everything a wrapped trigger chain needs, frozen at the method freeze."""

    mu0: float
    """Registered stationary-law mean (collie/data/families/base.py BaselineSpec)."""
    sigma0: float
    """Registered stationary-law sd. Same source."""
    cusum_k: float
    """CUSUM reference in sigma units: half the standardised shift (NIST convention)."""
    cusum_h: float
    """CUSUM decision interval in sigma units. Calibrated; see module docstring."""
    ph_delta: float
    """Page-Hinkley allowance, raw units (0.5 * sigma0)."""
    ph_threshold: float
    """Page-Hinkley threshold, raw units. Calibrated; see module docstring."""
    refractory_window: int
    """Covers the longest registered pulse (4) and pause (5): one incident, one firing cluster."""
    max_proposals: int
    """The primary design's cap of 2 (derivation note §5: alpha_j = alpha * 2**-j)."""


FROZEN = TriggerCalibration(
    mu0=100.0,
    sigma0=25.0,
    cusum_k=0.5,
    cusum_h=5.18,
    ph_delta=12.5,
    ph_threshold=129.5,
    refractory_window=5,
    max_proposals=2,
)
