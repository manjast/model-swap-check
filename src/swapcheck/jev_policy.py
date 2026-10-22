"""Spec §7.9 (amendment 2): Jev at its top confidence, descriptive. `swapcheck jev-policy` writes
`decisions/A2-jev.md` from the `contract-v2` `jev-noul` run and the `contract-v1` runs of `inc` and `jev-c51`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path

from swapcheck.calibrate import Calibration, fit_candidate
from swapcheck.contract import Contract
from swapcheck.data import Item, item_list_hash
from swapcheck.decide import DecisionRefusal, policy_comparison, pp
from swapcheck.groups import IntentGroups
from swapcheck.manifest import load_manifest, verify_manifest
from swapcheck.outcomes import build_run, dev_weights, pair_runs
from swapcheck.records import ItemRow, RunMeta, read_meta, read_rows
from swapcheck.runner import run_validity

REPORT = "A2-jev.md"
TOP = 1.0  # Jev's top confidence after rounding: J1's threshold, and where J2 reads the Noul probability
POLICY_LIMIT = Fraction(1, 50)


def gated_rows(rows: Sequence[ItemRow]) -> list[ItemRow]:
    """J2's signal in place of the confidence: the Noul match probability where the Choice confidence is at the top,
    else 0. `match_probability` itself is unchanged, so the 0.5 Noul gate still applies."""
    out = []
    for row in rows:
        if row.status == "ok":
            if row.confidence is None or row.match_probability is None:
                raise ValueError(f"{row.item_id}: an ok jev-noul row needs a confidence and a Noul probability")
            row = row.model_copy(update={"confidence": row.match_probability if row.confidence >= TOP else 0.0})
        out.append(row)
    return out


def fit_j2(
    items: Sequence[Item],
    rows: Sequence[ItemRow],
    groups: IntentGroups,
    dev_counts: Mapping[str, int],
    cert_counts: Mapping[str, int],
) -> Calibration:
    """tau_J2: the §6 incumbent rule on the gated signal of a `jev-noul` dev run (API errors carry no weight)."""
    usable = gated_rows([row for row in rows if row.status != "api_error"])
    run = build_run(items, usable, split="dev", groups=groups, noul=True)
    return fit_candidate(run, dev_weights(run.truth, dev_counts, cert_counts), POLICY_LIMIT)


def write_jev_policy(
    runs_dir: Path,
    base: Contract,
    contract: Contract,
    items: Sequence[Item],
    groups: IntentGroups,
    output_dir: Path,
) -> str:
    """Verify both contracts' runs before writing the deterministic report; items are injectable for replay."""
    policy, a = contract.jev_policy, base.analysis
    if policy is None or a is None:
        raise DecisionRefusal([f"{contract.tag} has no Jev policy or {base.tag} no analysis (§7.9)"])
    manifest = load_manifest(runs_dir)
    problems = verify_manifest(manifest, base, runs_dir) + verify_manifest(manifest, contract, runs_dir)
    if policy.base_tag != base.tag or policy.incumbent_tau != a.incumbent_tau:
        problems.append(f"the Jev policy's base contract or τ_inc differs from {base.tag}")
    for cid in ("inc", "jev-c51"):
        if contract.configurations.get(cid) != base.configurations.get(cid):
            problems.append(f"{cid}: configuration hashes differ between {base.tag} and {contract.tag}")
    cert_hash = item_list_hash(list(items))
    if not (cert_hash == contract.item_lists.get("cert") == base.item_lists.get("cert")):
        problems.append("cert items differ from the contracts' cert item lists")
    wanted = {(base.tag, "inc"), (base.tag, "jev-c51"), (contract.tag, "jev-noul")}
    loaded: dict[str, tuple[RunMeta, list[ItemRow]]] = {}
    for entry in manifest.runs:
        run_dir = runs_dir / entry.run_id
        if entry.split != "cert" or (entry.contract_tag, entry.config_id) not in wanted:
            continue
        if not (run_dir / "run.json").exists():
            continue  # reported by verify_manifest
        meta, rows = read_meta(run_dir), read_rows(run_dir)
        ok, why = run_validity(meta, rows)
        if not ok or not meta.complete:
            problems.append(why if not ok else f"{entry.run_id}: run is incomplete")
        loaded[entry.config_id] = meta, rows
    problems += [f"{cid}: required cert run under {tag} missing" for tag, cid in sorted(wanted) if cid not in loaded]
    if problems:
        raise DecisionRefusal(problems)

    inc = build_run(items, loaded["inc"][1], split="cert", groups=groups)
    arms = (
        (
            f"J1: `jev-c51` at τ = {TOP:.2f}",
            "jev-c51",
            build_run(items, loaded["jev-c51"][1], split="cert", groups=groups),
            policy.j1,
        ),
        (
            "J2: `jev-noul`, Noul match probability ≥ τ_J2 where the Choice confidence is 1.00",
            "jev-noul",
            build_run(items, gated_rows(loaded["jev-noul"][1]), split="cert", groups=groups, noul=True),
            policy.j2,
        ),
    )
    lines = [
        "# Amendment 2: Jev at its top confidence (§7.9)",
        "",
        f"Contract `{contract.tag}` (analysis code `{policy.code_version}`); the incumbent and `jev-c51` reuse their "
        f"`{base.tag}` cert runs. Descriptive; no verdict. D-J stays as registered.",
        "",
        f"Incumbent: `{loaded['inc'][0].run_id}` at τ_inc = {policy.incumbent_tau:.2f}. Unweighted cert estimates on "
        "the paired items, two-sided 95% Wilson score intervals.",
    ]
    for title, cid, cand, frozen in arms:
        paired = pair_runs(inc, cand)
        ir, cr = paired.runs
        lines += [
            "",
            f"## {title}",
            "",
            f"Run `{loaded[cid][0].run_id}`; frozen τ = {frozen.tau:.2f} (weighted dev W {pp(frozen.dev_w)}, "
            f"A {pp(frozen.dev_a)}). Paired n={len(ir)}; dropped API-error/absent items={paired.dropped}.",
            "",
            *policy_comparison(ir, policy.incumbent_tau, cr, frozen.tau, a.slices),
        ]
    text = "\n".join(lines) + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / REPORT).write_text(text, encoding="utf-8")
    return text
