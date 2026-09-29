"""Null exposure Monte Carlo of the frozen certify-then-hedge arm. Exploratory.

The bound under test is the exposure theorem: ``PLAN.md`` stage B, guarantee 1, and
``thm:exposure`` in the paper (not the paper's activation theorem).

Offline only: no model call, no registered episode, and ``cth.py`` is imported, never changed.
Every episode is the real :class:`~collie.sim.runner.EpisodeRunner` driving the frozen
:class:`~analysis.commitment.cth.CertifyThenHedgeArm`. The model is replaced by the arm's own
``replay`` seam (a fixed payload at each scripted firing, parsed by the arm exactly as a cached
answer is) and the frozen trigger by a scripted schedule, so nothing reaches module 02.

**Null paths.** Horizon 50, promised lead time 2, ``p = 4``, ``h = 1``, no order cap. The 50
demands and then the 5 train rows are iid ``round(N(100, sd^2))`` clipped at 0 (module 01's
``draw_baseline`` and ``as_demand_cells``), with ``sd = 100 * CV`` and CV in {0.15, 0.25, 0.35}.
Delays are deterministic (every order arrives after 2 periods) or, as a sensitivity, drawn per
order from module 05's registered arrival null (``REGISTERED_NULL_LAW``: delays 0..4, loss, and a
per-period transit pause), the law the lead-time e-process takes as its null. The delay and pause
draws come after the demand draws from the same generator, so both laws share the demand path.

**Firings.** One firing at ``tau`` in {10, 15, 20}, or two at ``tau`` and ``tau + 6`` (the
earliest pair the frozen refractory window of 5 allows). Firing times are scripted, not chosen by
the frozen detector. Every firing carries the same fixed false payload: a fixed family
(``demand_up``, the one most likely to cause over-ordering, in the main table; ``lead_time`` and
``demand_down`` in the other-family table) with onset window (0, 2), the modal window of the
cached real-content banks. Priors ``lam`` in {0, 0.25, 1}; ``lam = 1`` is content-free, so it
carries no payload and is run once per path.

**Scope.** The payload does not depend on the path. The theorem covers any ``F_tau``-measurable
model output; a payload that picks its family or window from the recent path is not tested here,
and neither are firings at detector-chosen times, which under ``plug_in`` could select
unfavorable prefixes (the stage C silent twins fire that way). The stage C null twins have a
stationary baseline with mean 100 and sd 25 and deterministic lead times, and their false alerts
come at period 10, so CV 0.25 with deterministic delays is the twin-matched cell (``tau = 10``
for the false-alert twins). The promised lead is fixed at 2 here, while some stage C lead-time
twins have lead 1. The other CVs, firing times and the registered delay law are extensions.

**Null regimes.** ``plug_in`` is the arm as frozen: each demand e-process takes the Gaussian
baseline estimated from the demand prefix before its firing, which module 05's null only
approximates. ``known`` gives the demand e-processes the true mean and sd in place of the prefix
estimate (:class:`KnownNullArm` overrides ``_prefix_stats`` for the demand stream only); the
hedge's sizing and the arrival e-process are unchanged. Under ``known`` every demand e-process is
a test martingale for the simulated demand. The lead-time e-process is one only when the delays
follow the registered law: deterministic delays are outside its null.

**Bounds.** ``A = sum_{j,h} a_j w_jh`` is read from the priors the arm registered (``alpha / 2``
for one firing, ``3 alpha / 4`` for two). For every stopping time ``sigma``,
``E0[Pi_sigma] <= A``, ``P0(sup_t Pi_t >= c) <= A (1 - c) / (c (1 - A))``, and
``E0[sum_t Pi_t] <= sum_t A_t`` with ``A_t`` the budget of the hypotheses live at decision ``t``.
``Pi_t`` is the arm's logged shock mass at decision ``t``. Reported stopping times: ``sigma = T``
(the last decision) and ``sigma = min(first t with Pi_t >= 0.1, T)``. Fixed decisions are checked
against ``A_t`` (``E0[Pi_t] <= A_t``) over ``t > tau_1 + 1``: at the first build ``Pi_t = A_1``
by construction. A check is flagged ``point`` when its estimate exceeds the bound and ``clear``
when a mean exceeds it by more than two Monte Carlo SEs or a ``P(sup)`` has its one-sided 97.5%
Clopper-Pearson lower bound above it; the Markdown states the chance rate across all checks.

**Seeds and cells.** Path ``(cv, rep)`` uses seed ``SEED_BASE + MAX_REPS * cv_index + rep``, and
every cell of that CV runs on it (common random numbers): a smaller run is a prefix of a larger
one, and contrasts between cells are on identical demand. Arm 1 runs once per path; harm is arm
1's net reward minus the arm's on the same path (positive: the arm lost). That is the negative of
stage C's null-safety contrast (``arm12_cth - arm1``, margin -25), and only the ``plug_in`` harm
is the frozen arm's: under ``known`` it is a counterfactual arm's. A ``lam = 0`` lead-time cell
registers no demand hypothesis, so its two regimes are one computation; it is run once, stored
under both in the JSON, and reported once (under ``known``) in the Markdown. Three strata (``default_strata``): the main table (deterministic
delays, ``demand_up`` at ``lam`` 0 and 0.25, and ``lam = 1``; ``--reps`` paths per CV), the
other families (deterministic, ``lead_time`` and ``demand_down``; ``--other-reps``), and the
registered-law sensitivity (every prior at CV 0.25; ``--sensitivity-reps``). The lead-time
e-process's exact forward filter dominates the run time, which is what sets the smaller strata.

Usage::

    uv run python -m analysis.commitment.mc_exposure --reps 1000 --processes 44

writes ``mc_exposure.json`` and ``mc_exposure.md`` to ``--out-dir`` (default
``analysis/commitment/out``). The files depend only on the options, never on ``--processes``; the
wall-clock time is printed, not written.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.stats import beta as beta_dist

from analysis.commitment.cth import ALPHA, CertifyThenHedgeArm
from collie.arms.base_stock import CappedBaseStockController
from collie.contracts import (
    AnalysisClass,
    EpisodeSpec,
    PeriodObservation,
    ShockFamily,
    SupplyRealization,
    TargetStream,
)
from collie.data.families.base import BaselineKind, BaselineSpec, as_demand_cells, draw_baseline
from collie.sim.loader import LoadedInstance
from collie.sim.runner import EpisodeRunner
from collie.trigger.calibration import FROZEN
from collie.verify.arrival import REGISTERED_NULL_LAW

__all__ = [
    "CVS",
    "FAMILIES",
    "LAWS",
    "MAIN_PRIORS",
    "OTHER_PRIORS",
    "PAYLOADS",
    "PRIORS",
    "REGIMES",
    "SEED_BASE",
    "TAUS",
    "Cell",
    "CellAccumulator",
    "EpisodeRow",
    "KnownNullArm",
    "ScriptedTrigger",
    "Stratum",
    "budget",
    "build_arm",
    "default_strata",
    "main",
    "null_instance",
    "path_seed",
    "render_markdown",
    "run_cell_episode",
    "run_mc",
    "run_path",
    "ville_bound",
    "write_outputs",
]

SEED_BASE = 96_000_000
"""Seeds occupy ``[SEED_BASE, SEED_BASE + len(CVS) * MAX_REPS)``: above every registered generator
pool (at most 90_001_299) and clear of the 97_xxx_xxx and 98_xxx_xxx seeds of the earlier
prototype Monte Carlo."""
MAX_REPS = 100_000

MEAN = 100.0
CVS = (0.15, 0.25, 0.35)
HORIZON = 50
TRAIN_ROWS = 5
PROMISED_LEAD_TIME = 2
PROFIT = 4.0
HOLDING = 1.0
TAUS = (10, 15, 20)
SECOND_GAP = FROZEN.refractory_window + 1
"""Two firings are ``tau`` and ``tau + SECOND_GAP``: the earliest pair the frozen trigger allows."""
FIRINGS = (1, 2)
LAWS = ("deterministic", "registered")
REGIMES = ("plug_in", "known")
FAMILIES = ("demand_up", "lead_time", "demand_down")
LAMS = (0.0, 0.25, 1.0)
MAIN_PRIORS: tuple[tuple[float, str | None], ...] = (
    (0.0, "demand_up"),
    (0.25, "demand_up"),
    (1.0, None),
)
"""``(lam, fixed LLM family)``: the fixed false family and the content-free prior."""
OTHER_PRIORS: tuple[tuple[float, str | None], ...] = tuple(
    (lam, family) for lam in (0.0, 0.25) for family in ("lead_time", "demand_down")
)
PRIORS = tuple(
    sorted(MAIN_PRIORS + OTHER_PRIORS, key=lambda p: (p[0], FAMILIES.index(p[1] or "demand_up")))
)
THRESHOLDS = (0.1, 0.25, 0.5)
STOP_LEVEL = 0.1
WINDOW = (0, 2)
SENSITIVITY_CVS = (0.25,)
TOL = 1e-9
"""Float slack below which an estimate equal to its bound is not called above it."""

_PAYLOAD_FIELDS: dict[str, dict] = {
    "demand_up": {
        "shock_family": "demand_level",
        "target_stream": "demand",
        "direction": "demand_up",
        "persistence": "persistent",
        "duration_bin": "longer",
        "prospective_signature": "sig_demand_level_up",
    },
    "demand_down": {
        "shock_family": "demand_level",
        "target_stream": "demand",
        "direction": "demand_down",
        "persistence": "persistent",
        "duration_bin": "longer",
        "prospective_signature": "sig_demand_level_down",
    },
    "lead_time": {
        "shock_family": "lead_time_shift",
        "target_stream": "arrival",
        "direction": "arrival_delayed",
        "persistence": "persistent",
        "duration_bin": "longer",
        "prospective_signature": "sig_arrival_delay",
    },
}
PAYLOADS: dict[str, dict] = {
    family: {**fields, "onset_window": list(WINDOW), "magnitude_bin": "high", "evidence_refs": []}
    for family, fields in _PAYLOAD_FIELDS.items()
}
"""The false proposals, in the arm's ``replay`` payload format (``proposals.jsonl`` rows)."""


# ---------------------------------------------------------------------------
# cells, strata, seeds, bounds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cell:
    law: str
    cv: float
    tau: int
    firings: int
    lam: float
    family: str | None
    regime: str

    @property
    def periods(self) -> tuple[int, ...]:
        return (self.tau, self.tau + SECOND_GAP)[: self.firings]

    @property
    def regime_free(self) -> bool:
        """No demand hypothesis is registered, so ``plug_in`` and ``known`` coincide."""
        return (
            self.lam == 0.0
            and self.family is not None
            and PAYLOADS[self.family]["target_stream"] == "arrival"
        )

    def key(self) -> dict:
        return {
            "law": self.law,
            "cv": self.cv,
            "tau": self.tau,
            "firings": self.firings,
            "firing_periods": list(self.periods),
            "lam": self.lam,
            "family": self.family,
            "regime": self.regime,
        }

    def label(self) -> str:
        return (
            f"{self.law} cv={self.cv:g} tau={self.tau} firings={self.firings} "
            f"lam={self.lam:g} {self.family or 'content-free'} {self.regime}"
        )


@dataclass(frozen=True, slots=True)
class Stratum:
    name: str
    law: str
    cvs: tuple[float, ...]
    priors: tuple[tuple[float, str | None], ...]
    reps: int

    def cells(self, cv: float) -> tuple[Cell, ...]:
        return tuple(
            Cell(self.law, cv, tau, n, lam, family, regime)
            for tau in TAUS
            for n in FIRINGS
            for lam, family in self.priors
            for regime in REGIMES
        )


def default_strata(
    reps: int,
    other_reps: int,
    sensitivity_reps: int,
    *,
    cvs: Sequence[float] = CVS,
    sensitivity_cvs: Sequence[float] = SENSITIVITY_CVS,
) -> tuple[Stratum, ...]:
    out = [Stratum("main", "deterministic", tuple(cvs), MAIN_PRIORS, reps)]
    if other_reps:
        out.append(Stratum("other_families", "deterministic", tuple(cvs), OTHER_PRIORS, other_reps))
    if sensitivity_reps:
        out.append(
            Stratum(
                "registered_law", "registered", tuple(sensitivity_cvs), PRIORS, sensitivity_reps
            )
        )
    return tuple(out)


def path_seed(cv: float, rep: int) -> int:
    if cv not in CVS:
        raise ValueError(f"cv {cv} not in {CVS}")
    if not 0 <= rep < MAX_REPS:
        raise ValueError(f"replicate {rep} outside 0..{MAX_REPS - 1}")
    return SEED_BASE + MAX_REPS * CVS.index(cv) + rep


def budget(firings: int) -> float:
    """``A = sum_j a_j`` over ``firings`` firings (the frozen schedule ``a_j = alpha 2^-j``)."""
    return math.fsum(ALPHA * 2.0 ** (-j) for j in range(1, firings + 1))


def ville_bound(a: float, c: float) -> float:
    """``P0(sup_t Pi_t >= c) <= A (1 - c) / (c (1 - A))``."""
    return a * (1.0 - c) / (c * (1.0 - a))


def budget_path(cell: Cell) -> np.ndarray:
    """``A_t``: the prior budget live at decision ``t`` (firing ``j`` is built at ``tau_j + 1``)."""
    out = np.zeros(HORIZON)
    for j, tau in enumerate(cell.periods, start=1):
        out[tau:] += ALPHA * 2.0 ** (-j)
    return out


# ---------------------------------------------------------------------------
# episodes and arms
# ---------------------------------------------------------------------------


def null_instance(cv: float, rep: int, law: str) -> LoadedInstance:
    """One synthetic null path: demand, then train, then (registered law) delays and pauses."""
    seed = path_seed(cv, rep)
    rng = np.random.default_rng(seed)
    baseline = BaselineSpec(BaselineKind.STATIONARY_IID, mean=MEAN, sd=MEAN * cv)
    demand = as_demand_cells(draw_baseline(rng, baseline, HORIZON))
    train = as_demand_cells(draw_baseline(rng, baseline, TRAIN_ROWS))
    if law == "deterministic":
        supply = SupplyRealization(lead_times=(float(PROMISED_LEAD_TIME),) * HORIZON)
    elif law == "registered":
        registered = REGISTERED_NULL_LAW
        p = np.array(
            [*registered.finite_delay_probabilities, registered.loss_probability], dtype=float
        )
        p /= p.sum()
        delays = rng.choice(len(p), size=HORIZON, p=p)
        pauses = rng.random(HORIZON) < registered.pause_probability
        supply = SupplyRealization(
            lead_times=tuple(math.inf if d == len(p) - 1 else float(d) for d in delays),
            pause_active=tuple(bool(x) for x in pauses),
        )
    else:
        raise ValueError(f"unknown delay law {law!r}")
    spec = EpisodeSpec(
        episode_id=f"mc_exposure/{law}/cv{cv:g}/{seed}",
        item_id="mc_exposure",
        horizon=HORIZON,
        promised_lead_time=PROMISED_LEAD_TIME,
        profit_per_unit=PROFIT,
        holding_cost_per_unit=HOLDING,
        order_cap=math.inf,
        family=ShockFamily.NO_CHANGE,
        source="mc_exposure",
        train_demand=train,
    )
    return LoadedInstance(
        spec=spec,
        demand=demand,
        supply=supply,
        profits=(PROFIT,) * HORIZON,
        holding_costs=(HOLDING,) * HORIZON,
        dates=tuple(f"Period_{t}" for t in range(1, HORIZON + 1)),
    )


@dataclass(frozen=True, slots=True)
class ScriptedTrigger:
    """Fires at exactly the scripted periods; stateless, so the arm's missing reset is harmless."""

    periods: frozenset[int]

    def should_propose(self, obs: PeriodObservation) -> bool:
        return obs.period in self.periods


class KnownNullArm(CertifyThenHedgeArm):
    """The frozen arm with the true demand mean and sd given to its demand verifiers.

    Only ``_prefix_stats`` for the demand stream changes: it is what ``_maybe_propose`` stores as
    a hypothesis's baseline and what ``_build`` hands module 05. The arrival verifiers never read
    it, and the hedge's sizing (``_pre_stats``) is untouched.
    """

    def __init__(self, *, known_mean: float, known_sd: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.known = (float(known_mean), float(known_sd))

    def _prefix_stats(self, target: TargetStream) -> tuple[float, float]:
        if target is TargetStream.ARRIVAL:
            return CertifyThenHedgeArm._prefix_stats(self, target)
        return self.known


def build_arm(instance: LoadedInstance, cell: Cell) -> CertifyThenHedgeArm:
    spec = instance.spec
    replay = None if cell.family is None else {t: dict(PAYLOADS[cell.family]) for t in cell.periods}
    kwargs = {
        "lam": cell.lam,
        "promised_lead_time": spec.promised_lead_time,
        "horizon": spec.horizon,
        "train_demand": spec.train_demand,
        "order_cap": spec.order_cap,
        "trigger": ScriptedTrigger(frozenset(cell.periods)),
        "replay": replay,
        "arm_id": f"mc_cth_{cell.regime}",
    }
    if cell.regime == "plug_in":
        return CertifyThenHedgeArm(**kwargs)
    if cell.regime == "known":
        return KnownNullArm(known_mean=MEAN, known_sd=MEAN * cell.cv, **kwargs)
    raise ValueError(f"unknown regime {cell.regime!r}")


def _runner(instance: LoadedInstance) -> EpisodeRunner:
    return EpisodeRunner(instance, analysis_class=AnalysisClass.EXPLORATORY, strict_isolation=False)


@dataclass(frozen=True, slots=True)
class EpisodeRow:
    pi: np.ndarray
    """``Pi_1 .. Pi_T``: the arm's logged shock mass at each decision."""
    net: float
    prior_total: float
    n_hypotheses: int
    n_dead: int
    n_from_llm: int
    consultations: int
    """Decisions the arm flags ``llm_called``. The arm has no channel, so each is a replayed
    payload, never a model call."""


def run_cell_episode(instance: LoadedInstance, cell: Cell) -> EpisodeRow:
    arm = build_arm(instance, cell)
    if arm.channel is not None or arm.prompter is not None or arm.parser is not None:
        raise RuntimeError("the Monte Carlo arm must not hold a model channel")
    outcome = _runner(instance).run(arm)
    pi = np.zeros(HORIZON)
    for t, mass, _ in arm.log:
        pi[t - 1] = mass
    hyps = arm._hyps
    return EpisodeRow(
        pi=pi,
        net=float(outcome.result.total_reward),
        prior_total=math.fsum(h.prior for h in hyps),
        n_hypotheses=len(hyps),
        n_dead=sum(int(h.dead) for h in hyps),
        n_from_llm=sum(int(h.from_llm) for h in hyps),
        consultations=sum(int(d.llm_called) for d in outcome.decisions),
    )


def run_path(args: tuple[str, float, int, tuple[Cell, ...]]) -> tuple[float, list[EpisodeRow]]:
    """Arm 1 and every listed cell on one path: arm 1's net and one row per cell."""
    law, cv, rep, cells = args
    instance = null_instance(cv, rep, law)
    base = _runner(instance).run(CappedBaseStockController(train_demand=instance.spec.train_demand))
    shared: dict[tuple, EpisodeRow] = {}
    rows = []
    for cell in cells:
        if cell.regime_free:
            key = (cell.tau, cell.firings, cell.lam, cell.family)
            if key not in shared:
                shared[key] = run_cell_episode(instance, cell)
            rows.append(shared[key])
        else:
            rows.append(run_cell_episode(instance, cell))
    return float(base.result.total_reward), rows


# ---------------------------------------------------------------------------
# accumulation
# ---------------------------------------------------------------------------


def _clopper_pearson_upper(k: int, n: int, level: float = 0.95) -> float:
    if n == 0 or k >= n:
        return 1.0
    return float(beta_dist.ppf(level, k + 1, n - k))


def _clopper_pearson_lower(k: int, n: int, level: float = 0.975) -> float:
    """One-sided lower confidence bound at ``level`` (0.975: the analogue of two SEs)."""
    if n == 0 or k <= 0:
        return 0.0
    return float(beta_dist.ppf(1.0 - level, k, n - k + 1))


def _mean_se(x: np.ndarray) -> tuple[float, float]:
    n = len(x)
    return float(x.mean()), (float(x.std(ddof=1) / math.sqrt(n)) if n > 1 else math.nan)


def _flag(est: float, se: float, bound: float) -> str | None:
    """``"clear"`` when a mean exceeds the bound by more than two standard errors, ``"point"``
    when it merely exceeds it, else ``None``."""
    if est <= bound + TOL:
        return None
    return "clear" if est - 2.0 * se > bound + TOL else "point"


def _flag_prob(p: float, lower: float, bound: float) -> str | None:
    """As :func:`_flag` for a proportion: ``"clear"`` when its one-sided 97.5% Clopper-Pearson
    lower bound exceeds the bound (exact at small counts, where a normal SE is not)."""
    if p <= bound + TOL:
        return None
    return "clear" if lower > bound + TOL else "point"


@dataclass
class CellAccumulator:
    """Per-replicate values of one cell (kept whole: the table needs means, SEs and tails)."""

    cell: Cell
    stratum: str
    pi: list[np.ndarray] = field(default_factory=list, repr=False)
    harm: list[float] = field(default_factory=list, repr=False)
    prior_total: set[float] = field(default_factory=set)
    n_hypotheses: set[int] = field(default_factory=set)
    n_from_llm: set[int] = field(default_factory=set)
    consultations: set[int] = field(default_factory=set)
    n_dead: int = 0

    def add(self, row: EpisodeRow, base_net: float) -> None:
        self.pi.append(row.pi)
        self.harm.append(base_net - row.net)
        self.prior_total.add(round(row.prior_total, 12))
        self.n_hypotheses.add(row.n_hypotheses)
        self.n_from_llm.add(row.n_from_llm)
        self.consultations.add(row.consultations)
        self.n_dead += row.n_dead

    def summary(self) -> dict:
        cell = self.cell
        pi = np.vstack(self.pi)
        n = pi.shape[0]
        if len(self.prior_total) != 1:
            raise RuntimeError(f"{cell.label()}: registered budget varies {self.prior_total}")
        a = next(iter(self.prior_total))
        if abs(a - budget(cell.firings)) > 1e-12:
            raise RuntimeError(f"{cell.label()}: registered budget {a} is not the schedule's")
        expected = {cell.firings if cell.lam < 1.0 else 0}
        if self.consultations != expected:
            raise RuntimeError(f"{cell.label()}: consultations {self.consultations} != {expected}")
        a_t = budget_path(cell)

        mean_t = pi.mean(axis=0)
        se_t = pi.std(axis=0, ddof=1) / math.sqrt(n) if n > 1 else np.full(HORIZON, math.nan)
        # Decision tau_1 + 1 (index tau_1) is the first build, where Pi = A_1 by construction (every
        # e-process is 1), so the per-decision check runs over the later decisions against A_t.
        after = np.arange(HORIZON) > cell.periods[0]
        excess = np.where(after, mean_t - a_t, -np.inf)
        t_star = int(excess.argmax())
        ratio_t = np.where(after, mean_t / np.where(a_t > 0, a_t, np.inf), -np.inf)
        sup = pi.max(axis=1)
        hit = pi >= STOP_LEVEL
        stop = np.where(hit.any(axis=1), hit.argmax(axis=1), HORIZON - 1)
        e_T, se_T = _mean_se(pi[:, -1])
        e_s, se_s = _mean_se(pi[np.arange(n), stop])
        e_sum, se_sum = _mean_se(pi.sum(axis=1))
        harm = np.asarray(self.harm)
        h_mean, h_se = _mean_se(harm)
        sup_rows = {}
        for c in THRESHOLDS:
            k = int((sup >= c).sum())
            p = k / n
            sup_rows[f"{c:g}"] = {
                "p": p,
                "se": math.sqrt(p * (1.0 - p) / n),
                "k": k,
                "ucb95": _clopper_pearson_upper(k, n),
                "lcb975": _clopper_pearson_lower(k, n),
                "bound": ville_bound(a, c),
            }
        sum_bound = float(a_t.sum())
        checks = {
            "E_pi_T": (e_T, se_T, a),
            "E_pi_sigma": (e_s, se_s, a),
            "max_t_E_pi_minus_A_t": (float(excess[t_star]), float(se_t[t_star]), 0.0),
            "E_sum_pi": (e_sum, se_sum, sum_bound),
        }
        flags = {k: f for k, (est, se, b) in checks.items() if (f := _flag(est, se, b))}
        for c, r in sup_rows.items():
            if f := _flag_prob(r["p"], r["lcb975"], r["bound"]):
                flags[f"P_sup_{c}"] = f
        return {
            **cell.key(),
            "stratum": self.stratum,
            "n": n,
            "A": a,
            "hypotheses_per_episode": sorted(self.n_hypotheses),
            "llm_hypotheses_per_episode": sorted(self.n_from_llm),
            "dead_hypotheses": self.n_dead,
            "E_pi_T": e_T,
            "E_pi_T_se": se_T,
            "E_pi_sigma": e_s,
            "E_pi_sigma_se": se_s,
            "max_t_E_pi_minus_A_t": float(excess[t_star]),
            "max_t_E_pi_minus_A_t_se": float(se_t[t_star]),
            "argmax_t": t_star + 1,
            "E_pi_at_argmax": float(mean_t[t_star]),
            "A_t_at_argmax": float(a_t[t_star]),
            "max_t_E_pi_over_A_t": float(ratio_t.max()),
            "E_pi_t": [float(x) for x in mean_t],
            "P_sup": sup_rows,
            "E_sum_pi": e_sum,
            "E_sum_pi_se": se_sum,
            "sum_bound": sum_bound,
            "harm_mean": h_mean,
            "harm_se": h_se,
            "harm_p99": float(np.quantile(harm, 0.99)),
            "harm_max": float(harm.max()),
            "frac_harm_positive": float((harm > 0).mean()),
            "above_bound": flags,
        }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def _pool_map(fn: Callable, jobs: Sequence, processes: int) -> Iterator:
    """``map`` in job order; a ``spawn`` pool when ``processes > 1``."""
    if processes <= 1:
        for job in jobs:
            yield fn(job)
        return
    chunk = max(1, len(jobs) // (32 * processes))
    with multiprocessing.get_context("spawn").Pool(processes) as pool:
        yield from pool.imap(fn, jobs, chunksize=chunk)


def run_mc(strata: Sequence[Stratum], *, processes: int = 1) -> dict:
    """Run every stratum; each ``(law, cv)`` path is shared by all the cells that use it."""
    for s in strata:
        if not 1 <= s.reps <= MAX_REPS:
            raise ValueError(f"{s.name}: reps must be in 1..{MAX_REPS}")
        if s.law not in LAWS or any(cv not in CVS for cv in s.cvs):
            raise ValueError(f"{s.name}: unknown law or cv")
    owner: dict[Cell, str] = {}
    paths: dict[tuple[str, float], list[tuple[Stratum, tuple[Cell, ...]]]] = {}
    for s in strata:
        for cv in s.cvs:
            cells = s.cells(cv)
            for c in cells:
                if c in owner:
                    raise ValueError(f"cell {c.label()} is in two strata")
                owner[c] = s.name
            paths.setdefault((s.law, cv), []).append((s, cells))
    jobs = []
    for (law, cv), groups in paths.items():
        for rep in range(max(s.reps for s, _ in groups)):
            cells = tuple(c for s, cs in groups if rep < s.reps for c in cs)
            jobs.append((law, cv, rep, cells))
    acc = {c: CellAccumulator(c, name) for c, name in owner.items()}
    base_nets: dict[tuple[str, float], list[float]] = {k: [] for k in paths}
    start = time.perf_counter()
    for job, (base_net, rows) in zip(jobs, _pool_map(run_path, jobs, processes), strict=True):
        law, cv, _, cells = job
        base_nets[(law, cv)].append(base_net)
        for cell, row in zip(cells, rows, strict=True):
            acc[cell].add(row, base_net)
    elapsed = time.perf_counter() - start
    return {
        "strata": [
            {
                "name": s.name,
                "law": s.law,
                "cvs": list(s.cvs),
                "priors": [{"lam": lam, "family": fam} for lam, fam in s.priors],
                "reps": s.reps,
            }
            for s in strata
        ],
        "n_paths": len(jobs),
        "n_cth_episodes": sum(len(j[3]) for j in jobs),
        "n_cells": len(acc),
        "arm1_net_mean": {
            f"{law}|cv={cv:g}": float(np.mean(v)) for (law, cv), v in base_nets.items()
        },
        "cells": [a.summary() for a in acc.values()],
        "elapsed_seconds": elapsed,
        "processes": processes,
    }


# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------


def _rounded(obj, digits: int = 6):
    if isinstance(obj, float):
        return round(obj, digits) if math.isfinite(obj) else obj
    if isinstance(obj, Mapping):
        return {str(k): _rounded(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_rounded(v, digits) for v in obj]
    if isinstance(obj, np.generic):
        return _rounded(obj.item(), digits)
    return obj


def config() -> dict:
    return {
        "alpha": ALPHA,
        "A_one_firing": budget(1),
        "A_two_firings": budget(2),
        "seed": f"{SEED_BASE} + {MAX_REPS} * cv_index + rep, cv_index over {list(CVS)}",
        "horizon": HORIZON,
        "promised_lead_time": PROMISED_LEAD_TIME,
        "profit": PROFIT,
        "holding": HOLDING,
        "order_cap": "inf",
        "demand": f"iid round-half-up N({MEAN:g}, (100 cv)^2) clipped at 0; 5 train rows after",
        "cvs": list(CVS),
        "taus": list(TAUS),
        "second_firing": f"tau + {SECOND_GAP}",
        "payloads": PAYLOADS,
        "lams": list(LAMS),
        "regimes": {
            "plug_in": "the frozen arm: demand e-process baseline = prefix mean and sd",
            "known": "the true mean 100 and sd 100 cv given to the demand e-processes",
        },
        "laws": {
            "deterministic": "every order arrives after exactly 2 periods",
            "registered": {
                "p_delay_0_4": list(REGISTERED_NULL_LAW.finite_delay_probabilities),
                "p_lost": REGISTERED_NULL_LAW.loss_probability,
                "p_pause_per_period": REGISTERED_NULL_LAW.pause_probability,
            },
        },
        "thresholds": list(THRESHOLDS),
        "stopping_times": ["T", f"min(first t with Pi_t >= {STOP_LEVEL:g}, T)"],
        "harm": (
            "arm 1 net reward minus the CTH arm's on the same path (positive: CTH lost); the "
            "negative of stage C's arm12_cth - arm1; the frozen arm's under plug_in only"
        ),
        "above_bound": (
            "point: estimate above the bound; clear: a mean above it by more than 2 MC SEs, or a "
            "P(sup) whose one-sided 97.5% Clopper-Pearson lower bound is above it"
        ),
        "per_decision_check": (
            "max over decisions t > tau_1 + 1 of E[Pi_t] - A_t (at t = tau_1 + 1, Pi_t = A_1 by "
            "construction)"
        ),
    }


def write_outputs(out_dir: Path, result: Mapping) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stable = {k: v for k, v in result.items() if k not in ("elapsed_seconds", "processes")}
    doc = _rounded({"config": config(), "result": stable, "exploratory": True})
    json_path = out_dir / "mc_exposure.json"
    md_path = out_dir / "mc_exposure.md"
    json_path.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(doc["result"]), encoding="utf-8")
    return json_path, md_path


# -- markdown ------------------------------------------------------------------


def _prior(row: Mapping) -> str:
    if row["family"] is None:
        return "lam=1 (content-free)"
    return f"lam={row['lam']:g} {row['family']}"


def _regime_free(r: Mapping) -> bool:
    """A ``lam = 0`` lead-time cell: no demand hypothesis, so both regimes are one computation."""
    return r["lam"] == 0.0 and r["family"] == "lead_time"


def _listed(cells: Sequence[Mapping]) -> list[Mapping]:
    """The cells the Markdown reports: a regime-free cell once, under ``known``."""
    return [r for r in cells if not (_regime_free(r) and r["regime"] == "plug_in")]


def _v(est: float, se: float, flag: str | None = None, digits: int = 4, sign: str = "") -> str:
    mark = {"clear": " **", "point": " *"}.get(flag or "", "")
    return f"{est:{sign}.{digits}f} ({se:.{digits}f}){mark}"


def _cell_line(r: Mapping) -> str:
    f = r["above_bound"]
    sups = [
        _v(r["P_sup"][f"{c:g}"]["p"], r["P_sup"][f"{c:g}"]["se"], f.get(f"P_sup_{c:g}"), 3)
        for c in THRESHOLDS
    ]
    regime = "either" if _regime_free(r) else r["regime"]
    excess = _v(
        r["max_t_E_pi_minus_A_t"],
        r["max_t_E_pi_minus_A_t_se"],
        f.get("max_t_E_pi_minus_A_t"),
        sign="+",
    )
    return (
        f"| {regime} | {r['cv']:g} | {r['tau']} | {r['firings']} | {_prior(r)} | "
        f"{r['n']} | {r['A']:.4f} | {_v(r['E_pi_T'], r['E_pi_T_se'], f.get('E_pi_T'))} | "
        f"{_v(r['E_pi_sigma'], r['E_pi_sigma_se'], f.get('E_pi_sigma'))} | "
        f"{excess} @{r['argmax_t']} | "
        + " | ".join(sups)
        + f" | {_v(r['E_sum_pi'], r['E_sum_pi_se'], f.get('E_sum_pi'), 3)} "
        f"[{r['sum_bound']:.3f}] | {r['harm_mean']:+.1f} ({r['harm_se']:.1f}) |"
    )


_CELL_HEADER = [
    "| regime | CV | tau | fir. | prior | n | A | E[Pi_T] | E[Pi_sigma] | "
    "max_t (E[Pi_t] - A_t) @t | P(sup >= 0.1) | P(sup >= 0.25) | P(sup >= 0.5) | "
    "E[sum Pi] [bound] | harm |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
]


def _order(r: Mapping) -> tuple:
    prior_rank = PRIORS.index((r["lam"], r["family"]))
    return (REGIMES.index(r["regime"]), r["firings"], r["cv"], r["tau"], prior_rank)


def _ratio(r: Mapping, metric: str) -> float:
    if metric.startswith("P_sup_"):
        c = metric.removeprefix("P_sup_")
        return r["P_sup"][c]["p"] / r["P_sup"][c]["bound"]
    if metric == "E_sum_pi":
        return r["E_sum_pi"] / r["sum_bound"]
    if metric == "max_t_E_pi_over_A_t":
        return r[metric]
    return r[metric] / r["A"]


_RATIO_METRICS = (
    "E_pi_sigma",
    "max_t_E_pi_over_A_t",
    "P_sup_0.1",
    "P_sup_0.25",
    "P_sup_0.5",
    "E_sum_pi",
)
N_CHECKS = 4 + len(THRESHOLDS)
"""Bound checks per cell: E[Pi_T], E[Pi_sigma], max_t (E[Pi_t] - A_t), E[sum Pi], P(sup) x 3."""
CHANCE_RATE = 0.025
"""Chance rate of a clear flag for one check whose true value sits exactly at its bound
(two-SE normal: about 0.023; one-sided 97.5% Clopper-Pearson: at most 0.025)."""


def _headline(cells: Sequence[Mapping]) -> list[str]:
    lines = [
        "| law | regime | prior | cells | worst E[Pi_sigma] / A | worst max_t E[Pi_t] / A_t | "
        "worst P(sup >= 0.5) / bound | worst E[sum Pi] / bound | cells above a bound "
        "(point / clear) | mean harm |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    listed = _listed(cells)
    for law in LAWS:
        for regime in REGIMES:
            for lam, fam in PRIORS:
                sel = [
                    r
                    for r in listed
                    if r["law"] == law
                    and r["regime"] == regime
                    and r["lam"] == lam
                    and r["family"] == fam
                ]
                if not sel:
                    continue
                worst = {m: max(sel, key=lambda r, m=m: _ratio(r, m)) for m in _RATIO_METRICS}
                n_point = sum(1 for r in sel if r["above_bound"])
                n_clear = len(_clear(sel))
                harm = float(np.mean([r["harm_mean"] for r in sel]))

                def w(m: str, worst=worst) -> str:
                    r = worst[m]
                    return f"{_ratio(r, m):.2f} (cv {r['cv']:g}, tau {r['tau']}, n {r['firings']})"

                shown = "either" if _regime_free(sel[0]) else regime
                lines.append(
                    f"| {law} | {shown} | {_prior({'lam': lam, 'family': fam})} | {len(sel)} | "
                    f"{w('E_pi_sigma')} | {w('max_t_E_pi_over_A_t')} | {w('P_sup_0.5')} | "
                    f"{w('E_sum_pi')} | {n_point} / {n_clear} | {harm:+.1f} |"
                )
    return lines


def _is_exact(r: Mapping) -> bool:
    """Every e-process of the cell is a test martingale for the simulated law: the known demand
    baseline, and either the registered delay law or no lead-time hypothesis. Regime-free cells
    are reported on their own."""
    if _regime_free(r):
        return False
    demand_only = r["lam"] == 0.0 and r["family"] in ("demand_up", "demand_down")
    return r["regime"] == "known" and (r["law"] == "registered" or demand_only)


def _clear(rows: Sequence[Mapping]) -> list[Mapping]:
    return [r for r in rows if "clear" in r["above_bound"].values()]


def _firings(r: Mapping) -> str:
    return "one firing" if r["firings"] == 1 else "two firings"


def _where(r: Mapping) -> str:
    return f"{_prior(r)}, {r['law']}, CV {r['cv']:g}, tau {r['tau']}, {_firings(r)}"


def _worst_text(rows: Sequence[Mapping]) -> str:
    ws = max(rows, key=lambda r: _ratio(r, "E_pi_sigma"))
    wm = max(rows, key=lambda r: r["max_t_E_pi_minus_A_t"])
    wp = max(rows, key=lambda r: _ratio(r, "P_sup_0.5"))
    ps = wp["P_sup"]["0.5"]
    return (
        f"largest E[Pi_sigma] {ws['E_pi_sigma']:.4f} ({ws['E_pi_sigma_se']:.4f}) against "
        f"A = {ws['A']:.4f} ({_where(ws)}); largest max_t (E[Pi_t] - A_t) over t > tau_1 + 1 "
        f"{wm['max_t_E_pi_minus_A_t']:+.4f} ({wm['max_t_E_pi_minus_A_t_se']:.4f}), E[Pi_t] "
        f"{wm['E_pi_at_argmax']:.4f} against A_t = {wm['A_t_at_argmax']:.4f} at t = "
        f"{wm['argmax_t']} ({_where(wm)}); largest P(sup Pi >= 0.5) {ps['p']:.3f} "
        f"(SE {ps['se']:.3f}, 97.5% lower bound {ps['lcb975']:.3f}) against {ps['bound']:.4f} "
        f"({_where(wp)})"
    )


def _count_text(rows: Sequence[Mapping]) -> str:
    clear = _clear(rows)
    one = [r for r in rows if r["above_bound"]]
    text = (
        f"{len(one)} of {len(rows)} cells have an estimate above a bound, {len(clear)} clearly "
        "above one"
    )
    if clear:
        metrics: dict[str, int] = {}
        for r in clear:
            for m, fl in r["above_bound"].items():
                if fl == "clear":
                    metrics[m] = metrics.get(m, 0) + 1
        text += " (" + ", ".join(f"{m} in {k}" for m, k in sorted(metrics.items())) + ")"
    return text


def _breakdown(rows: Sequence[Mapping], key: str, values: Sequence) -> str:
    clear = _clear(rows)
    parts = []
    for v in values:
        n = sum(1 for r in rows if r[key] == v)
        if n:
            parts.append(f"{v:g}: {sum(1 for r in clear if r[key] == v)}/{n}")
    return ", ".join(parts)


def _reading(cells: Sequence[Mapping]) -> list[str]:
    """Plain statements computed from the cells; no claim beyond them. Each cell enters exactly
    one of the first four groups."""
    out = []
    listed = _listed(cells)
    exact = [r for r in listed if _is_exact(r)]
    if exact:
        out.append(
            "- **Exact nulls** (known demand baseline, and the registered delay law or no "
            f"lead-time hypothesis; the exposure theorem's premise holds): {_count_text(exact)}; "
            f"{_worst_text(exact)}."
        )
    plug = [r for r in listed if r["regime"] == "plug_in"]
    for law in LAWS:
        rows = [r for r in plug if r["law"] == law]
        if not rows:
            continue
        out.append(
            f"- **Plug-in null, {law} delays** (the arm as frozen; lam=0 lead_time cells, which "
            f"have no demand hypothesis, are excluded): {_count_text(rows)}; "
            f"{_worst_text(rows)}. Cells clearly above a bound, by tau: "
            f"{_breakdown(rows, 'tau', TAUS)}; by CV: {_breakdown(rows, 'cv', CVS)}; by lam: "
            f"{_breakdown(rows, 'lam', LAMS)}."
        )
    rest = [
        r for r in listed if r["regime"] == "known" and not _regime_free(r) and not _is_exact(r)
    ]
    if rest:
        out.append(
            "- **Known demand baseline, deterministic delays, with a lead-time hypothesis** "
            "(deterministic delays are not the registered arrival null the lead-time e-process "
            f"tests against, so the premise fails for that hypothesis): {_count_text(rest)}; "
            f"{_worst_text(rest)}."
        )
    lt = [r for r in listed if _regime_free(r)]
    for law in LAWS:
        rows = [r for r in lt if r["law"] == law]
        if rows:
            premise = (
                "the premise holds"
                if law == "registered"
                else "deterministic delays are outside the arrival null, so the premise fails"
            )
            w = max(rows, key=lambda r: r["max_t_E_pi_minus_A_t"])
            out.append(
                f"- **Lead-time hypothesis alone, {law} delays** (lam=0, lead_time; no demand "
                f"hypothesis, so the two regimes coincide; {premise}): largest max_t "
                f"(E[Pi_t] - A_t) over t > tau_1 + 1 = {w['max_t_E_pi_minus_A_t']:+.4f} "
                f"({_where(w)}); {_count_text(rows)}."
            )
    main = [r for r in listed if r["stratum"] == "main"]
    if main:
        parts = []
        for regime in REGIMES:
            for lam, fam in MAIN_PRIORS:
                rows = [
                    r
                    for r in main
                    if r["regime"] == regime and r["lam"] == lam and r["family"] == fam
                ]
                if rows:
                    h = [r["harm_mean"] for r in rows]
                    parts.append(
                        f"{regime} {_prior({'lam': lam, 'family': fam})}: mean {np.mean(h):+.1f}, "
                        f"cells {min(h):+.1f} to {max(h):+.1f}"
                    )
        out.append(
            "- **Realized net harm against arm 1** (main table, per episode; arm 1 minus the arm, "
            "so positive means the arm lost, the opposite sign to stage C's arm12_cth - arm1; "
            "only plug_in is the frozen arm, known is a counterfactual arm): "
            + "; ".join(parts)
            + "."
        )
    plug_clear = _clear(plug)
    if exact and plug_clear and not _clear(exact):
        out.append(
            "- The two regimes differ only in the baseline handed to the demand e-processes, on "
            "identical paths and payloads. Where every e-process is exact no cell is clearly "
            "above a bound; the plug-in cells that are clearly above one are the ones to "
            "attribute to the prefix estimate of the demand baseline, not to the language payload."
        )
    n_tests = N_CHECKS * len(listed)
    out.append(
        f"- Multiplicity: the {len(listed)} listed cells carry {N_CHECKS} bound checks each, "
        f"{n_tests} in all. If every true value sat exactly at its bound, about "
        f"{CHANCE_RATE:.1%} of them, {CHANCE_RATE * n_tests:.1f}, would be clearly above by "
        "chance; fewer where the true value is below its bound, as it is for most E[Pi_T] and "
        "E[sum Pi] checks. The max_t (E[Pi_t] - A_t) check is itself a maximum over decisions, "
        "so its chance rate is higher. The checks within a cell, and the cells of one path, are "
        "correlated."
    )
    out.append(
        "- Selection: every 'largest' value above and every 'worst' ratio in the next table is a "
        "maximum over cells, and max_t (E[Pi_t] - A_t) is also a maximum over up to "
        f"{HORIZON - TAUS[0] - 1} decisions, so all of them are biased upward by selection. A "
        "single cell's E[Pi_sigma] or P(sup) estimate is unbiased, but the cell reported as the "
        "largest is not a random draw."
    )
    return out


def render_markdown(result: Mapping) -> str:
    cells = result["cells"]
    lines = [
        "# Certify-then-hedge: null exposure Monte Carlo (exposure theorem)",
        "",
        "Exploratory and offline: synthetic null episodes, the frozen `CertifyThenHedgeArm` "
        "driven by the real episode runner, a scripted trigger, and a fixed false payload "
        "injected through the arm's replay seam (no model call). Written by "
        "`python -m analysis.commitment.mc_exposure`; every number below is in "
        "`mc_exposure.json`.",
        "",
        "## Design",
        "",
        f"- Paths: horizon {HORIZON}, promised lead time {PROMISED_LEAD_TIME}, p = {PROFIT:g}, "
        f"h = {HOLDING:g}, no order cap; demand and {TRAIN_ROWS} train rows iid "
        f"round(N({MEAN:g}, (100 CV)^2)) clipped at 0, CV in "
        f"{{{', '.join(f'{c:g}' for c in CVS)}}}. Delays deterministic (2) or, as a sensitivity, "
        "the registered arrival null (delays 0-4 with probabilities "
        f"{', '.join(f'{p:g}' for p in REGISTERED_NULL_LAW.finite_delay_probabilities)}, loss "
        f"{REGISTERED_NULL_LAW.loss_probability:g}, pause {REGISTERED_NULL_LAW.pause_probability:g} "
        "per period).",
        f"- Firings: scripted, one at tau in {{{', '.join(str(t) for t in TAUS)}}}, or two at tau "
        f"and tau + {SECOND_GAP}. Each firing carries the same fixed false payload (one family, "
        f"onset window ({WINDOW[0]}, {WINDOW[1]}), not chosen from the path). lam = 1 is "
        "content-free.",
        "- Scope: CV 0.25 with deterministic delays is the cell matched to the stage C null twins "
        "(mean 100, sd 25, deterministic lead times, false alerts at period 10). A path-dependent "
        "payload, detector-chosen firing times and a promised lead other than 2 are not tested; "
        "the other CVs and the registered delay law are extensions.",
        "- Regimes: plug_in is the arm as frozen (demand e-process baseline estimated from the "
        "prefix before the firing); known gives the demand e-processes the true mean and sd. "
        "lam=0 lead_time cells have no demand hypothesis, so both regimes are one computation; "
        "they are listed once, as regime 'either'.",
        "- Seeds: "
        f"{SEED_BASE} + {MAX_REPS} * cv_index + rep; all cells of a CV share the path, and arm 1 "
        "runs once per path. Harm = arm 1 net reward minus the arm's (positive: the arm lost), "
        "per episode: the negative of stage C's null-safety contrast.",
        "- Strata and replicates: "
        + "; ".join(
            f"{s['name']} ({s['law']}, CV {', '.join(f'{c:g}' for c in s['cvs'])}): "
            f"{s['reps']} paths per CV"
            for s in result["strata"]
        )
        + ". The lead-time e-process's exact forward filter dominates the cost, so the "
        "secondary strata use fewer paths.",
        f"- Totals: {result['n_paths']} paths, {result['n_cth_episodes']} arm episodes, "
        f"{result['n_cells']} cells ({len(_listed(cells))} listed).",
        "",
        "## Bounds",
        "",
        "A is the prior budget the arm registered, read from its hypotheses. E0[Pi_sigma] <= A "
        "for every stopping time; E0[Pi_t] <= A_t, the budget live at decision t; "
        "P0(sup_t Pi_t >= c) <= A (1 - c) / (c (1 - A)); E0[sum_t Pi_t] <= sum_t A_t. At the "
        "first build, t = tau_1 + 1, Pi_t = A_1 by construction, so the per-decision check runs "
        "over t > tau_1 + 1.",
        "",
        "| firings | A | P bound, c = 0.1 | c = 0.25 | c = 0.5 |",
        "|---|---|---|---|---|",
    ]
    for n in FIRINGS:
        a = budget(n)
        lines.append(
            f"| {n} | {a:.4f} | "
            + " | ".join(f"{ville_bound(a, c):.4f}" for c in THRESHOLDS)
            + " |"
        )
    lines += [
        "",
        "## Reading",
        "",
        *_reading(cells),
        "",
        "## Worst cell per law, regime and prior",
        "",
        "Ratios of estimate to bound (above 1: the estimate exceeds the bound), with the cell "
        "attaining each; the per-decision ratio is the largest E[Pi_t] / A_t over t > tau_1 + 1. "
        "Cells above a bound: any check's estimate above its bound / clearly above it (a mean by "
        "more than two Monte Carlo SEs, a P(sup) with its one-sided 97.5% Clopper-Pearson lower "
        "bound above it).",
        "",
        *_headline(cells),
        "",
    ]
    sections = (
        ("main", "Main table: deterministic delays, demand_up payload and content-free"),
        ("other_families", "Other families: deterministic delays, lead_time and demand_down"),
        ("registered_law", "Sensitivity: registered delay law"),
    )
    listed = _listed(cells)
    for name, title in sections:
        rows = sorted((r for r in listed if r["stratum"] == name), key=_order)
        if not rows:
            continue
        lines += [
            f"## {title}",
            "",
            "Estimate (Monte Carlo SE). `*`: estimate above its bound; `**`: clearly above it (a "
            "mean by more than two SEs; a P(sup) with its one-sided 97.5% Clopper-Pearson lower "
            "bound above it). sigma = min(first t with Pi_t >= 0.1, T). max_t (E[Pi_t] - A_t) "
            "runs over t > tau_1 + 1; @t is the decision attaining it. harm: mean (SE) per "
            "episode, arm 1 minus the arm.",
            "",
            *_CELL_HEADER,
            *(_cell_line(r) for r in rows),
            "",
        ]
    arm1 = result["arm1_net_mean"]
    lines += [
        "Arm 1 mean net reward per path: "
        + "; ".join(f"{k} {v:.1f}" for k, v in sorted(arm1.items()))
        + ".",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.mc_exposure")
    ap.add_argument("--reps", type=int, default=1000, help="paths per CV, main table")
    ap.add_argument("--other-reps", type=int, default=200, help="paths per CV, other families")
    ap.add_argument(
        "--sensitivity-reps", type=int, default=200, help="paths per CV, registered law (0: skip)"
    )
    ap.add_argument("--cvs", nargs="+", type=float, default=list(CVS))
    ap.add_argument("--sensitivity-cvs", nargs="+", type=float, default=list(SENSITIVITY_CVS))
    ap.add_argument("--processes", type=int, default=1)
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "out")
    ap.add_argument(
        "--render-only",
        action="store_true",
        help="rewrite mc_exposure.md from the mc_exposure.json in --out-dir; run nothing",
    )
    args = ap.parse_args(argv)
    if args.render_only:
        doc = json.loads((args.out_dir / "mc_exposure.json").read_text(encoding="utf-8"))
        md_path = args.out_dir / "mc_exposure.md"
        md_path.write_text(render_markdown(doc["result"]), encoding="utf-8")
        print(md_path)
        return 0
    strata = default_strata(
        args.reps,
        args.other_reps,
        args.sensitivity_reps,
        cvs=args.cvs,
        sensitivity_cvs=args.sensitivity_cvs,
    )
    result = run_mc(strata, processes=args.processes)
    json_path, md_path = write_outputs(args.out_dir, result)
    print(
        f"{result['n_cth_episodes']} arm episodes on {result['n_paths']} paths in "
        f"{result['elapsed_seconds']:.0f} s ({args.processes} processes)"
    )
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
