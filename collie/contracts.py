"""Frozen core contracts — the single shared vocabulary for all eight branches.

Owned by branch A (collie-platform, P1). **Frozen at Gate 1**; later changes require a dated
entry in ``prereg/deviations.md``.

Three invariants are enforced by the types themselves rather than by convention:

1. ``PeriodObservation`` exposes only what is legitimately available at decision time. It has
   no reference to :class:`HiddenIncident`, and the object-graph walk in
   :func:`find_hidden_state` proves that at runtime.
2. ``ShockSpec`` is immutable once validated, so a hypothesis frozen at stopping time
   ``tau_j`` cannot be edited by the evidence that later tests it.
3. In-transit inventory is a **scalar with no shipment ages**, matching the audited benchmark
   contract (``docs/env_contract.md`` §4). Any age-resolved view is an imputation and is
   marked as such.

Vocabulary that branch D extends (registered onset windows, signatures, legal family-signature
pairings) lives in ``collie/spec/registry.py``; the *types* live here so no branch has to
import branch D to name a ``ShockSpec``.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    # enums
    "AlertKind",
    # observable
    "AlertMessage",
    "AnalysisClass",
    # outputs
    "CallLog",
    "ControlConfig",
    # protocols
    "Controller",
    "Decision",
    "Direction",
    "DurationBin",
    "EpisodeResult",
    "EpisodeSpec",
    # hidden
    "HiddenAlertSpec",
    "HiddenIncident",
    # isolation
    "HiddenStateLeak",
    "InformationCondition",
    "LLMClient",
    "LifecycleState",
    "MagnitudeBin",
    "ObservationMode",
    "ParseOutcome",
    "PeriodObservation",
    "Persistence",
    "RunRecord",
    "ShockFamily",
    # the bounded semantic commitment
    "ShockSpec",
    "Split",
    "SupplyEffect",
    "SupplyEffectKind",
    "SupplyProcess",
    "SupplyRealization",
    "TargetStream",
    "Trigger",
    "assert_no_hidden_state",
    "find_hidden_state",
]


# ---------------------------------------------------------------------------
# enums — the closed vocabularies
# ---------------------------------------------------------------------------


class ShockFamily(StrEnum):
    """The six controlled families, plus ``no_change`` abstention and ``compound``.

    Exactly the vocabulary in doc 3.5 section 4.2. ``no_change`` is a first-class output, not
    a failure code: the model must be able to decline rather than invent a shock.
    """

    NO_CHANGE = "no_change"
    DEMAND_LEVEL = "demand_level"
    TEMPORARY_PULSE = "temporary_pulse"
    LEAD_TIME_SHIFT = "lead_time_shift"
    SHIPMENT_LOSS = "shipment_loss"
    TRANSIT_PAUSE = "transit_pause"
    COMPOUND = "compound"


class TargetStream(StrEnum):
    NONE = "none"
    DEMAND = "demand"
    ARRIVAL = "arrival"
    BOTH = "both"


class Direction(StrEnum):
    NONE = "none"
    DEMAND_UP = "demand_up"
    DEMAND_DOWN = "demand_down"
    ARRIVAL_DELAYED = "arrival_delayed"
    ARRIVAL_INTERRUPTED = "arrival_interrupted"
    MIXED = "mixed"


class MagnitudeBin(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Persistence(StrEnum):
    NONE = "none"
    TRANSIENT = "transient"
    PERSISTENT = "persistent"
    UNKNOWN = "unknown"


class DurationBin(StrEnum):
    NONE = "none"
    SHORT = "1_3"
    MEDIUM = "4_8"
    LONGER = "longer"


class LifecycleState(StrEnum):
    """A hypothesis only influences orders while ``ACTIVE``; baseline OR runs otherwise."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    REFUTED = "refuted"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ParseOutcome(StrEnum):
    """Distinguishes model *capability* from model *reliability*.

    ``ACCEPTED`` with ``shock_family == NO_CHANGE`` is a deliberate abstention and feeds the
    abstention precision/recall metrics. ``FALLBACK`` is a formatting failure and feeds the
    reliability metrics. Collapsing the two would confuse two different phenomena.
    """

    ACCEPTED = "accepted"
    ACCEPTED_AFTER_REPAIR = "accepted_after_repair"
    FALLBACK = "fallback"


class SupplyEffectKind(StrEnum):
    NONE = "none"
    LEAD_TIME_SHIFT = "lead_time_shift"
    SHIPMENT_LOSS = "shipment_loss"
    TRANSIT_PAUSE = "transit_pause"


class ObservationMode(StrEnum):
    """``UNCENSORED`` is the headline setting: the benchmark reports true demand even during a
    stockout (``docs/env_contract.md`` §4). ``CENSORED`` exposes sales and availability only,
    which is a genuinely different observation model, not a relabeling."""

    UNCENSORED = "uncensored_demand"
    CENSORED = "censored_sales"


class AlertKind(StrEnum):
    ACCURATE = "accurate"
    OVERSTATED = "overstated"
    AMBIGUOUS = "ambiguous"
    DISTRACTOR = "distractor"
    NEUTRAL = "neutral"


class InformationCondition(StrEnum):
    NO_ALERT = "no_alert"
    EARLY_ACCURATE = "early_accurate"
    LATE_ACCURATE = "late_accurate"
    UNRELIABLE = "unreliable"


class Split(StrEnum):
    DEV = "dev"
    CAL = "cal"
    TEST = "test"
    NULL_AUDIT = "null_audit"


class AnalysisClass(StrEnum):
    """Stamped on every output record. The renderer refuses to present anything as
    ``CONFIRMATORY`` unless its identifier appears in the frozen preregistration."""

    CONFIRMATORY = "confirmatory"
    EXPLORATORY = "exploratory"


# ---------------------------------------------------------------------------
# observable state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlertMessage:
    """An operational note visible to the policy.

    Deliberately does **not** carry ``template_id`` or the canonical ``HiddenAlertSpec``.
    Template identity is needed for language-level clustering in analysis, so it travels on
    :class:`RunRecord` instead; putting it here would let a policy key on it.
    """

    alert_id: str
    period: int
    text: str


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    """Static description of one episode, known before it starts."""

    episode_id: str
    item_id: str
    horizon: int
    promised_lead_time: int
    profit_per_unit: float
    holding_cost_per_unit: float
    order_cap: float
    """Our cap. The benchmark imposes none (``docs/env_contract.md`` §2.3), so this is
    registered in ``prereg/prereg_v1.yaml`` and must be labelled as ours wherever it matters."""
    observation_mode: ObservationMode = ObservationMode.UNCENSORED
    product_text: str | None = None
    split: Split | None = None
    family: ShockFamily | None = None
    independent_unit_id: str | None = None
    """The seed-family unit. Branch H aggregates over this; the four information conditions of
    one seed are paired replays of a single independent unit, never four samples."""
    information_condition: InformationCondition | None = None
    source: str = "official"
    train_demand: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class PeriodObservation:
    """Everything a controller may see at period ``t``, and nothing else.

    Mirrors the audited signature of ``InventoryPolicy.get_order`` plus the alert channel.
    ``in_transit_total`` is a scalar by benchmark contract, and at decision time it still
    includes units scheduled to land this very period, because the arrival pop happens after
    the decision.
    """

    period: int
    date: str
    on_hand: float
    in_transit_total: float
    prev_order: float
    prev_arrivals: float
    profit_per_unit: float
    holding_cost_per_unit: float
    promised_lead_time: int
    prev_demand: float | None = None
    prev_sales: float | None = None
    prev_availability: bool | None = None
    product_text: str | None = None
    alert: AlertMessage | None = None

    def __post_init__(self) -> None:
        if self.prev_demand is None and self.prev_sales is None and self.period > 1:
            raise ValueError(
                f"period {self.period}: an observation must carry either prev_demand "
                "(uncensored mode) or prev_sales (censored mode)"
            )


# ---------------------------------------------------------------------------
# the bounded semantic commitment
# ---------------------------------------------------------------------------


class ShockSpec(BaseModel):
    """One typed, frozen, prospectively testable claim about the exogenous process.

    ``extra="forbid"`` and ``frozen=True`` deliver the two properties the validity argument
    rests on: the model cannot smuggle in a falsifier, threshold, likelihood, order equation,
    or code, and the object cannot be edited after ``tau_j``.

    Branch D (``collie/spec/``) owns the registry of legal ``onset_window`` intervals,
    ``prospective_signature`` identifiers, and legal family-signature pairings, and validates
    against it. This class enforces only what is universal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    target_stream: TargetStream
    shock_family: ShockFamily
    direction: Direction
    onset_window: tuple[int, int] | None
    magnitude_bin: MagnitudeBin | None
    persistence: Persistence
    duration_bin: DurationBin
    evidence_refs: tuple[str, ...]
    prospective_signature: str

    # Provenance. Set by the system after the model's payload validates; the model itself is
    # never permitted to supply these (branch D validates the payload with a sub-model).
    tau_j: int
    proposal_index: int
    model_id: str
    decoding_hash: str
    prompt_hash: str

    @field_validator("onset_window")
    @classmethod
    def _onset_window_ordered(cls, v: tuple[int, int] | None) -> tuple[int, int] | None:
        if v is not None and v[0] > v[1]:
            raise ValueError(f"onset_window must be ordered (lo <= hi), got {v}")
        return v

    @field_validator("proposal_index")
    @classmethod
    def _proposal_index_is_one_based(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"proposal_index is 1-based (alpha_j = alpha * 2**-j), got {v}")
        return v

    @model_validator(mode="before")
    @classmethod
    def _normalise_abstention_spelling(cls, data: Any) -> Any:
        """Accept ``"none"`` where JSON ``null`` was meant, for an abstention only.

        A model that writes ``magnitude_bin: "none"`` instead of ``null`` alongside
        ``shock_family: "no_change"`` is being cooperative, not wrong. Normalising here (before
        construction) keeps the post-validation invariant absolute — magnitude and onset are
        ``None`` for an abstention, always — without mutating a frozen instance.
        """
        if isinstance(data, Mapping) and data.get("shock_family") in (
            ShockFamily.NO_CHANGE,
            ShockFamily.NO_CHANGE.value,
        ):
            data = dict(data)
            for key in ("magnitude_bin", "onset_window"):
                if data.get(key) in (MagnitudeBin.NONE, MagnitudeBin.NONE.value):
                    data[key] = None
        return data

    @model_validator(mode="after")
    def _abstention_is_well_formed(self) -> ShockSpec:
        """``no_change`` must be a complete, self-consistent abstention."""
        if self.shock_family is ShockFamily.NO_CHANGE:
            if self.target_stream is not TargetStream.NONE:
                raise ValueError("no_change requires target_stream='none'")
            if self.direction is not Direction.NONE:
                raise ValueError("no_change requires direction='none'")
            if self.onset_window is not None:
                raise ValueError("no_change requires a null onset_window")
            if self.magnitude_bin is not None:
                raise ValueError("no_change requires a null magnitude_bin")
        else:
            if self.onset_window is None:
                raise ValueError(f"{self.shock_family} requires an onset_window")
            if self.magnitude_bin in (None, MagnitudeBin.NONE):
                raise ValueError(f"{self.shock_family} requires a non-none magnitude_bin")
            if self.target_stream is TargetStream.NONE:
                raise ValueError(f"{self.shock_family} requires a target_stream")
        return self

    @property
    def is_abstention(self) -> bool:
        return self.shock_family is ShockFamily.NO_CHANGE


# ---------------------------------------------------------------------------
# hidden state — never reachable from a policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SupplyEffect:
    kind: SupplyEffectKind
    start_period: int
    length: int
    disrupted_lead_time: int | None = None


@dataclass(frozen=True, slots=True)
class HiddenAlertSpec:
    """Canonical machine-readable structure behind an alert message.

    Records what is *actually* happening, even when the message overstates or is ambiguous, so
    downstream metrics compare against truth. Feeding this straight into the compiler is the
    parsing upper bound; no other arm may read it.
    """

    family: ShockFamily
    target_stream: TargetStream
    direction: Direction
    onset_window: tuple[int, int] | None
    magnitude_bin: MagnitudeBin | None
    persistence: Persistence
    duration_bin: DurationBin
    prospective_signature: str
    kind: AlertKind


@dataclass(frozen=True, slots=True)
class HiddenIncident:
    """Ground truth for a shocked episode. **Never** reachable from a policy.

    Enforced by :func:`find_hidden_state` at runtime and by a static import-boundary test.
    The oracle arm and the evaluation code are the only permitted readers.
    """

    family: ShockFamily
    onset_period: int
    magnitude: float
    duration: int
    conditional_independence: bool
    """``False`` for the compound family, where one incident drives both streams. Branch F reads
    this to choose between a registered joint likelihood and explicit alpha splitting; it must
    never multiply marginal ratios for convenience."""
    supply_effect: SupplyEffect | None = None
    alert_spec: HiddenAlertSpec | None = None
    baseline_twin_id: str | None = None
    seed: int | None = None
    held_out_combo: bool = False


@dataclass(frozen=True, slots=True)
class SupplyRealization:
    """Exogenous supply path. Feeds the runner's ``SupplyProcess``, never the observation."""

    lead_times: tuple[float, ...]
    """Per-period actual lead time; ``math.inf`` encodes a lost shipment, matching the
    benchmark's own ``lead_time = inf`` convention."""
    pause_active: tuple[bool, ...] = ()

    def __post_init__(self) -> None:
        if self.pause_active and len(self.pause_active) != len(self.lead_times):
            raise ValueError("pause_active must align with lead_times")

    @property
    def n_lost(self) -> int:
        return sum(1 for lt in self.lead_times if math.isinf(lt))


# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControlConfig:
    """What the compiler produces and the controller consumes. Branch E owns the 72-point grid."""

    m: float
    l_eff: int
    gamma: float
    predictive_model: str
    """The key that also selects branch F's registered verifier construction. One key, two
    consumers: control acts on it, verification tests it."""


@dataclass(frozen=True, slots=True)
class Decision:
    """One order plus the provenance the accountability story needs."""

    period: int
    order_quantity: float
    arm_id: str
    llm_called: bool = False
    active_spec_id: str | None = None
    control_config: ControlConfig | None = None
    lifecycle_state: LifecycleState | None = None
    triggered: bool = False


@dataclass(frozen=True, slots=True)
class CallLog:
    """One record per *attempted* call, including repairs, rejections, and cache hits.

    ``charged`` vs ``physical`` is what keeps the compute frontier honest: arms 8/9/10 share one
    physical proposal call and each carry a charged copy.
    """

    call_id: str
    arm_id: str
    episode_id: str
    period: int
    model_id: str
    prompt_hash: str
    decoding_hash: str
    attempt_index: int
    outcome: ParseOutcome | None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    usd_cost: float = 0.0
    cache_hit: bool = False
    physical: bool = True
    """``True`` when this arm caused the provider request; ``False`` when it is a charged copy
    of a call another arm physically made."""


@dataclass(frozen=True, slots=True)
class RunRecord:
    """One period of one episode under one arm. The atom of every reported number."""

    episode_id: str
    arm_id: str
    period: int
    date: str
    on_hand_start: float
    in_transit_start: float
    order_quantity: float
    arrivals: float
    demand: float
    units_sold: float
    lost_sales: float
    on_hand_end: float
    period_profit: float
    period_holding: float
    triggered: bool = False
    llm_called: bool = False
    lifecycle_state: LifecycleState | None = None
    active_spec_id: str | None = None
    control_config: ControlConfig | None = None
    template_id: str | None = None
    """Analysis-side only. Language claims bootstrap jointly over seed and template, so this
    must survive to the records even though the policy never sees it."""


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    """Episode aggregate, computed exactly as the audited evaluator computes it."""

    episode_id: str
    arm_id: str
    total_profit: float
    total_holding_cost: float
    total_reward: float
    total_demand: float
    total_sold: float
    total_lost_sales: float
    perfect_foresight: float
    normalized_reward: float
    records: tuple[RunRecord, ...] = ()
    calls: tuple[CallLog, ...] = ()
    independent_unit_id: str | None = None
    split: Split | None = None
    family: ShockFamily | None = None
    information_condition: InformationCondition | None = None
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY

    @property
    def fill_rate(self) -> float:
        return self.total_sold / self.total_demand if self.total_demand > 0 else 1.0


# ---------------------------------------------------------------------------
# protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class Controller(Protocol):
    """Every arm is a controller. The runner never learns which arm it is executing."""

    arm_id: str

    def reset(self) -> None: ...

    def order(self, obs: PeriodObservation) -> Decision: ...


@runtime_checkable
class SupplyProcess(Protocol):
    """Owns lead time, loss, and transit pause. The runner delegates all supply physics here."""

    def dispatch(self, period: int, qty: float) -> None: ...

    def receive(self, period: int) -> float: ...

    def in_transit_total(self, period: int) -> float: ...


@runtime_checkable
class Trigger(Protocol):
    """Invocation is shared infrastructure, identical across arms that share a rule."""

    def should_propose(self, obs: PeriodObservation) -> bool: ...


@runtime_checkable
class LLMClient(Protocol):
    """Narrow seam so branch D can be tested without branch G's transport."""

    model_id: str

    def complete(self, prompt: str, *, decoding_hash: str) -> str: ...


# ---------------------------------------------------------------------------
# hidden-state isolation
# ---------------------------------------------------------------------------

_HIDDEN_TYPES: tuple[type, ...] = (HiddenIncident, HiddenAlertSpec, SupplyRealization)

_ATOMIC = (str, bytes, int, float, bool, complex, type(None))
_MAX_DEPTH = 12


class HiddenStateLeak(AssertionError):
    """Raised when hidden ground truth is reachable from an object handed to a policy."""


def _children(obj: Any) -> Iterator[tuple[str, Any]]:
    if is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            yield f".{f.name}", getattr(obj, f.name, None)
    elif isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            yield f".{name}", getattr(obj, name, None)
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            yield f"[{k!r}]", v
    elif isinstance(obj, Sequence | set | frozenset) and not isinstance(obj, str | bytes):
        for i, v in enumerate(obj):
            yield f"[{i}]", v
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            yield f".{k}", v


def find_hidden_state(obj: Any, *, root: str = "obj") -> list[str]:
    """Walk the object graph and return the access path of every hidden object reachable.

    Structural rather than name-based: a leak through an undeclared attribute, a dict value, or
    a nested container is caught just as reliably as a declared field.
    """
    found: list[str] = []
    seen: set[int] = set()

    def walk(node: Any, path: str, depth: int) -> None:
        if depth > _MAX_DEPTH or isinstance(node, _ATOMIC):
            return
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, _HIDDEN_TYPES):
            found.append(path)
            return
        for suffix, child in _children(node):
            walk(child, path + suffix, depth + 1)

    walk(obj, root, 0)
    return found


def assert_no_hidden_state(obj: Any, *, context: str = "") -> None:
    """Raise :class:`HiddenStateLeak` if hidden ground truth is reachable from ``obj``."""
    leaks = find_hidden_state(obj)
    if leaks:
        where = f" in {context}" if context else ""
        raise HiddenStateLeak(
            f"hidden ground truth reachable{where} via: {', '.join(sorted(leaks))}. "
            "Only the oracle arm and the evaluation code may read hidden state."
        )
