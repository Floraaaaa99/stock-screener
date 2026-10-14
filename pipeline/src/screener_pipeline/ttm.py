"""Trailing-twelve-month revenue and year-over-year growth."""

from __future__ import annotations

from dataclasses import dataclass

from .quarters import MissingQuarter, Quarter, Slot


@dataclass(frozen=True)
class TTMResult:
    current: float | None
    previous: float | None
    growth_pct: float | None
    reason: str | None


def _sum4(slots: list[Slot]) -> float | None:
    if len(slots) < 4 or any(isinstance(s, MissingQuarter) for s in slots[:4]):
        return None
    return sum(s.val for s in slots[:4] if isinstance(s, Quarter))


def _missing_reason(window: list[Slot]) -> str:
    return "gap_in_quarters" if any(isinstance(s, MissingQuarter) for s in window) else "insufficient_quarters"


def compute_ttm(slots: list[Slot], blocking_reason: str | None = None) -> TTMResult:
    """slots are newest-first and consecutive (gaps are MissingQuarter).

    Growth requires 8 valid consecutive quarters and a positive previous TTM. Missing data is never
    treated as zero.
    """
    if blocking_reason:
        return TTMResult(None, None, None, blocking_reason)
    current = _sum4(slots[0:4])
    previous = _sum4(slots[4:8])
    if current is None:
        return TTMResult(None, None, None, _missing_reason(slots[0:4]))
    if previous is None:
        return TTMResult(current, None, None, _missing_reason(slots[4:8]))
    if previous <= 0:
        return TTMResult(current, previous, None, "previous_ttm_not_positive")
    return TTMResult(current, previous, (current / previous - 1.0) * 100.0, None)
