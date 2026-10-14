"""Publishing gates: a failed or incomplete refresh must not replace a live dataset."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "reasons": self.reasons, "metrics": self.metrics}


def _ratio(coverage: dict, key: str) -> float | None:
    listings = coverage.get("listings") or 0
    if listings <= 0:
        return None
    return (coverage.get(key) or 0) / listings


def _mismatch_ratio(coverage: dict) -> float | None:
    checks = coverage.get("quarterChecks") or {}
    total = sum(int(v) for v in checks.values())
    if total <= 0:
        return None
    return int(checks.get("mismatch") or 0) / total


def evaluate_gate(meta: dict, baseline: dict | None = None, *, publish: bool = False) -> GateResult:
    reasons: list[str] = []
    coverage = meta.get("coverage") or {}
    dataset = meta.get("dataset") or {}
    run = meta.get("run") or {}
    universe = meta.get("universe") or {}
    mismatch = _mismatch_ratio(coverage)
    metrics = {
        "mode": dataset.get("mode"),
        "status": run.get("status"),
        "listings": coverage.get("listings"),
        "eligible": universe.get("eligibleListings"),
        "cikMatched": coverage.get("cikMatched"),
        "growthRatio": _ratio(coverage, "growth"),
        "currentTtmRatio": _ratio(coverage, "currentTtm"),
        "quarterMismatchRatio": mismatch,
    }

    if run.get("status") != "complete":
        reasons.append("incomplete_run")
    if dataset.get("mode") == "partial":
        reasons.append("partial_universe")
    if dataset.get("mode") == "full" and coverage.get("listings") != universe.get("eligibleListings"):
        reasons.append("missing_listings")
    if mismatch is not None and mismatch > config.QUARTER_MISMATCH_MAX_RATIO:
        reasons.append(
            f"quarter_mismatch_ratio_{mismatch:.1%}_exceeds_{config.QUARTER_MISMATCH_MAX_RATIO:.0%}"
        )

    if baseline and dataset.get("mode") == (baseline.get("dataset") or {}).get("mode"):
        base_cov = baseline.get("coverage") or {}
        growth = _ratio(coverage, "growth")
        base_growth = _ratio(base_cov, "growth")
        if growth is not None and base_growth:
            drop = base_growth - growth
            metrics["growthDrop"] = drop
            if drop > config.GROWTH_COVERAGE_MAX_DROP:
                reasons.append(
                    f"growth_coverage_drop_{drop:.1%}_exceeds_{config.GROWTH_COVERAGE_MAX_DROP:.0%}"
                )

    if publish and dataset.get("mode") != "full":
        reasons.append("publish_requires_full_universe")
    if publish and not reasons and dataset.get("mode") == "full":
        pass

    return GateResult(ok=not reasons, reasons=reasons, metrics=metrics)
