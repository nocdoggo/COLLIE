"""The null exposure Monte Carlo (analysis/commitment/mc_exposure.py): fast, tiny sizes.

Offline only: synthetic null paths, the frozen certify-then-hedge arm, scripted firings and a
fixed payload through the arm's replay seam. No model call.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from analysis.commitment import mc_exposure as mc
from analysis.commitment.cth import ALPHA, CertifyThenHedgeArm
from collie.contracts import TargetStream


def _cell(**kw) -> mc.Cell:
    base = {
        "law": "deterministic",
        "cv": 0.25,
        "tau": 10,
        "firings": 1,
        "lam": 0.0,
        "family": "demand_up",
        "regime": "plug_in",
    }
    return mc.Cell(**{**base, **kw})


def _run(cell: mc.Cell, rep: int = 0) -> tuple[CertifyThenHedgeArm, mc.EpisodeRow]:
    instance = mc.null_instance(cell.cv, rep, cell.law)
    arm = mc.build_arm(instance, cell)
    mc._runner(instance).run(arm)
    return arm, mc.run_cell_episode(instance, cell)


def test_seeds_are_in_the_reserved_range_and_laws_share_the_demand_path():
    assert mc.path_seed(mc.CVS[0], 0) >= 95_000_000
    assert mc.path_seed(mc.CVS[-1], mc.MAX_REPS - 1) < 97_000_000
    det = mc.null_instance(0.35, 7, "deterministic")
    reg = mc.null_instance(0.35, 7, "registered")
    assert det.demand == reg.demand
    assert det.spec.train_demand == reg.spec.train_demand
    assert len(det.demand) == mc.HORIZON and len(det.spec.train_demand) == mc.TRAIN_ROWS
    assert all(v >= 0 and float(v).is_integer() for v in det.demand)
    assert set(det.supply.lead_times) == {2.0}
    assert len(reg.supply.pause_active) == mc.HORIZON
    assert all(math.isinf(x) or x in {0, 1, 2, 3, 4} for x in reg.supply.lead_times)
    with pytest.raises(ValueError):
        mc.path_seed(0.2, 0)


@pytest.mark.parametrize("family", mc.FAMILIES)
def test_the_payload_registers_the_llm_family_with_the_whole_budget_at_lam_0(family):
    arm, row = _run(_cell(family=family, firings=2))
    assert [(h.key, h.firing, h.from_llm) for h in arm._hyps] == [
        (family, 1, True),
        (family, 2, True),
    ]
    assert all(h.spec.onset_window == mc.WINDOW for h in arm._hyps)
    assert [h.tau for h in arm._hyps] == [10, 10 + mc.SECOND_GAP]
    assert math.isclose(row.prior_total, mc.budget(2)) and math.isclose(mc.budget(2), 0.0375)
    assert row.consultations == 2 and row.n_dead == 0
    assert arm.channel is None and arm.replay is not None


def test_content_free_prior_spreads_the_budget_over_the_four_hypotheses():
    arm, row = _run(_cell(lam=1.0, family=None))
    assert sorted(h.key for h in arm._hyps) == ["demand_down", "demand_up", "lead_time", "pulse_up"]
    assert all(math.isclose(h.prior, ALPHA / 2 / 4) for h in arm._hyps)
    assert not any(h.from_llm for h in arm._hyps)
    assert math.isclose(row.prior_total, mc.budget(1))


def test_known_regime_gives_the_true_demand_baseline_and_leaves_arrivals_alone():
    cell = _cell(lam=0.25, cv=0.15, regime="known")
    known, _ = _run(cell)
    plug, _ = _run(replace(cell, regime="plug_in"))
    assert isinstance(known, mc.KnownNullArm)
    for h in known._hyps:
        if h.spec.target_stream is TargetStream.DEMAND:
            assert h.baseline == (100.0, 15.0)
    lt_known = next(h for h in known._hyps if h.key == "lead_time")
    lt_plug = next(h for h in plug._hyps if h.key == "lead_time")
    assert lt_known.baseline == lt_plug.baseline
    assert next(h for h in plug._hyps if h.key == "demand_up").baseline != (100.0, 15.0)


def test_the_shock_mass_is_zero_before_the_build_and_at_most_A_at_it():
    for regime in mc.REGIMES:
        _, row = _run(_cell(lam=0.25, regime=regime, tau=15))
        assert np.all(row.pi[:15] == 0.0)
        a = mc.budget(1)
        assert a - 1e-4 <= row.pi[15] <= a + 1e-9


def test_a_lam_0_lead_time_cell_is_the_same_under_both_regimes():
    cell = _cell(family="lead_time", firings=2)
    assert cell.regime_free and not _cell().regime_free
    _, a = _run(cell, rep=3)
    _, b = _run(replace(cell, regime="known"), rep=3)
    assert np.array_equal(a.pi, b.pi) and a.net == b.net


def test_bounds():
    assert math.isclose(mc.budget(1), 0.025)
    assert math.isclose(mc.ville_bound(0.0375, 0.5), 0.0375 * 0.5 / (0.5 * 0.9625))
    cell = _cell(firings=2, tau=20)
    a_t = mc.budget_path(cell)
    assert a_t[19] == 0.0 and math.isclose(a_t[20], 0.025) and math.isclose(a_t[26], 0.0375)


def test_a_tiny_run_is_deterministic_and_complete(tmp_path):
    stratum = mc.Stratum("main", "deterministic", (0.25,), ((0.0, "demand_up"),), 2)
    first = mc.run_mc([stratum])
    second = mc.run_mc([stratum])
    assert first["n_paths"] == 2 and first["n_cells"] == len(mc.TAUS) * 2 * 2
    for r in first["cells"]:
        assert r["n"] == 2 and math.isclose(r["A"], mc.budget(r["firings"]))
        assert set(r["P_sup"]) == {"0.1", "0.25", "0.5"}
        assert len(r["E_pi_t"]) == mc.HORIZON
    j1, m1 = mc.write_outputs(tmp_path / "a", first)
    j2, m2 = mc.write_outputs(tmp_path / "b", second)
    assert j1.read_bytes() == j2.read_bytes() and m1.read_bytes() == m2.read_bytes()
    assert "## Reading" in m1.read_text()


def _row(pi: np.ndarray, firings: int) -> mc.EpisodeRow:
    return mc.EpisodeRow(
        pi=pi,
        net=0.0,
        prior_total=mc.budget(firings),
        n_hypotheses=firings,
        n_dead=0,
        n_from_llm=firings,
        consultations=firings,
    )


def test_the_per_decision_check_is_against_A_t_and_skips_the_first_build():
    cell = _cell(firings=2, tau=10)
    acc = mc.CellAccumulator(cell, "main")
    pi = np.zeros(mc.HORIZON)
    pi[10] = mc.budget(1)  # decision 11, the first build: A_1 by construction
    pi[12] = 0.03  # decision 13: above A_1 = 0.025 (live), below A = 0.0375
    for _ in range(4):
        acc.add(_row(pi, 2), base_net=0.0)
    s = acc.summary()
    assert s["argmax_t"] == 13
    assert math.isclose(s["A_t_at_argmax"], 0.025)
    assert math.isclose(s["max_t_E_pi_minus_A_t"], 0.005)
    assert s["above_bound"]["max_t_E_pi_minus_A_t"] == "clear"
    assert math.isclose(s["max_t_E_pi_over_A_t"], 0.03 / 0.025)


def test_probability_flags_use_the_clopper_pearson_lower_bound():
    bound = mc.ville_bound(mc.budget(1), 0.5)
    assert mc._clopper_pearson_lower(0, 100) == 0.0
    low3, low9 = mc._clopper_pearson_lower(3, 100), mc._clopper_pearson_lower(9, 100)
    assert low3 < bound < 0.03 and low9 > bound
    assert mc._flag_prob(0.03, low3, bound) == "point"
    assert mc._flag_prob(0.09, low9, bound) == "clear"
    assert mc._flag_prob(0.02, 0.0, bound) is None


def test_a_regime_free_cell_is_listed_once_and_left_out_of_the_plug_in_reading():
    stratum = mc.Stratum("other_families", "deterministic", (0.25,), ((0.0, "lead_time"),), 1)
    result = mc.run_mc([stratum])
    assert {r["regime"] for r in result["cells"]} == set(mc.REGIMES)
    listed = mc._listed(result["cells"])
    assert len(listed) == len(result["cells"]) // 2
    assert all(r["regime"] == "known" for r in listed)
    md = mc.render_markdown(result)
    assert "Plug-in null" not in md and "Lead-time hypothesis alone" in md
    assert sum(line.startswith("| either |") for line in md.splitlines()) == len(listed)
