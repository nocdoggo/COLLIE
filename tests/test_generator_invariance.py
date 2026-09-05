"""Task 6.3 — the generated instance directory as seen by the frozen loader.

The load-bearing claims: same seed yields byte-identical directories; every directory
round-trips through ``load_instance``; a sidecar that restates ``test.csv`` changes nothing; and
hidden truth is unreachable from anything a policy could see. These are the properties the
paired-comparison argument stands on, so they are tested as properties, not examples.
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collie.contracts import ShockFamily, find_hidden_state
from collie.data.families import generate_episode
from collie.data.families.base import FamilyParams, GeneratedEpisode
from collie.data.writer import DEFAULT_ITEM_ID, TWIN_SUFFIX, write_pair
from collie.sim.loader import load_instance
from collie.sim.runner import EpisodeRunner
from tests.strategies import seeds, shock_horizons
from tests.test_episode_runner import ConstantController

IMPLEMENTED = (1, 2, 3, 4, 5)  # family 6 lands in wave 4


def _promised_lead_time(ep: GeneratedEpisode) -> int:
    """The promised lead time our harness registers: the twin's constant lead time."""
    twin = set(ep.twin_lead_times)
    assert len(twin) == 1
    return int(twin.pop())


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@given(seed=seeds, horizon=shock_horizons, family=st.sampled_from(IMPLEMENTED))
@settings(max_examples=100, deadline=None)
def test_round_trips_through_loader(seed: int, horizon: int, family: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ep = generate_episode(seed=seed, horizon=horizon, params=FamilyParams(family))
        instance = write_pair(tmp_path, ep, relpath="dev/f/s")

        loaded = load_instance(
            instance, episode_id="dev/f/s", promised_lead_time=_promised_lead_time(ep)
        )
        assert loaded.spec.horizon == horizon
        assert loaded.demand == ep.demand
        assert loaded.supply.lead_times == ep.lead_times
        assert loaded.supply.pause_active == ()
        assert loaded.spec.train_demand == ep.train_demand
        assert loaded.spec.item_id == DEFAULT_ITEM_ID
        assert loaded.spec.source == "collie-shockspec"
        assert loaded.spec.family is ep.incident.family

        incident = loaded.incident
        assert incident is not None
        assert incident.family == ep.incident.family
        assert incident.onset_period == ep.incident.onset_period
        # the writer stamps the twin relpath onto the incident
        assert incident.baseline_twin_id == f"dev/f/s{TWIN_SUFFIX}"

        twin = load_instance(
            tmp_path / f"dev/f/s{TWIN_SUFFIX}",
            episode_id="twin",
            promised_lead_time=_promised_lead_time(ep),
        )
        assert twin.demand == ep.twin_demand
        assert twin.supply.lead_times == ep.twin_lead_times
        assert twin.incident is None, "the twin is an ordinary unshocked instance"
        assert twin.spec.source == "official"


@given(seed=seeds, family=st.sampled_from(IMPLEMENTED))
@settings(max_examples=50, deadline=None)
def test_bitwise_determinism(seed: int, family: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ep = generate_episode(seed=seed, horizon=50, params=FamilyParams(family))
        write_pair(tmp_path / "a", ep, relpath="dev/f/s")
        write_pair(
            tmp_path / "b",
            generate_episode(seed=seed, horizon=50, params=FamilyParams(family)),
            relpath="dev/f/s",
        )
        assert _tree_bytes(tmp_path / "a") == _tree_bytes(tmp_path / "b"), (
            "same seed must produce byte-identical directories"
        )


@given(seed=seeds, family=st.sampled_from(IMPLEMENTED))
@settings(max_examples=50, deadline=None)
def test_neutral_sidecar_changes_nothing(seed: int, family: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ep = generate_episode(seed=seed, horizon=50, params=FamilyParams(family))
        instance = write_pair(tmp_path, ep, relpath="dev/f/s")
        before = load_instance(instance, promised_lead_time=_promised_lead_time(ep))

        # A sidecar restating test.csv's lead-time column exactly.
        rows = ["period,lead_time"] + [
            f"{t},{'inf' if math.isinf(lt) else int(lt)}" for t, lt in enumerate(ep.lead_times, 1)
        ]
        (instance / "supply.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        after = load_instance(instance, promised_lead_time=_promised_lead_time(ep))

        assert after.demand == before.demand
        assert after.supply == before.supply
        controller = ConstantController(11.0)
        left = EpisodeRunner(instance=before).run(controller)
        right = EpisodeRunner(instance=after).run(controller)
        assert left.result.records == right.result.records


@given(seed=seeds, family=st.sampled_from(IMPLEMENTED))
@settings(max_examples=50, deadline=None)
def test_hidden_truth_is_unreachable_from_observables(seed: int, family: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ep = generate_episode(seed=seed, horizon=50, params=FamilyParams(family))
        instance = write_pair(tmp_path, ep, relpath="dev/f/s")
        loaded = load_instance(instance, promised_lead_time=_promised_lead_time(ep))
        assert find_hidden_state(loaded.spec) == []
        # The runner walks every observation with strict_isolation on; a leak would raise.
        outcome = EpisodeRunner(instance=loaded).run(ConstantController(9.0))
        for obs in outcome.observations:
            assert find_hidden_state(obs) == []


@pytest.mark.parametrize("family", IMPLEMENTED)
def test_conditional_independence_flag(tmp_path: Path, family: int) -> None:
    ep = generate_episode(seed=77, horizon=50, params=FamilyParams(family))
    instance = write_pair(tmp_path, ep, relpath="dev/f/s")
    loaded = load_instance(instance, promised_lead_time=_promised_lead_time(ep))
    assert loaded.incident is not None
    assert loaded.incident.conditional_independence is True  # families 1-5


@pytest.mark.parametrize("family", IMPLEMENTED)
def test_test_csv_carries_no_hidden_marker(tmp_path: Path, family: int) -> None:
    ep = generate_episode(seed=99, horizon=50, params=FamilyParams(family))
    instance = write_pair(tmp_path, ep, relpath="dev/f/s")
    text = (instance / "test.csv").read_text(encoding="utf-8")
    # Words only: an integer like the onset can legitimately appear as a demand cell, so the
    # check is about labels and markers, not numbers.
    for forbidden in (
        ep.incident.family.value,
        "incident",
        "family",
        "shock",
        "twin",
        "onset",
        "p0",  # official pattern names
        "p10",
    ):
        assert forbidden not in text
    header = text.splitlines()[0]
    assert header.split(",") == [
        f"exact_dates_{DEFAULT_ITEM_ID}",
        f"demand_{DEFAULT_ITEM_ID}",
        f"lead_time_{DEFAULT_ITEM_ID}",
        f"profit_{DEFAULT_ITEM_ID}",
        f"holding_cost_{DEFAULT_ITEM_ID}",
    ]


def test_inf_lead_time_round_trips_as_a_lost_shipment(tmp_path: Path) -> None:
    ep = generate_episode(seed=303, horizon=50, params=FamilyParams(5, onset=18, loss_length=3))
    instance = write_pair(tmp_path, ep, relpath="dev/f5/s")
    loaded = load_instance(instance, promised_lead_time=2)
    assert sum(1 for lt in loaded.supply.lead_times if math.isinf(lt)) == 3
    assert loaded.supply.n_lost == 3


def test_a_partial_sidecar_is_refused(tmp_path: Path) -> None:
    ep = generate_episode(seed=5, horizon=50, params=FamilyParams(1))
    instance = write_pair(tmp_path, ep, relpath="dev/f1/s")
    (instance / "supply.csv").write_text("period,pause_active\n1,true\n2,false\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must cover every period"):
        load_instance(instance, promised_lead_time=2)


def test_a_sidecar_without_period_is_refused(tmp_path: Path) -> None:
    ep = generate_episode(seed=5, horizon=50, params=FamilyParams(1))
    instance = write_pair(tmp_path, ep, relpath="dev/f1/s")
    (instance / "supply.csv").write_text("pause_active\n" + "false\n" * 50, encoding="utf-8")
    with pytest.raises(ValueError, match="requires a `period` column"):
        load_instance(instance, promised_lead_time=2)


def test_an_unknown_family_in_incident_json_is_refused(tmp_path: Path) -> None:
    ep = generate_episode(seed=5, horizon=50, params=FamilyParams(1))
    instance = write_pair(tmp_path, ep, relpath="dev/f1/s")
    payload = json.loads((instance / "incident.json").read_text(encoding="utf-8"))
    payload["family"] = "spontaneous_combustion"
    (instance / "incident.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="spontaneous_combustion"):
        load_instance(instance, promised_lead_time=2)


def test_a_non_integer_cell_is_refused_by_the_writer(tmp_path: Path) -> None:
    ep = generate_episode(seed=5, horizon=50, params=FamilyParams(1))
    broken = GeneratedEpisode(
        demand=(100.5,) * 50,
        lead_times=ep.lead_times,
        pause_active=ep.pause_active,
        incident=ep.incident,
        twin_demand=(100.5,) * 50,
        twin_lead_times=ep.twin_lead_times,
        train_demand=ep.train_demand,
    )
    with pytest.raises(ValueError, match="non-integer cell"):
        write_pair(tmp_path, broken, relpath="dev/f1/s")


def test_shock_family_names_cover_the_writer(tmp_path: Path) -> None:
    # Guard the enum-value rendering in incident.json against a silent rename.
    ep = generate_episode(seed=5, horizon=50, params=FamilyParams(3))
    instance = write_pair(tmp_path, ep, relpath="dev/f3/s")
    payload = json.loads((instance / "incident.json").read_text(encoding="utf-8"))
    assert payload["family"] == ShockFamily.TEMPORARY_PULSE.value
