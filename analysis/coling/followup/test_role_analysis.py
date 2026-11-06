"""Fictional paired responses for the role-study analysis."""

import json
from dataclasses import replace
from datetime import date

import pytest

from analysis.coling.followup.parsing import parse_role, unavailable_role
from analysis.coling.followup.role_analysis import (
    PRIMARY_ROUTES, RoleAnalysisConfig, RoleAssignment, RoleObservation, analyze_role,
    holm_role_family,
)
from analysis.coling.followup.role_materials import primary_position, synthetic_role_programme as role_programme
from analysis.coling.followup.test_role_materials import decision


LLAMA = "meta-llama/llama-3.3-70b-instruct"
DEEPSEEK = "deepseek/deepseek-chat"


def config(model=LLAMA):
    route, precision = PRIMARY_ROUTES[model]
    return RoleAnalysisConfig(model, route, precision, "a" * 64, "b" * 64, "c" * 64)


def assignments(n=4):
    programme = role_programme("reduced")
    return tuple(RoleAssignment(seed, decision(seed)) for seed in programme.assigned[:n])


def observation(seed, variant, cfg, answer="correct", *, identity=True):
    targets = {"correct": seed.target_date, "competing": seed.competing_date,
               "other": date(2020, 1, 1), "null": None}
    if answer == "missing":
        parsed = unavailable_role("transport_failure")
    elif answer == "invalid":
        parsed = parse_role("{", variant.notice_text, finish_reason="stop")
    elif answer == "truncated":
        parsed = parse_role("{", variant.notice_text, finish_reason="length")
    else:
        value = targets[answer]
        text = json.dumps({"date": None if value is None else value.isoformat(),
                           "quote": "" if value is None else "not a real quote"})
        parsed = parse_role(text, variant.notice_text, finish_reason="stop")
    return RoleObservation(variant.item_id, parsed, cfg.expected_identity(variant) if identity else None,
                           None if identity else "unidentified_response")


def responses(assigned, cfg, choices=None):
    choices = choices or {}
    result = []
    for assignment in assigned:
        seed = assignment.seed
        for variant in seed.variants:
            role = "primary" if variant.position == primary_position(seed.seed_id) else "alternate"
            answer = choices.get((seed.seed_id, role, variant.arm), "correct")
            result.append(observation(seed, variant, cfg, answer))
    return result


def test_primary_pair_and_exact_mcnemar_include_all_assigned_seeds():
    assigned, cfg = assignments(8), config()
    choices = {}
    for assignment in assigned[:3]:
        choices[(assignment.seed.seed_id, "primary", "competitor")] = "competing"
    choices[(assigned[3].seed.seed_id, "primary", "neutral")] = "other"
    result = analyze_role(assigned, responses(assigned, cfg, choices), config=cfg)
    assert result.scientific_status == "development_only_not_registered"
    assert result.primary.denominator == 8 and result.primary.complete_pairs == 8
    assert result.primary.estimate == .25
    assert (result.competitor_only_errors, result.neutral_only_errors) == (3, 1)
    assert result.p_raw == .625
    assert result.p_holm is None and result.bootstrap_95 is not None
    assert result.competitor_diagnostic.competing_date_selected == 3
    assert result.neutral_diagnostic.other_date_selected == 1
    assert result.competitor_diagnostic.target_correct == 5


def test_one_primary_pair_per_seed_other_position_is_diagnostic():
    assigned, cfg = assignments(3), config()
    choices = {(assignment.seed.seed_id, "alternate", "competitor"): "competing"
               for assignment in assigned}
    result = analyze_role(assigned, responses(assigned, cfg, choices), config=cfg)
    assert result.primary.denominator == 3 and result.primary.estimate == 0
    assert result.other_position.denominator == 3 and result.other_position.estimate == 1
    assert result.p_raw == 1
    assert result.target_first.denominator == result.target_last.denominator == 3
    assert result.competitor_earlier.denominator + result.competitor_later.denominator == 3


def test_invalid_null_and_truncated_responses_are_observed_errors_not_missing():
    assigned, cfg = assignments(4), config()
    choices = {(assigned[0].seed.seed_id, "primary", "competitor"): "invalid",
               (assigned[1].seed.seed_id, "primary", "competitor"): "truncated",
               (assigned[2].seed.seed_id, "primary", "competitor"): "null"}
    result = analyze_role(assigned, responses(assigned, cfg, choices), config=cfg)
    assert result.primary.complete_pairs == 4 and result.primary.estimate == .75
    assert result.competitor_only_errors == 3 and result.neutral_only_errors == 0
    assert result.p_raw == .25
    assert result.competitor_diagnostic.invalid_or_truncated == 2
    assert result.competitor_diagnostic.null_answer == 1
    assert result.competitor_diagnostic.unavailable == 0
    # Correct dates with nonmatching quotes stay correct: quotes are diagnostic.
    assert result.neutral_diagnostic.target_correct == 4


def test_missing_primary_pairs_have_bounds_no_p_and_no_complete_case_effect():
    assigned, cfg = assignments(2), config()
    choices = {(assigned[0].seed.seed_id, "primary", "competitor"): "missing",
               (assigned[1].seed.seed_id, "primary", "competitor"): "competing",
               (assigned[1].seed.seed_id, "primary", "neutral"): "missing"}
    result = analyze_role(assigned, responses(assigned, cfg, choices), config=cfg)
    assert result.primary.denominator == 2 and result.primary.incomplete_pairs == 2
    assert result.primary.estimate is None
    assert (result.primary.completion_lower, result.primary.completion_upper) == (0, 1)
    assert result.p_raw is None and result.bootstrap_95 is None
    assert result.competitor_only_errors is None and result.neutral_only_errors is None
    assert result.competitor_diagnostic.unavailable == 1
    assert result.neutral_diagnostic.unavailable == 1


def test_missing_identity_is_not_an_observed_invalid_task_error():
    assigned, cfg = assignments(1), config()
    seed = assigned[0].seed
    primary_comp = next(v for v in seed.variants if v.primary and v.arm == "competitor")
    all_responses = responses(assigned, cfg)
    all_responses = [obs for obs in all_responses if obs.item_id != primary_comp.item_id]
    all_responses.append(observation(seed, primary_comp, cfg, "invalid", identity=False))
    result = analyze_role(assigned, all_responses, config=cfg)
    assert result.p_raw is None and result.primary.incomplete_pairs == 1
    assert result.competitor_diagnostic.unavailable == 1
    assert result.competitor_diagnostic.invalid_or_truncated == 0


def test_missing_only_the_other_orientation_does_not_change_primary():
    assigned, cfg = assignments(2), config()
    choices = {(assigned[0].seed.seed_id, "alternate", "competitor"): "missing"}
    result = analyze_role(assigned, responses(assigned, cfg, choices), config=cfg)
    assert result.primary.incomplete_pairs == 0 and result.p_raw == 1
    assert result.other_position.incomplete_pairs == 1 and result.other_position.estimate is None


def test_identity_duplicates_and_unknown_variants_refuse_analysis():
    assigned, cfg = assignments(1), config()
    original = responses(assigned, cfg)
    with pytest.raises(ValueError, match="unique"):
        analyze_role(assigned + assigned, original, config=cfg)
    with pytest.raises(ValueError, match="unique"):
        analyze_role(assigned, original + original[:1], config=cfg)
    variant = assigned[0].seed.variants[0]
    invalid_identity = replace(cfg.expected_identity(variant), precision="fp4")
    altered = [RoleObservation(variant.item_id, original[0].parsed, invalid_identity)] + original[1:]
    with pytest.raises(ValueError, match="identity"):
        analyze_role(assigned, altered, config=cfg)
    with pytest.raises(ValueError, match="primary route"):
        RoleAnalysisConfig(LLAMA, "deepinfra/fp4", "fp4", "a" * 64, "b" * 64, "c" * 64)


def test_later_defects_remain_in_primary_and_have_separate_sensitivity():
    assigned, cfg = assignments(2), config()
    defective = (replace(assigned[0], post_unblinding_defect="ambiguity discovered later"), assigned[1])
    choices = {(assigned[0].seed.seed_id, "primary", "competitor"): "competing"}
    result = analyze_role(defective, responses(defective, cfg, choices), config=cfg)
    assert result.primary.denominator == 2 and result.primary.estimate == .5
    assert result.later_defect_count == 1
    assert result.without_later_defects.denominator == 1
    assert result.without_later_defects.estimate == 0


@pytest.mark.parametrize("codes", [("M1", "M2"), ("A1", "MADJ"), ("A1", "A1"),
                                  ("A0", "A2"), ("A1", "named person"), ["A1", "A2"]])
def test_human_assignment_does_not_accept_machine_or_nonanonymous_rater_codes(codes):
    assignment = assignments(1)[0]
    forged = replace(assignment.validation, rater_codes=codes)
    with pytest.raises(ValueError, match="human pre-unblinding validation"):
        RoleAssignment(assignment.seed, forged)


@pytest.mark.parametrize("changes", [{"valid": 1}, {"valid": "yes"}, {"reasons": []}])
def test_human_assignment_requires_typed_validation_status_and_reasons(changes):
    assignment = assignments(1)[0]
    forged = replace(assignment.validation, **changes)
    with pytest.raises(ValueError, match="human pre-unblinding validation"):
        RoleAssignment(assignment.seed, forged)


def test_two_model_holm_waits_for_both_primary_p_values():
    assigned = assignments(8)
    llama, deepseek = config(), config(DEEPSEEK)
    llama_choices = {(a.seed.seed_id, "primary", "competitor"): "competing" for a in assigned[:6]}
    deepseek_choices = {(a.seed.seed_id, "primary", "competitor"): "competing" for a in assigned[:2]}
    first = analyze_role(assigned, responses(assigned, llama, llama_choices), config=llama)
    second = analyze_role(assigned, responses(assigned, deepseek, deepseek_choices), config=deepseek)
    family = holm_role_family([first, second])
    p = {item.model_id: (item.p_raw, item.p_holm) for item in family.results}
    assert family.holm_complete and p[LLAMA] == (.03125, .0625)
    assert p[DEEPSEEK] == (.5, .5)
    deepseek_choices[(assigned[0].seed.seed_id, "primary", "neutral")] = "missing"
    missing = analyze_role(assigned, responses(assigned, deepseek, deepseek_choices), config=deepseek)
    incomplete = holm_role_family([first, missing])
    assert not incomplete.holm_complete and all(item.p_holm is None for item in incomplete.results)
    assert next(item for item in incomplete.results if item.model_id == DEEPSEEK).p_raw is None
    with pytest.raises(ValueError, match="exactly"):
        holm_role_family([first])
    with pytest.raises(ValueError, match="same assigned"):
        holm_role_family([first, replace(second, assignment_sha256="d" * 64)])
    with pytest.raises(ValueError, match="p-values"):
        holm_role_family([replace(first, p_raw=float("nan")), second])


def test_holm_refuses_different_validation_or_later_defect_records_for_the_same_seeds():
    assigned = assignments(2)
    llama, deepseek = config(), config(DEEPSEEK)
    first = analyze_role(assigned, responses(assigned, llama), config=llama)
    changed_validation = (replace(assigned[0], validation=replace(
        assigned[0].validation, rater_codes=("A1", "A3"))), assigned[1])
    second = analyze_role(changed_validation, responses(changed_validation, deepseek), config=deepseek)
    assert first.assignment_sha256 == second.assignment_sha256
    assert first.validation_sha256 != second.validation_sha256
    with pytest.raises(ValueError, match="same material validation"):
        holm_role_family([first, second])

    defective = (replace(assigned[0], post_unblinding_defect="invented later defect"), assigned[1])
    second = analyze_role(defective, responses(defective, deepseek), config=deepseek)
    assert first.assignment_sha256 == second.assignment_sha256
    assert first.validation_sha256 == second.validation_sha256
    assert first.later_defects_sha256 != second.later_defects_sha256
    with pytest.raises(ValueError, match="same later-defect record"):
        holm_role_family([first, second])
    with pytest.raises(ValueError, match="SHA256"):
        holm_role_family([replace(first, validation_sha256="invalid"), second])


def test_role_hashes_do_not_depend_on_assignment_order():
    assigned = assignments(3)
    cfg = config()
    forward = analyze_role(assigned, responses(assigned, cfg), config=cfg)
    backward = analyze_role(reversed(assigned), responses(assigned, cfg), config=cfg)
    assert (forward.assignment_sha256, forward.validation_sha256, forward.later_defects_sha256) == (
        backward.assignment_sha256, backward.validation_sha256, backward.later_defects_sha256)
