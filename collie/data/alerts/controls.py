"""Content contrasts share one call opportunity; channel/history ablations are separate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from collie.contracts import AlertMessage, assert_no_hidden_state

VARIANTS = ("true", "masked", "shuffled", "wrong", "neutral")


@dataclass(frozen=True, slots=True)
class ContentVariantSet:
    timestamp: int
    trigger_trace_hash: str
    texts: tuple[tuple[str, str], ...]

    def __post_init__(self):
        # Value objects use immutable fields; once the structure is validated, the shared experimental condition stays stable across later comparisons.
        if type(self.timestamp) is not int or self.timestamp < 1:
            raise ValueError("invalid shared timestamp")
        if not isinstance(self.trigger_trace_hash, str) or len(self.trigger_trace_hash) != 64:
            raise ValueError("expected a SHA256 trigger-trace hash")
        try:
            int(self.trigger_trace_hash, 16)
        except ValueError as exc:
            raise ValueError("expected a SHA256 trigger-trace hash") from exc
        if not isinstance(self.texts, tuple) or any(
            not isinstance(row, tuple)
            or len(row) != 2
            or any(not isinstance(v, str) or not v for v in row)
            for row in self.texts
        ):
            raise ValueError("variant texts must be immutable nonempty string pairs")
        if len(self.texts) != len(VARIANTS) or {k for k, _ in self.texts} != set(VARIANTS):
            raise ValueError("expected exactly five content variants")

    def message(self, variant):
        # Every variant builds its message from the set's single timestamp; no per-text call time is kept.
        return AlertMessage("operational-alert", self.timestamp, dict(self.texts)[variant])

    @classmethod
    def from_messages(cls, messages, trace_hashes):
        # Re-check timestamps and trigger traces when assembling from external messages, so a call-timing change is not mistaken for a semantic gain.
        if set(messages) != set(VARIANTS) or set(trace_hashes) != set(VARIANTS):
            raise ValueError("expected exactly five content variants")
        times = {m.period for m in messages.values()}
        hashes = set(trace_hashes.values())
        if len(times) != 1 or len(hashes) != 1:
            raise ValueError("cross-timestamp or cross-trigger-trace contrast forbidden")
        return cls(times.pop(), hashes.pop(), tuple((k, messages[k].text) for k in VARIANTS))


def content_contrast(variants, left="true", right="neutral"):
    # Accept only one complete set; callers must not freely mix messages from different times or trigger traces.
    if not isinstance(variants, ContentVariantSet):
        raise TypeError("content contrast requires one ContentVariantSet")
    return variants.message(left), variants.message(right)


def render_content_controls(
    message, *, trigger_trace, wrong_text, true_family, wrong_family, seed, length_tolerance=0
):
    # true is the reference and the other four variants change only the text; wrong's family information is supplied by the analysis-side caller.
    if true_family == wrong_family or not wrong_text.strip() or wrong_text == message.text:
        raise ValueError("wrong text must come from a different family")
    if type(length_tolerance) is not int or length_tolerance < 0:
        raise ValueError("invalid registered length tolerance")
    assert_no_hidden_state(trigger_trace, context="content-control trigger trace")
    trace_hash = hashlib.sha256(
        json.dumps(trigger_trace, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    words = message.text.split()
    order = sorted(
        range(len(words)),
        key=lambda i: hashlib.sha256(f"{seed}:{i}:{message.text}".encode()).digest(),
    )
    if order == list(range(len(words))) and len(words) > 1:
        order = order[1:] + order[:1]
    # Equal character count is an explicit provisional registration, not token matching.
    masked = "".join(" " if c.isspace() else "x" for c in message.text)
    filler = "Routine operations update. Please continue the usual administrative checks. "
    neutral = (filler * (len(message.text) // len(filler) + 1))[: len(message.text)]
    texts = (
        ("true", message.text),
        ("masked", masked),
        ("shuffled", " ".join(words[i] for i in order)),
        ("wrong", wrong_text),
        ("neutral", neutral),
    )
    for key, text in texts:
        if key in ("masked", "neutral") and abs(len(text) - len(message.text)) > length_tolerance:
            raise ValueError("length tolerance exceeded")
    return ContentVariantSet(message.period, trace_hash, texts)


@dataclass(frozen=True, slots=True)
class PromptChannels:
    """Observable prompt inputs only; neither ablation alters the simulator or trigger."""

    alert: AlertMessage | None
    numeric_history: tuple[str, ...]

    def __post_init__(self):
        # Value objects use immutable fields; once the structure is validated, the shared experimental condition stays stable across later comparisons.
        if not isinstance(self.numeric_history, tuple) or any(
            not isinstance(row, str) for row in self.numeric_history
        ):
            raise ValueError("numeric history must be an immutable tuple of prompt rows")
        if self.alert is not None and not isinstance(self.alert, AlertMessage):
            raise ValueError("alert must be an observable AlertMessage")
        assert_no_hidden_state(self)


def numeric_history_removed(channels: PromptChannels):
    # Remove only the numeric history from the prompt and keep the alert; simulator state and telemetry triggers are untouched.
    return PromptChannels(channels.alert, ())


def no_alert(channels: PromptChannels):
    # Remove the entire alert channel and keep the numeric history; this is a channel ablation, not a content contrast at fixed alert timing.
    return PromptChannels(None, channels.numeric_history)
