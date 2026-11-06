"""Prepare known exclusion inventories from permitted sample-list bytes.

No paths are opened and no model outputs, rule readings, or outcome columns are
read. The registered sample inventories and original guide/canary inventory
are not sufficient to authorize an N/C draw. Previously inspected outputs and
new prompt development still require complete, documented inventories.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Iterable, Mapping

from analysis.coling import audit_sample, corpus, read as study_read
from .e7 import confirmed_references
from .records import require_identifier, require_sha256
from .sampling import ExclusionSource, SourceEvent, field_fingerprint


REGISTERED_SAMPLE_SPECS = {
    "pilot": ("edd0c9c477b83f79", 20, "pilot_check_literal"),
    "check": ("eb80b0fc1ceb2485", 20, "pilot_check_literal"),
    "reserve": ("6be05e4f1a000cbd", 20, "pilot_check_literal"),
    "literal": ("05fcaf84b77406d7", 120, "pilot_check_literal"),
    "outcome_train_sample": ("53a1c2449c26a233", 56, "prior_development_reference"),
    "incontext_pool": ("ba42ebab7b3d1bb6", 50, "prior_development_reference"),
    "dev_prompt": ("b404466c9a22a1b6", 60, "prior_development_reference"),
    "pair_seeds": ("17caf511bf2bf3e1", 100, "prior_development_reference"),
}
FROZEN_GUIDE_SHA256 = "ce58129993b31d33944a9aa54195a9aa91fb60f09446631925a9b6eda468d8fb"
FROZEN_HARNESS_SHA256 = "54d171783601e72994f960cbe7b5adba157f6061ba3c9a1da30fd23e23be244f"
FROZEN_EVENTS_SHA256 = "d8d970a91691e702bacc27ae4d0605122a4170d275f7786bf066212a8d8aa145"


def _ids(raw: bytes, *, prefix: str, count: int) -> tuple[tuple[str, ...], str]:
    if not isinstance(raw, bytes):
        raise TypeError("registered sample input must be bytes")
    digest = hashlib.sha256(raw).hexdigest()
    if not digest.startswith(prefix):
        raise ValueError("registered sample file does not match its recorded identity")
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        header = next(rows)
        if len(header) != len(set(header)) or "statement_group_id" not in header:
            raise ValueError("registered sample lacks a unique statement ID column")
        position = header.index("statement_group_id")
        ids = []
        for row in rows:
            if len(row) != len(header):
                raise ValueError("registered sample row has the wrong width")
            item_id = row[position]
            require_identifier(item_id, "statement_group_id")
            ids.append(item_id)
    except (UnicodeError, StopIteration, csv.Error) as error:
        raise ValueError("registered sample is malformed") from error
    if len(ids) != count:
        raise ValueError("registered sample count differs from the record")
    return tuple(ids), digest


def known_registered_sources(
    sample_files: Mapping[str, bytes], *, task_e_bytes: bytes, events: Iterable[SourceEvent],
) -> tuple[ExclusionSource, ...]:
    """Build the three known exclusion classes, without drawing an evaluation sample."""
    if not isinstance(sample_files, Mapping) or set(sample_files) != set(REGISTERED_SAMPLE_SPECS):
        raise ValueError("all named registered sample lists are required")
    groups: dict[str, set[str]] = {"pilot_check_literal": set(), "prior_development_reference": set(),
                                   "task_e": set()}
    provenance: dict[str, dict[str, str]] = {name: {} for name in groups}
    for name, (prefix, count, category) in REGISTERED_SAMPLE_SPECS.items():
        ids, digest = _ids(sample_files[name], prefix=prefix, count=count)
        groups[category].update(ids)
        provenance[category][name] = digest
    confirmed = confirmed_references(task_e_bytes)
    groups["task_e"].update(confirmed.item_ids)
    provenance["task_e"]["confirmed_reference_list"] = confirmed.sha256

    event_ids = set()
    wording_by_group: dict[str, set[str]] = {}
    for event in events:
        if not isinstance(event, SourceEvent):
            raise TypeError("events must be allowlisted first-sight records")
        if event.event_id in event_ids:
            raise ValueError("duplicate first-sight event ID")
        event_ids.add(event.event_id)
        wording_by_group.setdefault(event.statement_group_id, set()).update(event.exclusion_fingerprints)
    sources = []
    for category in sorted(groups):
        missing = groups[category] - set(wording_by_group)
        if missing:
            raise ValueError("a registered exclusion ID is absent from the open events frame")
        wordings = frozenset(wording for item in groups[category] for wording in wording_by_group[item])
        encoded = json.dumps(provenance[category], sort_keys=True, separators=(",", ":")).encode()
        sources.append(ExclusionSource(category, frozenset(groups[category]), wordings, frozenset(),
                                       hashlib.sha256(encoded).hexdigest(), True))
    return tuple(sources)


def guide_prompt_source(
    guide_bytes: bytes, *, events: Iterable[SourceEvent], harness_sha256: str, events_sha256: str,
) -> ExclusionSource:
    """Identify original guide examples, quoted phrases, and the frozen prompt canary.

    The code uses only first-sight fields and visible canary text. It does not
    consult the canary's stored reference period or any rule or model reading.
    """
    require_sha256(harness_sha256, "harness source hash")
    require_sha256(events_sha256, "open events hash")
    if (not isinstance(guide_bytes, bytes) or hashlib.sha256(guide_bytes).hexdigest() != FROZEN_GUIDE_SHA256
            or harness_sha256 != FROZEN_HARNESS_SHA256 or events_sha256 != FROZEN_EVENTS_SHA256):
        raise ValueError("guide, harness, or open events identity differs from the registration")
    try:
        guide = guide_bytes.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("the guide must be UTF-8") from error
    declared = set(audit_sample.guide_exclusions(guide))
    if not declared:
        raise ValueError("the registered guide examples are missing")
    phrases = audit_sample.guide_phrases(guide)
    if not phrases:
        raise ValueError("the registered guide phrases are missing")
    events = tuple(events)
    if any(not isinstance(event, SourceEvent) for event in events):
        raise TypeError("events must be allowlisted first-sight records")
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("first-sight event IDs must be unique")
    def identity(event: SourceEvent) -> tuple[str, str, str]:
        return corpus.norm_text(event.generic_name), corpus.norm_text(event.company_name), event.event_date
    present = {identity(event) for event in events}
    if declared - present:
        raise ValueError("at least one registered guide example is absent from the open events")
    canary = study_read.CANARY_ITEM
    inside = corpus.norm_text(f"{canary.availability_information} || {canary.related_information}")
    canary_keys = {identity(event) for event in events
                   if corpus.norm_text(event.generic_name) == corpus.norm_text(canary.generic_name)
                   and event.event_date == canary.date_of_update
                   and corpus.norm_text(event.statement_text)
                   and corpus.norm_text(event.statement_text) in inside}
    if not canary_keys:
        raise ValueError("the registered prompt canary is absent from the open events")
    wanted = declared | canary_keys
    example_texts = {(corpus.norm_text(event.generic_name), corpus.norm_text(event.company_name),
                      corpus.norm_text(event.statement_text))
                     for event in events if identity(event) in wanted}
    excluded = [event for event in events if
                (corpus.norm_text(event.generic_name), corpus.norm_text(event.company_name),
                 corpus.norm_text(event.statement_text)) in example_texts]
    ids = frozenset(event.statement_group_id for event in excluded)
    wordings = frozenset(wording for event in excluded for wording in event.exclusion_fingerprints)
    phrase_hashes = frozenset(field_fingerprint(phrase) for phrase in phrases)
    provenance = hashlib.sha256(json.dumps({"guide_sha256": FROZEN_GUIDE_SHA256,
                                            "harness_sha256": harness_sha256,
                                            "events_sha256": events_sha256},
                                           sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ExclusionSource("guide_prompt_examples", ids, wordings, phrase_hashes, provenance, True)
