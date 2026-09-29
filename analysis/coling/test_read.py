"""Tests for :mod:`analysis.coling.read`, with a fake transport only: no call leaves the machine.

Usage (from the repository root)::

    python -m pytest analysis/coling/test_read.py -q
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import openai
import pytest

import analysis.coling.read as rd
from collie.llm import DiskCache
from collie.llm.client import DecodingConfig, RawResponse

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
        type_of_update="Reverified",
        availability_information="Product on backorder",
        related_information="Expected recovery April 2020. Teva is working with FDA.",
        reason_for_shortage="Demand increase for the drug",
        stated_end="2020-04-30",
        form="a month and year",
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


# --- templates and rendering ------------------------------------------------------------------


def test_templates_are_pinned_and_the_pin_moves_with_the_text() -> None:
    rd.check_frozen()
    t = rd.TEMPLATES["literal-v1"]
    assert replace(t, text=t.text + " ").sha256 != t.sha256
    assert len({t.sha256 for t in rd.TEMPLATES.values()}) == len(rd.TEMPLATES)


@pytest.mark.parametrize("template_id", sorted(rd.TEMPLATES))
def test_every_template_renders_fully(template_id: str) -> None:
    text = rd.render_prompt(rd.TEMPLATES[template_id], make_item(), rd.CANARY_TRACK)
    assert "$" not in text
    assert "2020-03-17" in text
    assert "Reply with one JSON object and nothing else" in text


def test_literal_prompt_shows_the_entry_and_conventions_only_in_v1() -> None:
    text = rd.render_prompt(rd.TEMPLATES["literal-v1"], make_item(related_information=""))
    assert '- Availability information: "Product on backorder"' in text
    assert "- Related information: (blank)" in text
    assert "Conventions:" in text
    free = rd.render_prompt(rd.TEMPLATES["literal-free-v1"], make_item())
    assert "Conventions:" not in free and "own judgement" in free


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
    assert "| a month and year | 120 | 31% | 62% | 140 |" in text
    assert "| TBD or unknown | 80 | n/a | n/a | n/a |" in text
    assert "This entry's form: a month and year" in text
    assert "recovered between 2021-06-10 and 2021-06-18, 98 to 106 days after the update." in text
    assert "not recovered within 365 days" in text
    with pytest.raises(ValueError, match="needs a track record"):
        rd.render_prompt(rd.TEMPLATES["predictive-track-v1"], make_item())


def test_probe_shows_no_notice_text() -> None:
    text = rd.render_prompt(rd.TEMPLATES["probe-v1"], make_item())
    assert "Expected recovery" not in text and "backorder" not in text
    assert "Horizon A is 2020-04-30 and horizon B is 2020-07-29." in text


def test_track_record_refuses_the_test_period() -> None:
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


def test_load_track_record_rejects_unknown_columns(tmp_path: Path) -> None:
    data = {"through": "2022-12-31", "slip_table": [], "examples": [{"date_of_update": "2021-01-01",
            "outcome": "discontinued", "hold_rate": 0.4}]}  # fmt: skip
    path = tmp_path / "track.json"
    path.write_text(json.dumps(data))
    with pytest.raises(TypeError):
        rd.load_track_record(path)


def test_items_accept_fda_headers_and_periods(tmp_path: Path) -> None:
    rows = [
        {"item_id": "a", "Generic Name": "X", "Date of Update": "03/17/2020", "extra": 1},
        {"item_id": "b", "generic_name": "Y", "date_of_update": "2023-01-01", "mask_terms": "Z"},
    ]
    path = tmp_path / "items.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    items = rd.load_items(path)
    assert items[0].date_of_update == "2020-03-17" and items[0].generic_name == "X"
    assert [i.period for i in items] == ["train", "test"]
    assert items[1].mask_terms == ("Z",)
    csv = tmp_path / "events.csv"
    csv.write_text(
        "event_id,event_date,generic_name,availability_text,related_text,resolved_note\n"
        "e1,2021-05-04,X,Backordered,Next release June 2021,Resolved 2021-07-01\n"
    )
    [event] = rd.load_items(csv)
    assert (event.item_id, event.date_of_update) == ("e1", "2021-05-04")
    assert event.related_information == "Next release June 2021"
    prompt = rd.render_prompt(rd.TEMPLATES["literal-v1"], event)
    assert "Resolved" not in prompt and "2021-07-01" not in prompt


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
    assert rd.shift_item(make_item(), 0) == make_item()


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
    repair_prompt = inner.calls[1][0]
    assert "Your previous reply was:\n<<<\nThe interval is April 2020.\n>>>" in repair_prompt
    assert "no JSON object found" in repair_prompt
    assert [a["attempt"] for a in row["attempts"]] == [0, 1]
    inner = FakeInner(["nope", "still nope"])
    row = make_reader(tmp_path / "b", inner).read(make_item())
    assert row["status"] == "failed" and row["reading"] is None and len(inner.calls) == 2
    assert row["errors"] == ["no JSON object found", "repair: no JSON object found"]


def test_refusal_is_not_repaired(tmp_path: Path) -> None:
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    refusal = openai.PermissionDeniedError(
        "moderated", response=httpx.Response(403, request=request), body=None
    )
    inner = FakeInner([refusal])
    row = make_reader(tmp_path, inner).read(make_item())
    assert row["status"] == "refused" and len(inner.calls) == 1
    events = [r["event"] for r in spend_rows(tmp_path)]
    assert events == ["refusal", "call"]


def test_projected_cap_stops_before_the_call(tmp_path: Path) -> None:
    inner = FakeInner([LITERAL_OK] * 5)
    reader = make_reader(tmp_path, inner, cap=0.0001)
    rows, status = rd.read_items(reader, [make_item()])
    assert rows == [] and inner.calls == [] and status.startswith("aborted: recorded spend")
    # a cap that fits two calls' projection lets exactly the calls it covers through
    one = rd.projected_call_usd(reader.prompt_for(make_item()), "deepseek-v3", "literal",
                                reader.endpoint)  # fmt: skip
    items = [make_item(item_id=f"i{n}") for n in range(5)]
    reader = make_reader(tmp_path / "b", FakeInner([LITERAL_OK] * 5), cap=2.5 * one)
    rows, status = rd.read_items(reader, items)
    assert status.startswith("aborted") and 2 <= len(rows) < 5
    assert reader.transport.spent_usd <= 2.5 * one


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
                availability_information="Anagrelide backordered until April 2021",
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
    assert "Anagrelide" not in sent and "April 2023" in sent and "2021-03-04" not in sent
    assert "entries updated from 2021-10-01 to 2024-12-31" in sent
    rows, _ = rd.read_items(reader, [make_item(item_id="late", date_of_update="2023-02-01")])
    assert "track_record_not_before_item" not in rows[0]["warnings"]
    assert "track_record_not_before_item" in reader.read(make_item())["warnings"]


# --- dry run and the command line -------------------------------------------------------------


def _no_live_client(*args, **kwargs):
    raise AssertionError("a live client was constructed")


def write_items(tmp_path: Path, items) -> Path:
    path = tmp_path / "items.jsonl"
    path.write_text("".join(json.dumps(i.__dict__ | {"mask_terms": []}) + "\n" for i in items))
    return path


def test_dry_run_prices_without_calling(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(rd, "EchoCheckedClient", _no_live_client)
    items = [make_item(item_id="a"), make_item(item_id="b", date_of_update="2024-02-01")]
    path = write_items(tmp_path, items)
    code = rd.main(
        ["--items", str(path), "--template", "predictive-v1", "--model", "gemini-3.8-flash",
         "--model", "llama-3.3-70b", "--dry-run", "--show", "1", "--out-root",
         str(tmp_path / "out")]
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 0 and "===== a (train)" in out
    summary = json.loads(out[out.rindex("\n{\n") + 1 :])
    assert summary["items_by_period"] == {"train": 1, "test": 1}
    gem, llama = summary["models"]["gemini-3.8-flash"], summary["models"]["llama-3.3-70b"]
    assert gem["calls"] == 2 and gem["usd_upper"] > gem["usd_typical"] > llama["usd_typical"] > 0
    assert not (tmp_path / "out").exists()


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
        cache_dirs={"deepseek-v3": tmp_path / "cache"},
    )
    assert summary["models"]["deepseek-v3"]["cached_calls"] == 1


def test_cli_guards(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rd, "EchoCheckedClient", _no_live_client)
    train = write_items(tmp_path, [make_item()])
    base = ["--items", str(train), "--model", "deepseek-v3", "--out-root", str(tmp_path / "o")]
    live = [*base, "--run-name", "r1", "--spend-cap-usd", "1"]
    with pytest.raises(SystemExit, match="--allow-live"):
        rd.main(live)
    with pytest.raises(SystemExit, match="temperature"):
        rd.main([*base, "--dry-run", "--samples", "3"])
    with pytest.raises(SystemExit, match="spend-cap"):
        rd.main([*base, "--run-name", "r1", "--allow-live"])
    (tmp_path / "t").mkdir()
    test = write_items(tmp_path / "t", [make_item(date_of_update="2023-05-01")])
    with pytest.raises(SystemExit, match="registered"):
        rd.main(["--items", str(test), *live[2:], "--allow-live"])
    other = tmp_path / "o" / "earlier-run" / "spend_log.jsonl"
    other.parent.mkdir(parents=True)
    other.write_text(json.dumps({"event": "call", "usd": 199.5}) + "\n")
    with pytest.raises(SystemExit, match="study would pass"):
        rd.main([*live, "--allow-live"])


def test_cli_live_run_end_to_end_with_a_fake(tmp_path: Path, monkeypatch, capsys) -> None:
    inner = FakeInner(lambda prompt: LITERAL_OK)
    monkeypatch.setattr(rd, "EchoCheckedClient", lambda endpoint, served_as, **kw: inner)
    path = write_items(tmp_path, [make_item(item_id="a"), make_item(item_id="b")])
    out_root, local_root = tmp_path / "out", tmp_path / "local"
    args = ["--items", str(path), "--model", "llama-3.3-70b", "--run-name", "lit-llama",
            "--spend-cap-usd", "1", "--allow-live", "--out-root", str(out_root),
            "--local-root", str(local_root)]  # fmt: skip
    assert rd.main(args) == 0
    run = out_root / "lit-llama"
    readings = [json.loads(line) for line in (run / "readings.jsonl").read_text().splitlines()]
    assert [r["item_id"] for r in readings] == ["a", "b"] and len(inner.calls) == 2
    manifest = json.loads((run / "run_manifest.json").read_text())
    assert manifest["by_status"] == {"ok": 2} and manifest["template"] == "literal-v1"
    assert (local_root / "lit-llama" / "responses.jsonl").is_file()
    assert rd.recorded_spend(out_root) == pytest.approx(manifest["guard"]["usd_total"])
    capsys.readouterr()
    assert rd.main(args) == 0 and len(inner.calls) == 2  # the rerun is served from the cache
    invocations = (run / "invocations.jsonl").read_text().splitlines()
    assert len(invocations) == 2 and json.loads(invocations[1])["guard"]["usd_this_invocation"] == 0
    with pytest.raises(SystemExit, match="other settings"):
        rd.main([*args, "--shift-years", "2"])
