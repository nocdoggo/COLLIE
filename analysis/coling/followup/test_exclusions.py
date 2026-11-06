"""Synthetic sample-list identity and exclusion-inventory checks."""

import hashlib
from types import SimpleNamespace

import pytest

from analysis.coling.followup import e7, exclusions
from analysis.coling.followup.exclusions import guide_prompt_source, known_registered_sources
from analysis.coling.followup.test_sampling import project_event, source_row


def raw_ids(*ids):
    return ("event_id,statement_group_id,thread_id\n" + "".join(
        f"event-{item},{item},thread-{item}\n" for item in ids)).encode()


def inputs(monkeypatch):
    files = {"early": raw_ids("statement-b"), "other": raw_ids("statement-c")}
    specs = {"early": (hashlib.sha256(files["early"]).hexdigest()[:16], 1, "pilot_check_literal"),
             "other": (hashlib.sha256(files["other"]).hexdigest()[:16], 1, "prior_development_reference")}
    monkeypatch.setattr(exclusions, "REGISTERED_SAMPLE_SPECS", specs)
    task = b"statement_group_id\nstatement-d\n"
    monkeypatch.setattr(e7, "TASK_E_CONFIRMED_SHA256", hashlib.sha256(task).hexdigest())
    monkeypatch.setattr(e7, "TASK_E_CONFIRMED_COUNT", 1)
    events = [project_event(source_row(i)) for i in range(1, 5)]
    return files, task, events


def test_known_lists_produce_id_and_text_exclusions_without_a_draw(monkeypatch):
    files, task, events = inputs(monkeypatch)
    sources = known_registered_sources(files, task_e_bytes=task, events=events)
    by_name = {source.name: source for source in sources}
    assert set(by_name) == {"pilot_check_literal", "prior_development_reference", "task_e"}
    assert by_name["pilot_check_literal"].statement_ids == frozenset({"statement-b"})
    assert by_name["task_e"].statement_ids == frozenset({"statement-d"})
    assert events[0].wording_sha256 in by_name["pilot_check_literal"].notice_fingerprints
    assert all(source.verified_complete for source in sources)


def test_hash_mismatch_missing_list_and_missing_event_refuse_inventory(monkeypatch):
    files, task, events = inputs(monkeypatch)
    with pytest.raises(ValueError, match="all named"):
        known_registered_sources({"early": files["early"]}, task_e_bytes=task, events=events)
    with pytest.raises(ValueError, match="recorded identity"):
        known_registered_sources({**files, "early": files["early"] + b"x"}, task_e_bytes=task, events=events)
    with pytest.raises(ValueError, match="absent"):
        known_registered_sources(files, task_e_bytes=task, events=events[1:])


def test_guide_examples_and_canary_are_excluded_without_reference_fields(monkeypatch):
    text = ('# Fictional guide\n\n## 3. Reading\n"Recovery in July"\n\n'
            '## 7. Edits\n"Later review update"\n\n## Appendix A. Examples\n'
            '| Fictional product | Fictional issuer | 2028-02-29 |\n\n## Appendix B. End\n')
    raw = text.encode()
    monkeypatch.setattr(exclusions, "FROZEN_GUIDE_SHA256", hashlib.sha256(raw).hexdigest())
    event = project_event(source_row(1))
    canary = SimpleNamespace(generic_name=event.generic_name, date_of_update=event.event_date,
                             availability_information=event.availability_text,
                             related_information=event.related_text)
    monkeypatch.setattr(exclusions.study_read, "CANARY_ITEM", canary)
    source = guide_prompt_source(raw, events=[event], harness_sha256=exclusions.FROZEN_HARNESS_SHA256,
                                 events_sha256=exclusions.FROZEN_EVENTS_SHA256)
    assert source.name == "guide_prompt_examples"
    assert source.statement_ids == frozenset({event.statement_group_id})
    assert event.wording_sha256 in source.notice_fingerprints
    assert len(source.whole_field_fingerprints) == 2
    with pytest.raises(ValueError, match="registration"):
        guide_prompt_source(raw, events=[event], harness_sha256="0" * 64,
                            events_sha256=exclusions.FROZEN_EVENTS_SHA256)


def test_guide_source_refuses_unmatched_examples(monkeypatch):
    text = ('# Guide\n\n## 3. Reading\n"Recovery in July"\n\n## 7. Edits\n"Later review update"\n\n'
            '## Appendix A. Examples\n| Missing product | Fictional issuer | 2028-02-29 |\n\n## Appendix B. End\n')
    raw = text.encode()
    monkeypatch.setattr(exclusions, "FROZEN_GUIDE_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="guide example is absent"):
        guide_prompt_source(raw, events=[project_event(source_row(1))],
                            harness_sha256=exclusions.FROZEN_HARNESS_SHA256,
                            events_sha256=exclusions.FROZEN_EVENTS_SHA256)
