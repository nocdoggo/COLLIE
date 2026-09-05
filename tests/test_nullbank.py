"""Task 8.5 — the null-audit bank: counts, strata, fragility, non-reachability.

The statistical tests pool episodes per stratum rather than trusting one trajectory, the same
way the official parameters were recovered (research notes §1). The non-reuse assertion (R5.5)
is static: it scans the source tree, so no caller discipline is being trusted.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from collie.contracts import ObservationMode, Split, find_hidden_state
from collie.data.nullbank import (
    BANK_SIZE,
    FRAGILITY_SIZE,
    FragilityViolation,
    NullAlertSchedule,
    NullGroup,
    NullStratum,
    build_nullbank,
    generate_null_episode,
)
from collie.data.splits import (
    HELD_OUT_COMBO,
    NULL_BANK_BASE,
    build_rollouts,
    seed_pools,
)
from collie.data.writer import write_null
from collie.sim.loader import load_instance
from tools.build_shockspec import render_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# counts, balance, seeds (R5.1, R5.4, R5.5)
# ---------------------------------------------------------------------------


def test_nullbank_counts_and_balance() -> None:
    bank = build_nullbank()
    assert len(bank) == BANK_SIZE + FRAGILITY_SIZE == 1300
    well = [r for r in bank if r.group is NullGroup.WELL_SPECIFIED]
    assert len(well) == BANK_SIZE
    assert Counter(r.stratum for r in well) == {s: 200 for s in NullStratum}
    assert Counter(r.schedule for r in well) == {s: 250 for s in NullAlertSchedule}
    frag = [r for r in bank if r.group is NullGroup.FRAGILITY]
    assert len(frag) == FRAGILITY_SIZE
    assert Counter(r.violation for r in frag) == {v: 75 for v in FragilityViolation}
    assert Counter(r.schedule for r in frag) == {s: 75 for s in NullAlertSchedule}
    # The two groups are never pooled: every row declares its group.
    assert all(r.split is Split.NULL_AUDIT for r in bank)


def test_nullbank_seeds_disjoint_from_every_other_pool() -> None:
    bank_seeds = {r.seed for r in build_nullbank()}
    assert len(bank_seeds) == 1300
    assert bank_seeds == {NULL_BANK_BASE + i for i in range(1300)}
    pools = seed_pools()
    for name, pool in pools.items():
        if name != "null_bank":
            assert bank_seeds.isdisjoint(pool), f"bank seeds leak into {name}"
    # and the test/dev/cal rollouts never reference a bank seed
    for split in (Split.TEST, Split.DEV, Split.CAL):
        assert {r.seed for r in build_rollouts(split)}.isdisjoint(bank_seeds)


def test_no_audit_trajectory_is_reachable_from_other_code() -> None:
    """R5.5, statically: the bank's seed range is named only by the registry, the bank itself,
    and the manifest builder. Nothing in tuning, compiler-selection, or confirmatory code can
    reach an audit trajectory without naming that range."""
    allowed = {
        "collie/data/splits.py",
        "collie/data/nullbank.py",
        "tools/build_shockspec.py",
    }
    offenders = []
    for path in (*REPO_ROOT.glob("collie/**/*.py"), *REPO_ROOT.glob("tools/**/*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in allowed or "/fakes/" in rel:
            continue
        if "NULL_BANK_BASE" in path.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, f"bank seed range referenced outside its owners: {offenders}"


def test_manifest_rows_carry_null_audit_split_only_for_the_bank() -> None:
    manifest = json.loads(render_manifest())
    audit = [r for r in manifest["rollouts"] if r["split"] == "null_audit"]
    assert audit == [], "no bank trajectory may appear among the experimental rollouts"
    assert all(r["split"] == "null_audit" for r in manifest["null_bank"])
    assert len(manifest["rollouts"]) == 640 + 48 + 4 + 144 + 96


def test_nullbank_is_deterministic() -> None:
    assert build_nullbank() == build_nullbank()
    row = build_nullbank()[0]
    assert generate_null_episode(row) == generate_null_episode(row)


# ---------------------------------------------------------------------------
# stratum laws and fragility violations, checked statistically
# ---------------------------------------------------------------------------


def _pooled(stratum: NullStratum, n: int = 40) -> np.ndarray:
    rows = [r for r in build_nullbank() if r.stratum is stratum][:n]
    return np.array([generate_null_episode(r).demand for r in rows])


def _lag1(paths: np.ndarray) -> float:
    x = paths - paths.mean(axis=1, keepdims=True)
    return float(np.sum(x[:, 1:] * x[:, :-1]) / np.sum(x[:, :-1] ** 2))


def test_well_specified_strata_follow_their_registered_laws() -> None:
    stationary = _pooled(NullStratum.STATIONARY_IID)
    assert abs(stationary.mean() - 100.0) < 2.0
    assert abs(stationary.std(ddof=1) - 25.0) < 3.0

    seasonal = _pooled(NullStratum.SEASONAL)
    centered = seasonal - seasonal.mean(axis=1, keepdims=True)
    ac10 = np.mean([np.corrcoef(row[:-10], row[10:])[0, 1] for row in centered])
    assert ac10 > 0.4, "registered seasonal period 10 must be visible"

    over = _pooled(NullStratum.OVERDISPERSED)
    assert over.var(ddof=1) / over.mean() > 15.0, "registered dispersion sd=50"

    dependent = _pooled(NullStratum.DEPENDENT)
    assert _lag1(dependent) > 0.4, "registered AR(1) phi=0.7"

    censored_rows = [r for r in build_nullbank() if r.stratum is NullStratum.CENSORED]
    assert all(r.observation_mode is ObservationMode.CENSORED for r in censored_rows)
    censored = _pooled(NullStratum.CENSORED)
    assert abs(censored.mean() - 100.0) < 2.0, "censored shares the stationary demand law"


def _fragility_paths(violation: FragilityViolation, n: int = 40) -> np.ndarray:
    rows = [r for r in build_nullbank() if r.violation is violation][:n]
    return np.array([generate_null_episode(r).demand for r in rows])


def test_fragility_episodes_actually_violate_the_iid_null() -> None:
    auto = _fragility_paths(FragilityViolation.AUTOCORRELATION)
    assert _lag1(auto) > 0.3, "unexpected autocorrelation must be present"

    var = _fragility_paths(FragilityViolation.VARIANCE_CHANGE)
    ratio = var[:, 25:].var(axis=1, ddof=1) / var[:, :25].var(axis=1, ddof=1)
    assert float(np.median(ratio)) > 2.5, "variance doubles after the midpoint"

    seas = _fragility_paths(FragilityViolation.SEASONALITY)
    centered = seas - seas.mean(axis=1, keepdims=True)
    ac10 = float(np.mean([np.corrcoef(row[:-10], row[10:])[0, 1] for row in centered]))
    assert ac10 > 0.3, "unmodelled seasonality must be present"

    out = _fragility_paths(FragilityViolation.OUTLIERS)
    assert (out.max(axis=1) > 3.5 * 100.0).all(), "each episode carries 4x outliers"


def test_alert_periods_and_proposal_windows() -> None:
    for row in build_nullbank():
        if row.schedule is NullAlertSchedule.SILENT:
            assert row.alert_period is None
        else:
            assert row.alert_period is not None and 10 <= row.alert_period <= 20
        assert row.proposal_periods == (12, 24), "at most two, registered, constant"


# ---------------------------------------------------------------------------
# on disk: a null is an ordinary official-format instance
# ---------------------------------------------------------------------------


def test_null_instances_carry_no_incident_and_no_sidecar() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for row in build_nullbank()[::333]:  # one per group flavour
            ep = generate_null_episode(row)
            instance = write_null(
                root,
                relpath=row.relpath,
                demand=ep.demand,
                lead_times=ep.lead_times,
                train=ep.train_demand,
            )
            assert not (instance / "incident.json").exists()
            assert not (instance / "supply.csv").exists()
            loaded = load_instance(instance, episode_id=row.relpath, promised_lead_time=2)
            assert loaded.demand == ep.demand
            assert loaded.incident is None
            assert loaded.spec.source == "official"
            assert loaded.spec.family is None
            assert find_hidden_state(loaded.spec) == []


# ---------------------------------------------------------------------------
# manifest byte stability (the committed-list pattern of select_equivalence_set)
# ---------------------------------------------------------------------------


def test_manifest_byte_stable() -> None:
    assert render_manifest() == render_manifest()


def test_manifest_check_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from tools.build_shockspec import main

    out = tmp_path / "shockspec_v1.json"
    assert main(["--all", "--out", str(out)]) == 0
    assert main(["--all", "--check", "--out", str(out)]) == 0
    out.write_text(out.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(SystemExit, match="stale"):
        main(["--all", "--check", "--out", str(out)])


def test_manifest_counts_and_required_fields() -> None:
    manifest = json.loads(render_manifest())
    assert manifest["counts"] == {
        "test_main": 600,
        "test_silent_null": 20,
        "test_false_alert_null": 20,
        "dev": 144,
        "cal": 96,
        "extrapolation": 48,
        "ood": 4,
        "null_bank_well_specified": 1000,
        "null_bank_fragility": 300,
    }
    for row in manifest["rollouts"]:
        assert {
            "rollout_id",
            "split",
            "family",
            "seed",
            "information_condition",
            "independent_unit_id",
            "slice",
            "promised_lead_time",
            "onset",
            "instance",
        } <= row.keys()
    # onset is recorded for shocked episodes and only there
    shocked = [
        r
        for r in manifest["rollouts"]
        if r["slice"] in ("main", "held_out_combo", "extrapolation", "ood")
    ]
    assert shocked and all(r["onset"] is not None for r in shocked)
    nulls = [r for r in manifest["rollouts"] if r["slice"] in ("silent_null", "false_alert_null")]
    assert nulls and all(r["onset"] is None for r in nulls)
    onsets = {r["onset"] for r in shocked}
    assert min(onsets) >= 14 and max(onsets) <= 22


def test_manifest_records_the_combo_per_rollout() -> None:
    manifest = json.loads(render_manifest())
    main_rows = [r for r in manifest["rollouts"] if r["slice"] in ("main", "held_out_combo")]
    assert main_rows and all(r["combo"] is not None for r in main_rows)
    # held-out-combo discipline is auditable from the artifact alone
    held = [r for r in main_rows if r["held_out_combo"]]
    assert held and all(tuple(r["combo"]) == HELD_OUT_COMBO[r["family"]] for r in held)
