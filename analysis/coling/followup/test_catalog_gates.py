"""Synthetic-only checks: no paths, real inventories, outcomes, or model outputs."""

from __future__ import annotations

import csv
import gzip
import io
import json
import pickle
import re
import sys
from dataclasses import asdict, replace

import pytest

from analysis.coling.followup import catalog_gates as gate
from analysis.coling.followup import sampling


def _digest(text: str) -> str:
    return gate.sha256_bytes(text.encode("utf-8"))


def _row(number: int, *, availability: str = "ordinary synthetic notice", related: str = "",
         statement: str | None = None, group: str | None = None) -> dict[str, str]:
    group = group or f"group{number}"
    return {
        "event_id": f"event{number}", "statement_group_id": group, "episode_id": f"episode:{group}",
        "listing": "shortage", "status_at_statement": "current", "availability_class": "limited",
        "event_date": "2026-01-01", "revision_index": "0", "generic_name": "synthetic",
        "company_name": "synthetic", "presentation": "synthetic", "therapeutic_category": "synthetic",
        "initial_posting_date": "", "type_of_update": "", "availability_text": availability,
        "related_text": related, "statement_text": statement if statement is not None else availability,
        "reason_for_shortage": "", "hidden_decoy": "synthetic-hidden-column-must-not-escape",
    }


def _compressed(rows: list[dict[str, str]]) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=[*sampling.SOURCE_FIELDS, "hidden_decoy"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(text.getvalue().encode("utf-8"), mtime=0)


_DEFAULT = object()
_SYNTHETIC_ALIAS_KEY = bytes(range(32))


def _bundle(category: str, events_sha256: str, *, ids: tuple[str, ...] = (),
            notices: tuple[str, ...] = (), whole: tuple[str, ...] = (),
            fragments: tuple[gate.FragmentFingerprint, ...] = (),
            fragment_texts: tuple[str, ...] = (),
            notice_texts: tuple[tuple[str, str], ...] = (), statement_texts: tuple[str, ...] = (),
            rationale: str | None | object = _DEFAULT, unresolved: int = 0, unmapped: int = 0,
            claims: tuple[str, ...] | None = None, fragment_support: bool = True,
            same_evidence_and_attestation: bool = False, source_identity: str | None = None,
            evidence_identity: str | None = None, attester_identity: str | None = None,
            source_version: str = sampling.FINGERPRINT_VERSION) -> gate.SourceBundle:
    empty = not (ids or notices or whole or fragments)
    if rationale is _DEFAULT:
        rationale = "Synthetic scoped source review documented an empty inventory." if empty else None
    source = gate.EvidenceIdentity(evidence_identity or f"{category}.source-record", "source_record",
                                   _digest(category + " source"))
    evidence = [source]
    fragment_source = None
    if not empty and fragment_support:
        fragment_source = gate.canonical_json_bytes({"schema": gate.FRAGMENT_SOURCE_SCHEMA,
                                                     "fingerprint_version": source_version,
                                                     "phrases": sorted(set(fragment_texts)),
                                                     "notices": [{"availability": a, "related": r}
                                                                 for a, r in sorted(set(notice_texts))],
                                                     "statements": sorted(set(statement_texts))})
        evidence.append(gate.EvidenceIdentity(f"{category}.fragment-record", "fragment_source",
                                              gate.sha256_bytes(fragment_source)))
    evidence = tuple(sorted(evidence, key=lambda item: item.identity))
    if claims is None:
        claim_set = {"coverage_complete"}
        if empty:
            claim_set.add("empty_after_review")
        if not empty and fragment_support:
            claim_set.add("fragment_from_authorized_source")
            claim_set.add("fingerprints_from_authorized_source")
        claims = tuple(sorted(claim_set))
    attestation_digest = source.document_sha256 if same_evidence_and_attestation else _digest(category + " attestation")
    attestation = gate.Attestation(
        f"{category}.attestation", attester_identity or "synthetic-review-identity", attestation_digest, category,
        claims, tuple(item.identity for item in evidence),
    )
    id_set_sha256 = gate.sha256_bytes(gate.canonical_json_bytes(sorted(ids)))
    provenance = gate.SourceProvenance(category, source_identity or f"{category}.source", evidence, (attestation,),
                                       len(ids), id_set_sha256, rationale, unresolved, unmapped)
    provenance_sha256 = gate.sha256_bytes(gate.canonical_json_bytes(asdict(provenance)))
    payload = {
        "schema": gate.SOURCE_SCHEMA, "fingerprint_version": sampling.FINGERPRINT_VERSION,
        "category": category, "events_sha256": events_sha256,
        "provenance_sha256": provenance_sha256, "statement_ids": sorted(ids),
        "notice_fingerprints": sorted(notices), "whole_field_fingerprints": sorted(whole),
        "fragments": [asdict(item) for item in sorted(fragments, key=lambda item: (item.token_count, item.sha256))],
    }
    inventory_bytes = gate.canonical_json_bytes(payload)
    inventory_sha256 = gate.sha256_bytes(inventory_bytes)
    regenerated = bytes(bytearray(inventory_bytes))
    regeneration = gate.RegenerationRecord(
        category, f"{category}.regeneration", "synthetic-regenerator", _digest(category + " method"),
        events_sha256, None if fragment_source is None else gate.sha256_bytes(fragment_source),
        provenance_sha256, inventory_sha256, gate.sha256_bytes(regenerated),
    )
    regeneration_sha256 = gate.sha256_bytes(gate.canonical_json_bytes(asdict(regeneration)))
    return gate.SourceBundle(category, inventory_bytes, inventory_sha256, regenerated,
                             gate.sha256_bytes(regenerated), provenance, provenance_sha256,
                             fragment_source, regeneration, regeneration_sha256)


def _request(rows: list[dict[str, str]] | None = None, *,
             sources: dict[str, dict] | None = None) -> gate.CatalogRequest:
    rows = rows if rows is not None else [_row(1)]
    compressed = _compressed(rows)
    events_sha256 = gate.sha256_bytes(compressed)
    source_options = sources or {}
    bundles = []
    for name in sorted(sampling.REQUIRED_EXCLUSIONS):
        options = dict(source_options.get(name, {}))
        ids = set(options.get("ids", ()))
        matched = [row for row in rows if row["statement_group_id"] in ids]
        pairs = set(options.get("notice_texts", ())) | {(row["availability_text"], row["related_text"]) for row in matched}
        statements = set(options.get("statement_texts", ())) | {row["statement_text"] for row in matched
                                                               if sampling.statement_fingerprint(row["statement_text"]) is not None}
        fingerprints = set(options.get("notices", ()))
        fingerprints.update(sampling.notice_fingerprint(a, r) for a, r in pairs)
        fingerprints.update(sampling.statement_fingerprint(text) for text in statements)
        options.update(notices=tuple(sorted(fingerprints)), notice_texts=tuple(sorted(pairs)),
                       statement_texts=tuple(sorted(statements)))
        bundles.append(_bundle(name, events_sha256, **options))
    policy = gate.CatalogPolicy(gate.FRAGMENT_MODE, 3, gate.BLANK_MODE, "new_prompt_development")
    return gate.CatalogRequest("ready", events_sha256, compressed, tuple(bundles), policy, _SYNTHETIC_ALIAS_KEY)


def _alias(value: str, kind: str = "item") -> str:
    return sampling.private_alias(_SYNTHETIC_ALIAS_KEY, kind, value)


def _commitment_for_bytes(request: gate.CatalogRequest, decision: gate.CatalogDecision,
                          package: str, manifest_bytes: bytes) -> gate.FrozenNCommitment:
    n_commitment = sampling.private_commitment(request.alias_key, "draw_manifest", manifest_bytes)
    evidence_identity = "synthetic.lock.evidence"
    evidence_sha256 = _digest("synthetic pre-access commitment evidence")
    record = {"schema": gate.N_COMMITMENT_SCHEMA, "gate_commitment": decision.gate_commitment,
              "protocol_commitment": decision.protocol_commitment,
              "fingerprint_version": sampling.FINGERPRINT_VERSION,
              "commitment_version": sampling.COMMITMENT_VERSION,
              "alias_key_commitment": sampling.alias_key_commitment(request.alias_key),
              "package": package, "n_manifest_commitment": n_commitment,
              "before_reference_and_evaluation": True,
              "evidence_identity": sampling.private_alias(request.alias_key, "evidence", evidence_identity),
              "evidence_commitment": sampling.digest_commitment(request.alias_key, "evidence_document", evidence_sha256)}
    record_bytes = gate.canonical_json_bytes(record)
    return gate.FrozenNCommitment(record_bytes, sampling.private_commitment(request.alias_key, "n_lock_record", record_bytes),
                                  n_commitment, evidence_identity, evidence_sha256)


def _commitment(request: gate.CatalogRequest, decision: gate.CatalogDecision,
                natural: gate.GatedDraw) -> gate.FrozenNCommitment:
    manifest = gate.gated_sample_manifest(request, decision, natural)
    return _commitment_for_bytes(request, decision, natural.package, gate.canonical_json_bytes(manifest))


def _with_bundle(request: gate.CatalogRequest, category: str, bundle: gate.SourceBundle) -> gate.CatalogRequest:
    return replace(request, sources=tuple(bundle if item.category == category else item for item in request.sources))


def _get_bundle(request: gate.CatalogRequest, category: str) -> gate.SourceBundle:
    return next(item for item in request.sources if item.category == category)


def _issue(request: gate.CatalogRequest, expected: str) -> None:
    decision = gate.assess_catalog(request)
    assert decision.status == "not_ready"
    assert any(expected in issue for issue in decision.issues)
    assert decision.gate_commitment is None


def test_ready_receipt_binds_evidence_and_separate_regeneration_without_plaintext():
    request = _request()
    decision = gate.assess_catalog(request)
    assert decision.status == "ready" and decision.issues == ()
    receipt = gate.gate_receipt(request, decision)
    assert sampling.private_commitment(request.alias_key, "gate", gate.canonical_json_bytes(receipt)) == decision.gate_commitment
    assert receipt["schema"] == "followup-catalog-gate-v4"
    assert receipt["fingerprint_version"] == sampling.FINGERPRINT_VERSION
    assert receipt["alias_key_commitment"] == sampling.alias_key_commitment(request.alias_key)
    assert receipt["scope"] == "candidate_not_authorization"
    assert receipt["events_commitment"] == sampling.digest_commitment(request.alias_key, "events", request.expected_events_sha256)
    assert len(receipt["sources"]) == 6
    assert all(item["regeneration_commitment"] != item["inventory_commitment"] for item in receipt["sources"])
    assert all(item["empty_rationale_commitment"] for item in receipt["sources"])
    assert all(item["expected_statement_count"] == 0 for item in receipt["sources"])
    assert "Synthetic scoped source review" not in json.dumps(receipt)
    assert "ordinary synthetic notice" not in repr(decision)
    assert "synthetic-hidden-column" not in json.dumps(receipt)
    assert gate.assess_catalog(replace(request, sources=tuple(reversed(request.sources)))).gate_commitment == decision.gate_commitment


def test_exported_receipt_lock_and_manifests_contain_only_keyed_data_commitments():
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    receipt = gate.gate_receipt(request, decision)
    natural = gate.gated_select_n(request, decision, package="reduced")
    n_manifest = gate.gated_sample_manifest(request, decision, natural)
    commitment = _commitment(request, decision, natural)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural,
                                     n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)
    c_manifest = gate.gated_sample_manifest(request, decision, convention, natural=natural,
                                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)
    _, state = gate._ready_state(request, decision)
    sources, _ = gate._effective_sources(state, request.policy, request.alias_key)
    retained = gate._restore_n_from_manifest(request, state, sources, natural, gate._checked_draw(request, decision, natural))
    raw_hashes = {request.expected_events_sha256, retained.frame_sha256, retained.sample_sha256,
                  retained.exclusions_sha256, commitment.evidence_sha256}
    for bundle in request.sources:
        raw_hashes.update((bundle.inventory_sha256, bundle.regenerated_inventory_sha256, bundle.provenance_sha256,
                           bundle.regeneration_sha256, bundle.provenance.expected_statement_set_sha256,
                           bundle.regeneration.method_sha256))
        if bundle.fragment_source_bytes is not None:
            raw_hashes.add(gate.sha256_bytes(bundle.fragment_source_bytes))
        raw_hashes.update(item.document_sha256 for item in bundle.provenance.evidence)
        raw_hashes.update(item.document_sha256 for item in bundle.provenance.attestations)
    raw_hashes.update(event.wording_sha256 for event in state.events)
    raw_hashes.update(event.model_input_sha256 for event in state.events)
    raw_hashes.update(event.statement_wording_sha256 for event in state.events if event.statement_wording_sha256)
    outputs = [receipt, json.loads(commitment.record_bytes), n_manifest, c_manifest]
    rendered = json.dumps(outputs, ensure_ascii=False) + repr(decision) + repr(natural) + repr(convention)
    assert all(value not in rendered for value in raw_hashes)
    assert request.alias_key.hex() not in rendered

    def strings(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value

    assert not any(re.fullmatch(r"[0-9a-f]{64}", value) for output in outputs for value in strings(output))


@pytest.mark.parametrize("status,issue", [("not_ready", "declared_not_ready"), ("unknown", "status_invalid")])
def test_explicit_status_blocks_sampling(status: str, issue: str):
    request = replace(_request(), declared_status=status)
    decision = gate.assess_catalog(request)
    assert decision.status == "not_ready" and decision.issues == (issue,)
    with pytest.raises(ValueError, match="not ready"):
        gate.gated_select_n(request, decision, package="reduced")


def test_not_ready_does_not_project_or_sample(monkeypatch):
    request = replace(_request(), declared_status="not_ready")

    def forbidden(*args, **kwargs):
        raise AssertionError("not-ready input must not be projected or sampled")

    monkeypatch.setattr(sampling, "project_open_events", forbidden)
    monkeypatch.setattr(sampling, "select_n", forbidden)
    decision = gate.assess_catalog(request)
    assert decision.status == "not_ready"
    with pytest.raises(ValueError, match="not ready"):
        gate.gated_select_n(request, decision, package="reduced")


def test_exactly_six_named_categories_are_required():
    request = _request()
    _issue(replace(request, sources=request.sources[:-1]), "categories_invalid")
    _issue(replace(request, sources=(*request.sources[:-1], request.sources[0])), "categories_invalid")
    _issue(replace(request, sources=(*request.sources, request.sources[0])), "categories_invalid")
    bad = replace(request.sources[0], category="unregistered")
    _issue(replace(request, sources=(bad, *request.sources[1:])), "categories_invalid")
    bad = replace(request.sources[0], category=[])
    _issue(replace(request, sources=(bad, *request.sources[1:])), "categories_invalid")


def test_compressed_events_are_verified_not_just_claimed():
    request = _request()
    _issue(replace(request, expected_events_sha256="0" * 64), "events_invalid_or_hash_mismatch")
    different = _compressed([_row(2)])
    _issue(replace(request, compressed_events=different), "events_invalid_or_hash_mismatch")
    _issue(replace(request, compressed_events=b"not gzip",
                   expected_events_sha256=gate.sha256_bytes(b"not gzip")), "events_invalid_or_hash_mismatch")
    _issue(_request(rows=[]), "events_empty")
    _issue(_request(rows=[_row(1), _row(1)]), "events_duplicate_ids")


@pytest.mark.parametrize("key", [b"", b"x" * 31, bytearray(32), "synthetic-key"])
def test_alias_key_requires_bytes_of_at_least_32_bytes(key):
    _issue(replace(_request(), alias_key=key), "alias_key_invalid")


def test_id_equal_to_notice_is_aliased_everywhere_and_private_mapping_is_recoverable():
    raw = "invented-ID-equals-notice"
    sensitive = _row(1, availability=raw, statement=raw, group=raw)
    sensitive["event_id"] = raw
    sensitive["episode_id"] = raw
    rows = [sensitive] + [_row(i, availability=f"early May synthetic event {i}") for i in range(2, 75)]
    request = _request(rows, sources={"task_e": {"ids": (raw,), "source_identity": raw,
                                                   "evidence_identity": raw, "attester_identity": raw}})
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    receipt = gate.gate_receipt(request, decision)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    record = json.loads(commitment.record_bytes)
    record["evidence_identity"] = sampling.private_alias(request.alias_key, "evidence", raw)
    record_bytes = gate.canonical_json_bytes(record)
    commitment = gate.FrozenNCommitment(record_bytes, sampling.private_commitment(request.alias_key, "n_lock_record", record_bytes),
                                        commitment.expected_n_manifest_commitment, raw, commitment.evidence_sha256)
    assert raw not in commitment.record_bytes.decode() and request.alias_key.hex() not in commitment.record_bytes.decode()
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    manifests = (gate.gated_sample_manifest(request, decision, natural),
                 gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, natural=natural,
                                            n_anchor_commitment=commitment.expected_record_commitment))
    source = next(item for item in receipt["sources"] if item["category"] == "task_e")
    assert source["source_identity"] == sampling.private_alias(request.alias_key, "source", raw)
    assert source["attestations"][0]["attester_identity"] == sampling.private_alias(request.alias_key, "actor", raw)
    assert sampling.private_alias(request.alias_key, "evidence", raw) in source["attestations"][0]["evidence_ids"]
    assert receipt["alias_key_commitment"] == sampling.alias_key_commitment(request.alias_key)
    for manifest in manifests:
        assert raw not in json.dumps(manifest) and request.alias_key.hex() not in json.dumps(manifest)
        frame = {item["item_id"]: item for item in manifest["sample"]["frame"]}
        entry = frame[_alias(raw)]
        assert len({entry["item_id"], entry["event_id"], entry["episode_id"]}) == 3
        assert any(item["statement_group_id"] == _alias(raw) for item in manifest["policy_exclusions"])
    bundle = _get_bundle(request, "task_e")
    private_index = sampling.private_alias_index([sampling.project_event(sensitive)], alias_key=request.alias_key)
    row = next(item for item in manifests[0]["sample"]["frame"] if item["item_id"] == _alias(raw))
    for kind in ("item", "event", "episode"):
        assert private_index.resolve(kind, row[kind + "_id"]) == raw
    objects = (sampling.project_event(sensitive), request, bundle, bundle.provenance, *bundle.provenance.evidence,
               *bundle.provenance.attestations, bundle.regeneration, private_index, decision, natural, commitment)
    assert all(raw not in repr(item) and request.alias_key.hex() not in repr(item) for item in objects)
    assert raw not in json.dumps(receipt) and request.alias_key.hex() not in json.dumps(receipt)


def test_alias_key_mismatch_and_alias_collision_fail_closed(monkeypatch):
    request = _request([_row(1), _row(2)])
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    different = replace(request, alias_key=bytes(reversed(range(32))))
    assert gate.assess_catalog(different).gate_commitment != decision.gate_commitment
    with pytest.raises(ValueError, match="not ready|no longer matches"):
        gate.gated_select_n(different, decision, package="reduced")
    with pytest.raises(ValueError, match="not ready|no longer matches"):
        gate.gated_select_c(different, decision, package="reduced", natural=natural, n_commitment=commitment,
                            n_anchor_commitment=commitment.expected_record_commitment)
    actual_alias = sampling.private_alias

    def colliding(key, kind, value):
        return "synthetic-collision" if kind == "item" else actual_alias(key, kind, value)

    monkeypatch.setattr(sampling, "private_alias", colliding)
    _issue(request, "alias_mapping_invalid")


def test_unicode_and_internal_space_ids_map_consistently_without_exporting_raw_text():
    item, event_id, episode = "製剤 α 供給 42", "更新 Δ 1", "期間 🌱 2"
    row = _row(1, availability=item, statement=item, group=item)
    row["event_id"], row["episode_id"] = event_id, episode
    request = _request([row], sources={"task_e": {"ids": (item,)}})
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    natural = gate.gated_select_n(request, decision, package="reduced")
    manifest = gate.gated_sample_manifest(request, decision, natural)
    exported = json.dumps([gate.gate_receipt(request, decision), manifest], ensure_ascii=False)
    assert all(value not in exported for value in (item, event_id, episode))
    frame = manifest["sample"]["frame"][0]
    index = sampling.private_alias_index([sampling.project_event(row)], alias_key=request.alias_key)
    assert index.resolve("item", frame["item_id"]) == item
    assert index.resolve("event", frame["event_id"]) == event_id
    assert index.resolve("episode", frame["episode_id"]) == episode


def test_raw_ids_equal_to_alias_or_commitment_fail_before_readiness():
    raw = "ordinary synthetic identity"
    alias = sampling.private_alias(_SYNTHETIC_ALIAS_KEY, "item", raw)
    commitment = sampling.alias_key_commitment(_SYNTHETIC_ALIAS_KEY)
    for value in (alias, commitment, "界" * 86, "inner\ncontrol", "trailing "):
        row = _row(1, group=value)
        _issue(_request([row]), "event_identifier_invalid")
    request = _request()
    source = _bundle("task_e", request.expected_events_sha256, ids=(alias,))
    _issue(_with_bundle(request, "task_e", source), "inventory_ids_invalid")


@pytest.mark.parametrize("kind", ["evidence", "actor", "idset"])
def test_receipt_alias_collisions_fail_closed(kind, monkeypatch):
    request = _request([_row(1), _row(2)], sources={"task_e": {"ids": ("group1",)}})
    actual_alias = sampling.private_alias

    def colliding(key, field, value):
        return "synthetic-collision" if field == kind else actual_alias(key, field, value)

    monkeypatch.setattr(sampling, "private_alias", colliding)
    _issue(request, "alias_mapping_invalid")


def test_conflicting_evidence_identity_fails_closed():
    request = _request(sources={"task_e": {"evidence_identity": "same.synthetic.record"},
                                "pilot_check_literal": {"evidence_identity": "same.synthetic.record"}})
    _issue(request, "alias_mapping_invalid")


@pytest.mark.parametrize("options,issue", [
    ({"rationale": None}, "empty_rationale_missing"),
    ({"rationale": "none"}, "empty_rationale_missing"),
    ({"claims": ("coverage_complete",)}, "empty_attestation_missing"),
    ({"same_evidence_and_attestation": True}, "attestation_support_missing"),
    ({"unresolved": 2}, "unresolved"),
    ({"unmapped": 1}, "unmapped"),
])
def test_empty_sources_need_separate_evidence_attestation_and_rationale(options: dict, issue: str):
    _issue(_request(sources={"inspected_item_outputs": options}), issue)


def test_absent_source_or_attestation_cannot_make_an_empty_source_ready():
    request = _request()
    original = _get_bundle(request, "inspected_item_outputs")
    no_evidence = replace(original.provenance, evidence=())
    _issue(_with_bundle(request, original.category, replace(original, provenance=no_evidence)), "evidence_invalid")
    no_attestation = replace(original.provenance, attestations=())
    _issue(_with_bundle(request, original.category, replace(original, provenance=no_attestation)),
           "attestation_invalid")


def test_unmapped_actual_statement_identity_blocks_the_gate():
    request = _request(sources={"task_e": {"ids": ("not-in-synthetic-events",)}})
    _issue(request, "unmapped_statement_ids")
    assert "not-in-synthetic-events" not in repr(gate.assess_catalog(request))


def test_nonempty_sources_need_evidence_even_when_no_fragments_are_recorded():
    _issue(_request(sources={"task_e": {"ids": ("group1",), "fragment_support": False}}),
           "fragment_evidence_missing")
    _issue(_request(sources={"task_e": {"ids": ("group1",),
                                          "claims": ("coverage_complete", "fragment_from_authorized_source")}}),
           "fingerprint_evidence_missing")
    request = _request(sources={"task_e": {"ids": ("group1",)}})
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    draw = gate.gated_select_n(request, decision, package="reduced")
    frame = gate.gated_sample_manifest(request, decision, draw)["sample"]["frame"]
    assert len(frame) == 1 and frame[0]["selected_rank"] is None and "task_e" in frame[0]["exclusions"]


def test_source_ids_require_all_presentation_fingerprints_from_verified_events():
    request = _request()
    incomplete = _bundle("task_e", request.expected_events_sha256, ids=("group1",))
    _issue(_with_bundle(request, "task_e", incomplete), "source_id_fingerprints_missing")
    rows = [_row(1, availability="synthetic visible wording", group="shared-group"),
            _row(2, availability="synthetic hidden wording", group="shared-group")]
    rows[1]["availability_class"] = "available"
    request = _request(rows)
    visible = sampling.project_event(rows[0])
    incomplete = _bundle("task_e", request.expected_events_sha256, ids=("shared-group",),
                         notices=tuple(sorted(visible.exclusion_fingerprints)),
                         notice_texts=((visible.availability_text, visible.related_text),),
                         statement_texts=(visible.statement_text,))
    _issue(_with_bundle(request, "task_e", incomplete), "source_id_fingerprints_missing")
    assert gate.assess_catalog(_request(rows, sources={"task_e": {"ids": ("shared-group",)}})).status == "ready"


def test_supplied_statement_count_and_canonical_id_set_digest_are_checked():
    request = _request(sources={"task_e": {"ids": ("group1",)}})
    bundle = _get_bundle(request, "task_e")
    wrong_count = replace(bundle.provenance, expected_statement_count=100)
    _issue(_with_bundle(request, bundle.category, replace(bundle, provenance=wrong_count)),
           "statement_count_mismatch")
    wrong_set = replace(bundle.provenance, expected_statement_set_sha256=_digest("other synthetic set"))
    _issue(_with_bundle(request, bundle.category, replace(bundle, provenance=wrong_set)),
           "statement_set_hash_mismatch")


def test_inventory_hash_and_canonical_json_are_required():
    request = _request()
    bundle = _get_bundle(request, "task_e")
    _issue(_with_bundle(request, bundle.category, replace(bundle, inventory_bytes=bundle.inventory_bytes + b" ")),
           "inventory_hash_mismatch")
    spaced = bundle.inventory_bytes + b" "
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=spaced, inventory_sha256=gate.sha256_bytes(spaced))),
           "inventory_not_canonical")
    duplicate = bundle.inventory_bytes.replace(b'"schema":', b'"schema":"duplicate","schema":', 1)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=duplicate, inventory_sha256=gate.sha256_bytes(duplicate))),
           "inventory_invalid")


def test_legacy_or_untyped_inventory_and_relabelled_legacy_hash_are_refused():
    request = _request()
    bundle = _get_bundle(request, "task_e")
    payload = json.loads(bundle.inventory_bytes)
    payload["schema"] = "followup-exclusion-source-v1"
    del payload["fingerprint_version"]
    raw = gate.canonical_json_bytes(payload)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=raw, inventory_sha256=gate.sha256_bytes(raw))),
           "inventory_schema_invalid")
    payload["schema"] = gate.SOURCE_SCHEMA
    payload["fingerprint_version"] = "legacy-untyped"
    raw = gate.canonical_json_bytes(payload)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=raw, inventory_sha256=gate.sha256_bytes(raw))),
           "fingerprint_version_mismatch")
    text = "synthetic legacy collision text"
    legacy = gate.sha256_bytes(gate.canonical_json_bytes(["statement", text]))
    rows = [_row(1, availability="statement", related=text)]
    mislabeled = _request(rows, sources={"task_e": {"notices": (legacy,),
                                                       "notice_texts": (("statement", text),)}})
    _issue(mislabeled, "fingerprint_regeneration_mismatch")
    phrase = "synthetic legacy phrase fragment"
    legacy_phrase = gate.sha256_bytes(sampling._wording(phrase).encode())
    legacy_fragment = gate.FragmentFingerprint(legacy_phrase, 4)
    mislabeled_phrase = _request(sources={"guide_prompt_examples": {"whole": (legacy_phrase,),
                                     "fragments": (legacy_fragment,), "fragment_texts": (phrase,)}})
    _issue(mislabeled_phrase, "fragment_regeneration_mismatch")
    _issue(_request(sources={"task_e": {"ids": ("group1",), "source_version": "legacy-untyped"}}),
           "fragment_source_invalid")


def test_versioned_fingerprints_prevent_cross_type_source_misattribution():
    text = "synthetic distinct collision value"
    rows = [
        _row(1, availability="statement", related=text, statement="other synthetic statement", group="notice-group"),
        _row(2, availability="different synthetic field", related="other", statement=text, group="statement-group"),
    ]
    rows.extend(_row(i, availability=f"early May separate case {i}") for i in range(3, 75))
    sources = {"task_e": {"notice_texts": (("statement", text),)},
               "prior_development_reference": {"statement_texts": (text,)}}
    request = _request(rows, sources=sources)
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    manifests = (gate.gated_sample_manifest(request, decision, natural),
                 gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, natural=natural,
                                            n_anchor_commitment=commitment.expected_record_commitment))
    for manifest in manifests:
        frame = {row["item_id"]: row for row in manifest["sample"]["frame"]}
        overlay = {row["statement_group_id"]: set(row["reasons"]) for row in manifest["policy_exclusions"]}
        assert set(frame[_alias("notice-group")]["exclusions"]) == {"task_e"}
        assert set(frame[_alias("statement-group")]["exclusions"]) == {"prior_development_reference"}
        assert overlay[_alias("notice-group")] == {"source_notice_fingerprint:task_e"}
        assert overlay[_alias("statement-group")] == {"source_statement_fingerprint:prior_development_reference"}
        assert text not in json.dumps(manifest)


def test_repeated_ids_and_unknown_inventory_fields_are_rejected():
    request = _request()
    bundle = _get_bundle(request, "task_e")
    payload = json.loads(bundle.inventory_bytes)
    payload["statement_ids"] = ["group1", "group1"]
    raw = gate.canonical_json_bytes(payload)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=raw, inventory_sha256=gate.sha256_bytes(raw))),
           "inventory_ids_invalid")
    payload["statement_ids"] = []
    payload["extra"] = "synthetic"
    raw = gate.canonical_json_bytes(payload)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=raw, inventory_sha256=gate.sha256_bytes(raw))),
           "inventory_schema_invalid")


def test_source_provenance_and_attestation_are_cryptographically_bound():
    request = _request()
    bundle = _get_bundle(request, "task_e")
    changed = replace(bundle.provenance, empty_rationale="A different synthetic review documents this empty source.")
    _issue(_with_bundle(request, bundle.category, replace(bundle, provenance=changed)), "provenance_hash_mismatch")
    attestation = replace(bundle.provenance.attestations[0], attester_identity="different-synthetic-attester")
    changed = replace(bundle.provenance, attestations=(attestation,))
    _issue(_with_bundle(request, bundle.category, replace(bundle, provenance=changed)), "provenance_hash_mismatch")
    other = _bundle(bundle.category, request.expected_events_sha256,
                    rationale="Another synthetic source review establishes a different empty-source rationale.")
    assert gate.assess_catalog(_with_bundle(request, bundle.category, other)).gate_commitment != gate.assess_catalog(request).gate_commitment


def test_regeneration_bytes_record_identity_and_hash_are_separately_bound():
    request = _request()
    bundle = _get_bundle(request, "task_e")
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, regenerated_inventory_bytes=bundle.regenerated_inventory_bytes + b"x")),
           "regeneration_hash_mismatch")
    different = b"synthetic different regenerated inventory"
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, regenerated_inventory_bytes=different,
                                regenerated_inventory_sha256=gate.sha256_bytes(different))),
           "regeneration_inventory_mismatch")
    changed_record = replace(bundle.regeneration, method_sha256=_digest("different synthetic method"))
    _issue(_with_bundle(request, bundle.category, replace(bundle, regeneration=changed_record)),
           "regeneration_record_hash_mismatch")
    wrong_events = replace(bundle.regeneration, events_sha256="1" * 64)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, regeneration=wrong_events,
                                regeneration_sha256=gate.sha256_bytes(gate.canonical_json_bytes(asdict(wrong_events))))),
           "regeneration_binding_mismatch")
    same_identity = replace(bundle.regeneration, identity=bundle.provenance.source_identity)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, regeneration=same_identity,
                                regeneration_sha256=gate.sha256_bytes(gate.canonical_json_bytes(asdict(same_identity))))),
           "regeneration_identity_not_separate")


def test_inventory_and_regeneration_bind_the_expected_events_digest():
    request = _request()
    bundle = _get_bundle(request, "task_e")
    payload = json.loads(bundle.inventory_bytes)
    payload["events_sha256"] = "1" * 64
    raw = gate.canonical_json_bytes(payload)
    _issue(_with_bundle(request, bundle.category,
                        replace(bundle, inventory_bytes=raw, inventory_sha256=gate.sha256_bytes(raw))),
           "inventory_events_mismatch")


def test_legacy_whole_field_hash_cannot_be_upgraded_without_recorded_token_count():
    phrase = "invented three word phrase"
    fragment = gate.fingerprint_fragment(phrase, min_tokens=3)
    assert fragment.sha256 == sampling.field_fingerprint(phrase)
    assert fragment.token_count == 4
    _issue(_request(sources={"guide_prompt_examples": {"whole": (fragment.sha256,)}}),
           "whole_field_token_counts_missing")
    _issue(_request(sources={"guide_prompt_examples": {
        "whole": (fragment.sha256,), "fragments": (fragment,), "fragment_support": False}}),
        "fragment_evidence_missing")
    _issue(_request(sources={"guide_prompt_examples": {
        "whole": (fragment.sha256,), "fragments": (replace(fragment, token_count=2),)}}),
        "fragment_token_count_invalid")
    with pytest.raises(ValueError, match="shorter"):
        gate.fingerprint_fragment("two words", min_tokens=3)


def test_fragment_counts_are_recomputed_from_hash_bound_synthetic_source_text():
    phrase = "invented three word phrase"
    fragment = gate.fingerprint_fragment(phrase, min_tokens=3)
    options = {"whole": (fragment.sha256,), "fragments": (fragment,), "fragment_texts": (phrase,)}
    request = _request(sources={"guide_prompt_examples": options})
    assert gate.assess_catalog(request).status == "ready"
    guessed = replace(fragment, token_count=fragment.token_count + 1)
    _issue(_request(sources={"guide_prompt_examples": {**options, "fragments": (guessed,)}}),
           "fragment_regeneration_mismatch")
    _issue(_request(sources={"guide_prompt_examples": {**options,
             "fragment_texts": ("different invented source phrase",)}}), "fragment_regeneration_mismatch")
    bundle = _get_bundle(request, "guide_prompt_examples")
    _issue(_with_bundle(request, bundle.category, replace(bundle, fragment_source_bytes=None)),
           "fragment_source_missing")
    equivalent_text = gate.canonical_json_bytes({"schema": gate.FRAGMENT_SOURCE_SCHEMA,
                                                 "phrases": ["Invented, THREE word phrase"]})
    _issue(_with_bundle(request, bundle.category, replace(bundle, fragment_source_bytes=equivalent_text)),
           "fragment_source_hash_mismatch")
    assert phrase not in repr(bundle) and phrase not in repr(request)


def test_policy_is_explicit_fixed_and_part_of_the_gate_identity():
    request = _request()
    _issue(replace(request, policy=replace(request.policy, min_fragment_tokens=2)), "policy_invalid")
    _issue(replace(request, policy=replace(request.policy, min_fragment_tokens=True)), "policy_invalid")
    _issue(replace(request, policy=replace(request.policy, fragment_mode="whole_only")), "policy_invalid")
    _issue(replace(request, policy=replace(request.policy, blank_mode="include_blank")), "policy_invalid")
    _issue(replace(request, policy=replace(request.policy, blank_anchor_category=[])), "policy_invalid")
    other = replace(request.policy, blank_anchor_category="task_e")
    assert gate.assess_catalog(replace(request, policy=other)).gate_commitment != gate.assess_catalog(request).gate_commitment


def _phrase_request() -> tuple[gate.CatalogRequest, str]:
    phrase = "Straße CAFÉ ﬁrm"
    fragment = gate.fingerprint_fragment(phrase, min_tokens=3)
    rows = [
        _row(1, availability="prefix STRASSE, Cafe\u0301 FIRM suffix"),
        _row(2, availability="a separate field", related="before Straße café firm after"),
        _row(3, availability=" -- . ", related="!!!", statement="synthetic invisible statement"),
        _row(4, availability="", related="ordinary remaining field"),
        _row(5, availability="separate", related="fields", statement="prefix strasse café firm suffix"),
        _row(6, availability="ordinary presentation", group="group6"),
        _row(7, availability="prefix STRASSE café firm suffix", group="group6"),
    ]
    rows.extend(_row(number, availability=f"mid November synthetic window {number}") for number in range(8, 80))
    request = _request(rows, sources={"guide_prompt_examples": {
        "whole": (fragment.sha256,), "fragments": (fragment,), "fragment_texts": (phrase,),
    }})
    return request, phrase


def test_fragment_windows_cover_unicode_case_punctuation_longer_and_one_of_two_fields():
    request, phrase = _phrase_request()
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    draw = gate.gated_select_n(request, decision, package="reduced")
    manifest = gate.gated_sample_manifest(request, decision, draw)
    flags = {item["statement_group_id"]: set(item["reasons"]) for item in manifest["policy_exclusions"]}
    for group in ("group1", "group2", "group5", "group6"):
        assert "policy_fragment:guide_prompt_examples" in flags[_alias(group)]
    assert "policy_blank_pair" in flags[_alias("group3")]
    assert _alias("group4") not in flags
    frame = {item["item_id"]: item for item in manifest["sample"]["frame"]}
    assert all(frame[_alias(group)]["selected_rank"] is None for group in ("group1", "group2", "group3", "group5", "group6"))
    assert "new_prompt_development" in frame[_alias("group3")]["exclusions"]
    assert "policy_blank_pair" in flags[_alias("group3")]  # The anchor is not a source-provenance claim.
    rendered = json.dumps(manifest, ensure_ascii=False)
    assert phrase not in rendered and "STRASSE, Cafe" not in rendered
    assert "synthetic invisible statement" not in rendered
    assert phrase not in repr(draw) and phrase not in json.dumps(gate.gate_receipt(request, decision), ensure_ascii=False)
    assert phrase not in str(asdict(decision)) and phrase not in str(asdict(draw))


def test_gated_n_and_c_share_policy_and_exclude_n_on_synthetic_rows():
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    n_manifest = gate.gated_sample_manifest(request, decision, natural)
    c_manifest = gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, natural=natural,
                                            n_anchor_commitment=commitment.expected_record_commitment)
    assert n_manifest["schema"] == c_manifest["schema"] == "followup-gated-sample-v4"
    n_ids = {row["item_id"] for row in n_manifest["sample"]["frame"] if row["selected_rank"] is not None}
    c_ids = {row["item_id"] for row in c_manifest["sample"]["frame"] if row["selected_rank"] is not None}
    assert len(n_ids) == 60 and c_ids and n_ids.isdisjoint(c_ids)
    assert n_ids.issubset({row["statement_group_id"] for row in c_manifest["n_wording_exclusions"]})
    assert c_manifest["sample"]["parent_sample_commitment"] == n_manifest["sample"]["sample_commitment"]
    assert n_manifest["gate_commitment"] == c_manifest["gate_commitment"] == decision.gate_commitment
    assert n_manifest["policy_overlay_commitment"] == c_manifest["policy_overlay_commitment"]
    assert sampling.private_commitment(request.alias_key, "gated_manifest", gate.canonical_json_bytes(
        {k: v for k, v in n_manifest.items() if k != "manifest_commitment"})) == n_manifest["manifest_commitment"]


def _source_fingerprint_rows() -> tuple[list[dict[str, str]], dict[str, dict], tuple[str, ...]]:
    notice = "invented previously exposed notice alpha"
    related = "invented related field alpha"
    statement = "invented previously exposed statement beta"
    shown_notice = _row(1, availability="early May visible notice group", group="notice-target")
    hidden_notice = _row(2, availability=notice, related=related, statement="different notice statement",
                         group="notice-target")
    shown_statement = _row(3, availability="early May visible statement group", group="statement-target")
    hidden_statement = _row(4, availability="different availability label", related="different related field",
                            statement=statement, group="statement-target")
    hidden_notice["availability_class"] = "available"
    hidden_statement["availability_class"] = "available"
    rows = [shown_notice, hidden_notice, shown_statement, hidden_statement]
    rows.extend(_row(number, availability=f"early May unrelated synthetic item {number}")
                for number in range(5, 115))
    notice_fp = sampling.notice_fingerprint(notice, related)
    statement_event = sampling.project_event(hidden_statement)
    statement_fp = statement_event.statement_wording_sha256
    assert statement_fp is not None and statement_fp not in {notice_fp, statement_event.wording_sha256}
    sources = {
        "pilot_check_literal": {"notices": (notice_fp,), "notice_texts": ((notice, related),)},
        "task_e": {"notices": (notice_fp,), "notice_texts": ((notice, related),)},
        "prior_development_reference": {"notices": (statement_fp,), "statement_texts": (statement,)},
    }
    return rows, sources, (notice, related, statement, shown_notice["availability_text"],
                           shown_statement["availability_text"])


def test_source_notice_and_statement_fingerprints_propagate_from_hidden_presentations():
    rows, sources, texts = _source_fingerprint_rows()
    projected = tuple(sampling.project_event(row) for row in rows)
    shown = {event.statement_group_id: event for event in sampling.display_events(projected)}
    assert shown["notice-target"].event_id == "event1"
    assert shown["statement-target"].event_id == "event3"
    request = _request(rows, sources=sources)
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    n_manifest = gate.gated_sample_manifest(request, decision, natural)
    c_manifest = gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, natural=natural,
                                            n_anchor_commitment=commitment.expected_record_commitment)
    for manifest in (n_manifest, c_manifest):
        frame = {row["item_id"]: row for row in manifest["sample"]["frame"]}
        overlay = {row["statement_group_id"]: set(row["reasons"]) for row in manifest["policy_exclusions"]}
        assert set(frame[_alias("notice-target")]["exclusions"]) == {"pilot_check_literal", "task_e"}
        assert set(frame[_alias("statement-target")]["exclusions"]) == {"prior_development_reference"}
        assert overlay[_alias("notice-target")] == {"source_notice_fingerprint:pilot_check_literal",
                                                    "source_notice_fingerprint:task_e"}
        assert overlay[_alias("statement-target")] == {"source_statement_fingerprint:prior_development_reference"}
        assert frame[_alias("notice-target")]["selected_rank"] is None
        assert frame[_alias("statement-target")]["selected_rank"] is None
        rendered = json.dumps(manifest, ensure_ascii=False)
        assert all(text not in rendered for text in texts)
    n_frame = {row["item_id"]: row for row in n_manifest["sample"]["frame"]}
    c_frame = {row["item_id"]: row for row in c_manifest["sample"]["frame"]}
    unrelated = next(_alias(row["statement_group_id"]) for row in rows
                     if row["statement_group_id"].startswith("group")
                     and n_frame[_alias(row["statement_group_id"])]["selected_rank"] is None
                     and not n_frame[_alias(row["statement_group_id"])]["exclusions"])
    assert not c_frame[unrelated]["exclusions"]


def test_source_fingerprint_propagation_and_draws_are_input_order_independent():
    rows, sources, _ = _source_fingerprint_rows()

    def run(input_rows):
        request = _request(input_rows, sources=sources)
        decision = gate.assess_catalog(request)
        natural = gate.gated_select_n(request, decision, package="reduced")
        commitment = _commitment(request, decision, natural)
        convention = gate.gated_select_c(request, decision, package="reduced", natural=natural,
                                         n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)
        return (decision, gate.gated_sample_manifest(request, decision, natural),
                gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, natural=natural,
                                           n_anchor_commitment=commitment.expected_record_commitment))

    first_gate, first_n, first_c = run(rows)
    reverse_gate, reverse_n, reverse_c = run(list(reversed(rows)))
    assert first_gate.gate_commitment != reverse_gate.gate_commitment  # Compressed byte identities differ.
    for left, right in ((first_n, reverse_n), (first_c, reverse_c)):
        assert left["policy_exclusions"] == right["policy_exclusions"]
        assert left["n_wording_exclusions"] == right["n_wording_exclusions"]
        assert left["sample"]["frame_commitment"] == right["sample"]["frame_commitment"]
        assert left["sample"]["sample_commitment"] == right["sample"]["sample_commitment"]


def _n_to_c_presentation_rows() -> tuple[list[dict[str, str]], str, tuple[str, ...], tuple[str, ...], str, tuple[str, ...]]:
    rows = [_row(i, availability=f"early May synthetic item {i}") for i in range(120)]
    order = sorted(range(len(rows)), key=lambda i: (
        sampling._draw_key(sampling.FOLLOWUP_SEED, "january-n-episode-v1", rows[i]["episode_id"]),
        rows[i]["episode_id"],
    ))
    n_index = order[0]
    notice_hh, statement_hh, notice_hd, statement_hd, notice_dh, statement_dh = order[-6:]
    unrelated = order[-7]
    n_base = rows[n_index]

    def hidden(number, owner, *, availability, related, statement):
        row = _row(number, group=owner["statement_group_id"], availability=availability,
                   related=related, statement=statement)
        row["availability_class"] = "available"
        return row

    n_hidden_notice = hidden(200, n_base, availability="invented N paired notice alpha",
                             related="invented N paired related alpha", statement="N unique statement alpha")
    n_hidden_statement = hidden(201, n_base, availability="N unique label", related="N unique field",
                                statement="invented N shared statement beta")
    extra = [n_hidden_notice, n_hidden_statement]
    extra.append(hidden(202, rows[notice_hh], availability=n_hidden_notice["availability_text"],
                        related=n_hidden_notice["related_text"], statement="candidate unique statement alpha"))
    extra.append(hidden(203, rows[statement_hh], availability="candidate distinct label",
                        related="candidate distinct field", statement=n_hidden_statement["statement_text"]))
    rows[notice_hd] = {**rows[notice_hd], "availability_text": n_hidden_notice["availability_text"],
                       "related_text": n_hidden_notice["related_text"], "statement_text": "candidate visible only"}
    rows[statement_hd] = {**rows[statement_hd], "statement_text": n_hidden_statement["statement_text"]}
    extra.append(hidden(204, rows[notice_dh], availability=n_base["availability_text"],
                        related=n_base["related_text"], statement="candidate nonvisible unique statement"))
    extra.append(hidden(205, rows[statement_dh], availability="another candidate label",
                        related="another candidate field", statement=n_base["statement_text"]))
    notice_groups = tuple(rows[i]["statement_group_id"] for i in (notice_hh, notice_hd, notice_dh))
    statement_groups = tuple(rows[i]["statement_group_id"] for i in (statement_hh, statement_hd, statement_dh))
    texts = (n_hidden_notice["availability_text"], n_hidden_notice["related_text"],
             n_hidden_statement["statement_text"], n_base["availability_text"])
    return rows + extra, n_base["statement_group_id"], notice_groups, statement_groups, rows[unrelated]["statement_group_id"], texts


def test_gated_c_uses_retained_n_all_presentation_wordings_without_reselecting(monkeypatch):
    rows, n_group, notice_groups, statement_groups, unrelated, texts = _n_to_c_presentation_rows()
    projected = tuple(sampling.project_event(row) for row in rows)
    shown = {event.statement_group_id: event for event in sampling.display_events(projected)}
    for row in rows:
        if row["event_id"].startswith("event20") and int(row["event_id"][5:]) >= 200:
            assert shown[row["statement_group_id"]].event_id != row["event_id"]
    request = _request(rows)
    reversed_request = _request(list(reversed(rows)))
    decision = gate.assess_catalog(request)
    reversed_decision = gate.assess_catalog(reversed_request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    reversed_natural = gate.gated_select_n(reversed_request, reversed_decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    reversed_commitment = _commitment(reversed_request, reversed_decision, reversed_natural)
    n_manifest = gate.gated_sample_manifest(request, decision, natural)
    selected_n = {row["item_id"] for row in n_manifest["sample"]["frame"] if row["selected_rank"] is not None}
    assert _alias(n_group) in selected_n
    assert not selected_n.intersection(_alias(group) for group in (*notice_groups, *statement_groups, unrelated))
    assert natural.sample_commitment == reversed_natural.sample_commitment

    calls = []
    def profile(frame, event, arg):
        if event == "call" and frame.f_code is sampling.select_n.__code__:
            calls.append(True)
    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                         n_anchor_commitment=commitment.expected_record_commitment)
        reversed_convention = gate.gated_select_c(reversed_request, reversed_decision, package="reduced",
                                                   natural=reversed_natural, n_commitment=reversed_commitment,
                                                   n_anchor_commitment=reversed_commitment.expected_record_commitment)
        assert gate.gated_sample_manifest(request, decision, natural) == n_manifest
        c_manifest = gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, natural=natural,
                                                n_anchor_commitment=commitment.expected_record_commitment)
        reverse_manifest = gate.gated_sample_manifest(reversed_request, reversed_decision, reversed_convention,
                                                     n_commitment=reversed_commitment, natural=reversed_natural,
                                                     n_anchor_commitment=reversed_commitment.expected_record_commitment)
    finally:
        sys.setprofile(previous)
    assert not calls
    frame = {row["item_id"]: row for row in c_manifest["sample"]["frame"]}
    overlay = {row["statement_group_id"]: set(row["reasons"]) for row in c_manifest["n_wording_exclusions"]}
    for group in notice_groups:
        assert overlay[_alias(group)] == {"assigned_n_notice_fingerprint"}
        assert "selected_n_wording" in frame[_alias(group)]["exclusions"] and frame[_alias(group)]["selected_rank"] is None
    for group in statement_groups:
        assert overlay[_alias(group)] == {"assigned_n_statement_fingerprint"}
        assert "selected_n_wording" in frame[_alias(group)]["exclusions"] and frame[_alias(group)]["selected_rank"] is None
    assert _alias(unrelated) not in overlay and not frame[_alias(unrelated)]["exclusions"]
    assert c_manifest["sample"]["parent_sample_commitment"] == natural.sample_commitment
    assert c_manifest["n_wording_exclusions"] == reverse_manifest["n_wording_exclusions"]
    assert c_manifest["sample"]["frame_commitment"] == reverse_manifest["sample"]["frame_commitment"]
    assert c_manifest["sample"]["sample_commitment"] == reverse_manifest["sample"]["sample_commitment"]
    assert n_manifest["n_wording_exclusions"] == []
    for manifest in (n_manifest, c_manifest):
        assert all(text not in json.dumps(manifest, ensure_ascii=False) for text in texts)
    changed_rows = [row for row in rows if row["event_id"] != "event200"]
    with pytest.raises(ValueError, match="no longer matches"):
        gate.gated_select_c(replace(request, compressed_events=_compressed(changed_rows)), decision,
                            package="reduced", natural=natural, n_commitment=commitment,
                            n_anchor_commitment=commitment.expected_record_commitment)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_select_c(request, decision, package="reduced", natural=replace(natural, _proof=None),
                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_select_c(request, decision, package="reduced", natural=pickle.loads(pickle.dumps(natural)),
                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_select_c(request, decision, package="reduced",
                            natural=replace(natural, _manifest_bytes=natural._manifest_bytes + b" "),
                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)


def test_tampered_or_stale_ready_decisions_and_draws_fail_closed():
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    changed_request = replace(request, compressed_events=_compressed([_row(200)]))
    with pytest.raises(ValueError, match="no longer matches"):
        gate.gated_select_n(changed_request, decision, package="reduced")
    forged = gate.CatalogDecision("ready", (), decision.gate_commitment, decision.policy_commitment)
    with pytest.raises(ValueError, match="not ready"):
        gate.gated_select_n(request, forged, package="reduced")
    with pytest.raises(ValueError, match="same catalog and package"):
        gate.gated_select_c(request, decision, package="full", natural=natural, n_commitment=commitment,
                            n_anchor_commitment=commitment.expected_record_commitment)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_sample_manifest(request, decision, replace(natural, sample_commitment="invalid"))
    original = _get_bundle(request, "task_e")
    other = _bundle(original.category, request.expected_events_sha256,
                    rationale="A new synthetic evidence record documents this distinct empty inventory.")
    different_gate = gate.assess_catalog(_with_bundle(request, original.category, other))
    assert different_gate.status == "ready" and different_gate.gate_commitment != decision.gate_commitment
    with pytest.raises(ValueError, match="same catalog and package"):
        gate.gated_select_c(_with_bundle(request, original.category, other), different_gate,
                            package="reduced", natural=natural, n_commitment=commitment,
                            n_anchor_commitment=commitment.expected_record_commitment)


def test_c_requires_independent_pre_access_commitment_and_rejects_changes():
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    anchor = commitment.expected_record_commitment
    with pytest.raises(TypeError):
        gate.gated_select_c(request, decision, package="reduced", natural=natural)
    with pytest.raises(TypeError):
        gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment)
    with pytest.raises(ValueError, match="commitment"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                            n_anchor_commitment="invalid")
    for changed in (replace(commitment, expected_record_commitment="invalid"),
                    replace(commitment, expected_n_manifest_commitment="invalid"),
                    replace(commitment, record_bytes=commitment.record_bytes + b" ")):
        with pytest.raises(ValueError, match="commitment"):
            gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=changed,
                                n_anchor_commitment=anchor)
    record = json.loads(commitment.record_bytes)
    altered_identity = "changed.synthetic.lock.evidence"
    record["evidence_identity"] = sampling.private_alias(request.alias_key, "evidence", altered_identity)
    altered_bytes = gate.canonical_json_bytes(record)
    altered = gate.FrozenNCommitment(altered_bytes, sampling.private_commitment(request.alias_key, "n_lock_record", altered_bytes),
                                     commitment.expected_n_manifest_commitment, altered_identity, commitment.evidence_sha256)
    with pytest.raises(ValueError, match="commitment"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=altered,
                            n_anchor_commitment=anchor)
    record = json.loads(commitment.record_bytes)
    record["before_reference_and_evaluation"] = False
    raw = gate.canonical_json_bytes(record)
    late = gate.FrozenNCommitment(raw, sampling.private_commitment(request.alias_key, "n_lock_record", raw),
                                  commitment.expected_n_manifest_commitment, commitment.evidence_identity,
                                  commitment.evidence_sha256)
    with pytest.raises(ValueError, match="commitment"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=late,
                            n_anchor_commitment=late.expected_record_commitment)
    record["before_reference_and_evaluation"] = True
    record["alias_key_commitment"] = sampling.alias_key_commitment(b"z" * 32)
    raw = gate.canonical_json_bytes(record)
    wrong_key = gate.FrozenNCommitment(raw, sampling.private_commitment(request.alias_key, "n_lock_record", raw),
                                       commitment.expected_n_manifest_commitment, commitment.evidence_identity,
                                       commitment.evidence_sha256)
    with pytest.raises(ValueError, match="commitment"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=wrong_key,
                            n_anchor_commitment=wrong_key.expected_record_commitment)
    record = json.loads(commitment.record_bytes)
    record["protocol_commitment"] = sampling.private_commitment(request.alias_key, "protocol", b"synthetic change")
    raw = gate.canonical_json_bytes(record)
    wrong_protocol = gate.FrozenNCommitment(raw, sampling.private_commitment(request.alias_key, "n_lock_record", raw),
                                            commitment.expected_n_manifest_commitment, commitment.evidence_identity,
                                            commitment.evidence_sha256)
    with pytest.raises(ValueError, match="commitment"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=wrong_protocol,
                            n_anchor_commitment=wrong_protocol.expected_record_commitment)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=anchor)
    with pytest.raises(ValueError, match="retained N"):
        gate.gated_sample_manifest(request, decision, convention, n_commitment=commitment, n_anchor_commitment=anchor)
    with pytest.raises(ValueError, match="commitment"):
        gate.gated_sample_manifest(request, decision, convention, natural=natural, n_anchor_commitment=anchor)


@pytest.mark.parametrize("change", ["n_targets", "c_quotas", "strata", "part", "week", "month", "year",
                                    "short_number", "relative", "may_verb", "part_flags", "display_seed",
                                    "followup_seed", "display_tag", "n_episode_tag", "n_notice_tag", "c_tag",
                                    "sampling_implementation", "gate_implementation", "function_defaults", "policy"])
def test_n_lock_binds_fixed_n_c_protocol_and_runtime_implementation(change, monkeypatch):
    request = _request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    record = json.loads(commitment.record_bytes)
    assert record["protocol_commitment"] == decision.protocol_commitment
    assert record["protocol_commitment"] == gate.gate_receipt(request, decision)["protocol_commitment"]
    current_request = request
    if change == "n_targets":
        monkeypatch.setattr(sampling, "N_TARGETS", {**sampling.N_TARGETS, "reduced": 61})
    elif change == "c_quotas":
        monkeypatch.setattr(sampling, "C_QUOTAS", {**sampling.C_QUOTAS, "reduced": (11, 12, 3, 3)})
    elif change == "strata":
        monkeypatch.setattr(sampling, "STRATA", tuple(reversed(sampling.STRATA)))
    elif change in {"part", "week", "month", "year", "short_number", "relative", "may_verb"}:
        name = {"part": "_PART", "week": "_WEEK", "month": "_MONTH_RE", "year": "_YEAR",
                "short_number": "_SHORT_NUMBER", "relative": "_RELATIVE", "may_verb": "_MAY_VERB"}[change]
        monkeypatch.setattr(sampling, name, re.compile("synthetic-changed-expression"))
    elif change == "part_flags":
        monkeypatch.setattr(sampling, "_PART", re.compile(sampling._PART.pattern, sampling._PART.flags ^ re.IGNORECASE))
    elif change in {"display_seed", "followup_seed"}:
        name = "DISPLAY_SEED" if change == "display_seed" else "FOLLOWUP_SEED"
        monkeypatch.setattr(sampling, name, getattr(sampling, name) + 1)
    elif change in {"display_tag", "n_episode_tag", "n_notice_tag", "c_tag"}:
        name = {"display_tag": "DISPLAY_TAG", "n_episode_tag": "N_EPISODE_TAG",
                "n_notice_tag": "N_NOTICE_TAG", "c_tag": "C_TAG"}[change]
        monkeypatch.setattr(sampling, name, getattr(sampling, name) + "-changed")
    elif change == "sampling_implementation":
        monkeypatch.setattr(sampling, "convention_stratum", lambda event: None)
    elif change == "gate_implementation":
        monkeypatch.setattr(gate, "_effective_sources", lambda *args: ((), b"[]"))
    elif change == "function_defaults":
        monkeypatch.setattr(sampling._frame, "__defaults__", (frozenset({"invented"}), frozenset()))
    else:
        current_request = replace(request, policy=replace(request.policy, min_fragment_tokens=4))
    with pytest.raises(ValueError, match="no longer matches|not ready"):
        gate.gated_select_c(current_request, decision, package="reduced", natural=natural,
                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)


def test_n_lock_rejects_changed_runtime_closure_used_by_c(monkeypatch):
    def classifier(force_part):
        def classify(event):
            return "part_of_month" if force_part else "week_expression"

        # Both installed versions have identical code, name, defaults and
        # module identity; only the captured synthetic policy value changes.
        classify.__module__ = sampling.__name__
        return classify

    rows = [_row(i, availability=f"ordinary synthetic case {i}") for i in range(100)]
    request = _request(rows)
    monkeypatch.setattr(sampling, "convention_stratum", classifier(False))
    decision = gate.assess_catalog(request)
    assert decision.status == "ready"
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    monkeypatch.setattr(sampling, "convention_stratum", classifier(True))
    fresh = gate.assess_catalog(request)
    assert fresh.status == "ready" and fresh.protocol_commitment != decision.protocol_commitment
    with pytest.raises(ValueError, match="no longer matches|not ready"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural,
                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)


def test_n_lock_rejects_mutation_of_a_c_classifier_closure(monkeypatch):
    setting = {"part": False}

    def classify(event):
        return "part_of_month" if setting["part"] else "week_expression"

    classify.__module__ = sampling.__name__
    monkeypatch.setattr(sampling, "convention_stratum", classify)
    request = _request([_row(i, availability=f"ordinary invented case {i}") for i in range(100)])
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    setting["part"] = True
    assert gate.assess_catalog(request).protocol_commitment != decision.protocol_commitment
    with pytest.raises(ValueError, match="no longer matches|not ready"):
        gate.gated_select_c(request, decision, package="reduced", natural=natural,
                            n_commitment=commitment, n_anchor_commitment=commitment.expected_record_commitment)


def test_opaque_runtime_closure_blocks_catalog_instead_of_hashing_only_its_type(monkeypatch):
    opaque = object()

    def classify(event):
        return "part_of_month" if opaque else "week_expression"

    classify.__module__ = sampling.__name__
    monkeypatch.setattr(sampling, "convention_stratum", classify)
    _issue(_request(), "protocol_invalid")


def test_class_valued_closure_cells_bind_contents_not_the_name_alone():
    """Same-qualname rebinding used to produce identical name-only records, so the 6
    November 2026 re-review could swap classifiers without moving the commitment; the
    record now binds class contents, and identical-content classes stay identical."""
    class Shared:
        def stratum(self, event):
            return "part_of_month"

    def first(event, classifier=Shared):
        return classifier().stratum(event)

    class Shared:  # same module and qualname, different method body
        def stratum(self, event):
            return "week_expression"

    def second(event, classifier=Shared):
        return classifier().stratum(event)

    first.__module__ = second.__module__ = sampling.__name__
    assert gate._function_record(first) != gate._function_record(second)

    class Alike:
        def stratum(self, event):
            return "part_of_month"

    class Alike:  # same module and qualname, identical method body
        def stratum(self, event):
            return "part_of_month"

    def one(event, classifier=Alike):
        return classifier().stratum(event)

    def two(event, classifier=Alike):
        return classifier().stratum(event)

    one.__module__ = two.__module__ = sampling.__name__
    assert gate._function_record(one) == gate._function_record(two)


def test_invalid_protocol_is_not_misreported_as_an_alias_failure(monkeypatch):
    request = _request()
    monkeypatch.setattr(sampling, "_PART", "not-an-expression")
    _issue(request, "protocol_invalid")


def _replace_draw_manifest(draw: gate.GatedDraw, payload: dict) -> gate.GatedDraw:
    sample = payload["sample"]
    sample["manifest_commitment"] = sampling.private_commitment(_SYNTHETIC_ALIAS_KEY, "sample_manifest",
        gate.canonical_json_bytes({key: value for key, value in sample.items() if key != "manifest_commitment"}))
    payload["manifest_commitment"] = sampling.private_commitment(_SYNTHETIC_ALIAS_KEY, "gated_manifest",
        gate.canonical_json_bytes({key: value for key, value in payload.items() if key != "manifest_commitment"}))
    raw = gate.canonical_json_bytes(payload)
    copied_proof = replace(draw._proof, manifest_commitment=sampling.private_commitment(_SYNTHETIC_ALIAS_KEY, "draw_manifest", raw))
    return replace(draw, _manifest_bytes=raw, _proof=copied_proof)


@pytest.mark.parametrize("field", ["episode_rank", "within_episode_rank", "within_stratum_rank", "stratum",
                                   "item_id", "event_id", "episode_id", "visible_input_alias", "wording_alias",
                                   "statement_wording_alias", "selected_draw_key_alias", "selected_rank", "exclusions"])
def test_c_rejects_rehashed_n_replacement_and_rebuilds_every_primitive(field, monkeypatch):
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    payload = json.loads(natural._manifest_bytes)
    row = next(item for item in payload["sample"]["frame"] if item["selected_rank"] is not None)
    if field in {"episode_rank", "within_episode_rank", "selected_rank"}:
        row[field] += 1
    elif field == "within_stratum_rank":
        row[field] = 1
    elif field == "stratum":
        row[field] = "part_of_month"
    elif field == "exclusions":
        row[field] = ["task_e"]
    else:
        kind = {"item_id": "item", "event_id": "event", "episode_id": "episode", "visible_input_alias": "visible",
                "wording_alias": "notice", "statement_wording_alias": "statement",
                "selected_draw_key_alias": "draw"}[field]
        row[field] = sampling.private_alias(request.alias_key, kind, "synthetic-forged-value")
    forged = _replace_draw_manifest(natural, payload)

    with pytest.raises(ValueError, match="commitment"):
        gate.gated_select_c(request, decision, package="reduced", natural=forged, n_commitment=commitment,
                            n_anchor_commitment=commitment.expected_record_commitment)
    # A newly supplied synthetic lock cannot make inconsistent primitives valid.
    forged_commitment = _commitment_for_bytes(request, decision, "reduced", forged._manifest_bytes)
    with pytest.raises(ValueError, match="retained N"):
        gate.gated_select_c(request, decision, package="reduced", natural=forged, n_commitment=forged_commitment,
                            n_anchor_commitment=forged_commitment.expected_record_commitment)
    with pytest.raises(ValueError, match="retained N"):
        gate.gated_sample_manifest(request, decision, forged)


@pytest.mark.parametrize("field", ["schema", "cohort", "package", "target", "shortfall", "events_commitment",
                                   "exclusions_commitment", "frame_commitment", "sample_commitment", "parent_sample_commitment",
                                   "requested_quotas", "achieved_quotas", "fingerprint_version", "alias_version",
                                   "alias_key_commitment"])
def test_rehashed_n_header_primitives_are_rebuilt_or_rejected(field, monkeypatch):
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    payload = json.loads(natural._manifest_bytes)
    sample = payload["sample"]
    if field in {"target", "shortfall"}:
        sample[field] += 1
    elif field in {"requested_quotas", "achieved_quotas"}:
        sample[field] = [["part_of_month", 1]]
    elif field == "cohort":
        sample[field] = "C"
    elif field == "package":
        sample[field] = "full"
    elif field in {"schema", "fingerprint_version", "alias_version"}:
        sample[field] = "synthetic-wrong-version"
    else:
        sample[field] = _digest("synthetic-wrong-header")
    forged = _replace_draw_manifest(natural, payload)

    with pytest.raises(ValueError):
        gate.gated_sample_manifest(request, decision, forged)


def test_rehashed_c_manifest_cannot_export_a_raw_id_even_with_a_copied_marker():
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    payload = json.loads(convention._manifest_bytes)
    raw = "invented-raw-id-equals-notice"
    payload["sample"]["frame"][0]["item_id"] = raw
    forged = _replace_draw_manifest(convention, payload)
    assert raw not in repr(forged)
    with pytest.raises(ValueError, match="retained C") as error:
        gate.gated_sample_manifest(request, decision, forged, n_commitment=commitment, natural=natural,
                                   n_anchor_commitment=commitment.expected_record_commitment)
    assert raw not in str(error.value)


def test_rehashed_c_manifest_cannot_substitute_a_different_eligible_item(monkeypatch):
    rows = [_row(i, availability=f"early May distinct synthetic case {i}") for i in range(150)]
    request = _request(rows)
    before = gate._implementation_record()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    after = gate._implementation_record()
    def changed(left, right, prefix=""):
        if isinstance(left, dict) and isinstance(right, dict):
            return [path for key in sorted(left.keys() | right.keys())
                    for path in changed(left.get(key), right.get(key), prefix + "/" + key)]
        return [] if left == right else [prefix]
    assert before == after, changed(before, after)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    payload = json.loads(convention._manifest_bytes)
    frame_rows = payload["sample"]["frame"]
    chosen = next(row for row in frame_rows if row["selected_rank"] is not None)
    replacement = next(row for row in frame_rows if row["selected_rank"] is None and not row["exclusions"]
                       and row["stratum"] == chosen["stratum"])
    _, state = gate._ready_state(request, decision)
    sources, _ = gate._effective_sources(state, request.policy, request.alias_key)
    natural_payload = gate._checked_draw(request, decision, natural)
    retained_n = gate._restore_n_from_manifest(request, state, sources, natural, natural_payload)
    ids = frozenset(item.event.statement_group_id for item in retained_n.selected)
    notice_groups, statement_groups = sampling._n_wording_groups(state.events, ids)
    frame = sampling._frame(state.events, sources, ids, notice_groups | statement_groups)
    index = sampling.private_alias_index(state.events, alias_key=request.alias_key)
    replacement_id = index.resolve("item", replacement["item_id"])
    key = sampling._draw_key(sampling.FOLLOWUP_SEED, "january-c-v1/" + replacement["stratum"], replacement_id)
    replacement["selected_rank"] = chosen["selected_rank"]
    replacement["selected_draw_key_alias"] = sampling.private_alias(request.alias_key, "draw", key)
    chosen["selected_rank"] = None
    chosen["selected_draw_key_alias"] = None
    selected = gate._retained_selected(request, state.events, frame, frame_rows, cohort="C")
    forged_sample_sha256 = sampling._sample_hash(selected)
    forged_sample_commitment = sampling.digest_commitment(request.alias_key, "sample", forged_sample_sha256)
    payload["sample"]["sample_commitment"] = forged_sample_commitment
    forged = _replace_draw_manifest(replace(convention, sample_commitment=forged_sample_commitment), payload)
    with pytest.raises(ValueError, match="retained C"):
        gate.gated_sample_manifest(request, decision, forged, n_commitment=commitment, natural=natural,
                                   n_anchor_commitment=commitment.expected_record_commitment)


def test_runtime_implementation_identity_is_stable_without_changes():
    before = gate._implementation_record()
    request = _request([_row(i, availability=f"early May stable case {i}") for i in range(150)])
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    _commitment(request, decision, natural)
    after = gate._implementation_record()

    def differences(left, right, prefix=""):
        if isinstance(left, dict) and isinstance(right, dict):
            return [path for key in sorted(left.keys() | right.keys())
                    for path in differences(left.get(key), right.get(key), prefix + "/" + key)]
        return [] if left == right else [prefix]

    assert before == after, differences(before, after)


def test_copied_markers_cannot_export_injected_raw_text_in_receipts_or_overlays():
    request, _ = _phrase_request()
    decision = gate.assess_catalog(request)
    natural = gate.gated_select_n(request, decision, package="reduced")
    commitment = _commitment(request, decision, natural)
    convention = gate.gated_select_c(request, decision, package="reduced", natural=natural, n_commitment=commitment,
                                     n_anchor_commitment=commitment.expected_record_commitment)
    raw = "invented-raw-id-equals-notice"
    receipt = gate.gate_receipt(request, decision)
    receipt["injected"] = raw
    receipt_bytes = gate.canonical_json_bytes(receipt)
    forged_decision = replace(decision, gate_commitment=sampling.private_commitment(request.alias_key, "gate", receipt_bytes),
                              _receipt_bytes=receipt_bytes)
    with pytest.raises(ValueError, match="no longer matches") as error:
        gate.gate_receipt(request, forged_decision)
    assert raw not in str(error.value)
    n_payload = json.loads(natural._manifest_bytes)
    n_payload["injected"] = raw
    forged_n = _replace_draw_manifest(natural, n_payload)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_sample_manifest(request, decision, forged_n)
    n_payload = json.loads(natural._manifest_bytes)
    n_payload["n_wording_exclusions"] = [{"statement_group_id": raw, "reasons": ["assigned_n_notice_fingerprint"]}]
    n_payload["n_wording_overlay_commitment"] = sampling.private_commitment(request.alias_key, "n_wording_overlay",
                                                                          gate.canonical_json_bytes(n_payload["n_wording_exclusions"]))
    forged_n = _replace_draw_manifest(replace(natural, n_wording_overlay_commitment=n_payload["n_wording_overlay_commitment"]),
                                     n_payload)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_sample_manifest(request, decision, forged_n)
    c_payload = json.loads(convention._manifest_bytes)
    c_payload["n_wording_exclusions"].append({"statement_group_id": raw, "reasons": ["assigned_n_notice_fingerprint"]})
    c_payload["n_wording_overlay_commitment"] = sampling.private_commitment(request.alias_key, "n_wording_overlay",
                                                                          gate.canonical_json_bytes(c_payload["n_wording_exclusions"]))
    forged_c = _replace_draw_manifest(replace(convention, n_wording_overlay_commitment=c_payload["n_wording_overlay_commitment"]),
                                     c_payload)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_sample_manifest(request, decision, forged_c, n_commitment=commitment, natural=natural,
                                   n_anchor_commitment=commitment.expected_record_commitment)
    c_payload = json.loads(convention._manifest_bytes)
    c_payload["policy_exclusions"].append({"statement_group_id": raw, "reasons": ["policy_blank_pair"]})
    c_payload["policy_overlay_commitment"] = sampling.private_commitment(request.alias_key, "policy_overlay",
                                                                       gate.canonical_json_bytes(c_payload["policy_exclusions"]))
    forged_c = _replace_draw_manifest(replace(convention, policy_overlay_commitment=c_payload["policy_overlay_commitment"]),
                                     c_payload)
    with pytest.raises(ValueError, match="does not match"):
        gate.gated_sample_manifest(request, decision, forged_c, n_commitment=commitment, natural=natural,
                                   n_anchor_commitment=commitment.expected_record_commitment)
