"""Task 8.1-8.4 — split counts, the seed registry, and the five integrity assertions.

Assertion 5 (the power rule cannot see test data) is checked **statically**: the test parses the
function's source and walks its AST, so no caller discipline is being trusted.
"""

from __future__ import annotations

import ast
import builtins
import dataclasses
import inspect
import math
import statistics
import textwrap

import pytest
from hypothesis import assume, given, settings

from collie.contracts import InformationCondition, Split
from collie.data.families.base import FAMILY_SHOCK
from collie.data.splits import (
    COMBO_A,
    CONDITIONS,
    EXTRAPOLATION_COMBO,
    FAMILIES,
    HELD_OUT_COMBO,
    N_FALSE_ALERT_NULL,
    N_SILENT_NULL,
    NULL_BANK_BASE,
    NULL_CONTROL_BASE,
    OOD_BASE,
    RolloutSlice,
    assert_held_out_combos_absent,
    assert_no_test_templates,
    assert_seed_pools_disjoint,
    assert_units_resolve,
    build_rollouts,
    build_units,
    combo_of_params,
    generate_ood_episode,
    required_confirmatory_seeds,
    seed_for,
    seed_pools,
)
from tests.strategies import st

# ---------------------------------------------------------------------------
# exact counts (R4.1, R4.2, R4.3)
# ---------------------------------------------------------------------------


def test_seed_pool_sizes_and_disjointness() -> None:
    pools = seed_pools()
    assert len(pools["test"]) == 150 == 6 * 25
    assert len(pools["dev"]) == 36 == 6 * 6
    assert len(pools["cal"]) == 24 == 6 * 4
    assert_seed_pools_disjoint(pools)


def test_rollout_counts_are_exact() -> None:
    test = build_rollouts(Split.TEST)
    paired = [r for r in test if r.slice in (RolloutSlice.MAIN, RolloutSlice.HELD_OUT_COMBO)]
    assert len(paired) == 600 == 6 * 25 * 4
    assert sum(1 for r in test if r.slice is RolloutSlice.SILENT_NULL) == N_SILENT_NULL
    assert sum(1 for r in test if r.slice is RolloutSlice.FALSE_ALERT_NULL) == N_FALSE_ALERT_NULL
    assert len(paired) + N_SILENT_NULL + N_FALSE_ALERT_NULL == 640
    assert len(build_rollouts(Split.DEV)) == 144 == 6 * 4 * 6
    assert len(build_rollouts(Split.CAL)) == 96 == 6 * 4 * 4


def test_every_main_unit_has_four_paired_conditions() -> None:
    for split in (Split.TEST, Split.DEV, Split.CAL):
        rollouts = build_rollouts(split)
        for unit in build_units(split):
            conditions = {
                r.information_condition
                for r in rollouts
                if r.independent_unit_id == unit.independent_unit_id
            }
            assert conditions == set(CONDITIONS)


def test_held_out_combo_counts() -> None:
    test = build_rollouts(Split.TEST)
    held = [r for r in test if r.slice is RolloutSlice.HELD_OUT_COMBO]
    assert len(held) == 5 * 6 * 4, "five test seeds per family carry the held-out combo"
    assert {r.params.onset for r in held} == {None}, "onset stays seed-drawn"
    for r in held:
        assert r.params is not None
        assert r.params.family in FAMILIES


def test_extrapolation_and_ood_slices() -> None:
    test = build_rollouts(Split.TEST)
    extra = [r for r in test if r.slice is RolloutSlice.EXTRAPOLATION]
    assert len(extra) == 6 * 2 * 4
    assert {r.family for r in extra} == set(FAMILIES)
    ood = [r for r in test if r.slice is RolloutSlice.OOD]
    assert len(ood) == 4, "one held-out composition crossed with four conditions"


def test_registry_is_deterministic() -> None:
    for split in Split:
        if split is Split.NULL_AUDIT:
            continue
        assert build_rollouts(split) == build_rollouts(split)


# ---------------------------------------------------------------------------
# assertion 1: seed pools pairwise disjoint
# ---------------------------------------------------------------------------


@given(
    family=st.sampled_from(FAMILIES),
    split=st.sampled_from([Split.TEST, Split.DEV, Split.CAL]),
    index=st.integers(min_value=0, max_value=24),
)
@settings(max_examples=200)
def test_seed_for_stays_inside_its_pool(family: int, split: Split, index: int) -> None:
    assume(index < {Split.TEST: 25, Split.DEV: 6, Split.CAL: 4}[split])
    seed = seed_for(family, split, index)
    assert seed in seed_pools()[split.value]
    for name, pool in seed_pools().items():
        if name != split.value:
            assert seed not in pool


def test_seed_for_rejects_out_of_pool_indices() -> None:
    with pytest.raises(ValueError, match="outside the dev pool"):
        seed_for(1, Split.DEV, 6)
    with pytest.raises(ValueError, match="family must be one of"):
        seed_for(9, Split.TEST, 0)


def test_disjointness_assertion_fails_on_a_doctored_registry() -> None:
    pools = seed_pools()
    doctored = {**pools, "dev": pools["dev"] | {next(iter(pools["test"]))}}
    with pytest.raises(AssertionError, match="overlap"):
        assert_seed_pools_disjoint(doctored)


# ---------------------------------------------------------------------------
# assertion 2: no test template id in dev or cal
# ---------------------------------------------------------------------------


def test_no_test_template_in_dev_or_cal() -> None:
    by_split = {s: build_rollouts(s) for s in (Split.TEST, Split.DEV, Split.CAL)}
    assert_no_test_templates(by_split)


def test_template_assertion_fails_on_a_leak() -> None:
    by_split = {s: build_rollouts(s) for s in (Split.TEST, Split.DEV, Split.CAL)}
    leaked = by_split[Split.DEV][0]
    doctored = (
        dataclasses.replace(leaked, template_id="tpl_test_f1_00"),  # a real test template id
        *by_split[Split.DEV][1:],
    )
    with pytest.raises(AssertionError, match="test template ids"):
        assert_no_test_templates({**by_split, Split.DEV: doctored})


# ---------------------------------------------------------------------------
# assertion 3: held-out combos absent from dev and cal
# ---------------------------------------------------------------------------


def test_held_out_combos_absent_from_dev_and_cal() -> None:
    by_split = {s: build_rollouts(s) for s in (Split.TEST, Split.DEV, Split.CAL)}
    assert_held_out_combos_absent(by_split)
    for split in (Split.DEV, Split.CAL):
        for r in by_split[split]:
            assert r.params is not None
            combo = _combo_of(r.params)
            assert combo in COMBO_A[r.params.family]
            assert combo != HELD_OUT_COMBO[r.params.family]
            assert combo != EXTRAPOLATION_COMBO[r.params.family]


_combo_of = combo_of_params  # the manifest and this suite share one inverse


# ---------------------------------------------------------------------------
# assertion 4: every independent unit resolves to exactly one seed
# ---------------------------------------------------------------------------


def test_units_resolve_to_one_seed() -> None:
    for split in (Split.TEST, Split.DEV, Split.CAL):
        assert_units_resolve(build_rollouts(split))
    by_unit: dict[str, set[int]] = {}
    for r in build_rollouts(Split.TEST):
        by_unit.setdefault(r.independent_unit_id, set()).add(r.seed)
    assert len(by_unit) == 150 + 12 + 1 + 40


def test_unit_resolution_assertion_fails_on_a_collision() -> None:
    rollouts = list(build_rollouts(Split.DEV))
    doctored = (*rollouts[1:], dataclasses.replace(rollouts[0], seed=rollouts[0].seed + 1))
    with pytest.raises(AssertionError, match="resolving to != 1 seed"):
        assert_units_resolve(doctored)


# ---------------------------------------------------------------------------
# assertion 5: the power rule cannot see test data — checked statically
# ---------------------------------------------------------------------------


def _referenced_names(fn) -> set[str]:
    """All names loaded in the function body, per its AST."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def test_power_rule_source_references_no_test_data_path() -> None:
    source = inspect.getsource(required_confirmatory_seeds)
    tree = ast.parse(textwrap.dedent(source))

    params = set(inspect.signature(required_confirmatory_seeds).parameters)
    assert params == {"calibrated_effects", "alpha", "power"}, params
    assert not any("test" in p.lower() for p in params)

    # Every Name loaded must be a parameter, a local, a whitelisted pure module, or a builtin.
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    allowed = params | assigned | {"math", "statistics", "Sequence"} | set(dir(builtins))
    unknown = _referenced_names(required_confirmatory_seeds) - allowed
    assert not unknown, f"power rule references non-local names: {unknown}"

    forbidden = ("Split", "build_rollouts", "build_units", "seed_pools", "seed_for")
    for name in forbidden:
        assert name not in source, f"power rule source mentions {name}"
    # The call graph is one level deep: nothing the rule calls reaches project code.
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls <= {"fmean", "stdev", "NormalDist", "inv_cdf", "ceil"}, calls


def test_power_rule_behaviour() -> None:
    # z_0.975 = 1.960, z_0.8 = 0.8416; effects 1.0 +/- 0.5 -> n = ceil((2.8016*0.5/1.0)^2)
    n = required_confirmatory_seeds([0.5, 1.0, 1.5])
    z = statistics.NormalDist().inv_cdf(0.975) + statistics.NormalDist().inv_cdf(0.8)
    assert n == math.ceil((z * statistics.stdev([0.5, 1.0, 1.5])) ** 2)
    assert n >= 1
    with pytest.raises(ValueError, match="at least two"):
        required_confirmatory_seeds([1.0])
    with pytest.raises(ValueError, match="no positive effect"):
        required_confirmatory_seeds([0.0, -1.0, -0.5])
    assert required_confirmatory_seeds([1.0, 1.0, 1.0]) == 1, "zero variance needs one unit"


# ---------------------------------------------------------------------------
# the OOD composition
# ---------------------------------------------------------------------------


def test_ood_episode_is_a_pulse_crossed_with_a_loss_burst() -> None:
    ep = generate_ood_episode(seed=OOD_BASE, horizon=50, onset=17)
    onset = ep.incident.onset_period
    assert ep.demand[: onset - 1] == ep.twin_demand[: onset - 1]
    assert ep.demand[onset - 1 : onset + 2] != ep.twin_demand[onset - 1 : onset + 2]
    assert ep.demand[onset + 2 :] == ep.twin_demand[onset + 2 :], "pulse ends after 3 periods"
    lost = [t for t, lt in enumerate(ep.lead_times, 1) if math.isinf(lt)]
    assert lost == [onset, onset + 1], "the loss burst covers exactly two order periods"
    assert ep.incident.conditional_independence is False
    assert ep.incident.supply_effect is not None


def test_ood_episode_is_deterministic() -> None:
    assert generate_ood_episode(seed=1, horizon=50) == generate_ood_episode(seed=1, horizon=50)


def test_ood_out_of_runway_is_refused() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        generate_ood_episode(seed=1, horizon=20, onset=20)


# ---------------------------------------------------------------------------
# registry coverage of the contracted vocabularies
# ---------------------------------------------------------------------------


def test_all_six_families_present_in_every_split() -> None:
    for split in (Split.TEST, Split.DEV, Split.CAL):
        families = {u.family for u in build_units(split) if u.slice is RolloutSlice.MAIN}
        held = {u.family for u in build_units(split) if u.slice is RolloutSlice.HELD_OUT_COMBO}
        assert families | held == set(FAMILIES)
        assert set(FAMILY_SHOCK) == set(FAMILIES)


def test_null_control_seeds_are_disjoint_from_the_bank() -> None:
    controls = {
        r.seed
        for r in build_rollouts(Split.TEST)
        if r.slice in (RolloutSlice.SILENT_NULL, RolloutSlice.FALSE_ALERT_NULL)
    }
    assert len(controls) == 40
    assert all(NULL_CONTROL_BASE <= s < NULL_BANK_BASE for s in controls)
    assert controls.isdisjoint(seed_pools()["null_bank"])


def test_no_alert_rollouts_carry_no_template() -> None:
    for r in build_rollouts(Split.DEV):
        if r.information_condition is InformationCondition.NO_ALERT:
            assert r.template_id is None
        else:
            assert r.template_id is not None
