"""Invented first-sight rows and deterministic sampling checks."""

import csv
import gzip
import hashlib
import io
import json
import pickle
from dataclasses import asdict, replace

import pytest

from analysis.coling.followup import sampling as sampling_module
from analysis.coling.followup.sampling import (
    C_QUOTAS, REQUIRED_EXCLUSIONS, SOURCE_FIELDS, STRATA, ExclusionSource,
    convention_stratum, display_events, field_fingerprint, notice_fingerprint,
    project_event, project_open_events, sample_manifest as _sample_manifest, select_c as _select_c, select_n as _select_n,
)

_SYNTHETIC_ALIAS_KEY = bytes(range(32))


def select_n(events, sources, *, package):
    return _select_n(events, sources, package=package, _gate_token=sampling_module._DRAW_CAPABILITY)


def select_c(events, sources, *, package, natural_draw):
    return _select_c(events, sources, package=package, natural_draw=natural_draw,
                     _gate_token=sampling_module._DRAW_CAPABILITY)


def sample_manifest(draw, *, events_sha256, alias_key):
    return _sample_manifest(draw, events_sha256=events_sha256, alias_key=alias_key,
                            _gate_token=sampling_module._DRAW_CAPABILITY)


def test_public_direct_draws_fail_closed():
    with pytest.raises(ValueError, match="direct draws are disabled"):
        sampling_module.select_n([], (), package="reduced")
    with pytest.raises(ValueError, match="direct draws are disabled"):
        sampling_module.select_c([], (), package="reduced", natural_draw=None)
    legacy = hashlib.sha256(json.dumps(["statement", "invented legacy value"], separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(ValueError, match="direct draws are disabled"):
        sampling_module.select_n(events(1), catalog(task_e={"notice_fingerprints": frozenset({legacy})}),
                                 package="reduced")
    draw = select_n(events(1), catalog(), package="reduced")
    with pytest.raises(ValueError, match="direct manifests are disabled"):
        sampling_module.sample_manifest(draw, events_sha256="d" * 64, alias_key=_SYNTHETIC_ALIAS_KEY)


def letters(n):
    result = ""
    while True:
        result = chr(ord("a") + n % 26) + result
        n //= 26
        if not n:
            return result


def source_row(index=0, *, episode=None, group=None, event=None, text=None, **extra):
    suffix = letters(index)
    values = {
        "event_id": event or f"event-{suffix}", "statement_group_id": group or f"statement-{suffix}",
        "episode_id": episode or f"episode-{suffix}", "listing": "shortage",
        "status_at_statement": "current", "availability_class": "unavailable",
        "event_date": "2028-02-29", "revision_index": "0", "generic_name": "Fictional product",
        "company_name": "Fictional issuer", "presentation": "One unit",
        "therapeutic_category": "Invented category", "initial_posting_date": "2027-12-01",
        "type_of_update": "revised", "availability_text": text or f"Recovery estimated in July; batch {suffix}",
        "related_text": "", "statement_text": text or f"Recovery estimated in July; batch {suffix}",
        "reason_for_shortage": "Invented reason",
    }
    values.update(extra)
    return values


def catalog(**overrides):
    sources = []
    for name in sorted(REQUIRED_EXCLUSIONS):
        values = dict(name=name, statement_ids=frozenset(), notice_fingerprints=frozenset(),
                      whole_field_fingerprints=frozenset(), provenance_sha256="a" * 64,
                      verified_complete=True)
        values.update(overrides.get(name, {}))
        sources.append(ExclusionSource(**values))
    return tuple(sources)


def events(count, *, episodes_per_two=False, only_part=False):
    rows = []
    for i in range(count):
        suffix = letters(i)
        phrases = [f"Early May 2028; batch {suffix}", f"First week of June 2028; batch {suffix}",
                   f"Recovery in July; batch {suffix}", f"Recovery in 12 weeks; batch {suffix}"]
        text = phrases[0 if only_part else i % len(phrases)]
        episode = "episode-" + letters(i // 2 if episodes_per_two else i)
        rows.append(project_event(source_row(i, episode=episode, text=text)))
    return tuple(rows)


class AllowlistOnly(dict):
    def __getitem__(self, key):
        assert key in SOURCE_FIELDS, f"non-allowlisted field accessed: {key}"
        return super().__getitem__(key)


def test_projection_and_model_input_never_export_hidden_fields():
    row = AllowlistOnly(source_row(0, outcome="forbidden-outcome", later_capture="later-value",
                                  stated_end="rule-reference", model_correct="model-answer"))
    event = project_event(row)
    assert set(asdict(event)) == set(SOURCE_FIELDS)
    model_input = event.model_input()
    assert set(model_input) == {"update_date", "notice_text"}
    serialized = json.dumps(model_input)
    for hidden in ("forbidden-outcome", "later-value", "rule-reference", "model-answer",
                   "Fictional issuer", "Fictional product"):
        assert hidden not in serialized


def compressed_csv(rows, header):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return gzip.compress(stream.getvalue().encode(), mtime=0)


def test_open_event_projection_checks_exact_hash_and_discards_extra_columns():
    row = source_row(0)
    header = list(SOURCE_FIELDS) + ["outcome", "stated_end", "later_capture"]
    raw = compressed_csv([[row[field] for field in SOURCE_FIELDS] + ["secret", "reference", "later"]], header)
    digest = hashlib.sha256(raw).hexdigest()
    projected = project_open_events(raw, expected_sha256=digest)
    assert len(projected) == 1 and projected[0] == project_event(row)
    assert "secret" not in repr(projected) and "reference" not in repr(projected)
    with pytest.raises(ValueError, match="identity"):
        project_open_events(raw, expected_sha256="0" * 64)
    duplicate = compressed_csv([], list(SOURCE_FIELDS) + [SOURCE_FIELDS[0]])
    with pytest.raises(ValueError, match="header"):
        project_open_events(duplicate, expected_sha256=hashlib.sha256(duplicate).hexdigest())
    short = compressed_csv([["too short"]], list(SOURCE_FIELDS))
    with pytest.raises(ValueError, match="number of fields"):
        project_open_events(short, expected_sha256=hashlib.sha256(short).hexdigest())
    corrupt = b"not gzip"
    with pytest.raises(ValueError, match="compressed"):
        project_open_events(corrupt, expected_sha256=hashlib.sha256(corrupt).hexdigest())


def test_display_rows_are_seeded_and_independent_of_input_order():
    a = project_event(source_row(1, group="group", event="event-a", episode="episode",
                                 availability_class="available"))
    b = project_event(source_row(2, group="group", event="event-b", episode="episode"))
    c = project_event(source_row(3, group="group", event="event-c", episode="episode"))
    original = display_events([a, b, c])
    assert original == display_events([c, a, b])
    assert original[0] in (b, c)
    key = lambda e: (hashlib.sha256(f"20261001\x1fdisplay/group\x1f{e.event_id}".encode()).hexdigest(), e.event_id)
    assert original[0] == min((b, c), key=key)
    with pytest.raises(ValueError, match="duplicate"):
        display_events([a, a])


def test_n_draw_is_episode_balanced_stable_and_reports_shortfalls():
    corpus = events(250, episodes_per_two=True)
    n = select_n(corpus, catalog(), package="full")
    reversed_n = select_n(reversed(corpus), reversed(catalog()), package="full")
    assert len(n.selected) == 100 and n.shortfall == 0
    assert len({item.event.episode_id for item in n.selected}) == 100
    assert len({item.event.statement_group_id for item in n.selected}) == 100
    assert n.selected == reversed_n.selected
    assert n.frame_sha256 == reversed_n.frame_sha256 and n.sample_sha256 == reversed_n.sample_sha256
    small = select_n(events(7, episodes_per_two=True), catalog(), package="reduced")
    assert len(small.selected) == 4 and small.shortfall == 56


def test_exclusions_include_ids_exact_wording_and_quoted_fields():
    rows = [project_event(source_row(i)) for i in range(5)]
    field = field_fingerprint(rows[2].availability_text)
    sources = catalog(
        task_e={"statement_ids": frozenset({rows[0].statement_group_id})},
        inspected_item_outputs={"notice_fingerprints": frozenset({rows[1].wording_sha256})},
        guide_prompt_examples={"whole_field_fingerprints": frozenset({field})},
    )
    result = select_n(rows, sources, package="full")
    reasons = {entry.event.statement_group_id: entry.exclusions for entry in result.frame}
    assert reasons[rows[0].statement_group_id] == ("task_e",)
    assert reasons[rows[1].statement_group_id] == ("inspected_item_outputs",)
    assert reasons[rows[2].statement_group_id] == ("guide_prompt_examples",)
    assert len(result.selected) == 2
    assert notice_fingerprint("Recovery, July!", "") == notice_fingerprint("recovery july", "")
    assert field_fingerprint("EARLY–May") == field_fingerprint("early may")


def test_statement_fingerprint_excludes_repeated_text_with_different_bare_labels():
    prior = project_event(source_row(1, availability_text="Out of stock", related_text="Recovery in July",
                                     statement_text="Recovery in July"))
    repeated = project_event(source_row(2, availability_text="Limited supply", related_text="Recovery in July",
                                        statement_text="Recovery in July"))
    assert prior.wording_sha256 != repeated.wording_sha256
    assert prior.statement_wording_sha256 == repeated.statement_wording_sha256
    sources = catalog(task_e={"notice_fingerprints": prior.exclusion_fingerprints})
    result = select_n([prior, repeated], sources, package="full")
    assert not result.selected and result.shortfall == 100


def test_versioned_domains_prevent_legacy_notice_statement_preimage_collision():
    text = "invented collision value"
    legacy_notice = hashlib.sha256(json.dumps(["statement", text], separators=(",", ":")).encode()).hexdigest()
    legacy_statement = hashlib.sha256(json.dumps(["statement", text], separators=(",", ":")).encode()).hexdigest()
    assert legacy_notice == legacy_statement
    notice = notice_fingerprint("statement", text)
    statement = sampling_module.statement_fingerprint(text)
    assert statement is not None and len({notice, statement, field_fingerprint(text), legacy_notice}) == 4
    first = project_event(source_row(1, availability_text="statement", related_text=text,
                                     statement_text="different invented statement"))
    second = project_event(source_row(2, availability_text="another invented label", related_text="different",
                                      statement_text=text))
    result = select_n([first, second], catalog(task_e={"notice_fingerprints": frozenset({notice})}), package="full")
    reasons = {entry.event.statement_group_id: entry.exclusions for entry in result.frame}
    assert reasons[first.statement_group_id] == ("task_e",)
    assert not reasons[second.statement_group_id]


def test_sampler_catalog_identity_binds_fingerprint_version(monkeypatch):
    before = sampling_module._catalog(catalog())[1]
    monkeypatch.setattr(sampling_module, "FINGERPRINT_VERSION", "synthetic-other-version")
    assert sampling_module._catalog(catalog())[1] != before


def test_private_aliases_hide_id_equal_to_notice_and_preserve_private_mapping():
    raw = "invented-id-equals-notice"
    event = project_event(source_row(1, group=raw, event=raw, episode=raw, text=raw))
    draw = select_n([event], catalog(), package="reduced")
    manifest = sample_manifest(draw, events_sha256="d" * 64, alias_key=_SYNTHETIC_ALIAS_KEY)
    row = manifest["frame"][0]
    assert raw not in json.dumps(manifest) and raw not in repr(event) and raw not in repr(draw)
    assert raw not in repr(catalog(task_e={"statement_ids": frozenset({raw})}))
    assert len({row["item_id"], row["event_id"], row["episode_id"]}) == 3
    index = sampling_module.private_alias_index([event], alias_key=_SYNTHETIC_ALIAS_KEY)
    assert raw not in repr(index)
    for kind in ("item", "event", "episode"):
        assert index.resolve(kind, row[kind + "_id"]) == raw
    assert manifest["alias_key_commitment"] == sampling_module.alias_key_commitment(_SYNTHETIC_ALIAS_KEY)
    with pytest.raises(TypeError):
        sample_manifest(draw, events_sha256="d" * 64)
    with pytest.raises(ValueError, match="alias key"):
        sample_manifest(draw, events_sha256="d" * 64, alias_key=b"x" * 31)
    with pytest.raises(ValueError, match="unknown"):
        sampling_module.private_alias_index([event], alias_key=b"z" * 32).resolve("item", row["item_id"])


def test_manifest_content_alias_collision_fails_closed(monkeypatch):
    draw = select_n(events(2), catalog(), package="reduced")
    actual_alias = sampling_module.private_alias

    def colliding(key, kind, value):
        return "synthetic-collision" if kind == "visible" else actual_alias(key, kind, value)

    monkeypatch.setattr(sampling_module, "private_alias", colliding)
    with pytest.raises(ValueError, match="alias collision"):
        sample_manifest(draw, events_sha256="d" * 64, alias_key=_SYNTHETIC_ALIAS_KEY)


def test_incomplete_or_missing_exclusion_inventory_blocks_all_draws():
    incomplete = catalog(task_e={"verified_complete": False})
    with pytest.raises(ValueError, match="verified"):
        select_n(events(3), incomplete, package="full")
    with pytest.raises(ValueError, match="exactly once"):
        select_n(events(3), catalog()[:-1], package="full")
    with pytest.raises(ValueError, match="exactly once"):
        select_n(events(3), catalog() + (catalog()[0],), package="full")
    with pytest.raises(ValueError, match="package"):
        select_n(events(3), catalog(), package="custom")


def test_fixed_stratum_overlap_and_conservative_missing_year_rule():
    make = lambda text: project_event(source_row(1, text=text))
    assert convention_stratum(make("early May 2028, first week of June")) == "part_of_month"
    assert convention_stratum(make("first week of June, in 12 weeks")) == "week_expression"
    assert convention_stratum(make("July; in 12 weeks")) == "missing_year"
    assert convention_stratum(make("release in 12 weeks")) == "numbered_relative"
    assert convention_stratum(make("release in June 2028")) is None
    assert convention_stratum(make("release June 15")) is None
    assert convention_stratum(make("no timing statement")) is None
    assert convention_stratum(make("Supply may be available later")) is None
    assert convention_stratum(make("May experience a delay")) is None
    assert convention_stratum(make("Recovery in May")) == "missing_year"


def test_c_quota_draw_excludes_n_and_preserves_episode_cap():
    corpus = events(400, episodes_per_two=True)
    exclusions = catalog()
    n = select_n(corpus, exclusions, package="reduced")
    c = select_c(corpus, exclusions, package="reduced", natural_draw=n)
    assert len(c.selected) == 30 and c.shortfall == 0
    assert dict(c.requested_quotas) == dict(zip(STRATA, C_QUOTAS["reduced"], strict=True))
    assert dict(c.achieved_quotas) == dict(c.requested_quotas)
    n_ids = {item.event.statement_group_id for item in n.selected}
    n_wording = {item.event.wording_sha256 for item in n.selected}
    assert not n_ids.intersection(item.event.statement_group_id for item in c.selected)
    assert not n_wording.intersection(item.event.wording_sha256 for item in c.selected)
    assert all(sum(item.event.episode_id == episode for item in c.selected) <= 2
               for episode in {item.event.episode_id for item in c.selected})
    assert c.parent_sample_sha256 == n.sample_sha256
    reordered = select_c(reversed(corpus), reversed(exclusions), package="reduced", natural_draw=n)
    assert c.selected == reordered.selected and c.sample_sha256 == reordered.sample_sha256


def test_c_excludes_any_presentation_matching_any_retained_n_presentation_without_redraw(monkeypatch):
    corpus = list(events(120, only_part=True))
    order = sorted(range(len(corpus)), key=lambda i: (
        sampling_module._draw_key(sampling_module.FOLLOWUP_SEED, "january-n-episode-v1", corpus[i].episode_id),
        corpus[i].episode_id,
    ))
    n_index = order[0]
    notice_hh, statement_hh, notice_hd, statement_hd, notice_dh, statement_dh = order[-6:]
    unrelated = order[-7]
    n_base = corpus[n_index]

    def hidden(index, owner, *, availability, related, statement):
        return project_event(source_row(
            index, group=owner.statement_group_id, episode=owner.episode_id, event=f"invented-hidden-{index}",
            availability_class="available", availability_text=availability, related_text=related,
            statement_text=statement,
        ))

    n_hidden_notice = hidden(200, n_base, availability="invented paired notice alpha",
                             related="invented paired related alpha", statement="n only statement alpha")
    n_hidden_statement = hidden(201, n_base, availability="n only visible label",
                                related="n only other field", statement="invented shared statement beta")
    extra = [n_hidden_notice, n_hidden_statement]
    extra.append(hidden(202, corpus[notice_hh], availability=n_hidden_notice.availability_text,
                        related=n_hidden_notice.related_text, statement="candidate only statement alpha"))
    extra.append(hidden(203, corpus[statement_hh], availability="candidate distinct label",
                        related="candidate distinct field", statement=n_hidden_statement.statement_text))
    corpus[notice_hd] = replace(corpus[notice_hd], availability_text=n_hidden_notice.availability_text,
                                related_text=n_hidden_notice.related_text, statement_text="candidate visible only")
    corpus[statement_hd] = replace(corpus[statement_hd], statement_text=n_hidden_statement.statement_text)
    extra.append(hidden(204, corpus[notice_dh], availability=n_base.availability_text,
                        related=n_base.related_text, statement="candidate nonvisible unique statement"))
    extra.append(hidden(205, corpus[statement_dh], availability="other candidate label",
                        related="other candidate field", statement=n_base.statement_text))
    corpus = tuple(corpus + extra)
    shown = {event.statement_group_id: event for event in display_events(corpus)}
    assert shown[n_base.statement_group_id] == n_base
    assert all(shown[event.statement_group_id].event_id != event.event_id for event in extra)

    exclusions = catalog()
    natural = select_n(corpus, exclusions, package="reduced")
    original_selection, original_hash = natural.selected, natural.sample_sha256
    assigned = {item.event.statement_group_id for item in natural.selected}
    assert n_base.statement_group_id in assigned
    candidate_indexes = (notice_hh, statement_hh, notice_hd, statement_hd, notice_dh, statement_dh, unrelated)
    assert all(corpus[index].statement_group_id not in assigned for index in candidate_indexes)

    def no_redraw(*args, **kwargs):
        raise AssertionError("C must use the retained N selection, not call select_n")

    monkeypatch.setattr(sampling_module, "select_n", no_redraw)
    convention = select_c(corpus, exclusions, package="reduced", natural_draw=natural)
    reversed_convention = select_c(reversed(corpus), reversed(exclusions), package="reduced", natural_draw=natural)
    assert natural.selected == original_selection and natural.sample_sha256 == original_hash
    assert convention.frame_sha256 == reversed_convention.frame_sha256
    assert convention.sample_sha256 == reversed_convention.sample_sha256
    frame = {entry.event.statement_group_id: entry for entry in convention.frame}
    chosen = {item.event.statement_group_id for item in convention.selected}
    for index in candidate_indexes[:-1]:
        group = corpus[index].statement_group_id
        assert "selected_n_wording" in frame[group].exclusions
        assert "selected_n" not in frame[group].exclusions and group not in chosen
    assert not frame[corpus[unrelated].statement_group_id].exclusions
    assert convention.parent_sample_sha256 == original_hash
    serialized = json.dumps(sample_manifest(convention, events_sha256="d" * 64, alias_key=_SYNTHETIC_ALIAS_KEY))
    for text in (n_hidden_notice.availability_text, n_hidden_notice.related_text,
                 n_hidden_statement.statement_text, n_base.availability_text):
        assert text not in serialized
    with pytest.raises(ValueError, match="does not match"):
        select_c(corpus, exclusions, package="reduced", natural_draw=replace(natural, _natural_proof=None))
    with pytest.raises(ValueError, match="does not match"):
        select_c(corpus, exclusions, package="reduced", natural_draw=pickle.loads(pickle.dumps(natural)))
    forged = replace(natural, selected=natural.selected[:-1], shortfall=natural.shortfall + 1,
                     sample_sha256=sampling_module._sample_hash(natural.selected[:-1]))
    with pytest.raises(ValueError, match="does not match"):
        select_c(corpus, exclusions, package="reduced", natural_draw=forged)
    for removed in (n_hidden_notice, extra[2]):
        missing_hidden = tuple(event for event in corpus if event.event_id != removed.event_id)
        assert display_events(missing_hidden) == display_events(corpus)
        with pytest.raises(ValueError, match="does not match"):
            select_c(missing_hidden, exclusions, package="reduced", natural_draw=natural)


def test_c_redistributes_in_fixed_order_and_reports_unfilled_target():
    corpus = events(80, only_part=True)
    n = select_n(corpus, catalog(), package="reduced")
    c = select_c(corpus, catalog(), package="reduced", natural_draw=n)
    assert len(c.selected) == 20 and c.shortfall == 10
    assert dict(c.achieved_quotas) == {"part_of_month": 20, "week_expression": 0,
                                      "missing_year": 0, "numbered_relative": 0}


def test_c_rejects_forged_or_stale_n_frame_and_exclusions():
    corpus = events(160)
    n = select_n(corpus, catalog(), package="reduced")
    with pytest.raises(ValueError, match="same package"):
        select_c(corpus, catalog(), package="full", natural_draw=n)
    with pytest.raises(ValueError, match="does not match"):
        select_c(corpus[:-1], catalog(), package="reduced", natural_draw=n)
    changed = replace(n, sample_sha256="0" * 64)
    with pytest.raises(ValueError, match="does not match"):
        select_c(corpus, catalog(), package="reduced", natural_draw=changed)
    altered_sources = catalog(task_e={"provenance_sha256": "b" * 64})
    with pytest.raises(ValueError, match="does not match"):
        select_c(corpus, altered_sources, package="reduced", natural_draw=n)


def test_frame_manifest_retains_exclusions_ranks_and_no_reference_or_outcome():
    corpus = events(240, episodes_per_two=True)
    n = select_n(corpus, catalog(), package="reduced")
    c = select_c(corpus, catalog(), package="reduced", natural_draw=n)
    n_manifest = sample_manifest(n, events_sha256="d" * 64, alias_key=_SYNTHETIC_ALIAS_KEY)
    c_manifest = sample_manifest(c, events_sha256="d" * 64, alias_key=_SYNTHETIC_ALIAS_KEY)
    assert len(n_manifest["frame"]) == len(n.frame)
    assert len(c_manifest["frame"]) == len(c.frame)
    assert sum(row["selected_rank"] is not None for row in n_manifest["frame"]) == len(n.selected)
    assert sum(row["selected_rank"] is not None for row in c_manifest["frame"]) == len(c.selected)
    assert all(row["episode_rank"] is not None and row["within_episode_rank"] is not None
               for row in n_manifest["frame"] if not row["exclusions"])
    assert all(row["within_stratum_rank"] is not None
               for row in c_manifest["frame"] if row["stratum"] is not None)
    assert c_manifest["parent_sample_commitment"] == sampling_module.digest_commitment(
        _SYNTHETIC_ALIAS_KEY, "sample", n.sample_sha256)
    text = json.dumps(c_manifest)
    assert "reference_answer" not in text and "outcome" not in text and "model_correct" not in text
    with pytest.raises(ValueError, match="draw hashes"):
        sample_manifest(replace(n, sample_sha256="0" * 64), events_sha256="d" * 64,
                        alias_key=_SYNTHETIC_ALIAS_KEY)
