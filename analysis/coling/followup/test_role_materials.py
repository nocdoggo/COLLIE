"""Tests use fictional generated notices and fictitious anonymous judgments."""

import hashlib
from collections import Counter
from dataclasses import replace
from datetime import timedelta

import pytest

from analysis.coling.followup import role_materials
from analysis.coling.followup.role_materials import (
    HumanRoleJudgment, RoleChecks, pilot_notices, primary_position, synthetic_role_programme as role_programme,
    role_programme as evaluation_role_programme, select_reserve, validate_human, validate_structure,
)


def judgment(seed, rater, *, valid=True, target=None, reason=None):
    target = seed.target_date if target is None else target
    return HumanRoleJudgment(seed.seed_id, rater,
                             tuple((variant.item_id, target) for variant in seed.variants),
                             RoleChecks(valid, True, True, True, True, True), valid, reason)


def decision(seed, *, valid=True):
    return validate_human(seed, [judgment(seed, "A1", valid=valid, reason=None if valid else "invalid role"),
                                 judgment(seed, "A2")], outputs_viewed=False)


def test_unregistered_evaluation_programme_cannot_be_instantiated(monkeypatch):
    monkeypatch.setattr(role_materials, "_programme", lambda *args: pytest.fail("generation must not occur"))
    for package in ("full", "reduced"):
        with pytest.raises(RuntimeError, match="evaluation.*disabled"):
            evaluation_role_programme(package)


def test_full_and_reduced_programmes_have_fixed_factor_allocations():
    full = role_programme("full")
    reduced = role_programme("reduced")
    assert full.purpose == reduced.purpose == "synthetic"
    assert (len(full.assigned), len(full.reserve)) == (80, 16)
    assert (len(reduced.assigned), len(reduced.reserve)) == (50, 16)
    cells = Counter((seed.wording_family, seed.competing_order) for seed in full.assigned)
    assert len(cells) == 8 and set(cells.values()) == {10}
    reduced_cells = Counter((seed.wording_family, seed.competing_order) for seed in reduced.assigned)
    assert len(reduced_cells) == 8 and set(reduced_cells.values()) == {6, 7}
    assert len({seed.seed_id for seed in (*full.assigned, *full.reserve)}) == 96
    assert full.manifest_sha256 == role_programme("full").manifest_sha256
    assert full.manifest_sha256 != reduced.manifest_sha256


def test_every_pair_shares_dates_and_has_one_primary_orientation():
    for seed in role_programme("full").assigned:
        validate_structure(seed)
        assert len(seed.variants) == 4
        assert {variant.position for variant in seed.variants if variant.primary} == {primary_position(seed.seed_id)}
        assert sum(variant.primary for variant in seed.variants) == 2
        for position in ("first", "last"):
            pair = [v for v in seed.variants if v.position == position]
            competitor = next(v for v in pair if v.arm == "competitor")
            neutral = next(v for v in pair if v.arm == "neutral")
            assert competitor.notice_text.replace("Next review", "Data filing") == neutral.notice_text
            assert len(competitor.notice_text) == len(neutral.notice_text)
            assert seed.competing_date.isoformat() in competitor.notice_text
            assert seed.competing_date.isoformat() in neutral.notice_text
            assert set(competitor.model_input()) == {"update_date", "notice_text"}
            assert "target_date" not in competitor.model_input()


def test_primary_position_is_most_significant_bit_of_specified_sha256():
    for seed_id in ("R001", "R002", "RR013", "synthetic-seed"):
        first_bit = hashlib.sha256(f"20261011|role-primary-position|{seed_id}".encode()).digest()[0] >> 7
        assert primary_position(seed_id) == ("first" if first_bit == 0 else "last")


def test_practice_notices_are_twelve_invented_and_separate():
    pilot = pilot_notices()
    programme = role_programme("full")
    assert len(pilot) == 12 and len({item.item_id for item in pilot}) == 12
    assert all(item.item_id.startswith("P") and "Practice notice:" in item.notice_text for item in pilot)
    evaluation_texts = {v.notice_text for seed in (*programme.assigned, *programme.reserve)
                        for v in seed.variants}
    assert not evaluation_texts.intersection(item.notice_text for item in pilot)
    assert all(set(item.model_input()) == {"update_date", "notice_text"} for item in pilot)


def test_structure_refuses_defective_dates_variants_and_primary_bits():
    seed = role_programme("full").assigned[0]
    with pytest.raises(ValueError):
        validate_structure(replace(seed, competing_date=seed.target_date))
    with pytest.raises(ValueError):
        validate_structure(replace(seed, publication_date=seed.update_date + timedelta(days=1)))
    with pytest.raises(ValueError):
        validate_structure(replace(seed, competing_order="later" if seed.competing_order == "earlier" else "earlier"))
    with pytest.raises(ValueError):
        validate_structure(replace(seed, variants=(seed.variants[0],) * 4))
    bad_primary = replace(seed.variants[0], primary=not seed.variants[0].primary)
    with pytest.raises(ValueError):
        validate_structure(replace(seed, variants=(bad_primary, *seed.variants[1:])))
    bad_text = replace(seed.variants[0], notice_text=seed.variants[0].notice_text.replace("superseded", "current"))
    with pytest.raises(ValueError):
        validate_structure(replace(seed, variants=(bad_text, *seed.variants[1:])))


def test_two_anonymous_first_passes_are_required_before_unblinding():
    seed = role_programme("reduced").assigned[0]
    one, two = judgment(seed, "A1"), judgment(seed, "A2")
    accepted = validate_human(seed, [one, two], outputs_viewed=False)
    assert accepted.valid and accepted.rater_codes == ("A1", "A2")
    with pytest.raises(ValueError, match="at least two"):
        validate_human(seed, [one], outputs_viewed=False)
    with pytest.raises(ValueError, match="distinct"):
        validate_human(seed, [one, one], outputs_viewed=False)
    with pytest.raises(ValueError, match="exposure"):
        validate_human(seed, [one, two], outputs_viewed=True)
    with pytest.raises(ValueError, match="all four"):
        validate_human(seed, [one, replace(two, targets=two.targets[:-1])], outputs_viewed=False)
    with pytest.raises(ValueError, match="anonymous"):
        judgment(seed, "Example Person")


def test_failed_human_validation_is_retained_without_replacement_by_default():
    seed = role_programme("reduced").assigned[0]
    rejected = validate_human(seed, [judgment(seed, "A1", valid=False, reason="two targets"),
                                     judgment(seed, "A2")], outputs_viewed=False)
    assert not rejected.valid and rejected.seed_id == seed.seed_id
    assert rejected.reasons == ("A1:two targets",)
    disagreement = validate_human(seed, [judgment(seed, "A1", target=seed.competing_date),
                                         judgment(seed, "A2")], outputs_viewed=False)
    assert not disagreement.valid and "A1:target_unconfirmed" in disagreement.reasons
    with pytest.raises(ValueError, match="six checks"):
        replace(judgment(seed, "A1"), checks=RoleChecks(True, None, True, True, True, True))


def test_reserve_requires_matched_factor_and_pre_unblinding_decisions():
    programme = role_programme("reduced")
    original = programme.assigned[0]
    matched = next(seed for seed in programme.reserve if
                   (seed.wording_family, seed.competing_order) ==
                   (original.wording_family, original.competing_order))
    different = next(seed for seed in programme.reserve if seed.wording_family != original.wording_family)
    rejected, accepted = decision(original, valid=False), decision(matched)
    assert select_reserve(programme, original, matched, rejected_validation=rejected,
                          replacement_validation=accepted, output_viewed=False,
                          used_seed_ids=[]) == matched
    with pytest.raises(ValueError, match="post-unblinding"):
        select_reserve(programme, original, matched, rejected_validation=rejected,
                       replacement_validation=accepted, output_viewed=True, used_seed_ids=[])
    with pytest.raises(ValueError, match="already been used"):
        select_reserve(programme, original, matched, rejected_validation=rejected,
                       replacement_validation=accepted, output_viewed=False, used_seed_ids=[matched.seed_id])
    with pytest.raises(ValueError, match="preserve"):
        select_reserve(programme, original, different, rejected_validation=rejected,
                       replacement_validation=decision(different), output_viewed=False, used_seed_ids=[])
    with pytest.raises(ValueError, match="rejection"):
        select_reserve(programme, original, matched, rejected_validation=decision(original),
                       replacement_validation=accepted, output_viewed=False, used_seed_ids=[])
    with pytest.raises(ValueError, match="reserve needs"):
        select_reserve(programme, original, matched, rejected_validation=rejected,
                       replacement_validation=decision(matched, valid=False), output_viewed=False, used_seed_ids=[])
