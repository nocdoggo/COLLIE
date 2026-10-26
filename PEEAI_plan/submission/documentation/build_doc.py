"""Build Plan_B_Project_Documentation.docx, the project documentation of Plan B.

    uv run --no-project --with python-docx==1.1.2 python build_doc.py

The figures are the slide deck's TikZ figures (../slides/figures/*.pdf), rendered here to PNG
with pdftoppm, and crops of the Wave 2 storyboard frames (../slides/figures/frames/).

Every held-out number comes from results.json, which ../make_results.py writes from the committed
run wave3_heldout_20261025T1625Z (its two report/metrics.json files). The rest of section 12
cites that run's README.md and FAILURES.md. That run stays the evaluation of record. Section 12.7
adds version 1.2 (Wave 3b) from results_v12.json, which the same script writes from the fresh
held-out run wave3b_fresh_20261025T2327Z and from the post-hoc diagnostic rerun on the spent cases
wave3b_rerun_spent_20261025T2345Z (not a held-out result).
"""

import json
import subprocess
from pathlib import Path

from docx_helpers import (
    bullets,
    code_block,
    figure,
    neutral_app_properties,
    new_document,
    numbered,
    para,
    rich,
    table,
)

HERE = Path(__file__).resolve().parent
FIGURES = HERE.parent / "slides" / "figures"
FRAMES = FIGURES / "frames"
PNG = HERE / "figures"
OUT = HERE / "Plan_B_Project_Documentation.docx"
RESULTS = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
# Wave 3b, policy 1.2: "fresh" is held-out (C09 to C12, T05, T06), "rerun" is a post-hoc
# diagnostic rerun on the spent cases and never a held-out result.
V12 = json.loads((HERE / "results_v12.json").read_text(encoding="utf-8"))

TITLE = "Plan B: The Show Must Go On"
AUTHOR = "Noctis Zhang"
REPO = "https://github.com/nocdoggo/FA26-COLLIE"
APP_URL = REPO


def render_figures() -> None:
    """Render each TikZ figure PDF to a 200 dpi PNG for the Word document."""
    PNG.mkdir(exist_ok=True)
    for pdf in sorted([*FIGURES.glob("fig_*.pdf"), *FIGURES.glob("report_*.pdf")]):
        target = PNG / f"{pdf.stem}.png"
        if target.exists() and target.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        subprocess.run(
            ["pdftoppm", "-png", "-r", "200", "-singlefile", str(pdf), str(PNG / pdf.stem)],
            check=True,
        )


def title_block(doc) -> None:
    doc.add_heading(TITLE, level=0)
    para(doc, "**Project Documentation**")
    para(doc, "An AI coordinator that decides what to verify, what to prepare, and when to commit a change.")
    table(
        doc,
        ["Item", "Value"],
        [
            ["Author", "Noctis Zhang (single author, no team)"],
            ["Institution", "University of Massachusetts Boston"],
            ["Event", "Paul English Applied AI Institute (PEAAII) Hackathon, UMass Boston, October 2026"],
            ["Repository", f"<<{APP_URL}>>"],
            ["App and submission paths", "the app is in `apps/plan_b` and the submission items are in `PEEAI_plan/submission` of the repository `nocdoggo/FA26-COLLIE`"],
        ],
        [1.6, 4.9],
    )


def _v12_met(layer: str) -> tuple[int, int]:
    """Runs met and recorded over both suites and all policies of one Wave 3b layer."""
    rows = [V12[layer][s][p] for s in ("campus", "pantry") for p in ("P0", "P1", "P2", "P3")]
    return sum(int(r["metk"]) for r in rows), sum(int(r["metn"]) for r in rows)


def table_caption(doc, text: str) -> None:
    paragraph = doc.add_paragraph(style="Caption")
    rich(paragraph, text)
    paragraph.paragraph_format.keep_with_next = True  # the caption stays with its table


def abstract(doc) -> None:
    doc.add_heading("Abstract", level=1)
    para(
        doc,
        "Small community events run on volunteers, borrowed equipment and fixed rooms. A single late "
        "delivery or stale message can push an organizer into a rushed change that costs people their "
        "time. **Plan B** is a coordinator agent that decides what to verify, what to prepare and when "
        "to commit a change, inside written limits it cannot exceed. A language model reads each "
        "message and picks one of the options the server has built and checked. A **hold** keeps a "
        "backup open while a fact or an approval is pending, and every accepted change returns a "
        "**receipt**. I built Plan B as a fictional local sandbox with a campus showcase, a community "
        "skills exchange and a fictional pantry, and compared four coordinator policies on held-out "
        "cases that were locked before the test. In 120 held-out runs of version 1.1, the evaluation of "
        "record, no policy executed a violation "
        "or changed a quiet event, but my policy showed no consistent advantage: a model calling the "
        "tools freely met every campus run at three times my policy's model cost, and fixed rules met "
        "every pantry run. That run exposed defects, so I made version 1.2 and tested it on a fresh "
        "held-out set of six cases, locked before any 1.2 call. It met the expected outcome in "
        f"{_v12_met('fresh')[0]} of {_v12_met('fresh')[1]} runs, and the one miss was the fixed rules on a late-volunteer case. "
        "That set is small and repeats known conditions in new cases, so it is not comparable with "
        "the first run. Everything is fictional and local, the case set is small, and no community "
        "pilot has been run.",
    )
    figure(doc, PNG / "fig_strip.png", "Figure 1. One recovery in four steps (development case dev01).")


def problem(doc) -> None:
    doc.add_heading("1. Problem and motivation", level=1)
    para(
        doc,
        "Imagine you organize a campus showcase. It opens at 17:00 and must finish by 18:00. At 16:40 "
        "a message says the projector may be about 25 minutes late. If you change too much, presenters "
        "and volunteers lose their time. If you wait too long, the demonstrations fail.",
    )
    para(doc, "Three facts make this hard:")
    bullets(
        doc,
        [
            "**A message is a claim, not a fact.** It can be late, stale, duplicated, about another "
            "booking, or simply wrong.",
            "**Checking costs time.** A status check takes minutes that the event may not have.",
            "**Changes have owners.** Spending money, changing the goal or recording that stock "
            "physically arrived belong to people, not to an assistant.",
        ],
    )
    para(
        doc,
        "AI agents are starting to book, buy and reschedule things for people. Acting on a wrong or "
        "stale message is the failure that matters. Plan B asks a narrow question: can an agent keep a "
        "community event on track by deciding what to verify, what to prepare and when to commit, "
        "without ever acting outside its written limits?",
    )
    figure(doc, PNG / "fig_timeline.png", "Figure 2. The fictional campus showcase and the 16:40 message.")


def different(doc) -> None:
    doc.add_heading("2. What is different here", level=1)
    para(
        doc,
        "Plan B combines known ideas in one bounded workflow. It does not claim to be the first of its "
        "kind. P0 to P3 are the four coordinator policies compared in section 7.",
    )
    bullets(
        doc,
        [
            "**Ordinary tool-calling agents** let the model write tool calls directly. Plan B keeps "
            "that design as a comparison policy (P1), and in its own policy (P2) the model picks one "
            "option from a menu the server built and checked.",
            "**Rule systems** are predictable but read only the message forms they were written for. "
            "Plan B keeps a published rule policy (P0) as a baseline.",
            "**Plan repair and information gathering** are well studied in planning research. Plan B "
            "applies them to a small event with explicit holds, receipts and human approval.",
            "**Reversible preparation.** A hold reserves a backup for free and expires on its own, so "
            "the agent can prepare without committing.",
            "**An honest comparison.** The four policies share the same tools, rights, candidate repairs, "
            "limits and executor, and were frozen before the held-out test. Prompts differ by policy "
            "(section 12.5).",
        ],
    )


def what_it_does(doc) -> None:
    doc.add_heading("3. What Plan B does", level=1)
    para(doc, "For each new message or observation, the coordinator takes one of five outcomes:")
    table(
        doc,
        ["Outcome", "Meaning", "Example"],
        [
            ["Verify", "Check one fact that could change the decision", "Supplier status: delayed, ETA 17:25"],
            ["Prepare", "Hold a backup while a fact or an approval is pending", "Backup projector held until 16:55"],
            ["Commit", "Apply a plan the server checked, with a receipt", "Free swap applied at 16:43"],
            ["Keep", "Change nothing on purpose", "A stale reminder about another order"],
            ["Report infeasible", "Name the blocking constraints, change nothing invalid", "No recovery fits the limits"],
        ],
        [1.3, 2.9, 2.3],
    )
    para(doc, "Each role has narrow, written rights, called a **grant**. The server enforces every grant.")
    figure(doc, PNG / "fig_roles.png", "Figure 3. Who may do what. One executor checks every request.")
    para(
        doc,
        "Everything runs in a **fictional local sandbox**. Every action is a real change to a local "
        "SQLite database and nothing else. No university booking, purchase, delivery or message is made.",
    )
    para(
        doc,
        "I built Plan B in three waves: the campus sandbox (Wave 1), the model policies, community roles "
        "and pantry (Wave 2), and the frozen held-out comparison (Wave 3). Each wave ended with an audit "
        "packet of evidence in `PEEAI_plan/handoffs/`, which later sections cite.",
    )


def walkthrough(doc) -> None:
    doc.add_heading("4. A recovery, step by step", level=1)
    para(doc, "The fictional campus showcase in these development cases takes place on November 5, 2026.")
    doc.add_heading("4.1 The late projector (development case dev01)", level=2)
    numbered(
        doc,
        [
            "At 16:40 a notice from the delivery contact says the projector delivery may be about 25 "
            "minutes later than the promised 17:00 arrival.",
            "The coordinator treats it as a claim and makes one **status check** of order P17. In the "
            "sandbox a status check takes two simulated minutes.",
            "The answer is delayed, reported ETA 17:25. A reported ETA is still not an arrival.",
            "The **planner** builds the allowed repairs from fixed templates (keep, swap, a ten-minute "
            "shift, the approved backup, and pairs of these) and checks each against the deadline, the "
            "people and the budget: 16 built, 3 feasible.",
            "The best repair is free: swap the demonstrations and the skills exchange, so the "
            "demonstrations start at 17:30, after the reported ETA.",
            "The executor applies it at 16:43 and writes receipt `rcpt_0001`. The plan version goes from "
            "1 to 2.",
        ],
    )
    figure(doc, PNG / "fig_swap.png", "Figure 4. The free swap: the demonstrations move after the projector's ETA.")
    figure(doc, FRAMES / "before_after.png", "Figure 5. The app's before and after view with the receipt (automated run).", 5.6)
    doc.add_heading("4.2 Four messages, zero changes (development case dev04)", level=2)
    numbered(
        doc,
        [
            "The same delay notice arrives, but the status check says on schedule, ETA 16:58. It is a "
            "false alarm, so the plan stays.",
            "At 16:44 a reminder says order P09 for the October 29 workshop was cancelled. That is "
            "another order on another date, so it does not apply.",
            "The reminder arrives again at 16:46, and a volunteer forwards it at 16:47. One source "
            "repeated is still one source, so it is a duplicate.",
            "Plan version 1 is kept: no hold, no spending, no change.",
        ],
    )
    figure(doc, PNG / "fig_quiet.png", "Figure 6. Four messages, zero changes.")
    doc.add_heading("4.3 Prepare, ask, commit (development case dev02)", level=2)
    numbered(
        doc,
        [
            "The status check reports ETA 17:45, too late for either demonstration slot.",
            "The coordinator places a free **hold** on the backup projector that expires at 16:55, and "
            "asks the organizer to raise the spending limit from $0 to $35.",
            "The organizer approves in a separate session. Only then is the backup committed, once, "
            "for $35.00.",
        ],
    )
    doc.add_heading("4.4 Which policy acted", level=2)
    para(
        doc,
        "The frames above come from an automated browser run of the rule baseline (P0), with no model "
        "call. In a recorded development run, the AI coordinator (P2) made the same status check and the "
        "same swap at 16:43 with receipt `rcpt_0001`, in 3 model calls for $0.0366.",
    )


def architecture(doc) -> None:
    doc.add_heading("5. Architecture", level=1)
    figure(doc, PNG / "fig_architecture.png", "Figure 7. Four policies, one executor at the authority boundary.")
    para(doc, "The runtime dependencies are FastAPI, uvicorn and Pydantic only. Paths are under `apps/plan_b/`.")
    table(
        doc,
        ["Component", "Role", "Where"],
        [
            ["Server", "HTTP API, sessions, moderator controls", "`plan_b/api/`"],
            ["Event store", "State, plan versions, holds, receipts, stock ledger (SQLite with migrations)", "`plan_b/store/`"],
            ["Executor and tools", "Checks grant, state version (revision), repeat key and budget, then writes a receipt", "`plan_b/tools/`"],
            ["Planner", "Builds and checks candidate repairs", "`plan_b/domain/candidates.py`, `constraints.py`, `objective.py`"],
            ["Adapters", "Campus and pantry rules on the shared core", "`plan_b/domain/adapters/`"],
            ["Runner and clock", "Simulated clock, scripted world events, policy wakes and limits", "`plan_b/scenarios/`"],
            ["Rule policies (P0)", "Published deterministic rules and parser", "`plan_b/evaluation/policies/`"],
            ["Model policies (P1 to P3)", "Menu, interpretation, attention rule, provider", "`plan_b/agent/`"],
            ["Browser board", "Organizer, participant, staff and moderator views", "`web/` (React, TypeScript)"],
            ["Trace and replay", "Sanitized traces, integrity check, offline replay", "`plan_b/evaluation/export_trace.py`, `web/src/replay/`"],
            ["Evaluation harness", "Freeze, held-out runs, metrics, report", "`plan_b/evaluation/`"],
        ],
        [1.5, 2.8, 2.2],
    )


def decision_policy(doc) -> None:
    doc.add_heading("6. The decision policy", level=1)
    figure(doc, PNG / "fig_loop.png", "Figure 8. Verify, prepare, commit, keep, with this event's examples.")
    para(
        doc,
        "The selective policy P2 follows these steps each time the runner wakes it, that is, gives it a "
        "turn because the shared state changed or a wait it set has passed:",
    )
    numbered(
        doc,
        [
            "A language model reads each new notice into a structured claim. The server then checks its "
            "identity: the booking reference and the date must match, or the notice does not apply.",
            "An **attention rule** decides whether the model is needed at all. It is called for a new "
            "notice the server cannot resolve, or when the menu offers an action. Otherwise the server "
            "records what the state determines.",
            "The server builds a closed **menu** from the visible state: keep, query, hold, apply a "
            "checked candidate, ask the organizer, release a hold, or wait.",
            "The model returns one option id under a strict JSON schema. An id outside the menu is "
            "rejected.",
            "The executor validates and runs the option, writes a receipt, and the next wake reads what "
            "actually happened.",
        ],
    )
    para(
        doc,
        "The model's rationale is stored and shown only as untrusted text. The receipts and checks are "
        "the evidence.",
    )


def policies(doc) -> None:
    doc.add_heading("7. The agent and the comparison policies", level=1)
    para(doc, "A **policy** is the rule that picks the next step. All four share the same tools, grants, candidate repairs, limits and executor. Prompts differ by policy (section 12.5).")
    table(
        doc,
        ["Policy", "Frozen id", "How it decides"],
        [
            ["P0 rules", "`rules/1.0.0`, `pantry-rules/1.1.0`", "Published deterministic rules and a small parser. No model"],
            ["P1 tool use", "`tool-use/1.1.0` (prompt `tool_use.v3`)", "The model calls the tools itself. The executor checks every call"],
            ["P2 selective (mine)", "`live/1.1.0`", "The model picks one option from the server's checked menu"],
            ["P3 verify all", "`verify-all/1.1.0`", "P2, with every relevant status check run first by the server under rule `verify-all-relevance/1.0.0`"],
        ],
        [1.4, 2.2, 2.9],
    )
    bullets(
        doc,
        [
            "**Model**: `anthropic/claude-sonnet-5.5` through OpenRouter, the same configuration for P1 "
            "to P3, 4096 output tokens per call, strict JSON output.",
            "**Limits per run**: 48 tool calls, 8 model calls, $0.50, 900 seconds. Every failed call "
            "and retry counts.",
            "**Seeds** 101, 202 and 303 are recorded but not sent, because the model's endpoints refuse a "
            "seed. The three runs of a case are repeated trials, not independent units, and not "
            "reproducible.",
            "**P1 is a serious baseline.** It sees the objective, the budget, the tools and the "
            "candidates, and may verify and hold like P2.",
            "**P3 is an ablation.** Its checks are made by the server, so its lower model-call count on "
            "campus does not mean less checking.",
        ],
    )


def community(doc) -> None:
    doc.add_heading("8. Community participation", level=1)
    bullets(
        doc,
        [
            "The moderator issues a one-time join code for each role. Each browser tab is its own "
            "scoped session.",
            "A participant can check in for their own role. A check-in can make the plan infeasible, and "
            "the coordinator then repairs it.",
            "In the community skills exchange, the kit steward may offer the registered backup kit. An "
            "accepted offer changes only that resource's status. Campus offers are refused.",
            "The organizer approves spending in their own session. No participant gains spending "
            "authority from a message.",
        ],
    )
    figure(
        doc,
        FRAMES / "community_replanned.png",
        "Figure 9. Development case skills_dev01: the peer lead's own check-in moves two activities (automated run).",
        5.0,
    )


def pantry(doc) -> None:
    doc.add_heading("9. The pantry extension", level=1)
    para(
        doc,
        "Pantry Continuity is a **fictional pantry sandbox**. Staff need 40 shelf-stable kits by 13:40. "
        "24 are on the shelf, 20 more are expected late and count for nothing until received, and 16 wait "
        "in a partner pool at the same venue. Two counters stay visible: the **supply shortfall** (kits "
        "still missing from the shelf) and the **service deficit** (kits not yet handed out).",
    )
    numbered(
        doc,
        [
            "The coordinator holds the 16 partner kits for a staff handoff. A hold moves no stock.",
            "Staff record the handoff: the partner pool goes from 16 to 0 and the pantry shelf from 24 to "
            "40. The supply shortfall is 0, but nobody has been served.",
            "The coordinator holds and commits the 40 kits for the distribution.",
            "Staff record the distribution of 40 kits at 13:40. Only this brings the service deficit to 0.",
        ],
    )
    figure(doc, PNG / "fig_pantry.png", "Figure 10. Stock and the two counters at four moments (development case pantry_dev01).")
    para(
        doc,
        "In development case pantry_dev02, staff hand off only 10 of the 16 kits. 34 kits are "
        "distributed, a 6-kit deficit is reported, and the target stays 40.",
    )
    para(
        doc,
        "The pantry reuses the shared core (state, versions, grants, holds, receipts, executor, loop) and "
        "adds a domain extension: consumable stock with quantity holds (`store/migrations/0004_consumable_stock.sql`, "
        "`domain/stock.py`, `tools/stock.py`), the pantry adapter and rule policy, and staff-only "
        "`record_stock_receipt` and `record_distribution`. This is reuse with an explicit extension, "
        "not zero-shot transfer.",
    )


def safety(doc) -> None:
    doc.add_heading("10. Safety and authority boundaries", level=1)
    bullets(
        doc,
        [
            "**Grants** are enforced by the executor on the server. The coordinator's grant lacks the "
            "staff tools, so it cannot record a receipt or a distribution.",
            "**State versions.** Every change names the state version it was made on (its **revision**). "
            "A change made on an old version is rejected without a partial change.",
            "**Repeat keys.** Repeating an action with the same key returns the same receipt without a "
            "second reservation or charge.",
            "**Holds expire** at their declared time and release the backup.",
            "**Message text is data.** Instructions inside a notice change nothing.",
            "**Receipts.** Every accepted change has a receipt. Refused requests are recorded too, some as "
            "attempts without a receipt. Read-only tools have no receipt.",
            "**Public and evaluator-only data are separate.** Hidden expectations never reach a policy or "
            "the browser.",
            "**Spend caps and a ledger** bound every paid model call. The key is read by the server's "
            "provider at call time. The audit scripts' reads of the key are disclosed in the Wave 2 audit packet "
            "(`PEEAI_plan/handoffs/wave_2/`).",
        ],
    )


def protocol(doc) -> None:
    doc.add_heading("11. Evaluation protocol", level=1)
    para(
        doc,
        "A **development case** is a practice case I built and debugged with. A **held-out case** was "
        "written and locked before the comparison, never used in development, and hidden from every "
        "policy. Development results are never reported as evaluation results.",
    )
    figure(doc, PNG / "fig_freeze.png", "Figure 11. Practice, freeze, then one held-out test.")
    table(
        doc,
        ["Case", "Public condition (from the protocol)", "Outcome class"],
        [
            ["C01", "Genuine projector delivery delay", "Goal"],
            ["C02", "Quiet event with ordinary updates", "Goal, negative control"],
            ["C03", "Plausible false delivery warning", "Goal, negative control"],
            ["C04", "Stale warning followed by its duplicate", "Goal, negative control"],
            ["C05", "Conflicting updates about the current booking", "Goal"],
            ["C06", "Volunteer late, with a later check-in", "Goal"],
            ["C07", "Relevant status service unavailable", "Goal"],
            ["C08", "No feasible recovery within the limits", "Appropriate infeasibility"],
            ["T01", "Shipment late, alternate 16 kits in time", "Target met"],
            ["T02", "Feasible supply with duplicate and adversarial quantities", "Target met"],
            ["T03", "Stale receipt claim, real receipt too late", "Supported partial"],
            ["T04", "Alternate source supplies only part of the kits", "Supported partial"],
        ],
        [0.7, 3.9, 1.9],
    )
    bullets(
        doc,
        [
            "**Planned size**: 80 campus runs (8 cases, P0 once, P1 to P3 three times each) and, "
            "separately, 40 pantry runs. The two suites are never pooled.",
            "**Freeze**: code, prompts, model, limits, seeds and run order fixed by hash in "
            "`plan_b/evaluation/manifests/freeze.json` (commit 3de5962) before the first held-out call.",
            "**Scoring** reads the final state and receipts, not the agent's narration. A timed-out or "
            "crashed run stays in the denominator as a failure.",
            "**Metrics**: goal completion (C01 to C07), appropriate infeasibility (C08), unnecessary "
            "committed changes on the quiet cases (C02 to C04), refused requests, executed violations, "
            "status checks, recovery delay, model calls and cost, and for the pantry target attainment, "
            "supported partial fulfillment and stock conservation.",
            "**Capped runs**: a run that reaches the limit of 8 model calls stops there and is scored "
            "from its final state like any other run, so it stays in the denominator. The results "
            "tables count them in the column \"Runs capped\".",
        ],
    )


def _row(suite: str, policy: str, keys: list[str]) -> list[str]:
    return [str(RESULTS[suite][policy][key]) for key in keys]


def results(doc) -> None:
    campus, pantry = RESULTS["campus"], RESULTS["pantry"]
    names = {"P0": "P0 rules", "P1": "P1 tool use", "P2": "P2 selective (mine)", "P3": "P3 verify all"}
    doc.add_heading("12. Results", level=1)
    para(
        doc,
        f"The reported run of the frozen comparison on the locked held-out cases is `{RESULTS['run_id']}`, "
        f"committed in c052338 under `{RESULTS['source']}/`. All {campus['all']['recorded']} planned "
        f"campus runs and all {pantry['all']['recorded']} planned pantry runs were recorded, with none "
        "missing, aborted, timed out or crashed. These are descriptive counts from one reported run on 8 campus "
        "and 4 pantry cases. The case is the unit, the three runs of a case are repeated trials, and no "
        "significance test is made. The two suites are separate. Section 12.7 adds version 1.2 "
        "(Wave 3b): a fresh held-out check on six new cases and a post-hoc diagnostic rerun on these "
        "spent cases. Neither replaces this run.",
    )
    para(
        doc,
        "**Headline.** No policy executed a violation, and no policy committed a change on the three "
        "quiet cases. **P2, my policy, shows no consistent advantage over P1 or P0 here.** On one reported run "
        f"of 8 campus and 4 pantry held-out cases, P2 met every run of {campus['P2']['cases']} of 8 "
        f"campus cases (P1 met every run of {campus['P1']['cases']}, P3 of {campus['P3']['cases']}, P0 of "
        f"{campus['P0']['cases']}) and of {pantry['P2']['cases']} of 4 pantry cases (P0 of "
        f"{pantry['P0']['cases']}, P1 of {pantry['P1']['cases']}, P3 of {pantry['P3']['cases']}). Its "
        "misses come from a frozen attention rule that passes only equipment notices to the planner (C06), choices that used up the 8-call limit (C07) "
        "and an unavailable pool kept as a handoff option (T03). A first attempt was voided, as "
        "section 12.5 explains.",
    )
    figure(doc, PNG / "fig_results.png", "Figure 12. Held-out runs that met the case's outcome, per policy and suite.")
    doc.add_heading("12.1 Campus suite (8 cases, 80 runs)", level=2)
    table_caption(doc, "Table 1. Campus outcomes per policy, version 1.1, held-out.")
    table(
        doc,
        ["Policy", "Met / recorded", "Cases fully met", "Goal met C01 to C07", "Infeasibility C08", "Changes on C02 to C04"],
        [
            [names[p], *_row("campus", p, ["met"]), f"{campus[p]['cases']} of 8", *_row("campus", p, ["goal", "infeas"]),
             f"{campus[p]['unnec']} in {campus[p]['unnecn']} runs"]
            for p in ["P0", "P1", "P2", "P3"]
        ],
        [1.5, 0.9, 0.9, 1.0, 1.0, 1.2],
    )
    table_caption(doc, "Table 2. Campus integrity and model use per policy, version 1.1, held-out.")
    table(
        doc,
        ["Policy", "Refused requests", "Executed violations", "Status checks per run", "Model calls", "Model USD", "Runs capped"],
        [[names[p], *_row("campus", p, ["refused", "viol", "checks", "calls", "usd", "capped"])] for p in ["P0", "P1", "P2", "P3"]],
        [1.5, 0.8, 0.85, 0.85, 0.8, 0.85, 0.85],
    )
    para(
        doc,
        "On C08, P0's infeasibility report was decided by the policy, P1's three by the model, and "
        "P2's and P3's three each by the server's shared narration. A refused request is a "
        "coordinator call that the server rejected, so nothing it asked for happened. Across both "
        f"suites {RESULTS['campus']['all']['stale'] + RESULTS['pantry']['all']['stale']} of the "
        f"{RESULTS['campus']['all']['refused'] + RESULTS['pantry']['all']['refused']} refused "
        "requests were made on a state that had changed meanwhile, which is retryable by design.",
    )
    doc.add_heading("12.2 Pantry suite (4 cases, 40 runs)", level=2)
    table_caption(doc, "Table 3. Pantry outcomes per policy, version 1.1, held-out.")
    table(
        doc,
        ["Policy", "Met / recorded", "Cases fully met", "Target met T01, T02", "Supported partial T03, T04", "Kits on time / target"],
        [
            [names[p], *_row("pantry", p, ["met"]), f"{pantry[p]['cases']} of 4", *_row("pantry", p, ["target", "partial", "kits"])]
            for p in ["P0", "P1", "P2", "P3"]
        ],
        [1.5, 0.9, 0.9, 1.0, 1.1, 1.1],
    )
    table_caption(doc, "Table 4. Pantry integrity and model use per policy, version 1.1, held-out.")
    table(
        doc,
        ["Policy", "Refused requests", "Executed violations", "Conservation failures", "Duplicate credits", "Model USD", "Runs capped"],
        [[names[p], *_row("pantry", p, ["refused", "viol", "conserv", "credits", "usd", "capped"])] for p in ["P0", "P1", "P2", "P3"]],
        [1.5, 0.8, 0.85, 0.85, 0.8, 0.85, 0.85],
    )
    para(
        doc,
        "Kits on time are summed over a policy's runs against the summed original targets. For pantry "
        "partial fulfillment, P0's two reports were decided by the policy, and P2's and P3's (T04, "
        "three each) by the server. P1's three T03 deficit reports were decided by the model but did "
        "not meet the class.",
    )
    doc.add_heading("12.3 Per-case figures from the report", level=2)
    figure(doc, PNG / "report_campus.png", "Figure 13. The report's per-case figure, campus (`campus/report/figure.svg`).", 5.6)
    figure(doc, PNG / "report_pantry.png", "Figure 14. The report's per-case figure, pantry (`pantry/report/figure.svg`).", 5.6)
    doc.add_heading("12.4 One success, one failure, and the other failures", level=2)
    para(
        doc,
        "**One success.** C01, a genuine projector delivery delay, was met in every run by every "
        "policy (10 of 10), scored from the final state and the receipts. The three quiet cases C02 to "
        "C04 were met in all 30 of their runs with no committed change.",
    )
    para(
        doc,
        "**One failure.** In C06 (a volunteer will be late, with a later check-in), P2 and P3 read the "
        "volunteer's message correctly in all six runs. But the frozen attention rule treats only "
        "equipment notices as material, so the reading never reached the planner, the plan was never "
        "put in question, and the activity the volunteer leads could not start in time. The earliest "
        "broken stage is planner input. P0's parser does not read the message. P1 met C06 in 3 of 3 "
        "runs. This limit was disclosed at the case lock, before the runs.",
    )
    figure(doc, PNG / "fig_failure.png", "Figure 15. The C06 failure of P2 and P3 in four steps.")
    para(doc, "The other failed runs, each with its earliest broken stage (from the run's `FAILURES.md`):")
    bullets(
        doc,
        [
            "**C07** (status service unavailable), P2 in 3 runs, action selection: a repeated check and a "
            "hold released and made again used the 8 model calls, and the organizer's approval arrived "
            "after the last one. P0 missed C07 too (interpretation), because its parser does not read "
            "the message.",
            "**T02**, P3 in 3 runs, execution: a correct apply was refused as stale during a one-minute "
            "tool call, and the remaining model calls went to reading new notices, so it was never "
            "retried.",
            "**T03 and T04**, P1 in 6 runs, action selection: P1 never held or committed the kits on hand.",
            "**T03**, P2 and P3 in 3 runs each, planner input (for P2 borderline with action selection): "
            "a defect in my frozen planner and menu kept a pool checked as unavailable as a ranked "
            "handoff option, and the shortfall report waited on it.",
            "The 8-call limit ended 15 of the 26 failed runs. No failed run had an executed violation, a "
            "conservation failure or an unauthorized credit.",
        ],
    )
    doc.add_heading("12.5 The tradeoff, the spend and what the counts do not show", level=2)
    para(
        doc,
        f"**The tradeoff.** P1, the model calling tools freely, met all campus runs, with the most model "
        f"use: {campus['P1']['calls']} model calls and ${campus['P1']['usd']} on campus, against "
        f"${campus['P2']['usd']} for P2 and ${campus['P3']['usd']} for P3. On the pantry, fixed rules met "
        f"{pantry['P0']['met']} runs at no model cost, while the model policies met "
        f"{pantry['P1']['metk']} to {pantry['P2']['metk']} of 12. P2 cost less than P1 (P3, with the same menu and server checks, cost less still on campus), and its "
        "misses trace to its frozen attention rule, choices that used up the call limit and the "
        "planner defect. These counts come from one reported run and do not show that any policy is "
        "better in general.",
    )
    para(
        doc,
        "**Spend.** The reported run cost 9.08 USD in provider-reported model charges (campus 4.58, "
        "pantry 4.49). With the voided first attempt the evaluation step cost 9.64 USD, and the spend "
        "ledger stood at 13.40 USD after it, under the 40 USD limit for Wave 3.",
    )
    para(
        doc,
        "**A voided first attempt.** The first attempt ran eight runs at a time and hit the provider's "
        "limit of 20 requests a minute. Most calls were answered with an error, and each error used up "
        "one of a run's 8 model calls. It was declared void before the reported run began, kept on "
        "record, and the whole protocol was rerun one run at a time. Under the frozen status rules its "
        "capped runs would have been scored, so the void is a disclosed departure from those rules.",
    )
    bullets(
        doc,
        [
            "**Prompts differ by policy.** Only P2 and P3 had pantry guidance in their prompts, so the "
            "pantry partial-fulfillment counts cannot be credited to the controller alone.",
            "**The limits are development values**: 8 model calls and 48 tool calls per run, not tuned on "
            "held-out cases. The 8-call limit was reached in 21 of the 120 runs.",
            "**No backoff on a rate-limit error** in the frozen provider. A live demo runs one model "
            "episode at a time, with the recorded replay as the fallback. Version 1.2 adds one "
            "(section 12.7).",
            "**Reproducibility.** Seeds were recorded but not sent, the temperature is the provider "
            "default, and the provider's upstream route was not recorded.",
            "**These held-out cases are now spent.** A revised policy needs new cases and a new freeze. "
            "Section 12.7 reports both for version 1.2.",
        ],
    )
    doc.add_heading("12.6 Functional evidence", level=2)
    bullets(
        doc,
        [
            "Python tests: 896 passed, in the Wave 3 evidence collector's run from a clean checkout of "
            "commit 3442874 (`PEEAI_plan/handoffs/wave_3/evidence/reports/checks.json`). The same run passed 396 "
            "web tests, the browser walkthroughs 41 of 41 and 30 of 30, the storyboard 32 of 32 and the "
            "keyboard walk 19 of 19, and `plan-b run-case all` matched all 9 development cases.",
            "At the Wave 2 packet (development evidence): 766 Python tests and 392 web tests passed, the "
            "browser walkthroughs passed 41 of 41 and 30 of 30 checks, and the demo storyboard 32 of 32.",
            "Wave 1 rejection demo: 20 steps, each with its expected result.",
            "Rehearsals: three automated rehearsals of the showcase's board path passed, one of them "
            "with a forced provider failure and a switch to the labelled replay (Wave 3 packet, "
            "`PEEAI_plan/handoffs/wave_3/REHEARSALS.md`). The spoken script is 932 words, about 6 "
            "minutes 39 seconds at 140 words a minute, inside the 7 minutes.",
        ],
    )
    wave3b(doc)


def wave3b(doc) -> None:
    """Section 12.7: version 1.2 in two layers that stay apart from the v1.1 record."""
    fresh, rerun = V12["fresh"], V12["rerun"]
    pols = ["P0", "P1", "P2", "P3"]
    fk, fn = _v12_met("fresh")
    calls = sum(int(fresh[s][p]["calls"]) for s in ("campus", "pantry") for p in pols)
    usd = {k: sum(float(V12[k][s][p]["usd"]) for s in ("campus", "pantry") for p in pols) for k in ("fresh", "rerun")}
    by_policy = {p: sum(float(fresh[s][p]["usd"]) for s in ("campus", "pantry")) for p in ("P1", "P2", "P3")}
    doc.add_heading("12.7 Wave 3b: version 1.2", level=2)
    para(
        doc,
        "**What changed and why.** The held-out run above exposed defects in the frozen 1.1 policies, "
        "and its `FAILURES.md` names them. Version 1.2 (P1 `tool-use/1.2.0`, P2 `live/1.2.0`, P3 "
        "`verify-all/1.2.0`) fixes them. `apps/plan_b/docs/RUNTIME_CONTRACT.md` section 21 lists each "
        "fix with its test.",
    )
    bullets(
        doc,
        [
            "**A person's delay** (C06). In 1.1 only equipment notices were material, so a volunteer's "
            "own report never reached the planner. In 1.2 a notice about a person that a not-started "
            "activity uses is material, and the claimed arrival time reaches the planner as a hypothesis.",
            "**An unavailable pool** (T03). In 1.1 a pool checked as unavailable stayed a ranked handoff "
            "option, and the shortfall report waited on it. In 1.2 the planner fails that handoff unless "
            "it is already held.",
            "**Calls with no progress** (the runs that used up the 8-call limit). In 1.2 the model is not "
            "called again on a menu it already passed on in the same state (the same revision, goal "
            "version and options).",
            "**A stale refusal** (T02). In 1.1 a choice refused only because the state had changed went "
            "back to the model. In 1.2 P2 and P3 send it again without a model call when the re-read "
            "menu still offers it.",
            "**Rate limits.** In 1.1 an HTTP 429 answer used up a model call. In 1.2 the provider waits "
            "and sends the same request again inside the call (3 s, doubled up to 20 s, at most 60 s of "
            "waiting a call), so a 429 uses no model call.",
            "P0's code and ids are unchanged, but it shares the planner, so the freeze records the "
            "planner version `plan_b.planner/1.2.0`. The model, the output limit and every cap are the "
            "same as in 1.1.",
        ],
    )
    para(
        doc,
        "**How the new held-out result was kept apart.** The twelve cases above are spent, because the "
        "fixes were made after reading their failures. A separate worker wrote six fresh cases (campus "
        "C09 to C12, with C10 a quiet negative control, and pantry T05 and T06). They were locked "
        "with the 1.2 freeze (`freeze_v1_2.json` at 23:23:47 UTC, `heldout2.json` at 23:23:54 UTC, "
        "commit 5955243) before the first 1.2 model call on them (23:27:31 UTC). Whoever changed the "
        "policies never read those cases. Two limits remain. The case author read the prose list of "
        "planned fixes, but no code. The audit before the freeze had seen the cases, so it changed no "
        "policy behavior and left five known limits of 1.2 frozen (section 13).",
    )
    layers = [
        ("v1.1 held-out, evaluation of record: campus C01 to C08", RESULTS, "campus"),
        ("v1.1 held-out, evaluation of record: pantry T01 to T04", RESULTS, "pantry"),
        ("v1.2 fresh held-out: campus C09 to C12", fresh, "campus"),
        ("v1.2 fresh held-out: pantry T05, T06", fresh, "pantry"),
        ("v1.2 post-hoc diagnostic rerun on spent cases, not held-out: campus C01 to C08", rerun, "campus"),
        ("v1.2 post-hoc diagnostic rerun on spent cases, not held-out: pantry T01 to T04", rerun, "pantry"),
    ]
    table_caption(doc, "Table 5. Runs that met the case's outcome over recorded runs, per policy, in three separately labelled layers.")
    table(
        doc,
        ["Layer and cases", "Runs", "P0 rules", "P1 tool use", "P2 selective (mine)", "P3 verify all"],
        [[label, str(src[suite]["all"]["recorded"]), *[str(src[suite][p]["met"]) for p in pols]] for label, src, suite in layers],
        [2.6, 0.5, 0.8, 0.8, 1.0, 0.8],
    )

    def quiet(src: dict, suite: str) -> str:
        n = sum(int(src[suite][p]["unnecn"]) for p in pols)
        return f"{src[suite]['all']['unnec']} in {n} runs" if n else "no quiet case"

    table_caption(doc, "Table 6. Integrity measures in the same layers, summed over the four policies.")
    table(
        doc,
        ["Layer and cases", "Executed violations", "Refused requests", "Runs capped", "Changes on quiet cases"],
        [
            [label, str(src[suite]["all"]["viol"]), str(src[suite]["all"]["refused"]), str(src[suite]["all"]["capped"]), quiet(src, suite)]
            for label, src, suite in layers
        ],
        [2.6, 0.95, 0.95, 0.9, 1.1],
    )
    para(doc, "**What these numbers show and do not show.**")
    bullets(
        doc,
        [
            "**Descriptive counts only.** Each layer is one run of the protocol. The case is the unit, "
            "the three seeds are repeated trials, and no significance test is made. The suites are "
            "separate.",
            f"**The fresh held-out check** (`wave3b_fresh_20261025T2327Z`). Version 1.2 met the outcome "
            f"in {fk} of {fn} runs. The one miss is P0 on C11, a late volunteer whose own report P0's "
            "frozen parser does not read, the same gap by construction as P0 on C06. P1, P2 and P3 met "
            f"every run, {fresh['campus']['P2']['met']} each on campus and {fresh['pantry']['P2']['met']} "
            f"each on the pantry. No run reached the 8-call limit, all {calls} model calls were "
            "answered, and the negative control C10 had no committed change in any of its 10 runs.",
            "**Small, and close to the spent cases.** Six cases is a small set. Its wording is close to "
            "the spent templates, and its conditions repeat spent ones (C11 repeats the C06 condition, "
            "T06 the T03 condition). So it tests new instances of known conditions, not new conditions. "
            "It is not comparable with the v1.1 counts, because the cases differ.",
            "**P2 still shows no consistent advantage.** P1, P2 and P3 all met every fresh run, so the "
            "fresh set cannot separate them. Model charges over both fresh suites were "
            f"${by_policy['P1']:.2f} for P1, ${by_policy['P2']:.2f} for P2 and ${by_policy['P3']:.2f} for P3.",
            "**The rerun on the spent cases is diagnostic, not held-out** "
            "(`wave3b_rerun_spent_20261025T2345Z`). Its counts are consistent with the fixes on the "
            "failures that motivated them: the C06 misses of P2 and P3 and the T03 misses did not "
            "recur. The C07 failure of P2 (a hold made, released and made again until the call limit) "
            "and the T02 failure of P3 (an apply refused as stale, whose retry needed a model call that "
            "the limit did not leave) remain, and P1 missed "
            "T04 in two of three runs. The fixes were made after reading these cases, so the rerun "
            "cannot show that 1.2 is better.",
            "**Harness labels.** The rerun used a case-scoped lock written outside the repository, so "
            "its generated files (`plan.json`, `metrics.json` and the report text) say held-out. Its "
            "README says in its first line that it is not a held-out result, and every table here "
            "labels it so.",
            "**Run conditions.** The fresh run went one episode at a time and met no rate limit. The "
            "rerun ran two at a time and waited out 61 HTTP 429 answers on 28 calls, each unbilled and "
            f"using no model call. {rerun['campus']['all']['capped'] + rerun['pantry']['all']['capped']} "
            "rerun episodes reached the 8-call limit.",
            f"**Zero executed violations** in all three layers. **Spend:** the fresh run cost "
            f"{usd['fresh']:.2f} USD and the rerun {usd['rerun']:.2f} USD in provider-reported model "
            "charges, and the spend ledger stood at 26.43 USD after both, under the 40 USD limit.",
        ],
    )


def limitations(doc) -> None:
    doc.add_heading("13. Limitations and what was not done", level=1)
    bullets(
        doc,
        [
            "**Fictional sandbox.** No real bookings, rooms, purchases, messages, people or stock.",
            "**Small case set.** Eight campus and four pantry held-out cases in the evaluation of "
            "record, and six fresh cases for version 1.2. The case is the unit, and three runs are "
            "not three worlds. No significance is claimed.",
            "**Version 1.2 has five known limits**, found by the audit before the freeze and left "
            "frozen: a person's delay hypothesis outlives a later check-in, the declined-menu rule "
            "holds no time (so a timed wake with the same options gets no model call), P1 notes a "
            "declined menu with the view after its turn, a stale re-send is recorded as a model "
            "choice, and a long `Retry-After` is cut to 20 s (`RUNTIME_CONTRACT.md` section 21).",
            "**The fresh held-out set** has four campus and two pantry cases. Its wording is close to "
            "the spent templates, its conditions repeat spent ones, and its author read the prose list "
            "of planned fixes.",
            "**The diagnostic rerun's generated files say held-out** because of the harness path. Its "
            "README says it is not a held-out result, and any quote of it must keep that label.",
            "**One model**, one provider, seeds not supported, so runs are repeated trials and not "
            "reproducible.",
            "**No comparative claim beyond the counts.** A P2 versus P0 difference does not separate the "
            "decision policy from language reading.",
            "**Zero executed violations** reflects the executor's checks. It means none were observed in "
            "these runs, not a proof that none can occur.",
            "**Rehearsals** were automated (three board rehearsals). No human rehearsal had been done "
            "when this document was written.",
            "**Failure paths** were mostly tested with scripted model replies. The model was driven from a "
            "browser once, by hand.",
            "**Not built**: the optional MBTA transit adapter. Authorization requests have no stored state "
            "of their own yet.",
            "**Browsers**: only Chromium was driven. Screen readers, Firefox and Safari were not tested.",
            "**Trace hashes** are checked but not signed.",
            "**No community validation, pilot or partner.**",
        ],
    )


def how_to_run(doc) -> None:
    doc.add_heading("14. How to run it", level=1)
    para(doc, f"Repository: <<{APP_URL}>>")
    para(
        doc,
        "Requirements: a bash shell (tested on Linux), Python 3.11 or 3.12 with uv (tested with uv "
        "0.9.18), and Node.js 22.18 or newer with npm. Get the code and start the board:",
    )
    code_block(
        doc,
        [
            f"git clone {REPO}",
            "cd FA26-COLLIE/apps/plan_b",
            "unset VIRTUAL_ENV",
            "uv sync --all-groups --locked",
            "(cd web && npm ci && npm run build)",
            "uv run plan-b serve                # http://127.0.0.1:8765",
        ],
    )
    para(
        doc,
        "Open http://127.0.0.1:8765 in a browser. Sign in with the moderator code in "
        "`var/moderator_code.txt`, which the server writes on its first start. Choose case `dev01`, "
        "click **Load episode**, then **Run deterministic policy**. The server keeps its terminal busy, "
        "so run the next commands in a second terminal in `FA26-COLLIE/apps/plan_b`.",
    )
    para(
        doc,
        "Deterministic development cases and the freeze check. All nine case lines should end with "
        "`matches_expectation=True`, and the check should print `verified` for `freeze.json` and "
        "`heldout.json`:",
    )
    code_block(doc, ["uv run plan-b run-case all", "uv run plan-b eval verify-freeze --require-heldout"])
    para(doc, "Recompute the held-out reports from the committed records, with no model call:")
    code_block(
        doc,
        [
            "R=evaluation/results/wave3_heldout_20261025T1625Z",
            "uv run plan-b eval report --results $R/campus --out /tmp/campus_report",
            "uv run plan-b eval report --results $R/pantry --out /tmp/pantry_report",
        ],
    )
    para(
        doc,
        "The demo setup, with a fresh state and verified recorded traces, on its own port. Replace "
        "`<choose one>` with any code, open http://127.0.0.1:8790 and sign in with it. "
        "The recorded runs play back with no key, for example "
        "http://127.0.0.1:8790/#/replay/live_p2-live_dev02_trace.json.",
    )
    code_block(
        doc,
        [
            "uv run python scripts/demo_prep.py",
            "PLAN_B_MODERATOR_CODE='<choose one>' uv run plan-b serve --port 8790 \\",
            "    --var var/demo/state --replay-dir var/demo/replays",
        ],
    )
    para(
        doc,
        "The tests behind section 12.6, from `FA26-COLLIE/apps/plan_b` (the browser walkthroughs are in "
        "`tests/e2e/`):",
    )
    code_block(doc, ["uv run pytest -q", "(cd web && npm test)"])
    para(
        doc,
        "The model policies P1 to P3 make paid calls. They need an OpenAI-compatible endpoint such as "
        "OpenRouter, set in `.local/keys/model_endpoint.env` at the repository root (the names are in "
        "`apps/plan_b/.env.example`), and a key file that only the server reads. Everything above runs "
        "without a key. The evaluation commands are in `apps/plan_b/docs/EVALUATION.md`.",
    )


def demo_guide(doc) -> None:
    doc.add_heading("15. Demo guide", level=1)
    table(
        doc,
        ["Clock", "Segment", "Case", "Show"],
        [
            ["0:00 to 0:37", "The problem", "dev01", "Goal, deadline, the 16:40 notice"],
            ["0:37 to 1:12", "Who may do what", "dev01", "The coordinator's grant"],
            ["1:12 to 2:35", "Verify, then commit", "dev01", "Status check, options, receipt"],
            ["2:35 to 3:25", "Four messages, zero changes", "dev04", "Does not apply, duplicate, plan kept"],
            ["3:25 to 4:23", "The loop and the gate", "dev02", "Hold until 16:55, organizer approval"],
            ["4:23 to 5:39", "Held-out results", "results", "Counts and one failure"],
            ["5:39 to 6:29", "Pantry cameo", "pantry_dev01", "The two counters"],
            ["6:29 to 7:00", "Close", "", "What works, what is next"],
        ],
        [1.1, 1.9, 1.1, 2.4],
    )
    para(
        doc,
        "The slide deck works alone. If the live board is used and the model provider fails, say "
        "“We are switching to a recorded run of the same scenario” and open the replay, which is "
        "labelled **Recorded replay** on every page. A **replay** re-shows a recorded run and never calls "
        "a tool.",
    )


def ethics(doc) -> None:
    doc.add_heading("16. Ethics and the fictional sandbox", level=1)
    bullets(
        doc,
        [
            "All events, people, rooms, stock, timings and costs are fictional. The November 2026 date is fictional.",
            "The pantry scenario is inspired by the public context of campus food services. No pantry, "
            "U-ACCESS staff, system or partner took part, and no partnership is claimed.",
            "The pantry plans aggregate kit counts only. There are no recipient identities and no "
            "eligibility, allergen or medical decisions.",
            "No participant feedback was collected. No real message was sent.",
            "Paid model calls ran only under per-run and total spend caps.",
        ],
    )


def future(doc) -> None:
    doc.add_heading("17. Future work", level=1)
    bullets(
        doc,
        [
            "Review the workflows with community staff, starting with one bounded tabletop session.",
            "Store authorization requests as explicit state.",
            "Add the optional MBTA transit context, labelled as uncertain information.",
            "More held-out cases and more than one model.",
            "Human rehearsals and a comprehension check with new viewers.",
        ],
    )


def appendices(doc) -> None:
    doc.add_heading("Appendix A. Glossary", level=1)
    table(
        doc,
        ["Term", "One-line meaning"],
        [
            ["Coordinator", "The AI agent that decides the next step, inside its grant"],
            ["Grant", "The written list of actions a role may take, enforced by the server"],
            ["Hold", "A free reservation of a backup that expires on its own"],
            ["Status check", "A query to a registered source, such as the supplier's status service"],
            ["Receipt", "The server's own record of an accepted change"],
            ["Revision (state version)", "The version number of the shared state. Every change raises it. The plan version counts only accepted plans"],
            ["Executor", "The server component that checks and runs every request"],
            ["Planner", "Builds candidate repairs from fixed templates and checks each"],
            ["Policy", "The rule that picks the next step: P0 to P3"],
            ["P0, P1, P2, P3", "Fixed rules, a model calling tools, a model picking checked options, and P2 with every check"],
            ["Development case", "A practice case used to build and debug"],
            ["Episode", "One run of one policy on one case"],
            ["Wake", "A turn the runner gives the coordinator when the state changed or its wait has passed"],
            ["Held-out case", "A case locked before the test and hidden from every policy"],
            ["Replay", "A re-showing of a recorded run that calls no tool"],
            ["Met", "The run's final state and receipts show the outcome its case requires"],
            ["Quiet case", "A case where the right answer is to change nothing (C02 to C04, the negative controls)"],
            ["Executed violation", "An accepted action that left the state breaking a rule on rights, stock or resources"],
            ["Refused request", "A request the server turned away, so nothing it asked for happened"],
            ["Capped run", "A run stopped by the limit of 8 model calls, scored as it stands"],
            ["Appropriate infeasibility", "With no recovery inside the limits, the coordinator names the blocking constraints and changes nothing invalid"],
            ["Earliest broken stage", "Where a failed run first went wrong: interpretation, planner input, action selection or execution"],
            ["Attention rule", "The P2 and P3 rule that decides whether a reading is material and needs the model"],
            ["Planner input", "The step where a reading becomes a question for the planner"],
            ["Supply shortfall", "Kits still missing from the pantry shelf"],
            ["Service deficit", "Kits of the target not yet handed out"],
        ],
        [1.9, 4.6],
    )
    doc.add_heading("Appendix B. File map", level=1)
    table(
        doc,
        ["Path", "Content"],
        [
            ["`apps/plan_b/`", "The app: Python package `plan_b`, `web/`, `tests/`, `scripts/`, `docs/`"],
            ["`apps/plan_b/docs/RUNTIME_CONTRACT.md`", "The runtime semantics, sections 1 to 20"],
            ["`apps/plan_b/docs/EVALUATION.md`", "The evaluation harness and its commands"],
            ["`apps/plan_b/plan_b/evaluation/manifests/`", "The frozen `freeze.json` and the held-out lock"],
            ["`apps/plan_b/plan_b/evaluation/development/`", "The development runs of P1 to P3"],
            ["`PEEAI_plan/`", "The plan: protocol, presentation plan, wave tasks"],
            ["`PEEAI_plan/handoffs/`", "The audit packets of each wave, with their evidence"],
            ["`PEEAI_plan/submission/`", "These submission items and their sources"],
        ],
        [3.0, 3.5],
    )
    doc.add_heading("Appendix C. Evidence index", level=1)
    table(
        doc,
        ["Number in this document", "Source"],
        [
            ["dev01 notice, check, 16 built and 3 feasible, swap at 16:43, `rcpt_0001`", "Wave 2 storyboard frames 4 to 7 and `PEEAI_plan/handoffs/wave_2/evidence/storyboard/storyboard_report.json`"],
            ["P2 on dev01: same check and swap, 3 model calls, $0.0366", "`apps/plan_b/plan_b/evaluation/development/README.md`"],
            ["dev02 hold until 16:55, $35.00 committed once", "Wave 2 storyboard frames 9 to 11, Wave 1 README"],
            ["dev04 messages and verdicts", "`apps/plan_b/plan_b/scenarios/private/dev04.json` (development), storyboard frame 8"],
            ["Pantry 24, 20, 16, 40 and the counters", "`PEEAI_plan/handoffs/wave_2/DEMO.md` section 4, `PEEAI_plan/handoffs/wave_2/evidence/reports/pantry_accounting.json`"],
            ["Partial handoff, 34 distributed, 6-kit deficit", "Wave 2 README (pantry_dev02)"],
            ["Frozen policies, model, limits, seeds", "`freeze.json`, `RUNTIME_CONTRACT.md` section 20"],
            ["Wave 2 test counts", "Wave 2 README and `VERIFICATION.md`"],
            ["Wave 3 test counts (section 12.6)", "`PEEAI_plan/handoffs/wave_3/evidence/reports/checks.json` (clean checkout of 3442874)"],
            ["Held-out results (section 12)", "`apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/` (commit c052338): `campus/report/metrics.json`, `pantry/report/metrics.json`, `README.md`, `FAILURES.md`, read by `PEEAI_plan/submission/make_results.py`"],
            ["Version 1.2 fresh held-out results (section 12.7)", "`apps/plan_b/evaluation/results/wave3b_fresh_20261025T2327Z/` (commit f715dfc): `campus/report/metrics.json`, `pantry/report/metrics.json`, `README.md`, `FAILURES.md`, read by `make_results.py` into `documentation/results_v12.json`"],
            ["Version 1.2 post-hoc diagnostic rerun on spent cases, not held-out (section 12.7)", "`apps/plan_b/evaluation/results/wave3b_rerun_spent_20261025T2345Z/` (commit f715dfc): the same files, and its README's first line says it is not a held-out result"],
            ["Version 1.2 fixes, known limits, freeze and lock", "`apps/plan_b/docs/RUNTIME_CONTRACT.md` section 21, `apps/plan_b/docs/EVALUATION.md`, `freeze_v1_2.json` and `heldout2.json` (commit 5955243)"],
        ],
        [3.3, 3.2],
    )


def main() -> None:
    render_figures()
    doc = new_document(
        title=f"{TITLE}, Project Documentation",
        author=AUTHOR,
        subject="PEAAII Hackathon project documentation",
        keywords="Plan B, community events, AI coordinator, verification, holds, receipts",
    )
    for section in (
        title_block, abstract, problem, different, what_it_does, walkthrough, architecture,
        decision_policy, policies, community, pantry, safety, protocol, results, limitations,
        how_to_run, demo_guide, ethics, future, appendices,
    ):
        section(doc)
    doc.save(OUT)
    neutral_app_properties(OUT)
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
