"""Real Module 02 -> 06 -> 04 integration, with only transport scripted."""

import hashlib
import json
from dataclasses import asdict, replace

import pytest

from collie.arms.protocols import RepairingSpecPrompter, SpecParser, SpecPrompter
from collie.arms.shockspec import (
    ARM8_ARM_ID,
    ARM9_ARM_ID,
    ARM10_ARM_ID,
    EProcessActivation,
    HeuristicRollbackActivation,
    ImmediateActivation,
)
from collie.contracts import ParseOutcome, ShockFamily, ShockSpec
from collie.control.mapping import GridCompiler, compile_spec
from collie.fakes import canned
from collie.fakes.fake_verifier import FakeVerifier
from collie.sim.runner import EpisodeRunner
from collie.spec.adapters import ShockSpecParser, ShockSpecPrompter
from collie.spec.prompt import REPAIR_SUFFIX
from collie.spec.registry import FAMILY_TARGET_STREAM, expected_direction, legal_pairs
from collie.spec.schema import validate_payload
from tests.test_arms_direct import _recording_harness, _ScriptedTrigger
from tests.test_arms_shockspec import _arm
from tests.test_episode_runner import make_instance
from tests.test_prompt_legality import _observation


def _valid():
    return json.dumps({**json.loads(canned.VALID), "evidence_refs": ["obs_t2"]})


def test_adapters_satisfy_runtime_protocols():
    prompter = ShockSpecPrompter()
    assert isinstance(prompter, SpecPrompter)
    assert isinstance(prompter, RepairingSpecPrompter)
    assert isinstance(ShockSpecParser(prompter), SpecParser)


def test_parser_requires_prompt_and_rejects_untrusted_fields():
    prompter = ShockSpecPrompter()
    parser = ShockSpecParser(prompter)
    with pytest.raises(RuntimeError, match="render a proposal"):
        parser.parse(_valid())
    prompter.prompt(_observation(2, demand=5))
    payload = parser.parse(_valid())
    assert asdict(payload) == validate_payload(json.loads(_valid())).model_dump()
    for key in ("tau_j", "proposal_index", "model_id", "decoding_hash", "prompt_hash", "threshold"):
        assert parser.parse(json.dumps({**json.loads(_valid()), key: "untrusted"})) is None
    assert parser.parse(canned.PHANTOM_EVIDENCE) is None
    assert parser.parse("BAD") is None
    assert parser.parse(canned.ABSTENTION).shock_family is ShockFamily.NO_CHANGE


def test_prompter_history_idempotence_future_filter_and_reset():
    p = ShockSpecPrompter()
    first = _observation(1, demand=4)
    p.observe(first)
    p.observe(first)
    with pytest.raises(ValueError, match="conflicting observations"):
        p.observe(replace(first, prev_demand=99))
    p.observe(_observation(3, demand=999))
    text = p.prompt(_observation(2, demand=5))
    assert p.bundle.evidence_ids == ("obs_t1", "obs_t2")
    assert "999" not in text
    assert p.repair_prompt() == text + "\n\n" + REPAIR_SUFFIX
    p.reset()
    with pytest.raises(RuntimeError):
        p.repair_prompt()
    p.prompt(first)
    assert p.bundle.evidence_ids == ("obs_t1",)


def _real_arm(metered, instance, arm_id=ARM8_ARM_ID, trigger=None):
    arm = _arm(
        metered,
        instance,
        ImmediateActivation(),
        arm_id=arm_id,
        trigger=trigger or _ScriptedTrigger({2}),
    )
    if arm_id == ARM9_ARM_ID:
        arm.activation = HeuristicRollbackActivation()
    elif arm_id == ARM10_ARM_ID:
        arm.activation = EProcessActivation(FakeVerifier())
    arm.prompter = ShockSpecPrompter()
    arm.parser = ShockSpecParser(arm.prompter)
    return arm


@pytest.mark.parametrize(
    "responses,outcomes",
    [
        ([_valid()], [ParseOutcome.ACCEPTED]),
        (["BAD", _valid()], [ParseOutcome.FALLBACK, ParseOutcome.ACCEPTED_AFTER_REPAIR]),
        (["BAD", "BAD"], [ParseOutcome.FALLBACK, ParseOutcome.FALLBACK]),
        ([canned.ABSTENTION], [ParseOutcome.ACCEPTED]),
    ],
)
def test_real_arm_calls_repair_and_ledger(tmp_path, responses, outcomes):
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0, 0.0, 0.0))
    transport, ledger, metered = _recording_harness(tmp_path, "BAD", responses)
    arm = _real_arm(metered, instance)
    result = EpisodeRunner(instance).run(arm)
    entries = ledger.charged_entries()
    assert [e.outcome for e in entries] == outcomes
    assert [e.attempt_index for e in entries] == list(range(1, len(outcomes) + 1))
    assert transport.n_calls == len(entries) == len(outcomes)
    ledger.assert_conserved()
    assert "[obs_t1]" in transport.seen[0][0]  # non-trigger period is retained
    if len(outcomes) == 2:
        assert transport.seen[1][0] == transport.seen[0][0] + "\n\n" + REPAIR_SUFFIX
    if responses[-1] == _valid():
        spec = arm._specs[-1]
        assert spec.tau_j == 2 and spec.proposal_index == 1
        assert spec.model_id == metered.endpoint.model_id
        assert spec.prompt_hash == hashlib.sha256(transport.seen[-1][0].encode()).hexdigest()
        assert result.decisions[1].control_config == GridCompiler().compile(
            spec, current=arm.baseline_config
        )
    else:
        assert arm._specs == []
        assert all(d.active_spec_id is None and d.control_config is None for d in result.decisions)


def test_fallback_is_identical_to_no_proposal(tmp_path):
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0, 0.0, 0.0))
    _, ledger, metered = _recording_harness(tmp_path, "BAD")
    fallback = EpisodeRunner(instance).run(_real_arm(metered, instance))
    baseline = EpisodeRunner(instance).run(
        _real_arm(metered, instance, arm_id="no-proposal", trigger=_ScriptedTrigger(set()))
    )
    assert [d.order_quantity for d in fallback.decisions] == [
        d.order_quantity for d in baseline.decisions
    ]
    assert len(ledger.charged_entries()) == 2
    ledger.assert_conserved()


def test_real_prompts_share_physical_repair_calls_across_arms(tmp_path):
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    transport, ledger, metered = _recording_harness(tmp_path, "BAD", ["BAD", _valid()])
    for arm_id in (ARM8_ARM_ID, ARM9_ARM_ID, ARM10_ARM_ID):
        EpisodeRunner(instance).run(_real_arm(metered, instance, arm_id=arm_id))
    assert transport.n_calls == 2
    assert len(ledger.charged_entries()) == 6
    ledger.assert_conserved()


def test_arm_reset_clears_real_prompt_context(tmp_path):
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _recording_harness(tmp_path, "BAD")
    arm = _real_arm(metered, instance)
    EpisodeRunner(instance).run(arm)
    arm.reset()
    with pytest.raises(RuntimeError):
        arm.parser.parse(_valid())
    arm.prompter.prompt(_observation(1, demand=5))
    assert arm.prompter.bundle.evidence_ids == ("obs_t1",)


@pytest.mark.parametrize("family,signature", legal_pairs())
def test_real_compiler_consumes_module02_registry(family, signature):
    data = json.loads(canned.ABSTENTION if family is ShockFamily.NO_CHANGE else canned.VALID)
    data.update(
        shock_family=family,
        prospective_signature=signature,
        target_stream=FAMILY_TARGET_STREAM[family],
        direction=expected_direction(family, signature),
    )
    payload = validate_payload(data)
    spec = ShockSpec(
        **payload.model_dump(),
        tau_j=2,
        proposal_index=1,
        model_id="test",
        prompt_hash="test",
        decoding_hash="det-v1",
    )
    assert compile_spec(spec) is not None
    from collie.control.grid import baseline_config_for

    current = baseline_config_for(2)
    composed = GridCompiler().compile(spec, current=current)
    if spec.is_abstention:
        assert composed == current
    else:
        assert composed.predictive_model == compile_spec(spec).predictive_model
