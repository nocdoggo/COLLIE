"""analysis/real_content_pilot — the exploratory real-content runner, tested offline only.

No test here reaches a provider: live endpoints are stubbed or refused. Two of the slow tests are
the runner's pre-flight checks: with the scripted transport and the frozen demo alerts it must
reproduce the registered pilot records bit for bit (so its wiring *is* ``run_ladder``'s), and with
module 03's bank alerts it must survive every legal proposal shape a real model can return. The
third sweeps every module-02-legal shape through module 05's register path (Rule U's premise).
"""

from __future__ import annotations

import gzip
import json
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from analysis.real_content_pilot import alerts as alerts_mod
from analysis.real_content_pilot.alerts import (
    NULL_FALSE_ALERT_PERIOD,
    pilot_bank_alerts,
)
from analysis.real_content_pilot.runner import (
    ARMS,
    CANONICAL_ABSTENTION,
    RefusedSplitError,
    assert_dev_cal,
    main,
    records_gz_bytes,
    rule_u_reason,
    run_pilot,
)
from analysis.real_content_pilot.transport import (
    CallCapReached,
    GuardedTransport,
    SpendCapReached,
    classify_error,
)
from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import ARM10_ARM_ID
from collie.contracts import (
    DurationBin,
    InformationCondition,
    LifecycleState,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    Split,
    assert_no_hidden_state,
)
from collie.eval.records import episode_result_to_dict
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import (
    DECODING_REGISTRY,
    EndpointConfig,
    OpenAICompatClient,
    RawResponse,
    gemini_primary,
)
from collie.llm.demo import scripted_endpoint
from collie.spec.parse import validate_extracted_payload
from collie.spec.registry import FAMILY_TARGET_STREAM, expected_direction, legal_pairs
from collie.verify import VerifierActivationPolicy
from collie.verify.registry import REGISTERED_ONSET_WINDOWS
from tools.run_arms import _DemoTransport, pilot_instances

REPO = Path(__file__).resolve().parents[1]
STORED_RECORDS = REPO / "reports" / "pilot_records.jsonl"
DET = DECODING_REGISTRY["det-v1"]


@pytest.fixture(scope="module")
def pilot(tmp_path_factory):
    instances, _truths = pilot_instances(tmp_path_factory.mktemp("pilot"), 120)
    return [instance for instance, _seed in instances]


# ---------------------------------------------------------------------------
# the bank alert channel
# ---------------------------------------------------------------------------


def test_bank_alerts_follow_module_03s_schedule(pilot) -> None:
    alerts = pilot_bank_alerts(pilot)
    assert set(alerts) == {instance.spec.episode_id for instance in pilot}
    kinds_seen = set()
    for instance in pilot:
        episode = alerts[instance.spec.episode_id]
        condition = instance.spec.information_condition
        for message in episode.alerts.values():
            assert_no_hidden_state(message)
            assert message.alert_id == "operational-alert"
        for template_id in episode.template_ids.values():
            assert template_id.startswith(f"tpl_{instance.spec.split.value}_")
        if instance.incident is None:
            if condition is InformationCondition.NO_ALERT:
                assert episode.alerts == {} and episode.source == "none:silent_null"
            else:
                assert list(episode.alerts) == [NULL_FALSE_ALERT_PERIOD]
                assert episode.source == "bank:false_alert_null"
                assert episode.template_kind == "accurate"
                assert "_demand_level_" in episode.template_ids[NULL_FALSE_ALERT_PERIOD]
            continue
        family = int(instance.spec.episode_id.split("/")[1][1:])
        if family == 2:
            assert episode.alerts == {} and episode.source == "none:bank_gap_demand_down"
            continue
        onset = instance.incident.onset_period
        expected = {
            InformationCondition.NO_ALERT: None,
            InformationCondition.EARLY_ACCURATE: onset - 1,
            InformationCondition.LATE_ACCURATE: onset + 2,
            InformationCondition.UNRELIABLE: onset - 1,
        }[condition]
        if expected is None:
            assert episode.alerts == {} and episode.template_kind is None
            continue
        assert list(episode.alerts) == [expected]
        if condition is InformationCondition.UNRELIABLE:
            assert episode.template_kind in {"overstated", "ambiguous", "distractor"}
            kinds_seen.add(episode.template_kind)
        else:
            assert episode.template_kind == "accurate"
    assert kinds_seen == {"overstated", "ambiguous", "distractor"}


def test_early_and_late_alerts_of_a_unit_share_text_and_selection_is_deterministic(
    pilot,
) -> None:
    first = pilot_bank_alerts(pilot)
    second = pilot_bank_alerts(pilot)
    assert {k: v.to_row() for k, v in first.items()} == {k: v.to_row() for k, v in second.items()}
    by_unit: dict[str, dict] = {}
    for instance in pilot:
        if instance.incident is None:
            continue
        unit = instance.spec.episode_id.rsplit("/", 1)[0]
        by_unit.setdefault(unit, {})[instance.spec.information_condition] = first[
            instance.spec.episode_id
        ]
    for unit, conditions in by_unit.items():
        early = conditions[InformationCondition.EARLY_ACCURATE].to_row()
        late = conditions[InformationCondition.LATE_ACCURATE].to_row()
        assert early["text"] == late["text"], unit


def test_the_test_template_file_is_never_opened(pilot, monkeypatch) -> None:
    opened: list[str] = []
    real = alerts_mod.load_template_file

    def spy(path):
        opened.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(alerts_mod, "load_template_file", spy)
    pilot_bank_alerts(pilot)
    assert opened == ["dev.yaml", "cal.yaml"]


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def test_runner_refuses_the_test_split() -> None:
    fake = SimpleNamespace(spec=SimpleNamespace(split=Split.TEST, episode_id="test/f1/s1/no_alert"))
    with pytest.raises(RefusedSplitError):
        assert_dev_cal([(fake, 1)])


def test_live_endpoints_need_explicit_opt_in(monkeypatch, tmp_path) -> None:
    def never(self):  # the key must not even be resolved without --allow-live
        raise AssertionError("resolve_key called")

    monkeypatch.setattr(EndpointConfig, "resolve_key", never)
    for endpoint in ("gemini", "grok"):
        with pytest.raises(SystemExit, match="--allow-live"):
            main(
                [
                    "--endpoint",
                    endpoint,
                    "--run-name",
                    "x",
                    "--out-root",
                    str(tmp_path / "out"),
                    "--local-root",
                    str(tmp_path / "local"),
                ]
            )


def test_scripted_smoke_writes_outputs_and_logs_the_invocation(tmp_path) -> None:
    code = main(
        [
            "--endpoint",
            "scripted",
            "--run-name",
            "smoke",
            "--episodes",
            "dev/f1/s1050000/early_accurate",
            "dev/f4/s4050000/unreliable",
            "--out-root",
            str(tmp_path / "out"),
            "--local-root",
            str(tmp_path / "local"),
        ]
    )
    assert code == 0
    out = tmp_path / "out" / "smoke"
    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["analysis_class"] == "exploratory" and manifest["partial"] is True
    assert manifest["episodes"] == 2 and manifest["alert_source"] == "bank"
    rows = [
        json.loads(line)
        for line in gzip.decompress((out / "records.jsonl.gz").read_bytes()).splitlines()
    ]
    assert {row["analysis_class"] for row in rows} == {"exploratory"}
    assert {row["arm_id"] for row in rows} == set(ARMS)
    invocation = json.loads((out / "invocations.jsonl").read_text().splitlines()[-1])
    assert invocation["status"] == "complete"
    proposals = [json.loads(line) for line in (out / "proposals.jsonl").read_text().splitlines()]
    assert proposals and all(p["arm_id"].startswith("arm") for p in proposals)
    assert (tmp_path / "local" / "smoke" / "responses.jsonl").is_file()


# ---------------------------------------------------------------------------
# the live-transport guard
# ---------------------------------------------------------------------------


class _Scripted:
    """An inner transport that replays a script of responses and exceptions."""

    model_id = "fake-model"

    def __init__(self, script) -> None:
        self.script = list(script)
        self.calls = 0

    def complete_metered(self, prompt, *, decoding, system=None):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _status(cls, code: int, headers: dict | None = None):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(code, request=request, headers=headers or {})
    return cls(f"status {code}", response=response, body=None)


def _guard(tmp_path, script, **kwargs):
    sleeps: list[float] = []
    defaults = {"spend_cap_usd": 5.0, "max_physical_calls": 100}
    defaults.update(kwargs)
    guard = GuardedTransport(
        inner=_Scripted(script),
        endpoint=gemini_primary(),
        spend_log=tmp_path / "spend_log.jsonl",
        sleep=sleeps.append,
        **defaults,
    )
    return guard, sleeps


def _log(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "spend_log.jsonl").read_text().splitlines()]


def test_guard_retries_transient_errors_with_backoff(tmp_path) -> None:
    ok = RawResponse(text="{}", prompt_tokens=10, completion_tokens=5, total_tokens=20)
    guard, sleeps = _guard(
        tmp_path,
        [
            _status(openai.RateLimitError, 429, {"retry-after": "2"}),
            _status(openai.InternalServerError, 503),
            ok,
        ],
    )
    assert guard.complete_metered("p", decoding=DET) == ok
    assert sleeps == [2.0, 10.0]
    events = [row["event"] for row in _log(tmp_path)]
    assert events == ["retry", "retry", "call"]
    assert _log(tmp_path)[-1]["attempts"] == 3 and guard.retries == 2


def test_guard_turns_a_403_into_a_logged_empty_refusal(tmp_path) -> None:
    guard, _ = _guard(tmp_path, [_status(openai.PermissionDeniedError, 403)])
    raw = guard.complete_metered("p", decoding=DET)
    assert raw == RawResponse(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)
    log = _log(tmp_path)
    assert [row["event"] for row in log] == ["refusal", "call"]
    assert log[-1]["status"] == "refused" and log[-1]["usd"] == 0.0 and guard.refusals == 1


def test_guard_raises_fatal_errors_at_once(tmp_path) -> None:
    guard, sleeps = _guard(tmp_path, [_status(openai.BadRequestError, 400)])
    with pytest.raises(openai.BadRequestError):
        guard.complete_metered("p", decoding=DET)
    assert sleeps == [] and [row["event"] for row in _log(tmp_path)] == ["error"]


def test_guard_gives_up_after_max_attempts(tmp_path) -> None:
    request = httpx.Request("POST", "https://example.invalid")
    script = [openai.APITimeoutError(request=request) for _ in range(3)]
    guard, sleeps = _guard(tmp_path, script, max_attempts=3)
    with pytest.raises(openai.APITimeoutError):
        guard.complete_metered("p", decoding=DET)
    assert sleeps == [5.0, 10.0]


def test_guard_enforces_the_spend_cap_across_invocations(tmp_path) -> None:
    million = RawResponse(
        text="x", prompt_tokens=1_000_000, completion_tokens=0, total_tokens=1_000_000
    )
    guard, _ = _guard(tmp_path, [million, million, million], spend_cap_usd=1.0)
    guard.complete_metered("a", decoding=DET)  # $0.75 at Gemini's input price
    guard.complete_metered("b", decoding=DET)  # $1.50: the call that crosses the cap completes
    with pytest.raises(SpendCapReached):
        guard.complete_metered("c", decoding=DET)
    resumed, _ = _guard(tmp_path, [million], spend_cap_usd=1.0)
    assert resumed.spent_usd == pytest.approx(1.5) and resumed.prior_calls == 2
    with pytest.raises(SpendCapReached):
        resumed.complete_metered("d", decoding=DET)


def test_guard_enforces_the_call_cap(tmp_path) -> None:
    ok = RawResponse(text="{}", prompt_tokens=1, completion_tokens=1, total_tokens=2)
    guard, _ = _guard(tmp_path, [ok, ok], max_physical_calls=1)
    guard.complete_metered("a", decoding=DET)
    with pytest.raises(CallCapReached):
        guard.complete_metered("b", decoding=DET)


def test_error_classification() -> None:
    request = httpx.Request("POST", "https://example.invalid")
    assert classify_error(_status(openai.RateLimitError, 429)) == "transient"
    assert classify_error(_status(openai.InternalServerError, 500)) == "transient"
    assert classify_error(openai.APIConnectionError(request=request)) == "transient"
    assert classify_error(_status(openai.PermissionDeniedError, 403)) == "refusal"
    assert classify_error(_status(openai.AuthenticationError, 401)) == "fatal"
    assert classify_error(_status(openai.NotFoundError, 404)) == "fatal"
    assert classify_error(ValueError("x")) == "fatal"


def test_a_guarded_real_client_passes_the_isolation_walk_quickly(monkeypatch, tmp_path) -> None:
    """The runner walks every non-oracle controller, and arms 8-10 hold the live client."""
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")  # env beats the key file: no file is read
    endpoint = gemini_primary()
    guard = GuardedTransport(
        inner=OpenAICompatClient(endpoint, timeout=5.0, max_retries=0),
        endpoint=endpoint,
        spend_log=tmp_path / "spend_log.jsonl",
        spend_cap_usd=1.0,
        max_physical_calls=1,
    )
    metered = MeteredClient(
        transport=guard, endpoint=endpoint, cache=DiskCache(tmp_path / "c"), ledger=CallLedger()
    )
    started = time.perf_counter()
    assert_no_hidden_state(metered.channel(arm_id="arm8_spec_immediate", episode_id="e"))
    assert time.perf_counter() - started < 5.0


def test_records_are_gzipped_byte_stably(tmp_path) -> None:
    run = run_pilot(
        endpoint=scripted_endpoint(),
        transport=_DemoTransport(),
        alert_source="bank",
        cache_dir=tmp_path / "cache",
        episode_ids=["dev/f3/s3050000/late_accurate"],
    )
    assert records_gz_bytes(run.results) == records_gz_bytes(run.results)


# ---------------------------------------------------------------------------
# Rule U: what module 02 accepts but module 05's lifecycle cannot register
# ---------------------------------------------------------------------------


def _shape(family, signature, window, magnitude, persistence, duration) -> ProposalPayload:
    return ProposalPayload(
        target_stream=FAMILY_TARGET_STREAM[family],
        shock_family=family,
        direction=expected_direction(family, signature),
        onset_window=window,
        magnitude_bin=magnitude,
        persistence=persistence,
        duration_bin=duration,
        evidence_refs=(),
        prospective_signature=signature,
    )


def _shock_shapes():
    for family, signature in legal_pairs():
        if family is ShockFamily.NO_CHANGE:
            continue
        for window in REGISTERED_ONSET_WINDOWS:
            for magnitude in (MagnitudeBin.LOW, MagnitudeBin.MEDIUM, MagnitudeBin.HIGH):
                for persistence in Persistence:
                    for duration in DurationBin:
                        yield _shape(family, signature, window, magnitude, persistence, duration)


def test_the_canonical_abstention_is_module_02s_own_no_change() -> None:
    text = json.dumps(
        {
            "target_stream": "none",
            "shock_family": "no_change",
            "direction": "none",
            "onset_window": None,
            "magnitude_bin": "none",  # the spelling ShockSpec normalises for an abstention
            "persistence": "unknown",
            "duration_bin": "none",
            "evidence_refs": [],
            "prospective_signature": "sig_demand_level_up",
        }
    )
    parsed = validate_extracted_payload(text, permitted_evidence_ids=("e1",))
    assert ProposalPayload(**parsed.model_dump()) == CANONICAL_ABSTENTION
    assert CANONICAL_ABSTENTION.shock_family is ShockFamily.NO_CHANGE
    assert rule_u_reason(CANONICAL_ABSTENTION, tau_j=50, horizon=50) is None


def test_rule_u_flags_exactly_the_shapes_the_lifecycle_refuses() -> None:
    flagged = kept = 0
    for payload in _shock_shapes():
        reason = rule_u_reason(payload, tau_j=20, horizon=50)
        none_fields = {
            "persistence_none": payload.persistence is Persistence.NONE,
            "duration_none": payload.duration_bin is DurationBin.NONE,
        }
        assert reason == ("+".join(k for k, v in none_fields.items() if v) or None)
        flagged += reason is not None
        kept += reason is None
        at_horizon = rule_u_reason(payload, tau_j=50, horizon=50)
        assert at_horizon is not None and at_horizon.endswith("tau_at_horizon")
    assert flagged and kept


@pytest.mark.slow
def test_every_shape_rule_u_keeps_registers_and_verifies_in_module_05() -> None:
    """The docstring's claim: nothing else module 02 accepts can abort arm 10's register path."""
    horizon = 50
    demands = [20.0 + (t % 5) for t in range(1, horizon + 1)]
    arrivals = [(20.0, 20.0 if t > 3 else 0.0) for t in range(1, horizon + 1)]
    kept = [p for p in _shock_shapes() if rule_u_reason(p, tau_j=1, horizon=horizon) is None]
    assert len(kept) == 7 * 4 * 3 * 3 * 3  # pairs x windows x magnitudes x persistence x duration
    checked = 0
    for payload in kept:
        for tau_j in (1, 20, horizon - 1):
            policy = VerifierActivationPolicy(episode_horizon=horizon)
            policy.prime(tuple(demands[: tau_j - 1]), tuple(arrivals[: tau_j - 1]))
            spec = ShockSpec(
                **asdict(payload),  # exactly how ShockSpecArm stamps an accepted payload
                tau_j=tau_j,
                proposal_index=1,
                model_id="m",
                decoding_hash="det-v1",
                prompt_hash="h",
            )
            policy.register(spec, baseline=(21.0, 1.4))
            dispatch, receipt = arrivals[tau_j - 1]
            policy.condition(tau_j, demands[tau_j - 1], dispatch=dispatch, receipt=receipt)
            for period in range(tau_j + 1, min(tau_j + 4, horizon + 1)):
                dispatch, receipt = arrivals[period - 1]
                state = policy.observe(
                    period, demands[period - 1], dispatch=dispatch, receipt=receipt
                )
                assert isinstance(state, LifecycleState)
            checked += 1
    assert checked == 3 * len(kept)


# ---------------------------------------------------------------------------
# the two pre-flight checks
# ---------------------------------------------------------------------------


def _comparable(record: dict) -> dict:
    out = {k: v for k, v in record.items() if k != "analysis_class"}
    out["calls"] = [
        {k: v for k, v in call.items() if k not in ("call_id", "latency_ms")}
        for call in record["calls"]
    ]
    return out


@pytest.mark.slow
def test_scripted_demo_run_reproduces_the_registered_pilot_records(tmp_path) -> None:
    run = run_pilot(
        endpoint=scripted_endpoint(),
        transport=_DemoTransport(),
        alert_source="demo",
        cache_dir=tmp_path / "cache",
    )
    stored = {}
    with STORED_RECORDS.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm_id"] in ARMS:
                stored[(row["episode_id"], row["arm_id"])] = row
    assert len(run.results) == len(stored) == 7 * 120 + 2 * 96
    for result in run.results:
        got = episode_result_to_dict(result)
        want = stored[(result.episode_id, result.arm_id)]
        assert got["analysis_class"] == "exploratory"
        assert _comparable(got) == _comparable(want), (result.episode_id, result.arm_id)


_LEGAL = (
    ("demand_level", "demand", "demand_up", "sig_demand_level_up"),
    ("demand_level", "demand", "demand_down", "sig_demand_level_down"),
    ("temporary_pulse", "demand", "demand_up", "sig_demand_pulse"),
    ("lead_time_shift", "arrival", "arrival_delayed", "sig_arrival_delay"),
    ("shipment_loss", "arrival", "arrival_interrupted", "sig_arrival_loss"),
    ("transit_pause", "arrival", "arrival_interrupted", "sig_arrival_stall"),
    ("compound", "both", "mixed", "sig_compound"),
)
_WINDOWS = ([-2, 0], [-1, 1], [0, 2], [-2, 2])
_MAGNITUDES = ("low", "medium", "high")
_PERSISTENCE = ("transient", "persistent", "unknown", "none")
_DURATIONS = ("1_3", "4_8", "longer", "none")


def _variants() -> list[str]:
    out = []
    for index, (family, stream, direction, signature) in enumerate(_LEGAL):
        for k, window in enumerate(_WINDOWS):
            payload = {
                "target_stream": stream,
                "shock_family": family,
                "direction": direction,
                "onset_window": window,
                "magnitude_bin": _MAGNITUDES[(index + k) % 3],
                "persistence": _PERSISTENCE[(index + k) % 4],
                "duration_bin": _DURATIONS[(index + 2 * k) % 4],
                "evidence_refs": [],
                "prospective_signature": signature,
            }
            text = json.dumps(payload)
            out.append(f"```json\n{text}\n```" if k == 3 else text)
    out.append(
        json.dumps(
            {
                "target_stream": "none",
                "shock_family": "no_change",
                "direction": "none",
                "onset_window": None,
                "magnitude_bin": None,
                "persistence": "unknown",
                "duration_bin": "none",
                "evidence_refs": [],
                "prospective_signature": "sig_demand_level_up",
            }
        )
    )
    out.append("I cannot tell from this history.")
    out.append("")
    return out


class _Rotating:
    """Returns every legal proposal shape (and some failures) in turn: a crash pre-flight."""

    model_id = "rotating-fake"

    def __init__(self) -> None:
        self.variants = _variants()
        self.n = 0

    def complete_metered(self, prompt, *, decoding, system=None):
        text = self.variants[self.n % len(self.variants)]
        self.n += 1
        return RawResponse(
            text=text,
            prompt_tokens=len(prompt) // 4 + 1,
            completion_tokens=len(text) // 4 + 1,
            total_tokens=(len(prompt) + len(text)) // 4 + 2,
        )


@pytest.mark.slow
def test_bank_run_survives_every_legal_proposal_shape(tmp_path) -> None:
    transport = _Rotating()
    run = run_pilot(
        endpoint=scripted_endpoint(),
        transport=transport,
        alert_source="bank",
        cache_dir=tmp_path / "cache",
    )
    assert len(run.results) == 7 * 120 + 2 * 96
    assert transport.n > len(transport.variants)  # every variant was served at least once
    parsed = [p for p in run.proposals if p["parsed"]]
    families = {p["payload"]["shock_family"] for p in parsed}
    assert families >= {row[0] for row in _LEGAL} | {"no_change"}
    assert any(not p["parsed"] for p in run.proposals)
    # Rule U fired, on arm 10 only, and only where module 05 cannot register the proposal.
    coerced = [p for p in run.proposals if p["arm10_coerced_abstention"]]
    assert coerced and {p["arm_id"] for p in coerced} == {ARM10_ARM_ID}
    for p in parsed:
        payload = p["payload"]
        unregistrable = payload["shock_family"] != "no_change" and (
            "none" in (payload["persistence"], payload["duration_bin"]) or p["period"] >= 50
        )
        assert p["arm10_coerced_abstention"] == (unregistrable and p["arm_id"] == ARM10_ARM_ID)
    # Every row carries the model-free digest of the prompt it answered (rebuilt and checked
    # against the cache key inside RecordingParser, repairs included).
    assert all(len(p["prompt_sha256"]) == 64 for p in run.proposals)
    assert any(p["attempt_index"] == 2 for p in run.proposals)
    # Arms 8 and 9 answered the same shared calls with the model's payload, uncoerced.
    by_call = {}
    for p in parsed:
        key = (p["episode_id"], p["period"], p["attempt_index"], p["prompt_key"])
        by_call.setdefault(key, []).append(p)
    shared = [rows for rows in by_call.values() if len(rows) > 1]
    assert any(any(r["arm10_coerced_abstention"] for r in rows) for rows in shared)
    for rows in shared:
        assert len({json.dumps(r["payload"], sort_keys=True) for r in rows}) == 1
