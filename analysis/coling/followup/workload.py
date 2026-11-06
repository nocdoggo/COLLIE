"""Conditional request-budget arithmetic for the draft machine-reference design.

This module neither selects items nor makes requests. It supplies no study
runner or global ledger, and a budget that fits here does not implement a retry
quota, validate batching or tokens, establish prices, authorize spending, or
constitute a registration, scientific claim, or provider guarantee. The two
tested-model lanes are T1 and T2; M1 and M2 are first-pass reference lanes and
MADJ is the adjudication lane. An optional blind first-proposal stage also uses
MADJ. Actual model and provider identities must be fixed and checked separately.
A real key-status response does not establish billing reconciliation or a
provider charge guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from .execution import HTTP_LIMIT, PICOS_PER_DOLLAR, PILOT_RETURN_LIMIT


LANES = ("T1", "T2", "M1", "M2", "MADJ")
REFERENCE_LANES = ("M1", "M2", "MADJ")
MAX_ROLE_REFERENCE_RESERVE_SEEDS = 16
_MAX_AMOUNT_CHARS = 256
_MAX_DECIMAL_EXPONENT = 100


def _count(value: int, name: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")


def _amount(value: str, name: str, *, positive: bool = False) -> Fraction:
    if type(value) is not str:
        raise TypeError(f"{name} must be a decimal string")
    if len(value) > _MAX_AMOUNT_CHARS:
        raise ValueError(f"{name} exceeds supported decimal length")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be finite") from error
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError(f"{name} must be a known {'positive' if positive else 'nonnegative'} amount")
    # Fraction(Decimal(...)) may otherwise attempt to construct an enormous
    # power of ten even for a syntactically short, extreme exponent.
    if abs(number.as_tuple().exponent) > _MAX_DECIMAL_EXPONENT:
        raise ValueError(f"{name} exceeds supported decimal exponent")
    return Fraction(number)


def _ceil_picos(value: str, name: str) -> int:
    scaled = _amount(value, name) * PICOS_PER_DOLLAR
    return -(-scaled.numerator // scaled.denominator)


def _floor_picos(value: str, name: str) -> int:
    scaled = _amount(value, name, positive=True) * PICOS_PER_DOLLAR
    result = scaled.numerator // scaled.denominator
    if not result:
        raise ValueError(f"{name} is below one picodollar")
    return result


def _batches(units: int, batch_size: int) -> int:
    return (units + batch_size - 1) // batch_size


@dataclass(frozen=True, slots=True)
class StudySize:
    """Assigned N notices, C notices, and R seeds, before any analysis."""

    natural_notices: int
    convention_notices: int
    role_seeds: int
    primary_pilot_responses_per_model: int = 20

    def __post_init__(self) -> None:
        for name in ("natural_notices", "convention_notices", "role_seeds",
                     "primary_pilot_responses_per_model"):
            _count(getattr(self, name), name)
        if self.primary_pilot_responses_per_model > PILOT_RETURN_LIMIT:
            raise ValueError("primary pilot exceeds the per-model returned-response ceiling")


@dataclass(frozen=True, slots=True)
class ReferenceBatches:
    """Maximum units per request, with all four R variants grouped by seed.

    The arithmetic assumes each independently counted evaluation or pilot stage
    fills every batch to this size except possibly its final batch. Smaller or
    split batches can require more requests than this calculation.
    An R request containing two seeds therefore contains eight variants. This
    is only a proposed grouping: token limits, reference prompts, item-level
    parsing and the handling of batch failures require separate validation.
    """

    natural_notices: int
    convention_notices: int
    role_seeds: int

    def __post_init__(self) -> None:
        for name in ("natural_notices", "convention_notices", "role_seeds"):
            _count(getattr(self, name), name, positive=True)


@dataclass(frozen=True, slots=True)
class ReferencePilot:
    """Excluded practice units exercised in each reference task.

    Counts may refer to the same practice material in different tasks; each
    task is budgeted separately. This object does not establish disjointness
    from evaluation material or establish a complete exposure inventory.
    """

    natural_notices: int = 0
    convention_notices: int = 0
    role_seeds: int = 0

    def __post_init__(self) -> None:
        for name in ("natural_notices", "convention_notices", "role_seeds"):
            _count(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ExtraPilotCalls:
    """Other excluded first attempts, including any paid route checks.

    Every planned development call must appear either in the pilot task rows
    or here. These counts are per lane, not per notice or per retry.
    """

    T1: int = 0
    T2: int = 0
    M1: int = 0
    M2: int = 0
    MADJ: int = 0

    def __post_init__(self) -> None:
        for name in LANES:
            _count(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class RequestCostBounds:
    """Conditional per-attempt dollar bounds, not verified provider prices.

    Bounds must include every applicable fee, input, output and reasoning cost
    for that lane, including retries. The MADJ bound must cover both the blind
    proposal and exposed adjudication stages, including their pilots. The
    caller must independently establish that provider limits and accounting
    enforce those assumptions.
    """

    T1: str
    T2: str
    M1: str
    M2: str
    MADJ: str

    def __post_init__(self) -> None:
        for lane in LANES:
            _amount(getattr(self, lane), f"{lane} request cost")


@dataclass(frozen=True, slots=True)
class RequestRow:
    stage: str
    lane: str
    unit: str
    units: int
    batch_size: int
    first_attempts: int
    pilot: bool


@dataclass(frozen=True, slots=True)
class Workload:
    """Arithmetic totals; only model requests are eligible for retries.

    The every-request-retries fields mean every model first request retries
    once. Administrative attempts are included once in the total and in an
    ADMIN row, but are not model or pilot requests.
    """

    rows: tuple[RequestRow, ...]
    first_attempts: int
    retry_allowance: int
    planned_attempts_with_quota: int
    attempts_if_every_request_retries: int
    attempt_ceiling: int
    fits_attempt_ceiling_with_quota: bool
    fits_if_every_request_retries: bool
    shared_retry_quota_required: bool
    pilot_first_attempts_by_lane: tuple[tuple[str, int], ...]
    fits_pilot_return_ceiling_if_all_return: bool
    first_cost_bound_picos: int | None
    retry_cost_bound_picos: int | None
    cost_bound_with_quota_picos: int | None
    programme_cap_picos: int
    fits_cost_ceiling_with_quota: bool | None

    @property
    def administrative_attempts(self) -> int:
        return sum(row.first_attempts for row in self.rows if row.lane == "ADMIN")

    @property
    def model_first_attempts(self) -> int:
        return self.first_attempts - self.administrative_attempts


def plan_workload(
    size: StudySize,
    batches: ReferenceBatches,
    *,
    reference_pilot: ReferencePilot = ReferencePilot(),
    extra_pilot: ExtraPilotCalls = ExtraPilotCalls(),
    retry_allowance: int,
    blind_madj: bool = False,
    administrative_attempts: int = 0,
    reference_reserve_role_seeds: int = 0,
    cost_bounds: RequestCostBounds | None = None,
    administrative_cost_bound_usd: str | None = None,
    programme_cap_usd: str = "10",
    attempt_ceiling: int = HTTP_LIMIT,
) -> Workload:
    """Count initial requests and a conservative shared retry allowance.

    Each eligible batch is counted independently for M1, M2 and exposed MADJ,
    even if adjudication is conditional or stages might later be combined.
    With blind_madj=True, one additional intended blind MADJ first-proposal
    request is counted per batch and stage, including pilots. Its rows use the
    blind_ prefix (pilot_blind_ for pilots); the ordinary MADJ rows remain the
    exposed adjudication. Row order does not enforce sequencing or blindness.

    C has separate absent-convention and specified-convention reference passes.
    Each R reference unit is a seed with four variants. Each tested model
    receives one request per N notice, all three C arms per notice, all four R
    variants per seed separately, and its specified pilot responses. Pilot stages
    are batched independently of evaluation stages. The optional R reserve count
    budgets every reference stage for a separately batched fixed reserve of at
    most 16 seeds; it does not send those reserves to tested models or implement
    a replacement policy. A retry allowance assumes
    no more than one retry per model first request *and* an independently
    enforced shared quota. Administrative attempts are counted in the initial
    total, but are neither retry-eligible nor model pilot responses. The caller
    must explicitly include all already-sent and planned administrative HTTP
    attempts, such as a key-status request, without also counting them as model
    pilots; the zero default does not discover prior attempts. For a conservative
    cost bound, retries are assigned to the highest-cost eligible model lanes
    first, using the same MADJ bound for both MADJ stages.

    administrative_cost_bound_usd is an independent nonnegative decimal-string
    upper bound per administrative attempt; it is not a model-lane rate. A
    supplied zero is an assumption that must itself be justified. Without this
    bound, any positive administrative count makes the total first cost, total
    cost and monetary fit unknown, even if model retry costs can be bounded.
    Model prices are also needed when there are model attempts. All bounds
    require independent verification and reconciliation, including for an
    already-sent key-status request.

    Pilot counts are first attempts per lane, including both MADJ stages. They
    bound returned pilots only if each logical request yields at most one
    counted response, including any retry. The per-lane fit flag also assumes
    distinct models across lanes, no earlier uncounted returns, and a complete
    pilot inventory. If other lanes share a model, their counts must be
    combined before checking its ceiling. The returned fit flags describe this
    arithmetic only; they do not track returns, enforce the quota or replace a
    registration, a global ledger, provider verification, cost reconciliation,
    model-identity checks, or input/output token checks.
    """
    if type(size) is not StudySize or type(batches) is not ReferenceBatches:
        raise TypeError("typed study size and reference batches are required")
    if type(reference_pilot) is not ReferencePilot or type(extra_pilot) is not ExtraPilotCalls:
        raise TypeError("typed pilot counts are required")
    if type(blind_madj) is not bool:
        raise TypeError("blind_madj must be a boolean")
    if cost_bounds is not None and type(cost_bounds) is not RequestCostBounds:
        raise TypeError("cost bounds must be RequestCostBounds")
    # Revalidate supplied records at the calculation boundary. A frozen
    # dataclass can still be changed by low-level mutation or reconstructed
    # without its original constructor; subclasses can override validation.
    StudySize.__post_init__(size)
    ReferenceBatches.__post_init__(batches)
    ReferencePilot.__post_init__(reference_pilot)
    ExtraPilotCalls.__post_init__(extra_pilot)
    if cost_bounds is not None:
        RequestCostBounds.__post_init__(cost_bounds)
    _count(retry_allowance, "retry_allowance")
    _count(administrative_attempts, "administrative_attempts")
    _count(reference_reserve_role_seeds, "reference_reserve_role_seeds")
    if reference_reserve_role_seeds > MAX_ROLE_REFERENCE_RESERVE_SEEDS:
        raise ValueError("the fixed role reference reserve cannot exceed 16 seeds")
    if reference_reserve_role_seeds and not size.role_seeds:
        raise ValueError("role reserves require an assigned role programme")
    _count(attempt_ceiling, "attempt_ceiling", positive=True)
    if attempt_ceiling > HTTP_LIMIT:
        raise ValueError("the proposed programme attempt ceiling cannot exceed 1400")
    if _amount(programme_cap_usd, "programme cap", positive=True) > 10:
        raise ValueError("the proposed programme cap cannot exceed $10")
    cap_picos = _floor_picos(programme_cap_usd, "programme cap")
    admin_rate = (None if administrative_cost_bound_usd is None else
                  _ceil_picos(administrative_cost_bound_usd, "administrative request cost"))

    rows: list[RequestRow] = []

    def add(stage: str, lane: str, unit: str, units: int, batch_size: int, pilot: bool = False) -> None:
        rows.append(RequestRow(stage, lane, unit, units, batch_size, _batches(units, batch_size), pilot))

    for lane in ("T1", "T2"):
        add("N", lane, "notice", size.natural_notices, 1)
        add("C_three_arms", lane, "notice_arm", 3 * size.convention_notices, 1)
        add("R_four_variants", lane, "variant", 4 * size.role_seeds, 1)
        add("pilot_tested", lane, "response", size.primary_pilot_responses_per_model, 1, True)

    reference_passes = tuple((lane, "") for lane in REFERENCE_LANES)
    if blind_madj:
        reference_passes = (("MADJ", "blind_"),) + reference_passes
    for lane, stage_prefix in reference_passes:
        for prefix, n, c, r, pilot in (
            ("", size.natural_notices, size.convention_notices, size.role_seeds, False),
            ("pilot_", reference_pilot.natural_notices, reference_pilot.convention_notices,
             reference_pilot.role_seeds, True),
        ):
            prefix += stage_prefix
            add(prefix + "N", lane, "notice", n, batches.natural_notices, pilot)
            add(prefix + "C_absent", lane, "notice", c, batches.convention_notices, pilot)
            add(prefix + "C_specified", lane, "notice", c, batches.convention_notices, pilot)
            add(prefix + "R", lane, "four_variant_seed", r, batches.role_seeds, pilot)
        if reference_reserve_role_seeds:
            add("reserve_" + stage_prefix + "R", lane, "four_variant_seed",
                reference_reserve_role_seeds, batches.role_seeds)

    for lane in LANES:
        add("pilot_other", lane, "request", getattr(extra_pilot, lane), 1, True)

    model_first = sum(row.first_attempts for row in rows)
    if administrative_attempts:
        add("administrative", "ADMIN", "attempt", administrative_attempts, 1)
    first = sum(row.first_attempts for row in rows)
    if retry_allowance > model_first:
        raise ValueError("at most one retry per model first request can be budgeted")
    pilot_counts = tuple((lane, sum(row.first_attempts for row in rows if row.lane == lane and row.pilot))
                         for lane in LANES)

    model_first_cost = first_cost = retry_cost = total_cost = None
    fits_cost = None
    if cost_bounds is not None:
        rates = {lane: _ceil_picos(getattr(cost_bounds, lane), f"{lane} request cost") for lane in LANES}
        counts = {lane: sum(row.first_attempts for row in rows if row.lane == lane) for lane in LANES}
        model_first_cost = sum(counts[lane] * rates[lane] for lane in LANES)
        left = retry_allowance
        retry_cost = 0
        for lane in sorted(LANES, key=lambda value: rates[value], reverse=True):
            take = min(left, counts[lane])
            retry_cost += take * rates[lane]
            left -= take
    elif administrative_attempts and model_first == 0:
        model_first_cost = retry_cost = 0

    if model_first_cost is not None:
        if administrative_attempts == 0:
            first_cost = model_first_cost
        elif admin_rate is not None:
            first_cost = model_first_cost + administrative_attempts * admin_rate
    if first_cost is not None and retry_cost is not None:
        total_cost = first_cost + retry_cost
        fits_cost = total_cost <= cap_picos

    planned = first + retry_allowance
    every_model_retries = first + model_first
    return Workload(
        tuple(rows), first, retry_allowance, planned, every_model_retries, attempt_ceiling,
        planned <= attempt_ceiling, every_model_retries <= attempt_ceiling, retry_allowance < model_first,
        pilot_counts, all(count <= PILOT_RETURN_LIMIT for _, count in pilot_counts),
        first_cost, retry_cost, total_cost, cap_picos, fits_cost,
    )
