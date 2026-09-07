"""Module 6 — proof that ``collie/arms/prompts.py`` is byte-exact against the pinned benchmark.

Three verification layers, strongest first:

1. **Live differential execution.** The upstream scripts are imported from the read-only
   submodule and their agent builders are executed with a dummy ``OPENROUTER_API_KEY`` (the
   ``LLMAgent`` constructor only builds an OpenAI client; no network call happens at
   construction). Digests are re-derived from the upstream builders on every test run — none
   is hardcoded — so a submodule re-pin breaks these tests loudly. For the user prompt, the
   real ``VendingMachineEnv`` + ``VendingMachineObservationWrapper`` are driven period by
   period, and the runner-side injections (which live inline in upstream ``main()``) are
   executed from the exact source lines extracted out of ``run_llm.py``. The ``or_to_llm``
   suffix block is likewise executed from lines extracted out of ``run_or_to_llm.py``.
2. **Hand-computed byte-hazard tests** (``==`` against expected literals) for every
   documented hazard: the double-space seam, the literal ``\\"\\"``, float rendering, the
   doubled header, the 70-= fences, date-injection shapes, and trailing-newline discipline.
3. **Hypothesis properties** over random integer-valued states.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import textwrap
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collie.arms.prompts import (
    PeriodConclusion,
    PromptSpec,
    build_or_to_llm_system_prompt,
    build_system_prompt,
    build_user_prompt,
)
from tests.strategies import horizons

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = REPO_ROOT / "third_party" / "InventoryBench"
RUN_LLM_PATH = BENCH_ROOT / "scripts" / "run_llm.py"
RUN_OR_TO_LLM_PATH = BENCH_ROOT / "scripts" / "run_or_to_llm.py"

FENCE = "=" * 70

SYNTHETIC_SPEC = PromptSpec(
    item_id="chips(Regular)",
    description=None,
    promised_lead_time=4,
    horizon=50,
    train_samples=tuple((f"Period_{i + 1}", float(100 + 7 * i)) for i in range(20)),
)
REAL_SPEC = PromptSpec(
    item_id="108775044",
    description="some product text",
    promised_lead_time=2,
    horizon=47,
    train_samples=tuple(
        (f"2019-{1 + i // 4:02d}-{7 + 14 * (i % 2):02d}", float(40 + 3 * i)) for i in range(10)
    ),
)
MINI_SPEC = PromptSpec(
    item_id="chips(Regular)",
    description=None,
    promised_lead_time=4,
    horizon=50,
    train_samples=(("Period_1", 280.0),),
)
CONCLUSION_1 = PeriodConclusion(
    period=1,
    date="Period_1",
    ordered=30.0,
    arrivals=(),
    start_on_hand=0.0,
    demand=10.0,
    sold=0.0,
    end_on_hand=0.0,
)
CONCLUSION_2 = PeriodConclusion(
    period=2,
    date="Period_2",
    ordered=0.0,
    arrivals=(),
    start_on_hand=0.0,
    demand=12.0,
    sold=0.0,
    end_on_hand=0.0,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_upstream(path: Path, module_name: str) -> ModuleType:
    """Import an upstream script by path (read-only usage).

    The caller's fixture keeps ``OPENROUTER_API_KEY=dummy`` set for the module's lifetime:
    ``LLMAgent.__init__`` reads it at construction time, which happens inside the tests, not
    at import. Construction only builds an OpenAI client — no network call.
    """
    if not path.is_file():
        pytest.skip(f"InventoryBench submodule not checked out: {path} missing")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def upstream_run_llm() -> ModuleType:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(BENCH_ROOT))
        module = _load_upstream(RUN_LLM_PATH, "collie_upstream_run_llm")
    return module


@pytest.fixture(scope="module")
def upstream_run_or_to_llm() -> ModuleType:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(BENCH_ROOT))
        module = _load_upstream(RUN_OR_TO_LLM_PATH, "collie_upstream_run_or_to_llm")
    return module


@pytest.fixture(autouse=True)
def _dummy_openrouter_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upstream agent constructors require the key but never use it (no network at
    construction)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")


def _extract_source_block(source: str, *, start_line: str, end_line: str) -> str:
    """Extract the inclusive [start_line, end_line] block (unique stripped matches), dedented.

    Both anchors failing to match exactly once is an assertion error, not a silent drift —
    that is how a submodule re-pin breaks the test loudly.
    """
    lines = source.split("\n")
    starts = [i for i, line in enumerate(lines) if line.strip() == start_line]
    ends = [i for i, line in enumerate(lines) if line.strip() == end_line]
    assert len(starts) == 1, f"anchor {start_line!r} found {len(starts)} times"
    assert len(ends) == 1, f"anchor {end_line!r} found {len(ends)} times"
    assert starts[0] < ends[0]
    return textwrap.dedent("\n".join(lines[starts[0] : ends[0] + 1]))


def _runner_injection_block() -> str:
    """run_llm.py:828-852 — the date injections, normalization, and insights prepend that
    live inline in upstream ``main()``, extracted as executable source. The one name the
    block reads that is defined a few lines earlier (``exact_date``, run_llm.py:823) is
    supplied through the exec namespace via :class:`_CsvPlayerShim`."""
    return _extract_source_block(
        RUN_LLM_PATH.read_text(encoding="utf-8"),
        start_line="period_pattern = re.compile(",
        end_line="observation = inject_carry_over_insights(observation, carry_over_insights)",
    )


def _or_suffix_block() -> str:
    """run_or_to_llm.py:1162-1168 — the OR-recommendation suffix, extracted as executable
    source."""
    return _extract_source_block(
        RUN_OR_TO_LLM_PATH.read_text(encoding="utf-8"),
        start_line='or_text = "\\n" + "="*70 + "\\n"',
        end_line='or_text += "="*70 + "\\n"',
    )


class _CsvPlayerShim:
    """Stand-in for ``run_llm.CSVDemandPlayer`` over scripted dates (the two methods the
    runner-side injection block calls)."""

    def __init__(self, dates: list[str]) -> None:
        self._dates = dates

    def get_exact_date(self, period_index: int) -> str:
        return self._dates[period_index - 1]

    def get_num_periods(self) -> int:
        return len(self._dates)


def _drive_upstream_episode(
    run_llm: ModuleType,
    *,
    spec: PromptSpec,
    orders: list[int],
    demands: list[int],
    dates: list[str],
    profit: float,
    holding: float,
    insight_memos: dict[int, str],
) -> dict[int, tuple[str, dict[str, Any]]]:
    """Drive the pinned env + wrapper + runner injections, capturing every VM turn.

    Returns ``{period: (upstream_observation, kwargs_for_build_user_prompt)}``. The env and
    wrapper execute for real; the runner-side injections execute from the extracted source
    block. ``insight_memos[p]`` is recorded after period p's VM turn, exactly as the runner
    records the action's ``carry_over_insight``.
    """
    injection_block = _runner_injection_block()
    ta = run_llm.ta
    env = ta.make(env_id="VendingMachine-v0")
    env.add_item(
        item_id=spec.item_id,
        description=spec.description if spec.description is not None else spec.item_id,
        lead_time=spec.promised_lead_time,
        profit=profit,
        holding_cost=holding,
    )
    env.reset(num_players=2, num_days=len(dates), initial_inventory_per_item=0)

    captured: dict[int, tuple[str, dict[str, Any]]] = {}
    carry_over_insights: dict[int, str] = {}
    done = False
    current_period = 1
    while not done:
        pid, observation = env.get_observation()
        if pid == 0:
            csv_player = _CsvPlayerShim(dates)
            namespace: dict[str, Any] = {
                "re": re,
                "current_period": current_period,
                "csv_player": csv_player,
                "exact_date": csv_player.get_exact_date(current_period),
                "observation": observation,
                "_normalize_timeline_terms": run_llm._normalize_timeline_terms,
                "inject_carry_over_insights": run_llm.inject_carry_over_insights,
                "carry_over_insights": carry_over_insights,
            }
            exec(injection_block, namespace)
            conclusions = tuple(
                PeriodConclusion(
                    period=log["day"],
                    date=dates[log["day"] - 1],
                    ordered=float(log["orders"][spec.item_id]),
                    arrivals=tuple(
                        (float(qty), order_day) for qty, order_day in log["arrivals"][spec.item_id]
                    ),
                    start_on_hand=float(log["starting_inventory"][spec.item_id]),
                    demand=float(log["requests"][spec.item_id]),
                    sold=float(log["sales"][spec.item_id]),
                    end_on_hand=float(log["ending_inventory"][spec.item_id]),
                )
                for log in env.daily_logs
            )
            in_transit = sum(
                order["quantity"]
                for order in env.pending_orders
                if order["item_id"] == spec.item_id and env.current_day <= order["arrival_day"]
            )
            kwargs: dict[str, Any] = {
                "period": current_period,
                "date": dates[current_period - 1],
                "on_hand": float(env.on_hand_inventory[spec.item_id]),
                "in_transit": float(in_transit),
                "profit": profit,
                "holding": holding,
                "conclusions": conclusions,
                "insights": tuple(sorted(carry_over_insights.items())),
            }
            captured[current_period] = (namespace["observation"], kwargs)
            action = json.dumps({"action": {spec.item_id: orders[current_period - 1]}})
            if current_period in insight_memos:
                carry_over_insights[current_period] = insight_memos[current_period]
        else:
            action = json.dumps({"action": {spec.item_id: demands[current_period - 1]}})
            current_period += 1
        done, _ = env.step(action=action)
    return captured


# ---------------------------------------------------------------------------
# live differential execution: system prompts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", [SYNTHETIC_SPEC, REAL_SPEC], ids=["synthetic", "real"])
def test_llm_system_prompt_matches_live_upstream(
    upstream_run_llm: ModuleType, spec: PromptSpec
) -> None:
    samples = [(date, int(demand)) for date, demand in spec.train_samples]
    agent = upstream_run_llm.make_vm_agent(
        initial_samples={spec.item_id: samples},
        promised_lead_time=spec.promised_lead_time,
    )
    ours = build_system_prompt(spec)
    assert _sha256(ours) == _sha256(agent.system_prompt)
    assert ours == agent.system_prompt


@pytest.mark.parametrize("spec", [SYNTHETIC_SPEC, REAL_SPEC], ids=["synthetic", "real"])
def test_or_to_llm_system_prompt_matches_live_upstream(
    upstream_run_or_to_llm: ModuleType, spec: PromptSpec
) -> None:
    samples = [(date, int(demand)) for date, demand in spec.train_samples]
    agent = upstream_run_or_to_llm.make_hybrid_vm_agent(
        initial_samples={spec.item_id: samples},
        promised_lead_time=spec.promised_lead_time,
    )
    ours = build_or_to_llm_system_prompt(spec)
    assert _sha256(ours) == _sha256(agent.system_prompt)
    assert ours == agent.system_prompt


def test_upstream_feedback_and_guidance_blocks_are_conditional(
    upstream_run_llm: ModuleType, upstream_run_or_to_llm: ModuleType
) -> None:
    """Justifies omitting those blocks: upstream itself adds them only when enabled, and
    the benchmark configuration enables neither."""
    samples = {"item": [("Period_1", 10)]}
    for builder in (upstream_run_llm.make_vm_agent, upstream_run_or_to_llm.make_hybrid_vm_agent):
        base = builder(initial_samples=samples, promised_lead_time=4)
        assert "HUMAN-IN-THE-LOOP MODE" not in base.system_prompt
        assert "STRATEGIC GUIDANCE" not in base.system_prompt
        with_feedback = builder(
            initial_samples=samples, promised_lead_time=4, human_feedback_enabled=True
        )
        with_guidance = builder(
            initial_samples=samples, promised_lead_time=4, guidance_enabled=True
        )
        assert "HUMAN-IN-THE-LOOP MODE" in with_feedback.system_prompt
        assert "STRATEGIC GUIDANCE" in with_guidance.system_prompt


# ---------------------------------------------------------------------------
# live differential execution: user prompt
# ---------------------------------------------------------------------------


def test_user_prompt_matches_live_upstream_episode(upstream_run_llm: ModuleType) -> None:
    """Synthetic-style episode: stockouts, an arrival cohort, a carry-over insight."""
    spec = PromptSpec("chips(Regular)", None, 4, 6, ())
    captured = _drive_upstream_episode(
        upstream_run_llm,
        spec=spec,
        orders=[30, 0, 25, 0, 5, 0],
        demands=[10, 12, 14, 16, 18, 20],
        dates=[f"Period_{i + 1}" for i in range(6)],
        profit=19.0,
        holding=1.0,
        insight_memos={2: "Lead time drift suspected: P1 order still in transit"},
    )
    assert len(captured) == 6
    for period, (upstream_observation, kwargs) in captured.items():
        assert build_user_prompt(spec, **kwargs) == upstream_observation, f"period {period}"


def test_user_prompt_matches_live_upstream_episode_real_style(
    upstream_run_llm: ModuleType,
) -> None:
    """Real-style episode: product description text, ISO dates, a lead-time-1 arrival."""
    spec = PromptSpec("108775044", "Canned black beans, 400g can", 1, 3, ())
    captured = _drive_upstream_episode(
        upstream_run_llm,
        spec=spec,
        orders=[5, 0, 0],
        demands=[3, 4, 2],
        dates=["2019-01-07", "2019-01-21", "2019-02-04"],
        profit=4.0,
        holding=1.0,
        insight_memos={},
    )
    assert len(captured) == 3
    for period, (upstream_observation, kwargs) in captured.items():
        assert build_user_prompt(spec, **kwargs) == upstream_observation, f"period {period}"


def test_or_suffix_matches_executed_upstream_block() -> None:
    """The suffix lives inline in upstream ``main()``; execute its exact source lines."""
    namespace: dict[str, Any] = {"or_recommendations": {"chips(Regular)": 137}}
    exec(_or_suffix_block(), namespace)
    upstream_suffix = namespace["or_text"]
    kwargs: dict[str, Any] = {
        "period": 2,
        "date": "Period_2",
        "on_hand": 0.0,
        "in_transit": 30.0,
        "profit": 19.0,
        "holding": 1.0,
        "conclusions": (CONCLUSION_1,),
        "insights": (),
    }
    without_or = build_user_prompt(MINI_SPEC, **kwargs)
    with_or = build_user_prompt(MINI_SPEC, **kwargs, or_recommendation=137)
    assert with_or == without_or + upstream_suffix


# ---------------------------------------------------------------------------
# byte hazards, hand-computed
# ---------------------------------------------------------------------------


def test_rationale_template_keeps_the_double_space_seam() -> None:
    line = next(
        ln for ln in build_system_prompt(MINI_SPEC).split("\n") if ln.startswith('  "rationale"')
    )
    assert line == (
        '  "rationale": "Step-by-step reasoning covering (a) world knowledge and product '
        "description (when available), (b) demand regime analysis,  (c) lead_time vs. "
        'missing orders, (d) inventory & pipeline assessment, (e) final order logic.",'
    )


def test_carry_over_instruction_keeps_literal_escaped_quotes() -> None:
    line = next(
        ln
        for ln in build_system_prompt(MINI_SPEC).split("\n")
        if ln.startswith('  "carry_over_insight"')
    )
    assert line == (
        '  "carry_over_insight": "Summarize all NEW sustained changes with evidence, '
        'or \\"\\" if none.",'
    )


def test_or_to_llm_carry_over_instruction_keeps_literal_escaped_quotes() -> None:
    line = next(
        ln
        for ln in build_or_to_llm_system_prompt(MINI_SPEC).split("\n")
        if ln.startswith('  "carry_over_insight"')
    )
    assert line == (
        '  "carry_over_insight": "Summaries of NEW sustained changes with evidence, or \\"\\".",'
    )


def test_board_renders_costs_via_python_float_str() -> None:
    prompt = build_user_prompt(
        MINI_SPEC,
        period=1,
        date="Period_1",
        on_hand=0.0,
        in_transit=0.0,
        profit=4.0,
        holding=1.0,
        conclusions=(),
        insights=(),
    )
    line = next(ln for ln in prompt.split("\n") if "Profit=" in ln)
    assert line == "chips(Regular) (chips(Regular)): Profit=$4.0/unit, Holding=$1.0/unit/period"


def test_board_header_doubles_item_id_when_description_is_none() -> None:
    without_desc = build_user_prompt(
        MINI_SPEC,
        period=1,
        date="Period_1",
        on_hand=0.0,
        in_transit=0.0,
        profit=19.0,
        holding=1.0,
        conclusions=(),
        insights=(),
    )
    line = next(ln for ln in without_desc.split("\n") if "Profit=" in ln)
    assert line == "chips(Regular) (chips(Regular)): Profit=$19.0/unit, Holding=$1.0/unit/period"
    with_desc = build_user_prompt(
        replace(MINI_SPEC, description="Tortilla chips"),
        period=1,
        date="Period_1",
        on_hand=0.0,
        in_transit=0.0,
        profit=19.0,
        holding=1.0,
        conclusions=(),
        insights=(),
    )
    line = next(ln for ln in with_desc.split("\n") if "Profit=" in ln)
    assert line == "chips(Regular) (Tortilla chips): Profit=$19.0/unit, Holding=$1.0/unit/period"


def test_carry_over_fences_are_seventy_equals_and_insights_sorted() -> None:
    prompt = build_user_prompt(
        MINI_SPEC,
        period=4,
        date="Period_4",
        on_hand=0.0,
        in_transit=0.0,
        profit=19.0,
        holding=1.0,
        conclusions=(CONCLUSION_1,),
        insights=((3, "memo b"), (1, "memo a")),
    )
    expected_prefix = (
        FENCE
        + "\nCARRY-OVER INSIGHTS (Key Discoveries):\n"
        + FENCE
        + "\nPeriod 1: memo a\nPeriod 3: memo b\n"
        + FENCE
        + "\n\n"
    )
    assert prompt.startswith(expected_prefix)


def test_header_date_injection_shape() -> None:
    prompt = build_user_prompt(
        MINI_SPEC,
        period=3,
        date="Period_3",
        on_hand=0.0,
        in_transit=30.0,
        profit=19.0,
        holding=1.0,
        conclusions=(CONCLUSION_1, CONCLUSION_2),
        insights=(),
    )
    lines = prompt.split("\n")
    assert lines[0] == "=== CURRENT STATUS ==="
    assert lines[1] == ""
    assert lines[2] == "PERIOD 3 (Date: Period_3) / 50"


def test_history_date_injection_shape() -> None:
    prompt = build_user_prompt(
        MINI_SPEC,
        period=3,
        date="Period_3",
        on_hand=0.0,
        in_transit=30.0,
        profit=19.0,
        holding=1.0,
        conclusions=(CONCLUSION_1, CONCLUSION_2),
        insights=(),
    )
    assert "Period 2 (Date: Period_2) conclude:" in prompt.split("\n")
    assert "Period 1 (Date: Period_1) conclude:" in prompt.split("\n")


def test_system_prompts_end_without_trailing_newline() -> None:
    llm_prompt = build_system_prompt(REAL_SPEC)
    or_prompt = build_or_to_llm_system_prompt(REAL_SPEC)
    assert not llm_prompt.endswith("\n")
    assert llm_prompt.endswith("Do not output extra text outside the JSON.")
    assert not or_prompt.endswith("\n")
    assert or_prompt.endswith("No extra commentary outside the JSON.")


def test_golden_three_period_user_prompt() -> None:
    """Period 3 with two conclusions and one insight; expected string built by hand."""
    expected = (
        FENCE
        + "\nCARRY-OVER INSIGHTS (Key Discoveries):\n"
        + FENCE
        + "\nPeriod 1: Demand regime shift at Period 1: avg jumped\n"
        + FENCE
        + "\n\n=== CURRENT STATUS ==="
        "\n\nPERIOD 3 (Date: Period_3) / 50"
        "\n\n=== ITEMS ==="
        "\nchips(Regular) (chips(Regular)): Profit=$19.0/unit, Holding=$1.0/unit/period"
        "\n  On-hand: 0, In-transit: 30 units"
        "\n\n\n=== GAME HISTORY ==="
        "\n\nPeriod 1 (Date: Period_1) conclude:"
        "\n  chips(Regular): ordered=30, arrived=0, starting on-hand inventory=0,"
        " demand=10, sold=0, ending on-hand inventory=0"
        "\n\nPeriod 2 (Date: Period_2) conclude:"
        "\n  chips(Regular): ordered=0, arrived=0, starting on-hand inventory=0,"
        " demand=12, sold=0, ending on-hand inventory=0"
    )
    prompt = build_user_prompt(
        MINI_SPEC,
        period=3,
        date="Period_3",
        on_hand=0.0,
        in_transit=30.0,
        profit=19.0,
        holding=1.0,
        conclusions=(CONCLUSION_1, CONCLUSION_2),
        insights=((1, "Demand regime shift at Period 1: avg jumped"),),
    )
    assert prompt == expected


def test_or_to_llm_suffix_exact_bytes() -> None:
    kwargs: dict[str, Any] = {
        "period": 2,
        "date": "Period_2",
        "on_hand": 0.0,
        "in_transit": 30.0,
        "profit": 19.0,
        "holding": 1.0,
        "conclusions": (CONCLUSION_1,),
        "insights": (),
    }
    expected_suffix = (
        "\n"
        + FENCE
        + "\nOR ALGORITHM RECOMMENDATIONS (capped policy):\n  chips(Regular): 137 units"
        "\n\nNote: OR uses the promised lead time and historical demand only."
        "\nIt cannot see lost shipments, or actual lead-time shifts—adjust accordingly.\n"
        + FENCE
        + "\n"
    )
    without_or = build_user_prompt(MINI_SPEC, **kwargs)
    with_or = build_user_prompt(MINI_SPEC, **kwargs, or_recommendation=137)
    assert with_or == without_or + expected_suffix


def test_train_demands_render_as_ints_not_floats() -> None:
    line = next(
        ln for ln in build_system_prompt(MINI_SPEC).split("\n") if ln.startswith("    Period_1:")
    )
    assert line == "    Period_1: 280"


def test_timeline_normalization_applies_to_descriptions() -> None:
    spec = replace(MINI_SPEC, description="7 Days a week")
    prompt = build_user_prompt(
        spec,
        period=1,
        date="Period_1",
        on_hand=0.0,
        in_transit=0.0,
        profit=4.0,
        holding=1.0,
        conclusions=(),
        insights=(),
    )
    line = next(ln for ln in prompt.split("\n") if "Profit=" in ln)
    assert line == "chips(Regular) (7 Periods a period): Profit=$4.0/unit, Holding=$1.0/unit/period"


def test_timeline_normalization_week_concluded_special_case() -> None:
    spec = replace(MINI_SPEC, description="Week 3 concluded: promo")
    prompt = build_user_prompt(
        spec,
        period=1,
        date="Period_1",
        on_hand=0.0,
        in_transit=0.0,
        profit=4.0,
        holding=1.0,
        conclusions=(),
        insights=(),
    )
    line = next(ln for ln in prompt.split("\n") if "Profit=" in ln)
    assert line == (
        "chips(Regular) (Period 3 conclude: promo): Profit=$4.0/unit, Holding=$1.0/unit/period"
    )


def test_no_historical_demand_section_without_train_samples() -> None:
    spec = replace(MINI_SPEC, train_samples=())
    assert "HISTORICAL DEMAND DATA" not in build_system_prompt(spec)
    assert "HISTORICAL DEMAND DATA" not in build_or_to_llm_system_prompt(spec)


def test_non_integer_inputs_raise_value_error() -> None:
    with pytest.raises(ValueError, match="integer-valued"):
        build_system_prompt(replace(MINI_SPEC, train_samples=(("Period_1", 280.5),)))
    base: dict[str, Any] = {
        "date": "Period_1",
        "profit": 4.0,
        "holding": 1.0,
        "insights": (),
    }
    with pytest.raises(ValueError, match="integer-valued"):
        build_user_prompt(MINI_SPEC, **base, period=1, on_hand=1.5, in_transit=0.0, conclusions=())
    with pytest.raises(ValueError, match="integer-valued"):
        build_user_prompt(MINI_SPEC, **base, period=1, on_hand=0.0, in_transit=0.5, conclusions=())
    bad_arrival = PeriodConclusion(2, "Period_2", 0.0, ((2.5, 1),), 0.0, 12.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="integer-valued"):
        build_user_prompt(
            MINI_SPEC, **base, period=2, on_hand=0.0, in_transit=0.0, conclusions=(bad_arrival,)
        )
    bad_demand = replace(CONCLUSION_1, demand=10.5)
    with pytest.raises(ValueError, match="integer-valued"):
        build_user_prompt(
            MINI_SPEC, **base, period=2, on_hand=0.0, in_transit=0.0, conclusions=(bad_demand,)
        )


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------

_DATES = st.from_regex(r"(Period_[0-9]{1,3}|20[0-9]{2}-[01][0-9]-[0-3][0-9])", fullmatch=True)
_MEMOS = st.from_regex(r"[a-z0-9 .,+\-]{1,40}", fullmatch=True)
_ITEM_IDS = st.from_regex(r"[a-z0-9_()]{1,8}", fullmatch=True)
_DESCRIPTIONS = st.from_regex(r"[a-z0-9 ]{1,15}", fullmatch=True)
_INT_FLOATS = st.integers(min_value=0, max_value=500).map(float)


@st.composite
def _prompt_calls(draw: st.DrawFn) -> tuple[PromptSpec, dict[str, Any]]:
    horizon = draw(horizons)
    period = draw(st.integers(min_value=1, max_value=horizon))
    spec = PromptSpec(
        item_id=draw(_ITEM_IDS),
        description=draw(st.one_of(st.none(), _DESCRIPTIONS)),
        promised_lead_time=draw(st.integers(min_value=0, max_value=6)),
        horizon=horizon,
        train_samples=tuple(
            (draw(_DATES), draw(_INT_FLOATS))
            for _ in range(draw(st.integers(min_value=0, max_value=3)))
        ),
    )
    history_periods = (
        sorted(
            draw(st.lists(st.integers(min_value=1, max_value=period - 1), max_size=3, unique=True))
        )
        if period > 1
        else []
    )
    conclusions = tuple(
        PeriodConclusion(
            period=p,
            date=draw(_DATES),
            ordered=draw(_INT_FLOATS),
            arrivals=tuple(
                (draw(_INT_FLOATS), draw(st.integers(min_value=1, max_value=p)))
                for _ in range(draw(st.integers(min_value=0, max_value=2)))
            ),
            start_on_hand=draw(_INT_FLOATS),
            demand=draw(_INT_FLOATS),
            sold=draw(_INT_FLOATS),
            end_on_hand=draw(_INT_FLOATS),
        )
        for p in history_periods
    )
    insights = tuple(
        sorted(
            draw(
                st.lists(
                    st.tuples(st.integers(min_value=1, max_value=period), _MEMOS),
                    max_size=2,
                    unique_by=lambda insight: insight[0],
                )
            )
        )
    )
    kwargs: dict[str, Any] = {
        "period": period,
        "date": draw(_DATES),
        "on_hand": draw(_INT_FLOATS),
        "in_transit": draw(_INT_FLOATS),
        "profit": draw(st.sampled_from([1.0, 4.0, 19.0])),
        "holding": 1.0,
        "conclusions": conclusions,
        "insights": insights,
        "or_recommendation": draw(st.one_of(st.none(), st.integers(min_value=0, max_value=1000))),
    }
    return spec, kwargs


@given(case=_prompt_calls())
@settings(max_examples=50)
def test_user_prompt_date_injection_and_structure_properties(
    case: tuple[PromptSpec, dict[str, Any]],
) -> None:
    spec, kwargs = case
    prompt = build_user_prompt(spec, **kwargs)
    period = kwargs["period"]
    assert f"PERIOD {period} (Date: {kwargs['date']}) / {spec.horizon}" in prompt
    # No stray "PERIOD N / T" remnant survives the header injection.
    assert not re.search(r"PERIOD\s+\d+\s+/\s+\d+", prompt, re.IGNORECASE)
    conclusions = kwargs["conclusions"]
    for conclusion in conclusions:
        assert f"Period {conclusion.period} (Date: {conclusion.date}) conclude:" in prompt
    assert ("GAME HISTORY" in prompt) == bool(conclusions)
    assert prompt.startswith(FENCE) == bool(kwargs["insights"])
    if kwargs["or_recommendation"] is not None:
        assert prompt.endswith(FENCE + "\n")
        assert f"  {spec.item_id}: {kwargs['or_recommendation']} units" in prompt


@given(case=_prompt_calls())
@settings(max_examples=50)
def test_period_one_without_conclusions_has_no_game_history(
    case: tuple[PromptSpec, dict[str, Any]],
) -> None:
    spec, kwargs = case
    prompt = build_user_prompt(
        spec,
        **{**kwargs, "period": 1, "conclusions": (), "insights": (), "or_recommendation": None},
    )
    assert "GAME HISTORY" not in prompt
    assert "conclude:" not in prompt


@given(case=_prompt_calls())
@settings(max_examples=50)
def test_system_prompts_are_deterministic(case: tuple[PromptSpec, dict[str, Any]]) -> None:
    spec, _ = case
    assert build_system_prompt(spec) == build_system_prompt(spec)
    assert build_or_to_llm_system_prompt(spec) == build_or_to_llm_system_prompt(spec)
