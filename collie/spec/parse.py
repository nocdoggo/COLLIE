"""Extract, validate, repair once, or cleanly fall back for ShockSpec output."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from collie.contracts import (
    AlertMessage,
    CallLog,
    LLMClient,
    ParseOutcome,
    PeriodObservation,
    ShockSpec,
)
from collie.spec.prompt import PromptBundle, build_prompt, build_repair_prompt
from collie.spec.schema import (
    ShockSpecPayload,
    inject_provenance,
    validate_payload,
    validate_proposal_context,
)

__all__ = [
    "ParseResult",
    "extract_json_payload",
    "parse_shockspec",
    "validate_extracted_payload",
]


_FENCE = re.compile(r"(?is)```(?:json)?\s*(.*?)\s*```")


@dataclass(frozen=True, slots=True)
class ParseResult:
    """The accepted immutable spec or a counted clean fallback."""

    outcome: ParseOutcome
    spec: ShockSpec | None
    calls: tuple[CallLog, ...]
    errors: tuple[str, ...] = ()


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _strict_object(text: str) -> dict[str, Any]:
    value = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


def _first_balanced_object(text: str) -> str | None:
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, character in enumerate(text):
        if start is None:
            if character == "{":
                start = index
                depth = 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json_payload(raw_output: str) -> dict[str, Any]:
    """Extract one object by strict, fenced, then balanced-object parsing."""
    if not isinstance(raw_output, str):
        raise ValueError("model output must be text")
    stripped = raw_output.strip()
    if not stripped:
        raise ValueError("model output is empty")

    try:
        return _strict_object(stripped)
    except json.JSONDecodeError:
        pass

    for match in _FENCE.finditer(stripped):
        candidate = match.group(1).strip()
        try:
            return _strict_object(candidate)
        except json.JSONDecodeError:
            continue

    candidate = _first_balanced_object(stripped)
    if candidate is None:
        raise ValueError("no balanced JSON object found")
    try:
        return _strict_object(candidate)
    except json.JSONDecodeError as error:
        raise ValueError(f"balanced object is not valid JSON: {error.msg}") from error


def validate_extracted_payload(
    raw_output: str, *, permitted_evidence_ids: Sequence[str]
) -> ShockSpecPayload:
    """Extract and validate a model payload against its exact prompt evidence."""
    data = extract_json_payload(raw_output)
    payload = validate_payload(data)
    permitted = frozenset(permitted_evidence_ids)
    unknown = frozenset(payload.evidence_refs) - permitted
    if unknown:
        raise ValueError(f"evidence_refs not present in prompt: {sorted(unknown)}")
    return payload


def _call_log(
    *,
    call_id: str,
    arm_id: str,
    episode_id: str,
    period: int,
    model_id: str,
    prompt: PromptBundle,
    decoding_hash: str,
    attempt_index: int,
    outcome: ParseOutcome | None,
    latency_ms: float,
) -> CallLog:
    return CallLog(
        call_id=call_id,
        arm_id=arm_id,
        episode_id=episode_id,
        period=period,
        model_id=model_id,
        prompt_hash=prompt.prompt_hash,
        decoding_hash=decoding_hash,
        attempt_index=attempt_index,
        outcome=outcome,
        latency_ms=latency_ms,
    )


def parse_shockspec(
    client: LLMClient,
    prompt: PromptBundle,
    *,
    episode_id: str,
    arm_id: str,
    proposal_index: int,
    generation_period: int | None = None,
    decoding_hash: str = "det-v1",
) -> ParseResult:
    """Make at most two calls and return a valid spec or a clean fallback."""
    generated_at = prompt.tau_j if generation_period is None else generation_period
    validate_proposal_context(
        tau_j=prompt.tau_j, generation_period=generated_at, proposal_index=proposal_index
    )

    calls: list[CallLog] = []
    errors: list[str] = []
    attempts = (prompt, build_repair_prompt(prompt))

    for attempt_index, attempt_prompt in enumerate(attempts, start=1):
        started = time.perf_counter()
        try:
            try:
                raw_output = client.complete(attempt_prompt.text, decoding_hash=decoding_hash)
            except Exception as error:
                # LLMClient does not restrict providers' exception hierarchies.
                # Normalize only transport exceptions; process cancellation still propagates.
                raise RuntimeError(f"transport {type(error).__name__}: {error}") from error
            payload = validate_extracted_payload(
                raw_output, permitted_evidence_ids=prompt.evidence_ids
            )
            outcome = (
                ParseOutcome.ACCEPTED if attempt_index == 1 else ParseOutcome.ACCEPTED_AFTER_REPAIR
            )
            spec = inject_provenance(
                payload,
                tau_j=prompt.tau_j,
                generation_period=generated_at,
                proposal_index=proposal_index,
                model_id=client.model_id,
                decoding_hash=decoding_hash,
                prompt_hash=attempt_prompt.prompt_hash,
            )
        except (ValueError, TypeError, RuntimeError, OSError) as error:
            latency_ms = (time.perf_counter() - started) * 1000
            errors.append(f"attempt {attempt_index}: {type(error).__name__}: {error}")
            final_outcome = ParseOutcome.FALLBACK if attempt_index == 2 else None
            calls.append(
                _call_log(
                    call_id=(
                        f"{episode_id}:{arm_id}:p{prompt.tau_j}:j{proposal_index}:a{attempt_index}"
                    ),
                    arm_id=arm_id,
                    episode_id=episode_id,
                    period=prompt.tau_j,
                    model_id=client.model_id,
                    prompt=attempt_prompt,
                    decoding_hash=decoding_hash,
                    attempt_index=attempt_index,
                    outcome=final_outcome,
                    latency_ms=latency_ms,
                )
            )
            if attempt_index == 2:
                return ParseResult(
                    outcome=ParseOutcome.FALLBACK,
                    spec=None,
                    calls=tuple(calls),
                    errors=tuple(errors),
                )
            continue

        latency_ms = (time.perf_counter() - started) * 1000
        calls.append(
            _call_log(
                call_id=(
                    f"{episode_id}:{arm_id}:p{prompt.tau_j}:j{proposal_index}:a{attempt_index}"
                ),
                arm_id=arm_id,
                episode_id=episode_id,
                period=prompt.tau_j,
                model_id=client.model_id,
                prompt=attempt_prompt,
                decoding_hash=decoding_hash,
                attempt_index=attempt_index,
                outcome=outcome,
                latency_ms=latency_ms,
            )
        )
        return ParseResult(
            outcome=outcome,
            spec=spec,
            calls=tuple(calls),
            errors=tuple(errors),
        )

    raise AssertionError("the two-attempt parse loop must always return")


def _demo_prompt() -> PromptBundle:
    observation = PeriodObservation(
        period=17,
        date="2026-01-17",
        on_hand=80.0,
        in_transit_total=35.0,
        prev_order=20.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=112.0,
        alert=AlertMessage(
            alert_id="source-alert",
            period=17,
            text="Transfer-hub processing may be interrupted for several periods.",
        ),
    )
    return build_prompt([observation], tau_j=17, product_context="seasonal apparel")


def _demo_corpus() -> Mapping[str, tuple[str, ...]]:
    # Fakes stay behind the demo boundary; importing the production parser does
    # not couple a real transport to test support code.
    from collie.fakes.fake_llm import canned

    valid = json.loads(canned.VALID)
    return {
        "valid": (canned.VALID,),
        "prose_wrapper": (canned.PROSE_WRAPPED,),
        "json_fence": (canned.FENCED,),
        "abstention": (canned.ABSTENTION,),
        "abstention_none_spelling": (canned.ABSTENTION_NONE_SPELLING,),
        "two_objects": (f'{canned.VALID}\n{{"ignored":true}}',),
        "nested_code_block": (f"```text\n```json\n{canned.VALID}\n```\n```",),
        "truncated": (canned.TRUNCATED, canned.VALID),
        "empty": (canned.EMPTY, canned.VALID),
        "extra_field": (canned.EXTRA_FIELD, canned.VALID),
        "smuggled_threshold": (canned.SMUGGLED_THRESHOLD, canned.VALID),
        "smuggled_falsifier": (canned.SMUGGLED_FALSIFIER, canned.VALID),
        "wrong_type": (canned.WRONG_TYPE, canned.VALID),
        "unknown_enum": (canned.UNKNOWN_ENUM, canned.VALID),
        "incoherent_abstention": (canned.INCOHERENT_ABSTENTION, canned.VALID),
        "phantom_evidence": (canned.PHANTOM_EVIDENCE, canned.VALID),
        "unregistered_window": (
            json.dumps({**valid, "onset_window": [-3, 3]}),
            canned.VALID,
        ),
        "illegal_pair": (
            json.dumps({**valid, "prospective_signature": "sig_demand_level_up"}),
            canned.VALID,
        ),
        "numeric_string_enum": (
            json.dumps({**valid, "magnitude_bin": "2"}),
            canned.VALID,
        ),
        "unicode_quotes": (canned.VALID.replace('"', "”"), canned.VALID),
        "trailing_comma": (canned.VALID[:-1] + ",}", canned.VALID),
        "null_enum": (
            json.dumps({**valid, "persistence": None}),
            canned.VALID,
        ),
        "fallback_after_two_failures": (
            canned.MALFORMED_JSON,
            canned.EXTRA_FIELD,
        ),
    }


def _run_demo() -> int:
    from collie.fakes.fake_llm import FakeLLM

    prompt = _demo_prompt()
    print("case\toutcome\tattempted\trepaired\trejected")
    for name, responses in _demo_corpus().items():
        client = FakeLLM(responses=list(responses))
        result = parse_shockspec(
            client,
            prompt,
            episode_id=f"demo-{name}",
            arm_id="demo",
            proposal_index=1,
        )
        rejected = sum(call.outcome in (None, ParseOutcome.FALLBACK) for call in result.calls)
        print(
            f"{name}\t{result.outcome.value}\t{len(result.calls)}\t"
            f"{int(len(result.calls) == 2)}\t{rejected}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-corpus", action="store_true")
    args = parser.parse_args(argv)
    if args.demo_corpus:
        return _run_demo()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
