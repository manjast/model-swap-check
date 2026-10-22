"""T-M2 (power.py half): margin selection order, the 1% floor and the fallback exit (spec §7.3)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "analysis" / "power.py"


def _power() -> ModuleType:
    spec = importlib.util.spec_from_file_location("standalone_power_t_m2", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m2_selects_first_pair_in_overall_then_slice_order(monkeypatch: pytest.MonkeyPatch) -> None:
    power = _power()
    # Only (0.0075, 0.015) and (0.005, 0.03) reach 80%. δ_W-then-δ_S order must pick the stricter overall
    # margin first, even though its slice margin is the loosest.
    table = {(0.0075, 0.015): 0.81, (0.005, 0.03): 0.80}

    def fake_simulate(p_disc: dict[str, float], o: float, s: float, **_: object) -> dict[str, float]:
        return {"joint": table.get((o, s), 0.5)}

    monkeypatch.setattr(power, "simulate", fake_simulate)
    assert power.select_margins({}, sims=1, seed=1) == ((0.005, 0.03), 0.80, True)


def test_m2_fallback_when_no_pair_reaches_target(monkeypatch: pytest.MonkeyPatch) -> None:
    power = _power()

    def fake_simulate(p_disc: dict[str, float], o: float, s: float, **_: object) -> dict[str, float]:
        return {"joint": 0.799}

    monkeypatch.setattr(power, "simulate", fake_simulate)
    assert power.select_margins({}, sims=1, seed=1) == ((0.01, 0.03), 0.799, False)


def test_m2_floor_and_missing_slice(tmp_path: Path) -> None:
    power = _power()
    raw = dict.fromkeys(power.CERT_SLICES, 0.002) | {"out_of_scope": 0.04}
    path = tmp_path / "dev.json"
    path.write_text(json.dumps(raw))
    assert power.load_pdisc(str(path)) == dict.fromkeys(power.CERT_SLICES, 0.01) | {"out_of_scope": 0.04}
    del raw["cash"]
    path.write_text(json.dumps(raw))
    with pytest.raises(SystemExit, match="cash"):
        power.load_pdisc(str(path))


def test_m2_cli_exits_2_with_the_fallback_on_high_discordance(tmp_path: Path) -> None:
    path = tmp_path / "dev.json"
    path.write_text(json.dumps(dict.fromkeys(_power().CERT_SLICES, 0.5)))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--pdisc-json", str(path), "--sims", "200"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "selected: overall 1.00 pp, slice 3.0 pp" in result.stdout
