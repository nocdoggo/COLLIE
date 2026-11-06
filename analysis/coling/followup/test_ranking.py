"""Synthetic enumeration checks for aggregate feasible rankings."""

import hashlib
from datetime import date
from itertools import product

import pytest

from analysis.coling.followup.measurement_sensitivity import ProbabilityPair
from analysis.coling.followup.ranking import (
    RankingRow, RankingScope, SharedEvent, feasible_ranking, scoped_feasible_ranking,
)


def row(item, comparator, tested, *, allowed=((0, 0), (0, 1), (1, 1)), group=None,
        early=date(2028, 3, 1), late=date(2028, 6, 1)):
    return RankingRow(item, early, late, ProbabilityPair(*comparator), ProbabilityPair(*tested), allowed, group)


def event(group="latent", **changes):
    values = dict(latent_event_id=group, construction="same_latent_recovery_event",
                  construction_sha256="a" * 64, earliest=None, latest=None)
    values.update(changes)
    return SharedEvent(**values)


def loss(p, label):
    return sum((x - y) ** 2 for x, y in zip((p.earlier, p.later), label, strict=True)) / 2


def test_uniform_scenarios_are_not_general_ranking_bounds():
    rows = [row("A", (.1, .3), (.7, .9)), row("B", (.7, .9), (.1, .3))]
    result = feasible_ranking(rows)
    values = [sum(loss(item.comparator, y) - loss(item.tested, y) for item, y in zip(rows, labels, strict=True)) / 2
              for labels in product(((0, 0), (0, 1), (1, 1)), repeat=2)]
    assert result.rowwise_lower == pytest.approx(min(values))
    assert result.rowwise_upper == pytest.approx(max(values))
    assert (result.rowwise_lower, result.rowwise_upper) == pytest.approx((-.6, .6))
    assert result.constrained_lower == result.rowwise_lower and result.constrained_upper == result.rowwise_upper


def test_shared_latent_event_can_remove_rowwise_uncertainty():
    rows = [row("A", (.1, .3), (.7, .9), group="latent"),
            row("B", (.7, .9), (.1, .3), group="latent")]
    result = feasible_ranking(rows, [event()])
    assert (result.rowwise_lower, result.rowwise_upper) == pytest.approx((-.6, .6))
    assert (result.constrained_lower, result.constrained_upper) == pytest.approx((0., 0.))
    assert result.shared_event_groups == 1


def test_different_horizons_and_event_window_are_constrained_jointly():
    a = row("A", (.1, .2), (.6, .8), group="latent", early=date(2028, 3, 1), late=date(2028, 4, 1))
    b = row("B", (.4, .5), (.2, .9), group="latent", early=date(2028, 3, 15), late=date(2028, 5, 1))
    shared = event(earliest=date(2028, 3, 10), latest=date(2028, 3, 20))
    result = feasible_ranking([a, b], [shared])
    direct = []
    for day in (date(2028, 3, 10), date(2028, 3, 15), date(2028, 3, 16), date(2028, 3, 20)):
        labels = [(int(day <= item.earlier_horizon), int(day <= item.later_horizon)) for item in (a, b)]
        direct.append(sum(loss(item.comparator, label) - loss(item.tested, label)
                          for item, label in zip((a, b), labels, strict=True)) / 2)
    assert result.constrained_lower == pytest.approx(min(direct))
    assert result.constrained_upper == pytest.approx(max(direct))
    assert result.rowwise_lower <= result.constrained_lower
    assert result.constrained_upper <= result.rowwise_upper


def test_fully_determined_states_have_a_single_point():
    rows = [row("A", (.1, .3), (.4, .5), allowed=((0, 1),)),
            row("B", (.4, .8), (.2, .9), allowed=((1, 1),))]
    result = feasible_ranking(rows)
    assert result.rowwise_lower == result.rowwise_upper
    assert result.constrained_lower == result.constrained_upper == result.rowwise_lower


def test_missing_or_invalid_shared_event_evidence_is_refused():
    grouped = row("A", (.1, .3), (.4, .5), group="latent")
    with pytest.raises(ValueError, match="explicit event"):
        feasible_ranking([grouped])
    with pytest.raises(ValueError, match="broad episode"):
        event(construction="same_episode")
    with pytest.raises(ValueError, match="unique"):
        feasible_ranking([grouped, grouped], [event()])
    with pytest.raises(TypeError, match="supplied explicitly"):
        row("X", (.1, .3), (.4, .5), allowed=None)
    impossible = row("B", (.2, .4), (.5, .8), group="latent", allowed=((1, 1),))
    after_horizons = event(earliest=date(2029, 1, 1))
    with pytest.raises(ValueError, match="no feasible"):
        feasible_ranking([impossible, replace_item(impossible, "C")], [after_horizons])


def replace_item(item, item_id):
    return RankingRow(item_id, item.earlier_horizon, item.later_horizon, item.comparator,
                      item.tested, item.allowed_labels, item.latent_event_id)


def test_scoped_adapter_keeps_primary_slice_and_exploratory_status():
    rows = [row("A", (.1, .3), (.4, .5)), row("B", (.3, .6), (.2, .7))]
    digest = hashlib.sha256(b"A\nB").hexdigest()
    scope = RankingScope("llama-3.3-70b", "H2", digest)
    result = scoped_feasible_ranking(scope, rows)
    assert result.scientific_status == "exploratory" and result.interval.statements == 2
    with pytest.raises(ValueError, match="fixed eligible"):
        scoped_feasible_ranking(scope, rows[:1])
    with pytest.raises(ValueError, match="three original"):
        RankingScope("another-model", "H2", digest)
    with pytest.raises(ValueError, match="three original"):
        RankingScope("llama-3.3-70b", "new-hypothesis", digest)
