"""Draft follow-up prompt identities and their strict response schemas.

These bytes are candidates, not an activated registration. In particular, the
neutral block has not been verified with both primary tokenizers.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Mapping

from .records import iso_date


COMMON = """Read the supply notice below as a statement, using only the displayed text and update date.
Report the calendar interval expressed by its current forward-looking recovery or next-supply
estimate. Preserve the distinction between what the notice says and what may actually happen.
Do not substitute a publication, expiry, administrative review or explicitly superseded date.
If the notice gives no readable calendar interval for that estimate, return a null interval.

{condition_block}

Update date: {update_date}
Notice: {notice_text}

Return only JSON with these keys:
{"statement_type":"recovery|next_delivery|other|none",
 "interval":{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"},
 "certainty":"asserted|estimated|undetermined|no_statement",
 "quote":"the exact supporting words"}
Use null in place of the interval object when no interval is provided.
An expressed estimate is estimated, an unqualified assertion is asserted, and an explicitly
unknown estimate is undetermined. Use no_statement only when no target statement is made.
"""

EXPLICIT = """Apply these calendar conventions for this task.
An ordinary named month covers its first through last day.
Early or beginning of a month means days 1 through 10. Mid or middle means days 11 through 20.
Late or end of a month means day 21 through its last day.
Week of an exact date means that date and the next six days. The first, second, third, fourth
and fifth week of a named month mean days 1 through 7, 8 through 14, 15 through 21, 22 through
28, and 29 through the last day. The last week of a named month means its final seven days.
The week of a part of a month, without an exact date, means that part. This week means the ISO
Monday-through-Sunday week containing the update date. The end of this week is that Sunday.
A named month without a year takes its first occurrence that is not wholly before the update
date. Parts of that month take the same year. A single month with an explicit year keeps it,
even when it ends before the update.
For numbered relative times measured from the update date, a week is seven days and a month
is thirty days. A single number without within, up to, or over the next gives one exact date.
For within, up to, or over the next, use the interval from the update date to the later date.
A numbered range gives its two bounds. These conventions specify the requested interval.
They do not state a probability that the estimate will hold."""

NEUTRAL = """This notice is one entry in a collection of short notices. Entries can differ in length,
punctuation, capitalisation, abbreviations and layout. Some entries use complete sentences,
while others use compact fragments or several clauses. These differences are ordinary
properties of the collection. The surrounding collection may contain entries from different
organisations and from different publication periods. Entries are displayed separately in
this task, and each display has its own text and identifying fields. The collection format
does not imply that an entry follows a standard sentence pattern. The text may include
ordinary formatting choices made by its publisher. This paragraph describes the presentation
of the collection and does not add information about the events described by an entry.
This is a general task note for every entry. It is the same for each case. It is not a source
about any firm or any product. It has no facts about any one entry. Some lines may be brief.
Some may be long. Some use a colon or a dash. Some use a line break. A blank field is part of
the display. The source may use a short form for a term. It may use a full form instead.
The task is the same when the layout changes. This note is not an added part of the notice.
It says nothing about the event. It is not evidence for an answer. Each entry stands on its
own. There is no required shared style across entries. No two entries need to look alike. Text may vary."""

ROLE = """Read only the notice below. Identify the exact date of the CURRENT RECOVERY estimate.
Current recovery means the presently stated date for supply recovery. Publication dates,
administrative review dates and explicitly superseded estimates are different roles.
Do not predict the actual recovery or substitute a date based on outside knowledge.

Update date: {update_date}
Notice: {notice_text}

Return only JSON:
{"date":"YYYY-MM-DD","quote":"the exact clause stating the current recovery estimate"}
If no exact current recovery date is stated, use null for date and an empty string for quote.
"""

NATURAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "statement_type": {"type": "string", "enum": ["recovery", "next_delivery", "other", "none"]},
        "interval": {"anyOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": False,
             "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
             "required": ["start", "end"]},
        ]},
        "certainty": {"type": "string", "enum": ["asserted", "estimated", "undetermined", "no_statement"]},
        "quote": {"type": "string"},
    },
    "required": ["statement_type", "interval", "certainty", "quote"],
}
ROLE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                   "quote": {"type": "string"}},
    "required": ["date", "quote"],
}

ARM_BLOCKS = {
    "january-natural-v1": "",
    "january-convention-absent-v1": "",
    "january-convention-neutral-v1": NEUTRAL,
    "january-convention-explicit-v1": EXPLICIT,
}
ROLE_ID = "january-role-v1"


def template_bytes(template_id: str) -> bytes:
    if template_id == ROLE_ID:
        return ROLE.encode("utf-8")
    if template_id not in ARM_BLOCKS:
        raise ValueError("unknown follow-up template")
    return COMMON.replace("{condition_block}", ARM_BLOCKS[template_id]).encode("utf-8")


def template_sha256(template_id: str) -> str:
    return hashlib.sha256(template_bytes(template_id)).hexdigest()


def schema_for(template_id: str) -> dict:
    if template_id == ROLE_ID:
        return deepcopy(ROLE_SCHEMA)
    if template_id in ARM_BLOCKS:
        return deepcopy(NATURAL_SCHEMA)
    raise ValueError("unknown follow-up template")


def schema_sha256(template_id: str) -> str:
    encoded = json.dumps(schema_for(template_id), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def render(template_id: str, model_input: Mapping[str, str]) -> str:
    if not isinstance(model_input, Mapping) or set(model_input) != {"update_date", "notice_text"}:
        raise ValueError("model input must contain only update_date and notice_text")
    iso_date(model_input["update_date"])
    if not isinstance(model_input["notice_text"], str):
        raise TypeError("notice text must be a string")
    template = template_bytes(template_id).decode("utf-8")
    # Replace the fixed placeholders before inserting notice text, so text cannot
    # introduce or consume a template placeholder.
    template = template.replace("{update_date}", model_input["update_date"])
    return template.replace("{notice_text}", model_input["notice_text"])


@dataclass(frozen=True, slots=True)
class TokenMatch:
    model_id: str
    neutral_tokens: int
    explicit_tokens: int
    relative_difference: float
    within_five_percent: bool


def neutral_token_matches(counters: Mapping[str, Callable[[str], int]]) -> tuple[TokenMatch, ...]:
    """Measure block length with both supplied model-specific tokenizers.

    The callers must verify tokenizer identities separately. This mechanical
    check cannot establish the neutral paragraph's lack of date guidance.
    """
    models = {"meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat"}
    if not isinstance(counters, Mapping) or set(counters) != models:
        raise ValueError("both primary tokenizers are required")
    results = []
    for model in sorted(models):
        count = counters[model]
        neutral, explicit = count(NEUTRAL), count(EXPLICIT)
        if type(neutral) is not int or type(explicit) is not int or neutral < 0 or explicit <= 0:
            raise ValueError("tokenizers must return nonnegative integer counts")
        relative = abs(neutral - explicit) / explicit
        results.append(TokenMatch(model, neutral, explicit, relative, relative <= .05))
    return tuple(results)
