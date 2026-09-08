from __future__ import annotations

from typing import Any, Mapping

from src.mtf_engine.alignment import AlignmentResult, evaluate_alignment
from src.mtf_engine.bias import MarketBias, bias_from_structure

SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("D1", "H4", "H1", "M15", "M5")


class TimeframeManager:
    """Build timeframe biases and enforce the top-down trading hierarchy."""

    hierarchy = SUPPORTED_TIMEFRAMES

    def analyze(self, analyses: Mapping[str, Any] | None) -> AlignmentResult:
        """Evaluate MarketStructure or MarketBias values without raising on gaps."""
        biases: dict[str, MarketBias] = {}
        for timeframe, analysis in (analyses or {}).items():
            normalized = self.normalize_timeframe(timeframe)
            if normalized not in SUPPORTED_TIMEFRAMES or analysis is None:
                continue
            if isinstance(analysis, MarketBias):
                biases[normalized] = analysis
            else:
                biases[normalized] = bias_from_structure(analysis, normalized)
        return evaluate_alignment(biases)

    def evaluate(self, analyses: Mapping[str, Any] | None) -> AlignmentResult:
        """Alias for callers that treat the manager as a decision evaluator."""
        return self.analyze(analyses)

    @staticmethod
    def normalize_timeframe(timeframe: Any) -> str:
        value = str(timeframe or "").strip().upper()
        return {"DAILY": "D1", "DAY": "D1", "1D": "D1"}.get(value, value)
