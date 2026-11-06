"""Invented, explicitly tagged fixtures only; these public keys have no entropy.

These tests do not establish secrecy, registration, semantic blinding, pilot
lineage separation, or eligibility for real collection/evaluation.
"""

import base64
import copy
import hashlib
import hmac
import inspect
import json
import pickle
import re
from collections import Counter
from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest

from analysis.coling.followup import role_generator_v2 as candidate
from analysis.coling.followup import role_materials as original


# Known, reproducible fixtures, NOT random or suitable for any real material.
INVENTED_KEY_A = hashlib.sha256(b"INVENTED PUBLIC SYNTHETIC TEST KEY A; NEVER USE FOR REAL").digest()
INVENTED_KEY_B = hashlib.sha256(b"INVENTED PUBLIC SYNTHETIC TEST KEY B; NEVER USE FOR REAL").digest()
# Intentionally public synthetic bytes containing quotes, backslash, and controls.
INVENTED_ESCAPED_KEY = bytes([34, 92, 10, 13, 9, 0, *range(65, 91)])
TAG = candidate.INVENTED_MATERIAL_TAG
TEST = candidate.TEST_NAMESPACE
PILOT = candidate.PILOT_NAMESPACE


def private_material(key=INVENTED_KEY_A):
    return candidate.PrivateMaterial(
        material=key, expected_commitment_sha256=candidate.material_commitment_sha256(key), material_tag=TAG,
    )


def isolated_material(label):
    key = hashlib.sha256(("INVENTED PUBLIC TEST MATERIAL ONLY: " + label).encode("utf-8")).digest()
    return private_material(key)


def programme(package, material, *, scope="synthetic", namespace=TEST, lineage=None):
    return candidate.synthetic_role_programme(
        package, material=material, scope=scope, namespace=namespace,
        expected_lineage_sha256=candidate.wording_lineage_sha256() if lineage is None else lineage,
    )


def synthetic_lock(value):
    # Synthetic test-only assertion; this is not evidence of external timing.
    return candidate.lock_synthetic_programme(value, expected_manifest_commitment_sha256=value.manifest_commitment_sha256,
                                             feedback_seen=False)


def reference_mac(key, domain, *context):
    fields = ("collie-role-generator-v2", candidate.GENERATOR_VERSION, TAG, "synthetic", domain, *context)
    encoded = [field.encode("utf-8") for field in fields]
    message = b"".join(len(field).to_bytes(4, "big") + field for field in encoded)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


@pytest.fixture(scope="module")
def material_a():
    return private_material(INVENTED_KEY_A)


@pytest.fixture(scope="module")
def material_b():
    return private_material(INVENTED_KEY_B)


@pytest.fixture(scope="module")
def full(material_a):
    return programme("full", material_a)


@pytest.fixture(scope="module")
def reduced(material_a):
    return programme("reduced", material_a)


@pytest.fixture(scope="module")
def full_lock(full):
    return synthetic_lock(full)


@pytest.fixture(scope="module")
def reduced_lock(reduced):
    return synthetic_lock(reduced)


@pytest.fixture(scope="module")
def escaped_reduced():
    return programme("reduced", private_material(INVENTED_ESCAPED_KEY))


@pytest.fixture(scope="module")
def escaped_reduced_lock(escaped_reduced):
    return synthetic_lock(escaped_reduced)


def test_material_commitment_is_deterministic_checked_and_domain_bound(material_a, material_b):
    key = INVENTED_KEY_A
    prefix = b"collie-role-v2-material-commitment"
    framed = len(prefix).to_bytes(4, "big") + prefix + len(key).to_bytes(4, "big") + key
    expected = hashlib.sha256(framed).hexdigest()
    assert candidate.material_commitment_sha256(key) == expected == material_a.commitment_sha256
    assert candidate.material_commitment_sha256(key) == candidate.material_commitment_sha256(key)
    assert material_a.commitment_sha256 != material_b.commitment_sha256
    assert re.fullmatch(r"[0-9a-f]{64}", expected)
    with pytest.raises(ValueError, match="does not match"):
        candidate.PrivateMaterial(material=key, expected_commitment_sha256=material_b.commitment_sha256,
                                  material_tag=TAG)
    for malformed in ("", "0" * 63, "A" * 64, None):
        with pytest.raises(ValueError, match="commitment"):
            candidate.PrivateMaterial(material=key, expected_commitment_sha256=malformed, material_tag=TAG)


@pytest.mark.parametrize("key", [b"", b"x" * 31, b"x" * 33, b"x" * 32, bytes(range(16)) * 2])
def test_wrong_length_or_obviously_weak_material_is_refused(key):
    with pytest.raises(ValueError, match="weak or invalid"):
        candidate.material_commitment_sha256(key)
    with pytest.raises(ValueError, match="weak or invalid"):
        candidate.PrivateMaterial(material=key, expected_commitment_sha256="0" * 64, material_tag=TAG)


@pytest.mark.parametrize("key", [None, "not-bytes", bytearray(range(32))])
def test_material_requires_exact_bytes(key):
    with pytest.raises(TypeError, match="bytes"):
        candidate.material_commitment_sha256(key)


@pytest.mark.parametrize("tag", [None, "", "real", "evaluation", "synthetic", "invented"])
def test_material_requires_the_explicit_invented_test_tag(tag):
    with pytest.raises(ValueError, match="invented"):
        candidate.PrivateMaterial(material=INVENTED_KEY_A,
                                  expected_commitment_sha256=candidate.material_commitment_sha256(INVENTED_KEY_A),
                                  material_tag=tag)


def test_material_is_rechecked_before_derivation():
    material = private_material()
    object.__setattr__(material, "_material", INVENTED_KEY_B)
    with pytest.raises(ValueError, match="does not match"):
        _ = material.commitment_sha256
    with pytest.raises(ValueError, match="does not match"):
        candidate._private_seed_id(material, TEST, "full", "assigned", 1)


def test_private_seed_and_aliases_match_independent_domain_separated_hmac(full, full_lock):
    seed = full.assigned[0]
    source = seed._source  # Private invented fixture, never the visible projection.
    lineage = candidate.wording_lineage_sha256()
    expected_seed = reference_mac(INVENTED_KEY_A, "private-seed", TEST, lineage, "full", "assigned",
                                  str(seed.ordinal))
    assert source.seed_id == expected_seed
    group_id = "G" + reference_mac(INVENTED_KEY_A, "group-alias", TEST, "full", "assigned", expected_seed)
    visible = full_lock.visible(seed)
    assert visible["group_id"] == group_id
    by_id = {notice["item_id"]: notice for notice in visible["notices"]}
    for variant in source.variants:
        alias = "V" + reference_mac(INVENTED_KEY_A, "variant-alias", TEST, "full", "assigned",
                                    expected_seed, variant.arm, variant.position)
        assert by_id[alias] == {"item_id": alias, "update_date": source.update_date.isoformat(),
                                "notice_text": variant.notice_text}
        assert alias[1:] not in {expected_seed, group_id[1:]}
    assert group_id[1:] != expected_seed


def test_domain_namespace_phase_and_key_separation(material_a, material_b):
    context = ("same", "context")
    domain_values = {material_a._mac(domain, *context) for domain in (
        "private-seed", "group-alias", "variant-alias", "private-manifest", "synthetic-lock",
    )}
    assert len(domain_values) == 5
    with pytest.raises(ValueError, match="domain"):
        material_a._mac("unregistered-domain", *context)
    test_seed = candidate._private_seed_id(material_a, TEST, "full", "assigned", 1)
    pilot_seed = candidate._private_seed_id(material_a, PILOT, "full", "assigned", 1)
    assert test_seed != pilot_seed  # No pilot notice is constructed by this identity check.
    assert test_seed != candidate._private_seed_id(material_a, TEST, "full", "reserve", 1)
    assert test_seed != candidate._private_seed_id(material_a, TEST, "reduced", "assigned", 1)
    assert test_seed != candidate._private_seed_id(material_b, TEST, "full", "assigned", 1)
    assert test_seed != candidate._private_seed_id(material_a, TEST, "full", "assigned", 2)
    with pytest.raises(ValueError, match="namespace"):
        candidate._private_seed_id(material_a, "evaluation", "full", "assigned", 1)


@pytest.mark.parametrize("name, count, cell_values, family_values", [
    ("full", 80, {10}, [20, 20, 20, 20]),
    ("reduced", 50, {6, 7}, [12, 12, 13, 13]),
])
def test_complete_balanced_programmes_and_reserve(request, name, count, cell_values, family_values):
    value = request.getfixturevalue(name)
    candidate.validate_synthetic_programme(value)
    assert value.scope == "synthetic" and value.namespace == TEST
    assert len(value.assigned) == count and len(value.reserve) == 16
    cells = Counter((seed._source.wording_family, seed._source.competing_order) for seed in value.assigned)
    assert len(cells) == 8 and set(cells.values()) == cell_values
    assert sorted(Counter(seed._source.wording_family for seed in value.assigned).values()) == family_values
    assert Counter(seed._source.competing_order for seed in value.assigned) == {
        "earlier": count // 2, "later": count // 2,
    }
    reserve_cells = Counter((seed._source.wording_family, seed._source.competing_order) for seed in value.reserve)
    assert len(reserve_cells) == 8 and set(reserve_cells.values()) == {2}
    assert [candidate._group_alias(seed) for seed in value.assigned] == sorted(
        candidate._group_alias(seed) for seed in value.assigned
    )
    assert [candidate._group_alias(seed) for seed in value.reserve] == sorted(
        candidate._group_alias(seed) for seed in value.reserve
    )


@pytest.mark.parametrize("name", ["full", "reduced"])
def test_chronology_exact_original_dates_2x2_and_one_sha_selected_primary_pair(request, name):
    value = request.getfixturevalue(name)
    for seed in (*value.assigned, *value.reserve):
        candidate.validate_synthetic_seed(seed)
        source = seed._source
        original.validate_structure(source)
        digest = hashlib.sha256(f"20261011|role-dates-v1|{source.seed_id}".encode()).digest()
        update = date(2027, 1, 1) + timedelta(days=int.from_bytes(digest[:4], "big") % 730)
        assert source.update_date == update
        assert source.publication_date == update - timedelta(days=80 + digest[4] % 20)
        assert source.superseded_issue_date == update - timedelta(days=35 + digest[5] % 15)
        assert source.superseded_target_date == update - timedelta(days=5 + digest[6] % 20)
        assert source.target_date == update + timedelta(days=60 + digest[7] % 90)
        gap = 14 + digest[8] % 14
        sign = -1 if source.competing_order == "earlier" else 1
        assert source.competing_date == source.target_date + timedelta(days=sign * gap)
        assert (source.publication_date < source.superseded_issue_date < source.superseded_target_date
                < source.update_date < min(source.target_date, source.competing_date))
        assert len({source.publication_date, source.superseded_issue_date, source.superseded_target_date,
                    source.update_date, source.target_date, source.competing_date}) == 6
        by_factor = {(variant.arm, variant.position): variant for variant in source.variants}
        assert set(by_factor) == {(arm, position) for arm in original.ARMS for position in original.POSITIONS}
        bit = hashlib.sha256(f"20261011|role-primary-position|{source.seed_id}".encode()).digest()[0] >> 7
        expected_position = ("first", "last")[bit]
        assert sum(variant.primary for variant in source.variants) == 2
        assert {(variant.arm, variant.position) for variant in source.variants if variant.primary} == {
            ("competitor", expected_position), ("neutral", expected_position),
        }
        for position in original.POSITIONS:
            competitor, neutral = by_factor[("competitor", position)], by_factor[("neutral", position)]
            assert competitor.notice_text.replace("Next review", "Data filing") == neutral.notice_text
            assert len(competitor.notice_text) == len(neutral.notice_text)
            for variant in (competitor, neutral):
                assert variant.update_date == source.update_date
                for role_date in (source.publication_date, source.superseded_issue_date,
                                  source.superseded_target_date, source.target_date, source.competing_date):
                    assert variant.notice_text.count(role_date.isoformat()) == 1


def test_ids_are_unique_and_package_separated(full, reduced, full_lock, reduced_lock):
    id_sets = []
    for value, lock in ((full, full_lock), (reduced, reduced_lock)):
        seeds = (*value.assigned, *value.reserve)
        views = (*lock.visible_views("assigned"), *lock.visible_views("reserve"))
        private_ids = {seed._source.seed_id for seed in seeds}
        groups = {view["group_id"] for view in views}
        aliases = {item["item_id"] for view in views for item in view["notices"]}
        assert len(private_ids) == len(groups) == len(seeds)
        assert len(aliases) == 4 * len(seeds)
        assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in private_ids)
        assert all(re.fullmatch(r"G[0-9a-f]{64}", value) for value in groups)
        assert all(re.fullmatch(r"V[0-9a-f]{64}", value) for value in aliases)
        id_sets.append((private_ids, groups, aliases))
    for left, right in zip(*id_sets, strict=True):
        assert left.isdisjoint(right)


def test_alias_collisions_fail_closed_instead_of_reselecting(full, full_lock, monkeypatch):
    monkeypatch.setattr(candidate, "_variant_alias", lambda seed, variant: "V" + "0" * 64)
    with pytest.raises(ValueError, match="collision"):
        candidate.validate_synthetic_programme(full)
    with pytest.raises(ValueError, match="collision"):
        full_lock.visible(full.assigned[0])


def test_group_collisions_fail_closed_instead_of_reselecting(full, monkeypatch):
    monkeypatch.setattr(candidate, "_group_alias", lambda seed: "G" + "0" * 64)
    with pytest.raises(ValueError, match="collision"):
        candidate.validate_synthetic_programme(full)


def test_visible_alias_cannot_expose_another_private_seed(full, full_lock, monkeypatch):
    seed, other = full.assigned[:2]
    variant_alias = candidate._variant_alias

    def leaking_alias(item, variant):
        if item is seed and variant is seed._source.variants[0]:
            return "V" + other._source.seed_id
        return variant_alias(item, variant)

    monkeypatch.setattr(candidate, "_variant_alias", leaking_alias)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        full_lock.visible(seed)


def test_different_invented_secrets_produce_different_mappings(material_b, reduced, reduced_lock):
    other = programme("reduced", material_b)
    other_lock = synthetic_lock(other)
    assert other.material_commitment_sha256 != reduced.material_commitment_sha256
    assert other.manifest_commitment_sha256 != reduced.manifest_commitment_sha256
    first = {seed._source.seed_id for seed in (*reduced.assigned, *reduced.reserve)}
    second = {seed._source.seed_id for seed in (*other.assigned, *other.reserve)}
    assert first.isdisjoint(second)
    first_views = (*reduced_lock.visible_views("assigned"), *reduced_lock.visible_views("reserve"))
    second_views = (*other_lock.visible_views("assigned"), *other_lock.visible_views("reserve"))
    first_groups = {view["group_id"] for view in first_views}
    second_groups = {view["group_id"] for view in second_views}
    assert first_groups.isdisjoint(second_groups)
    first_aliases = {notice["item_id"] for view in first_views for notice in view["notices"]}
    second_aliases = {notice["item_id"] for view in second_views for notice in view["notices"]}
    assert first_aliases.isdisjoint(second_aliases)


def test_visible_view_and_reprs_do_not_expose_private_material_or_raw_seed_ids(full, full_lock, material_a):
    seeds = (*full.assigned, *full.reserve)
    views = (*full_lock.visible_views("assigned"), *full_lock.visible_views("reserve"))
    receipt_repr = repr(full_lock.receipt())
    for seed, visible in zip(seeds, views, strict=True):
        assert set(visible) == {"synthetic_only", "group_id", "notices"}
        assert visible["synthetic_only"] is True and visible["group_id"] == candidate._group_alias(seed)
        assert len(visible["notices"]) == 4
        assert [item["item_id"] for item in visible["notices"]] == sorted(
            item["item_id"] for item in visible["notices"]
        )
        assert all(set(item) == {"item_id", "update_date", "notice_text"} for item in visible["notices"])
        encoded = json.dumps(visible, sort_keys=True)
        for representation in (encoded, repr(visible), repr(seed), repr(seed._source), repr(seed._source.variants),
                               repr(seed._source.variants[0]), repr(full), repr(full.assigned), repr(material_a),
                               repr(full_lock), receipt_repr):
            assert seed._source.seed_id not in representation
            assert INVENTED_KEY_A.hex() not in representation
            assert base64.b64encode(INVENTED_KEY_A).decode() not in representation
            assert repr(INVENTED_KEY_A) not in representation
        assert not ({"seed_id", "target_date", "primary", "arm", "position", "wording_family"} & set(visible))
    # The detached view can be changed by a caller without changing the source.
    view = full_lock.visible(full.assigned[0])
    view["notices"][0]["notice_text"] = "invented local mutation"
    assert full_lock.visible(full.assigned[0])["notices"][0]["notice_text"] != "invented local mutation"


def test_private_records_are_not_accidentally_copied_or_serialized(full, full_lock, material_a):
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="copied or serialized"):
            operation(material_a)
    with pytest.raises(TypeError, match="copied or serialized"):
        asdict(full)
    with pytest.raises(TypeError, match="copied or serialized"):
        pickle.dumps(full.assigned[0])
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="copied or serialized"):
            operation(full_lock)


@pytest.mark.parametrize("form", ["plain", "json-escaped", "python-escaped", "raw-seed", "ordinary"])
def test_private_variant_blocks_inherited_model_input_and_hash(full, form):
    seed = full.assigned[0]
    text = INVENTED_ESCAPED_KEY.decode("utf-8")
    supplied = {
        "plain": text,
        "json-escaped": json.dumps(text, ensure_ascii=True)[1:-1],
        "python-escaped": repr(INVENTED_ESCAPED_KEY)[2:-1],
        "raw-seed": seed._source.seed_id,
        "ordinary": "Invented ordinary synthetic text.",
    }[form]
    variant = replace(seed._source.variants[0], notice_text=supplied)
    assert isinstance(variant, original.RoleVariant)
    with pytest.raises(ValueError, match="private variant delivery is disabled"):
        variant.model_input()
    with pytest.raises(ValueError, match="private variant delivery is disabled"):
        _ = variant.model_input_sha256


def test_standalone_seed_delivery_is_disabled_even_after_a_programme_lock(full, full_lock):
    seed = full.assigned[0]
    with pytest.raises(ValueError, match="standalone seed delivery is disabled"):
        seed.visible()
    with pytest.raises(ValueError, match="standalone seed delivery is disabled"):
        _ = seed.group_id
    assert full_lock.visible(seed)["synthetic_only"] is True
    with pytest.raises(ValueError, match="standalone seed delivery is disabled"):
        seed.visible()


def test_synthetic_lock_requires_preflight_matching_manifest_and_explicit_unseen_feedback(full):
    manifest = full.manifest_commitment_sha256
    with pytest.raises(TypeError, match="feedback_seen"):
        candidate.lock_synthetic_programme(full, expected_manifest_commitment_sha256=manifest, feedback_seen=None)
    with pytest.raises(TypeError, match="feedback_seen"):
        candidate.lock_synthetic_programme(full, expected_manifest_commitment_sha256=manifest, feedback_seen=0)
    with pytest.raises(ValueError, match="declared feedback exposure"):
        candidate.lock_synthetic_programme(full, expected_manifest_commitment_sha256=manifest, feedback_seen=True)
    with pytest.raises(ValueError, match="expected programme manifest commitment does not match"):
        candidate.lock_synthetic_programme(full, expected_manifest_commitment_sha256="0" * 64, feedback_seen=False)
    with pytest.raises(ValueError, match="lowercase SHA256"):
        candidate.lock_synthetic_programme(full, expected_manifest_commitment_sha256="invalid", feedback_seen=False)
    with pytest.raises(TypeError):
        candidate.lock_synthetic_programme(full, expected_manifest_commitment_sha256=manifest)
    with pytest.raises(TypeError, match="use lock_synthetic_programme"):
        candidate.SyntheticRoleLock()


def test_fake_tampered_and_foreign_locks_fail_closed(full, reduced, full_lock):
    seed = full.assigned[0]
    fake = object.__new__(candidate.SyntheticRoleLock)
    with pytest.raises(ValueError, match="not issued by this in-memory factory"):
        fake.visible(seed)
    # Copying even every valid field does not make a second issued lock.
    object.__setattr__(fake, "_programme", full)
    object.__setattr__(fake, "_manifest", full_lock._manifest)
    object.__setattr__(fake, "_lock_commitment", full_lock._lock_commitment)
    with pytest.raises(ValueError, match="not issued by this in-memory factory"):
        fake.visible(seed)
    with pytest.raises(TypeError, match="exact synthetic programme lock"):
        candidate.SyntheticRoleLock.visible("not-a-lock", seed)
    with pytest.raises(ValueError, match="not bound"):
        full_lock.visible(reduced.assigned[0])
    with pytest.raises(ValueError, match="phase"):
        full_lock.visible_views("evaluation")

    fresh = programme("reduced", isolated_material("fake and tampered locks"))
    fresh_seed = fresh.assigned[0]
    wrong_manifest = synthetic_lock(fresh)
    wrong_commitment = synthetic_lock(fresh)
    swapped_programme = synthetic_lock(fresh)
    object.__setattr__(wrong_manifest, "_manifest", "0" * 64)
    with pytest.raises(ValueError, match="does not match the programme manifest"):
        wrong_manifest.visible(fresh_seed)
    with pytest.raises(ValueError, match="does not match the programme manifest"):
        wrong_manifest.receipt()
    object.__setattr__(wrong_commitment, "_lock_commitment", "0" * 64)
    with pytest.raises(ValueError, match="lock commitment does not match"):
        wrong_commitment.visible(fresh_seed)
    equivalent_programme = replace(fresh)
    object.__setattr__(swapped_programme, "_programme", equivalent_programme)
    with pytest.raises(ValueError, match="differs from its in-memory issuance"):
        swapped_programme.visible(equivalent_programme.assigned[0])


def test_receipt_is_exact_detached_and_excludes_all_private_ids_and_key(full, full_lock):
    receipt = full_lock.receipt()
    assert set(receipt) == {
        "kind", "synthetic_only", "generator_version", "scope", "namespace", "package",
        "wording_lineage_sha256", "material_commitment_sha256", "manifest_commitment_sha256",
        "lock_commitment_sha256", "feedback_not_seen_caller_attestation",
    }
    assert receipt["manifest_commitment_sha256"] == full.manifest_commitment_sha256
    assert receipt["lock_commitment_sha256"] == reference_mac(
        INVENTED_KEY_A, "synthetic-lock", "synthetic", TEST, "full", full.manifest_commitment_sha256,
        "caller-asserts-no-feedback-before-lock",
    )
    assert receipt["feedback_not_seen_caller_attestation"] is True
    assert receipt["synthetic_only"] is True and receipt["scope"] == "synthetic"
    encoded = json.dumps(receipt, sort_keys=True)
    assert INVENTED_KEY_A.hex() not in encoded
    assert base64.b64encode(INVENTED_KEY_A).decode("ascii") not in encoded
    assert all(seed._source.seed_id not in encoded for seed in (*full.assigned, *full.reserve))
    receipt["scope"] = "invented mutation"
    assert full_lock.receipt()["scope"] == "synthetic"


def test_lock_rejects_even_nonsecret_extra_receipt_fields(full, full_lock, monkeypatch):
    receipt = candidate._lock_receipt

    def changed_receipt(lock):
        value = receipt(lock)
        value["invented_extra"] = "not in the locked receipt schema"
        return value

    monkeypatch.setattr(candidate, "_lock_receipt", changed_receipt)
    with pytest.raises(ValueError, match="receipt does not match its exact projection"):
        full_lock.receipt()
    with pytest.raises(ValueError, match="receipt does not match its exact projection"):
        full_lock.visible(full.assigned[0])


@pytest.mark.parametrize("private_form", ["material-hex", "raw-seed"])
def test_lock_receipt_never_exports_a_private_value_even_if_a_digest_collides(private_form, monkeypatch):
    material = isolated_material("receipt digest collision " + private_form)
    fresh = programme("reduced", material)
    leaked = material._material.hex() if private_form == "material-hex" else fresh.reserve[0]._source.seed_id
    monkeypatch.setattr(candidate, "_lock_commitment", lambda programme, manifest: leaked)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        synthetic_lock(fresh)


@pytest.mark.parametrize("encoding", ["raw", "json-escaped", "double-json-escaped", "python-escaped"])
def test_receipt_preflight_rejects_quote_backslash_and_control_encodings(
    escaped_reduced, escaped_reduced_lock, encoding, monkeypatch,
):
    plaintext = INVENTED_ESCAPED_KEY.decode("utf-8")
    json_escaped = json.dumps(plaintext, ensure_ascii=True)[1:-1]
    private_value = {
        "raw": plaintext,
        "json-escaped": json_escaped,
        "double-json-escaped": json.dumps(json_escaped, ensure_ascii=True)[1:-1],
        "python-escaped": repr(INVENTED_ESCAPED_KEY)[2:-1],
    }[encoding]
    receipt = candidate._lock_receipt

    def leaking_receipt(lock):
        value = receipt(lock)
        value["kind"] += private_value
        return value

    monkeypatch.setattr(candidate, "_lock_receipt", leaking_receipt)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        escaped_reduced_lock.receipt()
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        escaped_reduced_lock.visible(escaped_reduced.assigned[0])


@pytest.mark.parametrize("private_form", ["material-hex", "raw-seed"])
def test_programme_manifest_field_is_checked_as_an_exported_receipt(full, private_form, monkeypatch):
    leaked = INVENTED_KEY_A.hex() if private_form == "material-hex" else full.reserve[0]._source.seed_id
    monkeypatch.setattr(candidate, "_manifest_commitment", lambda *args: leaked)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        replace(full, manifest_commitment_sha256=leaked)


def test_programme_preflight_refuses_even_a_common_plaintext_encoding_of_the_key():
    # This deliberately predictable, tagged invented key passes only shape checks.
    key = b"The recovery estimate issued on "
    assert len(key) == 32 and len(set(key)) >= 16
    material = private_material(key)
    ordinal, seed_id, family, order = candidate._allocation(material, TEST, "reduced", "assigned")[0]
    seed = candidate.SyntheticRoleSeed(TEST, "reduced", "assigned", ordinal,
                                       original._make_seed(seed_id, family, order), material)
    assert key.decode() in seed._source.variants[0].notice_text
    with pytest.raises(ValueError, match="standalone seed delivery is disabled"):
        seed.visible()
    with pytest.raises(ValueError, match="private variant delivery is disabled"):
        seed._source.variants[0].model_input()
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        programme("reduced", material)
    assert key.decode() not in repr(seed) and key.decode() not in repr(material)


def test_programme_preflight_checks_the_exact_python_view_repr():
    # Deliberately predictable invented key: its literal text crosses view keys
    # in repr rather than occurring in any value or the canonical JSON.
    key = b"{'synthetic_only': True, 'group_"
    assert len(key) == 32 and len(set(key)) >= 16
    material = private_material(key)
    ordinal, seed_id, family, order = candidate._allocation(material, TEST, "reduced", "assigned")[0]
    seed = candidate.SyntheticRoleSeed(TEST, "reduced", "assigned", ordinal,
                                       original._make_seed(seed_id, family, order), material)
    view = candidate._project_visible(seed)
    assert key.decode() in repr(view)
    assert all(key.decode() not in value for value in candidate._export_strings(view))
    assert key.decode() not in candidate._canonical(view)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        candidate._check_projection(seed, view, candidate._disclosure_tokens(key, (seed_id,)))
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        programme("reduced", material)


def test_programme_preflight_checks_unicode_normalized_private_material(monkeypatch):
    import unicodedata

    key = ("é" + "abcdefghijklmnopqrstuvwx123456").encode("utf-8")
    assert len(key) == 32 and len(set(key)) >= 16
    material = private_material(key)
    original_project = candidate._project_visible

    def leaking_projection(seed):
        view = original_project(seed)
        view["notices"][0]["notice_text"] += " " + unicodedata.normalize("NFD", key.decode("utf-8"))
        return view

    monkeypatch.setattr(candidate, "_project_visible", leaking_projection)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        programme("reduced", material)


@pytest.mark.parametrize("phase", ["assigned", "reserve"])
def test_validation_manifest_and_lock_all_preflight_each_phase(full, full_lock, phase, monkeypatch):
    target = getattr(full, phase)[0]
    project = candidate._project_visible

    def leaking_projection(seed):
        view = project(seed)
        if seed is target:
            view["notices"][0]["notice_text"] += " " + INVENTED_KEY_A.hex()
        return view

    monkeypatch.setattr(candidate, "_project_visible", leaking_projection)
    for operation in (
        lambda: candidate.validate_synthetic_programme(full),
        lambda: full.verify_manifest(full.manifest_commitment_sha256),
        lambda: full_lock.receipt(),
        lambda: full_lock.visible(full.assigned[1]),
        lambda: full_lock.visible_views("assigned"),
    ):
        with pytest.raises(ValueError, match="private seed or HMAC material"):
            operation()


@pytest.mark.parametrize("encoding", ["raw", "json-escaped", "double-json-escaped", "python-escaped", "seed-id"])
def test_preflight_rejects_quoted_backslash_control_and_private_seed_encodings(
    escaped_reduced, escaped_reduced_lock, encoding, monkeypatch,
):
    target = escaped_reduced.reserve[0]
    plaintext = INVENTED_ESCAPED_KEY.decode("utf-8")
    json_escaped = json.dumps(plaintext, ensure_ascii=True)[1:-1]
    private_value = {
        "raw": plaintext,
        "json-escaped": json_escaped,
        "double-json-escaped": json.dumps(json_escaped, ensure_ascii=True)[1:-1],
        "python-escaped": repr(INVENTED_ESCAPED_KEY)[2:-1],
        "seed-id": escaped_reduced.assigned[0]._source.seed_id,
    }[encoding]
    project = candidate._project_visible

    def leaking_projection(seed):
        view = project(seed)
        if seed is target:
            view["notices"][0]["notice_text"] += private_value
        return view

    monkeypatch.setattr(candidate, "_project_visible", leaking_projection)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        escaped_reduced.verify_manifest(escaped_reduced.manifest_commitment_sha256)
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        escaped_reduced_lock.visible(escaped_reduced.assigned[0])
    with pytest.raises(ValueError, match="private seed or HMAC material"):
        escaped_reduced_lock.receipt()


@pytest.mark.parametrize("operation", ["validate", "verify", "lock-view", "lock-receipt"])
def test_every_exact_projection_is_preflighted_before_success(full, full_lock, operation, monkeypatch):
    original_project = candidate._project_visible
    seen = []

    def tracked(seed):
        view = original_project(seed)
        seen.append((seed, view))
        return view

    monkeypatch.setattr(candidate, "_project_visible", tracked)
    if operation == "validate":
        candidate.validate_synthetic_programme(full)
    elif operation == "verify":
        full.verify_manifest(full.manifest_commitment_sha256)
    elif operation == "lock-view":
        shown = full_lock.visible(full.assigned[0])
        assert shown is seen[0][1]  # The checked object, not a second rendering.
    else:
        full_lock.receipt()
    assert [id(seed) for seed, _ in seen] == [id(seed) for seed in (*full.assigned, *full.reserve)]


@pytest.mark.parametrize("defect", ["extra-field", "reordered-variants", "changed-text", "unmarked"])
def test_exact_projection_drift_fails_closed(full, full_lock, defect, monkeypatch):
    target = full.reserve[0]
    project = candidate._project_visible

    def changed_projection(seed):
        view = project(seed)
        if seed is target:
            if defect == "extra-field":
                view["invented_extra"] = "unregistered synthetic field"
            elif defect == "reordered-variants":
                view["notices"].reverse()
            elif defect == "changed-text":
                view["notices"][0]["notice_text"] += " Invented change."
            else:
                view["synthetic_only"] = False
        return view

    monkeypatch.setattr(candidate, "_project_visible", changed_projection)
    with pytest.raises(ValueError):
        candidate.validate_synthetic_programme(full)
    with pytest.raises(ValueError):
        full.verify_manifest(full.manifest_commitment_sha256)
    with pytest.raises(ValueError):
        full_lock.visible(full.assigned[0])


def test_manifest_binds_exact_views_even_if_projection_checks_are_weakened(full, full_lock, monkeypatch):
    target = full.reserve[0]
    project = candidate._project_visible

    def changed_projection(seed):
        view = project(seed)
        if seed is target:
            view["notices"][0]["notice_text"] += " Invented benign change."
        return view

    # Exercise the manifest binding independently of the exact-projection check.
    monkeypatch.setattr(candidate, "_project_visible", changed_projection)
    monkeypatch.setattr(candidate, "_check_projection",
                        lambda seed, view, tokens: candidate._assert_safe_export(tokens, view))
    with pytest.raises(ValueError, match="manifest commitment does not match"):
        full.verify_manifest(full.manifest_commitment_sha256)
    with pytest.raises(ValueError, match="manifest commitment does not match"):
        full_lock.visible(full.assigned[0])


@pytest.mark.parametrize("defect", [
    "missing", "duplicate", "conflicting_id", "conflicting_position", "conflicting_text", "wrong_update",
    "wrong_primary", "same_dates", "bad_chronology", "wrong_order", "wrong_family",
])
def test_conflicting_or_missing_variants_and_dates_fail_closed(full, defect):
    seed = full.assigned[0]
    source = seed._source
    variants = list(source.variants)
    if defect == "missing":
        broken = replace(source, variants=tuple(variants[:-1]))
    elif defect == "duplicate":
        broken = replace(source, variants=(variants[0],) * 4)
    elif defect == "conflicting_id":
        variants[0] = replace(variants[0], item_id=variants[1].item_id)
        broken = replace(source, variants=tuple(variants))
    elif defect == "conflicting_position":
        variants[0] = replace(variants[0], position="last")
        broken = replace(source, variants=tuple(variants))
    elif defect == "conflicting_text":
        variants[0] = replace(variants[0], notice_text=variants[0].notice_text.replace("superseded", "current"))
        broken = replace(source, variants=tuple(variants))
    elif defect == "wrong_update":
        variants[0] = replace(variants[0], update_date=source.update_date + timedelta(days=1))
        broken = replace(source, variants=tuple(variants))
    elif defect == "wrong_primary":
        variants[0] = replace(variants[0], primary=not variants[0].primary)
        broken = replace(source, variants=tuple(variants))
    elif defect == "same_dates":
        broken = replace(source, competing_date=source.target_date)
    elif defect == "bad_chronology":
        broken = replace(source, publication_date=source.update_date + timedelta(days=1))
    elif defect == "wrong_order":
        other = "later" if source.competing_order == "earlier" else "earlier"
        broken = original._make_seed(source.seed_id, source.wording_family, other)
    else:
        broken = original._make_seed(source.seed_id, (source.wording_family + 1) % 4, source.competing_order)
    with pytest.raises(ValueError):
        replace(seed, _source=broken)


def test_lock_revalidates_an_in_memory_mutated_seed():
    fresh = programme("reduced", isolated_material("mutated seed revalidation"))
    seed = replace(fresh.assigned[0])
    isolated = replace(fresh, assigned=(seed, *fresh.assigned[1:]))
    lock = synthetic_lock(isolated)
    object.__setattr__(seed, "_source", replace(seed._source, variants=seed._source.variants[:-1]))
    with pytest.raises(ValueError):
        lock.visible(isolated.assigned[1])


def test_fixed_reserve_and_manifest_are_deterministic_and_not_feedback_parameterized(full, full_lock):
    again = programme("full", private_material())
    assert full.material_commitment_sha256 == again.material_commitment_sha256
    assert full.manifest_commitment_sha256 == again.manifest_commitment_sha256
    assert [candidate._group_alias(seed) for seed in full.assigned] == [
        candidate._group_alias(seed) for seed in again.assigned
    ]
    assert [candidate._group_alias(seed) for seed in full.reserve] == [
        candidate._group_alias(seed) for seed in again.reserve
    ]
    assert full_lock.visible_views("reserve") == tuple(candidate._project_visible(seed) for seed in again.reserve)
    with pytest.raises(ValueError, match="cannot be issued after programme view delivery"):
        synthetic_lock(again)
    assert full.verify_manifest(full.manifest_commitment_sha256) is None
    with pytest.raises(ValueError, match="does not match"):
        full.verify_manifest("0" * 64)
    with pytest.raises(ValueError, match="lowercase SHA256"):
        full.verify_manifest("invalid")
    assert set(inspect.signature(candidate.synthetic_role_programme).parameters) == {
        "package", "material", "scope", "namespace", "expected_lineage_sha256",
    }
    assert not hasattr(full, "replace_seed") and not hasattr(full, "select_reserve")
    with pytest.raises(TypeError):
        candidate.synthetic_role_programme("full", material=private_material(), scope="synthetic", namespace=TEST,
                                           expected_lineage_sha256=candidate.wording_lineage_sha256(),
                                           rejected_seed="invented-feedback")
    with pytest.raises(ValueError):
        replace(full, reserve=tuple(reversed(full.reserve)))
    with pytest.raises(ValueError):
        replace(full, manifest_commitment_sha256="0" * 64)


def test_locks_must_be_issued_before_any_supported_programme_delivery():
    material = isolated_material("lock issuance before synthetic delivery")
    first = programme("reduced", material)
    second = programme("reduced", material)
    assert first.manifest_commitment_sha256 == second.manifest_commitment_sha256
    first_lock = synthetic_lock(first)
    second_lock = synthetic_lock(second)
    assert first_lock.receipt() == second_lock.receipt()  # Receipts are not view delivery.
    assert first_lock.visible(first.assigned[0])["synthetic_only"] is True
    with pytest.raises(ValueError, match="cannot be issued after programme view delivery"):
        synthetic_lock(first)
    with pytest.raises(ValueError, match="cannot be issued after programme view delivery"):
        synthetic_lock(second)
    # An independently created but identical programme cannot bypass the local fence.
    third = programme("reduced", material)
    with pytest.raises(ValueError, match="cannot be issued after programme view delivery"):
        synthetic_lock(third)
    assert second_lock.visible(second.reserve[0])["synthetic_only"] is True


def test_namespace_and_wording_lineage_are_explicit_and_checked(full, full_lock, material_a, monkeypatch):
    assert full.wording_lineage_sha256 == candidate.wording_lineage_sha256()
    assert candidate.WORDING_LINEAGE == "role-materials-draft-v1-existing-families"
    with pytest.raises(ValueError, match="wording lineage"):
        programme("full", material_a, lineage="0" * 64)
    with pytest.raises(ValueError, match="namespace"):
        programme("full", material_a, namespace="synthetic-evaluation")
    with pytest.raises(TypeError):
        candidate.synthetic_role_programme("full", material=material_a, scope="synthetic", namespace=TEST)
    monkeypatch.setattr(original, "FAMILIES", original.FAMILIES[::-1])
    with pytest.raises(ValueError, match="lineage changed"):
        candidate.wording_lineage_sha256()
    with pytest.raises(ValueError, match="lineage changed"):
        full_lock.visible(full.assigned[0])


def test_changed_renderer_is_not_silently_accepted_as_the_original_structure(material_a, monkeypatch):
    renderer = original._render

    def changed_renderer(**values):
        # The legacy renderer and its validator would agree on this alteration.
        return renderer(**values) + " Invented extra sentence."

    monkeypatch.setattr(original, "_render", changed_renderer)
    with pytest.raises(ValueError, match="pinned original structure"):
        programme("reduced", material_a)


def test_reserved_pilot_namespace_never_renders_legacy_test_families(material_a, full, monkeypatch):
    def never_render(*args, **kwargs):
        raise AssertionError("the unresolved pilot must not call the legacy renderer")

    monkeypatch.setattr(original, "_make_seed", never_render)
    with pytest.raises(candidate.PilotIntegrationUnresolved, match="pilot rendering is unresolved"):
        candidate.synthetic_role_programme("full", material=material_a, scope="synthetic", namespace=PILOT,
                                           expected_lineage_sha256="0" * 64)
    with pytest.raises(candidate.PilotIntegrationUnresolved, match="pilot rendering is unresolved"):
        replace(full.assigned[0], namespace=PILOT)
    with pytest.raises(candidate.PilotIntegrationUnresolved, match="pilot rendering is unresolved"):
        replace(full, namespace=PILOT)


@pytest.mark.parametrize("scope", ["real", "evaluation", "eval", "pilot", "synthetic-evaluation", "", None, True])
def test_all_non_synthetic_scopes_fail_closed(material_a, scope):
    with pytest.raises(ValueError, match="real and evaluation scopes are disabled"):
        programme("reduced", material_a, scope=scope)


def test_registration_claims_cannot_activate_this_candidate(material_a, full):
    with pytest.raises(TypeError):
        candidate.synthetic_role_programme("full", material=material_a, scope="real", namespace=TEST,
                                           expected_lineage_sha256=candidate.wording_lineage_sha256(),
                                           registration="invented-claim", independently_verified=True)
    with pytest.raises(ValueError, match="real and evaluation scopes are disabled"):
        replace(full, scope="evaluation")


@pytest.mark.parametrize("package", ["", "50", "evaluation", None, True])
def test_unknown_packages_are_refused(material_a, package):
    with pytest.raises(ValueError, match="package"):
        programme(package, material_a)
