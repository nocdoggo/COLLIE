"""Invented data only: blinded machine-reference contracts and failure states."""

import base64
import copy
import hashlib
import hmac
import json
from dataclasses import FrozenInstanceError, asdict, fields, replace
from datetime import date, datetime, timedelta, timezone

import pytest

import analysis.coling.followup.machine_references as machine_references
from analysis.coling.followup.machine_references import (
    Agreement, BlindNotice, BlindReceipt, BlindRequest, BlindRoleSet, CallIdentity, DateSupport, Judge, LaterRegistration,
    LEGACY_PROTOCOL, SELECTED_PROTOCOL,
    MachineJudgment, MachineProtocol, MachineValidity, PrivateRoleBlinding, RawAnswer, ReconciledReadings, ReconciledRole,
    ReferenceState, RegisteredUse, RegistrationVerification, StageBinding, assess_synthetic_role_eligibility,
    assigned_identity, check_later_registration_claim, ingest_judgment, prepare_request as _prepare_request,
    reconcile_readings, reconcile_role, revalidate_readings, revalidate_role,
)
from analysis.coling.followup.records import NaturalReference, ParseStatus, StatementType
from analysis.coling.followup.role_materials import GENERATOR_VERSION, RoleSeed, RoleVariant, ValidationDecision, _make_seed


T0 = datetime(2028, 1, 1, tzinfo=timezone.utc)
BLOCK = "Invented convention: use the stated calendar end."
NOTICE = BlindNotice(
    "invented-notice", date(2028, 1, 15),
    "Invented notice: period starts 2028-03-01 and recovery estimated for 2028-03-14 or 2028-03-21 or 2028-03-25.",
)
_DEFAULT = object()
SYNTHETIC_PRIVATE_SEED = (
    "8f31a7c2b4e09d6572c1a3f905b8e46d"
    "91c2f7a56d08b3e4c9a12f684e73bd05"
)
SYNTHETIC_ALIAS_KEY = bytes.fromhex(
    "e0a1c2d3f40516273849bacbdcedfe0f"
    "193a5b7c9dbef0123456789abcde2468"
)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def role_blinding():
    return PrivateRoleBlinding(private_seed_id=SYNTHETIC_PRIVATE_SEED, alias_key=SYNTHETIC_ALIAS_KEY)


def prepare_request(p, material, *, attempt_id=None, **values):
    if attempt_id is None:
        attempt_id = f"attempt-{values['judge_code']}-{values['cohort']}-{values['stage']}"
    return _prepare_request(p, material, attempt_id=attempt_id, **values)


def protocol():
    judges = (
        Judge("M1", "fixture/judge-one", "revision-one", "route-one", "fp16"),
        Judge("M2", "fixture/judge-two", "revision-two", "route-two", "fp16"),
        Judge("MADJ", "fixture/judge-three", "revision-three", "route-three", "fp32"),
    )
    stages = [(code, cohort, stage) for code in ("M1", "M2") for cohort, stage in (
        ("N", "natural"), ("C", "unspecified"), ("C", "specified"), ("R", "role"),
    )]
    stages.extend(("MADJ", cohort, "adjudication") for cohort in ("N", "C", "R"))
    bindings = tuple(StageBinding(
        code, cohort, stage, f"template-{cohort}-{stage}", digest(f"template-{cohort}-{stage}"),
        digest(f"decoding-{cohort}-{stage}"), digest(f"schema-{cohort}-{stage}"),
        digest(f"parser-{cohort}-{stage}"),
        digest(BLOCK) if cohort == "C" and stage in {"specified", "adjudication"} else None,
    ) for code, cohort, stage in stages)
    blinding = role_blinding()
    return MachineProtocol("draft-fixture", ("fixture/evaluated-one", "fixture/evaluated-two"),
                           judges, bindings, "invented-v1", "synthetic", blinding.key_commitment_sha256,
                           (blinding.seed_commitment_sha256,), LEGACY_PROTOCOL)


def selected_protocol():
    base = protocol()
    stages = (("N", "blind_proposal"), ("C", "blind_unspecified"), ("C", "adjudication_absent"),
              ("C", "blind_specified"), ("C", "adjudication_specified"), ("R", "blind_proposal"))
    bindings = tuple(StageBinding(
        "MADJ", cohort, stage, f"template-{cohort}-{stage}", digest(f"template-{cohort}-{stage}"),
        digest(f"decoding-{cohort}-{stage}"), digest(f"schema-{cohort}-{stage}"),
        digest(f"parser-{cohort}-{stage}"),
        digest(BLOCK) if stage in {"blind_specified", "adjudication_specified"} else None,
    ) for cohort, stage in stages)
    retained = tuple(item for item in base.bindings if (item.judge_code, item.cohort, item.stage) !=
                     ("MADJ", "C", "adjudication"))
    return replace(base, protocol_design=SELECTED_PROTOCOL, bindings=(*retained, *bindings))


def option(*, end="2028-03-14", start="2028-03-01", statement="recovery", certainty="estimated",
           period="finite", quote=_DEFAULT):
    if quote is _DEFAULT:
        if end is None:
            quote = ""
        elif start == "2028-03-01" and end in NOTICE.notice_text:
            left = NOTICE.notice_text.index(start)
            right = NOTICE.notice_text.index(end) + len(end)
            quote = NOTICE.notice_text[left:right]
        else:
            quote = end
    return {"statement_type": statement, "period_status": period, "start": start,
            "end": end, "certainty": certainty, "quote": quote}


def reading(*options, reason=None):
    return {"alternatives": list(options), "unresolved_reason": reason}


def role_set():
    blinding = role_blinding()
    notices = []
    for number, (opaque, _) in enumerate(blinding.opaque_variant_map()):
        extra = "Next review" if number % 2 == 0 else "Administrative filing"
        text = (
            "Invented notice. Published 2027-12-01. Superseded recovery 2028-01-10. "
            f"Current recovery 2028-03-14. {extra} 2028-02-10."
        )
        notices.append(BlindNotice(opaque, date(2028, 1, 15), text))
    return BlindRoleSet(blinding.group_id, tuple(notices), blinding)


def role_reading(material, *, valid=True, reason=None):
    targets = []
    for notice in material.notices:
        is_review = "Next review" in notice.notice_text
        role, quote = (("next_review", "Next review 2028-02-10") if is_review else
                       ("administrative", "Administrative filing 2028-02-10"))
        targets.append({
            "variant_id": notice.item_id, "status": "exact", "target_date": "2028-03-14",
            "alternatives": [], "quote": "Current recovery 2028-03-14", "date_roles": [
                {"role": "publication", "date": "2027-12-01", "quote": "Published 2027-12-01"},
                {"role": "superseded_recovery", "date": "2028-01-10", "quote": "Superseded recovery 2028-01-10"},
                {"role": role, "date": "2028-02-10", "quote": quote},
            ],
        })
    checks = {name: True for name in (
        "unique_current_target", "coherent_chronology", "competing_role_preserves_target",
        "neutral_role_unrelated", "comparable_length_and_syntax", "position_preserves_meaning",
    )}
    return {"targets": targets, "checks": checks, "material_valid": valid, "reason": reason}


def answer(value):
    if isinstance(value, RawAnswer):
        return value
    return RawAnswer("returned", json.dumps(value), "stop", None)


def submit(p, request, value, *, judgment_id, submitted=T0 + timedelta(seconds=1), observed=_DEFAULT, **flags):
    raw = answer(value)
    if observed is _DEFAULT:
        observed = assigned_identity(p, request) if raw.kind == "returned" else None
    other_seen = (None if raw.kind == "unavailable" else False if raw.kind == "cap_blocked" else
                  request.judge_code == "MADJ" and request.stage in {
                      "adjudication", "adjudication_absent", "adjudication_specified",
                  } and bool(request.sources))
    exposure = {"evaluated_outputs_seen": False, "rule_proposals_seen": False, "sensitivity_seen": False,
                "outcomes_seen": False, "blind_madj_response_seen": False,
                "prior_madj_adjudication_seen": False,
                "convention_or_specified_preexposed": False,
                "other_judgments_seen": other_seen}
    exposure.update(flags)
    return ingest_judgment(p, request, judgment_id=judgment_id, answer=raw, observed_identity=observed,
                           submitted_utc=submitted, **exposure)


def firsts(p, material=NOTICE, cohort="N", left=_DEFAULT, right=_DEFAULT):
    stage = {"N": "natural", "C": "unspecified", "R": "role"}[cohort]
    default = role_reading(material) if cohort == "R" else reading(option())
    left = default if left is _DEFAULT else left
    right = default if right is _DEFAULT else right
    requests = [prepare_request(p, material, judge_code=code, cohort=cohort, stage=stage, shown_utc=T0)
                for code in ("M1", "M2")]
    return tuple(submit(p, request, value, judgment_id=f"{request.judge_code}-{cohort}-{stage}")
                 for request, value in zip(requests, (left, right)))


def specified(p, first, material=NOTICE, left=_DEFAULT, right=_DEFAULT):
    default = reading(option())
    left = default if left is _DEFAULT else left
    right = default if right is _DEFAULT else right
    requests = [prepare_request(p, material, judge_code=code, cohort="C", stage="specified",
                                shown_utc=T0 + timedelta(seconds=2), condition_block=BLOCK, first_passes=first)
                for code in ("M1", "M2")]
    return tuple(submit(p, request, value, judgment_id=f"{request.judge_code}-C-specified",
                        submitted=T0 + timedelta(seconds=3))
                 for request, value in zip(requests, (left, right)))


def adjudication(p, material, cohort, first, *, second=(), value=_DEFAULT):
    request = prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage="adjudication",
                              shown_utc=T0 + timedelta(seconds=4), first_passes=first,
                              specified_passes=second, condition_block=BLOCK if cohort == "C" else None)
    if value is _DEFAULT:
        if cohort == "C":
            value = {"defensible": reading(option()), "specified": reading(option()), "rationale": "Notice and rule."}
        else:
            value = {"reference": role_reading(material) if cohort == "R" else reading(option()),
                     "rationale": "Notice evidence."}
    return submit(p, request, value, judgment_id=f"MADJ-{cohort}", submitted=T0 + timedelta(seconds=5))


def blind_proposal(p, material, cohort, *, value=_DEFAULT, stage=None, first=(), earlier=(), absent=None,
                   shown=T0, submitted=T0 + timedelta(seconds=1), attempt_id=None):
    stage = stage or ("blind_unspecified" if cohort == "C" else "blind_proposal")
    request = prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage=stage,
                              shown_utc=shown, first_passes=first, blind_passes=earlier,
                              condition_block=BLOCK if stage == "blind_specified" else None, attempt_id=attempt_id,
                              absent_adjudication=absent)
    if value is _DEFAULT:
        value = role_reading(material) if cohort == "R" else reading(option())
    return submit(p, request, value, judgment_id=f"MADJ-{cohort}-{stage}", submitted=submitted)


def selected_absent(p, first, blind_first, *, value=_DEFAULT, shown=T0 + timedelta(seconds=2),
                    submitted=T0 + timedelta(seconds=3)):
    request = prepare_request(p, NOTICE, judge_code="MADJ", cohort="C", stage="adjudication_absent",
                              shown_utc=shown, first_passes=first, blind_passes=(blind_first,))
    if value is _DEFAULT:
        value = {"reference": reading(option()), "rationale": "Invented absent ruling."}
    return submit(p, request, value, judgment_id="MADJ-C-exposed-absent", submitted=submitted)


def selected_specified(p, first, blind_first, absent, *, left=_DEFAULT, right=_DEFAULT):
    left = reading(option()) if left is _DEFAULT else left
    right = reading(option()) if right is _DEFAULT else right
    requests = [prepare_request(p, NOTICE, judge_code=code, cohort="C", stage="specified",
                                shown_utc=T0 + timedelta(seconds=4), condition_block=BLOCK,
                                first_passes=first, blind_passes=(blind_first,), absent_adjudication=absent)
                for code in ("M1", "M2")]
    return tuple(submit(p, request, value, judgment_id=f"{request.judge_code}-selected-specified",
                        submitted=T0 + timedelta(seconds=5))
                 for request, value in zip(requests, (left, right)))


def selected_adjudication(p, material, cohort, first, *, second=(), blinds=(), absent=None, value=_DEFAULT):
    request = prepare_request(p, material, judge_code="MADJ", cohort=cohort,
                              stage="adjudication_specified" if cohort == "C" else "adjudication",
                              shown_utc=T0 + timedelta(seconds=6 if cohort == "C" else 4), first_passes=first,
                              specified_passes=second, blind_passes=blinds,
                              condition_block=BLOCK if cohort == "C" else None, absent_adjudication=absent)
    if value is _DEFAULT:
        value = {"reference": role_reading(material) if cohort == "R" else reading(option()),
                 "rationale": "Invented ruling."}
    return submit(p, request, value, judgment_id=f"MADJ-{cohort}-exposed-specified" if cohort == "C" else
                  f"MADJ-{cohort}-exposed", submitted=T0 + timedelta(seconds=7 if cohort == "C" else 5))


def n_reference(p, first, adj=None):
    return reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1",
                              first_passes=first, adjudication=adj)


def c_reference(p, first, second=(), adj=None):
    return reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1",
                              first_passes=first, specified_passes=second, adjudication=adj)


def r_reference(p, material, first, adj=None):
    return reconcile_role(p, material, reference_version="invented-v1", first_passes=first, adjudication=adj)


@pytest.mark.parametrize("code", ["A1", "ADJ", "M3", "m1", "", "M1 "])
def test_machine_codes_are_fixed_and_not_human_codes(code):
    with pytest.raises(ValueError, match="M1"):
        Judge(code, "fixture/model", "revision", "route", "fp16")


@pytest.mark.parametrize("model_id", ["model", "fixture/", "/model", "fixture/model ", "fixture/model/extra"])
def test_model_ids_are_provider_qualified_and_exact(model_id):
    with pytest.raises(ValueError, match="model ID"):
        Judge("M1", model_id, "revision", "route", "fp16")


@pytest.mark.parametrize("field,value", [
    ("provider_route", "auto"), ("provider_route", "unknown"), ("provider_route", "*"),
    ("precision", "default"), ("precision", ""), ("model_revision", "latest"),
    ("model_revision", "unknown"),
])
def test_route_and_precision_must_be_pinned(field, value):
    with pytest.raises(ValueError):
        replace(protocol().judges[0], **{field: value})


def test_all_three_judge_models_differ_from_one_another_and_every_evaluated_model():
    p = protocol()
    with pytest.raises(ValueError, match="distinct"):
        replace(p, judges=(p.judges[0], replace(p.judges[1], model_id="FIXTURE/JUDGE-ONE"), p.judges[2]))
    with pytest.raises(ValueError, match="distinct"):
        replace(p, evaluated_model_ids=("fixture/evaluated-one", "FIXTURE/JUDGE-THREE"))
    with pytest.raises(ValueError, match="distinct"):
        replace(p, evaluated_model_ids=("fixture/evaluated-one", "FIXTURE/EVALUATED-ONE"))
    with pytest.raises(ValueError, match="complete"):
        replace(p, evaluated_model_ids=())
    with pytest.raises(ValueError, match="one M1"):
        replace(p, judges=(p.judges[0], p.judges[0], p.judges[2]))


def test_protocol_fingerprint_is_order_independent_but_binds_all_identities():
    p = protocol()
    assert p.sha256 == replace(p, judges=tuple(reversed(p.judges)), bindings=tuple(reversed(p.bindings))).sha256
    assert p.sha256 != replace(p, evaluated_model_ids=("fixture/evaluated-one", "fixture/evaluated-new")).sha256
    assert p.sha256 != replace(p, data_scope="real").sha256
    assert p.sha256 != replace(p, reference_version="invented-v2").sha256
    with pytest.raises(ValueError, match="synthetic or real"):
        replace(p, data_scope="unknown")
    updated = replace(p.bindings[0], parser_sha256=digest("changed-parser"))
    assert p.sha256 != replace(p, bindings=(updated, *p.bindings[1:])).sha256
    with pytest.raises(FrozenInstanceError):
        p.protocol_id = "changed"


@pytest.mark.parametrize("field", ["template_sha256", "decoding_sha256", "schema_sha256", "parser_sha256"])
def test_stage_identity_hashes_are_required_and_strict(field):
    with pytest.raises(ValueError, match="SHA256"):
        replace(protocol().bindings[0], **{field: "A" * 64})


def test_stage_bindings_reject_missing_duplicate_or_inconsistent_identities():
    p = protocol()
    with pytest.raises(ValueError, match="exactly one binding"):
        replace(p, bindings=(*p.bindings, p.bindings[0]))
    with pytest.raises(ValueError, match="different template hashes"):
        replace(p, bindings=(*p.bindings[:-1], replace(p.bindings[-1], template_id=p.bindings[0].template_id)))
    c_binding = next(item for item in p.bindings if item.cohort == "C" and item.stage == "specified")
    altered = tuple(replace(item, condition_sha256=digest("different")) if item is c_binding else item
                    for item in p.bindings)
    with pytest.raises(ValueError, match="same convention"):
        replace(p, bindings=altered)
    with pytest.raises(ValueError, match="stage"):
        replace(p.bindings[0], stage="adjudication")
    with pytest.raises(ValueError, match="SHA256"):
        replace(c_binding, condition_sha256=None)
    only_other = replace(p, bindings=(p.bindings[1],))
    with pytest.raises(ValueError, match="no exact binding"):
        prepare_request(only_other, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)


def test_visible_notice_is_allowlisted_detached_and_contains_no_evaluated_identity():
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    assert request.payload == {"update_date": "2028-01-15", "notice_text": NOTICE.notice_text}
    assert request.input_sha256 == digest(request.visible_json)
    assert "evaluated" not in request.visible_json and "sensitivity" not in request.visible_json
    assert "judge-one" not in request.visible_json and "invented-notice" not in request.visible_json
    modified = request.payload
    modified["evaluated_output"] = "not shown"
    assert "evaluated_output" not in request.payload
    with pytest.raises(ValueError, match="convention"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0,
                        condition_block=BLOCK)


def test_role_view_contains_four_opaque_ids_but_no_expected_target_or_factor_map():
    p, material = protocol(), role_set()
    request = prepare_request(p, material, judge_code="M1", cohort="R", stage="role", shown_utc=T0)
    assert set(request.payload) == {"notices"}
    assert len(request.payload["notices"]) == 4
    assert all(set(item) == {"item_id", "update_date", "notice_text"} for item in request.payload["notices"])
    assert material.group_id not in request.visible_json
    assert "target_date" not in request.visible_json and "sensitivity" not in request.visible_json
    assert "judge-one" not in request.visible_json and "evaluated-one" not in request.visible_json


def test_role_material_rejects_nonopaque_or_duplicated_identifiers():
    material = role_set()
    with pytest.raises(ValueError, match="opaque G"):
        replace(material, group_id="seed-with-factor")
    with pytest.raises(ValueError, match="opaque V"):
        replace(material, notices=(material.notices[0],) * 4)
    with pytest.raises(ValueError, match="opaque V"):
        replace(material, notices=(replace(material.notices[0], item_id="competitor-first"), *material.notices[1:]))
    with pytest.raises(ValueError, match="four notices"):
        replace(material, notices=material.notices[:3])


def test_request_reconstruction_rejects_extra_visible_data_even_with_a_matching_new_hash():
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    visible = json.dumps({**request.payload, "evaluated_output": "invented leakage"}, sort_keys=True,
                         separators=(",", ":"))
    altered = replace(request, _visible_json=visible, input_sha256=digest(visible))
    with pytest.raises(ValueError, match="altered"):
        _ = altered.visible_json
    with pytest.raises(ValueError, match="altered"):
        _ = altered.payload
    with pytest.raises(ValueError, match="altered"):
        submit(p, altered, reading(option()), judgment_id="tampered")


@pytest.mark.parametrize("field,value", [
    ("judge_code", "M2"), ("cohort", "C"), ("stage", "unspecified"),
    ("model_id", "fixture/different"), ("model_revision", "other-revision"),
    ("provider_route", "another-route"), ("precision", "fp32"),
    ("template_id", "another-template"), ("template_sha256", digest("different-template")),
    ("decoding_sha256", digest("different-decoding")), ("schema_sha256", digest("different-schema")),
    ("parser_sha256", digest("different-parser")), ("input_sha256", digest("different-input")),
])
def test_returned_identity_must_match_every_assigned_field(field, value):
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    observed = replace(assigned_identity(p, request), **{field: value})
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, request, reading(option()), judgment_id="mismatch", observed=observed)


def test_unavailable_responses_do_not_invent_a_served_identity():
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    unavailable = RawAnswer("unavailable", None, None, "invented unavailable")
    item = submit(p, request, unavailable, judgment_id="unavailable")
    assert item.status is ParseStatus.UNAVAILABLE and item.observed_identity is None
    assert item.answer.content_sha256 is None and item.other_judgments_seen is None and item.view_seen is None
    with pytest.raises(ValueError, match="cannot assert"):
        submit(p, request, unavailable, judgment_id="unavailable", observed=assigned_identity(p, request))
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, request, reading(option()), judgment_id="returned", observed=None)
    capped = submit(p, request, RawAnswer("cap_blocked", None, None, "invented cap"), judgment_id="cap")
    assert capped.status is ParseStatus.CAP_BLOCKED and capped.parse_reason == "invented cap"
    assert capped.other_judgments_seen is False and capped.view_seen is False


@pytest.mark.parametrize("field", [
    "evaluated_outputs_seen", "rule_proposals_seen", "sensitivity_seen", "other_judgments_seen",
])
def test_first_passes_refuse_exposure_or_other_machine_judgments(field):
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    with pytest.raises(ValueError):
        submit(p, request, reading(option()), judgment_id="exposed", **{field: True})
    with pytest.raises(TypeError, match="booleans"):
        submit(p, request, reading(option()), judgment_id="unknown", **{field: 0})


def test_adjudicator_sees_only_machine_passes_and_cannot_be_exposed_to_evaluated_outputs():
    p = protocol()
    first = firsts(p)
    request = prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                              shown_utc=T0 + timedelta(seconds=4), first_passes=first)
    assert set(request.payload) == {"material", "first_passes"}
    assert [item["judge_code"] for item in request.payload["first_passes"]] == ["M1", "M2"]
    assert "evaluated-one" not in request.visible_json and "sensitivity" not in request.visible_json
    value = {"reference": reading(option()), "rationale": "Notice evidence."}
    with pytest.raises(ValueError, match="other machine-judgment exposure"):
        submit(p, request, value, judgment_id="adj", submitted=T0 + timedelta(seconds=5),
               other_judgments_seen=False)
    with pytest.raises(ValueError, match="blind"):
        submit(p, request, value, judgment_id="adj", submitted=T0 + timedelta(seconds=5), sensitivity_seen=True)
    with pytest.raises(ValueError, match="blind"):
        submit(p, request, value, judgment_id="adj", submitted=T0 + timedelta(seconds=5),
               evaluated_outputs_seen=True)
    with pytest.raises(ValueError, match="blind"):
        submit(p, request, value, judgment_id="adj", submitted=T0 + timedelta(seconds=5),
               rule_proposals_seen=True)


@pytest.mark.parametrize("raw,expected,reason", [
    (RawAnswer("returned", "{", "stop", None), ParseStatus.INVALID_JSON, "invalid_json"),
    (RawAnswer("returned", '{"alternatives":[],"unresolved_reason":"x","unresolved_reason":"y"}', "stop", None),
     ParseStatus.INVALID_JSON, "invalid_json"),
    (RawAnswer("returned", '{"alternatives":[],"unresolved_reason":NaN}', "stop", None),
     ParseStatus.INVALID_JSON, "invalid_json"),
    (RawAnswer("returned", '{"alternatives":[],"unresolved_reason":"\\ud800"}', "stop", None),
     ParseStatus.INVALID_JSON, "invalid_json"),
    (RawAnswer("returned", '{"alternatives":[],"unresolved_reason":1e999}', "stop", None),
     ParseStatus.INVALID_JSON, "invalid_json"),
    (RawAnswer("returned", "{}", "stop", None), ParseStatus.INVALID_SCHEMA, "invalid_schema"),
    (RawAnswer("returned", "{}", "length", None), ParseStatus.TRUNCATED, "output_token_ceiling"),
    (RawAnswer("returned", "{}", "filtered", None), ParseStatus.INVALID_SCHEMA,
     "unsupported_or_missing_finish_reason"),
    (RawAnswer("returned", "{}", None, None), ParseStatus.INVALID_SCHEMA,
     "unsupported_or_missing_finish_reason"),
])
def test_returned_parse_failures_are_retained_without_repair(raw, expected, reason):
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    judgment = submit(p, request, raw, judgment_id="returned-failure")
    assert judgment.status is expected and judgment.parse_reason == reason and judgment.result is None
    assert judgment.view_seen is True
    assert judgment.answer.content == raw.content
    assert judgment.answer.content_sha256 == digest(raw.content)


@pytest.mark.parametrize("value", [
    {"alternatives": [], "unresolved_reason": None},
    {"alternatives": [], "unresolved_reason": " "},
    {"alternatives": [], "unresolved_reason": "unknown", "extra": "not accepted"},
    reading(option(end="2028-02-30", quote="2028-03-14")),
    reading(option(start="2028-03-20", end="2028-03-14")),
    reading(option(statement="none", certainty="no_statement")),
    reading(option(certainty="no_statement")),
    reading(option(period="none")),
    reading(option(quote=True)),
    reading({**option(), "extra": "not accepted"}),
])
def test_natural_schema_is_strict_and_does_not_coerce_invalid_content(value):
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    judgment = submit(p, request, value, judgment_id="invalid-schema")
    assert judgment.status is ParseStatus.INVALID_SCHEMA and judgment.result is None


def test_agreement_without_madj_never_silently_becomes_a_reference():
    p = protocol()
    first = firsts(p)
    result = n_reference(p, first)
    assert result.first_agreement is Agreement.AGREED
    assert result.state is ReferenceState.UNRESOLVED
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert result.first_passes == first and result.adjudication is None
    assert not isinstance(result, NaturalReference)


def test_disagreements_and_adjudicated_alternatives_remain_available():
    p = protocol()
    first = firsts(p, left=reading(option()), right=reading(option(end="2028-03-21")))
    decision = {"reference": reading(option(), option(end="2028-03-21")), "rationale": "Both readings remain."}
    adj = adjudication(p, NOTICE, "N", first, value=decision)
    result = n_reference(p, first, adj)
    assert revalidate_readings(result) is None
    assert result.first_agreement is Agreement.DISAGREED
    assert result.state is ReferenceState.UNRESOLVED
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert "machine_first_semantic_disagreement" in result.reasons
    assert len(result.defensible.alternatives) == 2
    assert first[0].result.alternatives[0].end == date(2028, 3, 14)
    assert first[1].result.alternatives[0].end == date(2028, 3, 21)
    assert result.adjudication.result.rationale == "Both readings remain."


def test_explicit_madj_choice_is_not_replaced_by_a_silent_two_of_three_majority():
    p = protocol()
    first = firsts(p)
    decision = {"reference": reading(option(end="2028-03-25")), "rationale": "Different notice interpretation."}
    adj = adjudication(p, NOTICE, "N", first, value=decision)
    result = n_reference(p, first, adj)
    assert result.first_agreement is Agreement.AGREED
    assert result.state is ReferenceState.UNRESOLVED
    assert result.endpoint.end is None
    assert result.defensible.alternatives[0].end == date(2028, 3, 25)
    assert "machine_adjudication_semantic_disagreement" in result.reasons
    assert all(item.result.alternatives[0].end == date(2028, 3, 14) for item in result.first_passes)


def test_alternative_order_does_not_create_a_false_reading_disagreement():
    p = protocol()
    a, b = option(), option(end="2028-03-21")
    first = firsts(p, left=reading(a, b), right=reading(b, a))
    assert n_reference(p, first).first_agreement is Agreement.AGREED


def test_unknown_fields_are_not_counted_as_agreement_and_a_known_end_is_preserved():
    p = protocol()
    partial = reading(option(start=None, statement=None, certainty=None))
    first = firsts(p, left=partial, right=partial)
    adj = adjudication(p, NOTICE, "N", first, value={"reference": partial, "rationale": "Only end is known."})
    result = n_reference(p, first, adj)
    assert result.first_agreement is Agreement.UNKNOWN
    assert result.state is ReferenceState.UNRESOLVED
    assert result.endpoint.period_status == "unresolved" and result.endpoint.end is None
    assert result.defensible.alternatives[0].end == date(2028, 3, 14)
    assert result.defensible.alternatives[0].statement_type is None
    assert result.defensible.alternatives[0].certainty is None


def test_unresolved_reason_overrides_an_apparently_unique_end_without_erasing_it():
    p = protocol()
    first = firsts(p)
    unresolved = reading(option(), reason="two meanings not resolved")
    adj = adjudication(p, NOTICE, "N", first, value={"reference": unresolved, "rationale": "Retain uncertainty."})
    result = n_reference(p, first, adj)
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert result.defensible.unresolved_reason == "two meanings not resolved"
    assert result.defensible.alternatives[0].end == date(2028, 3, 14)


def test_explicit_no_period_is_not_an_unavailable_or_unresolved_response():
    p = protocol()
    absent = reading(option(start=None, end=None, statement="none", certainty="no_statement", period="none"))
    first = firsts(p, left=absent, right=absent)
    adj = adjudication(p, NOTICE, "N", first, value={"reference": absent, "rationale": "No period stated."})
    result = n_reference(p, first, adj)
    assert result.state is ReferenceState.ADJUDICATED
    assert result.endpoint.period_status == "none" and result.endpoint.end is None
    assert result.endpoint.unresolved_reason is None
    assert result.defensible.alternatives[0].quote_valid is None


def test_a_finite_reading_and_a_no_period_alternative_do_not_share_an_endpoint():
    p = protocol()
    absent = option(start=None, end=None, statement="none", certainty="no_statement", period="none")
    alternatives = reading(option(), absent)
    first = firsts(p, left=alternatives, right=alternatives)
    adj = adjudication(p, NOTICE, "N", first, value={"reference": alternatives, "rationale": "Both remain."})
    result = n_reference(p, first, adj)
    assert result.endpoint.unresolved_reason == "machine_endpoint_not_unique"
    assert {item.period_status for item in result.defensible.alternatives} == {"finite", "none"}


def test_finite_period_with_unknown_end_and_empty_unresolved_reading_stay_unknown():
    p = protocol()
    first = firsts(p)
    partial = reading(option(end=None, quote="2028-03-14"))
    adj = adjudication(p, NOTICE, "N", first, value={"reference": partial, "rationale": "End remains unknown."})
    result = n_reference(p, first, adj)
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert result.defensible.alternatives[0].start == date(2028, 3, 1)
    empty = reading(reason="no defensible interpretation recorded")
    adj = adjudication(p, NOTICE, "N", first, value={"reference": empty, "rationale": "Retain unknown."})
    result = n_reference(p, first, adj)
    assert result.defensible.alternatives == ()
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert result.defensible.unresolved_reason == "no defensible interpretation recorded"


def test_hallucinated_quote_is_preserved_but_cannot_resolve_the_endpoint():
    p = protocol()
    first = firsts(p)
    fabricated = reading(option(quote="not in the invented notice"))
    adj = adjudication(p, NOTICE, "N", first, value={"reference": fabricated, "rationale": "Recorded evidence."})
    result = n_reference(p, first, adj)
    assert adj.status is ParseStatus.VALID
    assert result.defensible.alternatives[0].quote == "not in the invented notice"
    assert result.defensible.alternatives[0].quote_valid is False
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert result.state is ReferenceState.UNRESOLVED


def test_missing_or_failed_first_pass_prevents_adjudication_from_upgrading_the_process():
    p = protocol()
    first = firsts(p, left=RawAnswer("unavailable", None, None, "invented network absence"))
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    assert result.first_agreement is Agreement.UNKNOWN and result.state is ReferenceState.UNRESOLVED
    assert result.defensible.alternatives[0].end == date(2028, 3, 14)
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert "machine_first_M1_unavailable" in result.reasons
    shown = adj.request.payload["first_passes"][0]
    assert shown == {"judge_code": "M1", "status": "unavailable"}
    assert "invented network absence" not in adj.request.visible_json


def test_failed_adjudication_retains_raw_answer_but_is_not_a_reference():
    p = protocol()
    first = firsts(p)
    adj = adjudication(p, NOTICE, "N", first, value=RawAnswer("returned", "{", "stop", None))
    result = n_reference(p, first, adj)
    assert result.state is ReferenceState.UNRESOLVED and result.defensible is None
    assert result.adjudication.answer.content == "{"
    assert "machine_adjudication_invalid_json" in result.reasons


def test_unavailable_or_blocked_adjudication_does_not_invent_exposure():
    p = protocol()
    first = firsts(p)
    unavailable = adjudication(p, NOTICE, "N", first, value=RawAnswer("unavailable", None, None, "not returned"))
    assert unavailable.other_judgments_seen is None
    assert n_reference(p, first, unavailable).state is ReferenceState.UNRESOLVED
    blocked = adjudication(p, NOTICE, "N", first, value=RawAnswer("cap_blocked", None, None, "not attempted"))
    assert blocked.other_judgments_seen is False
    with pytest.raises(ValueError, match="exposure"):
        submit(p, unavailable.request, unavailable.answer, judgment_id="invented-exposure",
               submitted=T0 + timedelta(seconds=5), other_judgments_seen=True)


def test_c_specified_pass_is_after_both_first_submissions_and_uses_the_pinned_block():
    p = protocol()
    first = firsts(p, cohort="C")
    with pytest.raises(ValueError, match="follow all"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified",
                        shown_utc=T0 + timedelta(seconds=1), first_passes=first, condition_block=BLOCK)
    with pytest.raises(ValueError, match="pinned hash"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified",
                        shown_utc=T0 + timedelta(seconds=2), first_passes=first, condition_block="changed")
    with pytest.raises(ValueError, match="exactly two"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified",
                        shown_utc=T0 + timedelta(seconds=2), first_passes=first[:1], condition_block=BLOCK)
    second = specified(p, first)
    for item in second:
        assert item.request.payload == {**NOTICE.visible(), "condition_block": BLOCK}
        assert "first_passes" not in item.request.payload
        assert item.request.sources == first
    assert all("condition_block" not in item.request.payload for item in first)


def test_c_cannot_show_the_block_after_an_unavailable_first_pass():
    p = protocol()
    first = firsts(p, cohort="C", left=RawAnswer("unavailable", None, None, "not returned"))
    with pytest.raises(ValueError, match="both first passes"):
        specified(p, first)
    result = c_reference(p, first)
    assert result.state is ReferenceState.UNRESOLVED and result.specified_passes == ()
    assert result.specified_agreement is Agreement.UNKNOWN
    assert {"machine_specified_M1_missing", "machine_specified_M2_missing"} <= set(result.reasons)


def test_c_partial_specified_collection_remains_explicitly_unresolved():
    p = protocol()
    first = firsts(p, cohort="C")
    second = specified(p, first)
    result = c_reference(p, first, second[:1])
    assert result.specified_passes == second[:1]
    assert result.specified_agreement is Agreement.UNKNOWN and result.state is ReferenceState.UNRESOLVED
    assert result.convention_target.unresolved_reason == "machine_process_incomplete"
    adj = adjudication(p, NOTICE, "C", first, second=second[:1])
    result = c_reference(p, first, second[:1], adj)
    assert "machine_specified_M2_missing" in result.reasons
    assert result.specified.alternatives and result.convention_target.end is None


def test_c_reconciliation_preserves_both_stages_and_multiple_defensible_readings():
    p = protocol()
    first = firsts(p, cohort="C", left=reading(option()), right=reading(option(end="2028-03-21")))
    second = specified(p, first)
    choice = {"defensible": reading(option(), option(end="2028-03-21")), "specified": reading(option()),
              "rationale": "The convention selects one interpretation."}
    adj = adjudication(p, NOTICE, "C", first, second=second, value=choice)
    result = c_reference(p, first, second, adj)
    assert result.state is ReferenceState.UNRESOLVED
    assert result.first_agreement is Agreement.DISAGREED and result.specified_agreement is Agreement.AGREED
    assert len(result.defensible.alternatives) == 2 and len(result.specified.alternatives) == 1
    assert result.endpoint.unresolved_reason == "machine_process_incomplete"
    assert result.convention_target.end is None
    assert "machine_first_semantic_disagreement" in result.reasons
    assert set(adj.request.payload) == {"material", "first_passes", "specified_passes", "condition_block"}
    assert result.first_passes == first and result.specified_passes == second


def test_c_nonunique_specified_target_is_not_chosen_by_order_or_majority():
    p = protocol()
    first = firsts(p, cohort="C")
    options = reading(option(), option(end="2028-03-21"))
    second = specified(p, first, left=options, right=options)
    choice = {"defensible": reading(option()), "specified": reading(option(), option(end="2028-03-21")),
              "rationale": "The rule target remains ambiguous."}
    adj = adjudication(p, NOTICE, "C", first, second=second, value=choice)
    result = c_reference(p, first, second, adj)
    assert result.state is ReferenceState.PARTIAL
    assert result.convention_target.unresolved_reason == "machine_specified_target_not_unique"
    assert len(result.specified.alternatives) == 2


def test_c_same_endpoint_with_different_statement_types_is_not_a_unique_specified_target():
    p = protocol()
    first = firsts(p, cohort="C")
    options = reading(option(), option(statement="next_delivery"))
    second = specified(p, first, left=options, right=options)
    choice = {"defensible": reading(option()), "specified": reading(option(), option(statement="next_delivery")),
              "rationale": "Type remains ambiguous."}
    adj = adjudication(p, NOTICE, "C", first, second=second, value=choice)
    result = c_reference(p, first, second, adj)
    assert result.convention_target.unresolved_reason == "machine_specified_target_not_unique"
    assert len(result.specified.alternatives) == 2


def test_c_target_can_be_known_even_when_certainty_is_unknown():
    p = protocol()
    first = firsts(p, cohort="C")
    second = specified(p, first)
    choice = {"defensible": reading(option()), "specified": reading(option(certainty=None)),
              "rationale": "Interval is known; certainty is not."}
    adj = adjudication(p, NOTICE, "C", first, second=second, value=choice)
    result = c_reference(p, first, second, adj)
    assert result.state is ReferenceState.UNRESOLVED
    assert result.convention_target.end is None
    assert result.specified.alternatives[0].end == date(2028, 3, 14)


def test_c_returned_parse_failure_is_not_fixed_by_a_later_adjudication():
    p = protocol()
    first = firsts(p, cohort="C", left=RawAnswer("returned", "{", "stop", None))
    second = specified(p, first)
    adj = adjudication(p, NOTICE, "C", first, second=second)
    result = c_reference(p, first, second, adj)
    assert result.state is ReferenceState.UNRESOLVED
    assert result.convention_target.unresolved_reason == "machine_process_incomplete"
    assert result.adjudication.result.specified.alternatives


def test_c_cannot_mix_first_passes_or_duplicate_judgment_ids():
    p = protocol()
    first = firsts(p, cohort="C")
    second = specified(p, first)
    changed_first = (replace(first[0], judgment_id="replacement-id"), first[1])
    with pytest.raises(ValueError, match="these first passes"):
        c_reference(p, changed_first, second)
    duplicate = replace(second[0], judgment_id=first[0].judgment_id)
    with pytest.raises(ValueError, match="distinct"):
        c_reference(p, first, (duplicate, second[1]))


def test_adjudication_must_follow_and_bind_exactly_the_source_passes():
    p = protocol()
    first = firsts(p)
    with pytest.raises(ValueError, match="follow all"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                        shown_utc=T0 + timedelta(seconds=1), first_passes=first)
    adj = adjudication(p, NOTICE, "N", first)
    changed_first = (replace(first[0], judgment_id="new-source"), first[1])
    with pytest.raises(ValueError, match="exact earlier passes"):
        n_reference(p, changed_first, adj)
    duplicate = replace(adj, judgment_id=first[0].judgment_id)
    with pytest.raises(ValueError, match="distinct"):
        n_reference(p, first, duplicate)


def test_tampered_parse_or_different_protocol_cannot_enter_reconciliation():
    p = protocol()
    first = firsts(p)
    forged = replace(first[0], result=first[1].result, status=ParseStatus.TRUNCATED)
    with pytest.raises(ValueError, match="parsed judgment was altered"):
        n_reference(p, (forged, first[1]))
    other = replace(p, protocol_id="different-draft")
    with pytest.raises(ValueError, match="altered|identity|match"):
        n_reference(other, first)
    with pytest.raises(ValueError, match="pinned protocol"):
        reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v2", first_passes=first)


def test_role_validity_requires_explicit_madj_and_is_not_human_validation():
    p, material = protocol(), role_set()
    first = firsts(p, material, "R")
    before = r_reference(p, material, first)
    assert before.first_agreement is Agreement.AGREED and before.validity is MachineValidity.UNRESOLVED
    adj = adjudication(p, material, "R", first)
    result = r_reference(p, material, first, adj)
    assert result.validity is MachineValidity.VALID
    assert result.validity.value == "machine_valid_adjudicated"
    assert result.first_passes == first and result.adjudication == adj
    assert not isinstance(result, ValidationDecision)


def test_role_disagreement_and_madj_rejection_are_preserved():
    p, material = protocol(), role_set()
    bad = role_reading(material, valid=False, reason="invented material defect")
    first = firsts(p, material, "R", right=bad)
    adj = adjudication(p, material, "R", first, value={"reference": bad, "rationale": "Defect remains."})
    result = r_reference(p, material, first, adj)
    assert result.first_agreement is Agreement.DISAGREED
    assert result.validity is MachineValidity.UNRESOLVED
    assert "machine_first_semantic_disagreement" in result.reasons
    assert result.first_passes[0].result.material_valid is True
    assert result.first_passes[1].result.reason == "invented material defect"
    assert result.decision.reason == "invented material defect"


def test_role_madj_can_explicitly_disagree_without_erasing_first_passes():
    p, material = protocol(), role_set()
    bad = role_reading(material, valid=False, reason="invented concern")
    first = firsts(p, material, "R", left=bad, right=bad)
    adj = adjudication(p, material, "R", first)
    result = r_reference(p, material, first, adj)
    assert result.first_agreement is Agreement.AGREED and result.validity is MachineValidity.UNRESOLVED
    assert "machine_adjudication_semantic_disagreement" in result.reasons
    assert all(item.result.material_valid is False for item in result.first_passes)
    assert result.decision.material_valid is True


@pytest.mark.parametrize("case,expected_reason", [
    ("unknown_validity", "machine_material_validity_unknown"),
    ("unknown_check", "machine_validity_conflicts_with_checks"),
    ("false_check", "machine_validity_conflicts_with_checks"),
    ("unknown_target", "machine_role_target_unresolved"),
    ("ambiguous_target", "machine_role_target_unresolved"),
    ("invalid_quote", "machine_role_target_unresolved"),
    ("different_targets", "machine_role_targets_differ"),
    ("unknown_date_role", "machine_date_role_unresolved"),
    ("invalid_role_quote", "machine_date_role_unresolved"),
    ("missing_date_roles", "machine_date_roles_incomplete"),
    ("ambiguous_date_role", "machine_date_role_not_unique"),
    ("conflicting_current_role", "machine_date_role_conflicts_with_target"),
    ("incoherent_chronology", "machine_role_chronology_conflict"),
])
def test_role_unknowns_conflicts_and_alternatives_cannot_become_machine_valid(case, expected_reason):
    p, material = protocol(), role_set()
    first = firsts(p, material, "R")
    value = role_reading(material)
    if case == "unknown_validity":
        value["material_valid"], value["reason"] = None, "unresolved material"
    elif case == "unknown_check":
        value["checks"]["coherent_chronology"] = None
    elif case == "false_check":
        value["checks"]["coherent_chronology"] = False
    elif case == "unknown_target":
        value["targets"][0].update(status="unresolved", target_date=None, quote="",
                                   alternatives=["2028-03-14", "2028-02-10"])
    elif case == "ambiguous_target":
        value["targets"][0]["alternatives"] = ["2028-02-10"]
    elif case == "invalid_quote":
        value["targets"][0]["quote"] = "Current recovery"
    elif case == "different_targets":
        value["targets"][0].update(target_date="2028-02-10", quote="Next review 2028-02-10")
    elif case == "unknown_date_role":
        value["targets"][0]["date_roles"][0]["role"] = None
    elif case == "invalid_role_quote":
        value["targets"][0]["date_roles"][0]["quote"] = "not present"
    elif case == "missing_date_roles":
        value["targets"][0]["date_roles"] = []
    elif case == "ambiguous_date_role":
        value["targets"][0]["date_roles"].append(
            {"role": "publication", "date": "2028-01-10", "quote": "Superseded recovery 2028-01-10"})
    elif case == "conflicting_current_role":
        value["targets"][0]["date_roles"].append(
            {"role": "current_recovery", "date": "2028-02-10", "quote": "Next review 2028-02-10"})
    elif case == "incoherent_chronology":
        value["targets"][0]["date_roles"][0].update(
            date="2028-01-10", quote="Superseded recovery 2028-01-10")
    adj = adjudication(p, material, "R", first, value={"reference": value, "rationale": "Retain the uncertainty."})
    result = r_reference(p, material, first, adj)
    assert adj.status is ParseStatus.VALID
    assert result.validity is MachineValidity.UNRESOLVED and expected_reason in result.reasons
    if case == "unknown_target":
        assert result.decision.targets[0].alternatives == (date(2028, 3, 14), date(2028, 2, 10))


def test_role_first_pass_unknown_is_not_counted_as_agreement():
    p, material = protocol(), role_set()
    value = role_reading(material, valid=None, reason="target uncertain")
    value["checks"]["unique_current_target"] = None
    first = firsts(p, material, "R", left=value, right=value)
    assert r_reference(p, material, first).first_agreement is Agreement.UNKNOWN


def test_rejected_role_with_unknown_date_roles_does_not_create_full_agreement():
    p, material = protocol(), role_set()
    value = role_reading(material, valid=False, reason="material not confirmed")
    value["targets"][0]["date_roles"][0]["role"] = None
    first = firsts(p, material, "R", left=value, right=value)
    assert r_reference(p, material, first).first_agreement is Agreement.UNKNOWN


def test_role_dated_roles_must_stay_consistent_across_the_four_variants():
    p, original = protocol(), role_set()
    material = replace(original, notices=tuple(
        replace(notice, notice_text=notice.notice_text + " Captured 2027-12-02.") for notice in original.notices
    ))
    first = firsts(p, material, "R")
    changed = role_reading(material)
    changed["targets"][0]["date_roles"][0].update(date="2027-12-02", quote="Captured 2027-12-02")
    adj = adjudication(p, material, "R", first, value={"reference": changed, "rationale": "Record the mismatch."})
    result = r_reference(p, material, first, adj)
    assert result.validity is MachineValidity.UNRESOLVED
    assert "machine_role_dates_differ_across_variants" in result.reasons


def test_role_group_with_inconsistent_update_dates_cannot_be_machine_valid():
    p, original = protocol(), role_set()
    material = replace(original, notices=(replace(original.notices[0], update_date=date(2028, 1, 16)),
                                          *original.notices[1:]))
    first = firsts(p, material, "R")
    adj = adjudication(p, material, "R", first)
    result = r_reference(p, material, first, adj)
    assert result.validity is MachineValidity.UNRESOLVED
    assert "machine_update_dates_differ" in result.reasons


def test_role_agreement_ignores_only_order_not_recorded_evidence():
    p, material = protocol(), role_set()
    left = role_reading(material)
    right = copy.deepcopy(left)
    right["targets"].reverse()
    for target in right["targets"]:
        target["date_roles"].reverse()
    first = firsts(p, material, "R", left=left, right=right)
    assert r_reference(p, material, first).first_agreement is Agreement.AGREED
    right["targets"][0]["quote"] = "2028-03-14"
    first = firsts(p, material, "R", left=left, right=right)
    result = r_reference(p, material, first)
    assert result.first_agreement is Agreement.AGREED
    assert result.first_quote_agreement is Agreement.DISAGREED


@pytest.mark.parametrize("case", [
    "missing_variant", "duplicate_variant", "unknown_variant", "missing_check", "nonbool_check",
    "nonbool_validity", "unexplained_unknown", "invalid_date", "extra_target_field", "duplicate_alternative",
])
def test_role_schema_refuses_partial_or_malformed_structures(case):
    p, material = protocol(), role_set()
    value = role_reading(material)
    if case == "missing_variant":
        value["targets"].pop()
    elif case == "duplicate_variant":
        value["targets"][1] = copy.deepcopy(value["targets"][0])
    elif case == "unknown_variant":
        value["targets"][0]["variant_id"] = "V" + "f" * 20
    elif case == "missing_check":
        del value["checks"]["coherent_chronology"]
    elif case == "nonbool_check":
        value["checks"]["coherent_chronology"] = 1
    elif case == "nonbool_validity":
        value["material_valid"] = 1
    elif case == "unexplained_unknown":
        value["material_valid"] = None
    elif case == "invalid_date":
        value["targets"][0]["target_date"] = "2028-02-30"
    elif case == "extra_target_field":
        value["targets"][0]["extra"] = "not accepted"
    elif case == "duplicate_alternative":
        value["targets"][0]["alternatives"] = ["2028-02-10", "2028-02-10"]
    request = prepare_request(p, material, judge_code="M1", cohort="R", stage="role", shown_utc=T0)
    judgment = submit(p, request, value, judgment_id="invalid-role")
    assert judgment.status is ParseStatus.INVALID_SCHEMA and judgment.result is None


def test_role_failed_first_pass_cannot_be_promoted_by_valid_adjudication():
    p, material = protocol(), role_set()
    first = firsts(p, material, "R", left=RawAnswer("cap_blocked", None, None, "invented cap"))
    adj = adjudication(p, material, "R", first)
    result = r_reference(p, material, first, adj)
    assert result.validity is MachineValidity.UNRESOLVED
    assert result.first_agreement is Agreement.UNKNOWN
    assert result.decision.material_valid is True
    assert "machine_first_M1_cap_blocked" in result.reasons


def registration_records(p):
    registration = LaterRegistration(
        "later-invented-registration", p.sha256, digest("implementation"), digest("material-plan"),
        digest("registration-record"), "a" * 40, T0, T0 + timedelta(seconds=1), T0 + timedelta(seconds=2),
        p.role_alias_commitment_sha256, p.role_seed_manifest_sha256,
    )
    verification = RegistrationVerification("a" * 40, digest("registration-record"), digest("implementation"),
                                            T0 + timedelta(seconds=3), True)
    return registration, verification


def registration_check(p, registration, verification, **changes):
    values = dict(registration=registration, verification=verification, implementation_sha256=digest("implementation"),
                  material_plan_sha256=digest("material-plan"), first_real_activity_utc=T0 + timedelta(seconds=4),
                  evaluation_utc=T0 + timedelta(seconds=5))
    values.update(changes)
    return check_later_registration_claim(p, **values)


def test_separate_registration_claim_requires_later_external_verification_before_real_activity():
    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    assert registration_check(p, registration, verification) is None
    assert registration_check(p, registration, verification, evaluation_utc=None) is None
    with pytest.raises(ValueError, match="registration and external verification"):
        registration_check(p, None, verification)
    with pytest.raises(ValueError, match="registration and external verification"):
        registration_check(p, registration, None)
    with pytest.raises(ValueError, match="separate identity"):
        registration_check(p, replace(registration, registration_id=p.protocol_id), verification)
    with pytest.raises(ValueError, match="precede all real activity"):
        registration_check(p, registration, verification, first_real_activity_utc=T0 + timedelta(seconds=3))
    with pytest.raises(ValueError, match="precede all real activity"):
        registration_check(p, registration, verification, evaluation_utc=T0 + timedelta(seconds=3))


@pytest.mark.parametrize("field,value", [
    ("protocol_sha256", digest("different-protocol")),
    ("implementation_sha256", digest("different-code")),
    ("material_plan_sha256", digest("different-material-plan")),
    ("record_sha256", digest("different-registration")),
    ("commit_sha", "b" * 40),
    ("role_alias_commitment_sha256", digest("different-role-commitment")),
    ("role_seed_manifest_sha256", digest("different-role-manifest")),
])
def test_registration_is_bound_to_protocol_implementation_materials_record_and_commit(field, value):
    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    with pytest.raises(ValueError, match="identities do not match"):
        registration_check(p, replace(registration, **{field: value}), verification)


def test_registration_verification_is_not_inferred_from_a_claim():
    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    with pytest.raises(ValueError, match="identities do not match"):
        registration_check(p, registration, replace(verification, pushed=False))
    with pytest.raises(ValueError, match="identities do not match"):
        registration_check(p, registration, replace(verification, implementation_sha256=digest("other")))
    with pytest.raises(ValueError, match="full lowercase"):
        replace(registration, commit_sha="abc123")
    with pytest.raises(ValueError, match="UTC"):
        replace(registration, recorded_utc=T0.replace(tzinfo=None))
    with pytest.raises(ValueError, match="follow the implementation freeze"):
        replace(registration, implementation_frozen_utc=registration.recorded_utc)
    with pytest.raises(ValueError, match="before it is recorded"):
        replace(registration, pushed_utc=T0)


def test_real_scope_is_disabled_even_with_a_matching_registration_claim():
    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    authorization = RegisteredUse(registration, verification, digest("implementation"), digest("material-plan"),
                                  T0 + timedelta(seconds=4))
    request_values = dict(judge_code="M1", cohort="N", stage="natural", shown_utc=T0 + timedelta(seconds=4))
    assert registration_check(p, registration, verification) is None
    with pytest.raises(ValueError, match="real use is disabled"):
        prepare_request(p, NOTICE, **request_values)
    with pytest.raises(ValueError, match="real use is disabled"):
        prepare_request(p, NOTICE, authorization=authorization, **request_values)
    with pytest.raises(ValueError, match="real use is disabled"):
        reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=())
    with pytest.raises(ValueError, match="real use is disabled"):
        reconcile_role(p, role_set(), reference_version="invented-v1", first_passes=())
    with pytest.raises(ValueError, match="synthetic requests"):
        prepare_request(protocol(), NOTICE, authorization=authorization, **request_values)
    synthetic = protocol()
    fake_registration, fake_verification = registration_records(synthetic)
    with pytest.raises(ValueError, match="synthetic protocol"):
        registration_check(synthetic, fake_registration, fake_verification)


def test_multiple_real_scope_registration_claims_do_not_enable_requests():
    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    first_auth = RegisteredUse(registration, verification, digest("implementation"), digest("material-plan"),
                               T0 + timedelta(seconds=4))
    other_registration = replace(registration, registration_id="another-registration", commit_sha="b" * 40,
                                 record_sha256=digest("another-record"))
    other_verification = replace(verification, commit_sha="b" * 40, record_sha256=digest("another-record"))
    second_auth = replace(first_auth, registration=other_registration, verification=other_verification)
    for code, authorization in (("M1", first_auth), ("M2", second_auth)):
        with pytest.raises(ValueError, match="real use is disabled"):
            prepare_request(p, NOTICE, judge_code=code, cohort="N", stage="natural",
                            shown_utc=T0 + timedelta(seconds=4), authorization=authorization)


def test_registered_scope_c_remains_disabled():
    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    authorization = RegisteredUse(registration, verification, digest("implementation"), digest("material-plan"),
                                  T0 + timedelta(seconds=4))
    with pytest.raises(ValueError, match="real use is disabled"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="unspecified",
                        shown_utc=T0 + timedelta(seconds=4), authorization=authorization)


def clone_as(value, subclass):
    cloned = object.__new__(subclass)
    for field in fields(value):
        object.__setattr__(cloned, field.name, getattr(value, field.name))
    return cloned


def test_untrusted_notice_and_protocol_subclasses_cannot_supply_or_hide_visible_fields():
    class ForgedNotice(BlindNotice):
        def visible(self):
            return {"notice_text": "substituted", "evaluated_output": "not permitted"}

        def __eq__(self, other):
            return True

    class ForgedProtocol(MachineProtocol):
        def binding(self, *args):
            return protocol().bindings[0]

        @property
        def sha256(self):
            return digest("forged")

        def __eq__(self, other):
            return True

    p = protocol()
    with pytest.raises(TypeError, match="material"):
        prepare_request(p, clone_as(NOTICE, ForgedNotice), judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    with pytest.raises(TypeError, match="exact MachineProtocol"):
        prepare_request(clone_as(p, ForgedProtocol), NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)


def test_untrusted_requests_and_judgments_cannot_override_equality_or_revalidation():
    class ForgedRequest(BlindRequest):
        def __eq__(self, other):
            return True

    class ForgedJudgment(MachineJudgment):
        def __eq__(self, other):
            return True

    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    fake_request = clone_as(request, ForgedRequest)
    with pytest.raises(TypeError, match="exact BlindRequest"):
        submit(p, fake_request, reading(option()), judgment_id="invented-forgery")
    first = firsts(p)
    fake_judgment = clone_as(first[0], ForgedJudgment)
    with pytest.raises(TypeError, match="exact MachineJudgment"):
        n_reference(p, (fake_judgment, first[1]))
    with pytest.raises(TypeError, match="exact MachineJudgment"):
        adjudication(p, NOTICE, "N", (fake_judgment, first[1]))


def test_nested_exact_records_are_revalidated_after_mutation():
    p = protocol()
    altered_judge = replace(p.judges[0])
    object.__setattr__(altered_judge, "provider_route", "auto")
    altered_protocol = replace(p)
    object.__setattr__(altered_protocol, "judges", (altered_judge, *p.judges[1:]))
    with pytest.raises(ValueError, match="pinned"):
        prepare_request(altered_protocol, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    first = firsts(p)
    altered_answer = replace(first[0].answer)
    object.__setattr__(altered_answer, "finish_reason", "length")
    altered_judgment = replace(first[0])
    object.__setattr__(altered_judgment, "answer", altered_answer)
    with pytest.raises(ValueError, match="parsed judgment was altered"):
        n_reference(p, (altered_judgment, first[1]))


def test_string_subclasses_and_nested_notice_subclasses_are_not_trusted():
    class MatchingText(str):
        def __eq__(self, other):
            return True

        __hash__ = str.__hash__

    class ForgedNotice(BlindNotice):
        def __eq__(self, other):
            return True

    with pytest.raises(TypeError, match="exact str"):
        BlindNotice("invented", date(2028, 1, 15), MatchingText("invented text"))
    material = role_set()
    fake = clone_as(material.notices[0], ForgedNotice)
    with pytest.raises(ValueError, match="four notices"):
        replace(material, notices=(fake, *material.notices[1:]))


def test_registration_subclasses_and_mutated_nested_records_are_not_trusted():
    class ForgedRegistration(LaterRegistration):
        def __eq__(self, other):
            return True

    class ForgedVerification(RegistrationVerification):
        def __eq__(self, other):
            return True

    p = replace(protocol(), data_scope="real")
    registration, verification = registration_records(p)
    with pytest.raises(TypeError, match="exact LaterRegistration"):
        registration_check(p, clone_as(registration, ForgedRegistration), verification)
    with pytest.raises(TypeError, match="exact RegistrationVerification"):
        registration_check(p, registration, clone_as(verification, ForgedVerification))
    poisoned = replace(registration)
    object.__setattr__(poisoned, "record_sha256", "not-a-hash")
    with pytest.raises(ValueError, match="SHA256"):
        registration_check(p, poisoned, verification)


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
@pytest.mark.parametrize("cohort,stage", [("N", "natural"), ("C", "unspecified")])
def test_every_ordinary_notice_with_an_nfkc_at_sign_is_refused(symbol, cohort, stage):
    p = protocol()
    notice = replace(NOTICE, notice_text=NOTICE.notice_text + " Invented contact " + symbol + " address.")
    with pytest.raises(ValueError, match="at-sign"):
        notice.visible()
    with pytest.raises(ValueError, match="at-sign"):
        prepare_request(p, notice, judge_code="M1", cohort=cohort, stage=stage, shown_utc=T0)


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
def test_role_payload_with_an_nfkc_at_sign_is_refused(symbol):
    p, material = protocol(), role_set()
    bad = replace(material.notices[0], notice_text=material.notices[0].notice_text + " " + symbol)
    material = replace(material, notices=(bad, *material.notices[1:]))
    with pytest.raises(ValueError, match="at-sign"):
        prepare_request(p, material, judge_code="M1", cohort="R", stage="role", shown_utc=T0)


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
def test_pinned_convention_material_with_an_nfkc_at_sign_is_refused(symbol):
    block = "Invented convention " + symbol + " text"
    base = protocol()
    bindings = tuple(replace(item, condition_sha256=digest(block)) if item.condition_sha256 is not None else item
                     for item in base.bindings)
    p = replace(base, bindings=bindings)
    first = firsts(p, cohort="C")
    with pytest.raises(ValueError, match="at-sign"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified",
                        shown_utc=T0 + timedelta(seconds=2), first_passes=first, condition_block=block)


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
def test_prior_unresolved_free_text_is_replaced_with_a_fixed_status(symbol):
    p = protocol()
    first = firsts(p, left=reading(option(), reason="invented unresolved " + symbol))
    assert first[0].status is ParseStatus.VALID
    adj = adjudication(p, NOTICE, "N", first)
    view = adj.request.payload["first_passes"][0]["reading"]
    assert view["unresolved_status"] == "reported" and "unresolved_reason" not in view
    assert "invented unresolved" not in adj.request.visible_json and symbol not in adj.request.visible_json
    result = n_reference(p, first, adj)
    assert result.first_passes[0].result.unresolved_reason.endswith(symbol)
    assert result.state is ReferenceState.UNRESOLVED


def test_invalid_prior_quotes_are_retained_but_never_forwarded_or_silently_redacted():
    p = protocol()
    first = firsts(p, left=reading(option(quote="invented quote absent from source")))
    assert first[0].result.alternatives[0].quote_valid is False
    with pytest.raises(ValueError, match="invalid source quotes"):
        adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first)
    assert result.first_passes[0].result.alternatives[0].quote == "invented quote absent from source"
    assert result.state is ReferenceState.UNRESOLVED
    material = role_set()
    invalid = role_reading(material)
    invalid["targets"][0]["date_roles"][0]["quote"] = "not in the source"
    role_first = firsts(p, material, "R", left=invalid)
    with pytest.raises(ValueError, match="invalid source quotes"):
        adjudication(p, material, "R", role_first)
    assert role_first[0].result.targets[0].date_roles[0].quote == "not in the source"


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
def test_invalid_source_quote_with_nfkc_at_sign_is_explicitly_refused(symbol):
    p = protocol()
    quote = "invented unsupported " + symbol + " quote"
    first = firsts(p, left=reading(option(quote=quote)))
    assert first[0].result.alternatives[0].quote_valid is False
    with pytest.raises(ValueError, match="at-sign"):
        adjudication(p, NOTICE, "N", first)
    assert first[0].result.alternatives[0].quote == quote


@pytest.mark.parametrize("marker", ["[REDACTED]", "<removed>", "████", "***"])
def test_recognizable_redacted_source_quotes_are_not_forwarded(marker):
    p = protocol()
    notice = replace(NOTICE, notice_text=NOTICE.notice_text + " " + marker)
    quoted = reading(option(quote=notice.notice_text))
    first = firsts(p, notice, "N", left=quoted, right=quoted)
    assert first[0].result.alternatives[0].quote_valid is True
    with pytest.raises(ValueError, match="redacted source quotes"):
        adjudication(p, notice, "N", first)
    result = reconcile_readings(p, notice, cohort="N", reference_version="invented-v1", first_passes=first)
    assert result.first_passes[0].result.alternatives[0].quote.endswith(marker)
    assert result.state is ReferenceState.UNRESOLVED


def test_observed_identity_binds_protocol_private_subject_material_and_attempt():
    p = protocol()
    first = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0,
                            attempt_id="attempt-original")
    observed = assigned_identity(p, first)
    other_notice = replace(NOTICE, item_id="invented-other-subject")
    other = prepare_request(p, other_notice, judge_code="M1", cohort="N", stage="natural", shown_utc=T0,
                            attempt_id="attempt-original")
    assert other.input_sha256 == first.input_sha256
    assert assigned_identity(p, other).subject_id != observed.subject_id
    assert assigned_identity(p, other).material_sha256 != observed.material_sha256
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, other, reading(option()), judgment_id="other-subject", observed=observed)
    retry = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0,
                            attempt_id="attempt-different")
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, retry, reading(option()), judgment_id="other-attempt", observed=observed)
    other_protocol = replace(p, protocol_id="different-invented-protocol")
    another = prepare_request(other_protocol, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0,
                              attempt_id="attempt-original")
    assert another.input_sha256 == first.input_sha256
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(other_protocol, another, reading(option()), judgment_id="other-protocol", observed=observed)


@pytest.mark.parametrize("field,value", [
    ("protocol_sha256", digest("other-protocol")), ("subject_id", "other-subject"),
    ("material_sha256", digest("other-material")), ("attempt_id", "other-attempt"),
    ("sources_sha256", digest("other-sources")),
])
def test_observed_identity_rejects_each_new_binding_mismatch(field, value):
    p = protocol()
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    observed = replace(assigned_identity(p, request), **{field: value})
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, request, reading(option()), judgment_id="new-binding-mismatch", observed=observed)


def test_attempt_ids_are_required_and_distinct_within_reconciliation():
    p = protocol()
    with pytest.raises(TypeError, match="attempt_id"):
        _prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    passes = []
    for code in ("M1", "M2"):
        request = prepare_request(p, NOTICE, judge_code=code, cohort="N", stage="natural", shown_utc=T0,
                                  attempt_id="duplicate-attempt")
        passes.append(submit(p, request, reading(option()), judgment_id=f"{code}-distinct-judgment"))
    with pytest.raises(ValueError, match="attempt IDs"):
        n_reference(p, passes)
    first = firsts(p)
    with pytest.raises(ValueError, match="attempt IDs"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                        shown_utc=T0 + timedelta(seconds=4), first_passes=first,
                        attempt_id=first[0].request.attempt_id)


def test_adjudication_identity_also_binds_source_records_when_visible_text_is_equal():
    p = protocol()
    first = firsts(p)
    relabeled = (replace(first[0], judgment_id="different-invented-source"), first[1])
    original = prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                               shown_utc=T0 + timedelta(seconds=4), first_passes=first,
                               attempt_id="same-declared-attempt")
    changed = prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                              shown_utc=T0 + timedelta(seconds=4), first_passes=relabeled,
                              attempt_id="same-declared-attempt")
    assert original.visible_json == changed.visible_json and original.input_sha256 == changed.input_sha256
    assert original.sources_sha256 != changed.sources_sha256
    observed = assigned_identity(p, original)
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, changed, {"reference": reading(option()), "rationale": "Invented proposal."},
               judgment_id="invented-adjudication", submitted=T0 + timedelta(seconds=5), observed=observed)


def test_machine_provenance_survives_endpoint_convention_and_role_summaries():
    p = protocol()
    first = firsts(p)
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    provenance = result.endpoint.provenance
    assert provenance.label == "machine_generated_not_human"
    assert provenance.protocol_sha256 == p.sha256
    assert provenance.material_sha256 == first[0].request.material_sha256
    assert len(provenance.records_sha256) == 64
    assert provenance.subject_id == NOTICE.item_id and provenance.reference_version == p.reference_version
    assert provenance.judgment_ids == tuple(item.judgment_id for item in (*first, adj))
    assert provenance.attempt_ids == tuple(item.request.attempt_id for item in (*first, adj))
    c_first = firsts(p, cohort="C")
    c_second = specified(p, c_first)
    c_adj = adjudication(p, NOTICE, "C", c_first, second=c_second)
    c = c_reference(p, c_first, c_second, c_adj)
    assert c.convention_target.provenance.label == "machine_generated_not_human"
    assert c.convention_target.provenance.cohort == "C"
    material = role_set()
    r_first = firsts(p, material, "R")
    r_adj = adjudication(p, material, "R", r_first)
    r = r_reference(p, material, r_first, r_adj)
    assert revalidate_role(r) is None
    assert r.provenance.label == "machine_generated_not_human" and r.provenance.subject_id == material.group_id


def test_detached_endpoint_replacement_is_rejected_and_exports_are_labelled_untrusted():
    p = protocol()
    first = firsts(p)
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    endpoint = result.endpoint
    with pytest.raises(TypeError):
        replace(endpoint, end=date(2099, 1, 1))
    with pytest.raises(TypeError):
        asdict(endpoint)
    serialized = endpoint.export()
    assert serialized["machine_reference_label"] == "machine_generated_not_human"
    assert serialized["detached_value_status"] == "untrusted_detached_serialization"
    assert serialized["semantic_truth"] == "not_verified"
    assert serialized["real_use_authorized"] is False
    assert serialized["date_evidence"] == "literal_iso_cooccurrence_only"
    assert endpoint.semantic_truth == "not_verified" and endpoint.date_evidence == "literal_iso_cooccurrence_only"
    assert serialized["provenance"]["label"] == "machine_generated_not_human"
    assert asdict(endpoint.provenance)["label"] == "machine_generated_not_human"
    assert asdict(endpoint.provenance)["use_status"] == "synthetic_claim_only_not_authorized"
    assert json.loads(endpoint.export_json())["semantic_truth"] == "not_verified"
    with pytest.raises(ValueError, match="init=False"):
        replace(endpoint.provenance, label="other")
    serialized["end"] = "2099-01-01"
    assert endpoint.end == date(2028, 3, 14)
    assert endpoint.export()["end"] == "2028-03-14"
    with pytest.raises(TypeError, match="exact ReconciledReadings"):
        revalidate_readings(serialized)


def test_detached_convention_target_cannot_retain_provenance_after_replacement():
    p = protocol()
    first = firsts(p, cohort="C")
    second = specified(p, first)
    adj = adjudication(p, NOTICE, "C", first, second=second)
    target = c_reference(p, first, second, adj).convention_target
    with pytest.raises(TypeError):
        replace(target, end=date(2099, 1, 1))
    serialized = target.export()
    assert serialized["machine_reference_label"] == "machine_generated_not_human"
    assert serialized["provenance"]["label"] == "machine_generated_not_human"
    assert serialized["semantic_truth"] == "not_verified"
    assert serialized["real_use_authorized"] is False
    assert target.semantic_truth == "not_verified" and target.date_evidence == "literal_iso_cooccurrence_only"
    assert json.loads(target.export_json())["detached_value_status"] == "untrusted_detached_serialization"
    serialized["end"] = "2099-01-01"
    assert target.end == date(2028, 3, 14) and target.export()["end"] == "2028-03-14"


def test_live_endpoint_and_target_rederive_after_parent_changes():
    p = protocol()
    first = firsts(p)
    adj = adjudication(p, NOTICE, "N", first)
    reference = n_reference(p, first, adj)
    endpoint = reference.endpoint
    old_provenance = endpoint.provenance.records_sha256
    object.__setattr__(reference, "adjudication", None)
    assert endpoint.end is None and endpoint.unresolved_reason == "machine_process_incomplete"
    assert endpoint.provenance.records_sha256 != old_provenance
    c_first = firsts(p, cohort="C")
    c_second = specified(p, c_first)
    c_adj = adjudication(p, NOTICE, "C", c_first, second=c_second)
    c_reference_value = c_reference(p, c_first, c_second, c_adj)
    target = c_reference_value.convention_target
    object.__setattr__(c_reference_value, "specified_passes", ())
    with pytest.raises(ValueError, match="exact earlier passes"):
        _ = target.end
    with pytest.raises(ValueError, match="exact earlier passes"):
        target.export_json()


def test_fabricated_final_states_cannot_be_constructed_or_survive_revalidation():
    p = protocol()
    first = firsts(p)
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    with pytest.raises(TypeError):
        replace(result, state=ReferenceState.ADJUDICATED)
    object.__setattr__(result, "first_passes", ())
    with pytest.raises(ValueError, match="exact earlier passes"):
        _ = result.state
    material = role_set()
    r_first = firsts(p, material, "R")
    r_adj = adjudication(p, material, "R", r_first)
    role = r_reference(p, material, r_first, r_adj)
    with pytest.raises(TypeError):
        replace(role, validity=MachineValidity.VALID)
    object.__setattr__(role, "adjudication", None)
    assert role.validity is MachineValidity.UNRESOLVED


def test_reconciled_subclasses_cannot_override_computed_final_states():
    class ForgedReadings(ReconciledReadings):
        def _parts(self):
            return {"state": ReferenceState.ADJUDICATED}

    class ForgedRole(ReconciledRole):
        def _parts(self):
            return {"validity": MachineValidity.VALID}

    p = protocol()
    reading_result = n_reference(p, firsts(p))
    fake_reading = clone_as(reading_result, ForgedReadings)
    with pytest.raises(TypeError, match="exact ReconciledReadings"):
        _ = fake_reading.state
    with pytest.raises(TypeError, match="exact ReconciledReadings"):
        revalidate_readings(fake_reading)
    material = role_set()
    role_result = r_reference(p, material, firsts(p, material, "R"))
    fake_role = clone_as(role_result, ForgedRole)
    with pytest.raises(TypeError, match="exact ReconciledRole"):
        _ = fake_role.validity
    with pytest.raises(TypeError, match="exact ReconciledRole"):
        revalidate_role(fake_role)


def test_fabricated_2099_end_is_not_supported_by_a_different_source_quote():
    p = protocol()
    forged = reading(option(end="2099-01-01", quote=option()["quote"]))
    first = firsts(p, left=forged, right=forged)
    adj = adjudication(p, NOTICE, "N", first, value={"reference": forged, "rationale": "Invented proposal."})
    result = n_reference(p, first, adj)
    proposal = result.defensible.alternatives[0]
    assert proposal.quote_valid is True and proposal.end_support is DateSupport.UNVERIFIED
    assert proposal.end == date(2099, 1, 1)
    assert result.first_agreement is Agreement.AGREED
    assert result.state is ReferenceState.UNRESOLVED and result.endpoint.end is None
    assert {"machine_first_M1_date_support_unverified", "machine_first_M2_date_support_unverified"} <= set(result.reasons)


@pytest.mark.parametrize("quote", ["early March", "recovery is expected early March", "2028-03-140"])
def test_nonliteral_normalization_and_partial_iso_substrings_remain_unverified(quote):
    p = protocol()
    notice = BlindNotice("invented-relative", date(2028, 1, 15),
                         "Invented notice: recovery is expected early March; code 2028-03-140.")
    value = reading(option(quote=quote))
    first = firsts(p, notice, "N", left=value, right=value)
    adj = adjudication(p, notice, "N", first, value={"reference": value, "rationale": "Invented normalization."})
    result = reconcile_readings(p, notice, cohort="N", reference_version="invented-v1",
                                first_passes=first, adjudication=adj)
    assert result.defensible.alternatives[0].end_support is DateSupport.UNVERIFIED
    assert result.endpoint.end is None and result.state is ReferenceState.UNRESOLVED


def test_literal_date_cooccurrence_is_only_lexical_support_not_semantic_truth():
    p = protocol()
    notice = BlindNotice("invented-cooccurrence", date(2028, 1, 15),
                         "Invented notice: review 2028-03-01; filing 2028-03-14; no recovery is stated.")
    value = reading(option(quote=notice.notice_text))
    first = firsts(p, notice, "N", left=value, right=value)
    adj = adjudication(p, notice, "N", first, value={"reference": value, "rationale": "Invented machine claim."})
    result = reconcile_readings(p, notice, cohort="N", reference_version="invented-v1",
                                first_passes=first, adjudication=adj)
    assert result.defensible.alternatives[0].end_support is DateSupport.LITERAL_ISO
    assert result.endpoint.provenance.label == "machine_generated_not_human"
    assert result.endpoint.end == date(2028, 3, 14)
    assert "no recovery is stated" in notice.notice_text
    exported = result.endpoint.export()
    assert exported["date_evidence"] == "literal_iso_cooccurrence_only"
    assert exported["semantic_truth"] == "not_verified"


@pytest.mark.parametrize("present", [0, 1])
def test_missing_n_first_passes_remain_unknown_even_with_an_adjudicator_proposal(present):
    p = protocol()
    first = firsts(p)[:present]
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    assert result.state is ReferenceState.UNRESOLVED and result.endpoint.end is None
    assert result.defensible.alternatives[0].end == date(2028, 3, 14)
    assert "machine_first_M2_missing" in result.reasons
    if present == 0:
        assert "machine_first_M1_missing" in result.reasons
        assert adj.other_judgments_seen is False
    assert len(result.first_passes) == present
    assert sum(item["status"] == "missing" for item in adj.request.payload["first_passes"]) == 2 - present


@pytest.mark.parametrize("present", [0, 1])
def test_missing_c_and_r_first_passes_retain_adjudicator_proposals(present):
    p = protocol()
    first = firsts(p, cohort="C")[:present]
    adj = adjudication(p, NOTICE, "C", first)
    result = c_reference(p, first, (), adj)
    assert result.state is ReferenceState.UNRESOLVED and result.convention_target.end is None
    assert result.defensible.alternatives and result.specified.alternatives
    assert "machine_first_M2_missing" in result.reasons
    assert {"machine_specified_M1_missing", "machine_specified_M2_missing"} <= set(result.reasons)
    material = role_set()
    role_first = firsts(p, material, "R")[:present]
    role_adj = adjudication(p, material, "R", role_first)
    role = r_reference(p, material, role_first, role_adj)
    assert role.validity is MachineValidity.UNRESOLVED and role.decision is not None
    assert "machine_first_M2_missing" in role.reasons


@pytest.mark.parametrize("raw,status", [
    (RawAnswer("returned", "{", "stop", None), "invalid_json"),
    (RawAnswer("returned", "{}", "stop", None), "invalid_schema"),
    (RawAnswer("returned", "{}", "length", None), "truncated"),
    (RawAnswer("unavailable", None, None, "invented unavailable"), "unavailable"),
    (RawAnswer("cap_blocked", None, None, "invented cap"), "cap_blocked"),
])
def test_first_pass_failure_states_stay_distinct_despite_an_adjudicator_proposal(raw, status):
    p = protocol()
    first = firsts(p, left=raw)
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    assert f"machine_first_M1_{status}" in result.reasons
    assert result.state is ReferenceState.UNRESOLVED and result.endpoint.end is None
    assert result.first_passes[0].answer == raw and result.defensible.alternatives


def test_semantic_agreement_is_separate_from_exact_quote_agreement():
    p = protocol()
    left = reading(option())
    right = reading(option(quote=NOTICE.notice_text))
    first = firsts(p, left=left, right=right)
    adj = adjudication(p, NOTICE, "N", first, value={"reference": left, "rationale": "Invented reading."})
    result = n_reference(p, first, adj)
    assert result.first_agreement is Agreement.AGREED
    assert result.first_quote_agreement is Agreement.DISAGREED
    assert result.state is ReferenceState.ADJUDICATED and result.endpoint.end == date(2028, 3, 14)


def test_unpaired_surrogate_keeps_status_and_explicitly_unavailable_text_hash():
    p = protocol()
    raw = RawAnswer("returned", '{"alternatives":[],"unresolved_reason":"\ud800"}', "stop", None)
    assert raw.content_sha256 is None
    assert raw.content_hash_evidence == "invalid_unicode_text_hash_unavailable"
    first = firsts(p, left=raw)
    assert first[0].status is ParseStatus.INVALID_JSON and first[0].answer.content == raw.content
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    assert result.state is ReferenceState.UNRESOLVED and "machine_first_M1_invalid_json" in result.reasons
    ordinary = answer(reading(option()))
    assert ordinary.content_sha256 == digest(ordinary.content)
    assert ordinary.content_hash_evidence == "utf8_text_only_not_transport_bytes"


def generated_role_fixture():
    seed = _make_seed(SYNTHETIC_PRIVATE_SEED, 0, "earlier")
    blinding = role_blinding()
    mapping = blinding.opaque_variant_map()
    by_variant = {variant.item_id: variant for variant in seed.variants}
    notices = tuple(BlindNotice(opaque, by_variant[variant_id].update_date, by_variant[variant_id].notice_text)
                    for opaque, variant_id in mapping)
    return seed, BlindRoleSet(blinding.group_id, notices, blinding), mapping


def generated_role_reading(seed, material, *, target=None):
    target = seed.target_date if target is None else target
    targets = []
    for notice in material.notices:
        competing_role = "next_review" if "Next review" in notice.notice_text else "administrative"
        targets.append({
            "variant_id": notice.item_id, "status": "exact", "target_date": target.isoformat(),
            "alternatives": [], "quote": target.isoformat(), "date_roles": [
                {"role": "publication", "date": seed.publication_date.isoformat(),
                 "quote": seed.publication_date.isoformat()},
                {"role": "superseded_issue", "date": seed.superseded_issue_date.isoformat(),
                 "quote": seed.superseded_issue_date.isoformat()},
                {"role": "superseded_recovery", "date": seed.superseded_target_date.isoformat(),
                 "quote": seed.superseded_target_date.isoformat()},
                {"role": competing_role, "date": seed.competing_date.isoformat(),
                 "quote": seed.competing_date.isoformat()},
            ],
        })
    checks = {name: True for name in (
        "unique_current_target", "coherent_chronology", "competing_role_preserves_target",
        "neutral_role_unrelated", "comparable_length_and_syntax", "position_preserves_meaning",
    )}
    return {"targets": targets, "checks": checks, "material_valid": True, "reason": None}


def generated_role_reference(seed, material, *, target=None):
    p = protocol()
    value = generated_role_reading(seed, material, target=target)
    first = firsts(p, material, "R", left=value, right=value)
    adj = adjudication(p, material, "R", first, value={"reference": value, "rationale": "Invented role reading."})
    return r_reference(p, material, first, adj)


def test_generator_eligibility_rejects_an_unlabelled_superseded_issue_date():
    seed, material, mapping = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    for target in reading["targets"]:
        target["date_roles"] = [role for role in target["date_roles"] if role["role"] != "superseded_issue"]
    p = protocol()
    first = firsts(p, material, "R", left=reading, right=reading)
    adj = adjudication(p, material, "R", first, value={"reference": reading, "rationale": "Invented role reading."})
    reference = r_reference(p, material, first, adj)
    assert reference.validity is MachineValidity.VALID  # Generic validity is not a generator-bound claim.
    eligibility = assess_synthetic_role_eligibility(reference, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.structural_checks_pass
    assert "machine_role_generator_date_roles_unverified" in eligibility.reasons


@pytest.mark.parametrize("which", ["target", "publication", "superseded_issue", "superseded_recovery", "competing"])
@pytest.mark.parametrize("edge,digit", [("prefix", "9"), ("suffix", "9"),
                                        ("prefix", "９"), ("suffix", "٩")])
def test_role_date_evidence_cannot_end_inside_a_longer_source_number(which, edge, digit):
    seed, material, _ = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    day = {"target": seed.target_date, "publication": seed.publication_date,
           "superseded_issue": seed.superseded_issue_date, "superseded_recovery": seed.superseded_target_date,
           "competing": seed.competing_date}[which]
    literal = day.isoformat()
    malformed = digit + literal if edge == "prefix" else literal + digit
    altered = replace(material, notices=tuple(replace(notice, notice_text=notice.notice_text.replace(literal, malformed))
                                               for notice in material.notices))
    parsed = machine_references._parse_roles(reading, altered)
    for item in parsed.targets:
        if which == "target":
            assert item.quote_valid is False
        else:
            labels = {"next_review", "administrative"} if which == "competing" else {which}
            assert next(role for role in item.date_roles if role.role in labels).quote_valid is False
    assert machine_references._role_problem(parsed, altered) == (
        "machine_role_target_unresolved" if which == "target" else "machine_date_role_unresolved"
    )


def test_role_date_evidence_can_use_a_later_standalone_source_occurrence():
    day = date(2028, 3, 14)
    notice = "Invented malformed 2028-03-140 followed by a standalone 2028-03-14."
    assert machine_references._evidence(day.isoformat(), notice, required=True, target=day) is True


@pytest.mark.parametrize("tail,expected", [
    ("unrelated 2028-03-14.", False),
    ("another target 2028-03-14.", True),
])
def test_role_date_evidence_binds_the_standalone_date_to_the_same_quote_occurrence(tail, expected):
    day = date(2028, 3, 14)
    notice = "Invented target 2028-03-149; " + tail
    assert machine_references._evidence("target 2028-03-14", notice, required=True, target=day) is expected


@pytest.mark.parametrize("defect", ["same_as_publication", "after_superseded", "missing_on_one_variant"])
def test_optional_issue_role_must_be_chronological_and_consistent_when_present(defect):
    seed, material, _ = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    for index, target in enumerate(reading["targets"]):
        if defect == "missing_on_one_variant":
            if index == 0:
                target["date_roles"] = [role for role in target["date_roles"] if role["role"] != "superseded_issue"]
        else:
            day = seed.publication_date if defect == "same_as_publication" else seed.target_date
            issue = next(role for role in target["date_roles"] if role["role"] == "superseded_issue")
            issue.update(date=day.isoformat(), quote=day.isoformat())
    parsed = machine_references._parse_roles(reading, material)
    assert machine_references._role_problem(parsed, material) == (
        "machine_role_dates_differ_across_variants" if defect == "missing_on_one_variant"
        else "machine_role_chronology_conflict"
    )
    p = protocol()
    first = firsts(p, material, "R", left=reading, right=reading)
    adj = adjudication(p, material, "R", first, value={"reference": reading, "rationale": "Invented role reading."})
    assert r_reference(p, material, first, adj).validity is MachineValidity.UNRESOLVED


@pytest.mark.parametrize("defect", ["duplicate", "extra_other_role"])
def test_generator_eligibility_rejects_redundant_or_contradictory_role_labels(defect):
    seed, material, mapping = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    roles = reading["targets"][0]["date_roles"]
    if defect == "duplicate":
        roles.append(dict(roles[0]))
    else:
        roles.append({"role": "other", "date": seed.publication_date.isoformat(),
                      "quote": seed.publication_date.isoformat()})
    p = protocol()
    first = firsts(p, material, "R", left=reading, right=reading)
    adj = adjudication(p, material, "R", first, value={"reference": reading, "rationale": "Invented role reading."})
    reference = r_reference(p, material, first, adj)
    assert reference.validity is MachineValidity.VALID
    eligibility = assess_synthetic_role_eligibility(reference, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.structural_checks_pass
    assert "machine_role_generator_date_roles_unverified" in eligibility.reasons


def test_generator_eligibility_allows_the_current_target_as_an_optional_date_role():
    seed, material, mapping = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    for target in reading["targets"]:
        target["date_roles"].append({"role": "current_recovery", "date": seed.target_date.isoformat(),
                                     "quote": seed.target_date.isoformat()})
    p = protocol()
    first = firsts(p, material, "R", left=reading, right=reading)
    adj = adjudication(p, material, "R", first, value={"reference": reading, "rationale": "Invented role reading."})
    reference = r_reference(p, material, first, adj)
    eligibility = assess_synthetic_role_eligibility(reference, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert reference.validity is MachineValidity.VALID and eligibility.structural_checks_pass
    assert not eligibility.eligible_for_synthetic_checks and not eligibility.blinded_role_eligible


@pytest.mark.parametrize("defect", ["swapped_publication_and_issue", "wrong_neutral_role"])
def test_machine_generator_eligibility_refuses_wrong_date_roles(defect):
    seed, material, mapping = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    notice_by_id = {item.item_id: item for item in material.notices}
    for target in reading["targets"]:
        roles = target["date_roles"]
        if defect == "swapped_publication_and_issue":
            publication = next(item for item in roles if item["role"] == "publication")
            issue = next(item for item in roles if item["role"] == "superseded_issue")
            publication["role"], issue["role"] = issue["role"], publication["role"]
        elif "Data filing" in notice_by_id[target["variant_id"]].notice_text:
            next(item for item in roles if item["role"] == "administrative")["role"] = "next_review"
    p = protocol()
    first = firsts(p, material, "R", left=reading, right=reading)
    adj = adjudication(p, material, "R", first, value={"reference": reading, "rationale": "Invented role reading."})
    reference = r_reference(p, material, first, adj)
    assert reference.validity is (MachineValidity.UNRESOLVED if defect == "swapped_publication_and_issue"
                                  else MachineValidity.VALID)
    eligibility = assess_synthetic_role_eligibility(reference, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.structural_checks_pass
    assert "machine_role_generator_date_roles_unverified" in eligibility.reasons


@pytest.mark.parametrize("arm", ["competitor", "neutral"])
def test_generator_eligibility_rejects_a_single_wrong_competing_role_in_either_arm(arm):
    seed, material, mapping = generated_role_fixture()
    reading = generated_role_reading(seed, material)
    opaque_by_variant = {variant: opaque for opaque, variant in mapping}
    variant = next(item for item in seed.variants if item.arm == arm)
    target = next(item for item in reading["targets"] if item["variant_id"] == opaque_by_variant[variant.item_id])
    expected = "next_review" if arm == "competitor" else "administrative"
    actual = "administrative" if arm == "competitor" else "next_review"
    next(item for item in target["date_roles"] if item["role"] == expected)["role"] = actual
    p = protocol()
    first = firsts(p, material, "R", left=reading, right=reading)
    adj = adjudication(p, material, "R", first, value={"reference": reading, "rationale": "Invented role reading."})
    reference = r_reference(p, material, first, adj)
    assert reference.validity is MachineValidity.VALID
    eligibility = assess_synthetic_role_eligibility(reference, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.structural_checks_pass
    assert "machine_role_generator_date_roles_unverified" in eligibility.reasons


def test_synthetic_role_eligibility_binds_generator_mapping_hashes_and_private_target():
    seed, material, mapping = generated_role_fixture()
    result = generated_role_reference(seed, material)
    assert result.validity is MachineValidity.VALID
    eligibility = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert eligibility.structural_checks_pass
    assert not eligibility.eligible_for_synthetic_checks and not eligibility.blinded_role_eligible
    assert "machine_role_separate_generator_revision_required" in eligibility.reasons
    assert eligibility.provenance.label == "machine_generated_not_human"
    first_payload = result.first_passes[0].request.payload
    assert set(first_payload) == {"notices"}
    assert "target_date" not in json.dumps(first_payload)
    assert seed.seed_id not in json.dumps(first_payload)
    assert seed.target_date.isoformat() not in repr(eligibility)


def test_synthetic_role_eligibility_is_recomputed_instead_of_accepting_fabricated_state():
    seed, material, mapping = generated_role_fixture()
    reference = generated_role_reference(seed, material)
    eligibility = assess_synthetic_role_eligibility(reference, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert eligibility.structural_checks_pass
    with pytest.raises(TypeError):
        replace(eligibility, eligible_for_synthetic_checks=True)
    swapped = ((mapping[0][0], mapping[1][1]), (mapping[1][0], mapping[0][1]), *mapping[2:])
    object.__setattr__(eligibility, "opaque_variant_map", swapped)
    assert not eligibility.eligible_for_synthetic_checks
    assert not eligibility.structural_checks_pass
    assert "machine_role_mapping_mismatch" in eligibility.reasons


def test_four_identical_competitors_fail_separate_role_eligibility_despite_machine_label():
    seed, material, mapping = generated_role_fixture()
    competitor = next(notice.notice_text for notice in material.notices if "Next review" in notice.notice_text)
    repeated = replace(material, notices=tuple(replace(notice, notice_text=competitor) for notice in material.notices))
    result = generated_role_reference(seed, repeated)
    assert result.validity is MachineValidity.VALID
    eligibility = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.eligible_for_synthetic_checks
    assert "machine_role_variant_hash_mismatch" in eligibility.reasons


def test_wrong_generated_target_is_not_made_eligible_by_a_machine_valid_label():
    seed, material, mapping = generated_role_fixture()
    wrong = seed.target_date + timedelta(days=3)
    changed = replace(material, notices=tuple(replace(notice, notice_text=notice.notice_text +
                                                       f" Alternate date {wrong.isoformat()}.")
                                               for notice in material.notices))
    result = generated_role_reference(seed, changed, target=wrong)
    assert result.validity is MachineValidity.VALID
    eligibility = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.eligible_for_synthetic_checks
    assert {"machine_role_variant_hash_mismatch", "machine_role_target_mismatch"} <= set(eligibility.reasons)


def test_role_eligibility_refuses_invalid_seed_chronology_mapping_and_generator_identity():
    seed, material, mapping = generated_role_fixture()
    result = generated_role_reference(seed, material)
    invalid_seed = replace(seed, publication_date=seed.update_date + timedelta(days=1))
    chronology = assess_synthetic_role_eligibility(result, seed=invalid_seed, opaque_variant_map=mapping,
                                                   generator_version=GENERATOR_VERSION)
    assert "machine_role_seed_structure_invalid" in chronology.reasons
    swapped = ((mapping[0][0], mapping[1][1]), (mapping[1][0], mapping[0][1]), *mapping[2:])
    wrong_map = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=swapped,
                                                  generator_version=GENERATOR_VERSION)
    assert "machine_role_mapping_mismatch" in wrong_map.reasons
    wrong_version = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                      generator_version="invented-other-generator")
    assert "machine_role_generator_version_mismatch" in wrong_version.reasons


def test_role_eligibility_rejects_seed_and_variant_subclasses():
    class ForgedSeed(RoleSeed):
        def __eq__(self, other):
            return True

    class ForgedVariant(RoleVariant):
        def __eq__(self, other):
            return True

    seed, material, mapping = generated_role_fixture()
    result = generated_role_reference(seed, material)
    with pytest.raises(TypeError, match="exact RoleSeed"):
        assess_synthetic_role_eligibility(result, seed=clone_as(seed, ForgedSeed), opaque_variant_map=mapping,
                                          generator_version=GENERATOR_VERSION)
    fake_variant = clone_as(seed.variants[0], ForgedVariant)
    bad_seed = replace(seed, variants=(fake_variant, *seed.variants[1:]))
    with pytest.raises(TypeError, match="exact RoleVariant"):
        assess_synthetic_role_eligibility(result, seed=bad_seed, opaque_variant_map=mapping,
                                          generator_version=GENERATOR_VERSION)


def test_nested_judge_binding_and_observed_identity_subclasses_are_refused():
    class ForgedJudge(Judge):
        def __eq__(self, other):
            return True

    class ForgedBinding(StageBinding):
        def __eq__(self, other):
            return True

    class ForgedIdentity(CallIdentity):
        def __eq__(self, other):
            return True

    p = protocol()
    poisoned = replace(p)
    object.__setattr__(poisoned, "judges", (clone_as(p.judges[0], ForgedJudge), *p.judges[1:]))
    with pytest.raises(ValueError, match="three machine judges"):
        prepare_request(poisoned, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    poisoned = replace(p)
    object.__setattr__(poisoned, "bindings", (clone_as(p.bindings[0], ForgedBinding), *p.bindings[1:]))
    with pytest.raises(ValueError, match="explicit stage bindings"):
        prepare_request(poisoned, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    request = prepare_request(p, NOTICE, judge_code="M1", cohort="N", stage="natural", shown_utc=T0)
    forged = clone_as(assigned_identity(p, request), ForgedIdentity)
    with pytest.raises(ValueError, match="identity mismatch"):
        submit(p, request, reading(option()), judgment_id="invented-fake-identity", observed=forged)


def test_cyclic_or_forged_nested_sources_fail_before_equality_is_considered():
    p = protocol()
    first = firsts(p)
    altered = replace(first[0])
    request = replace(altered.request)
    object.__setattr__(altered, "request", request)
    object.__setattr__(request, "sources", (altered,))
    with pytest.raises(ValueError, match="cycle"):
        n_reference(p, (altered, first[1]))


@pytest.mark.parametrize("raw,status", [
    (RawAnswer("returned", "{", "stop", None), "invalid_json"),
    (RawAnswer("returned", "{}", "stop", None), "invalid_schema"),
    (RawAnswer("returned", "{}", "length", None), "truncated"),
    (RawAnswer("unavailable", None, None, "invented unavailable"), "unavailable"),
    (RawAnswer("cap_blocked", None, None, "invented cap"), "cap_blocked"),
])
def test_c_specified_failure_states_remain_distinct_with_proposals_preserved(raw, status):
    p = protocol()
    first = firsts(p, cohort="C")
    second = specified(p, first, left=raw)
    adj = adjudication(p, NOTICE, "C", first, second=second)
    result = c_reference(p, first, second, adj)
    assert f"machine_specified_M1_{status}" in result.reasons
    assert result.state is ReferenceState.UNRESOLVED and result.convention_target.end is None
    assert result.specified_passes[0].answer == raw and result.specified.alternatives


@pytest.mark.parametrize("present", [0, 1])
def test_missing_first_passes_are_explicit_without_adjudication(present):
    p = protocol()
    first = firsts(p)[:present]
    result = n_reference(p, first)
    assert result.state is ReferenceState.UNRESOLVED
    assert "machine_first_M2_missing" in result.reasons and "machine_adjudication_missing" in result.reasons
    if present == 0:
        assert "machine_first_M1_missing" in result.reasons
    assert result.provenance.judgment_ids == tuple(item.judgment_id for item in first)


def test_unresolved_first_pass_cannot_be_completed_by_a_matching_adjudicator():
    p = protocol()
    unknown = reading(option(start=None, certainty=None), reason="invented unresolved interpretation")
    first = firsts(p, left=unknown)
    adj = adjudication(p, NOTICE, "N", first)
    result = n_reference(p, first, adj)
    assert result.state is ReferenceState.UNRESOLVED and result.endpoint.end is None
    assert "machine_first_M1_unresolved" in result.reasons
    assert result.first_passes[0].result.unresolved_reason == "invented unresolved interpretation"
    assert result.adjudication.result.reference.alternatives[0].end == date(2028, 3, 14)


def test_explicit_machine_material_rejections_do_not_become_a_resolved_candidate():
    p, material = protocol(), role_set()
    invalid = role_reading(material, valid=False, reason="invented defect")
    first = firsts(p, material, "R", left=invalid, right=invalid)
    adj = adjudication(p, material, "R", first, value={"reference": invalid, "rationale": "Retain rejection."})
    result = r_reference(p, material, first, adj)
    assert result.validity is MachineValidity.UNRESOLVED
    assert {"machine_first_M1_material_invalid", "machine_first_M2_material_invalid"} <= set(result.reasons)
    assert result.decision.material_valid is False


def test_c_nonliteral_start_is_not_inferred_even_if_end_is_literal():
    p = protocol()
    missing_start_support = reading(option(quote="2028-03-14"))
    first = firsts(p, cohort="C")
    second = specified(p, first, left=missing_start_support, right=missing_start_support)
    choice = {"defensible": reading(option()), "specified": missing_start_support,
              "rationale": "Invented incomplete support."}
    adj = adjudication(p, NOTICE, "C", first, second=second, value=choice)
    result = c_reference(p, first, second, adj)
    alternative = result.specified.alternatives[0]
    assert alternative.end_support is DateSupport.LITERAL_ISO
    assert alternative.start_support is DateSupport.UNVERIFIED
    assert result.convention_target.end is None and result.state is ReferenceState.UNRESOLVED
    assert "machine_specified_M1_date_support_unverified" in result.reasons


def test_altered_private_seed_target_fails_structural_and_target_binding():
    seed, material, mapping = generated_role_fixture()
    result = generated_role_reference(seed, material)
    altered = replace(seed, target_date=seed.target_date + timedelta(days=3))
    eligibility = assess_synthetic_role_eligibility(result, seed=altered, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.eligible_for_synthetic_checks
    assert {"machine_role_seed_structure_invalid", "machine_role_target_mismatch"} <= set(eligibility.reasons)


def test_fabricated_date_support_is_rejected_when_source_is_reparsed():
    p = protocol()
    unsupported = reading(option(end="2099-01-01", quote=option()["quote"]))
    first = firsts(p, left=unsupported, right=unsupported)
    alternative = replace(first[0].result.alternatives[0], end_support=DateSupport.LITERAL_ISO)
    forged_result = replace(first[0].result, alternatives=(alternative,))
    forged = replace(first[0], result=forged_result)
    with pytest.raises(ValueError, match="parsed judgment was altered"):
        n_reference(p, (forged, first[1]))


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
def test_prior_role_reason_with_nfkc_at_sign_is_not_forwarded(symbol):
    p, material = protocol(), role_set()
    invalid = role_reading(material, valid=False, reason="invented concern " + symbol)
    first = firsts(p, material, "R", left=invalid)
    adj = adjudication(p, material, "R", first)
    view = adj.request.payload["first_passes"][0]["reading"]
    assert view["reason_status"] == "reported" and "reason" not in view
    assert "invented concern" not in adj.request.visible_json and symbol not in adj.request.visible_json
    assert first[0].result.reason.endswith(symbol)
    assert r_reference(p, material, first, adj).validity is MachineValidity.UNRESOLVED


def test_role_eligibility_rejects_a_spoofed_final_reference():
    class ForgedRole(ReconciledRole):
        @property
        def validity(self):
            return MachineValidity.VALID

    seed, material, mapping = generated_role_fixture()
    reference = generated_role_reference(seed, material)
    forged = clone_as(reference, ForgedRole)
    with pytest.raises(TypeError, match="exact ReconciledRole"):
        assess_synthetic_role_eligibility(forged, seed=seed, opaque_variant_map=mapping,
                                          generator_version=GENERATOR_VERSION)


def test_role_aliases_use_private_domain_separated_hmac_and_hide_secret_from_views():
    p, material = protocol(), role_set()
    blinding = material.blinding
    expected_group = hmac.new(
        SYNTHETIC_ALIAS_KEY, b"collie-machine-role-group-v2\x00" + SYNTHETIC_PRIVATE_SEED.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    assert blinding.group_id == "G" + expected_group
    mapping = blinding.opaque_variant_map()
    assert len(mapping) == 4 and len({opaque for opaque, _ in mapping}) == 4
    for opaque, variant_id in mapping:
        expected = hmac.new(SYNTHETIC_ALIAS_KEY, b"collie-machine-role-variant-v2\x00" + variant_id.encode("ascii"),
                            hashlib.sha256).hexdigest()
        assert opaque == "V" + expected and len(opaque) == 65
        assert opaque[1:] != expected_group
    assert p.role_alias_commitment_sha256 == blinding.key_commitment_sha256
    request = prepare_request(p, material, judge_code="M1", cohort="R", stage="role", shown_utc=T0)
    visible = request.visible_json
    assert SYNTHETIC_PRIVATE_SEED not in visible and SYNTHETIC_ALIAS_KEY.hex() not in visible
    assert base64.b64encode(SYNTHETIC_ALIAS_KEY).decode("ascii") not in visible
    assert p.role_alias_commitment_sha256 not in visible
    assert all(private_id not in visible for _, private_id in mapping)
    assert SYNTHETIC_PRIVATE_SEED not in repr(material) and SYNTHETIC_ALIAS_KEY.hex() not in repr(material)
    with pytest.raises(TypeError, match="private role blinding"):
        asdict(request)


def test_role_aliases_change_with_private_seed_or_secret_without_claiming_entropy():
    original = role_blinding()
    other_seed = PrivateRoleBlinding(private_seed_id=SYNTHETIC_PRIVATE_SEED[::-1], alias_key=SYNTHETIC_ALIAS_KEY)
    other_key = bytes(value ^ 0xA5 for value in SYNTHETIC_ALIAS_KEY)
    other_secret = PrivateRoleBlinding(private_seed_id=SYNTHETIC_PRIVATE_SEED, alias_key=other_key)
    assert original.group_id != other_seed.group_id and original.group_id != other_secret.group_id
    assert set(original.opaque_variant_map()) != set(other_seed.opaque_variant_map())
    assert original.key_commitment_sha256 != other_secret.key_commitment_sha256


@pytest.mark.parametrize("seed_id", ["EVAL-R001", "EVAL-R002", "0" * 64, "f" * 64, "not-a-private-seed"])
def test_predictable_or_non_private_role_seed_shapes_are_refused(seed_id):
    with pytest.raises(ValueError, match="high-entropy-looking"):
        PrivateRoleBlinding(private_seed_id=seed_id, alias_key=SYNTHETIC_ALIAS_KEY)


@pytest.mark.parametrize("key", [b"x" * 32, b"short", bytes(32)])
def test_obviously_weak_or_short_role_alias_key_shapes_are_refused(key):
    with pytest.raises(ValueError, match="high-entropy-looking"):
        PrivateRoleBlinding(private_seed_id=SYNTHETIC_PRIVATE_SEED, alias_key=key)


def test_predictable_unkeyed_alias_format_is_not_accepted_for_role_views():
    material = role_set()
    mapping = material.blinding.opaque_variant_map()
    old_group = "G" + digest("20261011|role-blind-group-v1|" + SYNTHETIC_PRIVATE_SEED)[:20]
    old_notices = tuple(replace(notice, item_id="V" + digest("20261011|role-blind-id-v1|" + private_id)[:20])
                        for notice, (_, private_id) in zip(material.notices, mapping))
    with pytest.raises(ValueError, match="opaque G"):
        BlindRoleSet(old_group, old_notices, material.blinding)


def test_role_commitment_is_bound_to_protocol_and_registration_identity():
    p, material = protocol(), role_set()
    changed = replace(p, role_alias_commitment_sha256=digest("invented-other-role-commitment"))
    assert changed.sha256 != p.sha256
    with pytest.raises(ValueError, match="commitment"):
        prepare_request(changed, material, judge_code="M1", cohort="R", stage="role", shown_utc=T0)
    proposed = replace(p, data_scope="real")
    registration, verification = registration_records(proposed)
    assert registration.role_alias_commitment_sha256 == p.role_alias_commitment_sha256
    assert registration.role_seed_manifest_sha256 == p.role_seed_manifest_sha256
    with pytest.raises(ValueError, match="identities do not match"):
        registration_check(proposed, replace(registration, role_alias_commitment_sha256=digest("other")), verification)


def test_unlisted_private_seed_commitment_is_refused_before_a_role_view():
    p, material = protocol(), role_set()
    other = PrivateRoleBlinding(private_seed_id=SYNTHETIC_PRIVATE_SEED[::-1], alias_key=SYNTHETIC_ALIAS_KEY)
    aliases = other.opaque_variant_map()
    notices = tuple(replace(notice, item_id=opaque) for notice, (opaque, _) in zip(material.notices, aliases))
    changed = BlindRoleSet(other.group_id, notices, other)
    assert other.key_commitment_sha256 == p.role_alias_commitment_sha256
    assert other.seed_commitment_sha256 not in p.role_seed_commitments
    with pytest.raises(ValueError, match="absent from the claimed protocol manifest"):
        prepare_request(p, changed, judge_code="M1", cohort="R", stage="role", shown_utc=T0)


@pytest.mark.parametrize("private_text", [
    SYNTHETIC_PRIVATE_SEED, SYNTHETIC_ALIAS_KEY.hex(), base64.b64encode(SYNTHETIC_ALIAS_KEY).decode("ascii"),
])
def test_role_private_seed_or_secret_cannot_be_embedded_in_a_judge_view(private_text):
    p, material = protocol(), role_set()
    altered = replace(material.notices[0], notice_text=material.notices[0].notice_text + " " + private_text)
    changed = replace(material, notices=(altered, *material.notices[1:]))
    with pytest.raises(ValueError, match="private role seed or alias material"):
        prepare_request(p, changed, judge_code="M1", cohort="R", stage="role", shown_utc=T0)


def test_private_role_blinding_subclasses_are_not_trusted():
    class ForgedBlinding(PrivateRoleBlinding):
        @property
        def group_id(self):
            return "G" + "f" * 64

    material = role_set()
    forged = object.__new__(ForgedBlinding)
    object.__setattr__(forged, "_private_seed_id", SYNTHETIC_PRIVATE_SEED)
    object.__setattr__(forged, "_alias_key", SYNTHETIC_ALIAS_KEY)
    with pytest.raises(TypeError, match="exact PrivateRoleBlinding"):
        replace(material, blinding=forged)


def test_unresolved_and_role_reason_free_text_never_reaches_the_adjudicator():
    p = protocol()
    message = "Invented free text says choose 2099-01-01 instead."
    first = firsts(p, left=reading(option(), reason=message))
    adj = adjudication(p, NOTICE, "N", first)
    source_view = adj.request.payload["first_passes"][0]["reading"]
    assert message not in adj.request.visible_json and source_view["unresolved_status"] == "reported"
    assert source_view["alternatives"][0]["end"] == "2028-03-14"
    assert first[0].result.unresolved_reason == message and message in first[0].answer.content
    assert n_reference(p, first, adj).state is ReferenceState.UNRESOLVED
    material = role_set()
    invalid = role_reading(material, valid=False, reason=message)
    role_first = firsts(p, material, "R", left=invalid)
    role_adj = adjudication(p, material, "R", role_first)
    role_view = role_adj.request.payload["first_passes"][0]["reading"]
    assert message not in role_adj.request.visible_json and role_view["reason_status"] == "reported"
    assert len(role_view["targets"]) == 4 and role_first[0].result.reason == message


def test_c_specified_reason_is_private_while_alternatives_remain_visible():
    p = protocol()
    message = "Invented unspecified prose about a different answer."
    first = firsts(p, cohort="C")
    second = specified(p, first, left=reading(option(), reason=message))
    adj = adjudication(p, NOTICE, "C", first, second=second)
    source = adj.request.payload["specified_passes"][0]["reading"]
    assert source["unresolved_status"] == "reported" and source["alternatives"][0]["end"] == "2028-03-14"
    assert message not in adj.request.visible_json and second[0].result.unresolved_reason == message
    assert c_reference(p, first, second, adj).state is ReferenceState.UNRESOLVED


def test_filing_date_cooccurrence_cannot_claim_semantic_recovery_truth():
    p = protocol()
    notice = BlindNotice("invented-filing", date(2028, 1, 15),
                         "Invented filing covers 2028-03-01 to 2028-03-14; recovery timing is not stated.")
    claimed = reading(option(quote=notice.notice_text))
    first = firsts(p, notice, "N", left=claimed, right=claimed)
    adj = adjudication(p, notice, "N", first, value={"reference": claimed, "rationale": "Invented machine claim."})
    reference = reconcile_readings(p, notice, cohort="N", reference_version="invented-v1",
                                   first_passes=first, adjudication=adj)
    payload = json.loads(reference.endpoint.export_json())
    assert payload["date_evidence"] == "literal_iso_cooccurrence_only"
    assert payload["semantic_truth"] == "not_verified"
    assert payload["detached_value_status"] == "untrusted_detached_serialization"


def role_fixture_with_synthetic_key(alias_key):
    blinding = PrivateRoleBlinding(private_seed_id=SYNTHETIC_PRIVATE_SEED, alias_key=alias_key)
    p = replace(protocol(), role_alias_commitment_sha256=blinding.key_commitment_sha256,
                role_seed_commitments=(blinding.seed_commitment_sha256,))
    original = role_set()
    notices = tuple(replace(notice, item_id=opaque) for notice, (opaque, _) in
                    zip(original.notices, blinding.opaque_variant_map()))
    return p, BlindRoleSet(blinding.group_id, notices, blinding), blinding


def escaped_synthetic_key(special):
    prefix = b"0123456789ABCDEFGHIJKLMNOPQRSTU"
    assert len(prefix) == 31
    return prefix + special


def nfkc_variant(value):
    for index, character in enumerate(value):
        if "0" <= character <= "9" or "A" <= character <= "Z" or "a" <= character <= "z":
            return value[:index] + chr(ord(character) + 0xFEE0) + value[index + 1:]
    raise ValueError("invented value needs an ASCII letter or digit")


@pytest.mark.parametrize("special", [b'"', b"\\", b"\n", b"\r", b"\t", b"\x00", b"\x1b"])
@pytest.mark.parametrize("normalized_variant", [False, True])
def test_decoded_role_notice_refuses_json_escaped_private_key_before_export(special, normalized_variant):
    key = escaped_synthetic_key(special)
    p, material, _ = role_fixture_with_synthetic_key(key)
    decoded = key.decode("utf-8")
    embedded = nfkc_variant(decoded) if normalized_variant else decoded
    notice = replace(material.notices[0], notice_text=material.notices[0].notice_text + " " + embedded)
    changed = replace(material, notices=(notice, *material.notices[1:]))
    with pytest.raises(ValueError, match="private role seed or alias material") as error:
        changed.visible()
    assert decoded not in str(error.value)
    with pytest.raises(ValueError, match="private role seed or alias material"):
        prepare_request(p, changed, judge_code="M1", cohort="R", stage="role", shown_utc=T0)


@pytest.mark.parametrize("special", [b'"', b"\\", b"\n", b"\r", b"\t", b"\x00", b"\x1b"])
@pytest.mark.parametrize("normalized_variant", [False, True])
def test_nested_decoded_payload_values_refuse_escaped_private_key(special, normalized_variant):
    key = escaped_synthetic_key(special)
    _, _, blinding = role_fixture_with_synthetic_key(key)
    decoded = key.decode("utf-8")
    embedded = nfkc_variant(decoded) if normalized_variant else decoded
    visible = {"material": {"notices": [{"notice_text": "Invented notice."}]},
               "first_passes": [{"reading": {"targets": [{"date_roles": [{"quote": "before " + embedded}]}]}}]}
    with pytest.raises(ValueError, match="private role seed or alias material") as error:
        machine_references._refuse_private_role_material(blinding, visible)
    assert decoded not in str(error.value)


@pytest.mark.parametrize("special", [b'"', b"\\", b"\n", b"\r", b"\t", b"\x00", b"\x1b"])
@pytest.mark.parametrize("normalized_variant", [False, True])
def test_nested_adjudicator_payload_is_checked_before_serialization(monkeypatch, special, normalized_variant):
    key = escaped_synthetic_key(special)
    p, material, _ = role_fixture_with_synthetic_key(key)
    first = firsts(p, material, "R")
    decoded = key.decode("utf-8")
    embedded = nfkc_variant(decoded) if normalized_variant else decoded
    source = [{"judge_code": "M1", "reading": {"targets": [{"date_roles": [{"quote": embedded}]}]}}]
    monkeypatch.setattr(machine_references, "_source_views", lambda passes: source)
    original = machine_references._canonical
    serialized = []

    def record_serialization(value):
        if type(value) is dict and "first_passes" in value:
            serialized.append(True)
        return original(value)

    monkeypatch.setattr(machine_references, "_canonical", record_serialization)
    with pytest.raises(ValueError, match="private role seed or alias material") as error:
        prepare_request(p, material, judge_code="MADJ", cohort="R", stage="adjudication",
                        shown_utc=T0 + timedelta(seconds=4), first_passes=first)
    assert not serialized and decoded not in str(error.value)


def test_nfkc_normalizes_private_key_and_visible_text_before_comparison():
    suffix = "0123456789ABCDEFGHIJKLMNOPQRS"
    private_text = "Ａ" + suffix
    key = private_text.encode("utf-8")
    assert len(key) == 32
    p, material, blinding = role_fixture_with_synthetic_key(key)
    visible_text = "A" + suffix
    nested = {"first_passes": [{"reading": {"targets": [{"quote": visible_text}]}}]}
    with pytest.raises(ValueError, match="private role seed or alias material"):
        machine_references._refuse_private_role_material(blinding, nested)
    notice = replace(material.notices[0], notice_text=material.notices[0].notice_text + " " + visible_text)
    changed = replace(material, notices=(notice, *material.notices[1:]))
    with pytest.raises(ValueError, match="private role seed or alias material"):
        prepare_request(p, changed, judge_code="M1", cohort="R", stage="role", shown_utc=T0)


@pytest.mark.parametrize("representation", ["seed", "hex", "base64"])
def test_nfkc_variants_of_other_private_representations_are_refused_in_nested_values(representation):
    blinding = role_blinding()
    values = {"seed": SYNTHETIC_PRIVATE_SEED, "hex": SYNTHETIC_ALIAS_KEY.hex(),
              "base64": base64.b64encode(SYNTHETIC_ALIAS_KEY).decode("ascii")}
    visible = {"material": {"nested": [{"text": "before " + nfkc_variant(values[representation])}]}}
    with pytest.raises(ValueError, match="private role seed or alias material"):
        machine_references._refuse_private_role_material(blinding, visible)


def test_nested_payload_keys_and_at_signs_are_also_checked():
    key = escaped_synthetic_key(b'"')
    _, _, blinding = role_fixture_with_synthetic_key(key)
    visible = {"first_passes": [{"reading": {key.decode("utf-8"): "Invented value."}}]}
    with pytest.raises(ValueError, match="private role seed or alias material"):
        machine_references._refuse_private_role_material(blinding, visible)
    with pytest.raises(ValueError, match="at-sign"):
        machine_references._refuse_at_sign({"first_passes": [{"reading": {"quote": "invented ＠ text"}}]})


def test_selected_protocol_is_hash_bound_and_legacy_is_diagnostic_only():
    legacy, selected = protocol(), selected_protocol()
    assert legacy.protocol_design == LEGACY_PROTOCOL and selected.protocol_design == SELECTED_PROTOCOL
    assert legacy.sha256 != selected.sha256
    with pytest.raises(ValueError, match="every pinned blind and exposed stage|combined exposed adjudication"):
        replace(legacy, protocol_design=SELECTED_PROTOCOL)
    with pytest.raises(ValueError, match="legacy draft cannot contain"):
        replace(selected, protocol_design=LEGACY_PROTOCOL)
    first = firsts(legacy)
    exposed = adjudication(legacy, NOTICE, "N", first)
    result = n_reference(legacy, first, exposed)
    exported = result.endpoint.export()
    assert result.state is ReferenceState.ADJUDICATED and not result.selected_candidate_resolved
    assert exported["candidate_track"] == "legacy_three_stage_diagnostic_not_selected"
    assert exported["protocol_design"] == LEGACY_PROTOCOL and not exported["selected_candidate_resolved"]
    assert exported["blind_vs_exposed"] == Agreement.UNKNOWN.value
    assert result.blind_vs_exposed is Agreement.UNKNOWN


@pytest.mark.parametrize("field", ["template_id", "template_sha256", "parser_sha256"])
def test_selected_protocol_pins_distinct_madj_blind_and_exposed_artifacts(field):
    p = selected_protocol()
    blind = p.binding("MADJ", "N", "blind_proposal")
    exposed = p.binding("MADJ", "N", "adjudication")
    changed = tuple(replace(item, **{field: getattr(exposed, field)}) if item is blind else item
                    for item in p.bindings)
    with pytest.raises(ValueError, match="template and parser identities must differ"):
        replace(p, bindings=changed)


def test_selected_n_blind_and_exposed_views_are_separate_and_same_model_attempts_are_distinct():
    p = selected_protocol()
    first = firsts(p)
    blind = blind_proposal(p, NOTICE, "N")
    assert all(item.request.payload == NOTICE.visible() and item.request.sources == () for item in first)
    assert all(item.other_judgments_seen is False and not item.outcomes_seen for item in first)
    assert blind.request.payload == NOTICE.visible() and blind.request.sources == ()
    assert blind.request.blind_receipts == () and blind.other_judgments_seen is False
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    assert set(exposed.request.payload) == {"material", "first_passes"}
    assert [entry["judge_code"] for entry in exposed.request.payload["first_passes"]] == ["M1", "M2"]
    assert len(exposed.request.blind_receipts) == 1 and exposed.other_judgments_seen is True
    assert "blind_receipts" not in exposed.request.payload and "blind_passes" not in exposed.request.payload
    with pytest.raises(TypeError, match="private .*cannot be serialized"):
        asdict(exposed.request)
    blind_id, exposed_id = blind.observed_identity, exposed.observed_identity
    assert blind_id.model_id == exposed_id.model_id and blind_id.model_revision == exposed_id.model_revision
    assert blind_id.provider_route == exposed_id.provider_route
    assert blind_id.attempt_id != exposed_id.attempt_id and blind_id.input_sha256 != exposed_id.input_sha256
    assert blind_id.template_id != exposed_id.template_id and blind_id.template_sha256 != exposed_id.template_sha256
    assert blind_id.parser_sha256 != exposed_id.parser_sha256
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.state is ReferenceState.ADJUDICATED and result.selected_candidate_resolved
    assert result.blind_first_agreement is Agreement.AGREED and result.blind_vs_exposed is Agreement.AGREED
    assert result.blind_passes == (blind,) and result.adjudication == exposed
    exported = result.endpoint.export()
    assert exported["candidate_track"] == "selected_four_stage_separate_c_synthetic_only"
    assert exported["selected_candidate_resolved"] and not exported["real_use_authorized"]
    assert exported["blind_vs_exposed"] == Agreement.AGREED.value
    assert exported["provenance"]["label"] == "machine_generated_not_human"
    assert exported["provenance"]["protocol_design"] == SELECTED_PROTOCOL
    assert blind.judgment_id in result.provenance.judgment_ids


def test_exposed_view_never_contains_blind_madj_response_or_its_free_text():
    p = selected_protocol()
    first = firsts(p)
    private_one = "invented-private-blind-one"
    private_two = "invented-private-blind-two"
    blind_one = blind_proposal(p, NOTICE, "N", value=reading(option(), reason=private_one))
    blind_two = blind_proposal(p, NOTICE, "N", value=reading(option(end="2028-03-21"), reason=private_two),
                               attempt_id="invented-other-blind-attempt")
    exposed_one = selected_adjudication(p, NOTICE, "N", first, blinds=(blind_one,))
    exposed_two = selected_adjudication(p, NOTICE, "N", first, blinds=(blind_two,))
    assert exposed_one.request.visible_json == exposed_two.request.visible_json
    assert exposed_one.request.input_sha256 == exposed_two.request.input_sha256
    assert exposed_one.request.sources_sha256 != exposed_two.request.sources_sha256
    assert private_one not in exposed_one.request.visible_json and private_two not in exposed_two.request.visible_json
    assert private_one not in repr(exposed_one.request) and private_two not in repr(exposed_two.request)
    assert exposed_one.request.sources == first and all(item.request.judge_code != "MADJ" for item in exposed_one.request.sources)
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind_one,), adjudication=exposed_one)
    assert result.state is ReferenceState.UNRESOLVED and not result.selected_candidate_resolved
    assert result.blind_passes[0].result.unresolved_reason == private_one
    assert "machine_blind_first_MADJ_unresolved" in result.reasons


@pytest.mark.parametrize("field", ["evaluated_outputs_seen", "rule_proposals_seen", "sensitivity_seen",
                                   "outcomes_seen", "blind_madj_response_seen", "prior_madj_adjudication_seen",
                                   "convention_or_specified_preexposed", "other_judgments_seen"])
def test_selected_blind_proposal_refuses_every_exposure_attestation(field):
    p = selected_protocol()
    request = prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="blind_proposal", shown_utc=T0)
    with pytest.raises(ValueError):
        submit(p, request, reading(option()), judgment_id="invented-exposed-blind", **{field: True})


def test_selected_exposed_adjudication_refuses_blind_response_or_outcome_exposure():
    p = selected_protocol()
    first, blind = firsts(p), blind_proposal(p, NOTICE, "N")
    request = prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                              shown_utc=T0 + timedelta(seconds=4), first_passes=first, blind_passes=(blind,))
    value = {"reference": reading(option()), "rationale": "Invented ruling."}
    for field in ("blind_madj_response_seen", "prior_madj_adjudication_seen", "outcomes_seen",
                  "evaluated_outputs_seen", "sensitivity_seen", "convention_or_specified_preexposed"):
        with pytest.raises(ValueError, match="blind"):
            submit(p, request, value, judgment_id="invented-exposure", submitted=T0 + timedelta(seconds=5),
                   **{field: True})


@pytest.mark.parametrize("raw,status", [
    (RawAnswer("returned", "{", "stop", None), "invalid_json"),
    (RawAnswer("returned", "{}", "stop", None), "invalid_schema"),
    (RawAnswer("returned", "{}", "length", None), "truncated"),
    (RawAnswer("unavailable", None, None, "invented unavailable"), "unavailable"),
    (RawAnswer("cap_blocked", None, None, "invented cap"), "cap_blocked"),
])
def test_selected_invalid_or_unavailable_blind_proposal_cannot_be_overridden(raw, status):
    p = selected_protocol()
    first = firsts(p)
    blind = blind_proposal(p, NOTICE, "N", value=raw)
    if raw.kind == "returned":
        exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
        result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                    blind_passes=(blind,), adjudication=exposed)
        assert result.adjudication.result.reference.alternatives
    else:
        with pytest.raises(ValueError, match="actual prior returned blind submission"):
            selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
        result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                    blind_passes=(blind,))
    assert result.state is ReferenceState.UNRESOLVED and result.endpoint.end is None
    assert f"machine_blind_first_MADJ_{status}" in result.reasons
    assert result.blind_passes[0].answer == raw
    assert result.blind_vs_exposed is Agreement.UNKNOWN


@pytest.mark.parametrize("raw,status", [
    (RawAnswer("returned", "{", "stop", None), "invalid_json"),
    (RawAnswer("returned", "{}", "stop", None), "invalid_schema"),
    (RawAnswer("returned", "{}", "length", None), "truncated"),
    (RawAnswer("unavailable", None, None, "invented unavailable"), "unavailable"),
    (RawAnswer("cap_blocked", None, None, "invented cap"), "cap_blocked"),
])
def test_selected_m1_failure_remains_unknown_even_if_blind_and_exposed_agree(raw, status):
    p = selected_protocol()
    first = firsts(p, left=raw)
    blind = blind_proposal(p, NOTICE, "N")
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.state is ReferenceState.UNRESOLVED and not result.selected_candidate_resolved
    assert f"machine_first_M1_{status}" in result.reasons and result.blind_vs_exposed is Agreement.AGREED
    assert result.first_passes[0].answer == raw and result.adjudication.result.reference.alternatives


def test_selected_unverified_blind_and_first_endpoints_are_not_promoted():
    p = selected_protocol()
    unsupported = reading(option(end="2099-01-01", quote=option()["quote"]))
    first = firsts(p)
    blind = blind_proposal(p, NOTICE, "N", value=unsupported)
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.endpoint.end is None and result.blind_vs_exposed is Agreement.UNKNOWN
    assert "machine_blind_first_MADJ_date_support_unverified" in result.reasons
    assert result.blind_passes[0].result.alternatives[0].end == date(2099, 1, 1)
    first = firsts(p, left=unsupported)
    blind = blind_proposal(p, NOTICE, "N")
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.endpoint.end is None and "machine_first_M1_date_support_unverified" in result.reasons
    assert result.blind_vs_exposed is Agreement.AGREED


def test_selected_blind_disagreement_is_retained_and_never_resolved_by_exposed_choice():
    p = selected_protocol()
    first = firsts(p)
    blind = blind_proposal(p, NOTICE, "N", value=reading(option(end="2028-03-21")))
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.state is ReferenceState.UNRESOLVED and result.endpoint.end is None
    assert result.blind_first_agreement is Agreement.DISAGREED and result.blind_vs_exposed is Agreement.DISAGREED
    assert result.endpoint.export()["blind_vs_exposed"] == Agreement.DISAGREED.value
    assert "machine_blind_first_semantic_disagreement" in result.reasons
    assert blind.result.alternatives[0].end == date(2028, 3, 21)
    assert exposed.result.reference.alternatives[0].end == date(2028, 3, 14)


def test_selected_m1_m2_disagreement_remains_unknown_even_when_blind_matches_exposed():
    p = selected_protocol()
    first = firsts(p, right=reading(option(end="2028-03-21")))
    blind = blind_proposal(p, NOTICE, "N")
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.state is ReferenceState.UNRESOLVED and not result.selected_candidate_resolved
    assert result.first_agreement is Agreement.DISAGREED and result.blind_vs_exposed is Agreement.AGREED
    assert "machine_first_semantic_disagreement" in result.reasons


def test_selected_quote_differences_are_not_converted_to_semantic_disagreement():
    p = selected_protocol()
    first = firsts(p)
    blind = blind_proposal(p, NOTICE, "N", value=reading(option(quote=NOTICE.notice_text)))
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    result = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
    assert result.blind_first_agreement is Agreement.AGREED and result.blind_vs_exposed is Agreement.AGREED
    assert result.selected_candidate_resolved and blind.result.alternatives[0].quote != first[0].result.alternatives[0].quote


def test_selected_missing_or_late_discovered_blind_pass_cannot_be_silently_filled():
    p = selected_protocol()
    first, blind = firsts(p), blind_proposal(p, NOTICE, "N")
    with pytest.raises(ValueError, match="actual prior returned blind submission"):
        selected_adjudication(p, NOTICE, "N", first)
    exposed_with_receipt = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    missing_raw = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first,
                                     blind_passes=(), adjudication=exposed_with_receipt)
    assert "machine_blind_first_MADJ_missing" in missing_raw.reasons
    assert missing_raw.endpoint.end is None and missing_raw.blind_vs_exposed is Agreement.UNKNOWN
    missing_m1 = reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=first[1:],
                                    blind_passes=(blind,), adjudication=exposed_with_receipt)
    assert "machine_first_M1_missing" in missing_m1.reasons and missing_m1.endpoint.end is None


def test_selected_c_requires_three_initial_submissions_before_any_convention_view():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    assert all(item.request.payload == NOTICE.visible() for item in (*first, blind_first))
    for code, stage in (("M1", "specified"), ("MADJ", "blind_specified")):
        with pytest.raises(ValueError, match="all three actual blind first submissions"):
            prepare_request(p, NOTICE, judge_code=code, cohort="C", stage=stage,
                            shown_utc=T0 + timedelta(seconds=4), first_passes=first, condition_block=BLOCK)
    unavailable = blind_proposal(p, NOTICE, "C", value=RawAnswer("unavailable", None, None, "invented absence"))
    with pytest.raises(ValueError, match="all three actual blind first submissions"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified", shown_utc=T0 + timedelta(seconds=4),
                        first_passes=first, blind_passes=(unavailable,), condition_block=BLOCK)
    with pytest.raises(ValueError, match="actual completed absent adjudication"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified", shown_utc=T0 + timedelta(seconds=4),
                        first_passes=first, blind_passes=(blind_first,), condition_block=BLOCK)
    late = blind_proposal(p, NOTICE, "C", submitted=T0 + timedelta(seconds=3))
    with pytest.raises(ValueError, match="blind submissions must precede"):
        selected_absent(p, first, late)
    absent = selected_absent(p, first, blind_first)
    with pytest.raises(ValueError, match="follow the completed absent adjudication"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="specified", shown_utc=T0 + timedelta(seconds=3),
                        first_passes=first, blind_passes=(blind_first,), absent_adjudication=absent, condition_block=BLOCK)
    with pytest.raises(ValueError, match="must not see a convention"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="C", stage="blind_unspecified",
                        shown_utc=T0, condition_block=BLOCK)
    with pytest.raises(ValueError, match="first-pass views cannot contain other judgments"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="C", stage="blind_unspecified",
                        shown_utc=T0, first_passes=first)
    with pytest.raises(ValueError, match="first-pass views cannot contain other judgments"):
        prepare_request(p, NOTICE, judge_code="M1", cohort="C", stage="unspecified",
                        shown_utc=T0, blind_passes=(blind_first,))


def test_selected_c_keeps_both_blind_stages_isolated_and_preserves_two_stage_results():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    assert set(absent.request.payload) == {"material", "first_passes"}
    assert BLOCK not in absent.request.visible_json and "specified_passes" not in absent.request.payload
    assert blind_first.judgment_id not in absent.request.visible_json
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    for item in (*second, blind_second):
        assert item.request.payload == {**NOTICE.visible(), "condition_block": BLOCK}
        assert item.other_judgments_seen is False
        assert "first_passes" not in item.request.payload and "blind_receipts" not in item.request.payload
        with pytest.raises(TypeError, match="private .*cannot be serialized"):
            asdict(item.request)
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second),
                                    absent=absent)
    assert set(exposed.request.payload) == {"material", "specified_passes", "condition_block"}
    assert all(entry["judge_code"] in {"M1", "M2"} for entry in exposed.request.payload["specified_passes"])
    assert len(exposed.request.blind_receipts) == 2
    assert blind_first.judgment_id not in exposed.request.visible_json
    assert blind_second.judgment_id not in exposed.request.visible_json
    assert absent.judgment_id not in exposed.request.visible_json
    result = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                specified_adjudication=exposed)
    assert result.state is ReferenceState.ADJUDICATED and result.selected_candidate_resolved
    assert result.blind_first_agreement is Agreement.AGREED and result.blind_specified_agreement is Agreement.AGREED
    assert result.blind_vs_exposed_first is Agreement.AGREED and result.blind_vs_exposed_specified is Agreement.AGREED
    assert result.blind_vs_exposed is Agreement.AGREED
    assert result.convention_target.export()["blind_vs_exposed_specified"] == Agreement.AGREED.value
    assert result.convention_target.end == date(2028, 3, 14)
    assert result.blind_passes == (blind_first, blind_second)
    all_stages = (*first, blind_first, absent, *second, blind_second, exposed)
    assert len(all_stages) == 8 and len({item.request.attempt_id for item in all_stages}) == 8
    assert len(result.provenance.judgment_ids) == 8
    identities = (blind_first.observed_identity, absent.observed_identity, blind_second.observed_identity,
                  exposed.observed_identity)
    assert len({item.attempt_id for item in identities}) == 4
    assert len({item.template_id for item in identities}) == 4
    assert len({item.parser_sha256 for item in identities}) == 4
    assert len({item.input_sha256 for item in identities}) == 4
    assert len({item.model_id for item in identities}) == 1


def test_selected_c_blind_specified_disagreement_survives_exposed_adjudication():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5),
                                  value=reading(option(end="2028-03-21")))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    result = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                specified_adjudication=exposed)
    assert result.state is ReferenceState.UNRESOLVED and result.convention_target.end is None
    assert result.blind_specified_agreement is Agreement.DISAGREED
    assert result.blind_vs_exposed_specified is Agreement.DISAGREED and result.blind_vs_exposed is Agreement.DISAGREED
    assert "machine_blind_specified_semantic_disagreement" in result.reasons
    assert blind_second.result.alternatives[0].end == date(2028, 3, 21)


def test_selected_c_absent_blind_disagreement_is_separate_from_specified_agreement():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C", value=reading(option(end="2028-03-21")))
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    result = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                specified_adjudication=exposed)
    assert result.blind_vs_exposed_first is Agreement.DISAGREED
    assert result.blind_vs_exposed_specified is Agreement.AGREED and result.blind_vs_exposed is Agreement.DISAGREED
    assert result.state is ReferenceState.UNRESOLVED and result.convention_target.end is None
    assert result.blind_passes[0].result.alternatives[0].end == date(2028, 3, 21)


def test_selected_c_first_pass_disagreement_is_not_resolved_by_two_adjudications():
    p = selected_protocol()
    first = firsts(p, cohort="C", right=reading(option(end="2028-03-21")))
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    result = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                specified_adjudication=exposed)
    assert result.first_agreement is Agreement.DISAGREED and "machine_first_semantic_disagreement" in result.reasons
    assert result.state is ReferenceState.UNRESOLVED and not result.selected_candidate_resolved
    assert result.first_passes[1].result.alternatives[0].end == date(2028, 3, 21)


def test_selected_c_invalid_returned_blind_first_allows_ordered_second_pass_but_remains_unknown():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    raw = RawAnswer("returned", '{"invented-invalid-blind-marker"', "stop", None)
    blind_first = blind_proposal(p, NOTICE, "C", value=raw)
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    result = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                specified_adjudication=exposed)
    assert result.state is ReferenceState.UNRESOLVED and result.convention_target.end is None
    assert "machine_blind_first_MADJ_invalid_json" in result.reasons
    assert result.blind_vs_exposed_first is Agreement.UNKNOWN and result.blind_vs_exposed_specified is Agreement.AGREED
    assert "invented-invalid-blind-marker" not in exposed.request.visible_json
    assert result.blind_passes[0].answer == raw


def test_selected_c_exposed_adjudication_must_follow_all_blind_and_specified_submissions():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    with pytest.raises(ValueError, match="blind submissions must precede"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="C", stage="adjudication_specified",
                        shown_utc=T0 + timedelta(seconds=5), first_passes=first, specified_passes=second,
                        blind_passes=(blind_first, blind_second), absent_adjudication=absent, condition_block=BLOCK)


def test_selected_c_specified_exposure_requires_actual_specified_blind_record():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    valid = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    values = dict(judge_code="MADJ", cohort="C", stage="adjudication_specified",
                  shown_utc=T0 + timedelta(seconds=6), first_passes=first, specified_passes=second,
                  absent_adjudication=absent, condition_block=BLOCK)
    with pytest.raises(ValueError, match="actual prior returned blind submission"):
        prepare_request(p, NOTICE, blind_passes=(blind_first,), **values)
    with pytest.raises(ValueError, match="receipts cannot authorize"):
        prepare_request(p, NOTICE, blind_receipts=valid.request.blind_receipts, **values)


def test_selected_c_specified_chain_cannot_switch_the_prior_blind_submission():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    other_blind = blind_proposal(p, NOTICE, "C", value=reading(option(end="2028-03-21")),
                                 attempt_id="invented-other-unspecified-attempt")
    absent = selected_absent(p, first, blind_first)
    other_absent = selected_absent(p, first, other_blind)
    second = selected_specified(p, first, blind_first, absent)
    other_blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(other_blind,),
                                        absent=other_absent, shown=T0 + timedelta(seconds=4),
                                        submitted=T0 + timedelta(seconds=5))
    with pytest.raises(ValueError, match="same absent adjudication"):
        selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, other_blind_second), absent=absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    other_second = selected_specified(p, first, other_blind, other_absent)
    with pytest.raises(ValueError, match="same absent adjudication"):
        selected_adjudication(p, NOTICE, "C", first, second=other_second, blinds=(blind_first, blind_second), absent=absent)


def test_selected_c_retrospective_missing_passes_are_not_recovered_from_private_context():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    missing_blind = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                       specified_passes=second, blind_passes=(blind_first,), adjudication=absent,
                                       specified_adjudication=exposed)
    assert "machine_blind_specified_MADJ_missing" in missing_blind.reasons
    assert missing_blind.blind_vs_exposed is Agreement.UNKNOWN and missing_blind.convention_target.end is None
    missing_m1 = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first[1:],
                                    specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                    specified_adjudication=exposed)
    assert "machine_first_M1_missing" in missing_m1.reasons and missing_m1.convention_target.end is None
    assert missing_m1.blind_vs_exposed is Agreement.AGREED
    missing_absent = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                        specified_passes=second, blind_passes=(blind_first, blind_second),
                                        specified_adjudication=exposed)
    assert "machine_adjudication_absent_missing" in missing_absent.reasons
    assert missing_absent.blind_vs_exposed_first is Agreement.UNKNOWN and missing_absent.convention_target.end is None
    missing_specified = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                           specified_passes=second, blind_passes=(blind_first, blind_second),
                                           adjudication=absent)
    assert "machine_adjudication_specified_missing" in missing_specified.reasons
    assert missing_specified.blind_vs_exposed_specified is Agreement.UNKNOWN and missing_specified.convention_target.end is None


def test_selected_c_exposed_view_never_receives_private_blind_reason():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    secret_reason = "invented-private-madj-reason"
    blind_first = blind_proposal(p, NOTICE, "C", value=reading(option(), reason=secret_reason))
    absent = selected_absent(p, first, blind_first)
    assert secret_reason not in absent.request.visible_json
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    assert all(secret_reason not in item.request.visible_json for item in (*second, blind_second))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    assert secret_reason not in exposed.request.visible_json
    result = reconcile_readings(p, NOTICE, cohort="C", reference_version="invented-v1", first_passes=first,
                                specified_passes=second, blind_passes=(blind_first, blind_second), adjudication=absent,
                                specified_adjudication=exposed)
    assert "machine_blind_first_MADJ_unresolved" in result.reasons
    assert result.blind_passes[0].result.unresolved_reason == secret_reason


def test_selected_c_never_sends_prior_absent_decision_to_specified_views():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    private_rationale = "invented-private-absent-rationale"
    absent = selected_absent(p, first, blind_first,
                             value={"reference": reading(option()), "rationale": private_rationale})
    second = selected_specified(p, first, blind_first, absent)
    blind_second = blind_proposal(p, NOTICE, "C", stage="blind_specified", first=first, earlier=(blind_first,),
                                  absent=absent, shown=T0 + timedelta(seconds=4), submitted=T0 + timedelta(seconds=5))
    exposed = selected_adjudication(p, NOTICE, "C", first, second=second, blinds=(blind_first, blind_second), absent=absent)
    assert all(private_rationale not in item.request.visible_json for item in (*second, blind_second, exposed))
    assert all(not item.prior_madj_adjudication_seen for item in (*second, blind_second, exposed))
    assert absent.result.rationale == private_rationale


def test_selected_c_absent_view_refuses_convention_and_specified_proposals():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    absent = selected_absent(p, first, blind_first)
    second = selected_specified(p, first, blind_first, absent)
    with pytest.raises(ValueError, match="must not see a convention block"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="C", stage="adjudication_absent",
                        shown_utc=T0 + timedelta(seconds=6), first_passes=first,
                        blind_passes=(blind_first,), condition_block=BLOCK)
    with pytest.raises(ValueError, match="cannot receive specified"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="C", stage="adjudication_absent",
                        shown_utc=T0 + timedelta(seconds=6), first_passes=first,
                        specified_passes=second, blind_passes=(blind_first,))
    with pytest.raises(ValueError, match="out-of-order C exposure"):
        submit(p, absent.request, {"reference": reading(option()), "rationale": "Invented ruling."},
               judgment_id="invented-preexposed-absent", submitted=T0 + timedelta(seconds=3),
               convention_or_specified_preexposed=True)
    assert BLOCK not in absent.request.visible_json and "specified_passes" not in absent.request.payload


def test_selected_role_blind_and_exposed_are_separate_but_generator_eligibility_stays_closed():
    p = selected_protocol()
    seed, material, mapping = generated_role_fixture()
    value = generated_role_reading(seed, material)
    first = firsts(p, material, "R", left=value, right=value)
    blind = blind_proposal(p, material, "R", value=value)
    exposed = selected_adjudication(p, material, "R", first, blinds=(blind,),
                                    value={"reference": value, "rationale": "Invented role ruling."})
    assert set(blind.request.payload) == {"notices"}
    assert set(exposed.request.payload) == {"material", "first_passes"}
    assert SYNTHETIC_PRIVATE_SEED not in blind.request.visible_json
    assert SYNTHETIC_ALIAS_KEY.hex() not in exposed.request.visible_json
    result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                            blind_passes=(blind,), adjudication=exposed)
    assert result.validity is MachineValidity.VALID and result.blind_vs_exposed is Agreement.AGREED
    assert not result.selected_candidate_resolved
    eligibility = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert eligibility.structural_checks_pass and not eligibility.blinded_role_eligible
    assert "machine_role_separate_generator_revision_required" in eligibility.reasons
    assert result.provenance.candidate_track == "selected_four_stage_separate_c_synthetic_only"


@pytest.mark.parametrize("missing_stage", ["M1", "M2", "blind", "exposed"])
def test_selected_role_an_issue_missing_from_one_stage_cannot_become_valid(missing_stage):
    p = selected_protocol()
    seed, material, mapping = generated_role_fixture()
    complete = generated_role_reading(seed, material)
    incomplete = copy.deepcopy(complete)
    for target in incomplete["targets"]:
        target["date_roles"] = [role for role in target["date_roles"] if role["role"] != "superseded_issue"]
    first = firsts(p, material, "R", left=incomplete if missing_stage == "M1" else complete,
                   right=incomplete if missing_stage == "M2" else complete)
    blind = blind_proposal(p, material, "R", value=incomplete if missing_stage == "blind" else complete)
    exposed = selected_adjudication(
        p, material, "R", first, blinds=(blind,),
        value={"reference": incomplete if missing_stage == "exposed" else complete,
               "rationale": "Invented role ruling."},
    )
    result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                            blind_passes=(blind,), adjudication=exposed)
    eligibility = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert result.validity is MachineValidity.UNRESOLVED
    assert not eligibility.structural_checks_pass and not eligibility.blinded_role_eligible
    assert "machine_role_reference_unresolved" in eligibility.reasons


@pytest.mark.parametrize("duplicated_stage", ["M1", "M2", "blind", "exposed"])
def test_generator_eligibility_checks_duplicate_role_entries_at_each_selected_stage(duplicated_stage):
    p = selected_protocol()
    seed, material, mapping = generated_role_fixture()
    complete = generated_role_reading(seed, material)
    duplicate = copy.deepcopy(complete)
    date_roles = duplicate["targets"][0]["date_roles"]
    date_roles.append(dict(date_roles[0]))
    first = firsts(p, material, "R", left=duplicate if duplicated_stage == "M1" else complete,
                   right=duplicate if duplicated_stage == "M2" else complete)
    blind = blind_proposal(p, material, "R", value=duplicate if duplicated_stage == "blind" else complete)
    exposed = selected_adjudication(
        p, material, "R", first, blinds=(blind,),
        value={"reference": duplicate if duplicated_stage == "exposed" else complete,
               "rationale": "Invented role ruling."},
    )
    result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                            blind_passes=(blind,), adjudication=exposed)
    assert result.validity is MachineValidity.VALID  # Semantic keys discard duplicate role/date entries.
    eligibility = assess_synthetic_role_eligibility(result, seed=seed, opaque_variant_map=mapping,
                                                    generator_version=GENERATOR_VERSION)
    assert not eligibility.structural_checks_pass and not eligibility.blinded_role_eligible
    assert "machine_role_generator_date_roles_unverified" in eligibility.reasons


def test_selected_role_blind_rejection_and_exposed_validity_do_not_form_a_majority():
    p, material = selected_protocol(), role_set()
    first = firsts(p, material, "R")
    blind = blind_proposal(p, material, "R", value=role_reading(material, valid=False, reason="invented defect"))
    exposed = selected_adjudication(p, material, "R", first, blinds=(blind,))
    result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                            blind_passes=(blind,), adjudication=exposed)
    assert result.validity is MachineValidity.UNRESOLVED and not result.selected_candidate_resolved
    assert result.blind_first_agreement is Agreement.DISAGREED and result.blind_vs_exposed is Agreement.DISAGREED
    assert blind.result.material_valid is False and exposed.result.reference.material_valid is True


@pytest.mark.parametrize("raw,status", [
    (RawAnswer("returned", "{", "stop", None), "invalid_json"),
    (RawAnswer("returned", "{}", "length", None), "truncated"),
    (RawAnswer("unavailable", None, None, "invented absence"), "unavailable"),
])
def test_selected_role_failed_blind_pass_remains_unknown(raw, status):
    p, material = selected_protocol(), role_set()
    first = firsts(p, material, "R")
    blind = blind_proposal(p, material, "R", value=raw)
    if raw.kind == "returned":
        exposed = selected_adjudication(p, material, "R", first, blinds=(blind,))
        result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,), adjudication=exposed)
        assert result.decision.material_valid is True
    else:
        with pytest.raises(ValueError, match="actual prior returned blind submission"):
            selected_adjudication(p, material, "R", first, blinds=(blind,))
        result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                                blind_passes=(blind,))
    assert result.validity is MachineValidity.UNRESOLVED and result.blind_vs_exposed is Agreement.UNKNOWN
    assert f"machine_blind_first_MADJ_{status}" in result.reasons
    assert result.blind_passes[0].answer == raw


@pytest.mark.parametrize("cohort", ["N", "C", "R"])
def test_selected_exposed_views_require_actual_prior_blind_records_not_receipts(cohort):
    p = selected_protocol()
    material = role_set() if cohort == "R" else NOTICE
    first = firsts(p, material, cohort)
    blind = blind_proposal(p, material, cohort)
    stage = "adjudication_absent" if cohort == "C" else "adjudication"
    shown = T0 + timedelta(seconds=4)
    with pytest.raises(ValueError, match="actual prior returned blind submission"):
        prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage=stage,
                        shown_utc=shown, first_passes=first)
    request = prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage=stage,
                              shown_utc=shown, first_passes=first, blind_passes=(blind,))
    receipt = request.blind_receipts[0]
    backdated = replace(receipt, submitted_utc=T0 - timedelta(days=1), record_sha256=digest("invented-fake-record"))
    with pytest.raises(ValueError, match="receipts cannot authorize"):
        prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage=stage,
                        shown_utc=shown, first_passes=first, blind_receipts=(backdated,))
    forged_receipt = replace(request, blind_receipts=(backdated,))
    with pytest.raises(ValueError, match="blinded request or its source identity was altered"):
        _ = forged_receipt.payload
    no_record = replace(request, blind_receipts=(backdated,),
                        _private_evidence=machine_references._PrivateStageEvidence((), None))
    with pytest.raises(ValueError, match="actual prior returned blind submission"):
        _ = no_record.payload
    late = blind_proposal(p, material, cohort, submitted=T0 + timedelta(seconds=5))
    with pytest.raises(ValueError, match="blind submissions must precede"):
        prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage=stage,
                        shown_utc=shown, first_passes=first, blind_passes=(late,))
    disguised_late = replace(request, blind_receipts=(backdated,),
                             _private_evidence=machine_references._PrivateStageEvidence((late,), None))
    with pytest.raises(ValueError, match="blind submissions must precede"):
        _ = disguised_late.payload
    altered = replace(blind, submitted_utc=T0 - timedelta(seconds=1))
    with pytest.raises(ValueError, match="submission cannot precede"):
        prepare_request(p, material, judge_code="MADJ", cohort=cohort, stage=stage,
                        shown_utc=shown, first_passes=first, blind_passes=(altered,))


@pytest.mark.parametrize("cohort", ["N", "C"])
def test_selected_exposure_refuses_blind_record_from_another_private_subject(cohort):
    p = selected_protocol()
    first = firsts(p, cohort=cohort)
    other = replace(NOTICE, item_id="different-invented-subject")
    blind = blind_proposal(p, other, cohort)
    stage = "adjudication_absent" if cohort == "C" else "adjudication"
    with pytest.raises(ValueError, match="blind proposal identity, material, or stage mismatch"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort=cohort, stage=stage,
                        shown_utc=T0 + timedelta(seconds=4), first_passes=first, blind_passes=(blind,))


def test_selected_c_absent_adjudication_must_be_valid_before_specified_views():
    p = selected_protocol()
    first = firsts(p, cohort="C")
    blind_first = blind_proposal(p, NOTICE, "C")
    invalid = selected_absent(p, first, blind_first, value=RawAnswer("returned", "{", "stop", None))
    assert invalid.status is ParseStatus.INVALID_JSON
    with pytest.raises(ValueError, match="valid returned absent adjudication"):
        selected_specified(p, first, blind_first, invalid)


def test_selected_role_export_is_rederived_machine_labelled_and_never_human_gold():
    p, material = selected_protocol(), role_set()
    first = firsts(p, material, "R")
    blind = blind_proposal(p, material, "R")
    exposed = selected_adjudication(p, material, "R", first, blinds=(blind,))
    result = reconcile_role(p, material, reference_version="invented-v1", first_passes=first,
                            blind_passes=(blind,), adjudication=exposed)
    exported = result.export()
    assert exported["machine_reference_label"] == "machine_generated_not_human"
    assert exported["provenance"]["label"] == "machine_generated_not_human"
    assert exported["machine_validity"] == MachineValidity.VALID.value
    assert exported["blind_vs_exposed"] == Agreement.AGREED.value
    assert not exported["real_use_authorized"] and not exported["selected_candidate_resolved"]
    assert exported["generator_eligibility"] == "unresolved_separate_generator_revision_required"
    assert exported["detached_value_status"] == "untrusted_detached_serialization"
    assert SYNTHETIC_PRIVATE_SEED not in result.export_json() and SYNTHETIC_ALIAS_KEY.hex() not in result.export_json()
    exported["machine_validity"] = "invented-forgery"
    assert result.export()["machine_validity"] == MachineValidity.VALID.value
    object.__setattr__(result, "adjudication", None)
    assert result.export()["machine_validity"] == MachineValidity.UNRESOLVED.value


def test_selected_attempts_receipts_and_design_cannot_be_reused_or_forged():
    p = selected_protocol()
    first, blind = firsts(p), blind_proposal(p, NOTICE, "N")
    with pytest.raises(ValueError, match="attempt IDs must be distinct"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                        shown_utc=T0 + timedelta(seconds=4), first_passes=first, blind_passes=(blind,),
                        attempt_id=blind.request.attempt_id)
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    forged_receipt = replace(exposed.request.blind_receipts[0], record_sha256=digest("invented-forgery"))
    with pytest.raises(ValueError, match="receipts cannot authorize"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                        shown_utc=T0 + timedelta(seconds=4), first_passes=first, blind_receipts=(forged_receipt,))
    altered_blind = replace(blind, result=first[0].result, status=ParseStatus.TRUNCATED)
    with pytest.raises(ValueError, match="parsed judgment was altered"):
        selected_adjudication(p, NOTICE, "N", first, blinds=(altered_blind,))
    legacy_first = firsts(protocol())
    with pytest.raises(ValueError, match="protocol identity mismatch"):
        reconcile_readings(p, NOTICE, cohort="N", reference_version="invented-v1", first_passes=legacy_first)


def test_untrusted_blind_receipt_subclass_cannot_override_validation():
    class ForgedReceipt(BlindReceipt):
        def __eq__(self, other):
            return True

    p = selected_protocol()
    first, blind = firsts(p), blind_proposal(p, NOTICE, "N")
    exposed = selected_adjudication(p, NOTICE, "N", first, blinds=(blind,))
    forged = clone_as(exposed.request.blind_receipts[0], ForgedReceipt)
    with pytest.raises(TypeError, match="exact BlindReceipt"):
        prepare_request(p, NOTICE, judge_code="MADJ", cohort="N", stage="adjudication",
                        shown_utc=T0 + timedelta(seconds=4), first_passes=first, blind_receipts=(forged,))


@pytest.mark.parametrize("symbol", ["@", "＠", "﹫"])
def test_selected_blind_views_keep_existing_at_sign_and_real_scope_refusals(symbol):
    p = selected_protocol()
    notice = replace(NOTICE, notice_text=NOTICE.notice_text + " invented " + symbol)
    with pytest.raises(ValueError, match="at-sign"):
        blind_proposal(p, notice, "N")
    with pytest.raises(ValueError, match="real use is disabled"):
        blind_proposal(replace(p, data_scope="real"), NOTICE, "N")
