"""The InventoryBench LLM prompt pipeline, byte-exact, as pure functions.

Reimplements the prompt construction of the pinned benchmark (``third_party/InventoryBench``,
commit 62b1f116) for the ``llm`` strategy (``scripts/run_llm.py``), the ``or_to_llm``
strategy (``scripts/run_or_to_llm.py``), and the ``llm_to_or`` strategy
(``scripts/run_llm_to_or.py``), specialised to the benchmark's single-item configuration.
Upstream builds these strings inside script-level ``main()`` functions and game-harness
classes that read their state from CSVs and a live 2-player environment; the arms cannot run
inside that harness, so the state upstream would read is passed in explicitly through
:class:`PromptSpec` (episode constants) and :class:`PeriodConclusion` (per-period records
the arm tracks from its own orders and observations).

Every builder is transcribed byte-for-byte from the source region cited in its docstring,
including the hazards that are easy to "fix" by accident: a double space at a
string-concatenation seam in the ``rationale`` template, literal ``\\"\\"`` sequences inside
the JSON templates, a literal ``}}`` in the llm_to_or rendered example (an upstream
plain-string bug producing invalid JSON for the model), non-ASCII characters
(multiplication/minus signs, em dashes, bullets, and the unicode math of the OR sections),
and the trailing-newline discipline (the llm_to_or system prompt ends with one; the other
two do not). ``tests/test_prompts_verbatim.py`` proves byte-exactness by executing the
upstream builders and environment under this repo's venv and comparing digests live.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "PeriodConclusion",
    "PromptSpec",
    "build_llm_to_or_system_prompt",
    "build_or_to_llm_system_prompt",
    "build_system_prompt",
    "build_user_prompt",
]


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """Episode constants upstream reads from the CSV/config.

    ``description=None`` reproduces upstream's default ``desc = item_id`` (the doubled
    ``chips(Regular) (chips(Regular))`` header on synthetic instances). ``horizon`` is the
    ``T`` in ``PERIOD N / T`` — the full CSV row count. ``train_samples`` are
    ``(date, demand)`` pairs in CSV order; demands are integer-valued floats standing in for
    the ints upstream gets from ``pandas.Series.tolist()``.
    """

    item_id: str
    description: str | None
    promised_lead_time: int
    horizon: int
    train_samples: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class PeriodConclusion:
    """One period's conclude record, tracked by the arm from its own orders + observations.

    ``arrivals`` are ``(qty, order_period)`` cohorts, already attributed. ``date`` is the
    period's exact date, which the runner-side injection (``run_llm.py:837-849``) splices
    into the ``Period N conclude:`` header.
    """

    period: int
    date: str
    ordered: float
    arrivals: tuple[tuple[float, int], ...]
    start_on_hand: float
    demand: float
    sold: float
    end_on_hand: float


def _require_int(value: float, *, what: str) -> int:
    """Render an integer-valued float the way upstream renders its ints.

    Upstream's env state and CSV demands are Python ints, so f-strings render them without a
    decimal point. Our contract carries floats; silently truncating a non-integer would
    desynchronise the prompt from the arm's state, so refuse instead.
    """
    as_int = int(value)
    if as_int != value:
        raise ValueError(f"{what} must be integer-valued, got {value!r}")
    return as_int


def _historical_demand_section(spec: PromptSpec) -> str:
    """``run_llm.py:622-629``, identical to ``run_or_to_llm.py:868-875``."""
    section = "=== HISTORICAL DEMAND DATA ===\n"
    section += "Use these samples to inform your demand forecast:\n"
    section += f"  {spec.item_id}:\n"
    for date, demand in spec.train_samples:
        section += f"    {date}: {_require_int(demand, what='train demand')}\n"
    section += "\n"
    return section


def build_system_prompt(spec: PromptSpec) -> str:
    """The ``llm`` strategy's system prompt, from ``run_llm.py:510-686`` (``make_vm_agent``).

    Benchmark configuration only: ``human_feedback_enabled`` and ``guidance_enabled`` are
    always False upstream (``run_llm.py:783-789`` passes the CLI flags, and the shipped
    benchmark sets neither), so those blocks are omitted, as upstream itself does. Single
    item, so ``items_str`` is the one quoted id and ``example_action`` is the one-item case.
    Ends without a trailing newline (verified against live execution).
    """
    items_str = f'"{spec.item_id}"'
    system = (
        "=== ROLE & OBJECTIVE ===\n"
        f'You control a single vending SKU "{spec.item_id}". '
        "Maximize total reward (R_t = Profit × units_sold − HoldingCost × ending_inventory) over total periods.\n"
        "\n"
        "=== TIMELINE & DATA ===\n"
        "- Observations contain period information plus complete history to date; there is no future information feed.\n"
        "- Calendar dates and product descriptions may or may not be provided in context.\n"
        "- When dates are available, ACTIVELY apply calendar + world knowledge:\n"
        "  * Identify major retail/cultural calendar events from the date\n"
        "  * Recognize seasonal demand drivers\n"
        "- When product description is available, match it to seasonal relevance.\n"
        "- When calendar dates are available, demand can spike or drop significantly around key calendar events—anticipate and act proactively.\n"
        "\n"
        "=== GAME MECHANISM: PERIOD EXECUTION SEQUENCE ===\n"
        "Each period follows this strict execution order:\n"
        "  1. VM Decision Phase: You receive observation and place orders for Period N\n"
        "  2. Arrival Resolution: Orders scheduled to arrive in Period N are added to on-hand inventory\n"
        "  3. Demand Resolution: Customer demand is satisfied from on-hand inventory\n"
        "  4. Period Conclusion: System generates 'Period N conclude' message (visible in Period N+1)\n"
        "\n"
        "Important: Steps 2-4 happen AFTER your decision. You will see their results in the next period.\n"
        "\n"
        "=== LEAD TIME DEFINITION ===\n"
        f"Promised lead time: {spec.promised_lead_time} period(s). 'Lead time = L periods' means:\n"
        "1. Order placed in Period N's decision phase\n"
        "2. Order arrives during Period (N+L)'s arrival resolution phase\n"
        "3. Arrival becomes visible in 'Period (N+L) conclude' message\n"
        "4. You read this message at the start of Period (N+L+1)'s decision phase\n"
        "\n"
        "Note: There is always a 1-period observation delay between when orders physically arrive\n"
        "and when you can observe the arrival in the 'conclude' message.\n"
        "\n"
        "=== CRITICAL TIMING EXAMPLE ===\n"
        "SCENARIO A: Actual lead_time = 1 period\n"
        "  • Period 1: You place Order_A. No history yet, so no conclude to read.\n"
        "  • Period 2 START: You read 'Period 1 conclude: arrived=0'. This is NORMAL!\n"
        "    Order_A arrives DURING Period 2 (after your Period 2 decision), not before.\n"
        "  • Period 3 START: You read 'Period 2 conclude: arrived=X (ordered Period 1, lead_time was 1 periods)'.\n"
        "    NOW you have confirmation that actual lead_time = 1.\n"
        "\n"
        "SCENARIO B: Actual lead_time = 0 periods (same-period arrival)\n"
        "  • Period 1: You place Order_B.\n"
        "  • Period 2 START: You read 'Period 1 conclude: arrived=Y (ordered Period 1, lead_time was 0 periods)'.\n"
        "    With lead_time = 0, the order arrives within the same period it was placed.\n"
        "\n"
        "KEY INSIGHT: Do NOT conclude that 'actual lead_time ≠ promised' just because 'Period N conclude' shows arrived=0.\n"
        "When actual lead_time ≥ 1, the order placed in Period N arrives DURING Period N+lead_time, and you only\n"
        "see confirmation in 'Period N+lead_time conclude' (read at Period N+lead_time+1).\n"
        "\n"
        "Lost orders never produce a conclude statement—they remain in 'In-transit' indefinitely.\n"
        "Prolonged absence (multiple periods past promised lead_time with no conclude) signals a lost shipment.\n"
        "\n"
        "=== KEY IMPLICATIONS ===\n"
        "- When deciding for Period N, you see 'Period N-1 conclude' message\n"
        "- Period N's arrivals happen during Period N but are only visible in Period N+1\n"
        "- Only use CONCLUDED period messages to infer actual lead time\n"
        "- Actual lead time may differ from promised lead time; orders may also be lost\n"
        "- Your order decision should ensure: order + on-hand + in-transit covers (L+1) periods of demand\n"
        "  (L+1 because current period's demand occurs after your decision)\n"
        "\n"
        "=== INVENTORY & ORDERS ===\n"
        "- On-hand inventory starts at 0 in Period 1 and is charged holding cost every period.\n"
        '- "In-transit" shows total units not yet delivered; you must infer when each shipment should arrive.\n'
        f"- Supplier-promised lead time is {spec.promised_lead_time} period(s), but actual lead time can drift and must be inferred from CONCLUDED periods only.\n"
        "- Orders may also never CONCLUDE.\n"
        "\n"
        "=== DEMAND REASONING ===\n"
        "- When product description and/or calendar dates are available, use them as PRIMARY anchors for forecasting:\n"
        "  * What product category is this? (if description available)\n"
        "  * What time of year is it? (if dates available)\n"
        "  * Are there upcoming or recent calendar events that affect this category? (if dates available)\n"
        "- Compare historical demand segments to detect sustained mean/variance changes or new regimes.\n"
        "- Historical samples seed your prior, but demand can shift abruptly—confirm each change with evidence.\n"
        "- Combine calendar knowledge with actual demand patterns to inform your forecast.\n"
        "\n"
        "=== LEAD-TIME INFERENCE ===\n"
        "ONLY use 'Period X conclude' messages from history to infer actual lead time:\n"
        "- Message format: 'arrived=Y units (ordered on Period Z, lead_time was W periods)'\n"
        "- Actual lead time calculation: W = X - Z\n"
        "- NEVER infer lead-time from current period's observations (you haven't seen arrivals yet)\n"
        "- If orders don't arrive for many periods beyond promised lead time, they may be lost\n"
        "\n"
    )
    if spec.train_samples:
        system += _historical_demand_section(spec)
    example_action = f'"{spec.item_id}": 100'
    system += (
        "=== DECISION CHECKLIST ===\n"
        "1. When available, use world knowledge and product description to compare to historical demand for this SKU.\n"
        "2. Reconcile on-hand + in-transit vs. expected arrivals; flag overdue orders.\n"
        "3. Infer lead time (or order loss) from arrivals/absences and adjust safety stock.\n"
        "4. Forecast demand using calendar knowledge plus recent data regimes.\n"
        "5. Place an order that balances service level vs. holding cost while respecting pipeline.\n"
        "\n"
        "=== CARRY-OVER INSIGHTS ===\n"
        "This is a critical mechanism for cross-period memory.\n"
        "\n"
        "PURPOSE: Record NEW, sustained, actionable pattern shifts that "
        "future periods must remember for accurate decision-making.\n"
        "\n"
        "WHAT TO RECORD:\n"
        "- Confirmed demand regime changes (mean/variance shifts)\n"
        "- Lead time changes with evidence (e.g., 'Actual lead time is 3, not promised 2')\n"
        "- Seasonal patterns with evidence (e.g., 'Holiday demand spike confirmed')\n"
        "- Missing/delayed shipment patterns\n"
        "- Any observation helpful for future inventory decisions\n"
        "\n"
        "FORMAT REQUIREMENTS:\n"
        "- Include concrete numerical evidence (date ranges, averages, percentages)\n"
        "- **CRITICAL - BE CONSERVATIVE**: Only record if the signal is SIGNIFICANT and SUSTAINED "
        "(at least 3+ periods of consistent evidence). When in doubt, output empty string.\n"
        "- Do NOT repeat insights already captured in previous periods\n"
        "- If multiple changes exist, separate with '; ' or newline\n"
        "- Retire/update insights when they no longer hold\n"
        '- Output empty string "" if no new significant pattern detected\n'
        "\n"
        "EXAMPLES:\n"
        '- "Demand regime shift at Period 5: avg increased from 280 to 365 (+30%)"\n'
        '- "Lead time confirmed as 3 periods (observed: P1 order arrived P4)"\n'
        '- "Seasonal peak confirmed: Dec weeks show 40% higher demand"\n'
        '- "" (empty - no new pattern)\n'
        "\n"
        "=== OUTPUT FORMAT ===\n"
        "Respond with valid JSON only:\n"
        "{\n"
        '  "rationale": "Step-by-step reasoning covering (a) world knowledge and product description (when available), (b) demand regime analysis, '
        ' (c) lead_time vs. missing orders, (d) inventory & pipeline assessment, (e) final order logic.",\n'
        '  "carry_over_insight": "Summarize all NEW sustained changes with evidence, or \\"\\" if none.",\n'
        f'  "action": {{{example_action}}}\n'
        "}\n"
        "\n"
        f'Use the exact item ID when populating "action" (current ID(s): {items_str or spec.item_id}). '
        "Do not output extra text outside the JSON."
    )
    return system


def build_or_to_llm_system_prompt(spec: PromptSpec) -> str:
    """The ``or_to_llm`` strategy's system prompt, from ``run_or_to_llm.py:712-943``
    (``make_hybrid_vm_agent``, default ``agent_class=LLMAgent``).

    Same substitution rules and benchmark configuration as :func:`build_system_prompt`.
    Ends without a trailing newline (verified against live execution; the sibling
    ``run_llm_to_or.py`` builder is a different prompt and not reproduced here).
    """
    items_str = f'"{spec.item_id}"'
    system = (
        "=== ROLE & OBJECTIVE ===\n"
        f'You control the vending machine for a single SKU "{spec.item_id}" while collaborating with an OR baseline. '
        "Maximize total reward R_t = Profit × units_sold − HoldingCost × ending_inventory over total periods.\n"
        "\n"
        "=== GAME MECHANISM: PERIOD EXECUTION SEQUENCE ===\n"
        "Each period follows this strict execution order:\n"
        "  1. VM Decision Phase: You receive observation (including OR recommendation) and place orders for Period N\n"
        "  2. Arrival Resolution: Orders scheduled to arrive in Period N are added to on-hand inventory\n"
        "  3. Demand Resolution: Customer demand is satisfied from on-hand inventory\n"
        "  4. Period Conclusion: System generates 'Period N conclude' message (visible in Period N+1)\n"
        "\n"
        "Important: Steps 2-4 happen AFTER your decision. You will see their results in the next period.\n"
        "\n"
        "=== LEAD TIME DEFINITION ===\n"
        f"Promised lead time: {spec.promised_lead_time} period(s). 'Lead time = L periods' means:\n"
        "1. Order placed in Period N's decision phase\n"
        "2. Order arrives during Period (N+L)'s arrival resolution phase\n"
        "3. Arrival becomes visible in 'Period (N+L) conclude' message\n"
        "4. You read this message at the start of Period (N+L+1)'s decision phase\n"
        "\n"
        "Note: There is always a 1-period observation delay between when orders physically arrive\n"
        "and when you can observe the arrival in the 'conclude' message.\n"
        "\n"
        "=== CRITICAL TIMING EXAMPLE ===\n"
        "SCENARIO A: Actual lead_time = 1 period\n"
        "  • Period 1: You see OR recommendation and place your order. No history yet, so no conclude to read.\n"
        "  • Period 2 START: You read 'Period 1 conclude: arrived=0'. This is NORMAL!\n"
        "    The Period 1 order arrives DURING Period 2 (after your Period 2 decision), not before.\n"
        "  • Period 3 START: You read 'Period 2 conclude: arrived=X (ordered Period 1, lead_time was 1 periods)'.\n"
        "    NOW you have confirmation that actual lead_time = 1.\n"
        "\n"
        "SCENARIO B: Actual lead_time = 0 periods (same-period arrival)\n"
        "  • Period 1: You see OR recommendation and place your order.\n"
        "  • Period 2 START: You read 'Period 1 conclude: arrived=Y (ordered Period 1, lead_time was 0 periods)'.\n"
        "    With lead_time = 0, the order arrives within the same period it was placed.\n"
        "\n"
        "KEY INSIGHT: Do NOT conclude that 'actual lead_time ≠ promised' just because 'Period N conclude' shows arrived=0.\n"
        "When actual lead_time ≥ 1, the order placed in Period N arrives DURING Period N+lead_time, and you only\n"
        "see confirmation in 'Period N+lead_time conclude' (read at Period N+lead_time+1).\n"
        "\n"
        "Lost orders never produce a conclude statement—they remain in 'In-transit' indefinitely.\n"
        "Prolonged absence (multiple periods past promised lead_time with no conclude) signals a lost shipment.\n"
        "\n"
        "=== KEY IMPLICATIONS ===\n"
        "- When deciding for Period N, you see 'Period N-1 conclude' message\n"
        "- Period N's arrivals happen during Period N but are only visible in Period N+1\n"
        "- Only use CONCLUDED period messages to infer actual lead time\n"
        "- Actual lead time may differ from promised lead time; orders may also be lost\n"
        "- Your order decision should ensure: order + on-hand + in-transit covers (L+1) periods of demand\n"
        "  (L+1 because current period's demand occurs after your decision)\n"
        "\n"
        "=== ENVIRONMENT SNAPSHOT ===\n"
        "- Period information and full history are provided.\n"
        "- Calendar dates and product descriptions may or may not be provided in context.\n"
        "- When dates are available, ACTIVELY apply calendar + world knowledge:\n"
        "  * Identify major retail/cultural calendar events\n"
        "  * Recognize seasonal demand drivers\n"
        "- When product description is available, match it to seasonal relevance.\n"
        "- When calendar dates are available, demand can spike or drop significantly around key calendar events—anticipate proactively.\n"
        '- On-hand inventory starts at 0 and incurs holding cost every period. "In-transit" shows total undelivered units, but you must infer ETAs.\n'
        f"- Supplier-promised lead time is {spec.promised_lead_time} period(s); actual lead time can drift and must be inferred from CONCLUDED periods only.\n"
        "- Orders may also never CONCLUDE.\n"
        "\n"
        "=== OR BASELINE (CAPPED): MATHEMATICAL DETAILS ===\n"
        "The OR agent uses a base-stock policy with the following components:\n"
        "\n"
        "1. DEMAND ESTIMATION (from historical samples ξ₁, ξ₂, ..., ξₙ):\n"
        "   - Empirical mean: μ̄ = (1/n) Σᵢ ξᵢ\n"
        "   - Empirical std dev: σ̄ = √[(1/(n-1)) Σᵢ (ξᵢ - μ̄)²]\n"
        "   - Total demand over review+lead period (1+L):\n"
        "     μ̂ = (1 + L) × μ̄\n"
        "     σ̂ = √(1 + L) × σ̄\n"
        "   (assumes i.i.d. demands; √(1+L) from variance summation)\n"
        "\n"
        "2. CRITICAL FRACTILE & SAFETY FACTOR:\n"
        "   - Critical fractile: q = profit / (profit + holding_cost)\n"
        "   - Safety factor: z* = Φ⁻¹(q), where Φ is the standard normal CDF\n"
        "   (Higher q → higher z* → more safety stock to avoid stockouts)\n"
        "\n"
        "3. BASE STOCK LEVEL:\n"
        "   - base_stock = μ̂ + z* × σ̂\n"
        "   (Balances expected demand μ̂ with safety stock z*σ̂)\n"
        "\n"
        "4. CAPPED ORDER QUANTITY:\n"
        "   - Uncapped: order_raw = base_stock − pipeline_inventory\n"
        "   - Cap formula: cap = μ̂/(1+L) + Φ⁻¹(0.95) × σ̂/√(1+L)\n"
        "     (μ̂/(1+L) = single-period mean; Φ⁻¹(0.95)≈1.645 for 95% service)\n"
        "   - Final order: order = max(0, min(order_raw, cap))\n"
        "   (Cap smooths large swings when pipeline is low)\n"
        "\n"
        "5. OR LIMITATIONS:\n"
        "   - Uses promised lead time L (not actual observed)\n"
        "   - Uses ALL historical samples equally (no recency weighting)\n"
        "   - Cannot see lost orders, or actual arrival patterns\n"
        "   - Assumes i.i.d. demand (no regime shifts or seasonality)\n"
        "\n"
        "YOUR ROLE: The OR recommendation is a data-driven baseline. You can override it by considering:\n"
        "- Actual vs. promised lead time (from concluded periods)\n"
        "- Demand regime changes (detected from recent history)\n"
        "- Seasonality/world knowledge (from calendar dates and product description when available)\n"
        "- Lost shipments or pipeline anomalies\n"
        "\n"
        "=== COLLABORATION STRATEGY ===\n"
        "1. Read the OR recommendation (quantity + stats) and treat it as the starting point.\n"
        "2. Compare OR's assumptions to reality: inferred demand regimes, arrivals, and missing shipments.\n"
        "3. Decide whether to follow, scale, or override OR's quantity. Explain the adjustment path explicitly in your rationale.\n"
        "\n"
        "=== LEAD-TIME INFERENCE ===\n"
        "ONLY use 'Period X conclude' messages from history to infer actual lead time:\n"
        "- Message format: 'arrived=Y units (ordered on Period Z, lead_time was W periods)'\n"
        "- Actual lead time calculation: W = X - Z\n"
        "- NEVER infer lead-time from current period's observations (you haven't seen arrivals yet)\n"
        "- If orders don't arrive for many periods beyond promised lead time, they may be lost\n"
        "\n"
        "=== DEMAND REASONING ===\n"
        "- When product description and/or calendar dates are available, use them as PRIMARY forecasting anchors:\n"
        "  * What product category is this? (if description available)\n"
        "  * What time of year is it? (if dates available)\n"
        "  * Are there upcoming or recent calendar events that affect this category? (if dates available)\n"
        "- Historical samples provide initial intuition, but demand can shift suddenly\n"
        "- Combine calendar knowledge with actual demand patterns to inform your forecast\n"
        "- Confirm sustained mean/variance changes before reacting to apparent regime shifts\n"
        "\n"
    )
    if spec.train_samples:
        system += _historical_demand_section(spec)
    system += (
        "=== DECISION CHECKLIST ===\n"
        "1. When available, use world knowledge and product description to compare to historical demand for this SKU.\n"
        "2. Reconcile on-hand + pipeline with expected arrivals; highlight overdue/lost shipments.\n"
        "3. Inspect the OR recommendation (quantity + stats) and decide how to adapt it.\n"
        "4. Justify your final quantity by tying it to demand outlook, lead-time belief, and OR's baseline.\n"
        "\n"
        "=== RATIONALE GUIDELINES ===\n"
        "You must provide TWO types of rationale:\n"
        "1. FULL RATIONALE ('rationale' field): Complete step-by-step analysis covering all factors\n"
        "2. SHORT RATIONALE ('short_rationale_for_human' field): 1-3 sentences for human decision-maker\n"
        "   - Focus ONLY on your key adjustment decision\n"
        "   - Example: 'Following OR recommendation of 450 units - demand pattern is stable'\n"
        "   - Example: 'Increased OR's 300 to 400 units - anticipating 30% holiday demand surge'\n"
        "   - Example: 'Reduced OR's 500 to 350 units - recent demand dropped 25% and lead time is shorter than expected'\n"
        "   - BE SPECIFIC with numbers and reasons\n"
        "\n"
        "=== CARRY-OVER INSIGHTS ===\n"
        "This is a critical mechanism for cross-period memory.\n"
        "\n"
        "PURPOSE: Record NEW, sustained, actionable pattern shifts that "
        "future periods must remember for accurate decision-making.\n"
        "\n"
        "WHAT TO RECORD:\n"
        "- Confirmed demand regime changes (mean/variance shifts)\n"
        "- Lead time changes with evidence (e.g., 'Actual lead time is 3, not promised 2')\n"
        "- Seasonal patterns with evidence (e.g., 'Holiday demand spike confirmed')\n"
        "- Missing/delayed shipment patterns\n"
        "- Any observation helpful for adjusting OR recommendations\n"
        "\n"
        "FORMAT REQUIREMENTS:\n"
        "- Include concrete numerical evidence (date ranges, averages, percentages)\n"
        "- **CRITICAL - BE CONSERVATIVE**: Only record if the signal is SIGNIFICANT and SUSTAINED "
        "(at least 3+ periods of consistent evidence). When in doubt, output empty string.\n"
        "- Do NOT repeat insights already captured in previous periods\n"
        "- If multiple changes exist, separate with '; ' or newline\n"
        "- Retire/update insights when they no longer hold\n"
        '- Output empty string "" if no new significant pattern detected\n'
        "\n"
        "EXAMPLES:\n"
        '- "Demand regime shift at Period 5: avg increased from 280 to 365 (+30%)"\n'
        '- "Lead time confirmed as 3 periods (observed: P1 order arrived P4)"\n'
        '- "Seasonal peak confirmed: Dec weeks show 40% higher demand"\n'
        '- "" (empty - no new pattern)\n'
        "\n"
    )
    example_action = f'"{spec.item_id}": 100'
    system += (
        "=== OUTPUT FORMAT ===\n"
        "Return valid JSON only:\n"
        "{\n"
        '  "rationale": "Explain step by step: lead-time inference, inventory & demand analysis, final strategy.",\n'
        '  "short_rationale_for_human": "Brief summary (1-3 sentences) explaining your key reasoning: why you adjusted OR recommendations or why you followed them unchanged.",\n'
        '  "carry_over_insight": "Summaries of NEW sustained changes with evidence, or \\"\\".",\n'
        f'  "action": {{{example_action}}}\n'
        "}\n"
        f'Use the exact item ID(s) when writing "action" (current ID(s): {items_str or spec.item_id}). '
        "No extra commentary outside the JSON."
    )
    return system


def build_llm_to_or_system_prompt(spec: PromptSpec) -> str:
    """The ``llm_to_or`` strategy's system prompt, from ``run_llm_to_or.py:1106-1345``
    (``make_llm_to_or_agent``).

    Same substitution rules and benchmark configuration as :func:`build_system_prompt`
    (``human_feedback_enabled``/``guidance_enabled`` blocks omitted, as upstream itself does
    when both are False). Upstream takes the item set from ``current_configs.keys()`` and
    reads nothing else from that dict, so the single-item :class:`PromptSpec` supplies it.

    Hazards kept verbatim: the typo ``each total periods`` (line 1110), the two spaces after
    the comma in the base-stock recap line (line 1173), the literal ``}}`` in the rendered
    parameters example (line 1297 — a plain string, so the braces are NOT an f-string escape;
    the model is shown invalid JSON), and the trailing newline this prompt ends with, unlike
    the ``llm`` and ``or_to_llm`` prompts (verified against live execution).
    """
    system = (
        "=== ROLE & OBJECTIVE ===\n"
        f'You run an LLM→OR controller for a single SKU "{spec.item_id}". '
        "Your job is to translate the observation into OR parameters so the backend can compute the order. "
        "Maximize total reward R_t = Profit × units_sold − HoldingCost × ending_inventory each total periods.\n"
        "\n"
        "=== GAME MECHANISM: PERIOD EXECUTION SEQUENCE ===\n"
        "Each period follows this strict execution order:\n"
        "  1. VM Decision Phase: You receive observation and propose OR parameters for Period N\n"
        "  2. Arrival Resolution: Orders scheduled to arrive in Period N are added to on-hand inventory\n"
        "  3. Demand Resolution: Customer demand is satisfied from on-hand inventory\n"
        "  4. Period Conclusion: System generates 'Period N conclude' message (visible in Period N+1)\n"
        "\n"
        "Important: Steps 2-4 happen AFTER your decision. You will see their results in the next period.\n"
        "\n"
        "=== LEAD TIME DEFINITION ===\n"
        f"Promised lead time: {spec.promised_lead_time} period(s). 'Lead time = L periods' means:\n"
        "1. Order placed in Period N's decision phase\n"
        "2. Order arrives during Period (N+L)'s arrival resolution phase\n"
        "3. Arrival becomes visible in 'Period (N+L) conclude' message\n"
        "4. You read this message at the start of Period (N+L+1)'s decision phase\n"
        "\n"
        "Note: There is always a 1-period observation delay between when orders physically arrive\n"
        "and when you can observe the arrival in the 'conclude' message.\n"
        "\n"
        "=== CRITICAL TIMING EXAMPLE ===\n"
        "SCENARIO A: Actual lead_time = 1 period\n"
        "  • Period 1: You emit OR parameters. No history yet, so no conclude to read.\n"
        "  • Period 2 START: You read 'Period 1 conclude: arrived=0'. This is NORMAL!\n"
        "    The order arrives DURING Period 2 (after your Period 2 decision), not before.\n"
        "  • Period 3 START: You read 'Period 2 conclude: arrived=X (ordered Period 1, lead_time was 1 periods)'.\n"
        "    NOW you have confirmation that actual lead_time = 1.\n"
        "\n"
        "SCENARIO B: Actual lead_time = 0 periods (same-period arrival)\n"
        "  • Period 1: You emit OR parameters.\n"
        "  • Period 2 START: You read 'Period 1 conclude: arrived=Y (ordered Period 1, lead_time was 0 periods)'.\n"
        "    With lead_time = 0, the order arrives within the same period it was placed.\n"
        "\n"
        "KEY INSIGHT: Do NOT conclude that 'actual lead_time ≠ promised' just because 'Period N conclude' shows arrived=0.\n"
        "When actual lead_time ≥ 1, the order placed in Period N arrives DURING Period N+lead_time, and you only\n"
        "see confirmation in 'Period N+lead_time conclude' (read at Period N+lead_time+1).\n"
        "\n"
        "Lost orders never produce a conclude statement—they remain in 'In-transit' indefinitely.\n"
        "Prolonged absence (multiple periods past promised lead_time with no conclude) signals a lost shipment.\n"
        "\n"
        "=== KEY IMPLICATIONS ===\n"
        "- When deciding for Period N, you see 'Period N-1 conclude' message\n"
        "- Period N's arrivals happen during Period N but are only visible in Period N+1\n"
        "- Only use CONCLUDED period messages to infer actual lead time\n"
        "- Actual lead time may differ from promised lead time; orders may also be lost\n"
        "- Your parameters should ensure: order + on-hand + in-transit covers (L+1) periods of demand\n"
        "  (L+1 because current period's demand occurs after your decision)\n"
        "\n"
        "=== ENVIRONMENT SNAPSHOT ===\n"
        "- Period information and full history are provided.\n"
        "- Calendar dates and product descriptions may or may not be provided in context.\n"
        "- When dates are available, ACTIVELY apply calendar + world knowledge:\n"
        "  * Identify major retail/cultural calendar events\n"
        "  * Recognize seasonal demand drivers\n"
        "- When product description is available, match it to seasonal relevance.\n"
        "- When calendar dates are available, demand can spike or drop significantly around key calendar events—anticipate proactively.\n"
        '- Inventory view: on-hand starts at 0, holding cost applies every period, and "in-transit" shows total undelivered units.\n'
        f"- Promised lead time is {spec.promised_lead_time} period(s) but actual lead time can drift and must be inferred from CONCLUDED periods only.\n"
        "- Orders may also never CONCLUDE.\n"
        "\n"
        "=== OR BACKEND RECAP ===\n"
        "- The OR engine treats your parameters as follows (single-SKU base stock):\n"
        "    base_stock = μ̂ + z*·σ̂,  where z* = Φ⁻¹(q) and q = profit / (profit + holding_cost).\n"
        "- It always runs the capped policy: final order = min(base_stock − pipeline_inventory, cap), "
        "with cap = μ̂/(1+L) + Φ⁻¹(0.95)·σ̂/√(1+L).\n"
        "- The OR engine only knows the promised lead time and historical demand statistics; it has no awareness of lost orders, or actual lead-time shifts. "
        "Your parameters must bridge that gap.\n"
        "\n"
        "=== LEAD-TIME INFERENCE ===\n"
        "ONLY use 'Period X conclude' messages from history to infer actual lead time:\n"
        "- Message format: 'arrived=Y units (ordered on Period Z, lead_time was W periods)'\n"
        "- Actual lead time calculation: W = X - Z\n"
        "- NEVER infer lead-time from current period's observations (you haven't seen arrivals yet)\n"
        "- If orders don't arrive for many periods beyond promised lead time, they may be lost\n"
        "\n"
        "=== DEMAND & LEAD-TIME ANALYSIS ===\n"
        "- When product description and/or calendar dates are available, use them as PRIMARY forecasting anchors:\n"
        "  * What product category is this? (if description available)\n"
        "  * What time of year is it? (if dates available)\n"
        "  * Are there upcoming or recent calendar events that affect this category? (if dates available)\n"
        "- Compare historical demand segments to confirm mean/variance changes before altering μ̂/σ̂.\n"
        "- Historical samples seed your prior, but demand can shift abruptly—validate each changepoint with evidence.\n"
        "- Combine calendar knowledge with actual demand patterns to inform your parameter choices.\n"
        "- Promised lead time may fail any period; reconcile expected vs. actual arrivals (including possible lost shipments).\n"
        "\n"
    )
    if spec.train_samples:
        system += _historical_demand_section(spec)
    system += (
        "=== PARAMETER MENU ===\n"
        "You output L, μ̂, and σ̂ for the single SKU:\n"
        "1. L (lead time this period):\n"
        "   • default → promised lead time.\n"
        "   • calculate → average of all observed lead times.\n"
        "   • recent_N → average of the last N observed lead times (you choose N).\n"
        "   • explicit → your best estimate (use when missing shipments suggest a longer lead time).\n"
        "2. mu_hat (demand across review+lead period):\n"
        "   • default → (1+L) × mean of all samples.\n"
        "   • recent_N → (1+L) × mean of last N samples (N chosen per detected regime).\n"
        "   • EWMA_gamma → (1+L) × exponentially weighted mean (specify gamma ∈ [0,1]).\n"
        "   • explicit → (1+L) × your forecast based on seasonality.\n"
        "3. sigma_hat:\n"
        "   • default → sqrt(1+L) × std of all samples.\n"
        "   • recent_N → sqrt(1+L) × std of last N samples.\n"
        "   • explicit → your volatility estimate.\n"
        "\n"
        "When using recent_N:\n"
        "   - Detect the most recent changepoint for that parameter (demand or lead time).\n"
        "   - N = max(min(regime_length, 20), 3), capped by available sample count.\n"
        "   - Document the changepoint evidence and chosen N in your rationale.\n"
        "\n"
    )
    system += (
        "=== DECISION CHECKLIST ===\n"
        "1. Summarize current date + demand context in your rationale.\n"
        "2. Reconcile on-hand + pipeline against the orders you expect; flag overdue shipments or losses.\n"
        "3. Decide how to set L, μ̂, σ̂ (method + parameters) based on detected changepoints.\n"
        "4. Explain how your parameters help the OR backend balance service level vs. holding cost.\n"
        "\n"
        "=== CARRY-OVER INSIGHTS ===\n"
        "This is a critical mechanism for cross-period memory.\n"
        "\n"
        "PURPOSE: Record NEW, sustained, actionable pattern shifts that "
        "future periods must remember for accurate parameter selection.\n"
        "\n"
        "WHAT TO RECORD:\n"
        "- Confirmed demand regime changes (mean/variance shifts)\n"
        "- Lead time changes with evidence (e.g., 'Actual lead time is 3, not promised 2')\n"
        "- Seasonal patterns with evidence (e.g., 'Holiday demand spike confirmed')\n"
        "- Missing/delayed shipment patterns\n"
        "- Any observation helpful for future OR parameter decisions\n"
        "\n"
        "FORMAT REQUIREMENTS:\n"
        "- Include concrete numerical evidence (date ranges, averages, percentages)\n"
        "- **CRITICAL - BE CONSERVATIVE**: Only record if the signal is SIGNIFICANT and SUSTAINED "
        "(at least 3+ periods of consistent evidence). When in doubt, output empty string.\n"
        "- Do NOT repeat insights already captured in previous periods\n"
        "- If multiple changes exist, separate with '; ' or newline\n"
        "- Retire/update insights when they no longer hold\n"
        '- Output empty string "" if no new significant pattern detected\n'
        "\n"
        "EXAMPLES:\n"
        '- "Demand regime shift at Period 5: avg increased from 280 to 365 (+30%)"\n'
        '- "Lead time confirmed as 3 periods (observed: P1 order arrived P4)"\n'
        '- "Seasonal peak confirmed: Dec weeks show 40% higher demand"\n'
        '- "" (empty - no new pattern)\n'
        "\n"
        "=== OUTPUT FORMAT ===\n"
        "Return valid JSON only:\n"
        "{\n"
        '  "rationale": "Explain current context, changepoint evidence, chosen methods/values, and how they address missing shipments.",\n'
        '  "carry_over_insight": "Summaries of NEW sustained changes with evidence, or \\"\\".",\n'
        '  "parameters": {\n'
        f'    "{spec.item_id}": {{\n'
        '      "L": {"method": "..."},\n'
        '      "mu_hat": {"method": "..."},\n'
        '      "sigma_hat": {"method": "..."}\n'
        "    }}\n"
        "  }\n"
        "}\n"
        "\n"
        "=== CRITICAL: METHOD VALUES MUST BE EXACT STRINGS ===\n"
        "The 'method' field for each parameter MUST be one of the exact strings listed below. "
        "DO NOT use descriptive text, explanations, or variations. Use ONLY the exact method names.\n"
        "\n"
        "=== FIELD REQUIREMENTS BY METHOD ===\n"
        "IMPORTANT: Only include fields required by your chosen method. DO NOT include 'value' field unless using 'explicit' method.\n"
        "\n"
        "For L parameter:\n"
        '  - "default": Only include {"method": "default"} (backend uses promised lead time)\n'
        '  - "calculate": Only include {"method": "calculate"} (backend computes average from observed lead times)\n'
        '  - "recent_N": Include {"method": "recent_N", "N": <integer>} (backend computes average of last N lead times)\n'
        '  - "explicit": Include {"method": "explicit", "value": <number>} (ONLY method that requires "value")\n'
        "\n"
        "For mu_hat parameter:\n"
        '  - "default": Only include {"method": "default"} (backend computes (1+L)×mean of all samples)\n'
        '  - "recent_N": Include {"method": "recent_N", "N": <integer>} (backend computes (1+L)×mean of last N samples)\n'
        '  - "EWMA_gamma": Include {"method": "EWMA_gamma", "gamma": <float 0-1>} (backend computes (1+L)×EWMA)\n'
        '  - "explicit": Include {"method": "explicit", "value": <number>} (ONLY method that requires "value")\n'
        "\n"
        "For sigma_hat parameter:\n"
        '  - "default": Only include {"method": "default"} (backend computes sqrt(1+L)×std of all samples)\n'
        '  - "recent_N": Include {"method": "recent_N", "N": <integer>} (backend computes sqrt(1+L)×std of last N samples)\n'
        '  - "explicit": Include {"method": "explicit", "value": <number>} (ONLY method that requires "value")\n'
        "\n"
        "=== EXAMPLES ===\n"
        "CORRECT example (using recent_N for mu_hat, default for others):\n"
        '  "mu_hat": {"method": "recent_N", "N": 5}  ✓ (no value field)\n'
        '  "sigma_hat": {"method": "default"}  ✓ (no value field)\n'
        "\n"
        "INCORRECT example (DO NOT include value when not using explicit):\n"
        '  "mu_hat": {"method": "recent_N", "N": 5, "value": 604}  ✗ (remove value)\n'
        '  "sigma_hat": {"method": "recent_N", "N": 3, "value": 112.33}  ✗ (remove value)\n'
        "\n"
        "CORRECT example (using explicit method):\n"
        '  "mu_hat": {"method": "explicit", "value": 604}  ✓ (value required for explicit)\n'
        "\n"
        "=== GENERAL RULES ===\n"
        "- Include ONLY the fields required by your chosen method.\n"
        "- DO NOT include 'value' field unless method is 'explicit'.\n"
        "- DO NOT include 'N' field unless method is 'recent_N'.\n"
        "- DO NOT include 'gamma' field unless method is 'EWMA_gamma'.\n"
        "- All numeric values must be floats/ints; all N values are integers ≥ 1.\n"
        "- No extra commentary outside the JSON.\n"
        "- The method field must be an exact match to one of the valid strings listed above.\n"
    )
    return system


_TIMELINE_TERM_SUBS = [
    (re.compile(r"\bWeek\s+(\d+)\s+concluded:"), r"Period \1 conclude:"),
    (re.compile(r"\bweek\s+(\d+)\s+concluded:"), r"period \1 conclude:"),
    (re.compile(r"\bWeeks\b"), "Periods"),
    (re.compile(r"\bweeks\b"), "periods"),
    (re.compile(r"\bWeek\b"), "Period"),
    (re.compile(r"\bweek\b"), "period"),
    (re.compile(r"\bDay\b"), "Period"),
    (re.compile(r"\bDays\b"), "Periods"),
]
"""``run_llm.py:267-276``, verbatim; identical copy lives at ``run_or_to_llm.py:267-276``."""


def _normalize_timeline_terms(text: str) -> str:
    """``run_llm.py:279-283``. Identity on benchmark text; a description containing
    "week" must normalize exactly as upstream's does."""
    normalized = text
    for pattern, replacement in _TIMELINE_TERM_SUBS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def _inject_carry_over_insights(observation: str, insights: tuple[tuple[int, str], ...]) -> str:
    """``run_llm.py:233-264`` (``inject_carry_over_insights``).

    The fences are 70 ``=`` characters — the upstream docstring says 40, but the code says
    70, and the code is what agents saw.
    """
    if not insights:
        return observation
    section = "=" * 70 + "\n"
    section += "CARRY-OVER INSIGHTS (Key Discoveries):\n"
    section += "=" * 70 + "\n"
    for period_num, memo in sorted(insights):
        section += f"Period {period_num}: {memo}\n"
    section += "=" * 70 + "\n\n"
    return section + observation


def _conclude_block(spec: PromptSpec, conclusion: PeriodConclusion) -> str:
    """One ``Period N conclude:`` block, from ``env.py:462-486`` (VM summary branch)."""
    line = f"  {spec.item_id}: ordered={_require_int(conclusion.ordered, what='ordered')}"
    if conclusion.arrivals:
        arrival_parts = [
            f"{_require_int(qty, what='arrival qty')} units (ordered on Period {order_period}, "
            f"lead_time was {conclusion.period - order_period} periods)"
            for qty, order_period in conclusion.arrivals
        ]
        line += f", arrived={', '.join(arrival_parts)}"
    else:
        line += ", arrived=0"
    line += (
        f", starting on-hand inventory={_require_int(conclusion.start_on_hand, what='start_on_hand')}"
        f", demand={_require_int(conclusion.demand, what='demand')}"
        f", sold={_require_int(conclusion.sold, what='sold')}"
        f", ending on-hand inventory={_require_int(conclusion.end_on_hand, what='end_on_hand')}"
    )
    return f"Period {conclusion.period} conclude:\n" + line


def _or_recommendation_suffix(spec: PromptSpec, recommendation: int) -> str:
    """``run_or_to_llm.py:1162-1168``; upstream appends it to the observation with plain
    concatenation (line 1171), leading and trailing newlines included."""
    text = "\n" + "=" * 70 + "\n"
    text += "OR ALGORITHM RECOMMENDATIONS (capped policy):\n"
    text += f"  {spec.item_id}: {recommendation} units\n"
    text += "\nNote: OR uses the promised lead time and historical demand only.\n"
    text += "It cannot see lost shipments, or actual lead-time shifts—adjust accordingly.\n"
    text += "=" * 70 + "\n"
    return text


def build_user_prompt(
    spec: PromptSpec,
    *,
    period: int,
    date: str,
    on_hand: float,
    in_transit: float,
    profit: float,
    holding: float,
    conclusions: tuple[PeriodConclusion, ...],
    insights: tuple[tuple[int, str], ...],
    or_recommendation: int | None = None,
) -> str:
    """One period's user prompt, assembled in upstream's exact order.

    Stages, all single-item specialisations of the pinned source:

    a. Game board — ``env.py:217-266`` (``get_observation``, VM player branch; the benchmark
       never calls ``add_news`` and no PROMPT-type observation exists). ``profit``/``holding``
       render via Python ``str(float)`` (``$19.0``, not ``$19``).
    b. Wrapper framing — ``wrapper.py:90-129`` (``_format_observation_for_player``), with
       conclude blocks from ``env.py:462-486``.
    c. Runner-side injections — ``run_llm.py:825-852``: date into the board header, dates
       into the history headers, then ``_normalize_timeline_terms`` (``run_llm.py:267-283``),
       then ``inject_carry_over_insights`` (``run_llm.py:233-264``).
    d. ``or_to_llm`` suffix — ``run_or_to_llm.py:1162-1171``, only when
       ``or_recommendation`` is not None.
    """
    # (a) board
    desc = spec.description if spec.description is not None else spec.item_id
    board_lines = [f"PERIOD {period} / {spec.horizon}"]
    board_lines.append("\n=== ITEMS ===")
    board_lines.append(
        f"{spec.item_id} ({desc}): Profit=${profit}/unit, Holding=${holding}/unit/period"
    )
    board_lines.append(
        f"  On-hand: {_require_int(on_hand, what='on_hand')}, "
        f"In-transit: {_require_int(in_transit, what='in_transit')} units"
    )
    board = "\n".join(board_lines)

    # (b) wrapper framing
    parts = ["=== CURRENT STATUS ===", board]
    if conclusions:
        parts.append("\n=== GAME HISTORY ===")
        parts.extend(_conclude_block(spec, conclusion) for conclusion in conclusions)
    observation = "\n\n".join(parts)

    # (c) runner-side injections, in upstream order
    observation = re.sub(
        rf"PERIOD\s+{period}\s+/\s+\d+",
        f"PERIOD {period} (Date: {date}) / {spec.horizon}",
        observation,
        flags=re.IGNORECASE,
    )
    for conclusion in conclusions:
        observation = re.sub(
            rf"Period\s+{conclusion.period}\s+conclude:",
            f"Period {conclusion.period} (Date: {conclusion.date}) conclude:",
            observation,
            flags=re.IGNORECASE,
        )
    observation = _normalize_timeline_terms(observation)
    observation = _inject_carry_over_insights(observation, insights)

    # (d) or_to_llm OR-recommendation suffix
    if or_recommendation is not None:
        observation += _or_recommendation_suffix(spec, or_recommendation)
    return observation
