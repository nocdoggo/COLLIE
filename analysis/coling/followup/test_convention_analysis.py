"""Fictional convention judgments and paired model responses."""

import json
from dataclasses import replace
from datetime import date, timedelta

import pytest

from analysis.coling.followup import prompts
from analysis.coling.followup.convention_analysis import (
    ARM_TEMPLATES, ConventionConfig, ConventionObservation, ConventionUnit, summarize_conventions,
)
from analysis.coling.followup.parsing import parse_natural, unavailable_natural
from analysis.coling.followup.test_references import T0, first, option, specified
from analysis.coling.followup.references import adjudicate_convention


MODEL = "meta-llama/llama-3.3-70b-instruct"


def unit(item, episode):
    return ConventionUnit(item, episode, "c" * 64)


def reference(item, *, defensible=None, targets=None):
    firsts = [replace(first(rater, "unspecified", item=item), judgment_id=f"{item}-{rater}-first")
              for rater in ("A1", "A2")]
    seconds = [replace(specified(rater, item=item), judgment_id=f"{item}-{rater}-specified")
               for rater in ("A1", "A2")]
    return adjudicate_convention(
        item_id=item, reference_version="v1", first_passes=firsts, specified_passes=seconds,
        defensible_options=defensible if defensible is not None else (option(),),
        specified_options=targets if targets is not None else (option(),), adjudicator="ADJ",
        adjudicated_utc=T0 + timedelta(seconds=5), outputs_seen=False, sensitivity_seen=False,
        rationale="Resolve the fictional item",
    )


def config():
    return ConventionConfig(MODEL, "deepinfra/turbo", "fp8",
                            tuple((arm, prompts.template_sha256(template)) for arm, template in ARM_TEMPLATES.items()),
                            "b" * 64, "d" * 64)


def observation(item, episode, arm, *, end="2028-03-14", answer="valid"):
    unit_record, cfg = unit(item, episode), config()
    if answer == "unavailable":
        parsed = unavailable_natural("network")
    elif answer == "invalid":
        parsed = parse_natural("{", "fictional", finish_reason="stop")
    else:
        content = json.dumps({"statement_type": "recovery", "interval": {"start": "2028-03-01", "end": end},
                              "certainty": "estimated", "quote": "fictional"})
        parsed = parse_natural(content, "fictional", finish_reason="stop")
    return ConventionObservation(item, arm, parsed, cfg.expected_identity(unit_record, arm))


def test_paired_contrasts_keep_equal_item_weights_and_episode_clusters():
    units = [unit("C1", "episode-a"), unit("C2", "episode-a"), unit("C3", "episode-b")]
    refs = [reference(u.item_id) for u in units]
    obs = []
    for u in units:
        obs.extend([observation(u.item_id, u.episode_id, "absent", end="2028-03-15"),
                    observation(u.item_id, u.episode_id, "neutral", end="2028-03-15" if u.item_id == "C1" else "2028-03-14"),
                    observation(u.item_id, u.episode_id, "explicit")])
    summary = summarize_conventions(units, refs, obs, config=config())
    assert summary.scientific_status == "exploratory" and summary.episodes == 2
    assert summary.specified_explicit_minus_neutral.estimate == 1 / 3
    assert summary.specified_explicit_minus_absent.estimate == 1
    assert summary.specified_explicit_minus_neutral.denominator == 3
    assert summary.specified_explicit_minus_neutral.bootstrap_95 is not None
    arms = dict(summary.arms)
    assert arms["absent"].specified_agreement.known_false == 3
    assert arms["explicit"].specified_agreement.known_true == 3


def test_returned_failures_are_disagreements_while_unavailable_is_unknown():
    units = [unit("C1", "a"), unit("C2", "b")]
    refs = [reference(item.item_id) for item in units]
    obs = [observation("C1", "a", arm, answer="invalid" if arm == "neutral" else "valid")
           for arm in ARM_TEMPLATES]
    obs += [observation("C2", "b", arm, answer="unavailable" if arm == "neutral" else "valid")
            for arm in ARM_TEMPLATES]
    summary = summarize_conventions(units, refs, obs, config=config())
    neutral = dict(summary.arms)["neutral"]
    assert neutral.returned_failure == 1 and neutral.unavailable_response == 1
    assert (neutral.specified_agreement.known_true, neutral.specified_agreement.known_false,
            neutral.specified_agreement.unknown) == (0, 1, 1)
    contrast = summary.specified_explicit_minus_neutral
    assert contrast.estimate is None and contrast.complete_pairs == 1
    assert (contrast.completion_lower, contrast.completion_upper) == (.5, 1)
    assert contrast.bootstrap_95 is None and contrast.interval_reason == "missing_paired_components"


def test_ambiguous_and_unmapped_references_remain_in_denominator():
    units = [unit("C1", "a"), unit("C2", "b")]
    ambiguous = option(start=None, certainty="conditional", model_certainty=None)
    refs = [reference("C1", defensible=(option(), ambiguous),
                      targets=(option(), option(end=date(2028, 3, 15)))), reference("C2")]
    obs = [observation(u.item_id, u.episode_id, arm) for u in units for arm in ARM_TEMPLATES]
    result = summarize_conventions(units, refs, obs, config=config())
    explicit = dict(result.arms)["explicit"]
    assert explicit.specified_agreement.denominator == 2
    assert explicit.specified_agreement.unknown == 1
    # Membership is known true when an answer matches a mapped defensible reading,
    # even though another preserved alternative is not fully mapped.
    assert explicit.defensible_membership.known_true == 2


def test_nonmatching_unmapped_reference_has_unknown_membership():
    units = [unit("C1", "a")]
    ambiguous = option(start=None, certainty="conditional", model_certainty=None)
    ref = reference("C1", defensible=(option(), ambiguous))
    obs = [observation("C1", "a", arm, end="2028-03-15") for arm in ARM_TEMPLATES]
    result = summarize_conventions(units, [ref], obs, config=config())
    assert dict(result.arms)["explicit"].defensible_membership.unknown == 1
    assert result.defensible_explicit_minus_neutral.estimate is None


def test_identity_episode_and_judgment_duplicates_refuse_analysis():
    units = [unit("C1", "episode"), unit("C2", "episode"), unit("C3", "episode")]
    with pytest.raises(ValueError, match="at most two"):
        summarize_conventions(units, [], [], config=config())
    one = [unit("C1", "a")]
    obs = observation("C1", "a", "absent")
    with pytest.raises(ValueError, match="unique"):
        summarize_conventions(one, [reference("C1")], [obs, obs], config=config())
    wrong = replace(obs, identity=replace(obs.identity, template_id="literal-v1"))
    with pytest.raises(ValueError, match="identity"):
        summarize_conventions(one, [reference("C1")], [wrong], config=config())
    same_passes = replace(reference("C2"), first_pass_ids=reference("C1").first_pass_ids)
    with pytest.raises(ValueError, match="judgment IDs"):
        summarize_conventions([unit("C1", "a"), unit("C2", "b")],
                              [reference("C1"), same_passes], [], config=config())
