"""The oracle arm's config selection.

This is a factory, not a controller subclass. Once :func:`oracle_config_for` has read the hidden
incident and produced a :class:`~collie.contracts.ControlConfig`, everything downstream is the
identical :class:`~collie.control.controller.OrCompilerController` every other arm wraps — the
shared control path (``tests/test_controller.py::test_shared_control_path_byte_identical``) is
what makes an oracle-vs-ShockSpec profit comparison a comparison of *hypotheses*, not of
controllers.

The oracle is one of the two permitted readers of :class:`~collie.contracts.HiddenIncident`
outside the evaluator (``collie/contracts.py``'s own docstring), and it is never tuned on test
(``docs/implementation/README.md``, standing rule 1). This module exists at Checkpoint 2 only to
demonstrate the compiler's headroom before module 06 builds the full arm ladder; the proposal
budget and triggering a real oracle arm needs are out of scope here.

**Activation window.** A real ShockSpec arm earns activation from module 05's verifier, which has
not landed yet. The oracle does not need to earn it — it is privileged to read
``incident.onset_period`` and ``incident.duration`` directly, so it activates its compiled config
for exactly that window and runs the baseline config outside it. This is not a stand-in for the
verifier's lifecycle: it is knowledge only the oracle is allowed to have. Applying the compiled
config for an entire episode regardless of whether the hazard is still live was tried first and
produces a large *negative* headroom on families with a short-lived hazard (``shipment_loss``,
``transit_pause``) — a low ``gamma`` held on well past the hazard window makes the controller
distrust perfectly real, arriving inventory for the rest of the episode, which manufactures a
holding-cost blowup that has nothing to do with the hypothesis being wrong. That failure mode is
a property of running a static config with no lifecycle, not of the compiler, which is exactly
why the real arms need module 05's activation gate rather than a config applied forever.
"""

from __future__ import annotations

from dataclasses import dataclass

from collie.contracts import (
    ControlConfig,
    Decision,
    HiddenIncident,
    PeriodObservation,
    ShockFamily,
    ShockSpec,
)
from collie.control.controller import OrCompilerController
from collie.control.grid import BASELINE_CONFIG
from collie.control.mapping import compile_spec

__all__ = ["ORACLE_ARM_ID", "OracleController", "oracle_config_for", "oracle_controller_for"]

ORACLE_ARM_ID = "oracle_shockspec"


def oracle_config_for(incident: HiddenIncident) -> ControlConfig:
    """Translate ground truth into the exact typed hypothesis a perfectly informed model would
    commit to, then compile it through the identical path every ShockSpec arm uses.

    A null incident (or one somehow missing its alert spec) gets the baseline, exactly like a
    ``no_change`` proposal would.
    """
    if incident.family is ShockFamily.NO_CHANGE or incident.alert_spec is None:
        return BASELINE_CONFIG
    alert = incident.alert_spec
    spec = ShockSpec(
        target_stream=alert.target_stream,
        shock_family=alert.family,
        direction=alert.direction,
        onset_window=alert.onset_window,
        magnitude_bin=alert.magnitude_bin,
        persistence=alert.persistence,
        duration_bin=alert.duration_bin,
        evidence_refs=(),
        prospective_signature=alert.prospective_signature,
        tau_j=incident.onset_period,
        proposal_index=1,
        model_id="oracle",
        decoding_hash="oracle",
        prompt_hash="oracle",
    )
    return compile_spec(spec)


@dataclass(slots=True)
class OracleController:
    """Wraps the shared :class:`OrCompilerController`, swapping its ``.config`` between the
    ground-truth config and the baseline as the episode crosses the hazard window.

    Composition, not subclassing: the order rule itself (``inner``) never learns *why* its
    config changed, only what it is right now, exactly as ``OrCompilerController``'s own
    docstring anticipates for a lifecycle-gated arm.
    """

    inner: OrCompilerController
    active_config: ControlConfig
    onset_period: int
    active_through: int
    """Last period (inclusive) the hazard is live. ``onset_period - 1`` if it never activates."""
    arm_id: str = ORACLE_ARM_ID

    def reset(self) -> None:
        self.inner.reset()

    def order(self, obs: PeriodObservation) -> Decision:
        active = self.onset_period <= obs.period <= self.active_through
        self.inner.config = self.active_config if active else BASELINE_CONFIG
        decision = self.inner.order(obs)
        return Decision(
            period=decision.period,
            order_quantity=decision.order_quantity,
            arm_id=self.arm_id,
            control_config=decision.control_config,
            lifecycle_state=None,
            triggered=active,
        )


def oracle_controller_for(
    incident: HiddenIncident, *, order_cap: float, train_demand: tuple[float, ...] = ()
) -> OracleController:
    """The oracle arm: the shared controller, pre-loaded with the ground-truth config and gated
    to the ground-truth activation window (see the module docstring for why the gate matters)."""
    inner = OrCompilerController(
        order_cap=order_cap, config=BASELINE_CONFIG, train_demand=train_demand
    )
    if incident.family is ShockFamily.NO_CHANGE:
        return OracleController(
            inner=inner, active_config=BASELINE_CONFIG, onset_period=1, active_through=0
        )
    return OracleController(
        inner=inner,
        active_config=oracle_config_for(incident),
        onset_period=incident.onset_period,
        active_through=incident.onset_period + max(incident.duration, 1) - 1,
    )
