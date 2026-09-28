"""Render the forensics outputs as compact markdown tables (exploratory).

Run: ``uv run python -m analysis.forensics.tables`` after the other scripts have written their
JSON under ``analysis/forensics/out``. Every measured number in
``analysis/kill_trigger_forensics.md`` is printed by this script from those files; none is
hand-entered. (The report's premise corrections also quote figures from other tracked documents,
cited there by path.)
"""

from __future__ import annotations

import json

from analysis.forensics.common import FAMILY_KEY, OUT

KEYS = [FAMILY_KEY[f] for f in sorted(FAMILY_KEY)]


def _load(name: str) -> dict | None:
    path = OUT / name
    return json.loads(path.read_text()) if path.is_file() else None


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _iv(pair: list[float], fmt: str = "+.1f") -> str:
    return f"[{pair[0]:{fmt}}, {pair[1]:{fmt}}]"


def facts_tables(facts: dict) -> list[str]:
    r = facts["registered_reproduction"]
    lines = [
        "### Facts-a. Registered reproduction (the frozen evaluator's own functions)",
        "",
        f"insufficient_headroom: count {r['headroom_count']}, interval {r['headroom_interval']}. "
        f"detector_indistinguishable: {r['detector_estimate']:+.3f} "
        f"{_iv(r['detector_interval'], '+.3f')}, n = {r['detector_n_units']}.",
        "",
        "Collinearity on the registered contrasts (arm 10 - arm 1, gross): profit_lift as "
        f"registered (stratum-weighted) {r['profit_lift_registered']:+.4f} / "
        f"lost_sales_reduction {r['lost_sales_reduction_registered']:+.4f} = "
        f"{r['profit_lift_registered'] / r['lost_sales_reduction_registered']:.4f}; unweighted "
        f"{r['profit_lift_unweighted']:+.4f} / {r['lost_sales_reduction_unweighted']:+.4f} = "
        f"{r['profit_lift_unweighted'] / r['lost_sales_reduction_unweighted']:.4f}; detector "
        "gap / (arm 10 - control lost sales) = "
        f"{r['detector_estimate'] / facts['detector_intervals']['lost']['estimate']:.4f}.",
        "",
        "| key | arm 1 gross | oracle gross | raw lift | CVaR10 lift |",
        "|---|---:|---:|---:|---:|",
    ]
    for key in KEYS:
        k = r["headroom_per_key"][key]
        lines.append(
            f"| {key} | {k['arm1_mean']:.0f} | {k['oracle_mean']:.0f} | "
            f"{_pct(100 * k['raw_lift'])} | {_pct(100 * k['cvar10_lift'])} |"
        )
    d = facts["detector_intervals"]
    lines += [
        "",
        "### Facts-b. arm 10 minus the detector control, three interval constructions",
        "",
        "| per-episode column | estimate | registered-style normal, n=120 | seed-cluster "
        "bootstrap, 24 seeds | seed-collapsed normal | shocked mean | null mean |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for col, label in (
        ("profit", "total_profit (registered, gross)"),
        ("reward", "total_reward (net, not registered)"),
        ("holding", "total_holding_cost"),
        ("lost", "total_lost_sales"),
    ):
        e = d[col]
        lines.append(
            f"| {label} | {e['estimate']:+.2f} | {_iv(e['registered_style_normal_n120'])} | "
            f"{_iv(e['seed_cluster_bootstrap'])} | {_iv(e['seed_collapsed_normal'])} | "
            f"{e['shocked_mean']:+.2f} | {e['null_mean']:+.2f} |"
        )
    hb = facts["headroom_seed_bootstrap"]
    lines += [
        "",
        "### Facts-c. Headroom count under a seed bootstrap (4 seeds per family)",
        "",
        f"point count {hb['point_count']}; bootstrap distribution "
        f"{hb['seed_bootstrap_distribution']}; 95% interval {hb['seed_bootstrap_interval']}.",
        "",
        "| key | oracle raw lift per seed |",
        "|---|---|",
    ]
    for key in KEYS:
        seeds = ", ".join(f"{100 * v:+.2f}%" for v in hb["per_seed_raw_lift"][key])
        lines.append(f"| {key} | {seeds} |")
    fa = facts["false_activation"]
    nd = facts["null_duplicates"]
    rt = facts["recovery_time"]
    se = facts["start_of_episode"]
    lines += [
        "",
        "### Facts-d. Record-level identities and criterion constructions",
        "",
        f"- arm 8 vs detector control: {facts['arm8_vs_ctrl']}",
        f"- collinearity: {facts['collinearity']}",
        f"- oracle vs arm 1: {json.dumps(facts['oracle_vs_arm1'])}",
        f"- distinct trajectories per seed (4 conditions each): "
        f"{json.dumps(facts['condition_replication'])}",
        f"- nulls: {nd['null_episodes']} episodes, {nd['distinct_null_trajectories']} distinct "
        f"trajectories, {nd['distinct_seeds']} seeds; group sizes {json.dumps(nd['group_sizes'])}",
        f"- false activation: control estimate {fa['control_estimate']:.4f}; activated "
        f"{fa['activated_null_episodes']}; registered-style normal "
        f"{_iv(fa['registered_style_normal_interval'], '.4f')}; Wilson n=24 "
        f"{_iv(fa['wilson_interval_n24'], '.4f')}; Wilson on distinct trajectories "
        f"{_iv(fa['wilson_interval_distinct'], '.4f')}",
        f"- recovery_time: mean {rt['recovery_time_mean']:.4f}; by family "
        f"{json.dumps(rt['mean_by_family'])}; never recovered "
        f"{json.dumps(rt['never_recovered_by_family'])}; final shock periods "
        f"{json.dumps(rt['final_shock_periods_by_family'])}",
        f"- start of episode: {json.dumps(se)}",
        f"- derived: recovery_time floor for any arm = 51 x "
        f"{sum(rt['never_recovered_by_family'].values())} never-recoverable / "
        f"{facts['record_counts']['episodes'] - nd['null_episodes']} shocked = "
        f"{51 * sum(rt['never_recovered_by_family'].values()) / (facts['record_counts']['episodes'] - nd['null_episodes']):.2f}; "
        "fill-rate ceiling for any arm = 1 - "
        f"{se['mean_share_of_demand_lost_in_leading_periods']:.4f} = "
        f"{1 - se['mean_share_of_demand_lost_in_leading_periods']:.4f}",
        "",
        "| arm | fill, all 120 | shocked | null |",
        "|---|---:|---:|---:|",
    ]
    for arm, f in facts["fill_rates"].items():
        null = "—" if f["null"] is None else f"{f['null']:.4f}"
        lines.append(f"| {arm} | {f['all_episodes']:.4f} | {f['shocked']:.4f} | {null} |")
    return lines


def q1_tables(q1: dict) -> list[str]:
    fam = q1["per_family"]
    lines = [
        "### Q1-a. Registered endpoint (gross profit): lift over arm 1, 4 seeds per family",
        "",
        "| family | arm 1 | oracle | max-stock @onset (content-free) | clairvoyant @onset, "
        "smoother-capped | clairvoyant @onset, uncapped | clairvoyant @period 1, uncapped |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in KEYS:
        g = fam[key]["gross"]
        lines.append(
            f"| {key} | {g['arm1']:.0f} | {_pct(g['oracle_lift_pct'])} | "
            f"{_pct(g['maxstock_onset_lift_pct'])} | {_pct(g['clv_gross_cap_onset_lift_pct'])} | "
            f"{_pct(g['clv_gross_uncap_onset_lift_pct'])} | "
            f"{_pct(g['clv_gross_uncap_start_lift_pct'])} |"
        )
    counts = fam["families_passing_registered_rule"]["gross"]
    lines += [
        "",
        "Families clearing the registered rule (raw >= 5% or CVaR10 >= 10%), gross endpoint: "
        + ", ".join(
            f"{name} {counts[name]}"
            for name in (
                "oracle",
                "maxstock_onset",
                "maxstock_early1",
                "maxstock_early2",
                "maxstock_start",
                "clv_gross_cap_onset",
                "clv_gross_cap_early1",
                "clv_gross_uncap_onset",
                "clv_gross_uncap_start",
            )
        ),
    ]
    anchors = [
        ("oracle", "oracle"),
        ("capped @onset", "clv_gross_cap_onset"),
        ("capped @onset-1", "clv_gross_cap_early1"),
        ("capped @onset-2", "clv_gross_cap_early2"),
        ("capped @period 1", "clv_gross_cap_start"),
        ("uncapped @onset", "clv_gross_uncap_onset"),
        ("uncapped @onset-1", "clv_gross_uncap_early1"),
        ("uncapped @onset-2", "clv_gross_uncap_early2"),
        ("uncapped @period 1", "clv_gross_uncap_start"),
    ]
    lines += [
        "",
        "### Q1-a2. Registered rule by warning time, gross endpoint (PASS = raw >= 5% or "
        "CVaR10 >= 10%; cell = raw / CVaR10 lift, %)",
        "",
        "| family | " + " | ".join(label for label, _ in anchors) + " |",
        "|---|" + "---:|" * len(anchors),
    ]
    for key in KEYS:
        g = fam[key]["gross"]
        cells = []
        for _, name in anchors:
            rule = g[f"{name}_rule"]
            mark = "PASS " if rule["passes"] else ""
            cells.append(f"{mark}{rule['raw_lift_pct']:+.1f} / {rule['cvar10_lift_pct']:+.1f}")
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    lines.append(
        "| **families passing** | " + " | ".join(str(counts[name]) for _, name in anchors) + " |"
    )
    did_anchors = [
        ("capped @onset", "cap_onset"),
        ("capped @onset-1", "cap_early1"),
        ("capped @onset-2", "cap_early2"),
        ("capped @period 1", "cap_start"),
        ("uncapped @onset", "uncap_onset"),
        ("uncapped @onset-1", "uncap_early1"),
        ("uncapped @onset-2", "uncap_early2"),
        ("uncapped @period 1", "uncap_start"),
    ]
    for objective, title in (
        ("gross", "gross profit (registered)"),
        ("net", "net reward (NOT registered)"),
    ):
        lines += [
            "",
            f"### Q1-b ({objective}). Shock-attributable clairvoyant headroom on {title}: "
            "(bound - arm 1) - (same bound on the unshocked twin - arm 1 on the twin), % of arm 1",
            "",
            "| family | " + " | ".join(label for label, _ in did_anchors) + " |",
            "|---|" + "---:|" * len(did_anchors),
        ]
        passing = [0] * len(did_anchors)
        for key in KEYS:
            block = fam[key][objective]
            cells = []
            for i, (_, suffix) in enumerate(did_anchors):
                v = block[f"clv_{objective}_{suffix}_shock_attributable_pct"]
                passing[i] += v >= 5.0
                cells.append(_pct(v))
            lines.append(f"| {key} | " + " | ".join(cells) + " |")
        lines.append("| **families >= 5%** | " + " | ".join(str(p) for p in passing) + " |")
    lines += [
        "",
        "### Q1-c. Net of holding (benchmark total_reward, NOT registered): lift over arm 1",
        "",
        "| family | arm 1 net | oracle | max-stock @onset | clairvoyant @onset, capped | "
        "clairvoyant @onset, uncapped | clairvoyant @period 1, uncapped |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in KEYS:
        n = fam[key]["net"]
        lines.append(
            f"| {key} | {n['arm1']:.0f} | {_pct(n['oracle_lift_pct'])} | "
            f"{_pct(n['maxstock_onset_lift_pct'])} | {_pct(n['clv_net_cap_onset_lift_pct'])} | "
            f"{_pct(n['clv_net_uncap_onset_lift_pct'])} | "
            f"{_pct(n['clv_net_uncap_start_lift_pct'])} |"
        )
    ncounts = fam["families_passing_registered_rule"]["net"]
    lines += [
        "",
        "Families clearing the same rule if it were read on net reward (exploratory only): "
        + ", ".join(
            f"{name} {ncounts[name]}"
            for name in (
                "oracle",
                "clv_net_cap_onset",
                "clv_net_uncap_onset",
                "clv_net_uncap_start",
            )
        ),
        "",
        "Twin (no-shock) gains of the net clairvoyant @onset over arm 1, i.e. pure noise "
        "foresight: "
        + ", ".join(
            f"{key} {fam[key]['net']['clv_net_cap_onset_twin_gain']:+.2f}"
            for key in KEYS
            if "clv_net_cap_onset_twin_gain" in fam[key]["net"]
        ),
        "",
        "### Q1-d. What the oracle's compiled response actually is",
        "",
        "| family | compiled (m, l_eff, gamma) | oracle window periods | window orders that land | "
        "smoother binds post-onset: arm 1 / oracle |",
        "|---|---|---|---|---:|",
    ]
    for key in KEYS:
        f = fam[key]
        cfgs = ", ".join(f"({m:g}, {lead}, {g:g})" for m, lead, g in f["oracle_compiled_configs"])
        cb = f["cap_binding_post_onset"]
        lines.append(
            f"| {key} | {cfgs} | {f['oracle_window_periods']} | "
            f"{f['oracle_window_orders_landed']} | {100 * cb['arm1']:.1f}% / "
            f"{100 * cb['oracle']:.1f}% |"
        )
    lines += [
        "",
        f"Reproduction: {q1['verified_reproduction']}",
    ]
    return lines


def mechanism_tables(mech: dict) -> list[str]:
    fam = mech["per_family"]
    lines = [
        "### Mechanisms. Per-seed physics behind the headroom result",
        "",
    ]
    for key in ("demand_level:demand_up", "demand_level:demand_down"):
        parts = []
        for r in fam[key]:
            ratio = ", ".join(f"+{k}: {v:.2f}" for k, v in r["implied_over_true_level"].items())
            parts.append(f"{r['cluster']} ({ratio})")
        lines.append(
            f"- {key}: compiled m x running mean / true level, by periods after onset: "
            + "; ".join(parts)
        )
    lines.append(
        "- temporary_pulse: "
        + "; ".join(
            f"{r['cluster']} pulse {r['pulse_periods']}, order at onset lands "
            f"{r['order_at_onset_lands']}, pulse periods reachable from onset "
            f"{r['pulse_periods_reachable_from_onset']} / from onset-1 "
            f"{r['pulse_periods_reachable_from_onset_minus_1']}"
            for r in fam["temporary_pulse"]
        )
    )
    lines.append(
        "- lead_time_shift: "
        + "; ".join(
            f"{r['cluster']} promised {r['promised_lead_time']}, true shift {r['true_shift']}, "
            f"compiled offset {r['compiled_offset']}"
            for r in fam["lead_time_shift"]
        )
    )
    lines.append(
        "- shipment_loss: "
        + "; ".join(
            f"{r['cluster']} lost-order periods {r['loss_periods']}, oracle window orders that "
            f"land {r['window_orders_that_land']}, first post-burst order lands "
            f"{r['first_order_after_burst_lands']}"
            for r in fam["shipment_loss"]
        )
    )
    lines.append(
        "- compound: "
        + "; ".join(
            f"{r['cluster']} onset {r['onset']}, pause {r['pause_periods']}, landing period of "
            f"an order placed at onset+k {json.dumps(r['landing_of_order_placed_at'])}"
            for r in fam["compound"]
        )
    )
    return lines


def q2_tables(q2: dict) -> list[str]:
    s = q2["summary"]
    d = s["decomposition"]
    lines = [
        "### Q2-a. The -565.5 decomposed (contribution to the 120-episode mean)",
        "",
        "| stratum | no fire | blocked | activated: delay | activated: lifecycle | row total |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for stratum, cell in d["profit"]["cells"].items():
        act = cell["activated"]
        total = (
            cell["no_fire"]["contribution"] + cell["blocked"]["contribution"] + act["contribution"]
        )
        lines.append(
            f"| {stratum} (n={cell['n']}) | {cell['no_fire']['contribution']:+.2f} "
            f"[{cell['no_fire']['n']}] | {cell['blocked']['contribution']:+.2f} "
            f"[{cell['blocked']['n']}] | {act['delay_contribution']:+.2f} [{act['n']}] | "
            f"{act['lifecycle_contribution']:+.2f} | {total:+.2f} |"
        )
    p = d["profit"]
    lines += [
        f"| **all** | {p['by_category']['no_fire']:+.2f} | {p['by_category']['blocked']:+.2f} | "
        f"{p['activated_split']['delay']:+.2f} | {p['activated_split']['lifecycle']:+.2f} | "
        f"{p['sum_of_contributions']:+.2f} |",
        "",
        "Same decomposition on net reward (profit - holding; NOT registered): "
        f"no fire {d['reward']['by_category']['no_fire']:+.2f}, blocked "
        f"{d['reward']['by_category']['blocked']:+.2f}, delay "
        f"{d['reward']['activated_split']['delay']:+.2f}, lifecycle "
        f"{d['reward']['activated_split']['lifecycle']:+.2f}, total "
        f"{d['reward']['sum_of_contributions']:+.2f}.",
        "",
        f"Activation: {json.dumps(s['activation'], default=float)}",
        "",
        f"Benefit given activation: {json.dumps(s['benefit_given_activation'], default=float)}",
        "",
        f"Nulls: {json.dumps(s['nulls'], default=float)}",
        "",
        f"Seed-cluster intervals: {json.dumps(s['intervals'], default=float)}",
    ]
    return lines


def fill_table(q1: dict) -> list[str]:
    fam = q1["per_family"]
    lines = [
        "### Q1-e. Fill rate: arm 1, oracle, and the clairvoyant bounds (registered floor 0.95)",
        "",
        "| family | arm 1 | oracle | clairvoyant net, capped @onset | clairvoyant gross, "
        "uncapped @period 1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for key in KEYS:
        f = fam[key]["fill"]
        lines.append(
            f"| {key} | {f['arm1']:.3f} | {f['oracle']:.3f} | {f['clv_net_cap_onset']:.3f} | "
            f"{f['clv_gross_uncap_start']:.3f} |"
        )
    return lines


def q3_tables(q3: dict) -> list[str]:
    s = q3["summary"]
    lines = [
        "### Q3-a. Demand CUSUM alone (no_alert rows, one per seed)",
        "",
        "| family | seeds | fired | latency vs onset |",
        "|---|---:|---:|---|",
    ]
    for key, row in s["detector_power_no_alert"].items():
        lines.append(
            f"| {key} | {row['distinct_seeds']} | {row['fired_at_all']} | {row['latencies']} |"
        )
    lines += [
        "",
        "### Q3-b. Gap contribution by family x condition (gross / net), sum "
        f"{s['gap_by_cell']['sum']:+.2f}",
        "",
        "| family | no_alert | early_accurate | late_accurate | unreliable |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, cells in s["gap_by_cell"]["cells"].items():
        row = [key]
        for cond in ("no_alert", "early_accurate", "late_accurate", "unreliable"):
            c = cells.get(cond)
            row.append(
                "—"
                if c is None
                else f"{c['contribution_gross']:+.2f} / {c['contribution_net']:+.2f}"
            )
        lines.append("| " + " | ".join(row) + " |")
    act = s["gap_by_actionability"]
    lines += [
        "",
        "### Q3-b2. The gap by who could act (contribution to the 120-episode mean)",
        "",
        "| class | episodes | gross [seed-cluster 95%] | share | net [seed-cluster 95%] |",
        "|---|---:|---:|---:|---:|",
    ]
    for cls in ("supply_no_alert", "supply_alert_only", "demand_visible", "null"):
        e = act[cls]
        gi, ni = e["seed_cluster_interval_gross"], e["seed_cluster_interval_net"]
        lines.append(
            f"| {cls} | {e['n']} | {e['contribution_gross']:+.2f} [{gi[0]:+.1f}, {gi[1]:+.1f}] | "
            f"{100 * e['share_of_total_gross'] + 0.0:.1f}% | "
            f"{e['contribution_net']:+.2f} [{ni[0]:+.1f}, {ni[1]:+.1f}] |"
        )
    lines += [
        "",
        f"First firing source over all 120 episodes: {s['first_firing_source']}",
    ]
    obs = s["arrival_observability"]
    lines += [
        "",
        "### Q3-c. Arrival-side observability (arm 1 trajectories; decision period minus onset)",
        "",
        f"identity violations {obs['identity_violations']}, false signals on demand families "
        f"and twins {obs['false_signals_on_demand_families_and_twins']}, trajectories "
        f"{obs['trajectories_checked']}",
        "",
        "| generator family | in-transit loss identity | promised-lead arrival residual |",
        "|---|---|---|",
    ]
    for fam, row in obs["by_family"].items():
        lines.append(
            f"| f{fam} | {row['loss_signal_latency']} | {row['arrival_residual_latency']} |"
        )
    return lines


def ladder_tables(ladder: dict) -> list[str]:
    lines = [
        "### Ladder. Per family means and contrasts with the detector control (gross / net)",
        "",
        "| family | arm 1 | ctrl (= arm 8) | arm 10 | AlertSpec UB | oracle | "
        "arm10 - ctrl | UB - ctrl |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, entry in ladder["by_key"].items():
        a = entry["arms"]
        c = entry["contrasts"]

        def cell(arm: str, a: dict = a) -> str:
            return f"{a[arm]['gross']:.0f} / {a[arm]['net']:.0f}" if arm in a else "—"

        ub = c.get("ctrl_alertspec_upper_bound_minus_ctrl")
        lines.append(
            f"| {key} | {cell('arm1_capped_base_stock')} | {cell('ctrl_cusum_to_compiler')} | "
            f"{cell('arm10_spec_eprocess')} | {cell('ctrl_alertspec_upper_bound')} | "
            f"{cell('oracle_shockspec_headroom')} | "
            f"{c['arm10_spec_eprocess_minus_ctrl']['gross']:+.1f} / "
            f"{c['arm10_spec_eprocess_minus_ctrl']['net']:+.1f} | "
            + ("—" if ub is None else f"{ub['gross']:+.1f} / {ub['net']:+.1f}")
            + " |"
        )
    b = ladder["perfect_language_bound_vs_detector"]
    lines += [
        "",
        "Perfect-information language bound minus detector control (UB on shocked, arm 1 on "
        f"nulls): gross {b['gross']['mean_over_120']:+.2f} (shocked {b['gross']['shocked_mean']:+.2f}, "
        f"null {b['gross']['null_mean']:+.2f}); net {b['net']['mean_over_120']:+.2f} "
        f"(shocked {b['net']['shocked_mean']:+.2f}, null {b['net']['null_mean']:+.2f}).",
        "",
        "Compiled (m, l_eff, gamma) while a spec was active, active-period counts:",
        "",
        "| family | ctrl | arm 10 | keyword | AlertSpec UB | oracle |",
        "|---|---|---|---|---|---|",
    ]
    compiled = ladder["compiled_configs_active_periods"]
    arms = (
        "ctrl_cusum_to_compiler",
        "arm10_spec_eprocess",
        "ctrl_keyword_parser",
        "ctrl_alertspec_upper_bound",
        "oracle_shockspec_headroom",
    )
    for key in [*KEYS, "null"]:
        cells = []
        for arm in arms:
            counts = compiled.get(arm, {}).get(key)
            cells.append(
                "—" if not counts else ", ".join(f"{cfg} x{n}" for cfg, n in counts.items())
            )
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    lines += [
        "",
        f"early_accurate == unreliable replicas: {json.dumps(ladder['early_vs_unreliable_replicas'])}",
        f"category by condition: {json.dumps(ladder['category_by_condition'])}",
        f"wrong-family activation: {json.dumps(ladder['wrong_family_activation'])}",
        f"record stamps: {ladder['record_analysis_class']}; model ids: {ladder['record_model_ids']}",
    ]
    return lines


def proposal_tables(prop: dict) -> list[str]:
    shared = prop["shared_proposal_call_arms_8_9_10"]
    lines = [
        "### Proposal sizing. The shared arm 8/9/10 ShockSpec proposal call on the same 120 "
        "episodes (USD at dated list prices)",
        "",
        f"episodes with a proposal {shared['episodes_with_a_proposal']}; mean input tokens "
        f"{shared['mean_input_tokens']:.0f}; scripted output tokens "
        f"{shared['mean_output_tokens_scripted']:.0f}; volumes {json.dumps(shared['volumes'])}",
        "",
        "| endpoint | model | seed honoured | volume | output x1 | output x5 | output x20 |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for name, ep in prop["endpoints"].items():
        for volume in shared["volumes"]:
            usd = shared["usd"][volume][name]
            lines.append(
                f"| {name} | {ep['model_id']} | {ep['supports_seed']} | {volume} | "
                f"${usd['output_x1']:.2f} | ${usd['output_x5']:.2f} | ${usd['output_x20']:.2f} |"
            )
    lines += [
        "",
        "| optional arm | charged calls | mean input tokens | gemini x1 / x20 | grok x1 / x20 |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm, row in prop["per_arm_ledger"].items():
        usd = row["usd_if_every_charged_call_physical"]
        lines.append(
            f"| {arm} | {row['charged_calls']} | {row['mean_input_tokens']:.0f} | "
            f"${usd['gemini_primary']['output_x1']:.2f} / "
            f"${usd['gemini_primary']['output_x20']:.2f} | "
            f"${usd['grok_confirmation']['output_x1']:.2f} / "
            f"${usd['grok_confirmation']['output_x20']:.2f} |"
        )
    return lines


def main() -> None:
    lines: list[str] = []
    facts = _load("facts.json")
    if facts:
        lines += [*facts_tables(facts), ""]
    q1 = _load("q1_clairvoyant.json")
    if q1:
        lines += [*q1_tables(q1), "", *fill_table(q1), ""]
    mech = _load("mechanisms.json")
    if mech:
        lines += [*mechanism_tables(mech), ""]
    q2 = _load("q2_decomposition.json")
    if q2:
        lines += [*q2_tables(q2), ""]
    q3 = _load("q3_detection.json")
    if q3:
        lines += [*q3_tables(q3), ""]
    ladder = _load("ladder.json")
    if ladder:
        lines += [*ladder_tables(ladder), ""]
    prop = _load("proposal.json")
    if prop:
        lines += [*proposal_tables(prop), ""]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
