"""The oracle ShockSpec headroom bound (arm_id ``oracle_shockspec_headroom``).

This arm is the headroom ceiling of the arm ladder: at the incident's true onset period it
maps the *hidden truth* onto a proposal payload, compiles it through the same injected
:class:`~collie.arms.protocols.SpecCompiler` and controller factory as every other
compile-once arm (``collie/arms/controls.py``'s :class:`~collie.arms.controls.CompilerSwitchArm`),
and orders from the compiled controller for exactly the ground-truth hazard window — onset
through ``onset_period + duration - 1`` — with the baseline dispatching outside it (the window
is load-bearing: a hazard config held past a short-lived shock manufactures a holding-cost
blowup, module 04's checkpoint finding). The band between arm 1's score and
this arm's score is the entire value any alert channel, detector, parser, or verifier could
ever add on a shocked episode — the quantity the ladder's contrasts are read against.

**This arm reads hidden truth, and that is its whole definition.** The
:class:`~collie.contracts.HiddenIncident` enters through the constructor, injected by the
harness — the only place hidden state may enter — never through the observation stream. The
runner must therefore execute it with ``check_controller_isolation=False`` (the runner's own
docstring names this arm as the exception), and two disciplines bind its use:

* it may never be tuned on test data — the mapping below is fixed by the registered family
  semantics, and the one provisional choice (the magnitude binning) is marked as such; and
* it is an analysis instrument, not a candidate policy — nothing deployable may inherit from
  it.

No LLM is called; like the controls, call-ledger conservation is vacuous here.
"""

from __future__ import annotations

from dataclasses import dataclass

from collie.arms.controls import CompilerSwitchArm
from collie.arms.protocols import ProposalPayload
from collie.contracts import (
    Direction,
    DurationBin,
    HiddenIncident,
    MagnitudeBin,
    PeriodObservation,
    Persistence,
    ShockFamily,
    TargetStream,
)

__all__ = [
    "ORACLE_ARM_ID",
    "OracleShockSpecArm",
    "incident_to_payload",
]

ORACLE_ARM_ID = "oracle_shockspec_headroom"


def _duration_bin(duration: int) -> DurationBin:
    """Bin an incident duration: 1-3 short, 4-8 medium, longer otherwise.

    The cut points are the ``DurationBin`` vocabulary's own values (``"1_3"`` / ``"4_8"``),
    applied to truth. Callers guarantee ``duration >= 1``.
    """
    if duration <= 3:
        return DurationBin.SHORT
    if duration <= 8:
        return DurationBin.MEDIUM
    return DurationBin.LONGER


def _magnitude_bin(magnitude: float) -> MagnitudeBin:
    """Bin a demand multiplier by ``|magnitude - 1|``: under 0.3 low, under 0.6 medium, else high.

    **Provisional binning — module 02 owns the real one.** The registered dev magnitudes
    (1.25/1.5 up, 0.6/0.75 down; ``collie/data/families/demand.py``) sit at 0.25-0.5 from 1,
    so the cut points separate the registered set without having been fit to anything.
    Supply-family incidents carry ``magnitude == 1.0`` by the fixture convention
    (``collie/data/families/supply.py``) and therefore bin LOW; the bin is only meaningful for
    demand families, and the compiler does not read it either way.
    """
    delta = abs(magnitude - 1.0)
    if delta < 0.3:
        return MagnitudeBin.LOW
    if delta < 0.6:
        return MagnitudeBin.MEDIUM
    return MagnitudeBin.HIGH


def incident_to_payload(incident: HiddenIncident) -> ProposalPayload:
    """Map ground truth onto the payload a perfect shock-typer would emit at onset.

    Family determines ``(target_stream, direction)``: the demand families carry their
    multiplier's sign; a lead-time shift is a delay; a shipment loss or transit pause is an
    interruption. Persistence is TRANSIENT for a temporary pulse and PERSISTENT otherwise (the
    demand-level and permanent supply families run to the horizon). Compound maps to the
    registered joint ``(both, mixed)`` compiler shape; this does not multiply marginal evidence
    because the oracle bypasses verification and only supplies the hidden-truth compiler upper
    bound. The onset window is ``(0, 0)`` — the oracle knows the onset is *now*, which is exactly
    the headroom being measured. ``no_change`` is not an incident.
    """
    family = incident.family
    if family in (ShockFamily.DEMAND_LEVEL, ShockFamily.TEMPORARY_PULSE):
        stream = TargetStream.DEMAND
        if incident.magnitude > 1.0:
            direction = Direction.DEMAND_UP
        elif incident.magnitude < 1.0:
            direction = Direction.DEMAND_DOWN
        else:
            raise ValueError(
                f"a {family} incident with magnitude 1.0 is a non-shock and has no direction"
            )
    elif family is ShockFamily.LEAD_TIME_SHIFT:
        stream, direction = TargetStream.ARRIVAL, Direction.ARRIVAL_DELAYED
    elif family in (ShockFamily.SHIPMENT_LOSS, ShockFamily.TRANSIT_PAUSE):
        stream, direction = TargetStream.ARRIVAL, Direction.ARRIVAL_INTERRUPTED
    elif family is ShockFamily.COMPOUND:
        stream, direction = TargetStream.BOTH, Direction.MIXED
    else:
        raise ValueError(f"the oracle does not map family {family!r}: no_change is not an incident")
    persistence = (
        Persistence.TRANSIENT
        if family in (ShockFamily.TEMPORARY_PULSE, ShockFamily.COMPOUND)
        else Persistence.PERSISTENT
    )
    return ProposalPayload(
        target_stream=stream,
        shock_family=family,
        direction=direction,
        onset_window=(0, 0),
        magnitude_bin=_magnitude_bin(incident.magnitude),
        persistence=persistence,
        duration_bin=_duration_bin(incident.duration),
        evidence_refs=(),
        prospective_signature=f"sig_oracle_{family.value}",  # clearly labelled, never registry
    )


@dataclass(slots=True, kw_only=True)
class OracleShockSpecArm(CompilerSwitchArm):
    """The oracle headroom bound — **this arm reads hidden truth** (see the module docstring).

    Constructed with the episode's :class:`~collie.contracts.HiddenIncident`; at
    ``obs.period == incident.onset_period`` the truth is mapped onto a payload
    (:func:`incident_to_payload`) and compiled, and the compiled controller orders for exactly
    the ground-truth hazard window — onset through ``onset_period + duration - 1`` — with the
    baseline dispatching outside it. The window is not optional: holding a hazard config past
    a short-lived shock manufactures a holding-cost blowup that measures a missing lifecycle,
    not the hypothesis (module 04's checkpoint demo caught a negative aggregate gap from this,
    and the merged ladder shows temporary_pulse at -542 per episode un-windowed). Real
    ShockSpec arms earn the same deactivation from module 05's verifier lifecycle; the oracle
    is simply privileged to read it. Construction validates the incident eagerly — an
    unmappable family, a unit magnitude on a demand family, or a non-positive onset or
    duration fails before any episode runs rather than mid-episode.
    """

    incident: HiddenIncident
    arm_id: str = ORACLE_ARM_ID

    def __post_init__(self) -> None:
        # Explicit base call: under @dataclass(slots=True) the zero-argument super() binds to
        # the pre-slots class object and raises TypeError.
        CompilerSwitchArm.__post_init__(self)
        if self.incident.onset_period < 1:
            raise ValueError(f"onset_period must be >= 1, got {self.incident.onset_period}")
        if self.incident.duration < 1:
            raise ValueError(f"duration must be >= 1, got {self.incident.duration}")
        incident_to_payload(self.incident)  # fail fast on unmappable truth

    @property
    def _active_through(self) -> int:
        """Last period (inclusive) the ground-truth hazard is live."""
        return self.incident.onset_period + self.incident.duration - 1

    def _dispatch_active(self, obs: PeriodObservation) -> bool:
        return obs.period <= self._active_through

    def _switch_payload(self, obs: PeriodObservation) -> ProposalPayload | None:
        if obs.period < self.incident.onset_period:
            return None
        return incident_to_payload(self.incident)
