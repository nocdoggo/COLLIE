"""Task 4 — instance loading, the project-owned sidecars, and instance stratification.

The load-bearing claim here is **sidecar neutrality**: an official instance must load identically
whether or not a ``supply.csv`` is present that merely restates what ``test.csv`` already says. If
that failed, every shocked episode would carry an unmeasured confound from the file format itself,
and the comparison against baseline twins would be worthless.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from collie.contracts import (
    ObservationMode,
    ShockFamily,
    SupplyEffectKind,
    find_hidden_state,
)
from collie.data.instances import (
    InstanceKey,
    _lead_time_label,
    _read_header_economics,
    cost_ratio_label,
    enumerate_instances,
    stratified_sample,
    stratify,
)
from collie.sim.loader import load_instance, promised_lead_time_for
from collie.sim.runner import EpisodeRunner
from tests.test_episode_runner import ConstantController

# ---------------------------------------------------------------------------
# synthetic instance fixtures on disk
# ---------------------------------------------------------------------------

ITEM = "SKU9"
DEMAND = (10.0, 12.0, 8.0, 15.0)
LEADS = (1.0, 1.0, 1.0, 1.0)


def write_instance(
    root: Path,
    *,
    lead_times: tuple[float, ...] = LEADS,
    with_train: bool = True,
    description: str | None = None,
) -> Path:
    """Write a minimal official-format instance under a ``lead_time_4`` parent."""
    instance = root / "lead_time_4" / "inst01"
    instance.mkdir(parents=True)

    cols = [f"exact_dates_{ITEM}", f"demand_{ITEM}"]
    if description is not None:
        cols.append(f"description_{ITEM}")
    cols += [f"lead_time_{ITEM}", f"profit_{ITEM}", f"holding_cost_{ITEM}"]

    lines = [",".join(cols)]
    for index, demand in enumerate(DEMAND):
        row = [f"2019/1/{index + 1}", str(demand)]
        if description is not None:
            row.append(description)
        lead = lead_times[index]
        row += ["inf" if math.isinf(lead) else str(lead), "4.0", "1.0"]
        lines.append(",".join(row))
    (instance / "test.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if with_train:
        train = [f"exact_dates_{ITEM},demand_{ITEM}"]
        train += [f"2018/1/{i + 1},{v}" for i, v in enumerate((9.0, 11.0, 10.0))]
        (instance / "train.csv").write_text("\n".join(train) + "\n", encoding="utf-8")
    return instance


def write_supply_sidecar(
    instance: Path,
    *,
    lead_times: tuple[float, ...] | None = None,
    pause: tuple[bool, ...] | None = None,
) -> None:
    cols = ["period"]
    if lead_times is not None:
        cols.append("lead_time")
    if pause is not None:
        cols.append("pause_active")
    lines = [",".join(cols)]
    for index in range(len(DEMAND)):
        row = [str(index + 1)]
        if lead_times is not None:
            lead = lead_times[index]
            row.append("inf" if math.isinf(lead) else str(lead))
        if pause is not None:
            row.append("true" if pause[index] else "false")
        lines.append(",".join(row))
    (instance / "supply.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# basic loading
# ---------------------------------------------------------------------------


def test_loads_the_official_format(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    loaded = load_instance(instance, episode_id="unit/inst01")

    assert loaded.spec.episode_id == "unit/inst01"
    assert loaded.spec.item_id == ITEM
    assert loaded.spec.horizon == len(DEMAND)
    assert loaded.spec.promised_lead_time == 4, "derived from the lead_time_4 path component"
    assert loaded.spec.profit_per_unit == 4.0
    assert loaded.spec.holding_cost_per_unit == 1.0
    assert loaded.spec.order_cap == math.inf, "the benchmark imposes no cap"
    assert loaded.spec.observation_mode is ObservationMode.UNCENSORED
    assert loaded.demand == DEMAND
    assert loaded.supply.lead_times == LEADS
    assert loaded.supply.pause_active == ()
    assert loaded.incident is None
    assert loaded.spec.train_demand == (9.0, 11.0, 10.0)
    assert loaded.spec.source == "official"


def test_episode_id_defaults_to_the_directory_name(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    assert load_instance(instance).spec.episode_id == "inst01"


def test_description_column_becomes_product_text(tmp_path: Path) -> None:
    instance = write_instance(tmp_path, description="Ladies knitted sweater")
    assert load_instance(instance).spec.product_text == "Ladies knitted sweater"


def test_absent_description_leaves_product_text_none(tmp_path: Path) -> None:
    assert load_instance(write_instance(tmp_path)).spec.product_text is None


def test_missing_train_csv_is_tolerated(tmp_path: Path) -> None:
    instance = write_instance(tmp_path, with_train=False)
    assert load_instance(instance).spec.train_demand == ()


def test_inf_lead_time_is_parsed_as_a_lost_shipment(tmp_path: Path) -> None:
    instance = write_instance(tmp_path, lead_times=(1.0, math.inf, 1.0, 1.0))
    loaded = load_instance(instance)
    assert math.isinf(loaded.supply.lead_times[1])
    assert loaded.supply.n_lost == 1


def test_promised_lead_time_can_be_supplied_when_the_path_says_nothing(tmp_path: Path) -> None:
    instance = tmp_path / "loose" / "inst"
    instance.mkdir(parents=True)
    (instance / "test.csv").write_text(
        f"exact_dates_{ITEM},demand_{ITEM},lead_time_{ITEM},profit_{ITEM},holding_cost_{ITEM}\n"
        "2019/1/1,10.0,0.0,4.0,1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cannot derive promised lead time"):
        load_instance(instance)
    assert load_instance(instance, promised_lead_time=2).spec.promised_lead_time == 2


def test_promised_lead_time_mapping_covers_the_three_labels(tmp_path: Path) -> None:
    for label, expected in (("lead_time_0", 0), ("lead_time_4", 4), ("lead_time_stochastic", 2)):
        assert promised_lead_time_for(tmp_path / label / "x") == expected


def test_missing_demand_column_is_refused(tmp_path: Path) -> None:
    instance = tmp_path / "lead_time_0" / "bad"
    instance.mkdir(parents=True)
    (instance / "test.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no demand_"):
        load_instance(instance)


def test_empty_test_csv_is_refused(tmp_path: Path) -> None:
    instance = tmp_path / "lead_time_0" / "empty"
    instance.mkdir(parents=True)
    (instance / "test.csv").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="is empty"):
        load_instance(instance)


# ---------------------------------------------------------------------------
# sidecar neutrality
# ---------------------------------------------------------------------------


def test_a_neutral_supply_sidecar_changes_nothing(tmp_path: Path) -> None:
    """A sidecar restating ``test.csv`` must produce an identical episode.

    Without this, the file format itself would be a confound between a shocked episode and its
    baseline twin.
    """
    plain = write_instance(tmp_path / "a")
    baseline = load_instance(plain, episode_id="e")

    with_sidecar_dir = write_instance(tmp_path / "b")
    write_supply_sidecar(with_sidecar_dir, lead_times=LEADS)
    sidecar = load_instance(with_sidecar_dir, episode_id="e")

    assert sidecar.demand == baseline.demand
    assert sidecar.supply.lead_times == baseline.supply.lead_times
    assert sidecar.profits == baseline.profits
    assert sidecar.holding_costs == baseline.holding_costs
    assert sidecar.spec == baseline.spec

    controller = ConstantController(11.0)
    left = EpisodeRunner(instance=baseline).run(controller)
    right = EpisodeRunner(instance=sidecar).run(controller)
    assert left.result.records == right.result.records
    assert left.result.total_reward == right.result.total_reward


def test_a_sidecar_lead_time_column_overrides_test_csv(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    write_supply_sidecar(instance, lead_times=(0.0, 0.0, math.inf, 2.0))
    loaded = load_instance(instance)
    assert loaded.supply.lead_times == (0.0, 0.0, math.inf, 2.0)


def test_a_sidecar_may_declare_pause_only_and_keep_test_csv_lead_times(tmp_path: Path) -> None:
    """Transit pause is the one family that ``test.csv`` cannot express (env contract §7)."""
    instance = write_instance(tmp_path)
    write_supply_sidecar(instance, pause=(False, True, True, False))
    loaded = load_instance(instance)
    assert loaded.supply.lead_times == LEADS, "lead times still come from test.csv"
    assert loaded.supply.pause_active == (False, True, True, False)


def test_a_partial_sidecar_is_refused(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    (instance / "supply.csv").write_text("period,lead_time\n1,0.0\n2,0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must cover every period"):
        load_instance(instance)


def test_a_sidecar_without_a_period_column_is_refused(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    (instance / "supply.csv").write_text("lead_time\n0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="requires a `period` column"):
        load_instance(instance)


# ---------------------------------------------------------------------------
# hidden incident
# ---------------------------------------------------------------------------


def test_incident_json_loads_and_stays_out_of_observations(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    (instance / "incident.json").write_text(
        json.dumps(
            {
                "family": "transit_pause",
                "onset_period": 2,
                "magnitude": 1.5,
                "duration": 2,
                "conditional_independence": True,
                "supply_effect": {
                    "kind": "transit_pause",
                    "start_period": 2,
                    "length": 2,
                    "disrupted_lead_time": None,
                },
                "baseline_twin_id": "twin-1",
                "seed": 4242,
                "held_out_combo": True,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_instance(instance, episode_id="shocked/inst01")

    incident = loaded.incident
    assert incident is not None
    assert incident.family is ShockFamily.TRANSIT_PAUSE
    assert incident.onset_period == 2
    assert incident.magnitude == 1.5
    assert incident.duration == 2
    assert incident.conditional_independence is True
    assert incident.supply_effect is not None
    assert incident.supply_effect.kind is SupplyEffectKind.TRANSIT_PAUSE
    assert incident.supply_effect.length == 2
    assert incident.baseline_twin_id == "twin-1"
    assert incident.seed == 4242
    assert incident.held_out_combo is True

    # Presence of hidden truth marks provenance but must not reach the policy.
    assert loaded.spec.source == "collie-shockspec"
    assert loaded.spec.family is ShockFamily.TRANSIT_PAUSE
    assert find_hidden_state(loaded.spec) == []

    controller = ConstantController(5.0)
    runner = EpisodeRunner(instance=loaded)
    runner.run(controller)
    assert runner.incident is incident


def test_incident_without_a_supply_effect_loads(tmp_path: Path) -> None:
    instance = write_instance(tmp_path)
    (instance / "incident.json").write_text(
        json.dumps(
            {
                "family": "demand_level",
                "onset_period": 3,
                "magnitude": 2.0,
                "duration": 5,
                "conditional_independence": True,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_instance(instance)
    assert loaded.incident is not None
    assert loaded.incident.supply_effect is None
    assert loaded.incident.held_out_combo is False


# ---------------------------------------------------------------------------
# instance enumeration and stratification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profit", "expected"), [(19.0, "high"), (4.0, "med"), (1.0, "low"), (19, "high")]
)
def test_cost_ratio_label(profit: float, expected: str) -> None:
    assert cost_ratio_label(profit) == expected


def test_cost_ratio_label_refuses_an_unaudited_value() -> None:
    """Better to fail loudly than to bin by distance if the benchmark pin moves."""
    with pytest.raises(ValueError, match="not one of the audited values"):
        cost_ratio_label(7.0)


def _key(relpath: str, profit: float = 4.0) -> InstanceKey:
    return InstanceKey(
        relpath=relpath,
        trajectory=relpath.split("/")[0],
        lead_time_label=relpath.split("/")[1],
        cost_ratio_label=cost_ratio_label(profit),
        profit_per_unit=profit,
        holding_cost_per_unit=1.0,
        horizon=50,
        item_id="X",
    )


def test_stratify_groups_by_the_three_axes() -> None:
    keys = (
        _key("real_trajectory/lead_time_0/a", 19.0),
        _key("real_trajectory/lead_time_0/b", 19.0),
        _key("real_trajectory/lead_time_4/c", 1.0),
        _key("synthetic_trajectory/lead_time_stochastic/p/v/r", 4.0),
    )
    cells = stratify(keys)
    assert len(cells) == 3
    assert len(cells[("real_trajectory", "lead_time_0", "high")]) == 2


def test_stratified_sample_is_deterministic_and_spread() -> None:
    keys = tuple(_key(f"real_trajectory/lead_time_0/a{i:03d}", 19.0) for i in range(20))
    first = stratified_sample(keys, per_cell=5)
    assert first == stratified_sample(keys, per_cell=5), "selection must be reproducible"
    assert len(first) == 5
    assert len({k.relpath for k in first}) == 5
    # Even stride, not the first five.
    assert [k.relpath[-3:] for k in first] == ["000", "004", "008", "012", "016"]


def test_stratified_sample_returns_a_small_cell_whole() -> None:
    keys = tuple(_key(f"real_trajectory/lead_time_0/a{i}", 19.0) for i in range(3))
    assert len(stratified_sample(keys, per_cell=10)) == 3


def test_stratified_sample_rejects_a_nonpositive_size() -> None:
    with pytest.raises(ValueError, match="per_cell must be"):
        stratified_sample((), per_cell=0)


def test_lead_time_label_must_be_present() -> None:
    assert _lead_time_label("real_trajectory/lead_time_stochastic/x") == "lead_time_stochastic"
    with pytest.raises(ValueError, match="no lead-time label"):
        _lead_time_label("real_trajectory/unlabelled/x")


# ---------------------------------------------------------------------------
# header parsing: the two ways an instance CSV can be malformed
# ---------------------------------------------------------------------------


def test_header_economics_refuses_a_file_with_no_data_rows(tmp_path: Path) -> None:
    """A header-only ``test.csv`` must name itself, not surface as a bare IndexError.

    The census reads the first data row of 1,320 files; a truncated one is the realistic
    failure, and enumeration has to say which file rather than dying on ``rows[0]``.
    """
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        f"exact_dates_{ITEM},demand_{ITEM},lead_time_{ITEM},profit_{ITEM},holding_cost_{ITEM}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="has a header but no data rows"):
        _read_header_economics(csv_path)


def test_header_economics_refuses_a_file_with_no_demand_column(tmp_path: Path) -> None:
    """The item id is derived from the ``demand_*`` column, so its absence is unrecoverable."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        f"exact_dates_{ITEM},sales_{ITEM},profit_{ITEM},holding_cost_{ITEM}\n"
        "2024-01-01,10.0,4.0,1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"no demand_\* column"):
        _read_header_economics(csv_path)


@pytest.mark.needs_benchmark
def test_enumeration_matches_the_audited_census() -> None:
    keys = enumerate_instances()
    assert len(keys) == 1320
    assert sum(1 for k in keys if k.trajectory == "synthetic_trajectory") == 720
    assert sum(1 for k in keys if k.trajectory == "real_trajectory") == 600
    assert {k.holding_cost_per_unit for k in keys} == {1.0}
    assert {k.profit_per_unit for k in keys} == {1.0, 4.0, 19.0}
    # Horizons: 47 decisions for real, 50 for synthetic.
    assert {k.horizon for k in keys if k.trajectory == "real_trajectory"} == {47}
    assert {k.horizon for k in keys if k.trajectory == "synthetic_trajectory"} == {50}
    assert len(stratify(keys)) == 18
