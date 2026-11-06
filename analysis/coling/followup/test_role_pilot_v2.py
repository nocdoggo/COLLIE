"""Invented-only checks for a separate three-seed role-pilot candidate."""

import base64
import copy
import hashlib
import json
import pickle
import unicodedata
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from analysis.coling.followup import role_generator_v2 as privategen
from analysis.coling.followup import role_materials as original
from analysis.coling.followup import role_pilot_v2 as pilot


KEY_A = bytes(range(32))
KEY_B = bytes(range(32, 64))


def material(key=KEY_A):
    return privategen.PrivateMaterial(material=key, expected_commitment_sha256=privategen.material_commitment_sha256(key),
                                      material_tag=privategen.INVENTED_MATERIAL_TAG)


def programme(key=KEY_A):
    return pilot.synthetic_pilot_programme(material=material(key), scope="synthetic")


def views(value):
    return value.visible(expected_manifest_commitment=value.manifest_commitment, no_feedback_seen=True)


@pytest.fixture(autouse=True)
def refuse_any_legacy_evaluation_generation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("legacy evaluation generation must not occur in a pilot test")

    monkeypatch.setattr(original, "role_programme", forbidden)
    monkeypatch.setattr(original, "_programme", forbidden)


@pytest.mark.parametrize("scope", ["real", "evaluation", "pilot", "", None, True])
def test_real_or_ambiguous_scope_is_refused_before_seed_generation(scope, monkeypatch):
    monkeypatch.setattr(pilot, "_build_seed", lambda *args: pytest.fail("scope must be checked first"))
    with pytest.raises(ValueError, match="scopes are disabled"):
        pilot.synthetic_pilot_programme(material=material(), scope=scope)


def test_three_synthetic_seeds_give_twelve_opaque_views_without_private_metadata():
    result = programme()
    shown = views(result)
    assert len(result._seeds) == len(shown) == 3
    assert len({group["group_id"] for group in shown}) == 3
    assert sum(len(group["notices"]) for group in shown) == 12
    assert len({notice["item_id"] for group in shown for notice in group["notices"]}) == 12
    assert all(group["synthetic_only"] is True and set(group) == {"synthetic_only", "group_id", "notices"}
               for group in shown)
    assert all(set(notice) == {"item_id", "update_date", "notice_text"}
               for group in shown for notice in group["notices"])
    exported = json.dumps(shown, sort_keys=True) + repr(shown) + repr(result.receipt())
    for seed in result._seeds:
        assert seed.private_seed_id not in exported and seed.private_seed_id not in repr(seed)
    for secret in (KEY_A.hex(), base64.b64encode(KEY_A).decode(), repr(KEY_A)):
        assert secret not in exported and secret not in repr(result)
    assert not any(name in result.receipt() for name in ("target", "seed_id", "arm", "position", "primary"))
    with pytest.raises(TypeError, match="copied or serialized"):
        asdict(result)
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="copied or serialized"):
            operation(result.material)


def test_each_seed_has_fixed_chronology_2x2_and_one_primary_pair():
    result = programme()
    assert [seed.competing_order for seed in result._seeds] == ["earlier", "later", "earlier"]
    for seed in result._seeds:
        pilot._validate_seed(seed)
        assert seed.publication < seed.old_issue < seed.old_target < seed.update < seed.target
        assert seed.competing > seed.update and seed.competing != seed.target
        assert {(item.arm, item.position) for item in seed.variants} == {
            (arm, position) for arm in ("competitor", "neutral") for position in ("first", "last")}
        assert sum(item.primary for item in seed.variants) == 2
        assert {item.position for item in seed.variants if item.primary} == {original.primary_position(seed.private_seed_id)}
        for position in ("first", "last"):
            first = next(item for item in seed.variants if item.arm == "competitor" and item.position == position)
            second = next(item for item in seed.variants if item.arm == "neutral" and item.position == position)
            assert first.notice_text.replace("Next review", "Data filing") == second.notice_text
            assert len(first.notice_text) == len(second.notice_text)


def test_pilot_families_and_namespaces_are_separate_from_synthetic_test_lineage():
    result = programme()
    assert set(pilot.PILOT_FAMILIES).isdisjoint(original.FAMILIES)
    assert pilot.PILOT_NAMESPACE != privategen.TEST_NAMESPACE
    synthetic = privategen.synthetic_role_programme(
        "reduced", material=result.material, scope="synthetic", namespace=privategen.TEST_NAMESPACE,
        expected_lineage_sha256=privategen.wording_lineage_sha256(),
    )
    pilot_ids = {seed.private_seed_id for seed in result._seeds}
    test_ids = {seed._source.seed_id for seed in (*synthetic.assigned, *synthetic.reserve)}
    assert pilot_ids.isdisjoint(test_ids)
    pilot_groups = {group["group_id"] for group in views(result)}
    test_groups = {privategen._group_alias(seed) for seed in (*synthetic.assigned, *synthetic.reserve)}
    assert pilot_groups.isdisjoint(test_groups)
    pilot_variants = {notice["item_id"] for group in views(result) for notice in group["notices"]}
    test_variants = {privategen._variant_alias(seed, variant) for seed in (*synthetic.assigned, *synthetic.reserve)
                     for variant in seed._source.variants}
    assert pilot_variants.isdisjoint(test_variants)
    assert result.receipt()["lineage_sha256"] != synthetic.wording_lineage_sha256
    # This does not prove semantic or near-duplicate separation.


def test_determinism_and_secret_domain_separation():
    one, same, other = programme(), programme(), programme(KEY_B)
    assert one.receipt() == same.receipt() and views(one) == views(same)
    assert one.manifest_commitment != other.manifest_commitment
    assert {seed.private_seed_id for seed in one._seeds}.isdisjoint(seed.private_seed_id for seed in other._seeds)
    assert {group["group_id"] for group in views(one)}.isdisjoint(group["group_id"] for group in views(other))


def test_one_hundred_invented_keys_preserve_pilot_structure_and_opaque_uniqueness():
    groups, variants, seed_ids = set(), set(), set()
    for index in range(100):
        key = hashlib.sha256(f"invented-pilot-key-{index}".encode()).digest()
        result = programme(key)
        shown = views(result)
        assert len(shown) == 3 and sum(len(group["notices"]) for group in shown) == 12
        for seed in result._seeds:
            pilot._validate_seed(seed)
            assert seed.private_seed_id not in seed_ids
            seed_ids.add(seed.private_seed_id)
        for group in shown:
            assert group["group_id"] not in groups
            groups.add(group["group_id"])
            for notice in group["notices"]:
                assert notice["item_id"] not in variants
                variants.add(notice["item_id"])
    assert (len(seed_ids), len(groups), len(variants)) == (300, 300, 1200)


def test_delivery_requires_matching_commitment_and_explicit_no_feedback_claim():
    result = programme()
    for invalid in (False, None, 1, "yes"):
        with pytest.raises(ValueError, match="no-feedback"):
            result.visible(expected_manifest_commitment=result.manifest_commitment, no_feedback_seen=invalid)
    with pytest.raises(ValueError, match="commitment differs"):
        result.visible(expected_manifest_commitment="0" * 64, no_feedback_seen=True)
    with pytest.raises(ValueError, match="commitment differs"):
        result.visible(expected_manifest_commitment="é" * 64, no_feedback_seen=True)
    detached = views(result)
    detached[0]["notices"][0]["notice_text"] = "invented mutation"
    assert views(result)[0]["notices"][0]["notice_text"] != "invented mutation"


def test_tampered_seed_variant_or_manifest_is_not_delivered():
    result = programme()
    with pytest.raises(ValueError, match="commitment differs"):
        replace(result, manifest_commitment="0" * 64)
    seed = result._seeds[0]
    bad_seed = replace(seed, old_issue=seed.update + timedelta(days=1))
    with pytest.raises(ValueError, match="chronology"):
        replace(result, _seeds=(bad_seed, *result._seeds[1:]))
    variant = replace(seed.variants[0], primary=not seed.variants[0].primary)
    with pytest.raises(ValueError, match="variant differs"):
        replace(result, _seeds=(replace(seed, variants=(variant, *seed.variants[1:])), *result._seeds[1:]))


@pytest.mark.parametrize("change", [{"ordinal": True}, {"family": False},
                                    {"primary_position": "invalid"}, {"private_seed_id": "x" * 64}])
def test_typed_seed_factors_cannot_be_spoofed_by_equal_or_malformed_values(change):
    result = programme()
    seed = replace(result._seeds[0], **change)
    with pytest.raises(ValueError, match="seed identity or factors"):
        replace(result, _seeds=(seed, *result._seeds[1:]))


def test_alias_collision_and_private_material_in_a_view_fail_preflight(monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setattr(pilot, "_variant_alias", lambda *args: "V" + "0" * 64)
        with pytest.raises(ValueError, match="alias.*differs|alias collision"):
            programme()
    original_render = pilot._render

    def leaking(seed, arm, position):
        return original_render(seed, arm, position) + " " + KEY_A.hex()

    monkeypatch.setattr(pilot, "_render", leaking)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        programme()


def test_unique_but_unbound_variant_alias_is_not_exported(monkeypatch):
    def forged(material, seed, variant):
        digest = hashlib.sha256((seed.private_seed_id + variant.arm + variant.position).encode()).hexdigest()
        return "V" + digest

    monkeypatch.setattr(pilot, "_variant_alias", forged)
    with pytest.raises(ValueError, match="variant alias differs"):
        programme()


def test_predictable_key_hidden_only_across_python_repr_is_refused():
    key = b"{'synthetic_only': True, 'group_"
    assert len(key) == 32 and len(set(key)) >= 16
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        programme(key)


def test_normalized_private_key_cannot_enter_a_synthetic_view(monkeypatch):
    key = ("é" + "abcdefghijklmnopqrstuvwx123456").encode("utf-8")
    assert len(key) == 32 and len(set(key)) >= 16
    decomposed = unicodedata.normalize("NFD", key.decode("utf-8"))
    original_render = pilot._render

    def leaking(seed, arm, position):
        return original_render(seed, arm, position) + " " + decomposed

    monkeypatch.setattr(pilot, "_render", leaking)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        programme(key)
