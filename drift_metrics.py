"""Strategic Drift Detector for autonomous LLM agent monitoring.

Provides pure-mathematical utilities to detect when an agent enters a
degenerate execution loop.  By tracking token-consumption variance and
execution-latency Exponential Moving Average (EMA), the detector flags
situations where the agent repeatedly produces near-identical output while
wall-clock time per iteration is increasing — the mathematical signature
of an infinite retry loop.

Zero external dependencies: only ``math``, ``statistics``, and
``collections`` from the Python standard library.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Telemetry record
# ---------------------------------------------------------------------------

@dataclass
class TelemetryRecord:
    """A single (token_count, duration_sec) observation."""
    token_count: int
    duration_sec: float


# ---------------------------------------------------------------------------
# Drift detector
# ---------------------------------------------------------------------------

class DriftDetector:
    """Fixed-window statistical monitor for agent execution health.

    Maintains a bounded :class:`~collections.deque` of the most recent
    *window_size* ``(token_count, duration_sec)`` observations.  Exposes
    an EMA calculator and a loop-anomaly detector that flags when variance
    in token counts approaches zero while execution latency is spiking.

    Parameters
    ----------
    window_size:
        Maximum number of telemetry records to retain.  When the deque is
        full, the oldest record is silently discarded on the next append.
    """

    # -- thresholds (tunable per deployment) --------------------------------
    _VARIANCE_EPSILON: float = 1.0
    """Token-count variance below this value is treated as near-zero."""

    _EMA_SPIKE_MULTIPLIER: float = 1.5
    """EMA of duration must exceed this multiple of the median duration
    to be considered a spike.  This prevents false positives during
    normally fast, stable execution."""

    def __init__(self, window_size: int = 5) -> None:
        if window_size < 2:
            raise ValueError(
                f"window_size must be >= 2 for meaningful variance, got {window_size}"
            )
        self._window: deque[TelemetryRecord] = deque(maxlen=window_size)

    # -- properties ---------------------------------------------------------

    @property
    def window_size(self) -> int:
        """Configured maximum deque length."""
        return self._window.maxlen  # type: ignore[arg-type]

    @property
    def record_count(self) -> int:
        """Number of records currently in the window."""
        return len(self._window)

    # -- mutation -----------------------------------------------------------

    def add_telemetry(self, token_count: int, duration_sec: float) -> None:
        """Append a new observation, evicting the oldest if full.

        Parameters
        ----------
        token_count:
            Number of tokens consumed by the agent in this iteration.
        duration_sec:
            Wall-clock seconds taken for this iteration.
        """
        self._window.append(
            TelemetryRecord(token_count=token_count, duration_sec=duration_sec),
        )

    # -- mathematical core --------------------------------------------------

    @staticmethod
    def calculate_ema(
        values: list[float],
        smoothing: float = 2.0,
    ) -> float:
        """Compute the Exponential Moving Average (EMA) over *values*.

        The EMA applies exponentially decaying weights to recent observations,
        giving higher sensitivity to recent changes than a simple moving
        average.  The smoothing factor *α* is derived from the traditional
        formula::

            α = 2 / (N + 1)

        where *N* is the user-supplied *smoothing* parameter (higher values
        produce a more responsive EMA).  The first value in the series is
        used as the initial seed (SMA of the first element).

        Parameters
        ----------
        values:
            Ordered sequence of floating-point observations (oldest first).
        smoothing:
            Controls the decay rate.  The default of ``2.0`` corresponds to
            the standard N=2 multiplier used in financial EMA (α = 0.667).

        Returns
        -------
        float
            The EMA of the full series.  Returns ``0.0`` for an empty input.

        Mathematical Reference
        ----------------------
        Given series x_1, x_2, ..., x_n and multiplier k:

            α = 2 / (k + 1)
            S_1 = x_1
            S_i = α · x_i + (1 - α) · S_{i-1}   for i ≥ 2
        """
        if not values:
            return 0.0

        alpha: float = 2.0 / (smoothing + 1.0)
        ema: float = values[0]
        for value in values[1:]:
            ema = alpha * value + (1.0 - alpha) * ema
        return ema

    def detect_loop_anomaly(self) -> bool:
        """Detect whether the agent is mathematically trapped in a retry loop.

        Algorithm
        ---------
        1. Compute the **population variance** of token counts across the
           window using :func:`statistics.variance`.
        2. If variance is below :attr:`_VARIANCE_EPSILON`, the agent is
           producing nearly identical output each iteration (low entropy).
        3. Independently compute the **EMA** of durations and the median
           duration.  If the EMA exceeds
           :attr:`_EMA_SPIKE_MULTIPLIER` × median, latency is spiking.
        4. Return ``True`` only when **both** conditions hold: near-zero
           token variance **and** spiking duration EMA.

        This dual-signal approach eliminates false positives from agents
        that naturally have low variance (e.g., short response templates)
        but are not actually looping.

        Returns
        -------
        bool
            ``True`` if a loop anomaly is detected, ``False`` otherwise.
            Also returns ``False`` if the window has fewer than 2 records
            (insufficient data for variance).
        """
        if len(self._window) < 2:
            return False

        token_counts: list[int] = [r.token_count for r in self._window]
        durations: list[float] = [r.duration_sec for r in self._window]

        # ---- Signal 1: token-count variance --------------------------------
        try:
            token_variance: float = statistics.variance(token_counts)
        except statistics.StatisticsError:
            # All values are identical → variance is exactly 0.
            token_variance = 0.0

        if token_variance > self._VARIANCE_EPSILON:
            # High entropy in token output — not a loop.
            return False

        # ---- Signal 2: duration EMA spike ----------------------------------
        duration_ema: float = self.calculate_ema(durations)
        duration_median: float = float(statistics.median(durations))

        # Avoid division-by-zero when all durations are 0.
        if duration_median == 0.0:
            return False

        is_spiking: bool = (
            duration_ema > duration_median * self._EMA_SPIKE_MULTIPLIER
        )

        return is_spiking

    # -- introspection helpers ----------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """Return a diagnostic snapshot of the current window state.

        Useful for logging, debugging, or feeding into upstream
        monitoring dashboards.

        Returns
        -------
        dict[str, Any]
            Keys: ``record_count``, ``token_counts``, ``durations``,
            ``token_variance``, ``duration_ema``, ``anomaly_detected``.
        """
        token_counts: list[int] = [r.token_count for r in self._window]
        durations: list[float] = [r.duration_sec for r in self._window]

        try:
            token_var: float = statistics.variance(token_counts)
        except statistics.StatisticsError:
            token_var = 0.0

        return {
            "record_count": len(self._window),
            "token_counts": list(token_counts),
            "durations": list(durations),
            "token_variance": token_var,
            "duration_ema": self.calculate_ema(durations) if durations else 0.0,
            "anomaly_detected": self.detect_loop_anomaly(),
        }
