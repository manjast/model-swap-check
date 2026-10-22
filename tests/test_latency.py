"""T-R12: offline sequential study, spending, frozen inputs and deterministic timing replay."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeAdapter, FakeClock, Handler, items, ok_body, request_text
from test_golden import GOLDEN, load_golden

from swapcheck import cost, latency, runner
from swapcheck.budget import BudgetConfig
from swapcheck.configs import Configuration, load_configurations
from swapcheck.data import item_list_hash
from swapcheck.decide import write_decisions
from swapcheck.http import Clock, Sender
from swapcheck.manifest import Manifest, ManifestRun, load_manifest, save_manifest
from swapcheck.prompt import Prompt
from swapcheck.providers.base import WARMUP_TEXT, HttpRequest
from swapcheck.records import Attempt, Timing, Usage, read_meta, read_rows
from swapcheck.schema import schema_sha256

CONFIGS = load_configurations()
StudyRunner = Callable[[Handler, int, float], Coroutine[Any, Any, latency.Study]]


def test_report_refuses_missing_study(tmp_path: Path) -> None:
    with pytest.raises(latency.LatencyError, match="found 0"):
        latency.write_report(tmp_path / "runs", tmp_path / "report")


class StudyAdapter(FakeAdapter):
    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest:
        request = super().build_request(cfg, prompt, text, cache_key)
        request.headers["x-test-config"] = cfg.id
        return request


@pytest.fixture
def study_runner(tmp_path: Path, incumbent: Prompt, monkeypatch: pytest.MonkeyPatch) -> StudyRunner:
    monkeypatch.setattr(latency, "head_commit", lambda _: "a" * 40)
    entries = [
        ManifestRun(
            contract_tag="contract-v2" if cid == "jev-noul" else "contract-v1",
            contract_tag_commit="b" * 40,
            config_id=cid,
            split="cert",
            run_id=f"{cid}-cert",
            config_sha256=CONFIGS[cid].sha256(),
            prompt_sha256=incumbent.sha256(),
            schema_sha256=schema_sha256(CONFIGS[cid], incumbent),
            item_list_sha256=item_list_hash(items(5)),
        )
        for cid in latency.ORDER
    ]
    save_manifest(tmp_path / "runs", Manifest(runs=entries))

    async def run(handler: Handler, rounds: int = 3, cap: float = 100.0) -> latency.Study:
        clock = FakeClock()

        async def probe(host: str, _: Clock) -> float:
            return 12.0

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            senders = {cid: Sender(client, StudyAdapter(), "test", clock=clock) for cid in latency.ORDER}
            return await latency.run_study(
                client="Test city, wired network",
                rounds=rounds,
                items=items(5),
                configs=CONFIGS,
                prompts={cid: incumbent for cid in latency.ORDER},
                senders=senders,
                prices=cost.load_prices(),
                budget=BudgetConfig(
                    caps_usd={p: cap for p in ("openai", "anthropic", "typesafe")},
                    reserve_margin_usd=0.5,
                ),
                runs_dir=tmp_path / "runs",
                repo_root=tmp_path,
                clock=clock,
                probe=probe,
            )

    return run


async def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=ok_body())


def test_rotation_is_sequential_and_warmups_precede_calls(study_runner: StudyRunner, tmp_path: Path) -> None:
    in_flight = 0
    peak = 0
    texts: list[str] = []
    observed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        texts.append(request_text(request))
        observed.append(request.headers["x-test-config"])
        await asyncio.sleep(0)
        in_flight -= 1
        return httpx.Response(200, json=ok_body())

    study = asyncio.run(study_runner(handler, 3, 100.0))
    assert study.complete and peak == 1
    assert texts[:18] == [WARMUP_TEXT] * 18
    assert texts[18:] == [item.text for item in items(3) for _ in latency.ORDER]
    for r in range(3):
        calls = [call for call in study.calls if call.round == r]
        assert [call.config_id for call in calls] == list(latency.ORDER[r:] + latency.ORDER[:r])
        assert [call.position for call in calls] == list(range(6))
        assert observed[18 + r * 6 : 18 + (r + 1) * 6] == list(latency.ORDER[r:] + latency.ORDER[:r])
    assert len(study.probes) == 3
    assert len(read_meta(tmp_path / "runs" / study.run_ids["inc"]).warmups) == 16
    spent = cost.spent_usd(tmp_path / "runs", cost.load_prices(), CONFIGS)
    expected: dict[str, float] = {}
    for cid, rid in study.run_ids.items():
        cfg = CONFIGS[cid]
        expected[cfg.provider] = expected.get(cfg.provider, 0.0) + read_meta(tmp_path / "runs" / rid).totals.billed_usd
    assert spent == pytest.approx(expected)


@pytest.mark.parametrize("field", ["config_sha256", "prompt_sha256", "schema_sha256"])
def test_frozen_hash_mismatch_refuses_before_http(study_runner: StudyRunner, tmp_path: Path, field: str) -> None:
    path = tmp_path / "runs" / "manifest.yaml"
    manifest = load_manifest(path.parent)
    manifest.runs[0] = manifest.runs[0].model_copy(update={field: "changed"})
    save_manifest(path.parent, manifest)

    async def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP must not start for unfrozen settings")

    with pytest.raises(latency.LatencyError, match="differs from frozen"):
        asyncio.run(study_runner(forbidden, 1, 100.0))
    assert not list(path.parent.glob("*/study.json"))


def test_budget_refusal_marks_every_run_incomplete_and_refuses_report(
    study_runner: StudyRunner, tmp_path: Path
) -> None:
    study = asyncio.run(study_runner(ok, 3, 0.50001))
    assert not study.complete
    assert study.incomplete_reason == "budget cap"
    assert all(not read_meta(tmp_path / "runs" / rid).complete for rid in study.run_ids.values())
    with pytest.raises(latency.LatencyError, match="incomplete"):
        latency.write_report(tmp_path / "runs", tmp_path / "report")


def test_provider_budget_is_shared_across_configurations(
    study_runner: StudyRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cost, "attempt_cost_usd", lambda prices, cfg, usage: 1.0)
    monkeypatch.setattr(cost, "reservation_usd", lambda prices, cfg, usage: 1.0)
    study = asyncio.run(study_runner(ok, 3, 19.5))
    assert not study.complete
    assert [call.config_id for call in study.calls] == ["inc", "luna-none"]
    assert cost.spent_usd(tmp_path / "runs", cost.load_prices(), CONFIGS)["openai"] == 19.0


def test_report_quantiles_residuals_retries_and_connections(study_runner: StudyRunner, tmp_path: Path) -> None:
    study = asyncio.run(study_runner(ok, 5, 100.0))
    for rid in study.run_ids.values():
        run_dir = tmp_path / "runs" / rid
        rows = read_rows(run_dir)
        for i, row in enumerate(rows):
            final = Attempt(
                number=2 if i == 0 else 1,
                http_status=400 if i == 4 else 200,
                error="http_400" if i == 4 else None,
                latency_ms=float((i + 1) * 100),
                headers={"openai-processing-ms": str((4 - i) * 10)},
                timing=Timing(
                    headers_ms=float((i + 1) * 50), connect_ms=10.0 if i == 0 else None, tls_ms=20.0 if i == 0 else None
                ),
            )
            row.attempts = [Attempt(number=1, http_status=503, error="http_503"), final] if i == 0 else [final]
            row.status = "api_error" if i == 4 else "ok"
        runner._write_final_rows(run_dir, rows)
    output = latency.write_report(tmp_path / "runs", tmp_path / "report")
    first = output.read_bytes()
    # Four successes: total [100,200,300,400], headers [50,100,150,200],
    # server [40,30,20,10], per-call residual [10,70,130,190].
    assert "| inc | 4 | 1 | 1 | 300 / 400 | 150 / 200 | 30 / 40 | 130 / 190 |" in first.decode()
    assert "| fake.invalid | 12 / 12 | 0 | 6 | 10 | 20 |" in first.decode()
    latency.write_report(tmp_path / "runs", tmp_path / "report")
    assert output.read_bytes() == first
    assert b"customer message" not in first
    second = tmp_path / "runs" / "latency-second"
    second.mkdir()
    (second / "study.json").write_bytes((tmp_path / "runs" / study.study_id / "study.json").read_bytes())
    with pytest.raises(latency.LatencyError, match="found 2"):
        latency.write_report(tmp_path / "runs", tmp_path / "report")


def test_decision_replay_ignores_latency_records(study_runner: StudyRunner, tmp_path: Path) -> None:
    study = asyncio.run(study_runner(ok, 1, 100.0))
    root = tmp_path / "golden"
    shutil.copytree(GOLDEN, root)
    args = load_golden(root)
    write_decisions(*args, tmp_path / "before")
    shutil.copytree(tmp_path / "runs" / study.study_id, root / "runs" / study.study_id)
    for rid in study.run_ids.values():
        shutil.copytree(tmp_path / "runs" / rid, root / "runs" / rid)
    write_decisions(*args, tmp_path / "after")
    assert {p.name: p.read_bytes() for p in (tmp_path / "before").iterdir()} == {
        p.name: p.read_bytes() for p in (tmp_path / "after").iterdir()
    }


def test_attempt_trace_events_and_opt_out_serialization(incumbent: Prompt) -> None:
    async def run(enabled: bool) -> Attempt:
        clock = FakeClock()

        async def handler(request: httpx.Request) -> httpx.Response:
            if enabled:
                trace = request.extensions["trace"]
                for event, step in [
                    ("connection.connect_tcp.started", 0.0),
                    ("connection.connect_tcp.complete", 0.01),
                    ("connection.start_tls.started", 0.0),
                    ("connection.start_tls.complete", 0.02),
                    ("http11.receive_response_headers.complete", 0.03),
                ]:
                    clock.t += step
                    await trace(event, {})
            return httpx.Response(200, json=ok_body())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = FakeAdapter()
            sender = Sender(client, adapter, "test", clock=clock, trace_timing=enabled)
            result = await sender.send(
                adapter.build_request(CONFIGS["inc"], incumbent, "synthetic", None),
                tokens=0,
                parse=lambda body: adapter.parse_response(CONFIGS["inc"], incumbent, body),
                timeout_usage=lambda: Usage(),
            )
            return result.final

    traced = asyncio.run(run(True))
    assert traced.timing is not None
    assert traced.timing.connect_ms == pytest.approx(10)
    assert traced.timing.tls_ms == pytest.approx(20)
    assert traced.timing.headers_ms == pytest.approx(60)
    assert "timing" not in json.loads(asyncio.run(run(False)).model_dump_json())
