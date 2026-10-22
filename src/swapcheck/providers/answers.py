"""Validation shared by the decision-interface adapters (Jev, `luna-dec`; spec §9.2).

Each check raises `InvalidAnswer` with the `invalid_output` error code; the adapters map it to a row.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

PROBABILITY_SUM_TOLERANCE = 0.01


class InvalidAnswer(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def number(value: Any) -> float | None:
    """`value` as a float if it is a JSON number (not a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def unit(answer: Mapping[str, Any], field: str, code_prefix: str) -> float:
    """A required number in [0, 1]; error codes `<code_prefix>_not_numeric` / `<code_prefix>_out_of_range`."""
    if field not in answer:
        raise InvalidAnswer("missing_field")
    value = number(answer[field])
    if value is None:
        raise InvalidAnswer(f"{code_prefix}_not_numeric")
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        raise InvalidAnswer(f"{code_prefix}_out_of_range")
    return value


def probability_map(probabilities: Mapping[str, Any], options: list[str]) -> dict[str, float]:
    """Per-option probabilities whose keys are exactly `options` and whose sum is 1 ± 0.01."""
    if set(probabilities) != set(options):
        raise InvalidAnswer("probabilities_keys")
    values = {k: number(v) for k, v in probabilities.items()}
    clean = {k: v for k, v in values.items() if v is not None and math.isfinite(v)}
    if len(clean) != len(values):
        raise InvalidAnswer("probabilities_not_numeric")
    if abs(sum(clean.values()) - 1.0) > PROBABILITY_SUM_TOLERANCE + 1e-9:  # 1e-9: float slack at the bound
        raise InvalidAnswer("probabilities_sum")
    return clean
