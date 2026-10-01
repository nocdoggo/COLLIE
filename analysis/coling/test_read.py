"""Tests for :mod:`analysis.coling.read`, with a fake transport only: no call leaves the machine.

Every test runs behind the fixture ``sealed_off``: a network connection or a key lookup fails
the test, and the module's repository is a folder that is not one, so no test reads the tags of
the real repository or writes into its git directory.

Usage (from the repository root)::

    python -m pytest analysis/coling/test_read.py -q
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

import analysis.coling.read as rd
from collie.llm import DiskCache
from collie.llm.client import DecodingConfig, EndpointConfig, RawResponse


@pytest.fixture(autouse=True)
def sealed_off(tmp_path_factory, monkeypatch) -> None:
    """What no test may do, made impossible for every test: open a network connection, read an
    API key (from the environment or from a key file), or use the real repository, whose tags
    clear paid calls and whose git directory holds the shared-roots file."""

    def no_network(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")

    def no_key(self):
        raise AssertionError("a test tried to read an API key")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(EndpointConfig, "resolve_key", no_key)
    for name in list(os.environ):
        if name.endswith("_API_KEY") or name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(rd, "REPO", tmp_path_factory.mktemp("not-a-repository"))


LITERAL_OK = json.dumps(
    {
        "statement_type": "recovery",
        "interval": {"start": "2020-04-01", "end": "2020-04-30"},
        "certainty": "estimated",
        "stale": False,
        "quote": "Expected recovery April 2020",
    }
)
PREDICTIVE_OK = json.dumps(
    {
        "p_by_horizon_a": 0.3,
        "p_by_horizon_b": 0.6,
        "days_to_recovery": {"q10": 20, "q50": 80, "q80": 150, "q90": 200, "q95": 365},
    }
)


def make_item(**changes) -> rd.ReadItem:
    base = rd.ReadItem(
        item_id="i1",
        generic_name="Anagrelide Hydrochloride Capsules",
        company_name="Teva Pharmaceuticals",
        presentation="1 MG 100 Capsules (NDC 0172-5240-60)",
        date_of_update="2020-03-17",
        therapeutic_category="Hematology",
        initial_posting_date="2019-11-22",
        type_of_update="Reverified",
        availability_information="Product on backorder",
        related_information="Expected recovery April 2020. Teva is working with FDA.",
        reason_for_shortage="Demand increase for the drug",
        stated_end="2020-04-30",
        form="a month and year",
        revision="second",
    )
    return replace(base, **changes)


class FakeInner:
    """Stands in for the live client behind the real guard; replies are scripted."""

    def __init__(self, replies, *, prompt_tokens=500, completion_tokens=60, hidden=0) -> None:
        self.replies = replies if callable(replies) else list(replies)
        self.calls: list[tuple[str, DecodingConfig, str | None]] = []
        self.tokens = (prompt_tokens, completion_tokens, hidden)

    @property
    def model_id(self) -> str:
        return "fake"

    def complete_metered(self, prompt, *, decoding, system=None) -> RawResponse:
        self.calls.append((prompt, decoding, system))
        reply = self.replies(prompt) if callable(self.replies) else self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        p, c, h = self.tokens
        return RawResponse(text=reply, prompt_tokens=p, completion_tokens=c, total_tokens=p + c + h)


class FakeSDK:
    """Stands in for the SDK client inside the real :class:`rd.RouteCheckedClient`: every
    response echoes a model id and, like OpenRouter, names a provider."""

    def __init__(self, replies, *, model, provider="DeepInfra", metadata=None, tokens=(500, 60)):
        self.replies = replies if callable(replies) else list(replies)
        self.model, self.provider, self.metadata, self.tokens = model, provider, metadata, tokens
        self.calls: list[dict] = []
        self.chat = self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["messages"][-1]["content"]
        reply = self.replies(prompt) if callable(self.replies) else self.replies.pop(0)
        p, c = self.tokens
        return SimpleNamespace(
            model=self.model,
            provider=self.provider,
            openrouter_metadata=self.metadata,
            usage=SimpleNamespace(prompt_tokens=p, completion_tokens=c, total_tokens=p + c),
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
        )


LLAMA = "meta-llama/llama-3.3-70b-instruct"
PINNED = {
    "llama-3.3-70b": rd.Route(LLAMA, "deepinfra/turbo", "fp8", (0.10, 0.32, "2026-10-01")),
    "deepseek-v3": rd.Route(
        "deepseek/deepseek-chat", "deepinfra/fp4", "fp4", (0.32, 0.89, "2026-10-01")
    ),
}
RealClient = rd.RouteCheckedClient


def git(repo: Path, *args: str) -> None:
    """A git command in a temporary repository. ``GIT_*`` variables are dropped, so that a
    variable such as ``GIT_DIR`` (set when the tests run from a git hook) can never turn a
    commit or a tag made here into one in the real repository."""
    quiet = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "gpg.format=openpgp"]
    quiet += ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    subprocess.run(["git", *quiet, *args], cwd=repo, check=True, capture_output=True, env=env)


def make_repo(path: Path, *tags: str) -> Path:
    """A temporary git repository with one commit and the given tags on it."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "-q", "--allow-empty", "-m", "one")
    for tag in tags:
        git(path, "tag", tag)
    return path


@pytest.fixture
def live_ready(tmp_path: Path, monkeypatch) -> Path:
    """What a live run needs besides its arguments, with no network: a repository that carries
    both tags, two filled routes, and the pilot sentences settled (as saying nothing)."""
    repo = make_repo(tmp_path / "repo", rd.REGISTRATION_TAG, rd.F1_TAG)
    monkeypatch.setattr(rd, "REPO", repo)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": "", "D3": ""})
    return repo


def make_reader(
    tmp_path: Path,
    inner: FakeInner,
    *,
    model: str = "deepseek-v3",
    template: str = "literal-v1",
    cap: float = 5.0,
    temperature: float = 0.0,
    **kwargs,
) -> rd.Reader:
    endpoint, guard = rd.build_transport(
        model,
        spend_log=tmp_path / "out" / "spend_log.jsonl",
        spend_cap_usd=cap,
        max_physical_calls=100,
        inner=inner,
    )
    return rd.Reader(
        model=model,
        template=rd.TEMPLATES[template],
        endpoint=endpoint,
        transport=guard,
        cache=DiskCache(tmp_path / "cache"),
        decoding=rd.decoding_for(temperature),
        **kwargs,
    )


def spend_rows(tmp_path: Path) -> list[dict]:
    path = tmp_path / "out" / "spend_log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_no_test_can_reach_a_key_the_network_or_the_real_repository() -> None:
    # the live client reads its key when it is built: under ``sealed_off`` that fails the test
    with pytest.raises(AssertionError, match="read an API key"):
        RealClient(rd.route_endpoint("gemini-3.8-flash"), ("gemini-3.8-flash",))
    with pytest.raises(AssertionError, match="network connection"):
        socket.create_connection(("example.invalid", 443), timeout=1)
    with pytest.raises(AssertionError, match="network connection"), socket.socket() as sock:
        sock.connect(("192.0.2.1", 443))
    assert not any(name.endswith("_API_KEY") or name.startswith("GIT_") for name in os.environ)
    # the module's repository is not one: no tag is found and no shared-roots file can be written
    checkout = Path(rd.__file__).resolve().parents[2]
    assert checkout != rd.REPO and checkout not in rd.REPO.parents
    assert rd.roots_anchor() is None and len(rd.paid_call_refusals(["test"])) == 2


# --- templates and rendering ------------------------------------------------------------------


def test_templates_are_pinned_and_the_pin_moves_with_the_text() -> None:
    rd.check_frozen()
    t = rd.TEMPLATES["literal-v1"]
    assert replace(t, text=t.text + " ").sha256 != t.sha256
    assert len({t.sha256 for t in rd.TEMPLATES.values()}) == len(rd.TEMPLATES)


def test_print_pins_lists_every_template_with_its_pin(capsys) -> None:
    assert rd.main(["--print-pins"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert set(listing["templates"]) == set(rd.TEMPLATES) == set(rd.FROZEN_SHA256)
    for template_id, entry in listing["templates"].items():
        assert entry["sha256"] == entry["pinned"] == rd.FROZEN_SHA256[template_id]
        assert entry["matches_pin"] is True
    assert len(listing["read_py_sha256"]) == len(listing["schemas_sha256"]) == 64


def test_print_pins_reports_a_template_that_left_its_pin(monkeypatch, capsys) -> None:
    monkeypatch.setitem(rd.FROZEN_SHA256, "probe-v1", "0" * 64)
    assert rd.main(["--print-pins"]) == 1
    listing = json.loads(capsys.readouterr().out)
    assert listing["templates"]["probe-v1"]["matches_pin"] is False
    with pytest.raises(RuntimeError, match="probe-v1"):
        rd.check_frozen()


@pytest.mark.parametrize("template_id", sorted(rd.TEMPLATES))
def test_every_template_renders_fully(template_id: str) -> None:
    text = rd.render_prompt(rd.TEMPLATES[template_id], make_item(), rd.CANARY_TRACK)
    assert "$" not in text
    assert "2020-03-17" in text
    assert "Reply with one JSON object and nothing else" in text


def test_entry_block_shows_category_and_posting_date_and_no_status() -> None:
    for template_id in ("literal-v1", "literal-free-v1", "predictive-v1", "predictive-track-v1"):
        text = rd.render_prompt(rd.TEMPLATES[template_id], make_item(), rd.CANARY_TRACK)
        assert "- Therapeutic category: Hematology\n- Initial posting date: 2019-11-22\n" in text
        assert "Status" not in text
    blank = make_item(therapeutic_category="", initial_posting_date="")
    text = rd.render_prompt(rd.TEMPLATES["literal-v1"], blank)
    assert "- Therapeutic category: (blank)\n- Initial posting date: (blank)\n" in text


def test_literal_prompt_shows_the_entry_and_conventions_only_in_v1() -> None:
    text = rd.render_prompt(rd.TEMPLATES["literal-v1"], make_item(related_information=""))
    assert '- Availability information: "Product on backorder"' in text
    assert "- Related information: (blank)" in text
    assert "Conventions:" in text
    free = rd.render_prompt(rd.TEMPLATES["literal-free-v1"], make_item())
    assert "Conventions:" not in free and "own judgement" in free


def test_pilot_sentences_are_placeholders_until_filled(monkeypatch) -> None:
    # as the file stands (pending or filled): each sentence sits on its own line at the place
    # its placeholder names, and a template waits for exactly the sentences that are still None
    assert set(rd.PILOT_SENTENCES) == {"D1", "D3"}
    tail, conventions = rd.LITERAL_TAIL, rd.CONVENTIONS
    assert tail == rd.LITERAL_CERTAINTY + rd._pilot_line("D1", "   ") + rd.LITERAL_REST
    assert conventions == rd.CONVENTIONS_FIRST + rd._pilot_line("D3", "   - ") + rd.CONVENTIONS_REST
    waiting = tuple(d for d in ("D1", "D3") if rd.PILOT_SENTENCES[d] is None)
    assert rd.TEMPLATES["literal-v1"].pending == waiting
    assert rd.TEMPLATES["literal-free-v1"].pending == tuple(d for d in waiting if d == "D1")
    assert rd.CONVENTIONS in rd.LITERAL_TEXT and rd.CONVENTIONS_REST not in rd.LITERAL_FREE_TEXT
    assert all(not rd.TEMPLATES[t].pending for t in ("predictive-v1", "probe-v1"))
    # pending: nothing is added to the text, and the two literal templates say what they wait for
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": None, "D3": None})
    assert rd._pilot_line("D1", "   ") == rd._pilot_line("D3", "   - ") == ""
    assert rd.TEMPLATES["literal-v1"].pending == ("D1", "D3")
    assert rd.TEMPLATES["literal-free-v1"].pending == ("D1",)
    # filled: one line each; "" settles a point as adding nothing
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": "A sentence.", "D3": ""})
    assert rd._pilot_line("D1", "   ") == "   A sentence.\n"
    assert rd._pilot_line("D3", "   - ") == ""
    assert rd.TEMPLATES["literal-v1"].pending == ()
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": "costs $5", "D3": None})
    with pytest.raises(ValueError, match="one line"):
        rd._pilot_line("D1", "   ")


def test_predictive_horizons_stated_and_fallback() -> None:
    a, b, rule = rd.horizons(make_item())
    assert (a, b, rule) == (date(2020, 4, 30), date(2020, 7, 29), "stated_end")
    a, b, rule = rd.horizons(make_item(stated_end=None))
    assert (a, b, rule) == (date(2020, 6, 15), date(2020, 9, 13), "fallback")
    text = rd.render_prompt(rd.TEMPLATES["predictive-v1"], make_item(stated_end=None))
    assert "The entry states no period, so horizon A, 2020-06-15" in text
    assert "Track record" not in text


def test_track_prompt_carries_table_form_and_examples() -> None:
    text = rd.render_prompt(rd.TEMPLATES["predictive-track-v1"], make_item(), rd.CANARY_TRACK)
    assert "| form | revision | statements | basis | recovered by the stated end |" in text
    assert "| a month and year | first | 240 | cell | 31% | 62% | 140 |" in text
    assert "| a quarter | third or later | 310 | form | 20% | 41% | n/a |" in text
    assert "| TBD or unknown | first | 180 | cell | n/a | n/a | n/a |" in text
    assert "This entry's form: a month and year\nThis entry's revision bucket: second\n" in text
    assert "recovered between 2020-06-10 and 2020-06-18, 98 to 106 days after the update." in text
    assert "not recovered within 365 days" in text
    with pytest.raises(ValueError, match="needs a track record"):
        rd.render_prompt(rd.TEMPLATES["predictive-track-v1"], make_item())


def test_track_sentence_says_what_the_table_is() -> None:
    text = rd.render_prompt(rd.TEMPLATES["predictive-track-v1"], make_item(), rd.CANARY_TRACK)
    block = text.split("Track record:")[1].split("| form |")[0]
    assert "the whole list, all companies together, not of this entry's company" in block
    assert "Turnbull estimates" in block
    assert "the first one made for its presentation, the second, or the third or a later" in block
    assert "fewer than 100 statements" in block and '"all dated forms"' in block
    assert "issuer" not in text


# --- the no-notice probe ----------------------------------------------------------------------

PROBE_SHOWN = {
    "generic_name",
    "company_name",
    "presentation",
    "therapeutic_category",
    "initial_posting_date",
    "date_of_update",
}
PROBE_WORD = "zzbrandq"


def leaky_item() -> tuple[rd.ReadItem, dict[str, list[str]]]:
    """An item whose every field outside the probe's own carries marker words that nothing else
    in a prompt holds. The loop runs over the dataclass, so a field added later is covered
    without an edit here: it gets markers unless ``PROBE_FIELDS`` lists it."""
    markers: dict[str, list[str]] = {}
    changes: dict[str, object] = {}
    for n, f in enumerate(dataclasses.fields(rd.ReadItem)):
        if f.name in rd.PROBE_FIELDS:
            continue
        if f.name == "stated_end":
            changes[f.name] = "2020-05-17"  # not a fixed offset of the date of update
            markers[f.name] = ["2020-05-17"]
        elif f.name == "revision":
            changes[f.name] = "third or later"
            markers[f.name] = ["third or later"]
        else:
            changes[f.name] = f"Zzleak{n} Qxmarker{n} due in July 2021"
            markers[f.name] = [f"Zzleak{n}", f"Qxmarker{n}", "July"]
    # the notice also marks as a brand a word that the presentation carries: a masker that had
    # read the notice would replace it there, so the masked probe would depend on the notice
    changes["presentation"] = f"1 MG 100 Capsules, {PROBE_WORD} pack (NDC 0172-5240-60)"
    changes["availability_information"] += f" {PROBE_WORD.capitalize()}® is on back order."
    return make_item(**changes), markers


def test_probe_fields_are_exactly_what_the_plan_lists() -> None:
    # PLAN section 5 (E4) and DECISIONS 6: generic, company, presentation, therapeutic category,
    # initial posting date and statement date; plus the id and the masker's term list
    assert set(rd.PROBE_FIELDS) == PROBE_SHOWN | {"item_id", "mask_terms"}
    # every other field of an item is kept from the probe; a field added to ReadItem fails here
    # until it is put on one side or the other
    names = {f.name for f in dataclasses.fields(rd.ReadItem)}
    assert names - set(rd.PROBE_FIELDS) == {
        "type_of_update",
        "availability_information",
        "related_information",
        "reason_for_shortage",
        "stated_end",
        "form",
        "revision",
    }
    used = set(re.findall(r"\$([a-z_]+)", rd.PROBE_TEXT))
    assert used == PROBE_SHOWN | {"horizon_note", "horizon_a", "horizon_b"}


@pytest.mark.parametrize(("mask", "shift"), [(False, 0), (True, 0), (False, 4), (True, 4)])
def test_no_text_derived_field_reaches_the_probe(tmp_path: Path, mask: bool, shift: int) -> None:
    item, markers = leaky_item()
    clean = rd.probe_view(item)
    assert all(getattr(clean, name) in (None, "", ()) for name in markers)
    template = rd.TEMPLATES["probe-v1"]
    masker = rd.NameMasker() if mask else None
    inner = FakeInner(lambda prompt: PREDICTIVE_OK)
    reader = make_reader(tmp_path, inner, template="probe-v1", masker=masker, shift_years=shift)
    row = reader.read(item)
    summary = rd.dry_run(
        [item],
        models=["deepseek-v3"],
        template=template,
        track=None,
        samples=1,
        temperature=0.0,
        mask_names=mask,
        shift_years=shift,
    )
    prompts = {
        "runner": inner.calls[0][0],
        "render_for": rd.render_for(template, item, masker=masker, shift_years=shift),
        "render_prompt": rd.render_prompt(template, rd.prepare(item, masker, shift)),
    }
    expected = rd.render_for(template, clean, masker=masker, shift_years=shift)
    for path, prompt in prompts.items():
        for name, pieces in markers.items():
            for piece in pieces:
                assert piece not in prompt, (path, name, piece)
        if path != "render_prompt":  # that path masks before the view, so brand terms may differ
            assert prompt == expected, path
            assert f"{PROBE_WORD} pack" in prompt, path  # the masker never read the notice
    # the horizons are fixed offsets from the date of update, in the prompt and in the row
    assert row["horizons"] == {"a": "2020-06-15", "b": "2020-09-13", "rule": "probe"}
    shown = rd.shift_day(date(2020, 3, 17), shift)
    a, b = shown + rd.FALLBACK_HORIZONS[0], shown + rd.FALLBACK_HORIZONS[1]
    assert f"Horizon A, {a}, is 90 days after the date of update" in prompts["runner"]
    assert f"horizon B, {b}, is 180 days after it." in prompts["runner"]
    stated = rd.shift_day(date(2020, 5, 17), shift).isoformat()
    assert stated not in prompts["runner"] and "the entry states" not in prompts["runner"]
    assert summary["prompt_tokens"]["total"] == rd.estimate_tokens(expected)


def test_probe_shows_its_six_fields_and_nothing_of_the_notice() -> None:
    text = rd.render_prompt(rd.TEMPLATES["probe-v1"], make_item())
    assert "Expected recovery" not in text and "backorder" not in text
    assert "Reverified" not in text and "Demand increase" not in text
    for line in (
        "- Drug: Anagrelide Hydrochloride Capsules",
        "- Company: Teva Pharmaceuticals",
        "- Therapeutic category: Hematology",
        "- Initial posting date: 2019-11-22",
        "- Date of update: 2020-03-17",
    ):
        assert line in text
    assert rd.horizons(make_item(), probe=True) == (date(2020, 6, 15), date(2020, 9, 13), "probe")
    assert "2020-04-30" not in text and "2020-07-29" not in text


# --- the track-record file ---------------------------------------------------------------------

TRACK_FIXTURE = {
    "schema": "coling-track-record-v1",
    "split": "fit",
    "since": "2019-10-01",
    "through": "2020-12-31",
    "seed": 20261001,
    "min_cell": 100,
    "source": {"outcomes_sha256": "0" * 64, "events_sha256": "1" * 64, "builder_sha256": "2" * 64},
    "slip_table": [
        {
            "form": "a month and year",
            "revision": "first",
            "statements": 412,
            "basis": "cell",
            "share_by_stated_end": 0.31,
            "share_by_stated_end_90": 0.62,
            "median_days_to_recovery": 140,
        },
        {
            "form": "a month and year",
            "revision": "second",
            "statements": 655,
            "basis": "form",
            "share_by_stated_end": 0.28,
            "share_by_stated_end_90": 0.6,
            "median_days_to_recovery": 151.5,
        },
        {
            "form": "TBD or unknown",
            "revision": "first",
            "statements": 230,
            "basis": "cell",
            "share_by_stated_end": None,
            "share_by_stated_end_90": None,
            "median_days_to_recovery": None,
        },
    ],
    "examples": [
        {
            "item_id": "S0001",
            "date_of_update": "2020-03-04",
            "outcome": "recovered",
            "type_of_update": "Revised",
            "availability_information": "Backordered. Next release April 2020.",
            "stated_end": "2020-04-30",
            "recovered_after": "2020-06-10",
            "recovered_by": "2020-06-18",
            "generic_name": "Anagrelide Capsules",
            "company_name": "Teva Pharmaceuticals",
            "form": "a month and year",
            "revision": "first",
        },
        {
            "item_id": "S0002",
            "date_of_update": "2020-05-01",
            "outcome": "not_recovered",
            "related_information": "Next shipment TBD",
            "followed_until": "2022-10-06",
        },
        {"item_id": "S0003", "date_of_update": "2020-07-01", "outcome": "discontinued"},
    ],
}
"""The track-record file as its builder must write it (schema ``coling-track-record-v1``)."""


def write_track(tmp_path: Path, **changes) -> Path:
    path = tmp_path / "track.json"
    path.write_text(json.dumps(TRACK_FIXTURE | changes, indent=1))
    return path


def changed(key: str, index: int, **changes) -> dict:
    """The fixture's list ``key`` with one record changed (a value of ``...`` removes the key)."""
    records = [dict(r) for r in TRACK_FIXTURE[key]]
    records[index] |= changes
    records[index] = {k: v for k, v in records[index].items() if v is not ...}
    return {key: records}


def test_load_track_record_reads_the_fixture_and_keeps_its_hash(tmp_path: Path) -> None:
    path = write_track(tmp_path)
    track = rd.load_track_record(path)
    assert rd.track_file_errors(TRACK_FIXTURE) == [] and track.errors() == []
    assert track.sha256 == rd._sha256_file(path) and len(track.sha256) == 64
    assert (track.split, track.since, track.through, track.min_cell) == (
        "fit",
        "2019-10-01",
        "2020-12-31",
        100,
    )
    assert [(r.form, r.revision, r.basis) for r in track.slip_table][1] == (
        "a month and year",
        "second",
        "form",
    )
    assert [ex.item_id for ex in track.examples] == ["S0001", "S0002", "S0003"]
    text = rd.render_prompt(rd.TEMPLATES["predictive-track-v1"], make_item(), track)
    assert "| a month and year | second | 655 | form | 28% | 60% | 152 |" in text
    assert "entries updated from 2019-10-01 to 2020-12-31" in text
    assert "S0001" not in text and "Anagrelide Capsules" not in text  # ids and names: not shown


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema": "coling-track-record-v0"}, "schema must be"),
        ({"seed": 7}, "study seed"),
        ({"seed": "20261001"}, "'seed' must be of type int"),
        ({"hold_rate": 0.4}, "unknown key 'hold_rate'"),
        ({"slip_table": []}, "slip_table is empty"),
        ({"source": {"outcomes_sha256": 5}}, "source must map names to strings"),
        (changed("slip_table", 0, hold_rate=0.4), "slip_table row 1: unknown key 'hold_rate'"),
        (changed("slip_table", 0, basis=...), "slip_table row 1: missing key 'basis'"),
        (changed("slip_table", 0, share_by_stated_end="31%"), "must be a number or null"),
        (changed("examples", 2, recovered=True), "example 3: unknown key 'recovered'"),
        (changed("examples", 2, item_id=...), "example 3: missing key 'item_id'"),
        (changed("examples", 2, stated_end=20200430), "example 3: every value must be a string"),
    ],
)
def test_load_track_record_checks_the_schema(tmp_path: Path, changes: dict, message: str) -> None:
    with pytest.raises(ValueError, match="not a track-record file") as caught:
        rd.load_track_record(write_track(tmp_path, **changes))
    assert message in str(caught.value)
    missing = {k: v for k, v in TRACK_FIXTURE.items() if k != "min_cell"}
    assert rd.track_file_errors(missing) == ["missing key 'min_cell'"]
    assert rd.track_file_errors([TRACK_FIXTURE]) == ["the file must hold one JSON object"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"through": "2023-01-31", "split": "fit+dev"}, "must end before 2023-01-01"),
        ({"through": "2021-06-30"}, "a fit-split record must end before 2021-01-01"),
        ({"split": "train"}, "split must be one of"),
        (changed("examples", 0, date_of_update="2023-01-01"), "in the test period"),
        (changed("examples", 0, date_of_update="2021-02-01"), "outside the fit split"),
        (
            {"split": "fit+dev", "through": "2022-12-31"}
            | changed("examples", 0, date_of_update="2021-02-01", recovered_after=...),
            "example 1: dated 2021-02-01, outside the fit split",
        ),
        ({"through": "2020-06-30"}, "example 3: dated 2020-07-01, after the record's last day"),
        (changed("examples", 0, recovered_by="2023-01-13"), "recovered_by 2023-01-13 is in the"),
        (changed("examples", 0, recovered_by=...), "a recovered example needs recovered_by"),
        (changed("examples", 0, recovered_after="2020-07-01"), "later than recovered_by"),
        (changed("examples", 0, recovered_by="2020-02-01"), "recovered_by is before the update"),
        (changed("examples", 1, followed_until="2021-04-30"), "needs 365 days of follow-up"),
        (changed("examples", 1, followed_until=...), "needs 365 days of follow-up"),
        (changed("examples", 1, followed_until="2023-01-13"), "followed_until 2023-01-13 is in"),
        (changed("examples", 2, recovered_by="2020-08-01"), "only a recovered example"),
        (changed("examples", 2, outcome="resolved"), "outcome must be one of"),
        (changed("examples", 2, item_id="S0001"), "example item ids must be unique"),
        (changed("slip_table", 1, revision="first"), "two rows for one form and revision bucket"),
        (changed("slip_table", 1, revision="2"), "revision must be one of"),
        (changed("slip_table", 1, basis="pooled"), "basis must be one of"),
        (changed("slip_table", 0, statements=99), "a cell needs at least 100 statements"),
        (changed("slip_table", 1, statements=0), "a pooled row at least 1"),
        (changed("slip_table", 0, share_by_stated_end=1.2), "share outside"),
        (changed("slip_table", 0, share_by_stated_end_90=0.2), "is below the share by it"),
        (changed("slip_table", 0, median_days_to_recovery=400), "median outside"),
    ],
)
def test_load_track_record_refuses_what_must_not_reach_a_prompt(
    tmp_path: Path, changes: dict, message: str
) -> None:
    with pytest.raises(ValueError, match="track record refused") as caught:
        rd.load_track_record(write_track(tmp_path, **changes))
    assert message in str(caught.value)


def test_track_record_refuses_the_test_period() -> None:
    assert rd.CANARY_TRACK.errors() == []
    late = replace(rd.CANARY_TRACK.examples[0], date_of_update="2023-01-01")
    with pytest.raises(ValueError, match="test period"):
        replace(rd.CANARY_TRACK, examples=(late,)).check()
    with pytest.raises(ValueError, match="end before"):
        replace(rd.CANARY_TRACK, through="2023-02-01").check()
    many = rd.CANARY_TRACK.examples[:1] * 11
    with pytest.raises(ValueError, match="at most 10"):
        replace(rd.CANARY_TRACK, examples=many).check()
    with pytest.raises(ValueError, match="test period"):
        rd.transform_track(replace(rd.CANARY_TRACK, examples=(late,)), None, 0)


def test_items_accept_fda_headers_and_periods(tmp_path: Path) -> None:
    rows = [
        {
            "item_id": "a",
            "Generic Name": "X",
            "Date of Update": "03/17/2020",
            "Therapeutic Category": "Oncology",
            "Initial Posting Date": "02/18/2014",
            "Status": "Current",
            "extra": 1,
        },
        {"item_id": "b", "generic_name": "Y", "date_of_update": "2023-01-01", "mask_terms": "Z"},
        {"item_id": "c", "date_of_update": "2025-12-31", "revision": "third or later"},
        {"item_id": "d", "date_of_update": "2026-01-01", "initial_posting_date": "not known"},
    ]
    path = tmp_path / "items.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    items = rd.load_items(path)
    assert items[0].date_of_update == "2020-03-17" and items[0].generic_name == "X"
    assert (items[0].therapeutic_category, items[0].initial_posting_date) == (
        "Oncology",
        "2014-02-18",
    )
    assert "Current" not in rd.render_prompt(rd.TEMPLATES["literal-v1"], items[0])
    assert [i.period for i in items] == ["train", "test", "test", "late"]
    assert items[1].mask_terms == ("Z",) and items[2].revision == "third or later"
    assert items[3].initial_posting_date == "not known"
    with pytest.raises(ValueError, match="revision must be one of"):
        rd.ReadItem.from_dict({"item_id": "e", "date_of_update": "2020-01-01", "revision": "2"})
    csv = tmp_path / "events.csv"
    csv.write_text(
        "event_id,event_date,generic_name,availability_text,related_text,resolved_note,"
        "therapeutic_category,initial_posting_date,status_at_statement\n"
        "e1,2021-05-04,X,Backordered,Next release June 2021,Resolved 2021-07-01,"
        "Oncology,02/18/2014,Current\n"
    )
    [event] = rd.load_items(csv)
    assert (event.item_id, event.date_of_update) == ("e1", "2021-05-04")
    assert event.related_information == "Next release June 2021"
    assert event.initial_posting_date == "2014-02-18"
    prompt = rd.render_prompt(rd.TEMPLATES["literal-v1"], event)
    assert "Resolved" not in prompt and "2021-07-01" not in prompt and "Current" not in prompt


# --- parsing ----------------------------------------------------------------------------------


def test_parse_literal_accepts_fences_think_and_abstain() -> None:
    text = f"<think>hmm {{</think>```json\n{LITERAL_OK}\n```"
    result = rd.parse_reading(text, "literal", date_of_update=date(2020, 3, 17))
    assert result.ok and result.reading["interval"]["end"] == "2020-04-30"
    abstain = json.loads(LITERAL_OK) | {"interval": "ABSTAIN", "certainty": "undetermined"}
    assert rd.parse_reading(json.dumps(abstain), "literal").ok


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"interval": {"start": "2020-02-30", "end": "2020-03-01"}}, "not a calendar date"),
        ({"interval": {"start": "2020-05-01", "end": "2020-04-01"}}, "start is after end"),
        ({"interval": "April 2020"}, "matches no allowed form"),
        ({"certainty": "likely"}, "must be one of"),
        ({"stale": "no"}, "must be of type boolean"),
        ({"reasoning": "because"}, "unexpected key"),
    ],
)
def test_parse_literal_rejects(change: dict, message: str) -> None:
    result = rd.parse_reading(json.dumps(json.loads(LITERAL_OK) | change), "literal")
    assert not result.ok and any(message in e for e in result.errors)


def test_parse_literal_warnings_are_not_errors() -> None:
    reading = json.loads(LITERAL_OK) | {"certainty": "undetermined", "stale": True}
    result = rd.parse_reading(json.dumps(reading), "literal", date_of_update=date(2020, 3, 17))
    assert result.ok
    assert {"interval_for_undetermined", "stale_flag_disagrees_with_interval"} <= set(
        result.warnings
    )
    both = rd.parse_reading(f"Sure: {LITERAL_OK} {LITERAL_OK}", "literal")
    assert both.ok and {"text_outside_json", "several_json_objects"} <= set(both.warnings)
    other = LITERAL_OK.replace("estimated", "asserted")
    assert rd.parse_reading(f"{LITERAL_OK}\n{other}", "literal").errors == [
        "several different JSON objects"
    ]


def test_parse_predictive() -> None:
    assert rd.parse_reading(PREDICTIVE_OK, "predictive").ok
    base = json.loads(PREDICTIVE_OK)
    floats = base | {"days_to_recovery": {k: float(v) for k, v in base["days_to_recovery"].items()}}
    parsed = rd.parse_reading(json.dumps(floats), "predictive")
    assert parsed.ok and parsed.reading["days_to_recovery"]["q50"] == 80
    assert isinstance(parsed.reading["days_to_recovery"]["q50"], int)
    down = base | {"days_to_recovery": base["days_to_recovery"] | {"q90": 100}}
    assert "quantiles decrease" in rd.parse_reading(json.dumps(down), "predictive").errors[0]
    percent = base | {"p_by_horizon_a": 30}
    assert not rd.parse_reading(json.dumps(percent), "predictive").ok
    over = base | {"days_to_recovery": base["days_to_recovery"] | {"q95": 400}}
    assert not rd.parse_reading(json.dumps(over), "predictive").ok
    nan = PREDICTIVE_OK.replace("0.3", "NaN")
    assert not rd.parse_reading(nan, "predictive").ok
    swapped = base | {"p_by_horizon_a": 0.7}
    result = rd.parse_reading(json.dumps(swapped), "predictive")
    assert result.ok and "p_by_horizon_b_below_a" in result.warnings
    assert rd.parse_reading("no json here", "predictive").errors == ["no JSON object found"]


def test_parsing_is_strict_nothing_is_sorted_or_clipped() -> None:
    base = json.loads(PREDICTIVE_OK)
    unsorted = base | {
        "days_to_recovery": {"q10": 80, "q50": 20, "q80": 150, "q90": 200, "q95": 365}
    }
    result = rd.parse_reading(json.dumps(unsorted), "predictive")
    assert result.reading is None and result.errors == ["$.days_to_recovery: quantiles decrease"]
    for name, value in (("p_by_horizon_a", 1.2), ("p_by_horizon_b", -0.1)):
        result = rd.parse_reading(json.dumps(base | {name: value}), "predictive")
        assert result.reading is None and "outside [0, 1]" in result.errors[0]
    assert (
        rd.fallback_for("literal", "failed") == rd.fallback_for("literal", "refused") == "abstain"
    )
    assert rd.fallback_for("predictive", "failed") == "base_rate"
    assert rd.fallback_for("predictive", "refused") == "base_rate"
    assert rd.fallback_for("literal", "ok") is rd.fallback_for("predictive", "repaired") is None


# --- masking and date shifts ------------------------------------------------------------------


def test_name_masker_replaces_names_everywhere_and_consistently() -> None:
    masked = rd.NameMasker().mask_item(make_item())
    assert (
        "Anagrelide" not in masked.generic_name and "Hydrochloride Capsules" in masked.generic_name
    )
    assert "Teva" not in masked.company_name and masked.company_name.endswith("Pharmaceuticals")
    assert "Teva" not in masked.related_information
    fake_company = masked.company_name.split()[0]
    assert masked.related_information.endswith(f"{fake_company} is working with FDA.")
    again = rd.NameMasker().mask_item(make_item())
    assert again == masked  # deterministic across instances
    upper = rd.NameMasker().mask_item(make_item(related_information="TEVA says so"))
    assert upper.related_information == f"{fake_company.upper()} says so"


def test_name_masker_ndc_strength_brand_and_salt_only_names() -> None:
    masker = rd.NameMasker()
    item = make_item(
        generic_name="Sodium Chloride Injection",
        presentation="0.9% 1 g/10 mL vial (NDC 0409-4888-10); BYDUREON® pen, NDC 31722053605",
        related_information="Allocation at 80% of demand. Sodium chloride 1 g in 250 mL soon.",
        mask_terms=("Lupron Depot",),
        availability_information="Lupron Depot unavailable",
    )
    out = masker.mask_item(item)
    k = masker.strength_factor(item.generic_name)
    assert k != 1
    assert "Sodium" not in out.generic_name and "Injection" in out.generic_name
    assert "0409-4888-10" not in out.presentation and "31722053605" not in out.presentation
    assert out.presentation.count("-") == item.presentation.count("-")
    scaled = format((Decimal("0.9") * k).normalize(), "f")
    assert out.presentation.startswith(f"{scaled}% {format(k.normalize(), 'f')} g/10 mL vial")
    assert "BYDUREON" not in out.presentation and "®" in out.presentation
    assert "80% of demand" in out.related_information  # percentages in free text are kept
    assert f" {format(k.normalize(), 'f')} g in 250 mL" in out.related_information
    assert "Lupron" not in out.availability_information
    a, b = masker.fake_word("alpha", "ingredient"), masker.fake_word("beta", "ingredient")
    assert a != b and masker.fake_word("ALPHA", "ingredient") == a


def test_name_masker_keeps_labeller_codes_and_initialisms_consistent() -> None:
    masker = rd.NameMasker()
    one = masker.mask_item(make_item(presentation="1 mg (NDC 0409-1630-10)"))
    two = masker.mask_item(make_item(presentation="2 mg (NDC 0409-4911-34)"))
    assert one.presentation.split("NDC ")[1][:4] == two.presentation.split("NDC ")[1][:4]
    bms = masker.mask_item(
        make_item(company_name="Bristol Myers Squibb Co.", related_information="BMS will ship")
    )
    assert "BMS" not in bms.related_information
    initials = "".join(w[0] for w in bms.company_name.split()[:3])
    assert bms.related_information == f"{initials.upper()} will ship"


@pytest.mark.parametrize(
    ("text", "years", "expected"),
    [
        ("Expected recovery April 2020", 3, "Expected recovery April 2023"),
        (
            "Next release Dec-20; 2Q21 or Q3 '21, FY21",
            2,
            "Next release Dec-22; 2Q23 or Q3 '23, FY23",
        ),
        ("Updated 03/17/2020 and 3/7/20", -1, "Updated 03/17/2019 and 3/7/19"),
        ("As of 2020-02-29", 1, "As of 2021-02-28"),
        ("NDC 0409-2020-01 and 55150-170-30", 5, "NDC 0409-2020-01 and 55150-170-30"),
        (
            "Available Aug 20; 2000 mg vials; 2020-2021",
            1,
            "Available Aug 20; 2000 mg vials; 2021-2022",
        ),
        ("Late December/early January", 4, "Late December/early January"),
    ],
)
def test_shift_dates(text: str, years: int, expected: str) -> None:
    assert rd.shift_dates(text, years) == expected


def test_shift_item_moves_structured_dates() -> None:
    moved = rd.shift_item(make_item(), 3)
    assert (moved.date_of_update, moved.stated_end) == ("2023-03-17", "2023-04-30")
    assert "April 2023" in moved.related_information
    assert moved.initial_posting_date == "2022-11-22"
    assert rd.shift_item(make_item(), 0) == make_item()
    masked = rd.NameMasker().mask_item(make_item())
    assert (masked.therapeutic_category, masked.initial_posting_date) == (
        "Hematology",
        "2019-11-22",
    )


# --- the runner, with a fake transport behind the real guard ---------------------------------


def test_reader_reads_caches_and_logs_spend(tmp_path: Path) -> None:
    inner = FakeInner([LITERAL_OK])
    reader = make_reader(tmp_path, inner)
    row = reader.read(make_item())
    assert row["status"] == "ok" and row["reading"]["certainty"] == "estimated"
    prompt, decoding, system = inner.calls[0]
    assert prompt == rd.render_prompt(rd.TEMPLATES["literal-v1"], make_item())
    assert (decoding.decoding_hash, decoding.temperature, system) == ("det-v1", 0.0, None)
    [log] = spend_rows(tmp_path)
    expected = (500 * 0.257 + 60 * 1.029) / 1e6
    assert log["usd"] == pytest.approx(expected) == row["attempts"][0]["usd"]
    assert log["prompt_tokens"] == 500 and log["billable_output_tokens"] == 60
    # a second reader on the same cache: no new call, same reading, nothing billed
    inner2 = FakeInner([])
    again = make_reader(tmp_path, inner2).read(make_item())
    assert inner2.calls == [] and again["reading"] == row["reading"]
    assert again["attempts"][0]["cache_hit"] is True
    assert len(spend_rows(tmp_path)) == 1


def test_thinking_tokens_are_billed_as_output(tmp_path: Path) -> None:
    inner = FakeInner([PREDICTIVE_OK], prompt_tokens=1000, completion_tokens=50, hidden=1000)
    reader = make_reader(tmp_path, inner, model="gemini-3.8-flash", template="predictive-v1")
    row = reader.read(make_item())
    [log] = spend_rows(tmp_path)
    assert log["billable_output_tokens"] == 1050
    assert log["usd"] == pytest.approx((1000 * 0.75 + 1050 * 3.75) / 1e6)
    assert row["horizons"] == {"a": "2020-04-30", "b": "2020-07-29", "rule": "stated_end"}


def test_one_repair_attempt(tmp_path: Path) -> None:
    inner = FakeInner(["The interval is April 2020.", LITERAL_OK])
    row = make_reader(tmp_path, inner).read(make_item())
    assert row["status"] == "repaired" and len(inner.calls) == 2
    assert row["fallback"] is None
    repair_prompt = inner.calls[1][0]
    assert "Your previous reply was:\n<<<\nThe interval is April 2020.\n>>>" in repair_prompt
    assert "no JSON object found" in repair_prompt
    assert [a["attempt"] for a in row["attempts"]] == [0, 1]
    inner = FakeInner(["nope", "still nope"])
    row = make_reader(tmp_path / "b", inner).read(make_item())
    assert row["status"] == "failed" and row["reading"] is None and len(inner.calls) == 2
    assert row["errors"] == ["no JSON object found", "repair: no JSON object found"]
    assert row["fallback"] == "abstain"  # a literal reading that fails twice counts as ABSTAIN
    # a predictive reading that fails twice is flagged for the base-rate replacement; exactly one
    # repair call is made, and a reply with decreasing quantiles is a failure, not sorted
    down = PREDICTIVE_OK.replace('"q90": 200', '"q90": 100')
    inner = FakeInner([down, down])
    reader = make_reader(tmp_path / "c", inner, template="predictive-v1")
    row = reader.read(make_item())
    assert (row["status"], row["fallback"], row["reading"]) == ("failed", "base_rate", None)
    assert len(inner.calls) == 2 and "quantiles decrease" in inner.calls[1][0]


def test_refusal_is_not_repaired(tmp_path: Path) -> None:
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    refusal = openai.PermissionDeniedError(
        "moderated", response=httpx.Response(403, request=request), body=None
    )
    inner = FakeInner([refusal])
    row = make_reader(tmp_path, inner).read(make_item())
    assert row["status"] == "refused" and len(inner.calls) == 1
    assert (row["fallback"], row["echo"]) == ("abstain", "refused")
    events = [r["event"] for r in spend_rows(tmp_path)]
    assert events == ["refusal", "call"]


def test_projected_cap_stops_before_the_call(tmp_path: Path) -> None:
    inner = FakeInner([LITERAL_OK] * 5)
    reader = make_reader(tmp_path, inner, cap=0.0001)
    rows, status = rd.read_items(reader, [make_item()])
    assert rows == [] and inner.calls == [] and status.startswith("aborted: recorded spend")
    # a cap with room for one projected call on top of one and a half billed calls lets exactly
    # two calls through. (The cap is built from the projection and the fake's own bill, so the
    # count does not move with the length of the prompt, as it did when the cap was 2.5
    # projections.)
    one = rd.projected_call_usd(reader.prompt_for(make_item()), "deepseek-v3", "literal",
                                reader.endpoint)  # fmt: skip
    billed = (500 * 0.257 + 60 * 1.029) / 1e6
    items = [make_item(item_id=f"i{n}") for n in range(5)]
    reader = make_reader(tmp_path / "b", FakeInner([LITERAL_OK] * 5), cap=one + 1.5 * billed)
    rows, status = rd.read_items(reader, items)
    assert status.startswith("aborted") and len(rows) == 2
    assert reader.transport.spent_usd == pytest.approx(2 * billed)


def test_samples_have_their_own_cache_entries(tmp_path: Path) -> None:
    inner = FakeInner([PREDICTIVE_OK] * 3)
    reader = make_reader(tmp_path, inner, template="predictive-v1", temperature=1.0)
    rows, status = rd.read_items(reader, [make_item()], samples=3)
    assert status == "complete" and [r["sample"] for r in rows] == [0, 1, 2]
    assert len(inner.calls) == 3 and {c[1].decoding_hash for c in inner.calls} == {"temp1-v1"}
    assert all(c[1].temperature == 1.0 for c in inner.calls)
    assert len(DiskCache(tmp_path / "cache")) == 3
    states = {rd.call_state(reader.template, "i1", s, 0) for s in range(3)}
    assert len(states) == 3


def test_masked_and_shifted_reading(tmp_path: Path) -> None:
    shifted = json.loads(LITERAL_OK) | {"interval": {"start": "2023-04-01", "end": "2023-04-30"}}
    inner = FakeInner([json.dumps(shifted)])
    reader = make_reader(tmp_path, inner, masker=rd.NameMasker(), shift_years=3)
    row = reader.read(make_item())
    entry = inner.calls[0][0].split("Answer these")[0]  # the conventions quote 2020 examples
    assert "Anagrelide" not in entry and "Teva" not in entry and "2020" not in entry
    assert "Date of update: 2023-03-17" in entry and "April 2023" in entry
    assert row["interval_unshifted"] == {"start": "2020-04-01", "end": "2020-04-30"}
    assert row["mask_names"] is True and row["shift_years"] == 3
    assert "stale_flag_disagrees_with_interval" not in row["warnings"]


def test_track_record_is_masked_and_shifted_with_the_item(tmp_path: Path) -> None:
    track = replace(
        rd.CANARY_TRACK,
        examples=(
            replace(
                rd.CANARY_TRACK.examples[0],
                generic_name="Anagrelide Capsules",
                availability_information="Anagrelide backordered until May 2020",
            ),
        ),
    )
    inner = FakeInner(lambda prompt: PREDICTIVE_OK)
    reader = make_reader(
        tmp_path,
        inner,
        template="predictive-track-v1",
        track=track,
        masker=rd.NameMasker(),
        shift_years=2,
    )
    reader.read(make_item())
    sent = inner.calls[0][0]
    assert "Anagrelide" not in sent and "May 2022" in sent and "2020-03-04" not in sent
    assert "1. Date of update: 2022-03-04" in sent
    assert "entries updated from 2021-10-01 to 2024-12-31" in sent
    rows, _ = rd.read_items(reader, [make_item(item_id="late", date_of_update="2023-02-01")])
    assert "track_record_not_before_item" not in rows[0]["warnings"]
    assert "track_record_not_before_item" in reader.read(make_item())["warnings"]


# --- routes, the provider pin and the echo ------------------------------------------------------


def test_routes_cover_the_eight_readers_and_wait_for_f1() -> None:
    assert tuple(rd.ROUTES) == rd.STUDY_MODELS and set(rd.MODEL_CAPS_USD) == set(rd.STUDY_MODELS)
    assert sum(rd.MODEL_CAPS_USD.values()) <= rd.STUDY_CAP_USD
    for model, route in rd.ROUTES.items():
        on_openrouter = rd.LADDER[model].provider == "openrouter"
        assert route.provider == (rd.UNSET if on_openrouter else rd.DIRECT)
        assert route.model_id == rd.LADDER[model].model_id
        assert rd.provider_object(route) is None and rd.route_tag(route) == ""
        assert bool(rd.route_errors(model)) is on_openrouter
    assert "has no provider yet (UNSET)" in rd.route_errors("deepseek-v3")[0]
    assert "not one of the eight" in rd.route_errors("qwen-2.5-72b")[0]
    assert rd.PROVIDER_ECHO_REQUIRED is False


def test_provider_object_and_endpoint_of_a_filled_route(monkeypatch) -> None:
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    route = rd.ROUTES["llama-3.3-70b"]
    pin = {"order": ["deepinfra/turbo"], "allow_fallbacks": False, "quantizations": ["fp8"]}
    assert rd.provider_object(route) == pin and rd.route_errors("llama-3.3-70b") == []
    endpoint = rd.route_endpoint("llama-3.3-70b")
    assert endpoint.extra_body == {"provider": pin} and endpoint.model_id == LLAMA
    assert (endpoint.price_input_per_mtok, endpoint.price_output_per_mtok) == (0.10, 0.32)
    assert endpoint.price_date == "2026-10-01"
    # an endpoint that states no precision sends no quantisation filter
    assert rd.provider_object(rd.Route("qwen/qwen-2.5-7b-instruct", "phala")) == {
        "order": ["phala"],
        "allow_fallbacks": False,
    }
    # a dated id replaces the ladder's id, and then only the dated id (or a listed echo) is accepted
    dated = rd.Route(
        "openai/gpt-4o-mini-2024-07-18", "openai", also_served_as=("openai/gpt-4o-mini",)
    )
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | {"gpt-4o-mini": dated})
    assert rd.route_endpoint("gpt-4o-mini").model_id == "openai/gpt-4o-mini-2024-07-18"
    assert rd.served_as("gpt-4o-mini") == ("openai/gpt-4o-mini-2024-07-18", "openai/gpt-4o-mini")
    # a direct route and a model outside the table keep the ladder's endpoint
    assert rd.route_endpoint("gemini-3.8-flash") == rd.LADDER["gemini-3.8-flash"].endpoint()
    assert rd.route_endpoint("qwen-2.5-72b") == rd.LADDER["qwen-2.5-72b"].endpoint()
    assert len(rd.route_tag(route)) == 8
    assert rd.route_tag(route) != rd.route_tag(rd.ROUTES["deepseek-v3"])
    wrong = rd.ROUTES | {"gemini-3.8-flash": rd.Route("gemini-3.8-flash", "deepinfra")}
    monkeypatch.setattr(rd, "ROUTES", wrong)
    assert "needs an endpoint slug, others DIRECT" in rd.route_errors("gemini-3.8-flash")[0]
    # a pinned endpoint is not called at the ladder's price: the route must carry its own
    unpriced = replace(PINNED["deepseek-v3"], price=None)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | {"deepseek-v3": unpriced})
    assert "gives no price" in rd.route_errors("deepseek-v3")[0]
    assert (
        rd.route_endpoint("deepseek-v3").price_date
        == rd.LADDER["deepseek-v3"].endpoint().price_date
    )
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    assert rd.route_errors("deepseek-v3") == [] and rd.route_errors("grok-4.20") == []
    priced = rd.route_endpoint("deepseek-v3")
    assert (priced.price_input_per_mtok, priced.price_output_per_mtok) == (0.32, 0.89)
    # a row filled in by halves (a price, and the provider still unset) would be called with no
    # pin at all: it is refused as unset
    half = replace(PINNED["deepseek-v3"], provider=rd.UNSET)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | {"deepseek-v3": half})
    assert rd.provider_object(half) is None
    assert "has no provider yet (UNSET)" in rd.route_errors("deepseek-v3")[0]


def test_provider_names_are_compared_on_the_slug() -> None:
    route = PINNED["llama-3.3-70b"]
    for names in (["DeepInfra"], ["deepinfra/turbo"], ["DeepInfra", "deepinfra/turbo"]):
        assert rd.provider_problem(route, names) is None
    assert "['Together']" in rd.provider_problem(route, ["Together"])
    assert "deepinfra/fp8" in rd.provider_problem(route, ["DeepInfra", "deepinfra/fp8"])
    assert rd.provider_problem(route, []) is None  # tolerated until PROVIDER_ECHO_REQUIRED
    assert rd.provider_problem(rd.ROUTES["gemini-3.8-flash"], ["anything"]) is None
    assert rd.provider_problem(None, ["anything"]) is None
    alias = replace(route, also_served_by=("Deep Infra Inc",))
    assert rd.provider_problem(alias, ["deep-infra inc"]) is None


def test_served_of_reads_the_provider_from_the_response() -> None:
    plain = SimpleNamespace(model="models/gemini-3.8-flash")
    assert rd.served_of(plain) == {
        "model": "gemini-3.8-flash",
        "provider": None,
        "provider_names": [],
        "metadata": None,
    }
    meta = {"endpoints": [{"provider_name": "DeepInfra", "tag": "deepinfra/turbo", "name": "x/y"}]}
    served = rd.served_of(SimpleNamespace(model=LLAMA, provider=None, openrouter_metadata=meta))
    assert served["provider_names"] == ["DeepInfra", "deepinfra/turbo"]
    assert served["provider"] == "DeepInfra | deepinfra/turbo" and "x/y" in served["metadata"]
    top = rd.served_of({"model": LLAMA, "provider": "DeepInfra", "openrouter_metadata": meta})
    assert top["provider_names"] == ["DeepInfra", "deepinfra/turbo"]


def considered(*endpoints: tuple[str, bool | None]) -> dict:
    """Routing metadata in the documented shape: the endpoints considered for a request, each
    with its provider and a ``selected`` flag (left out when the flag is None)."""
    available = [
        {"provider": name} | ({} if flag is None else {"selected": flag})
        for name, flag in endpoints
    ]
    return {"endpoints": {"available": available}}


def test_an_endpoint_that_was_considered_and_not_used_names_nobody(tmp_path: Path) -> None:
    route = PINNED["llama-3.3-70b"]

    def names(*endpoints: tuple[str, bool | None]) -> list[str]:
        response = SimpleNamespace(model=LLAMA, openrouter_metadata=considered(*endpoints))
        return rd.served_of(response)["provider_names"]

    # the pinned endpoint served the call; the others were only considered
    used = names(("DeepInfra", True), ("Novita", False), ("Together", False))
    assert used == ["DeepInfra"] and rd.provider_problem(route, used) is None
    # another endpoint served it: the pinned one, listed and not selected, does not excuse that
    other = names(("DeepInfra", False), ("Novita", True))
    assert other == ["Novita"] and "['Novita']" in rd.provider_problem(route, other)
    # an entry with no flag, or with a flag that is not exactly false, counts as naming
    assert names(("DeepInfra", True), ("Novita", None)) == ["DeepInfra", "Novita"]
    assert rd._provider_names({"provider": "Novita", "selected": None}) == ["Novita"]
    # nothing under an entry that was not used is read either
    nested = {"provider": "Novita", "selected": False, "fallback": {"provider": "Groq"}}
    assert rd._provider_names([nested]) == []
    # no endpoint selected: no provider is reported
    assert names(("DeepInfra", False)) == []
    # through the client and the runner: a listing of several endpoints does not stop the run
    listing = considered(("DeepInfra", True), ("Novita", False))
    sdk = FakeSDK([LITERAL_OK], model=LLAMA, provider=None, metadata=listing)
    row = pinned_reader(tmp_path / "a", sdk).read(make_item())
    assert (row["echo"], row["attempts"][0]["served_provider"]) == ("ok", "DeepInfra")
    swapped = considered(("DeepInfra", False), ("Novita", True))
    sdk = FakeSDK([LITERAL_OK], model=LLAMA, provider=None, metadata=swapped)
    rows, status = rd.read_items(pinned_reader(tmp_path / "b", sdk), [make_item()])
    assert rows == [] and status.startswith("aborted: served by another model or provider")


def make_client(sdk: FakeSDK, model: str = "llama-3.3-70b") -> rd.RouteCheckedClient:
    route = PINNED[model]
    endpoint = replace(
        rd.LADDER[model].endpoint(), extra_body={"provider": rd.provider_object(route)}
    )
    return rd.RouteCheckedClient(endpoint, (route.model_id,), route=route, sdk=sdk)


def test_client_sends_the_pin_and_records_who_served() -> None:
    sdk = FakeSDK([LITERAL_OK], model=LLAMA)
    client = make_client(sdk)
    raw = client.complete_metered("hello", decoding=rd.decoding_for(0.0))
    assert raw.text == LITERAL_OK and (raw.prompt_tokens, raw.total_tokens) == (500, 560)
    [call] = sdk.calls
    assert call["model"] == LLAMA and call["temperature"] == 0.0
    assert call["extra_body"] == {
        "provider": {
            "order": ["deepinfra/turbo"],
            "allow_fallbacks": False,
            "quantizations": ["fp8"],
        }
    }
    assert call["extra_headers"] == {"X-OpenRouter-Metadata": "enabled"}
    assert client.last_served["model"] == LLAMA and client.last_served["provider"] == "DeepInfra"
    assert client.last_billed == (500, 60, 560)
    # a direct route sends neither a pin nor the metadata header
    direct = FakeSDK([LITERAL_OK], model="gemini-3.8-flash", provider=None)
    endpoint = rd.LADDER["gemini-3.8-flash"].endpoint()
    route = rd.ROUTES["gemini-3.8-flash"]
    client = rd.RouteCheckedClient(endpoint, ("gemini-3.8-flash",), route=route, sdk=direct)
    client.complete_metered("hello", decoding=rd.decoding_for(0.0))
    assert "extra_headers" not in direct.calls[0] and "extra_body" not in direct.calls[0]
    assert client.last_served["provider"] is None


def test_client_refuses_another_model_or_provider() -> None:
    other_model = make_client(FakeSDK([LITERAL_OK], model="meta-llama/llama-3.1-8b-instruct"))
    with pytest.raises(rd.ServedModelMismatch, match=r"llama-3\.1-8b"):
        other_model.complete_metered("hello", decoding=rd.decoding_for(0.0))
    assert other_model.last_billed == (500, 60, 560)  # billed all the same, so it is kept
    assert other_model.last_served["model"] == "meta-llama/llama-3.1-8b-instruct"
    other_provider = make_client(FakeSDK([LITERAL_OK], model=LLAMA, provider="Together"))
    with pytest.raises(rd.ServedProviderMismatch, match="Together"):
        other_provider.complete_metered("hello", decoding=rd.decoding_for(0.0))
    assert other_provider.last_billed == (500, 60, 560)
    silent = make_client(FakeSDK([LITERAL_OK], model=LLAMA, provider=None))
    silent.complete_metered("hello", decoding=rd.decoding_for(0.0))
    assert silent.last_served["provider"] is None


def pinned_reader(tmp_path: Path, sdk: FakeSDK, **kwargs) -> rd.Reader:
    model = "llama-3.3-70b"
    return make_reader(
        tmp_path, make_client(sdk, model), model=model, route=PINNED[model], **kwargs
    )


def test_rows_and_cache_keep_the_echoed_model_and_provider(tmp_path: Path) -> None:
    sdk = FakeSDK(["not json", LITERAL_OK], model=LLAMA)
    row = pinned_reader(tmp_path, sdk).read(make_item())
    assert (row["status"], row["echo"]) == ("repaired", "ok")
    assert (row["model_id"], row["provider_pin"]) == (LLAMA, "deepinfra/turbo")
    assert [(a["served_model"], a["served_provider"]) for a in row["attempts"]] == [
        (LLAMA, "DeepInfra")
    ] * 2
    assert not any(key.startswith("_") for key in row["attempts"][0])
    # resumed from the cache: no call, and the row still says who served the answer
    idle = FakeSDK([], model=LLAMA)
    reader = pinned_reader(tmp_path, idle)
    again = reader.read(make_item())
    assert idle.calls == [] and again["echo"] == "ok"
    assert [a["cache_hit"] for a in again["attempts"]] == [True, True]
    assert again["attempts"][1]["served_provider"] == "DeepInfra"
    assert reader.responses[0]["served"]["model"] == LLAMA
    # the pin is part of the cache key: under another pin the answer is asked for again
    moved = replace(PINNED["llama-3.3-70b"], provider="novita/bf16", quantization="bf16")
    other = make_reader(
        tmp_path, FakeInner([LITERAL_OK]), model="llama-3.3-70b", cap=5.0, route=moved
    )
    assert other.read(make_item())["attempts"][0]["cache_hit"] is False


def test_a_cache_entry_is_written_once_with_its_echo(tmp_path: Path, monkeypatch) -> None:
    replaced: list[str] = []
    real_replace = os.replace

    def counting_replace(src, dst):
        replaced.append(Path(dst).name)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", counting_replace)
    raw = RawResponse(text="x", prompt_tokens=5, completion_tokens=2, total_tokens=7)
    served = {"model": LLAMA, "provider": "DeepInfra", "provider_names": ["DeepInfra"]}
    cache = rd.ReadCache(tmp_path / "cache")
    cache.put("sha256:" + "a" * 64, raw, served)
    assert replaced == ["a" * 64 + ".json"]  # one write: never an answer without its echo
    plain = DiskCache(tmp_path / "plain")
    plain.put("sha256:" + "a" * 64, raw)
    assert cache.get("sha256:" + "a" * 64) == plain.get("sha256:" + "a" * 64) | {"served": served}
    cache.put("sha256:" + "b" * 64, raw)  # a refusal or a scripted answer carries no echo
    assert "served" not in cache.get("sha256:" + "b" * 64)
    assert not list((tmp_path / "cache").rglob("*.tmp"))


def test_echo_flags(tmp_path: Path) -> None:
    scripted = make_reader(tmp_path / "a", FakeInner([LITERAL_OK])).read(make_item())
    assert scripted["echo"] == "not_recorded" and scripted["attempts"][0]["served_model"] is None
    quiet = FakeSDK([LITERAL_OK], model=LLAMA, provider=None)
    assert pinned_reader(tmp_path / "b", quiet).read(make_item())["echo"] == "provider_not_reported"
    assert rd.echo_acceptable("ok") and rd.echo_acceptable("refused")
    assert rd.echo_acceptable("provider_not_reported")  # until PROVIDER_ECHO_REQUIRED is set
    assert not rd.echo_acceptable("mismatch") and not rd.echo_acceptable("not_recorded")
    # an answer in the cache that another model gave is flagged when its row is written
    reader = pinned_reader(tmp_path / "c", FakeSDK([LITERAL_OK], model=LLAMA))
    reader.read(make_item())
    [entry] = (tmp_path / "c" / "cache").rglob("*.json")
    payload = json.loads(entry.read_text())
    payload["served"]["model"] = "meta-llama/llama-3.1-8b-instruct"
    entry.write_text(json.dumps(payload))
    assert pinned_reader(tmp_path / "c", FakeSDK([], model=LLAMA)).read(make_item())["echo"] == (
        "mismatch"
    )


@pytest.mark.parametrize(
    ("sdk_kwargs", "message"),
    [
        ({"model": "meta-llama/llama-3.1-8b-instruct"}, "llama-3.1-8b"),
        ({"model": LLAMA, "provider": "Together"}, "Together"),
    ],
)
def test_a_wrong_echo_stops_the_run_and_its_spend_is_logged(
    tmp_path: Path, sdk_kwargs: dict, message: str
) -> None:
    good = FakeSDK([LITERAL_OK], model=LLAMA)
    bad = FakeSDK(lambda prompt: LITERAL_OK, **sdk_kwargs)
    reader = pinned_reader(tmp_path, good)
    items = [make_item(item_id=f"i{n}") for n in range(3)]
    rows, status = rd.read_items(reader, items[:1])
    assert status == "complete"
    reader.transport.inner = make_client(bad)
    rows, status = rd.read_items(reader, items, rows=rows)
    assert status.startswith("aborted: served by another model or provider") and message in status
    assert [r["item_id"] for r in rows] == ["i0", "i0"] and len(bad.calls) == 1
    log = spend_rows(tmp_path)
    assert [r.get("status") for r in log if r["event"] == "call"] == ["ok", "served_mismatch"]
    assert log[-1]["usd"] == pytest.approx((500 * 0.10 + 60 * 0.32) / 1e6)
    assert reader.transport.spent_usd == pytest.approx(2 * log[-1]["usd"])
    assert len(DiskCache(tmp_path / "cache")) == 1  # the refused answer is not cached


def test_an_item_that_is_a_track_example_is_refused(tmp_path: Path) -> None:
    reader = make_reader(
        tmp_path, FakeInner([PREDICTIVE_OK]), template="predictive-track-v1", track=rd.CANARY_TRACK
    )
    with pytest.raises(ValueError, match="one of the track record's examples"):
        reader.read(make_item(item_id="canary-1"))
    row = reader.read(make_item(form="a year", date_of_update="2023-02-01"))
    assert row["warnings"] == ["no_track_row_for_item"]
    assert row["track_record_sha256"] is None and row["condition"].endswith("|track=-")


# --- samples and shards -------------------------------------------------------------------------


def test_sampled_quantiles_are_empirical_quantiles_of_the_sampled_medians(tmp_path: Path) -> None:
    medians = [200, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170]
    medians += [180, 190]  # 20 samples: 10, 20, ..., 200 in some order
    replies = [
        json.dumps(
            {
                "p_by_horizon_a": 0.3,
                "p_by_horizon_b": 0.6,
                "days_to_recovery": {"q10": 0, "q50": m, "q80": m, "q90": 365, "q95": 365},
            }
        )
        for m in medians
    ]
    inner = FakeInner(list(replies))
    reader = make_reader(tmp_path, inner, template="predictive-v1", temperature=1.0)
    rows, status = rd.read_items(reader, [make_item()], samples=20)
    assert status == "complete" and len(inner.calls) == 20
    assert {r["condition"] for r in rows} == {"predictive-v1|temp1-v1|mask=0|shift=0|track=-"}
    assert rd.sampled_quantiles(rows) == {
        "i1": {
            "samples": 20,
            "parsed": 20,
            "quantiles": {"q10": 20, "q50": 100, "q80": 160, "q90": 180, "q95": 190},
        }
    }
    # failed samples are left out and counted; an item with none has no quantiles
    partial = [r | {"reading": None} if r["sample"] >= 3 else r for r in rows]
    assert rd.sampled_quantiles(partial)["i1"] == {
        "samples": 20,
        "parsed": 3,
        "quantiles": {"q10": 10, "q50": 20, "q80": 200, "q90": 200, "q95": 200},
    }
    none = [r | {"reading": None, "item_id": "i2"} for r in rows[:2]]
    assert rd.sampled_quantiles(none) == {"i2": {"samples": 2, "parsed": 0, "quantiles": None}}


def test_shards_are_disjoint_and_cover_every_item() -> None:
    ids = [f"S{n:04d}" for n in range(400)]
    shards = [[i for i in ids if rd.shard_of(i, 4) == k] for k in range(4)]
    assert sorted(i for shard in shards for i in shard) == ids and all(len(s) > 60 for s in shards)
    assert rd.parse_shard("3/4") == (3, 4) and rd.parse_shard(None) is None
    for bad in ("4/4", "1", "a/b", "1/0"):
        with pytest.raises(SystemExit, match="--shard"):
            rd.parse_shard(bad)


# --- paid-call guards ---------------------------------------------------------------------------


def test_registration_and_f1_tags_must_be_ancestors_of_head(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path / "repo")
    monkeypatch.setattr(rd, "REPO", repo)
    assert not rd.tag_is_ancestor(rd.REGISTRATION_TAG)
    refusals = rd.paid_call_refusals(["train"])
    assert len(refusals) == 1 and "no paid call before the registration" in refusals[0]
    assert len(rd.paid_call_refusals(["train", "test"])) == 2
    # a tag on a commit that HEAD does not descend from is not a registration of HEAD
    git(repo, "checkout", "-q", "-b", "side")
    git(repo, "commit", "-q", "--allow-empty", "-m", "side")
    git(repo, "tag", rd.REGISTRATION_TAG)
    git(repo, "checkout", "-q", "main")
    assert not rd.tag_is_ancestor(rd.REGISTRATION_TAG) and rd.paid_call_refusals(["train"])
    git(repo, "tag", "-f", rd.REGISTRATION_TAG, "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "two")
    assert rd.tag_is_ancestor(rd.REGISTRATION_TAG)  # HEAD may have moved on from the tag
    assert rd.paid_call_refusals(["train"]) == []
    for period in ("test", "late"):
        [refusal] = rd.paid_call_refusals(["train", period])
        assert f"no call on {period}-period items before F1" in refusal and rd.F1_TAG in refusal
    git(repo, "tag", rd.F1_TAG)
    assert rd.paid_call_refusals(["train", "test", "late"]) == []
    monkeypatch.setattr(rd, "REPO", tmp_path)  # not a repository at all
    assert len(rd.paid_call_refusals(["test"])) == 2


def test_git_variables_in_the_environment_cannot_point_the_guards_elsewhere(
    tmp_path: Path, monkeypatch
) -> None:
    # another repository carries both tags; the checkout that holds the harness carries none
    tagged = make_repo(tmp_path / "tagged", rd.REGISTRATION_TAG, rd.F1_TAG)
    plain = make_repo(tmp_path / "plain")
    monkeypatch.setattr(rd, "REPO", plain)
    monkeypatch.setenv("GIT_DIR", str(tagged / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tagged))
    monkeypatch.setenv("GIT_COMMON_DIR", str(tagged / ".git"))
    assert not rd.tag_is_ancestor(rd.REGISTRATION_TAG) and not rd.tag_is_ancestor(rd.F1_TAG)
    assert len(rd.paid_call_refusals(["train", "test"])) == 2
    assert rd.roots_anchor() == plain / ".git" / rd.ROOTS_ANCHOR_NAME
    monkeypatch.setattr(rd, "REPO", tagged)  # and the tagged repository is still read as itself
    assert rd.paid_call_refusals(["train", "test"]) == []


def test_a_paying_client_is_refused_wherever_it_is_asked_for(tmp_path: Path, monkeypatch) -> None:
    built: list[tuple] = []

    def scripted_client(endpoint, served_as, **kwargs):
        built.append((endpoint.model_id, kwargs["route"].provider))
        return FakeInner([])

    monkeypatch.setattr(rd, "RouteCheckedClient", scripted_client)
    repo = make_repo(tmp_path / "repo")
    monkeypatch.setattr(rd, "REPO", repo)
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": None, "D3": ""})
    out, local = tmp_path / "out", tmp_path / "local"

    def build(model: str = "llama-3.3-70b", template: str | None = "predictive-v1", **more):
        chosen = rd.TEMPLATES[template] if template else None
        log = out / "r1" / "spend_log.jsonl"
        more = {"spend_cap_usd": 1.0, "periods": ["train"]} | more
        return rd.build_transport(
            model, spend_log=log, max_physical_calls=10, template=chosen, **more
        )

    def refused(message: str, **more) -> None:
        with pytest.raises(rd.LiveRunRefused, match=message):
            build(**more)
        assert built == [] and not out.exists()

    refused("needs the template", template=None)
    refused(r"UNSET.*no paid call before the registration")
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    refused("no paid call before the registration")
    git(repo, "tag", rd.REGISTRATION_TAG)
    # a caller that does not say which periods its items are in is held to the F1 rule
    with pytest.raises(rd.LiveRunRefused, match="before F1"):
        rd.build_transport(
            "llama-3.3-70b",
            spend_log=out / "r1" / "spend_log.jsonl",
            spend_cap_usd=1.0,
            max_physical_calls=10,
            template=rd.TEMPLATES["predictive-v1"],
        )
    refused("no call on late or test-period items before F1", periods=["test", "late"])
    refused(r"waits for the pilot sentences \['D1'\]", template="literal-v1")
    # registered and ready, but the budget rules come first: the shared roots, then the ledger
    refused("not the one every paid run shares")
    rd.check_roots(tmp_path / "elsewhere", local)
    refused("not the one every paid run shares")
    (repo / ".git" / rd.ROOTS_ANCHOR_NAME).unlink()
    rd.check_roots(out, local)
    refused("not declared in the study ledger")
    rd.declare_run(out, run="r1", model="deepseek-v3", cap_usd=1.0)
    with pytest.raises(rd.LiveRunRefused, match="not declared in the study ledger for llama"):
        build()  # declared for another model
    rd.declare_run(out, run="r1", model="llama-3.3-70b", cap_usd=1.0)
    with pytest.raises(rd.LiveRunRefused, match=r"with a cap of \$2\.0"):
        build(spend_cap_usd=2.0)  # another cap than the declared one
    rd.close_run(out, run="r1", model="llama-3.3-70b", spent_usd=0.0)
    with pytest.raises(rd.LiveRunRefused, match="not declared in the study ledger"):
        build()  # a finished run declares again before it calls again
    assert built == []
    rd.declare_run(out, run="r1", model="llama-3.3-70b", cap_usd=1.0)
    endpoint, guard = build()
    assert built == [(LLAMA, "deepinfra/turbo")] and guard.spend_cap_usd == 1.0
    assert endpoint.extra_body["provider"]["allow_fallbacks"] is False
    # a scripted client is never blocked: no repository, no tag, no ledger, no template
    monkeypatch.setattr(rd, "REPO", tmp_path)
    monkeypatch.setattr(rd, "ROUTES", {})
    _, guard = rd.build_transport(
        "deepseek-v3",
        spend_log=tmp_path / "x" / "spend_log.jsonl",
        spend_cap_usd=1.0,
        max_physical_calls=1,
        inner=FakeInner([]),
    )
    assert built == [(LLAMA, "deepinfra/turbo")] and guard.inner.model_id == "fake"


def test_all_paid_runs_share_one_out_root_and_one_local_root(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path / "repo")
    monkeypatch.setattr(rd, "REPO", repo)
    assert rd.roots_anchor() == repo / ".git" / rd.ROOTS_ANCHOR_NAME
    out, local = tmp_path / "out", tmp_path / "local"
    first = rd.check_roots(out, local)
    assert first == {"out_root": str(out), "local_root": str(local)}
    assert (
        rd.check_roots(out, tmp_path / "x" / ".." / "local") == first
    )  # resolved before comparing
    with pytest.raises(SystemExit, match="shares one output root and one local root"):
        rd.check_roots(tmp_path / "other-out", local)
    with pytest.raises(SystemExit, match="shares one output root and one local root"):
        rd.check_roots(out, tmp_path / "other-local")
    # a second worktree of the same repository finds the same file
    git(repo, "worktree", "add", "-q", str(tmp_path / "second"), "-b", "second")
    monkeypatch.setattr(rd, "REPO", tmp_path / "second")
    assert rd.roots_anchor() == repo / ".git" / rd.ROOTS_ANCHOR_NAME
    with pytest.raises(SystemExit, match="shares one output root"):
        rd.check_roots(tmp_path / "second" / "out", local)
    monkeypatch.setattr(rd, "REPO", tmp_path)
    with pytest.raises(SystemExit, match="needs the git repository"):
        rd.check_roots(out, local)


# --- the study ledger ---------------------------------------------------------------------------


def spend(out_root: Path, run: str, dollars: float) -> None:
    log = out_root / run / "spend_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as handle:
        handle.write(json.dumps({"event": "call", "usd": dollars}) + "\n")


def test_ledger_holds_planned_caps_per_model_and_for_the_study(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert rd.MODEL_CAPS_USD["llama-3.3-70b"] == 5.0
    rd.declare_run(out, run="a", model="llama-3.3-70b", cap_usd=3.0)
    # a run that has not spent anything still holds its cap: the second run cannot take it too
    with pytest.raises(SystemExit, match=r"hold \$3\.00.*would pass its \$5\.00 cap"):
        rd.declare_run(out, run="b", model="llama-3.3-70b", cap_usd=2.5)
    rd.declare_run(out, run="b", model="llama-3.3-70b", cap_usd=2.0)
    held = rd.held_by_run(out)
    assert {run: h["held_usd"] for run, h in held.items()} == {"a": 3.0, "b": 2.0}
    # a run declared again replaces its own declaration (a resumed run, a changed cap)
    rd.declare_run(out, run="b", model="llama-3.3-70b", cap_usd=1.0)
    with pytest.raises(SystemExit, match="would pass its"):
        rd.declare_run(out, run="b", model="llama-3.3-70b", cap_usd=2.01)
    # a finished run holds what it spent, which frees the rest of its cap
    spend(out, "a", 0.4)
    rd.close_run(out, run="a", model="llama-3.3-70b", spent_usd=0.4)
    assert rd.held_by_run(out)["a"] == {
        "model": "llama-3.3-70b",
        "cap_usd": 3.0,
        "open": False,
        "spent_usd": 0.4,
        "held_usd": 0.4,
    }
    rd.declare_run(out, run="c", model="llama-3.3-70b", cap_usd=3.6)
    # another model has its own cap, and the study its own
    rd.declare_run(out, run="g", model="gemini-3.8-flash", cap_usd=110.0)
    with pytest.raises(SystemExit, match=r"gemini-3\.8-flash hold \$110\.00"):
        rd.declare_run(out, run="g2", model="gemini-3.8-flash", cap_usd=0.5)
    rd.declare_run(out, run="k", model="grok-4.20", cap_usd=30.0)
    with pytest.raises(SystemExit, match=r"the study would pass its \$150\.00 cap"):
        rd.declare_run(out, run="d", model="deepseek-v3", cap_usd=6.0, study_cap_usd=150.0)
    with pytest.raises(SystemExit, match="cannot be raised"):
        rd.declare_run(out, run="d", model="deepseek-v3", cap_usd=6.0, study_cap_usd=250.0)
    summary = rd.ledger_summary(out)
    assert summary["held_usd"] == pytest.approx(0.4 + 1.0 + 3.6 + 110.0 + 30.0)
    assert summary["spent_usd"] == pytest.approx(0.4)
    assert summary["models"]["llama-3.3-70b"] == {
        "runs": 3,
        "spent_usd": pytest.approx(0.4),
        "held_usd": pytest.approx(5.0),
        "cap_usd": 5.0,
    }
    rows = [json.loads(line) for line in (out / rd.LEDGER_NAME).read_text().splitlines()]
    assert [r["event"] for r in rows].count("declare") == 6 and rows[-1]["run"] == "k"


def test_ledger_counts_overspend_and_undeclared_runs_and_logs_amendments(tmp_path: Path) -> None:
    out = tmp_path / "out"
    rd.declare_run(out, run="a", model="qwen-2.5-7b", cap_usd=1.0)
    spend(out, "a", 1.2)  # a run can pass its cap by one call; the ledger then holds its spend
    assert rd.held_by_run(out)["a"]["held_usd"] == 1.2
    with pytest.raises(SystemExit, match=r"hold \$1\.20"):
        rd.declare_run(out, run="b", model="qwen-2.5-7b", cap_usd=1.9)
    spend(out, "stray", 190.0)  # a spend log with no declaration counts for the study
    with pytest.raises(SystemExit, match=r"the study would pass its \$200\.00 cap"):
        rd.declare_run(out, run="k", model="grok-4.20", cap_usd=9.0)
    assert rd.recorded_spend(out) == pytest.approx(191.2)
    assert rd.recorded_spend(out, exclude="stray") == pytest.approx(1.2)
    # the registered cap of a model is replaced only with a note, which the ledger keeps
    with pytest.raises(SystemExit, match="needs an --amendment note"):
        rd.declare_run(out, run="b", model="qwen-2.5-7b", cap_usd=3.0, model_cap_usd=5.0)
    row = rd.declare_run(
        out, run="b", model="qwen-2.5-7b", cap_usd=3.0, model_cap_usd=5.0, amendment="A3: reserve"
    )
    assert row["amendment"] == "A3: reserve" and row["model_cap_usd"] == 5.0
    assert rd.ledger_summary(out)["models"]["undeclared"]["spent_usd"] == 190.0


def held_usd(out_root: Path) -> dict[str, float]:
    return {run: entry["held_usd"] for run, entry in rd.held_by_run(out_root).items()}


def test_ledger_through_a_failed_run_a_resumed_run_and_a_deleted_folder(tmp_path: Path) -> None:
    out = tmp_path / "out"
    model = "deepseek-v3"  # its cap is $12
    # a run that failed (declared, some spend, never finished) keeps holding its whole cap
    rd.declare_run(out, run="a", model=model, cap_usd=8.0)
    spend(out, "a", 2.0)
    assert held_usd(out) == {"a": 8.0}
    with pytest.raises(SystemExit, match=r"hold \$8\.00"):
        rd.declare_run(out, run="b", model=model, cap_usd=4.5)
    # resumed under its own name with the same cap: its own cap and spend are not counted twice
    rd.declare_run(out, run="a", model=model, cap_usd=8.0)
    rd.declare_run(out, run="b", model=model, cap_usd=4.0)
    assert held_usd(out) == {"a": 8.0, "b": 4.0}
    # the failed run is given up: declared again with a small cap, it holds what it spent
    rd.declare_run(out, run="a", model=model, cap_usd=0.5)
    assert held_usd(out) == {"a": 2.0, "b": 4.0}
    # a resumed run that asks for more than is left is refused, and keeps its earlier entry
    with pytest.raises(SystemExit, match=r"hold \$4\.00.*would pass its \$12\.00 cap"):
        rd.declare_run(out, run="a", model=model, cap_usd=8.5)
    assert held_usd(out)["a"] == 2.0
    # finished, then its folder is deleted: the ledger still counts what it cost
    rd.close_run(out, run="a", model=model, spent_usd=2.0)
    shutil.rmtree(out / "a")
    assert rd.held_by_run(out)["a"] == {
        "model": model,
        "cap_usd": 0.5,
        "open": False,
        "spent_usd": 2.0,
        "held_usd": 2.0,
    }
    with pytest.raises(SystemExit, match=r"hold \$6\.00"):
        rd.declare_run(out, run="c", model=model, cap_usd=6.5)
    rd.declare_run(out, run="c", model=model, cap_usd=6.0)
    assert sum(held_usd(out).values()) == rd.MODEL_CAPS_USD[model]
    # a run declared again after it finished holds its new cap, and never less than it cost
    with pytest.raises(SystemExit, match=r"hold \$10\.00"):
        rd.declare_run(out, run="a", model=model, cap_usd=2.5)
    rd.declare_run(out, run="a", model=model, cap_usd=1.0)
    assert held_usd(out)["a"] == 2.0
    assert rd.ledger_summary(out)["held_usd"] == pytest.approx(12.0)
    # a damaged ledger stops every declaration: nothing is assumed about what it held
    with (out / rd.LEDGER_NAME).open("a") as handle:
        handle.write('{"event": "declare", "run": "z", "mod')
    with pytest.raises(json.JSONDecodeError):
        rd.declare_run(out, run="k", model="grok-4.20", cap_usd=1.0)


def test_a_model_cap_is_raised_within_the_reserve_only(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert sum(rd.MODEL_CAPS_USD.values()) == 169.0 and rd.STUDY_CAP_USD == 200.0
    note = {"amendment": "A1: grok takes the reserve"}
    # $30 plus the whole reserve of $31 is the most grok-4.20 can be given
    with pytest.raises(SystemExit, match=r"within the reserve.*sum to \$200\.50"):
        rd.declare_run(out, run="k", model="grok-4.20", cap_usd=1.0, model_cap_usd=61.5, **note)
    assert not (out / rd.LEDGER_NAME).exists()
    rd.declare_run(out, run="k", model="grok-4.20", cap_usd=40.0, model_cap_usd=61.0, **note)
    assert rd.amended_caps(out) == {"grok-4.20": 61.0}
    # the reserve is spent: a second model cannot be raised as well, in a later declaration
    with pytest.raises(SystemExit, match=r"within the reserve.*sum to \$200\.50"):
        rd.declare_run(
            out, run="q", model="qwen-2.5-7b", cap_usd=1.0, model_cap_usd=3.5, amendment="A2"
        )
    # a raised cap is not a standing one: the next run of the model must name it again
    with pytest.raises(SystemExit, match=r"would pass its \$30\.00 cap"):
        rd.declare_run(out, run="k2", model="grok-4.20", cap_usd=1.0)
    # the amendment can be taken back in part, which frees reserve for another model
    rd.declare_run(
        out, run="k", model="grok-4.20", cap_usd=40.0, model_cap_usd=60.0, amendment="A3"
    )
    rd.declare_run(
        out, run="q", model="qwen-2.5-7b", cap_usd=1.0, model_cap_usd=4.0, amendment="A4"
    )
    assert rd.amended_caps(out) == {"grok-4.20": 60.0, "qwen-2.5-7b": 4.0}
    # with the caps summing to $200 at most, declared runs alone cannot pass the study's $200;
    # dollars spent outside any declaration still count against it
    rd.declare_run(out, run="g", model="gemini-3.8-flash", cap_usd=110.0)
    rd.declare_run(out, run="d", model="deepseek-v3", cap_usd=12.0)
    rd.declare_run(out, run="l", model="llama-3.3-70b", cap_usd=5.0)
    rd.declare_run(out, run="m", model="gemma-3-27b", cap_usd=3.0)
    rd.declare_run(out, run="o", model="gpt-oss-20b", cap_usd=3.0)
    rd.declare_run(out, run="n", model="gpt-4o-mini", cap_usd=3.0)
    assert rd.ledger_summary(out)["held_usd"] == pytest.approx(177.0)
    rd.declare_run(
        out, run="k3", model="grok-4.20", cap_usd=20.0, model_cap_usd=60.0, amendment="A3"
    )
    spend(out, "stray", 1.0)
    with pytest.raises(SystemExit, match=r"the study would pass its \$200\.00 cap"):
        rd.declare_run(
            out, run="q2", model="qwen-2.5-7b", cap_usd=3.0, model_cap_usd=4.0, amendment="A4"
        )


def test_runs_launched_together_cannot_take_the_same_dollars(tmp_path: Path) -> None:
    # six processes each ask for $2 of a $5 model cap at the same moment: two get it
    code = (
        "import sys; from pathlib import Path; import analysis.coling.read as rd; "
        "rd.declare_run(Path(sys.argv[1]), run=sys.argv[2], model='llama-3.3-70b', cap_usd=2.0)"
    )
    root = str(Path(rd.__file__).resolve().parents[2])
    env = os.environ | {"PYTHONPATH": root, "PYTHONDONTWRITEBYTECODE": "1"}
    out = tmp_path / "out"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(out), f"run{n}"], env=env, stderr=subprocess.PIPE
        )
        for n in range(6)
    ]
    results = [(p.communicate()[1].decode(), p.returncode) for p in procs]
    assert sorted(code for _, code in results) == [0, 0, 1, 1, 1, 1]
    assert all("would pass its $5.00 cap" in err for err, code in results if code)
    held = rd.held_by_run(out)
    assert len(held) == 2 and sum(h["held_usd"] for h in held.values()) == 4.0


def test_a_declaration_waits_for_the_ledger_lock(tmp_path: Path) -> None:
    # the check and the write of a declaration happen under one lock: while another process
    # holds it, a declaration neither reads the ledger nor writes to it
    code = (
        "import sys; from pathlib import Path; import analysis.coling.read as rd; "
        "print('ready', flush=True); "
        "rd.declare_run(Path(sys.argv[1]), run='late', model='llama-3.3-70b', cap_usd=2.0)"
    )
    root = str(Path(rd.__file__).resolve().parents[2])
    env = os.environ | {"PYTHONPATH": root, "PYTHONDONTWRITEBYTECODE": "1"}
    out = tmp_path / "out"
    command = [sys.executable, "-c", code, str(out)]
    pipes = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    with rd._locked(out / f"{rd.LEDGER_NAME}.lock"):
        proc = subprocess.Popen(command, env=env, **pipes)
        try:
            assert proc.stdout.readline().strip() == "ready"
            with pytest.raises(subprocess.TimeoutExpired):
                proc.wait(timeout=1.0)
            assert not (out / rd.LEDGER_NAME).exists()
            # what the holder of the lock declares meanwhile is seen by the one that waits
            first = {"event": "declare", "run": "first", "model": "llama-3.3-70b", "cap_usd": 4.0}
            rd._append_ledger(out, first)
        except BaseException:
            proc.kill()
            raise
    errors = proc.communicate(timeout=60)[1]
    assert proc.returncode == 1 and "hold $4.00" in errors
    assert list(rd.held_by_run(out)) == ["first"]


# --- the run sheet ------------------------------------------------------------------------------


def test_run_sheet_projects_calls_and_cost_per_model() -> None:
    counts = {"e2": 120, "e3": 1000, "probe": 300, "samples": 300, "dev": 100, "twobytwo": 300}
    sheet = rd.run_sheet(counts)
    models = sheet["models"]
    # gemini reads E2 (two prompts) and the three E3 conditions only
    assert models["gemini-3.8-flash"]["calls"] == 2 * 120 + 3 * 1000
    assert set(models["gemini-3.8-flash"]["lines"]) == {
        "e2-literal",
        "e2-literal-free",
        "e3-a",
        "e3-b",
        "e3-c",
    }
    secondary = 2 * 120 + 3 * 1000 + 300
    assert models["grok-4.20"]["calls"] == models["qwen-2.5-7b"]["calls"] == secondary
    primary = secondary + 20 * 300 + 3 * 100 + 3 * 300
    assert models["llama-3.3-70b"]["calls"] == models["deepseek-v3"]["calls"] == primary
    assert models["llama-3.3-70b"]["lines"]["e3-samples"]["calls"] == 6000
    assert sheet["total"]["calls"] == sum(m["calls"] for m in models.values())
    assert sheet["total"]["caps_usd"] == 169.0 and sheet["total"]["reserve_usd"] == 31.0
    assert sheet["counts"]["e5"] == 0 and "e5" in sheet["counts_not_given"]
    for model, slot in models.items():
        assert 0 < slot["usd_typical"] <= slot["usd_upper"]
        assert slot["cap_usd"] == rd.MODEL_CAPS_USD[model]
    # one line, by hand: prompt tokens times the input price plus output tokens times the output
    line = next(entry for entry in sheet["lines"] if entry["name"] == "e3-a")
    tokens = round(rd.sheet_prompt_tokens()["predictive-v1"])
    assert line["prompt_tokens"] == rd.sheet_prompt_tokens()["predictive-v1"]
    each = (
        tokens * 0.10 + rd.output_tokens("llama-3.3-70b", "predictive", upper=False) * 0.32
    ) / 1e6
    assert models["llama-3.3-70b"]["lines"]["e3-a"]["usd_typical"] == pytest.approx(
        1000 * each, abs=1e-4
    )
    # with the plan's fixed counts, the calls per model are the formulas of PLAN section 9
    fixed = {"e2": 120, "probe": 300, "e5": 800, "trial": 20, "twobytwo": 300}
    fixed |= {"paraphrase": 200, "samples": 300}
    n_e, n_s, n_d = 2585, 1030, 661
    plan = rd.run_sheet(fixed | {"e3": n_e, "e3_secondary": n_s, "dev": n_d})["models"]
    assert plan["gemini-3.8-flash"]["calls"] == 320 + 3 * n_e
    for model in ("grok-4.20", "qwen-2.5-7b", "gemma-3-27b", "gpt-oss-20b", "gpt-4o-mini"):
        assert plan[model]["calls"] == 1440 + 3 * n_e
    for model in rd.PRIMARIES:
        assert plan[model]["calls"] == 8940 + 3 * (n_e + n_s + n_d)
    with_e6 = rd.run_sheet(fixed | {"e3": n_e, "e6": 1200})["models"]
    assert with_e6["grok-4.20"]["calls"] == 1440 + 3 * n_e + 1200
    assert "e6" not in with_e6["gemini-3.8-flash"]["lines"]
    # every run gets a cap, and the caps of a model's runs never pass the model's cap
    for model, slot in plan.items():
        caps = [entry["cap_usd"] for entry in slot["lines"].values()]
        assert all(cap > 0 for cap in caps)
        assert rd.MODEL_CAPS_USD[model] - 0.01 < sum(caps) <= rd.MODEL_CAPS_USD[model] + 1e-9
    # the track-record prompt is priced with a full-size table and ten examples
    assert rd.sheet_prompt_tokens()["predictive-track-v1"] > 2 * tokens
    assert len(rd._sheet_track().slip_table) == 33 and len(rd._sheet_track().examples) == 10


def test_run_sheet_options_and_table(tmp_path: Path, capsys) -> None:
    counts = {"e2": 120, "e3": 1000}
    base = rd.run_sheet(counts)
    priced = rd.run_sheet(counts, prices={"deepseek-v3": (0.32, 0.89)})
    assert priced["models"]["deepseek-v3"]["usd_per_mtok"] == [0.32, 0.89]
    assert (
        priced["models"]["deepseek-v3"]["usd_typical"]
        != base["models"]["deepseek-v3"]["usd_typical"]
    )
    flat = rd.run_sheet(counts, per_call_usd={"gemini-3.8-flash": 0.011})
    assert flat["models"]["gemini-3.8-flash"]["usd_typical"] == pytest.approx(3240 * 0.011)
    assert flat["models"]["gemini-3.8-flash"]["per_call_usd_given"] is True
    repaired = rd.run_sheet(counts, repair_rate=0.05)
    assert repaired["models"]["grok-4.20"]["calls"] == 2 * 126 + 3 * 1050
    with pytest.raises(SystemExit, match="unknown counts \\['e33'\\]"):
        rd.run_sheet({"e33": 5})
    items = tmp_path / "items.jsonl"
    items.write_text(json.dumps({"item_id": "a", "date_of_update": "2021-02-03"}) + "\n")
    code = rd.main(
        ["--run-sheet", "--count", "e2=120", "--count", "e3=1000", "--sheet-format", "md",
         "--price", "gemma-3-27b=0.08,0.16", "--per-call-usd", "gemini-3.8-flash=0.011",
         "--items", str(items)]
    )  # fmt: skip
    table = capsys.readouterr().out
    assert (
        code == 0 and "| Model | Calls | Cost per call | Estimate | Upper estimate | Cap |" in table
    )
    assert "| gemini-3.8-flash | 3,240 | $0.01100 | $35.64 |" in table
    assert "| e3-b | predictive-track-v1 | 1,000 | 1,000 | 8 |" in table and "**All**" in table
    assert "Suggested cap per run, in dollars" in table and "| Run | llama-3.3-70b |" in table
    assert rd.main(["--run-sheet", "--count", "e2=120"]) == 0
    assert json.loads(capsys.readouterr().out)["prompt_tokens_from"] == "the canary item"
    with pytest.raises(SystemExit, match="not among the eight readers"):
        rd.main(["--run-sheet", "--price", "qwen-2.5-72b=1,1"])
    with pytest.raises(SystemExit, match="takes NAME=VALUE"):
        rd.main(["--run-sheet", "--count", "e2"])


# --- dry run and the command line -------------------------------------------------------------


def _no_live_client(*args, **kwargs):
    raise AssertionError("a live client was constructed")


def write_items(tmp_path: Path, items) -> Path:
    path = tmp_path / "items.jsonl"
    path.write_text("".join(json.dumps(i.__dict__ | {"mask_terms": []}) + "\n" for i in items))
    return path


def test_dry_run_prices_without_calling(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(rd, "RouteCheckedClient", _no_live_client)
    monkeypatch.setattr(rd, "REPO", tmp_path)  # no repository, no tag: a dry run asks for neither
    items = [make_item(item_id="a"), make_item(item_id="b", date_of_update="2024-02-01")]
    path = write_items(tmp_path, items)
    code = rd.main(
        ["--items", str(path), "--template", "predictive-v1", "--model", "gemini-3.8-flash",
         "--model", "llama-3.3-70b", "--dry-run", "--show", "1", "--out-root",
         str(tmp_path / "out"), "--local-root", str(tmp_path / "local")]
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 0 and "===== a (train)" in out
    summary = json.loads(out[out.rindex("\n{\n") + 1 :])
    # the late period (2026 on) is counted beside train and test
    assert summary["items_by_period"] == {"train": 1, "test": 1, "late": 0}
    gem, llama = summary["models"]["gemini-3.8-flash"], summary["models"]["llama-3.3-70b"]
    assert gem["calls"] == 2 and gem["usd_upper"] > gem["usd_typical"] > llama["usd_typical"] > 0
    assert (gem["route_ready"], llama["route_ready"]) == (True, False)
    assert summary["ledger"]["held_usd"] == 0 and summary["template_pending"] == []
    assert not (tmp_path / "out").exists() and not (tmp_path / "local").exists()
    # a literal template can be dry-run while its pilot sentences are pending
    roots = ["--out-root", str(tmp_path / "out"), "--local-root", str(tmp_path / "local")]
    assert rd.main(["--items", str(path), "--model", "deepseek-v3", "--dry-run", *roots]) == 0
    pending = list(rd.TEMPLATES["literal-v1"].pending)
    assert json.loads(capsys.readouterr().out)["template_pending"] == pending


def test_dry_run_counts_cached_calls(tmp_path: Path) -> None:
    reader = make_reader(tmp_path, FakeInner([LITERAL_OK]))
    reader.read(make_item())
    summary = rd.dry_run(
        [make_item(), make_item(item_id="i2")],
        models=["deepseek-v3"],
        template=rd.TEMPLATES["literal-v1"],
        track=None,
        samples=1,
        temperature=0.0,
        mask_names=False,
        shift_years=0,
        cache_dir=tmp_path / "cache",
    )
    assert summary["models"]["deepseek-v3"]["cached_calls"] == 1


def test_cli_guards(tmp_path: Path, monkeypatch, live_ready: Path) -> None:
    monkeypatch.setattr(rd, "RouteCheckedClient", _no_live_client)
    train = write_items(tmp_path, [make_item()])
    roots = ["--out-root", str(tmp_path / "o"), "--local-root", str(tmp_path / "l")]
    base = ["--items", str(train), "--model", "deepseek-v3", *roots]
    live = [*base, "--run-name", "r1", "--spend-cap-usd", "1"]
    with pytest.raises(SystemExit, match="--allow-live"):
        rd.main(live)
    with pytest.raises(SystemExit, match="temperature"):
        rd.main([*base, "--dry-run", "--samples", "3"])
    with pytest.raises(SystemExit, match="spend-cap"):
        rd.main([*base, "--run-name", "r1", "--allow-live"])
    with pytest.raises(SystemExit, match="not one of the eight readers"):
        rd.main(["--items", str(train), "--model", "qwen-2.5-72b", *live[4:], "--allow-live"])
    (tmp_path / "t").mkdir()
    test = write_items(tmp_path / "t", [make_item(date_of_update="2023-05-01")])
    # the message now names F1: a test or late item needs the flag and the F1 tag
    with pytest.raises(SystemExit, match="only after the freeze amendment F1"):
        rd.main(["--items", str(test), *live[2:], "--allow-live"])
    spend(tmp_path / "o", "earlier-run", 199.5)
    with pytest.raises(SystemExit, match="study would pass"):
        rd.main([*live, "--allow-live"])
    with pytest.raises(SystemExit, match=r"would pass its \$12\.00 cap"):
        rd.main([*live[:-1], "12.5", "--allow-live"])
    assert not (tmp_path / "o" / "r1").exists() and not (tmp_path / "l").exists()


def test_cli_refuses_a_live_run_that_is_not_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rd, "RouteCheckedClient", _no_live_client)
    repo = make_repo(tmp_path / "repo")
    monkeypatch.setattr(rd, "REPO", repo)
    train = write_items(tmp_path, [make_item()])
    (tmp_path / "t").mkdir()
    test = write_items(tmp_path / "t", [make_item(date_of_update="2026-02-01")])
    roots = ["--out-root", str(tmp_path / "o"), "--local-root", str(tmp_path / "l")]
    tail = ["--run-name", "r1", "--spend-cap-usd", "1", "--allow-live", *roots]

    def run(items: Path, *more: str) -> None:
        rd.main(["--items", str(items), "--model", "deepseek-v3", *tail, *more])

    # 1. the literal templates wait for the pilot sentences
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": None, "D3": None})
    with pytest.raises(SystemExit, match="waits for the pilot sentences \\['D1', 'D3'\\]"):
        run(train)
    # 2. the route has no provider yet, and nothing is registered
    with pytest.raises(SystemExit, match=r"UNSET.*no paid call before the registration"):
        run(train, "--template", "predictive-v1")
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    with pytest.raises(SystemExit, match="no paid call before the registration"):
        run(train, "--template", "predictive-v1")
    # 3. registered: train-period items may be read, late-period items need F1 as well
    git(repo, "tag", rd.REGISTRATION_TAG)
    with pytest.raises(SystemExit, match="no call on late-period items before F1"):
        run(test, "--template", "predictive-v1", "--allow-test-items")
    git(repo, "tag", rd.F1_TAG)
    with pytest.raises(SystemExit, match="only after the freeze amendment F1"):
        run(test, "--template", "predictive-v1")  # the flag is still asked for
    # 4. with everything in place the next step is the client itself
    with pytest.raises(AssertionError, match="a live client was constructed"):
        run(test, "--template", "predictive-v1", "--allow-test-items")
    assert not (tmp_path / "o" / "r1" / "readings.jsonl").exists()


def live_args(tmp_path: Path, items: Path, run: str, *more: str) -> list[str]:
    return ["--items", str(items), "--model", "llama-3.3-70b", "--run-name", run,
            "--spend-cap-usd", "1", "--allow-live", "--out-root", str(tmp_path / "out"),
            "--local-root", str(tmp_path / "local"), *more]  # fmt: skip


def use_sdk(monkeypatch, sdk: FakeSDK) -> None:
    """Let the command line build the real client around a scripted SDK (no key, no network)."""
    monkeypatch.setattr(
        rd,
        "RouteCheckedClient",
        lambda endpoint, served_as, **kw: RealClient(
            endpoint, served_as, route=kw["route"], sdk=sdk
        ),
    )


def test_cli_live_run_end_to_end_with_a_fake(tmp_path, monkeypatch, capsys, live_ready) -> None:
    sdk = FakeSDK(lambda prompt: LITERAL_OK, model=LLAMA)
    use_sdk(monkeypatch, sdk)
    path = write_items(tmp_path, [make_item(item_id="a"), make_item(item_id="b")])
    out_root, local_root = tmp_path / "out", tmp_path / "local"
    args = live_args(tmp_path, path, "lit-llama")
    assert rd.main(args) == 0
    run = out_root / "lit-llama"
    readings = [json.loads(line) for line in (run / "readings.jsonl").read_text().splitlines()]
    assert [r["item_id"] for r in readings] == ["a", "b"] and len(sdk.calls) == 2
    assert {r["echo"] for r in readings} == {"ok"}
    assert sdk.calls[0]["extra_body"]["provider"]["order"] == ["deepinfra/turbo"]
    manifest = json.loads((run / "run_manifest.json").read_text())
    assert manifest["by_status"] == {"ok": 2} and manifest["template"] == "literal-v1"
    assert manifest["complete"] is True and manifest["expected_rows"] == 2
    assert manifest["item_ids_sha256"] == rd._ids_sha256(["a", "b"])
    assert manifest["by_echo"] == {"ok": 2} and manifest["fallbacks"] == 0
    assert manifest["route"]["provider"] == "deepinfra/turbo"
    assert manifest["provider_object"]["allow_fallbacks"] is False
    assert manifest["usd_per_mtok"] == [0.10, 0.32] and manifest["price_date"] == "2026-10-01"
    assert manifest["read_py_sha256"] == rd._sha256_file(Path(rd.__file__))
    assert manifest["git"]["registration"] and manifest["git"]["f1"]
    assert manifest["roots"] == {"out_root": str(out_root), "local_root": str(local_root)}
    assert (local_root / "lit-llama" / "responses.jsonl").is_file()
    assert len(DiskCache(local_root / "cache")) == 2  # one cache for every run
    assert rd.recorded_spend(out_root) == pytest.approx(manifest["guard"]["usd_total"])
    # the finished run holds what it spent, not its cap
    held = rd.held_by_run(out_root)["lit-llama"]
    assert held["open"] is False and held["held_usd"] == held["spent_usd"] < 0.01
    capsys.readouterr()
    assert rd.main(args) == 0 and len(sdk.calls) == 2  # the rerun is served from the cache
    invocations = (run / "invocations.jsonl").read_text().splitlines()
    assert len(invocations) == 2 and json.loads(invocations[1])["guard"]["usd_this_invocation"] == 0
    with pytest.raises(SystemExit, match="other settings"):
        rd.main([*args, "--shift-years", "2"])
    with pytest.raises(SystemExit, match=r"other settings.*shard"):
        rd.main([*args, "--shard", "0/2"])
    # another root is refused before anything is written there
    with pytest.raises(SystemExit, match="shares one output root and one local root"):
        rd.main([*args[:-1], str(tmp_path / "elsewhere")])
    assert not (tmp_path / "elsewhere").exists()
    capsys.readouterr()
    assert rd.main(["--check-runs", "--out-root", str(out_root)]) == 0
    [entry] = json.loads(capsys.readouterr().out)
    assert (
        entry["ready"] is True
        and entry["items_answered"] == 2
        and entry["model"] == "llama-3.3-70b"
    )


def test_declare_only_writes_the_cap_and_makes_no_call(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(rd, "RouteCheckedClient", _no_live_client)
    monkeypatch.setattr(rd, "REPO", make_repo(tmp_path / "repo"))  # not registered yet
    path = write_items(tmp_path, [make_item(date_of_update="2024-01-01")])
    args = live_args(tmp_path, path, "plan-llama")
    args[args.index("--allow-live")] = "--declare-only"
    assert rd.main(args) == 0
    assert json.loads(capsys.readouterr().out)["cap_usd"] == 1.0
    assert rd.held_by_run(tmp_path / "out") == {
        "plan-llama": {
            "model": "llama-3.3-70b",
            "cap_usd": 1.0,
            "open": True,
            "spent_usd": 0.0,
            "held_usd": 1.0,
        }
    }
    assert not (tmp_path / "out" / "plan-llama").exists()


def test_shards_resume_and_completeness(tmp_path, monkeypatch, capsys, live_ready) -> None:
    sdk = FakeSDK(lambda prompt: PREDICTIVE_OK, model=LLAMA)
    use_sdk(monkeypatch, sdk)
    items = [make_item(item_id=f"S{n:03d}", date_of_update="2021-05-04") for n in range(12)]
    path = write_items(tmp_path, items)
    out_root = tmp_path / "out"
    predictive = ["--template", "predictive-v1"]
    sizes = []
    for k in range(3):
        args = live_args(tmp_path, path, f"e3-a-llama.s{k}", *predictive, "--shard", f"{k}/3")
        assert rd.main(args) == 0
        manifest = json.loads((out_root / f"e3-a-llama.s{k}" / "run_manifest.json").read_text())
        assert manifest["complete"] and manifest["shard"] == f"{k}/3"
        assert manifest["items_in_file"] == 12
        sizes.append(manifest["items"])
    assert sum(sizes) == 12 == len(sdk.calls)
    groups = rd.collect_readings(out_root)
    [key] = groups
    assert key == ("llama-3.3-70b", "predictive-v1|det-v1|mask=0|shift=0|track=-")
    assert groups[key]["item_ids"] == {i.item_id for i in items}
    assert set(groups[key]["runs"]) <= {f"e3-a-llama.s{k}" for k in range(3)}
    assert not groups[key]["incomplete_runs"] and not groups[key]["duplicates"]
    capsys.readouterr()
    check = ["--check-runs", "--out-root", str(out_root), "--items", str(path), *predictive]
    assert rd.main(check) == 0
    [entry] = json.loads(capsys.readouterr().out)
    assert (entry["expected"], entry["missing"], entry["unexpected"], entry["ready"]) == (
        12,
        0,
        0,
        True,
    )
    assert entry["item_ids_sha256"] == rd._ids_sha256(i.item_id for i in items)
    # the same items under another run name cost nothing (one cache), and show up as duplicates
    assert rd.main(live_args(tmp_path, path, "e3-a-llama.all", *predictive)) == 0
    assert len(sdk.calls) == 12
    capsys.readouterr()
    assert rd.main(check) == 3
    [entry] = json.loads(capsys.readouterr().out)
    assert entry["duplicates"] == 12 and entry["ready"] is False
    # against a longer expected list the group is incomplete, and the missing ids are named
    (tmp_path / "more").mkdir()
    more = write_items(tmp_path / "more", [*items, make_item(item_id="S999")])
    report = rd.check_runs(out_root, expected=[i.item_id for i in rd.load_items(more)])
    assert report[0]["missing"] == 1 and report[0]["missing_first"] == ["S999"]
    # no run of the template asked for: not ready
    assert rd.main(["--check-runs", "--out-root", str(out_root), "--items", str(path)]) == 3


def test_a_stopped_run_keeps_its_rows_and_resumes_free(
    tmp_path, monkeypatch, capsys, live_ready
) -> None:
    items = [make_item(item_id=f"i{n}") for n in range(4)]
    path = write_items(tmp_path, items)
    args = live_args(tmp_path, path, "lit-llama")
    run = tmp_path / "out" / "lit-llama"
    # stopped by its cap after two calls
    sdk = FakeSDK(lambda prompt: LITERAL_OK, model=LLAMA)
    use_sdk(monkeypatch, sdk)
    endpoint = rd.route_endpoint("llama-3.3-70b")
    one = rd.projected_call_usd(
        rd.render_for(rd.TEMPLATES["literal-v1"], items[0]), "llama-3.3-70b", "literal", endpoint
    )
    billed = (500 * 0.10 + 60 * 0.32) / 1e6  # what the scripted client bills per call
    capped = [*args]
    capped[capped.index("--spend-cap-usd") + 1] = str(one + 1.5 * billed)  # room for two calls
    assert rd.main(capped) == 3
    manifest = json.loads((run / "run_manifest.json").read_text())
    assert (
        manifest["status"].startswith("aborted: recorded spend") and manifest["complete"] is False
    )
    assert manifest["readings"] == 2 and manifest["expected_rows"] == 4
    assert rd.held_by_run(tmp_path / "out")["lit-llama"]["open"] is True
    [entry] = rd.check_runs(tmp_path / "out")
    assert entry["incomplete_runs"] == ["lit-llama"] and entry["ready"] is False
    done = len(sdk.calls)

    # stopped by a provider error: the rows read so far are written, then the error is raised
    def broken(prompt: str) -> str:
        if len(sdk2.calls) > 1:
            raise RuntimeError("the provider fell over")
        return LITERAL_OK

    sdk2 = FakeSDK(broken, model=LLAMA)
    use_sdk(monkeypatch, sdk2)
    with pytest.raises(RuntimeError, match="fell over"):
        rd.main(args)
    manifest = json.loads((run / "run_manifest.json").read_text())
    assert manifest["status"].startswith("error: RuntimeError") and not manifest["complete"]
    assert manifest["readings"] == done + 1
    last = json.loads((run / "invocations.jsonl").read_text().splitlines()[-1])
    assert last["status"].startswith("error: RuntimeError")
    # resumed under the same name: only the missing items are called
    sdk3 = FakeSDK(lambda prompt: LITERAL_OK, model=LLAMA)
    use_sdk(monkeypatch, sdk3)
    capsys.readouterr()
    assert rd.main(args) == 0
    assert len(sdk3.calls) == 4 - (done + 1)
    manifest = json.loads((run / "run_manifest.json").read_text())
    assert manifest["complete"] is True and manifest["by_status"] == {"ok": 4}
    assert rd.held_by_run(tmp_path / "out")["lit-llama"]["open"] is False


def test_cli_track_record_run_records_the_file_hash(
    tmp_path, monkeypatch, capsys, live_ready
) -> None:
    sdk = FakeSDK(lambda prompt: PREDICTIVE_OK, model=LLAMA)
    use_sdk(monkeypatch, sdk)
    track_path = write_track(tmp_path)
    digest = rd._sha256_file(track_path)
    path = write_items(tmp_path, [make_item(item_id="d1", date_of_update="2021-05-04")])
    track_args = ["--template", "predictive-track-v1", "--track-record", str(track_path)]
    args = live_args(tmp_path, path, "dev-b-llama", *track_args)
    assert rd.main(args) == 0
    run = tmp_path / "out" / "dev-b-llama"
    manifest = json.loads((run / "run_manifest.json").read_text())
    assert manifest["track_record_sha256"] == digest and manifest["track_record_split"] == "fit"
    [row] = [json.loads(line) for line in (run / "readings.jsonl").read_text().splitlines()]
    assert row["track_record_sha256"] == digest
    assert row["condition"] == f"predictive-track-v1|det-v1|mask=0|shift=0|track={digest[:16]}"
    assert (
        "| a month and year | first | 412 | cell | 31% | 62% | 140 |"
        in (sdk.calls[0]["messages"][0]["content"])
    )
    # another track-record file under the same run name is another condition: refused
    (tmp_path / "t2").mkdir()
    other = ["--template", "predictive-track-v1", "--track-record"]
    other.append(str(write_track(tmp_path / "t2", min_cell=50)))
    with pytest.raises(SystemExit, match=r"other settings.*track_record_sha256"):
        rd.main(live_args(tmp_path, path, "dev-b-llama", *other))
    # an item that is one of the examples is refused before any call
    clash = write_items(tmp_path / "t2", [make_item(item_id="S0001", date_of_update="2021-05-04")])
    with pytest.raises(SystemExit, match="examples of the track record"):
        rd.main(live_args(tmp_path, clash, "dev-b-llama-2", *track_args))
    with pytest.raises(SystemExit, match="needs --track-record"):
        rd.main(live_args(tmp_path, path, "dev-b-llama-3", "--template", "predictive-track-v1"))


def test_cli_refuses_a_track_record_that_covers_its_items(
    tmp_path, monkeypatch, capsys, live_ready
) -> None:
    monkeypatch.setattr(rd, "RouteCheckedClient", _no_live_client)
    for name in ("w", "d", "t"):
        (tmp_path / name).mkdir()
    fit = write_track(tmp_path)  # the fit split, to 2020-12-31
    whole = write_track(tmp_path / "w", split="fit+dev", through="2022-12-31")
    dev = write_items(tmp_path / "d", [make_item(item_id="d1", date_of_update="2021-05-04")])
    test = write_items(tmp_path / "t", [make_item(item_id="t1", date_of_update="2024-05-04")])

    def args(items: Path, track: Path, *more: str) -> list[str]:
        shown = ["--template", "predictive-track-v1", "--track-record", str(track)]
        return live_args(tmp_path, items, "b-llama", *shown, *more)

    # a dev item with the table of the whole train period: dev outcomes would be in its prompt
    with pytest.raises(SystemExit, match=r"1 items are dated on or before .*\(2022-12-31\).*d1"):
        rd.main(args(dev, whole))
    # a test item with the fit table: not the registered condition
    with pytest.raises(
        SystemExit, match=r"read with the fit\+dev track record, not with the 'fit'"
    ):
        rd.main(args(test, fit, "--allow-test-items"))
    assert not (tmp_path / "out").exists()  # refused before the ledger and the roots file
    # a dry run is not refused; it counts the items the record does not precede
    assert rd.main([*args(dev, whole), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["items_not_after_track_record"] == 1
    # the registered pairs go through, as far as the client
    for items, track, more in ((dev, fit, ()), (test, whole, ("--allow-test-items",))):
        with pytest.raises(AssertionError, match="a live client was constructed"):
            rd.main(args(items, track, *more))
    assert rd.track_refusals(rd.load_track_record(whole), rd.load_items(test)) == []
    both = rd.track_refusals(rd.load_track_record(fit), [make_item(), *rd.load_items(test)])
    assert len(both) == 2
