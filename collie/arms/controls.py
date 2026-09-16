"""Arm 2 (telemetry-only adaptive OR), the compile-once controls, and the parsing upper bound.

Provenance: the arm-2 design is the registered one in ``docs/module06_research_notes.md`` §3 —
a hand-rolled two-state Gaussian HMM forward filter over demand, its emissions frozen from dev
calibration, feeding a graded (not switched) adjustment of arm 1's capped base-stock rule. The
three controls and the upper bound are the module-06 brief's wave-6 rows (R5.2, R5.5, R5.10):
each replaces exactly one component of the LLM-to-compiler path with a cheaper or omniscient
substitute, routing through the *same* injected compiler and controller factory so any outcome
difference is the substituted component and nothing else.

**No LLM is called anywhere in this module.** No arm here holds a channel and every Decision is
stamped ``llm_called=False``, so call-ledger conservation is vacuous for these arms — zero
calls made, zero charged — and the ledger tests stay with the LLM arms.

Hidden-truth discipline: :class:`AlertSpecUpperBoundArm` is one of the two arms in the project
permitted to carry hidden state (the other is the oracle in ``collie/arms/oracle.py``); the
canonical ``HiddenAlertSpec`` enters through its constructor, injected by the harness, never
through the observation stream. Every other class in this module carries no hidden state, and
``tests/test_controls.py`` proves both halves of that sentence with
:func:`~collie.contracts.find_hidden_state`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace

import numpy as np
from scipy.stats import norm

from collie.arms.history import BenchmarkHistory
from collie.arms.protocols import ProposalPayload, SpecCompiler
from collie.contracts import (
    ControlConfig,
    Controller,
    Decision,
    Direction,
    DurationBin,
    HiddenAlertSpec,
    MagnitudeBin,
    PeriodObservation,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
    Trigger,
)

__all__ = [
    "ALERTSPEC_UB_ARM_ID",
    "ARM2_ARM_ID",
    "ARRIVAL_ALERT_KEYWORDS",
    "DEMAND_DOWN_ALERT_KEYWORDS",
    "DEMAND_UP_ALERT_KEYWORDS",
    "DETECTOR_CONTROL_ARM_ID",
    "DETECTOR_PAYLOAD",
    "EMISSION_HORIZON",
    "HMM_A00",
    "HMM_A11",
    "HMM_MU0",
    "HMM_MU1",
    "HMM_SIGMA0",
    "HMM_SIGMA1",
    "KEYWORD_CONTROL_ARM_ID",
    "KEYWORD_RULES",
    "RECENT_WINDOW",
    "AlertSpecUpperBoundArm",
    "CompilerSwitchArm",
    "DetectorToCompilerArm",
    "KeywordParserArm",
    "TelemetryHMMController",
    "TwoRegimeHMM",
    "alertspec_to_payload",
    "parse_alert_text",
    "telemetry_order",
]

ARM2_ARM_ID = "arm2_telemetry_hmm_or"
DETECTOR_CONTROL_ARM_ID = "ctrl_cusum_to_compiler"
KEYWORD_CONTROL_ARM_ID = "ctrl_keyword_parser"
ALERTSPEC_UB_ARM_ID = "ctrl_alertspec_upper_bound"

# ---------------------------------------------------------------------------
# arm 2 — the registered two-regime HMM (research notes §3)
# ---------------------------------------------------------------------------

HMM_A00 = 0.98
"""Sticky normal-to-normal transition mass. Registered starting point (research notes §3),
an unsourced heuristic flagged as such there — tuned on dev only if at all, then frozen."""

HMM_A11 = 0.90
"""Sticky disrupted-to-disrupted transition mass. Same provenance and same caveat as A00."""

HMM_MU0 = 100.0
"""Normal-regime emission mean: the registered stationary-IID law (collie/data/families/base.py)."""

HMM_SIGMA0 = 25.0
"""Normal-regime emission sd. Same source."""

EMISSION_HORIZON = 50
"""Horizon of the calibration episodes — the official synthetic horizon, matching
``tools/calibrate_triggers.py`` so the two calibrations are computed over the same episodes."""

# Derivation of the frozen disrupted-regime emission (recomputed from the registry and asserted
# equal by tests/test_controls.py::test_frozen_disrupted_emissions_match_the_dev_registry —
# the same frozen-calibration discipline as tools/calibrate_triggers.py --check):
#
#   units  = build_units(Split.DEV), demand-side families 1-3 (collie/data/families/demand.py)
#   per unit: ep = generate_episode(seed=unit.seed, horizon=50, params=unit.params)
#   cells  = ep.demand[ep.incident.onset_period - 1 :]   (literal post-onset demand)
#   pooled : 18 units -> 598 cells
#   HMM_MU1    = mean(cells)          = 102.3076923076923
#   HMM_SIGMA1 = std(cells, ddof=0)   = 36.17657792449045   (the Gaussian MLE)
#
# Per-family contributions (mean/sd/n): f1 128.55/30.93/197, f2 72.94/19.70/195,
# f3 105.01/32.16/206. Pooling both shift directions and family 3's post-pulse reverted cells
# makes the disrupted emission *wider* than any single family's law — that is the intent: the
# regime must explain large deviations in either direction, not track one family. Test data
# never entered the computation.
HMM_MU1 = 102.3076923076923
"""Disrupted-regime emission mean, frozen from the dev registry. Derivation above."""

HMM_SIGMA1 = 36.17657792449045
"""Disrupted-regime emission sd, frozen from the dev registry. Derivation above."""

RECENT_WINDOW = 5
"""Arm 2's disrupted-regime estimator window, in observed demands. Module 06's heuristic,
registered here: five periods is the frozen refractory window
(``collie/trigger/calibration.py``), the episode-scale on which a confirmed disruption
expresses itself, so the window asks "what has demand looked like over one trigger-silence
lately" rather than introducing a second, disconnected constant."""

_CAP_QUANTILE = 0.95
"""The order smoother's quantile — arm 1's published value (``collie/arms/base_stock.py``)."""

_SQRT_2PI = math.sqrt(2.0 * math.pi)


@dataclass(slots=True)
class TwoRegimeHMM:
    """A hand-rolled two-state Gaussian HMM forward filter over demand (research notes §3).

    States ``{0 normal, 1 disrupted}``; sticky transition matrix
    ``A = [[a00, 1-a00], [1-a11, a11]]``; frozen Gaussian emissions. :meth:`update` is one
    Rabiner alpha-pass step — predict through the chain, weight by the emissions, normalise —
    and returns the posterior disrupted probability. Two scalar accumulators stand in for the
    ~30-line numpy alpha pass; the algorithm is identical.

    The filter starts in the normal state with probability one: episodes begin pre-shock by
    construction (onsets are uniform on {14..22}, ``collie/data/families/base.py``), so the
    degenerate-normal initialisation is the honest prior, not a tuning knob.
    """

    a00: float = HMM_A00
    a11: float = HMM_A11
    mu0: float = HMM_MU0
    sigma0: float = HMM_SIGMA0
    mu1: float = HMM_MU1
    sigma1: float = HMM_SIGMA1
    _a0: float = field(default=1.0, init=False, repr=False)
    _a1: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0.0 < self.a00 < 1.0:
            raise ValueError(f"a00 must lie in (0, 1), got {self.a00}")
        if not 0.0 < self.a11 < 1.0:
            raise ValueError(f"a11 must lie in (0, 1), got {self.a11}")
        if self.sigma0 <= 0.0:
            raise ValueError(f"sigma0 must be positive, got {self.sigma0}")
        if self.sigma1 <= 0.0:
            raise ValueError(f"sigma1 must be positive, got {self.sigma1}")

    @property
    def p_disrupted(self) -> float:
        """The current posterior probability of the disrupted regime."""
        return self._a1

    def reset(self) -> None:
        """Back to the degenerate normal-state prior for a fresh episode."""
        self._a0, self._a1 = 1.0, 0.0

    def update(self, x: float) -> float:
        """Filter one demand observation; return the posterior disrupted probability."""
        # Predict: alpha~_j = sum_i alpha_i * A[i, j].
        p0 = self._a0 * self.a00 + self._a1 * (1.0 - self.a11)
        p1 = self._a0 * (1.0 - self.a00) + self._a1 * self.a11
        # Update: alpha_j ∝ alpha~_j * Normal(x; mu_j, sigma_j).
        z0 = (x - self.mu0) / self.sigma0
        z1 = (x - self.mu1) / self.sigma1
        e0 = math.exp(-0.5 * z0 * z0) / (self.sigma0 * _SQRT_2PI)
        e1 = math.exp(-0.5 * z1 * z1) / (self.sigma1 * _SQRT_2PI)
        a0, a1 = p0 * e0, p1 * e1
        total = a0 + a1
        if total <= 0.0:
            # Both emissions underflowed (x sits dozens of sigmas from either regime): the
            # observation is uninformative at float64 resolution, so keep the prediction —
            # still normalised because the chain's rows sum to one — rather than NaN out.
            self._a0, self._a1 = p0, p1
            return p1
        self._a0 = a0 / total
        self._a1 = a1 / total
        return self._a1


def telemetry_order(
    *,
    samples: Sequence[float],
    recent: Sequence[float],
    p_disrupted: float,
    on_hand: float,
    in_transit: float,
    promised_lead_time: float,
    profit_per_unit: float,
    holding_cost_per_unit: float,
    cap_quantile: float = _CAP_QUANTILE,
) -> float:
    """Arm 2's order rule: arm 1's capped base stock evaluated on regime-blended estimates.

    The per-period demand level and sd are the posterior blend of two estimators —
    ``(1-p) * normal + p * disrupted`` — where the normal estimator is the running mean/std
    (``ddof=1``) of ``samples`` (train followed by every observed demand, exactly arm 1's
    sample set) and the disrupted estimator is the same over ``recent`` (the last
    ``RECENT_WINDOW`` observed demands; an empty window falls back to the running statistics,
    which only happens before the first demand is observed, when ``p`` is still 0). The blend
    then flows through arm 1's formula unchanged: ``mu_eff = (1+L) * level``,
    ``sigma_eff = sqrt(1+L) * sd``, ``target = mu_eff + z* * sigma_eff`` with
    ``z* = Phi^-1(profit / (profit + holding))``, order ``min(ceil(target - stock), ceil(cap))``
    floored at 0. The cap stays arm 1's L-independent smoother over the *running* statistics
    (``mean + Phi^-1(0.95) * std``): blending moves the target, not the smoother, so the
    smoothing convention never confounds the adaptation contrast.

    At ``p_disrupted == 0`` this is bit-identical to
    :func:`~collie.arms.base_stock.base_stock_order` — the differential test in
    ``tests/test_controls.py`` pins that, so arm 2 is arm 1 plus a graded term, never a
    reimplementation drift.
    """
    if not samples:
        return 0.0
    mean = float(np.mean(samples))
    std = float(np.std(samples, ddof=1)) if len(samples) > 1 else 0.0
    recent_mean = float(np.mean(recent)) if recent else mean
    recent_std = float(np.std(recent, ddof=1)) if len(recent) > 1 else 0.0

    p = p_disrupted
    level_eff = (1.0 - p) * mean + p * recent_mean
    sd_eff = (1.0 - p) * std + p * recent_std
    mu_eff = (1.0 + promised_lead_time) * level_eff
    sigma_eff = math.sqrt(1.0 + promised_lead_time) * sd_eff

    critical_fractile = profit_per_unit / (profit_per_unit + holding_cost_per_unit)
    z_star = float(norm.ppf(critical_fractile))
    target = mu_eff + z_star * sigma_eff

    uncapped = max(math.ceil(target - (on_hand + in_transit)), 0)
    cap = mean + float(norm.ppf(cap_quantile)) * std
    return float(max(min(uncapped, math.ceil(cap)), 0))


@dataclass(slots=True)
class TelemetryHMMController:
    """Arm 2: telemetry-only adaptive OR. Implements :class:`~collie.contracts.Controller`.

    Record-then-decide, exactly as arm 1: at period ``t`` the previous period's demand is
    appended to the sample set *and* filtered through the HMM before the order is computed.
    Period 1's ``prev_demand`` is the reference's own 0.0 pre-loop initialisation
    (``collie/sim/observation.py``) — it is neither recorded nor filtered, since feeding a
    spurious zero would read as a fabricated downshift.

    UNCENSORED only: like arm 1, the estimator needs true demand, so a missing ``prev_demand``
    raises rather than silently substituting sales.

    Holds no hidden state: the demand history comes from the observation stream and the HMM
    parameters are the frozen module constants.
    """

    train_demand: tuple[float, ...] = ()
    hmm: TwoRegimeHMM = field(default_factory=TwoRegimeHMM)
    recent_window: int = RECENT_WINDOW
    cap_quantile: float = _CAP_QUANTILE
    arm_id: str = ARM2_ARM_ID
    _observed: list[float] = field(default_factory=list, init=False, repr=False)
    _p_disrupted: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.recent_window < 1:
            raise ValueError(f"recent_window must be >= 1, got {self.recent_window}")
        if not 0.0 < self.cap_quantile < 1.0:
            raise ValueError(f"cap_quantile must be in (0, 1), got {self.cap_quantile}")

    def reset(self) -> None:
        self.hmm.reset()
        self._observed = []
        self._p_disrupted = 0.0

    def order(self, obs: PeriodObservation) -> Decision:
        self._record_demand(obs)
        if obs.period > 1:
            assert obs.prev_demand is not None  # _record_demand enforced it
            self._p_disrupted = self.hmm.update(obs.prev_demand)
        quantity = telemetry_order(
            samples=[*self.train_demand, *self._observed],
            recent=self._observed[-self.recent_window :],
            p_disrupted=self._p_disrupted,
            on_hand=obs.on_hand,
            in_transit=obs.in_transit_total,
            promised_lead_time=obs.promised_lead_time,
            profit_per_unit=obs.profit_per_unit,
            holding_cost_per_unit=obs.holding_cost_per_unit,
            cap_quantile=self.cap_quantile,
        )
        return Decision(period=obs.period, order_quantity=quantity, arm_id=self.arm_id)

    def _record_demand(self, obs: PeriodObservation) -> None:
        """Append the previous period's demand — arm 1's record-then-decide discipline."""
        if obs.period == 1:
            # The reference's pre-loop initialisation, not an observation.
            return
        if obs.prev_demand is None:
            raise ValueError(
                f"{self.arm_id!r} is an uncensored-demand policy but observation at period "
                f"{obs.period} carries no prev_demand. Censored operation needs a purpose-built "
                "estimator, not this arm with sales substituted for demand."
            )
        self._observed.append(obs.prev_demand)


# ---------------------------------------------------------------------------
# the compile-once switch base
# ---------------------------------------------------------------------------

_NO_LLM_PROVENANCE = "none"
"""Provenance stamp for the controls' internally built specs: no model, no decoding, no prompt.
The string is honest rather than evocative — the spec object never leaves the arm."""


@dataclass(slots=True, kw_only=True)
class CompilerSwitchArm:
    """Internal base owning the one-shot compile-and-switch mechanics (R5.10).

    Every period the injected baseline controller is fed the observation — its estimator never
    skips, whether or not the switch has happened, so the baseline/compiled contrast is never
    an estimator artifact. Until the subclass's :meth:`_switch_payload` returns a payload, the
    baseline's order is dispatched. The first non-``None`` payload is compiled into one
    :class:`~collie.contracts.ControlConfig` through the injected
    :class:`~collie.arms.protocols.SpecCompiler`, the experimental controller is created once
    through the injected ``controller_factory`` with the demand history observed so far, and
    its order is dispatched from that period on — immediately and permanently. There is no
    lifecycle verification and no rollback: that absence is precisely what these arms are
    controls *against* (the verified arms are ``collie/arms/shockspec.py``).

    The switch seam mirrors ``ShockSpecArm._activate`` exactly: the factory receives demands
    through period ``t-2`` and the experimental controller records ``t-1``'s demand itself when
    its ``order`` is called at the switch period ``t`` — each cell enters its estimator exactly
    once. The seam is shared with the verified arms deliberately; these controls exist to
    isolate *verification*, not to diverge in estimator bookkeeping.

    The pre-switch ``(mean, std)`` of the spec-relevant stream (``_baseline_stats``,
    the same computation ``ShockSpecArm`` hands its activation policy) is computed at the
    switch and kept on ``_baseline_handoff``. A bare ``CompilerSwitchArm`` never switches —
    its condition returns ``None`` — which makes it the never-switch baseline used to prove
    the routing tests are not vacuous.
    """

    compiler: SpecCompiler
    controller_factory: Callable[[ControlConfig, tuple[float, ...]], Controller]
    """Builds the experimental controller at the switch: the compiled config plus the demand
    history observed so far, so its estimator starts continuous rather than empty."""
    baseline: Controller
    baseline_config: ControlConfig
    arm_id: str
    _history: BenchmarkHistory = field(init=False, repr=False)
    _spec: ShockSpec | None = field(default=None, init=False, repr=False)
    _experimental: Controller | None = field(default=None, init=False, repr=False)
    _compiled: ControlConfig | None = field(default=None, init=False, repr=False)
    _switch_period: int | None = field(default=None, init=False, repr=False)
    _baseline_handoff: tuple[float, float] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._history = BenchmarkHistory(arm_id=self.arm_id)

    def reset(self) -> None:
        self._history.reset()
        self._spec = None
        self._experimental = None
        self._compiled = None
        self._switch_period = None
        self._baseline_handoff = None
        self.baseline.reset()

    def order(self, obs: PeriodObservation) -> Decision:
        self._history.observe(obs)
        self._history.record_demand(obs)
        if self._experimental is None:
            payload = self._switch_payload(obs)
            if payload is not None:
                self._switch(obs, payload)

        baseline_decision = self.baseline.order(obs)
        if self._experimental is not None:
            quantity = self._experimental.order(obs).order_quantity
            active_spec_id = f"spec-1@tau{self._switch_period}"
            config = self._compiled
            triggered = obs.period == self._switch_period
        else:
            quantity = baseline_decision.order_quantity
            active_spec_id = None
            config = None
            triggered = False
        self._history.note_dispatch(obs.period, quantity)
        return Decision(
            period=obs.period,
            order_quantity=quantity,
            arm_id=self.arm_id,
            llm_called=False,  # no LLM anywhere in these arms — this is the control
            triggered=triggered,
            active_spec_id=active_spec_id,
            control_config=config,
        )

    # -- internals -----------------------------------------------------------

    def _switch_payload(self, obs: PeriodObservation) -> ProposalPayload | None:
        """The subclass-owned switch condition. The base's answer is "never"."""
        del obs
        return None

    def _switch(self, obs: PeriodObservation, payload: ProposalPayload) -> None:
        """Compile once and create the experimental controller once, with the demand history.

        The factory receives demands through period ``t-2``: the experimental controller
        records ``t-1``'s demand itself when its ``order`` is called at the switch period
        ``t``, so handing it the full history would count that cell twice. Shared verbatim
        with ``ShockSpecArm._activate`` — the seam must not differ between the verified arms
        and their controls.
        """
        spec = ShockSpec(
            **asdict(payload),
            tau_j=obs.period,
            proposal_index=1,  # one spec per episode — the proposal cap's spirit, by construction
            model_id=_NO_LLM_PROVENANCE,
            decoding_hash=_NO_LLM_PROVENANCE,
            prompt_hash=_NO_LLM_PROVENANCE,
        )
        self._compiled = self.compiler.compile(spec, current=self.baseline_config)
        self._experimental = self.controller_factory(self._compiled, self._history.demands[:-1])
        self._spec = spec
        self._switch_period = obs.period
        self._baseline_handoff = self._baseline_stats(spec)

    def _baseline_stats(self, spec: ShockSpec) -> tuple[float, float]:
        """Pre-switch (mean, std) of the spec-relevant stream — ``ShockSpecArm``'s computation."""
        if spec.target_stream is TargetStream.ARRIVAL:
            samples = self._history.arrivals
        else:
            samples = self._history.demands
        if not samples:
            return 0.0, 0.0
        mean = sum(samples) / len(samples)
        variance = (
            sum((s - mean) ** 2 for s in samples) / (len(samples) - 1) if len(samples) > 1 else 0.0
        )
        return mean, math.sqrt(variance)


# ---------------------------------------------------------------------------
# control 1 — detector to compiler (R5.2)
# ---------------------------------------------------------------------------

DEMAND_UP_PAYLOAD = ProposalPayload(
    target_stream=TargetStream.DEMAND,
    shock_family=ShockFamily.DEMAND_LEVEL,
    direction=Direction.DEMAND_UP,
    onset_window=(0, 0),  # provisional: "from now" — module 02 owns the legal windows
    magnitude_bin=MagnitudeBin.MEDIUM,  # provisional: telemetry carries no magnitude
    persistence=Persistence.PERSISTENT,
    duration_bin=DurationBin.LONGER,  # a level shift runs to the horizon
    evidence_refs=(),
    prospective_signature="sig_demand_level_up",  # provisional: module 02 owns the registry
)
"""The fixed "demand up, persistent" payload the detector control and the demand-up keyword
class both compile. One constant, one place to read what either arm claims."""

DETECTOR_PAYLOAD = DEMAND_UP_PAYLOAD
"""The detector control compiles this one fixed payload when its trigger fires (R5.2)."""


@dataclass(slots=True, kw_only=True)
class DetectorToCompilerArm(CompilerSwitchArm):
    """Control: a change detector wired straight into the compiler, no LLM (R5.2).

    The injected ``trigger`` is a Cusum/Page-Hinkley detector wrapped exactly as the LLM arms
    wrap theirs (``RefractoryWrapper`` + ``MaxProposalsWrapper``) — constructed by the caller,
    never inside the arm, so the wiring the test asserts on is the wiring that runs. The first
    permitted firing compiles :data:`DETECTOR_PAYLOAD` and switches. Like
    :class:`~collie.arms.shockspec.ShockSpecArm` the arm does not reset the trigger chain; the
    harness wires a fresh chain per episode.
    """

    trigger: Trigger
    payload: ProposalPayload = DETECTOR_PAYLOAD
    arm_id: str = DETECTOR_CONTROL_ARM_ID

    def _switch_payload(self, obs: PeriodObservation) -> ProposalPayload | None:
        return self.payload if self.trigger.should_propose(obs) else None


# ---------------------------------------------------------------------------
# control 2 — the keyword parser (provisional until module 03)
# ---------------------------------------------------------------------------

ARRIVAL_ALERT_KEYWORDS = (
    "delay",
    "delayed",
    "stuck",
    "held",
    "lost",
    "shipment",
    "supplier",
    "port",
    "transit",
    "pause",
)
DEMAND_UP_ALERT_KEYWORDS = (
    "increase",
    "surge",
    "spike",
    "elevated",
    "strong demand",
    "demand up",
)
DEMAND_DOWN_ALERT_KEYWORDS = ("decrease", "drop", "weak", "slow")

_ARRIVAL_PAYLOAD = ProposalPayload(
    target_stream=TargetStream.ARRIVAL,
    shock_family=ShockFamily.SHIPMENT_LOSS,
    direction=Direction.ARRIVAL_INTERRUPTED,
    onset_window=(0, 0),
    magnitude_bin=MagnitudeBin.MEDIUM,
    persistence=Persistence.PERSISTENT,
    duration_bin=DurationBin.MEDIUM,
    evidence_refs=(),
    prospective_signature="sig_arrival_stall",
)

_DEMAND_DOWN_PAYLOAD = ProposalPayload(
    target_stream=TargetStream.DEMAND,
    shock_family=ShockFamily.DEMAND_LEVEL,
    direction=Direction.DEMAND_DOWN,
    onset_window=(0, 0),
    magnitude_bin=MagnitudeBin.MEDIUM,
    persistence=Persistence.PERSISTENT,
    duration_bin=DurationBin.LONGER,
    evidence_refs=(),
    prospective_signature="sig_demand_level_down",
)

KEYWORD_RULES: tuple[tuple[tuple[str, ...], ProposalPayload], ...] = (
    (ARRIVAL_ALERT_KEYWORDS, _ARRIVAL_PAYLOAD),
    (DEMAND_UP_ALERT_KEYWORDS, DEMAND_UP_PAYLOAD),
    (DEMAND_DOWN_ALERT_KEYWORDS, _DEMAND_DOWN_PAYLOAD),
)
"""The keyword table, **provisional until module 03** owns alert parsing. Matching is plain
substring on the lowercased text (which is why the multi-word cues work — and why ``"port"``
fires inside ``"report"``; the test suite pins that consequence so the choice is explicit).
First class in this tuple wins when the text hits several — registration order, no scoring."""


def parse_alert_text(text: str, *, evidence_refs: tuple[str, ...] = ()) -> ProposalPayload | None:
    """Rule-parse one alert's text into a fixed payload, or ``None`` to abstain.

    The returned payload is the class's template with ``evidence_refs`` filled in — the only
    field the alert itself can legitimately supply.
    """
    lowered = text.lower()
    for keywords, payload in KEYWORD_RULES:
        if any(kw in lowered for kw in keywords):
            return replace(payload, evidence_refs=evidence_refs)
    return None


@dataclass(slots=True, kw_only=True)
class KeywordParserArm(CompilerSwitchArm):
    """Control: the alert channel answered by a keyword table instead of a model.

    The first alert whose text parses decisively compiles the class's payload and switches;
    alerts after that are ignored (the base only asks until the switch — one spec per episode,
    the proposal cap's spirit). Unparseable text abstains: no switch, baseline runs on.
    """

    arm_id: str = KEYWORD_CONTROL_ARM_ID

    def _switch_payload(self, obs: PeriodObservation) -> ProposalPayload | None:
        if obs.alert is None:
            return None
        return parse_alert_text(obs.alert.text, evidence_refs=(obs.alert.alert_id,))


# ---------------------------------------------------------------------------
# the parsing upper bound (R5.5)
# ---------------------------------------------------------------------------


def alertspec_to_payload(spec: HiddenAlertSpec) -> ProposalPayload:
    """The 1:1 map: every model-controlled field of the canonical spec, plus its family.

    ``evidence_refs`` is the only payload field with no counterpart on
    :class:`~collie.contracts.HiddenAlertSpec`; it stays empty rather than being invented.
    """
    return ProposalPayload(
        target_stream=spec.target_stream,
        shock_family=spec.family,
        direction=spec.direction,
        onset_window=spec.onset_window,
        magnitude_bin=spec.magnitude_bin,
        persistence=spec.persistence,
        duration_bin=spec.duration_bin,
        evidence_refs=(),
        prospective_signature=spec.prospective_signature,
    )


@dataclass(slots=True, kw_only=True)
class AlertSpecUpperBoundArm(CompilerSwitchArm):
    """The canonical-parsing upper bound (R5.5) — **this arm reads hidden truth.**

    The harness constructs it with the episode's canonical
    :class:`~collie.contracts.HiddenAlertSpec` and the alert's period, both injected from
    hidden truth through this constructor — the only place hidden state may enter. When the
    observation period reaches the alert period, the canonical spec is mapped directly onto a
    payload (``alertspec_to_payload``) and compiled: the score of a perfect parser. The gap
    between the keyword parser and this arm prices parsing; the gap to the oracle prices the
    alert channel itself.

    Because it carries hidden state, the runner's ``check_controller_isolation`` must stay
    ``False`` for this arm — ``tests/test_controls.py`` asserts the walk finds the spec here
    and nowhere else in this module.
    """

    alert_spec: HiddenAlertSpec
    alert_period: int
    arm_id: str = ALERTSPEC_UB_ARM_ID

    def __post_init__(self) -> None:
        # Explicit base call: under @dataclass(slots=True) the zero-argument super() binds to
        # the pre-slots class object and raises TypeError.
        CompilerSwitchArm.__post_init__(self)
        if self.alert_period < 1:
            raise ValueError(f"alert_period must be >= 1, got {self.alert_period}")

    def _switch_payload(self, obs: PeriodObservation) -> ProposalPayload | None:
        if obs.period < self.alert_period:
            return None
        return alertspec_to_payload(self.alert_spec)
