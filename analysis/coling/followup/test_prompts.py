"""Prompt and convention checks using only invented notices."""

from datetime import date
from hashlib import sha256

import pytest

from analysis.coling import rules
from analysis.coling.followup.prompts import (
    EXPLICIT, NEUTRAL, ROLE_ID, neutral_token_matches, render, schema_for, schema_sha256,
    template_bytes, template_sha256,
)


def test_natural_and_absent_share_text_but_keep_separate_template_ids():
    natural = "january-natural-v1"
    absent = "january-convention-absent-v1"
    assert natural != absent and template_bytes(natural) == template_bytes(absent)
    assert template_sha256(natural) == template_sha256(absent)
    assert template_sha256("january-convention-neutral-v1") != template_sha256(
        "january-convention-explicit-v1")


def test_render_accepts_only_visible_fields_and_preserves_notice_bytes():
    notice = "Fictional notice containing {update_date} and {notice_text} literally."
    rendered = render("january-natural-v1", {"update_date": "2028-02-29", "notice_text": notice})
    assert notice in rendered and "Update date: 2028-02-29" in rendered
    with pytest.raises(ValueError):
        render("january-natural-v1", {"update_date": "2028-02-29", "notice_text": notice,
                                      "reference": "must not be shown"})
    with pytest.raises(ValueError):
        render("january-natural-v1", {"update_date": "2027-02-29", "notice_text": notice})
    with pytest.raises(ValueError):
        template_bytes("literal-v1")


def test_schema_is_copied_and_has_a_stable_identity():
    one = schema_for(ROLE_ID)
    digest = schema_sha256(ROLE_ID)
    one["properties"]["date"] = {"type": "integer"}
    assert schema_sha256(ROLE_ID) == digest
    assert schema_for(ROLE_ID)["additionalProperties"] is False
    assert schema_for("january-natural-v1")["additionalProperties"] is False


def test_within_relative_is_not_treated_as_a_single_exact_date():
    reading = rules.read("Estimated recovery within 6 weeks", date(2028, 3, 1))
    assert reading.interval == ["2028-03-01", "2028-04-12"]
    assert "without within, up to, or over the next" in EXPLICIT
    assert "For within, up to, or over the next" in EXPLICIT


def test_known_guide_rule_differences_are_not_silently_erased():
    fifth = rules.read("Estimated recovery fifth week of May 2028", date(2028, 3, 1))
    end_week = rules.read("Estimated recovery end of this week", date(2028, 3, 1))
    assert fifth.interval == ["2028-05-01", "2028-05-31"]
    assert end_week.interval == ["2028-02-28", "2028-03-05"]
    assert "29 through the last day" in EXPLICIT
    assert "end of this week is that Sunday" in EXPLICIT


def test_token_matching_requires_both_model_specific_counters():
    llama = "meta-llama/llama-3.3-70b-instruct"
    deepseek = "deepseek/deepseek-chat"
    with pytest.raises(ValueError, match="both"):
        neutral_token_matches({llama: lambda text: 100})
    results = neutral_token_matches({llama: lambda text: 100, deepseek: lambda text: 100})
    assert len(results) == 2 and all(result.within_five_percent for result in results)
    invalid = {llama: lambda text: True, deepseek: lambda text: 100}
    with pytest.raises(ValueError, match="integer"):
        neutral_token_matches(invalid)


def test_provisional_neutral_revision_has_recorded_static_bytes():
    assert NEUTRAL.endswith("No two entries need to look alike. Text may vary.")
    assert sha256(NEUTRAL.encode("utf-8")).hexdigest() == "ec54b2ffa7daba0d498625db0c43f0795411bb6ca41da06c881122fd54a78431"
    assert sha256(EXPLICIT.encode("utf-8")).hexdigest() == "6ce6c50d2440ac6c2cb0d8cfae6a2d3652afd33caa0970c58b98b053366c7dfe"
