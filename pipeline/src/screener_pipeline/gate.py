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
    return coverage.get(key, 0) / listings


def evaluate_gate(meta: dict, baseline: dict | None = None, *, publish: bool = False) -> GateResult:
    reasons: list[str] = []
    coverage = meta.get("coverage") or {}
    dataset = meta.get("dataset") or {}
    run = meta.get("run") or {}
    universe = meta.get("universe") or {}
    metrics = {
        "mode": dataset.get("mode"),
        "status": run.get("status"),
        "listings": coverage.get("listings"),
        "eligible": universe.get("eligibleListings"),
        "growthRatio": _ratio(coverage, "growth"),
        "yahooProfileRatio": _ratio(coverage, "yahooProfile"),
    }

    if run.get("status") != "complete":
        reasons.append("incomplete_run")
    if dataset.get("mode") == "partial":
        reasons.append("partial_universe")
    if dataset.get("mode") == "full" and coverage.get("listings") != universe.get("eligibleListings"):
        reasons.append("missing_listings")
    if publish and dataset.get("mode") == "full":
        reasons.append("yahoo_terms_block_public_full_dataset")

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
        yahoo = _ratio(coverage, "yahooProfile")
        base_yahoo = _ratio(base_cov, "yahooProfile")
        if yahoo is not None and base_yahoo:
            drop = base_yahoo - yahoo
            metrics["yahooProfileDrop"] = drop
            if drop > config.YAHOO_PROFILE_COVERAGE_MAX_DROP:
                reasons.append(
                    f"yahoo_profile_coverage_drop_{drop:.1%}_exceeds_{config.YAHOO_PROFILE_COVERAGE_MAX_DROP:.0%}"
                )

    return GateResult(ok=not reasons, reasons=reasons, metrics=metrics)
