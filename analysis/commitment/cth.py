"""Certify-then-hedge (CtH): graded, evidence-sized commitment to LLM shock hypotheses.

The registered arm 10 lets a proposal act only after its e-process crosses 1/alpha_j, and then
acts on the compiled configuration at the magnitude the LLM stated. CtH keeps the e-processes and
changes what they are used for:

1. **Hypotheses.** At each trigger firing ``j`` (at most two, the frozen trigger's limit) a fixed,
   action-aligned set ``H = {demand_up, demand_down, lead_time, pulse_up}`` is registered. The
   families module 04 cannot profitably act on (compound, shipment_loss, transit_pause; zero or
   negative oracle headroom) carry no hypothesis. Hypothesis ``h`` of firing ``j`` gets prior
   mass ``a_j * w_jh`` with ``a_j = alpha * 2^-j`` (the frozen alpha schedule) and
   ``w_jh = lam / |H| + (1 - lam) * 1{h = LLM's family}``. The LLM therefore only sets prior
   weights: ``lam = 1`` is content-free (no model call), ``lam = 0`` trusts the model's family
   alone, and an abstention or a non-actionable family leaves its share with the null.
2. **Certification.** Each hypothesis has its own module 05 e-process (``DemandEProcess`` or
   ``ArrivalEProcess``, built from a canonical legal spec with the LLM's onset window for the
   LLM's hypothesis and the widest registered window otherwise), conditioned through ``tau_j``
   and fed every later period. Every hypothesis keeps receiving evidence after a later firing,
   so nothing is lost to supersession.
3. **Posterior.** The shock mass of ``(j, h)`` at decision ``t`` is proportional to
   ``a_j w_jh E_jh,t-1``; the null keeps ``1 - sum a_j w_jh``. Under the null each ``E`` is a
   test supermartingale (as far as module 05's null holds), so the total shock mass obeys the
   exposure bounds in ``PLAN.md`` stage B whatever the LLM said.
4. **Sizing.** Within a hypothesis, the size comes from the data, not the LLM's magnitude bin: a
   Gaussian working likelihood of the visible demand path over (multiplier in the registered
   set, start, duration) for demand hypotheses, with a conjugate post-change level anchored at
   the pre-onset mean; and over (offset in {1, 2, 3}, start) of the visible receipts and
   in-transit total for the lead-time hypothesis.
5. **Hedge.** The order-up-to requirement is the critical-fractile ``p / (p + h)`` quantile of the
   posterior-predictive mixture of lead-time demand net of ``gamma`` times in-transit; the
   order is ``min(ceil(x - on_hand)^+, published smoother, cap)``. With no live hypothesis the
   mixture is arm 1's own predictive, so the arm then orders exactly as arm 1.

The mechanism is the offline "E-Hedge" prototype (``hedge2``-``hedge4``) of the method-design
panel, re-implemented as a live arm that makes its own module 02 calls, with the hypothesis-set
prior of the "PriorGate" design. ``scheme='map'`` (compiled target iff the shock mass is at least
1/2) and ``scheme='linear'`` (target interpolated by the shock mass) are the ablations.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.special import ndtr
from scipy.stats import norm

from collie.arms.history import BenchmarkHistory
from collie.arms.protocols import RepairingSpecPrompter
from collie.contracts import (
    Decision,
    Direction,
    DurationBin,
    MagnitudeBin,
    ParseOutcome,
    PeriodObservation,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.control.controller import PUBLISHED_SMOOTHER_QUANTILE, critical_fractile
from collie.control.forecast import DemandForecaster
from collie.data.families.base import BaselineKind, BaselineSpec
from collie.data.families.demand import MAGNITUDE_SETS
from collie.verify.adapter import MIN_BASELINE_PARAMETER
from collie.verify.arrival import ArrivalEProcess
from collie.verify.demand import DemandEProcess

ALPHA = 0.05
Z95 = float(norm.ppf(PUBLISHED_SMOOTHER_QUANTILE))
HYPOTHESES = ("demand_up", "demand_down", "lead_time", "pulse_up")
UNIFORM_WINDOW = (-2, 2)
DELTAS = (1, 2, 3)
CANONICAL: dict[str, dict] = {
    "demand_up": {
        "shock_family": ShockFamily.DEMAND_LEVEL,
        "target_stream": TargetStream.DEMAND,
        "direction": Direction.DEMAND_UP,
        "persistence": Persistence.PERSISTENT,
        "duration_bin": DurationBin.LONGER,
        "prospective_signature": "sig_demand_level_up",
    },
    "demand_down": {
        "shock_family": ShockFamily.DEMAND_LEVEL,
        "target_stream": TargetStream.DEMAND,
        "direction": Direction.DEMAND_DOWN,
        "persistence": Persistence.PERSISTENT,
        "duration_bin": DurationBin.LONGER,
        "prospective_signature": "sig_demand_level_down",
    },
    "lead_time": {
        "shock_family": ShockFamily.LEAD_TIME_SHIFT,
        "target_stream": TargetStream.ARRIVAL,
        "direction": Direction.ARRIVAL_DELAYED,
        "persistence": Persistence.PERSISTENT,
        "duration_bin": DurationBin.LONGER,
        "prospective_signature": "sig_arrival_delay",
    },
    "pulse_up": {
        "shock_family": ShockFamily.TEMPORARY_PULSE,
        "target_stream": TargetStream.DEMAND,
        "direction": Direction.DEMAND_UP,
        "persistence": Persistence.TRANSIENT,
        "duration_bin": DurationBin.SHORT,
        "prospective_signature": "sig_demand_pulse",
    },
}


def hypothesis_key(family: ShockFamily, direction: Direction) -> str | None:
    """The action-aligned hypothesis an LLM proposal names, or None (non-actionable)."""
    if family is ShockFamily.DEMAND_LEVEL:
        return {Direction.DEMAND_UP: "demand_up", Direction.DEMAND_DOWN: "demand_down"}.get(
            direction
        )
    if family is ShockFamily.LEAD_TIME_SHIFT:
        return "lead_time"
    if family is ShockFamily.TEMPORARY_PULSE and direction is Direction.DEMAND_UP:
        return "pulse_up"
    return None


def canonical_spec(key: str, *, tau: int, index: int, window: tuple[int, int]) -> ShockSpec:
    return ShockSpec(
        **CANONICAL[key],
        onset_window=window,
        magnitude_bin=MagnitudeBin.MEDIUM,
        evidence_refs=(),
        tau_j=tau,
        proposal_index=index,
        model_id="cth-canonical",
        decoding_hash="det-v1",
        prompt_hash="cth-canonical",
    )


def mixture_quantile(comps, beta: float, it: float) -> float:
    """x with sum_c w_c Phi((x + g_c it - mu_c) / sd_c) = beta; comps: (w, mu, sd, g)."""
    w = np.array([c[0] for c in comps], float)
    mu = np.array([c[1] for c in comps], float)
    sd = np.maximum(np.array([c[2] for c in comps], float), 1e-9)
    g = np.array([c[3] for c in comps], float)
    shift = mu - g * it
    lo = float(np.min(shift - 12 * sd))
    hi = float(np.max(shift + 12 * sd))
    while hi - lo > 1e-7:
        mid = 0.5 * (lo + hi)
        if float(np.sum(w * ndtr((mid - shift) / sd))) < beta:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass
class _Hyp:
    key: str
    firing: int
    tau: int
    prior: float
    spec: ShockSpec
    from_llm: bool
    baseline: tuple[float, float]
    verifier: object = None
    dead: bool = False


@dataclass(slots=True)
class CertifyThenHedgeArm:
    """A Controller: module 02 proposals (when ``lam < 1``) steer a certified Bayes hedge."""

    lam: float
    promised_lead_time: int
    horizon: int
    train_demand: tuple[float, ...]
    order_cap: float
    trigger: object
    channel: object = None
    prompter: object = None
    parser: object = None
    replay: dict | None = None
    """Development only: ``{period: payload dict or None}`` answers replayed instead of a call
    (arm 10's cached answers for the same episode); ``None`` makes live module 02 calls."""
    arm_id: str = "arm12_cth"
    scheme: str = "hedge"
    n0: float = 5.0
    p_persist: float = 0.5
    lt_noise: float = 0.05
    _hist: BenchmarkHistory = field(init=False, repr=False)
    _f: DemandForecaster = field(init=False, repr=False)
    _hyps: list = field(default_factory=list, repr=False)
    _firings: int = field(default=0, repr=False)
    log: list = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.lam <= 1.0:
            raise ValueError("lam must be in [0, 1]")
        live = self.channel is not None and self.prompter is not None and self.parser is not None
        if self.lam < 1.0 and self.replay is None and not live:
            raise ValueError("an arm that consults the model needs a channel, prompter and parser")
        self._hist = BenchmarkHistory(arm_id=self.arm_id)
        self._f = DemandForecaster(train_demand=self.train_demand)

    def reset(self) -> None:
        self._hist.reset()
        self._f.reset()
        if isinstance(self.prompter, RepairingSpecPrompter):
            self.prompter.reset()
        self._hyps = []
        self._firings = 0
        self.log = []

    # -- evidence --------------------------------------------------------------

    def _build(self, h: _Hyp) -> None:
        tau = h.tau
        demands = tuple(self._hist.demands[:tau])
        arrivals = tuple(
            (float(self._hist.dispatch_at(p)), float(self._hist.arrivals[p - 1]))
            for p in range(1, tau + 1)
        )
        try:
            if h.spec.target_stream is TargetStream.ARRIVAL:
                h.verifier = ArrivalEProcess.from_spec(
                    h.spec, alpha_episode=ALPHA, preproposal_history=arrivals
                )
            else:
                mean, sd = h.baseline
                baseline = BaselineSpec(
                    BaselineKind.STATIONARY_IID,
                    mean=max(mean, MIN_BASELINE_PARAMETER),
                    sd=max(sd, MIN_BASELINE_PARAMETER),
                )
                h.verifier = DemandEProcess.from_spec(
                    h.spec,
                    baseline=baseline,
                    alpha_episode=ALPHA,
                    history_before_proposal=demands,
                )
        except Exception:  # an unbuildable construction carries no mass
            h.dead = True

    def _feed(self, h: _Hyp, period: int) -> None:
        try:
            if isinstance(h.verifier, ArrivalEProcess):
                h.verifier.observe(
                    period, self._hist.dispatch_at(period), self._hist.arrivals[period - 1]
                )
            else:
                h.verifier.observe(period, self._hist.demands[period - 1])
        except Exception:  # an observation impossible under the law ends it
            h.dead = True

    def _evidence(self, obs: PeriodObservation) -> None:
        ev = obs.period - 1
        for h in self._hyps:
            if h.dead or ev < h.tau:
                continue
            if ev == h.tau:
                self._build(h)
            elif h.verifier is not None:
                self._feed(h, ev)

    # -- proposals -------------------------------------------------------------

    def _ask(self, obs: PeriodObservation) -> ShockSpec | None:
        """One module 02 proposal (with one repair), as ShockSpecArm makes it."""
        if self.replay is not None:
            payload = self.replay.get(obs.period)
            if payload is None:
                return None
            return ShockSpec(
                shock_family=ShockFamily(payload["shock_family"]),
                target_stream=TargetStream(payload["target_stream"]),
                direction=Direction(payload["direction"]),
                onset_window=(
                    None if payload["onset_window"] is None else tuple(payload["onset_window"])
                ),
                magnitude_bin=(
                    None
                    if payload["magnitude_bin"] is None
                    else MagnitudeBin(payload["magnitude_bin"])
                ),
                persistence=Persistence(payload["persistence"]),
                duration_bin=DurationBin(payload["duration_bin"]),
                evidence_refs=tuple(payload["evidence_refs"]),
                prospective_signature=payload["prospective_signature"],
                tau_j=obs.period,
                proposal_index=self._firings,
                model_id="replay",
                decoding_hash="det-v1",
                prompt_hash="replay",
            )
        prompt = self.prompter.prompt(obs)
        raw = self.channel.complete_attempt(prompt, decoding_hash="det-v1", attempt_index=1)
        call_id = self.channel.last_call_id
        payload = self.parser.parse(raw)
        outcome = ParseOutcome.ACCEPTED
        if payload is None:
            self.channel.settle(call_id, ParseOutcome.FALLBACK)
            if not isinstance(self.prompter, RepairingSpecPrompter):
                return None
            prompt = self.prompter.repair_prompt()
            raw = self.channel.complete_attempt(prompt, decoding_hash="det-v1", attempt_index=2)
            call_id = self.channel.last_call_id
            payload = self.parser.parse(raw)
            if payload is None:
                self.channel.settle(call_id, ParseOutcome.FALLBACK)
                return None
            outcome = ParseOutcome.ACCEPTED_AFTER_REPAIR
        self.channel.settle(call_id, outcome)
        return ShockSpec(
            **asdict(payload),
            tau_j=obs.period,
            proposal_index=self._firings,
            model_id=self.channel.model_id,
            decoding_hash="det-v1",
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest(),
        )

    def _prefix_stats(self, target: TargetStream) -> tuple[float, float]:
        samples = self._hist.arrivals if target is TargetStream.ARRIVAL else self._hist.demands
        if not samples:
            return 0.0, 0.0
        mean = sum(samples) / len(samples)
        var = (
            sum((s - mean) ** 2 for s in samples) / (len(samples) - 1) if len(samples) > 1 else 0.0
        )
        return mean, math.sqrt(var)

    def _maybe_propose(self, obs: PeriodObservation) -> bool:
        """Register this firing's hypotheses. Returns whether the trigger fired."""
        if not self.trigger.should_propose(obs):
            return False
        self._firings += 1
        j = self._firings
        a_j = ALPHA * 2.0 ** (-j)
        tau = obs.period
        llm_key, window = None, UNIFORM_WINDOW
        if self.lam < 1.0:
            spec = self._ask(obs)
            if spec is not None and not spec.is_abstention:
                llm_key = hypothesis_key(spec.shock_family, spec.direction)
                if spec.onset_window is not None:
                    window = tuple(spec.onset_window)
        weights = {key: self.lam / len(HYPOTHESES) for key in HYPOTHESES}
        if llm_key is not None:
            weights[llm_key] += 1.0 - self.lam
        for key, weight in weights.items():
            if weight <= 0.0:
                continue
            use_llm_window = key == llm_key and self.lam < 1.0
            spec = canonical_spec(
                key, tau=tau, index=j, window=window if use_llm_window else UNIFORM_WINDOW
            )
            self._hyps.append(
                _Hyp(
                    key=key,
                    firing=j,
                    tau=tau,
                    prior=a_j * weight,
                    spec=spec,
                    from_llm=key == llm_key,
                    baseline=self._prefix_stats(spec.target_stream),
                )
            )
        return True

    # -- sizing ----------------------------------------------------------------

    def _pre_stats(self, s: int) -> tuple[float, float]:
        xs = list(self.train_demand) + list(self._hist.demands[: max(0, s - 1)])
        if len(xs) < 2:
            xs = list(self.train_demand)
        arr = np.asarray(xs, float)
        return float(arr.mean()), float(arr.std(ddof=1))

    def _within_demand(self, h: _Hyp, t: int):
        tau = h.tau
        if h.key == "pulse_up":
            ms = MAGNITUDE_SETS[3]
            durs = [(d, 1 / 3) for d in (2, 3, 4)]
        else:
            ms = MAGNITUDE_SETS[1] if h.key == "demand_up" else MAGNITUDE_SETS[2]
            durs = [(None, self.p_persist)] + [(d, (1 - self.p_persist) / 3) for d in (2, 3, 4)]
        starts = list(range(max(2, tau - 4), tau + 3))
        lo = starts[0]
        demands = self._hist.demands
        cands = []
        for s in starts:
            mu0, sd0 = self._pre_stats(s)
            sd0 = max(sd0, 1.0)
            for m in ms:
                for d, pd in durs:
                    ll = 0.0
                    for u in range(lo, t):
                        act = u >= s and (d is None or u < s + d)
                        mu, sd = (m * mu0, m * sd0) if act else (mu0, sd0)
                        ll += -0.5 * ((demands[u - 1] - mu) / sd) ** 2 - math.log(sd)
                    cands.append((ll + math.log(pd / (len(starts) * len(ms))), (m, s, d)))
        lls = np.array([c[0] for c in cands])
        ps = np.exp(lls - lls.max())
        ps /= ps.sum()
        return [(float(p), c[1]) for p, c in zip(ps, cands, strict=True) if p > 1e-6]

    def _demand_comp(self, params, t: int, lead: int) -> tuple[float, float]:
        m, s, d = params
        mu0, sd0 = self._pre_stats(s)
        level = m * mu0
        if math.isfinite(self.n0):
            end = t - 1 if d is None else min(t - 1, s + d - 1)
            post = self._hist.demands[s - 1 : end] if end >= s else []
            if post:
                level = (self.n0 * m * mu0 + sum(post)) / (self.n0 + len(post))
        sd1 = m * sd0
        mean = var = 0.0
        for u in range(t, t + lead + 1):
            if u >= s and (d is None or u < s + d):
                mean += level
                var += sd1**2
            else:
                mean += mu0
                var += sd0**2
        return mean, math.sqrt(var)

    def _lt_posterior(self, h: _Hyp, t: int, lead: int, it_now: float):
        tau = h.tau
        starts = range(max(2, tau - 4), tau + 5)
        q = [self._hist.dispatch_at(u) for u in range(1, t)]
        arrivals = list(self._hist.arrivals)
        cands = []
        for delta in DELTAS:
            for s in starts:
                ell = [lead + (delta if u >= s else 0) for u in range(1, t)]
                pred = [0.0] * (t + 8)
                for u, (qq, e) in enumerate(zip(q, ell, strict=True), start=1):
                    if u + e < len(pred):
                        pred[u + e] += qq
                ll = 0.0
                for v in range(max(2, tau - 4), t):
                    sd = 2.0 + self.lt_noise * abs(pred[v])
                    ll += -0.5 * ((arrivals[v - 1] - pred[v]) / sd) ** 2 - math.log(sd)
                pit = sum(
                    qq for u, (qq, e) in enumerate(zip(q, ell, strict=True), start=1) if u + e >= t
                )
                sd = 2.0 + self.lt_noise * abs(pit)
                ll += -0.5 * ((it_now - pit) / sd) ** 2 - math.log(sd)
                cands.append((ll, delta, s))
        lls = np.array([c[0] for c in cands])
        ps = np.exp(lls - lls.max())
        ps /= ps.sum()
        return [(float(p), dl, s) for p, (_, dl, s) in zip(ps, cands, strict=True)]

    # -- decision --------------------------------------------------------------

    def _components(self, t: int, lead: int, mean: float, std: float, it_now: float):
        live = [h for h in self._hyps if h.verifier is not None and not h.dead]
        if not live:
            return None, None
        total = sum(h.prior for h in live)
        comps = [(math.log(1.0 - total), (1 + lead) * mean, math.sqrt(1 + lead) * std, 1.0)]
        masses: dict[str, float] = {}
        for h in live:
            log_e = h.verifier._engine.log_e_value
            lmass = math.log(h.prior) + (log_e if not math.isnan(log_e) else -math.inf)
            masses[h.key] = masses.get(h.key, 0.0) + (math.exp(lmass) if lmass > -700 else 0.0)
            if h.key == "lead_time":
                for p, delta, s in self._lt_posterior(h, t, lead, it_now):
                    if p < 1e-6:
                        continue
                    le = lead + (delta if t >= s else 0)
                    comps.append(
                        (lmass + math.log(p), (1 + le) * mean, math.sqrt(1 + le) * std, 1.0)
                    )
            else:
                for p, params in self._within_demand(h, t):
                    mu, sd = self._demand_comp(params, t, lead)
                    comps.append((lmass + math.log(p), mu, sd, 1.0))
        return comps, masses

    def order(self, obs: PeriodObservation) -> Decision:
        if self.channel is not None:
            self.channel.set_period(obs.period)
        self._hist.observe(obs)
        if isinstance(self.prompter, RepairingSpecPrompter):
            self.prompter.observe(obs)
        self._hist.record_demand(obs)
        if obs.period > 1:
            self._f.record(obs.prev_demand)
        self._evidence(obs)
        fired = self._maybe_propose(obs)
        called = fired and self.lam < 1.0

        stats = self._f.stats()
        beta = critical_fractile(obs.profit_per_unit, obs.holding_cost_per_unit)
        z = float(norm.ppf(beta))
        lead = self.promised_lead_time
        t = obs.period
        on_hand, it_now = obs.on_hand, obs.in_transit_total
        base_target = (1 + lead) * stats.mean + z * math.sqrt(1 + lead) * stats.std
        smoother = math.ceil(stats.mean + Z95 * stats.std)
        comps, masses = self._components(t, lead, stats.mean, stats.std, it_now)
        shock_mass, top = 0.0, None
        if comps is None:
            x = base_target - it_now
        else:
            logs = np.array([c[0] for c in comps])
            ps = np.exp(logs - logs.max())
            ps /= ps.sum()
            shock_mass = 1.0 - float(ps[0])
            mix = [(float(p), *c[1:]) for p, c in zip(ps, comps, strict=True)]
            if self.scheme == "hedge":
                x = mixture_quantile(mix, beta, it_now)
            else:
                alt = mix[1:]
                tot = sum(c[0] for c in alt)
                xb = base_target - it_now
                xc = (
                    mixture_quantile([(c[0] / tot, *c[1:]) for c in alt], beta, it_now)
                    if tot > 0
                    else xb
                )
                if self.scheme == "linear":
                    w = shock_mass
                elif self.scheme == "map":
                    w = 1.0 if shock_mass >= 0.5 else 0.0
                else:
                    raise ValueError(f"unknown scheme {self.scheme!r}")
                x = xb + w * (xc - xb)
            if masses:
                top = max(masses, key=masses.get)
        quantity = float(min(max(math.ceil(x - on_hand), 0), smoother, self.order_cap))
        self._hist.note_dispatch(t, quantity)
        self.log.append((t, round(shock_mass, 6), top))
        active = shock_mass >= 0.5 and top is not None
        return Decision(
            period=t,
            order_quantity=quantity,
            arm_id=self.arm_id,
            llm_called=called,
            triggered=fired,
            active_spec_id=f"cth-{top}@t{t}" if active else None,
        )
