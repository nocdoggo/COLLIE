"""Build Plan_B_Project_Documentation.docx, the project documentation of Plan B.

    uv run --no-project --with python-docx==1.1.2 python build_doc.py

The report follows PEEAI_plan/submission/REVISION_PLAN.md section 7 (the Rule of Three, the seven
questions, the writing rules). Outside facts and their numbers come from RESEARCH_BRIEF.md [1] to
[37], cited with cite(). The figures are the slide deck's TikZ figures (../slides/figures/*.pdf),
rendered here to 300 dpi PNG with pdftoppm. A figure whose PDF does not exist yet is skipped with
a printed warning, so the report builds while the deck's figures are being redrawn.

The numbers of the final six-case test come from results_v12.json ("fresh"), which
../make_results.py writes from the committed run wave3b_fresh_20261025T2327Z. The earlier 12-case
test comes from results.json (run wave3_heldout_20261025T1625Z) and the diagnostic rerun on its
spent cases from results_v12.json ("rerun", never a sealed result).
"""

import datetime
import json
import re
import subprocess
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from docx_helpers import (
    PRIMARY,
    bullets,
    cite,
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
LOGO_SOURCE = HERE.parent / "slides" / "Blue-UMB-logo-lockup.png"
LOGO_BOX = (1012, 1456, 5589, 3643)  # the visible part of the 6600 by 5100 lockup
PNG = HERE / "figures"
SHOTS = HERE.parent / "screenshots"
LOGO = PNG / "umb_lockup_blue.png"
OUT = HERE / "Plan_B_Project_Documentation.docx"
RESULTS = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
V12 = json.loads((HERE / "results_v12.json").read_text(encoding="utf-8"))
COMPARISON_BRIEF = HERE.parent / "COMPARISON_BRIEF.md"

TITLE = "Plan B, The Show Must Go On"
PROMISE = "Plan B checks before it changes anything."
TAGLINE = "Check the fact. Pick only what fits. Leave a receipt."
MONEY = "Money waits for a person's OK."
STUDENT = "It checks the text before you spend club money, and leaves the treasurer a record of why."
AUTHOR = "Noctis Zhang, Zhen Lu and Yinzhi Jin"
AUTHOR_LINES = (
    "**Noctis Zhang** and **Zhen Lu**, Department of Computer Science, University of Massachusetts Boston",
    "**Yinzhi Jin**, Department of Management Information Systems, Carnegie Mellon University",
)
EVENT = "PEAAII AI Applications Hackathon 2026, October 2026"
REPO = "https://github.com/nocdoggo/FA26-COLLIE"

# The deck's figures used here, in the order they appear. Anything else in ../slides/figures is
# not rendered (old figures whose wording breaks the writing rules stay out of the report).
USED_FIGURES = [
    "fig_hook", "fig_ideas", "fig_check", "fig_fits", "fig_receipt", "fig_whatif", "fig_design",
    "fig_pantry_kits", "fig_test", "fig_outcomes", "fig_flow", "fig_people", "fig_others", "fig_why",
]
SLIDE_FIGURE_WIDTH_IN = 6.0

_figure_count = 0
_table_count = 0


def render_figures() -> None:
    """Render each figure the report uses from its PDF to a 300 dpi PNG, and crop the blue UMass
    Boston lockup to its visible box at native resolution (Pillow, when it is installed)."""
    PNG.mkdir(exist_ok=True)
    for stem in USED_FIGURES:
        pdf = FIGURES / f"{stem}.pdf"
        target = PNG / f"{stem}.png"
        if not pdf.exists():
            continue
        if target.exists() and target.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile", str(pdf), str(PNG / stem)], check=True)
    if not LOGO.exists():
        try:
            from PIL import Image
        except ImportError:
            print("warning: Pillow is not installed, so the cropped lockup cannot be made")
            return
        Image.open(LOGO_SOURCE).crop(LOGO_BOX).save(LOGO, optimize=True)


def fig(doc, stem: str, caption: str, width_in: float = SLIDE_FIGURE_WIDTH_IN) -> None:
    """A numbered figure from the deck's figure PDFs. A missing figure stops the build."""
    global _figure_count
    pdf = FIGURES / f"{stem}.pdf"
    if not pdf.exists():
        raise SystemExit(f"figure {stem} is missing, build it in ../slides/figures first")
    _figure_count += 1
    figure(doc, PNG / f"{stem}.png", f"Figure {_figure_count}. {caption}", width_in)


def shot(doc, name: str, caption: str, width_in: float = 6.0) -> None:
    """A numbered screenshot of the running board, at its native resolution, only scaled down."""
    global _figure_count
    path = SHOTS / name
    if not path.exists():
        raise SystemExit(f"screenshot {name} is missing")
    _figure_count += 1
    figure(doc, path, f"Figure {_figure_count}. {caption}", width_in)


def tab(doc, caption: str, header: list[str], rows: list[list[str]], widths: list[float]) -> None:
    """A numbered table with its caption above it."""
    global _table_count
    _table_count += 1
    paragraph = doc.add_paragraph(style="Caption")
    rich(paragraph, f"Table {_table_count}. {caption}")
    paragraph.paragraph_format.keep_with_next = True
    table(doc, header, rows, widths)


def h1(doc, text: str) -> None:
    doc.add_heading(text, level=1)


def h2(doc, text: str) -> None:
    doc.add_heading(text, level=2)


def fresh_totals() -> dict:
    fresh = V12["fresh"]
    suites, ai = ("campus", "pantry"), ("P1", "P2", "P3")
    met = sum(int(fresh[s][p]["metk"]) for s in suites for p in ("P0", *ai))
    runs = sum(int(fresh[s][p]["metn"]) for s in suites for p in ("P0", *ai))
    ai_met = sum(int(fresh[s][p]["metk"]) for s in suites for p in ai)
    ai_runs = sum(int(fresh[s][p]["metn"]) for s in suites for p in ai)
    cases = sum(int(fresh[s]["P2"]["ncases"]) for s in suites)
    calls = sum(int(fresh[s][p]["calls"]) for s in suites for p in ai)
    refused = sum(int(fresh[s]["all"]["refused"]) for s in suites)
    viol = sum(int(fresh[s]["all"]["viol"]) for s in suites)
    return dict(met=met, runs=runs, ai_met=ai_met, ai_runs=ai_runs, cases=cases, calls=calls, refused=refused, viol=viol)


# ----------------------------------------------------------------------------------------------
# Title, abstract, one page, seven questions
# ----------------------------------------------------------------------------------------------


def title_block(doc) -> None:
    if LOGO.exists():
        doc.add_picture(str(LOGO), width=Inches(2.2))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.LEFT
    else:
        print("warning: the cropped lockup is missing, title block has no logo")
    title = doc.add_paragraph()
    run = title.add_run(TITLE)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(26), PRIMARY
    title.paragraph_format.space_before = Pt(12)
    title.paragraph_format.space_after = Pt(4)
    promise = doc.add_paragraph()
    run = promise.add_run(PROMISE)
    run.font.size = Pt(14)
    para(doc, f"**{TAGLINE}** {MONEY}")
    para(doc, "Project documentation")
    for line in (*AUTHOR_LINES, EVENT):
        p = para(doc, line)
        p.paragraph_format.space_after = Pt(0)
    para(doc, f"Code and these documents, <<{REPO}>>").paragraph_format.space_before = Pt(6)


def abstract(doc) -> None:
    t = fresh_totals()
    h1(doc, "Abstract")
    para(
        doc,
        f"**{TAGLINE}** Plan B is a free and open AI event coordinator for small volunteer events. "
        "When a text says the projector may be late, Plan B looks up the one fact the decision "
        "depends on. It lists every allowed change, throws out the ones that break the time, the "
        "people or the budget, and lets the AI pick one of the changes that fit. Plan B then checks "
        "the change against the rules before it happens and leaves a receipt, a written record of "
        f"the change. {MONEY} I built Plan B and tested it as a rehearsal on a computer, with "
        f"made-up events. The final test ran {t['cases']} cases that were sealed before the test "
        f"began. {t['met']} of {t['runs']} runs met the expected outcome. Every AI run met it "
        f"({t['ai_met']} of {t['ai_runs']}), the fixed rules with no AI missed one, and no executed "
        "action broke a rule. The whole test cost $3.61 in AI service charges. Six cases are a small "
        "check, not a ranking, and no club, pantry or person has used Plan B yet.",
    )


def one_page(doc) -> None:
    t = fresh_totals()
    h1(doc, "Plan B in one page")
    para(
        doc,
        "**The 30-second version.** Jordan, a volunteer organizer we made up, gets a text twenty "
        "minutes before doors open. The projector may be 25 minutes late. Plan B does not panic and "
        "does not spend. It checks the delivery first, which says about 5.25 pm. It lists every possible "
        "change, keeps the 3 that fit the time, the people and the budget, and the AI picks the free "
        "one, swapping two activities. Plan B checks the change and leaves a receipt. Doors open on "
        "time, and the projector arrives in time for the demonstrations. No club money spent.",
    )
    para(
        doc,
        "**The moment of tension.** At 4.40 pm the text arrives. If it is true, the demonstrations "
        "at 5.10 pm start with no projector. A backup projector costs $35. Jordan is carrying chairs, "
        "the advisor is not picking up, and the three easy moves are all bad. Wait and hope, spend "
        "$35 of club money on a maybe, or reshuffle the evening alone.",
    )
    fig(doc, "fig_hook", "At 4.40 pm a text says the projector may be 25 minutes late, and Jordan has three bad moves.")
    tab(
        doc,
        "The three ideas of Plan B, each in three parts.",
        ["Idea", "Part a", "Part b", "Part c"],
        [
            [
                "**1. Check the fact**",
                "A message is a claim, not a fact. A text can be wrong, late, about another order or sent twice.",
                "Look up only the fact that could change the plan. One look-up, 2 rehearsal minutes, the answer \"delayed, expected about 5.25 pm\".",
                "Most messages should change nothing. A false alarm, a note about another order or the same note twice leaves the plan as it is.",
            ],
            [
                "**2. Pick only what fits**",
                "Plan B lists every allowed change. Keep, swap, a ten-minute shift, the backup, and pairs of these. 16 for Jordan.",
                "It throws out any that break the time, the people or the budget. 3 fit.",
                "The AI reads the messages and picks one, but cannot change the plan itself. It picked the free swap.",
            ],
            [
                f"**3. Leave a receipt**\n{MONEY}",
                "Plan B checks every change against the rules before it happens. If a check fails, it says so and keeps the plan.",
                "Every accepted change leaves a receipt. What changed, when, which part of Plan B made it, and what it cost.",
                f"{MONEY} Plan B's own spending allowance is $0, and only a person can raise it.",
            ],
        ],
        [1.2, 1.75, 1.75, 1.8],
    )
    para(
        doc,
        f"**The headline result.** On {t['cases']} test cases sealed before the final test, "
        f"{t['met']} of {t['runs']} runs met the expected outcome. Every AI run met it. The fixed "
        "rules with no AI missed one, a late volunteer whose message they were never written to read. "
        "No executed action broke a rule. Six cases are a small check, not a ranking.",
    )
    para(doc, f"**The sentence a student can repeat.** \"{STUDENT}\"")


SECTIONS = {
    "problem": "1. The problem we want to solve",
    "ideas": "2. Three ideas",
    "evening": "3. Jordan's evening, step by step",
    "works": "4. How Plan B works",
    "people": "5. Who takes part, and the made-up pantry",
    "tested": "6. How we evaluated the AI agents",
    "results": "7. Results",
    "responsible": "8. Responsible use of AI",
    "market": "9. Who it is for, our target market",
    "others": "10. Who else does this, our direct and indirect competitors",
    "why": "10.3 Why Plan B and not the tools people already use",
    "benefit": "11. How students and the community benefit",
    "limits": "12. Limitations",
    "run": "13. How to run it",
    "demo": "14. Demo guide",
    "else": "15. Anything else to add",
    "close": "16. Three ideas, one evening",
    "sources": "Key sources and acknowledgement",
}


def seven_questions(doc) -> None:
    h1(doc, "The seven questions at a glance")
    para(doc, "The hackathon asks seven questions. Each one is answered in its own section, named here.")
    s = SECTIONS
    tab(
        doc,
        "Where each of the seven questions is answered.",
        ["Question", "Where it is answered"],
        [
            ["1. What problems would you like to solve?", f"{s['problem']}, told through Jordan's evening, and Plan B in one page"],
            ["2. Who are your direct and indirect competitors?", f"{s['others']}, then {s['why']}"],
            ["3. Who is your target market?", f"{s['market']}, and {s['benefit']}"],
            ["4. How does your application work?", f"{s['ideas']}, {s['evening']} and {s['works']}"],
            ["5. Evaluation of AI agents, and responsible use of AI", f"{s['tested']}, {s['results']} and {s['responsible']}"],
            ["6. Key sources and acknowledgement", f"{s['sources']}, with the acknowledgements and the references [1] to [37]"],
            ["7. Anything else to add", f"{s['else']}, then {s['close']}"],
        ],
        [2.6, 3.9],
    )


# ----------------------------------------------------------------------------------------------
# 1 to 5, the story and how Plan B works
# ----------------------------------------------------------------------------------------------


def problem(doc) -> None:
    h1(doc, SECTIONS["problem"])
    para(
        doc,
        "Small volunteer events change by text, with nobody to check, and a wrong move costs club "
        "money or the evening. Plan B is built for the twenty minutes before the doors open, when a "
        "message arrives and somebody has to decide what to do.",
    )
    para(
        doc,
        "Jordan, a volunteer organizer we made up, runs a small campus showcase. This event has no "
        "operations staff. Doors open at 5 pm with a welcome. The community demonstrations at 5.10 pm "
        "need a projector, promised for 5 pm. The skills exchange follows at 5.30 pm. Its leader "
        "checks in at 5.05 pm, and the demonstration presenter at 5.20 pm. Everything has to be done "
        "by 6 pm. At 4.40 pm a text says the projector \"may be about 25 minutes late\".",
    )
    para(doc, "Three things make that moment hard.")
    bullets(
        doc,
        [
            "**A message is a claim, not a fact.** It can be wrong, late, about another order, or the same note sent twice.",
            "**A wrong move costs something.** Spending $35 on a rumor wastes club money. Doing nothing can leave the demonstrations without a projector.",
            "**Jordan decides alone, with twenty minutes left.** Jordan is carrying chairs and the advisor is not picking up. Reshuffling the program by hand means keeping the times, the people and the equipment in one head.",
        ],
    )
    para(
        doc,
        "The problem we want to solve is that moment. A small group should be able to check the one "
        "fact that matters, see only the changes that really fit, and keep a record of what changed "
        "and why, without spending money nobody agreed to.",
    )


def ideas(doc) -> None:
    h1(doc, SECTIONS["ideas"])
    para(doc, f"Plan B rests on three simple ideas. **{TAGLINE}** Under the third idea sits one more line. **{MONEY}**")
    fig(doc, "fig_ideas", "The three ideas, each with one fact from Jordan's evening.")
    h2(doc, "Idea 1. Check the fact")
    bullets(
        doc,
        [
            "**A message is a claim, not a fact.** A text can be wrong, late, about another order or sent twice.",
            "**Look up only the fact that could change the plan.** For Jordan that is the delivery. One look-up takes 2 rehearsal minutes and answers \"delayed, expected about 5.25 pm\".",
            "**Most messages should change nothing.** A false alarm, a note about another order or the same note twice leaves the plan as it is.",
        ],
    )
    para(doc, "**Why.** Acting on a rumor is the mistake that costs money. Each look-up takes time (two minutes in the rehearsal), so Plan B looks up only the one fact that could change the decision.")
    h2(doc, "Idea 2. Pick only what fits")
    bullets(
        doc,
        [
            "**Plan B lists every allowed change.** Keep the plan, swap two activities, shift one by ten minutes, book the backup, or pairs of these. For Jordan that is 16 changes.",
            "**It throws out any that break the time, the people or the budget.** 3 fit. A change that would start the demonstrations before the projector arrives never reaches the AI.",
            "**The AI reads the messages and picks one, but cannot change the plan itself.** It picked the free swap.",
        ],
    )
    para(
        doc,
        "**Why only pick.** The AI reads messy messages well, but it can answer differently each "
        "time. So in our design it never writes a change the rules have not checked. The AI chooses. "
        "Plan B makes the change.",
    )
    h2(doc, f"Idea 3. Leave a receipt. {MONEY}")
    bullets(
        doc,
        [
            "**Plan B checks every change against the rules before it happens.** The right role, the plan still current, within budget. If a check fails, it says so and keeps the plan.",
            "**Every accepted change leaves a receipt.** A receipt is a written record of the change. It says what changed, when, which part of Plan B made it, and what it cost. For Jordan, 4.43 pm, plan version 1 to 2, $0, and the $35 backup not booked. The treasurer can read it.",
            f"**{MONEY}** Plan B's own spending allowance is $0. It can hold a backup for free while it asks, and only a person can allow spending.",
        ],
    )
    para(doc, "**Why.** Spending club money is a decision a person should own, and a written record lets anyone see later what changed and why. Plan B holds a backup for free first, so it is not lost while the person decides, and nothing is spent if nobody answers.")


def evening(doc) -> None:
    h1(doc, SECTIONS["evening"])
    para(
        doc,
        "Jordan's evening is a practice case in Plan B's rehearsal on a computer, a practice copy "
        "of an event with a clock we can speed up, where nothing real is booked or bought. The "
        "event, the times, the people and the numbers are that practice case.",
    )
    h2(doc, "3.1 The main run")
    numbered(
        doc,
        [
            "**Setup.** Doors open at 5 pm with a welcome. The demonstrations at 5.10 pm need the projector, promised for 5 pm. The skills exchange follows at 5.30 pm. The skills exchange leader checks in at 5.05 pm and the demonstration presenter at 5.20 pm.",
            "**The text (idea 1).** At 4.40 pm a text says the projector may be about 25 minutes late. Plan B treats it as a claim, not a fact.",
            "**The look-up (idea 1).** Plan B looks up the delivery once. In the rehearsal that takes 2 minutes. The answer is \"delayed, expected about 5.25 pm\". An expected time is still not an arrival.",
            "**The changes that fit (idea 2).** Plan B lists every allowed change, 16 in all, and throws out any that break the time, the people or the budget. 3 fit. The AI picks one of the 3, the free swap. The skills exchange moves up to 5.10 pm, since its leader is there from 5.05 pm, and the demonstrations move to 5.30 pm, after the expected arrival and after the presenter checks in.",
            "**The receipt (idea 3).** At 4.43 pm Plan B checks the swap against the rules, makes it and writes a receipt. The plan goes from version 1 to version 2. $0 is spent, and the $35 backup is not booked. Jordan tells the group chat and the host from the new plan on the board. Plan B sends no messages in the rehearsal.",
            "**Resolution.** Doors open at 5 pm on time. The projector arrives at 5.24 pm, in time for the demonstrations at 5.30 pm.",
        ],
    )
    fig(doc, "fig_check", "Plan B treats the text as a claim and looks up the delivery once, while most messages change nothing.")
    fig(doc, "fig_fits", "Of 16 allowed changes, 3 fit the time, the people and the budget, and the AI picks the free swap.")
    fig(doc, "fig_receipt", "The receipt at 4.43 pm records the swap, version 1 to 2, $0 spent and the $35 backup not booked.")
    h2(doc, "3.2 A practice case under idea 1, four messages and no change")
    para(doc, "Another practice case shows the third part of idea 1, that most messages should change nothing.")
    numbered(
        doc,
        [
            "The same delay text arrives, but the look-up says the delivery is on schedule, expected at 4.58 pm. It is a false alarm, so the plan stays.",
            "At 4.44 pm a reminder says an order for a workshop on October 29 was cancelled. That is another order on another date, so it does not apply.",
            "The reminder arrives again at 4.46 pm, and a volunteer forwards it at 4.47 pm. One source repeated is still one source.",
            "Plan version 1 is kept. No hold, no spending, no change.",
        ],
    )
    h2(doc, "3.3 A practice case under idea 3, the 5.45 pm \"what if\"")
    para(
        doc,
        "This is a separate practice case, never part of Jordan's main run. If the look-up had said "
        "5.45 pm, too late for either slot, Plan B holds the backup projector for free. Held for free "
        "means kept aside for ten minutes at no cost and released on its own, here at 4.55 pm. Plan B "
        "then asks the organizer to allow $35, because its own spending allowance is $0 and only a "
        "person can raise it. The organizer says OK in their own session, and only then is the backup "
        "booked, once, for $35.00. In a recorded run of this case the AI made that choice at 4.48 pm, "
        "after the OK. If nobody had answered, the hold would have lapsed, nothing would have been "
        "bought, and the evening might have had no projector.",
    )
    fig(doc, "fig_whatif", "A second practice case, where the backup is held for free, the organizer says OK and $35 is spent once.")
    h2(doc, "3.4 Which run these pictures show")
    para(
        doc,
        "Acted out on a computer. In an earlier recorded run, the AI made the same choice. "
        "The pictures of Jordan's evening come from a rehearsal of this case with the fixed rules, "
        "with no AI. In an earlier recorded run of the same case, an earlier version of our "
        "coordinator made the same look-up and the same swap at 4.43 pm, with 3 AI calls costing "
        "under 4 cents ($0.0366). That recorded run used an earlier version, not version 1.2, which "
        "is the one tested in section 7. On a real night the look-up would be the delivery company's "
        "tracking page, and that link is not built yet.",
    )


def works(doc) -> None:
    h1(doc, SECTIONS["works"])
    para(
        doc,
        "**In plain words.** Messages come in. The AI reads them and helps decide what to do. Plan B's "
        "server, the part that keeps the plan and is the only part allowed to change it, does the "
        "rest. It answers look-ups, lists the allowed changes and checks each one against the time, "
        "the people and the budget. It checks every change against the rules before it happens and "
        "writes a receipt. People watch the same plan on a board in their browser. The organizer "
        "approves any spending in their own session, and staff record what really arrived.",
    )
    fig(doc, "fig_design", "Messages come in, the AI picks from the changes that fit, and Plan B checks every change and writes the receipt.")
    para(
        doc,
        "**The running board.** The three pictures below are screenshots of the real board in a "
        "rehearsal of Jordan's evening with the fixed rules, so the ranking shown is the fixed rules' "
        "ranking, not the AI's pick. The board uses its own words. Its log marks every stated reason "
        "as narration and not evidence, and shows internal names and clock times the way the code "
        "prints them.",
    )
    shot(doc, "shot_campus_beforeafter_crop.png", "The running board after the swap. The demonstrations move from 5.10 pm to 5.30 pm and the skills exchange from 5.30 pm to 5.10 pm, and nothing else changes.")
    shot(doc, "shot_campus_alternatives.png", "The changes that fit, best first, on the running board. The free swap ranks first of 3, with no added spending.")
    shot(doc, "shot_campus_trail.png", "The board's log at 4.40 pm to 4.43 pm, newest on top. The look-up, the decision, the change and its receipt.")
    para(doc, "Each time something changes, our coordinator does one of five things.")
    tab(
        doc,
        "The five things our coordinator can do with a new message.",
        ["What it does", "When", "Example from the practice cases"],
        [
            ["Keep the plan", "The message changes nothing", "A reminder about another order on another date"],
            ["Look up the fact", "One fact could change the decision", "The delivery says delayed, expected about 5.25 pm"],
            ["Hold for free", "A backup may be needed while a fact or an OK is pending", "The backup projector held until 4.55 pm, in the separate 5.45 pm practice case"],
            ["Make a change", "A change fits and the rules allow it", "The free swap at 4.43 pm, with its receipt"],
            ["Say it cannot be done", "No change fits", "Plan B names what blocks it and changes nothing that breaks a rule"],
        ],
        [1.4, 2.4, 2.7],
    )
    h2(doc, "4.1 The four approaches we compared")
    para(
        doc,
        "Every approach works on the same plan, the same tools and the same limits, and in every "
        "approach only Plan B's server can make a change, and it checks each one. They differ in who "
        "decides the next step.",
    )
    tab(
        doc,
        "The four approaches.",
        ["Approach", "How it decides"],
        [
            ["Our coordinator", "The AI reads the messages and picks one step from a short list Plan B built and checked. This is my design."],
            ["The check-all variant", "Our coordinator, with every relevant look-up made by the server first."],
            ["The tool-calling model", "The AI calls Plan B's tools itself and chooses its own next tool. The server still checks every call."],
            ["The fixed rules", "Written rules and a small message reader, with no AI and no cost."],
        ],
        [1.8, 4.7],
    )
    para(
        doc,
        "So \"the AI only picks\" describes our coordinator and the check-all variant. The "
        "tool-calling model chooses its own tools. What holds for all four is that only the server "
        "can make a change.",
    )
    h2(doc, "4.2 Details that matter")
    bullets(
        doc,
        [
            "**The receipt names the part that acted.** It records which part of Plan B made the change, for example our coordinator's own login and its allowance. It does not name the organizer, because free changes inside the rules happen without a person.",
            "**The AI's reason is shown as untrusted text.** The board shows the AI's stated reason under the label \"untrusted model text, not evidence\". The receipts and the checks are the evidence.",
            "**The AI model.** The three AI approaches used Claude Sonnet 5.5 by Anthropic, reached through OpenRouter. The settings accept any AI service that takes the same requests as OpenAI's, chosen with one setting, but only this one model was run.",
            "**Limits on each run.** At most 48 tool calls, 8 AI calls, $0.50 of AI service charges and 900 seconds.",
            "**Each role has a written list of what it may do.** The server enforces those lists. The coordinator may look up a fact, hold a backup for free or make a change the rules allow. It cannot record that stock arrived, which only staff may do.",
        ],
    )
    tab(
        doc,
        "The parts of Plan B. Appendix B shows where each one lives in the code.",
        ["Part", "What it does"],
        [
            ["Store", "Keeps the plan, its versions, holds, receipts and stock"],
            ["Tools and checks", "Check the role, the plan version and the budget before a change, then write the receipt"],
            ["Change lister", "Lists the allowed changes and checks each against time, people and budget"],
            ["AI coordinator", "Reads messages and picks a step from the checked list"],
            ["Rehearsal clock", "A clock we can speed up and messages that arrive at set times"],
            ["Test runner", "Seals cases, runs them, scores the end state"],
            ["Board", "What the organizer, volunteers, staff and the moderator see"],
        ],
        [1.6, 4.9],
    )


def people(doc) -> None:
    h1(doc, SECTIONS["people"])
    bullets(
        doc,
        [
            "**Sign-in.** The moderator signs in with a code Plan B makes on its first start, and gives each role a one-time join code. Each browser tab is its own session.",
            "**Volunteers** check in for their own role from a phone link. A check-in can make the plan stop fitting, and Plan B then looks for a change that fits.",
            "**A partner** may offer a listed backup, such as a spare kit. An accepted offer changes only that item's status.",
            "**The organizer** approves spending in their own session. No message gives anyone a say over money or bookings.",
        ],
    )
    h2(doc, "5.1 The made-up pantry, a second example of the same three ideas")
    para(
        doc,
        "The pantry is made up, not based on any real pantry's data. It shows that the same three "
        "ideas work for a distribution day. 40 kits are needed by 1.40 pm. 24 are on the shelf and "
        "20 are late, so the late ones are not counted until staff sign for them.",
    )
    numbered(
        doc,
        [
            "**Check the fact.** A delivery claim counts for nothing until staff sign for the kits.",
            "**Pick only what fits.** Late kits do not count, so the change that fits is a partner's 16 kits, held for free.",
            "**Leave a receipt.** Each accepted change is written down, and the handoff waits for staff to sign. Staff sign for 10 of the 16, and the other 6 stay with the partner. 34 kits are handed out on time, and Plan B tells staff that 6 will be short. Staff decide what to tell the line, and no kit is counted twice.",
        ],
    )
    fig(doc, "fig_pantry_kits", "Kits at four moments of the made-up pantry's day. Late kits and kits still at the partner are outlines, because they are not counted.")
    shot(doc, "shot_pantry_stock.png", "The made-up pantry's stock on the running board at the start of the day. 24 kits on the shelf, 20 expected and not counted, 0 of 40 handed out yet.")
    shot(doc, "shot_pantry_trail.png", "The board's log for the made-up pantry. Plan B checks the claims, holds the partner's 16 kits for free and asks staff for the handoff.")
    para(
        doc,
        "Two of the six final test cases were pantry days, and all 20 of their runs met the expected "
        "outcome. The pantry needed a small extension for counting stock, so it reuses the same core "
        "with new code rather than a new settings file alone. It handles identical boxed kits only, "
        "with no fresh food, household sizes or client choice.",
    )
    para(doc, "**Plan B counts kits, never people. Who gets food is always a person's call, and Plan B never decides who goes without.**")


# ----------------------------------------------------------------------------------------------
# 6 to 8, tests, results, responsible use
# ----------------------------------------------------------------------------------------------


def tested(doc) -> None:
    h1(doc, SECTIONS["tested"])
    para(doc, "Five words first, in plain terms.")
    bullets(
        doc,
        [
            "**A test case** is a small made-up event day written in advance, with messages that arrive at set times. We run it in the rehearsal, and at the end code checks the final state, for example that every activity happened by 6 pm, the welcome started at 5 pm, nothing started before its equipment arrived, and no rule was broken.",
            "**The rehearsal on a computer** is a practice copy of the event, with a clock we can speed up, where nothing real is booked or bought.",
            "**A sealed case** was written and locked before the final test, and never seen by the person who changed the code. The six sealed cases use new wording but the same kinds of trouble as earlier cases.",
            "**3 runs** means the same case repeated three times with the AI, because the AI can answer differently each time. The fixed rules give the same answer every time, so they ran once. 6 cases times (1 plus 3 approaches times 3 runs) is 60 runs.",
            "**Met the expected outcome** means the code's checks on the final state all passed. For most cases that means the event ran on time with no rule broken. For a case that cannot be fully done, it means Plan B said so plainly instead of pretending.",
        ],
    )
    fig(doc, "fig_test", "One test, from a made-up event day and its messages to code that checks the end state.")
    h2(doc, "6.1 How the final test ran")
    bullets(
        doc,
        [
            "**Sealed first.** The code, the AI instructions, the model and the limits were locked at 23.23.47 UTC on October 25, 2026, with a digital fingerprint that shows any later change. The six cases were locked at 23.23.54 UTC. The first AI call of the test came at 23.27.31 UTC.",
            "**Four campus cases and two pantry cases**, each run once with the fixed rules and three times with each of the three AI approaches, one run at a time.",
            "**Scored by the end state.** Code reads the final plan and the receipts, not the AI's explanation. A run that stops early still counts.",
            "**Kept apart.** The person who changed the code never opened the sealed cases. The case author saw no new code, but did read the coder's short written list of the problems to be fixed. That isolation is good but not perfect.",
            "**Same kinds of trouble.** Each sealed case repeats a kind of trouble seen in development, with new wording. So the test shows new examples of known trouble, not new kinds of trouble.",
        ],
    )
    para(
        doc,
        "Scoring by the final state of the rehearsal follows τ-bench, which compares the database "
        f"at the end of a conversation with the goal state {cite(30)}. Running each AI case three "
        f"times follows the same paper's idea of checking how reliably an agent behaves over repeated "
        f"trials {cite(30)}. We count runs that met the outcome and do not compute that paper's own "
        "measure.",
    )


SIX_CASES = [
    ["Projector late", "C09", "The projector really arrives too late for its slot", "The evening runs on time with no rule broken", "10 of 10"],
    ["False alarm", "C10", "An anonymous call says the projector will be late, but the delivery is on time", "No unneeded change", "10 of 10"],
    ["Volunteer late", "C11", "The skills exchange leader texts that their bus is out of service", "The evening still runs on time", "9 of 10 (the fixed rules missed it)"],
    ["Cannot be saved", "C12", "The projector fails its test and the spare cannot be confirmed in time", "Plan B says plainly that it cannot be done", "10 of 10"],
    ["Pantry delivery", "T05", "The late delivery cannot arrive in time, but a partner's kits can", "The 40 kits are handed out on time", "10 of 10"],
    ["Pantry claims", "T06", "Wrong and stale delivery claims, and a partner who declines", "Plan B hands out what it can and says plainly how many are short", "10 of 10"],
]


def results(doc) -> None:
    t = fresh_totals()
    fresh = V12["fresh"]
    h1(doc, SECTIONS["results"])
    h2(doc, "7.1 The final test on six sealed cases")
    para(
        doc,
        f"**{t['met']} of {t['runs']} runs met the expected outcome.** Every AI run met it "
        f"({t['ai_met']} of {t['ai_runs']}). The fixed rules missed one. No executed action broke a "
        f"rule. Plan B refused {t['refused']} attempts, and nothing happened. The whole test cost "
        f"$3.61 in AI service charges for {t['calls']} AI calls, with no errors from the AI service.",
    )
    fig(doc, "fig_outcomes", "Each of the six sealed cases with its one fixed-rules run and nine AI runs, where only one run missed.")
    tab(
        doc,
        "The six sealed cases and their results.",
        ["Case", "What happens", "What met means here", "Runs met"],
        [row[:1] + row[2:] for row in SIX_CASES],
        [1.1, 2.35, 1.95, 1.1],
    )
    rows = []
    names = {"P0": "The fixed rules", "P1": "The tool-calling model", "P2": "Our coordinator", "P3": "The check-all variant"}
    for p in ("P2", "P3", "P1", "P0"):
        met = sum(int(fresh[s][p]["metk"]) for s in ("campus", "pantry"))
        n = sum(int(fresh[s][p]["metn"]) for s in ("campus", "pantry"))
        usd = sum(float(fresh[s][p]["usd"]) for s in ("campus", "pantry"))
        calls = sum(int(fresh[s][p]["calls"]) for s in ("campus", "pantry"))
        per_run = f"about {100 * usd / n:.1f} cents" if usd else "no cost"
        rows.append([names[p], f"{met} of {n}", str(calls), f"${usd:.2f}", per_run])
    tab(doc, "Results and cost per approach in the final test.", ["Approach", "Runs met", "AI calls", "AI service cost", "Cost per run"], rows, [1.9, 1.0, 0.9, 1.3, 1.4])
    bullets(
        doc,
        [
            "**The one miss.** The fixed rules missed the late-volunteer case because they were never written to read a volunteer's own message. This does not show that the AI helps, because the AI approaches were changed after failing the same kind of case earlier.",
            "**No approach looked anything up in the late-volunteer case.** All of them took the volunteer's word. That is a known limit (section 12).",
            "**The 6 refused attempts** were all on pantry days. 5 asked for a partner's rack that the case was built to decline, and 1 was based on an out-of-date plan. They were expected refusals, not misbehavior.",
            "**The false alarm** led to no unneeded change in any of its 10 runs. **The case that cannot be saved** was said plainly in all 10 runs.",
            "**Cost per run.** Our coordinator cost about 2.9 cents a run on the campus cases and about 7.0 cents on the pantry days, so 3 to 7 cents. The tool-calling model met the same 18 of 18 at about three times the cost. So the test does not show that picking from a list improves outcomes. It shows the same outcomes at about a third of the cost.",
            "**How often each approach looked things up**, as description only. On the campus cases our coordinator made 10 look-ups in 12 runs and the check-all variant 18 in 12. Fewer look-ups is not better in itself. In the earlier test the check-all variant cost less than our coordinator and met more of the campus runs.",
            "**Six cases are a small check, not a ranking.** They cannot show that one approach is better than another.",
        ],
    )
    earlier(doc)


# The earlier test's cost per approach, summed from the unrounded suite costs in
# apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/README.md (campus plus pantry).
EARLIER_USD = {"P1": 3.006960 + 2.555110, "P2": 1.004722 + 0.953090, "P3": 0.570856 + 0.986032}


def earlier(doc) -> None:
    r, rerun = RESULTS, V12["rerun"]
    h2(doc, "7.2 The earlier 12-case test, which found four problems")
    para(
        doc,
        "Before the final test, an earlier sealed test ran the previous version on 12 cases, 8 campus "
        f"and 4 pantry, in {r['campus']['all']['recorded'] + r['pantry']['all']['recorded']} runs. "
        "It found four problems, which I worked on before the final test. An earlier planning brief "
        "for this submission said three problems, and the records of that test say four, so this "
        "report says four. Those 12 cases are now spent, because the code was changed after reading "
        "their failures.",
    )
    names = {"P0": "The fixed rules", "P1": "The tool-calling model", "P2": "Our coordinator", "P3": "The check-all variant"}
    tab(
        doc,
        "Runs that met the expected outcome in the earlier test, per approach.",
        ["Approach", "Campus, 8 cases", "Pantry, 4 cases", "AI service cost"],
        [
            [names[p], r["campus"][p]["met"].replace("/", " of "), r["pantry"][p]["met"].replace("/", " of "),
             f"${EARLIER_USD[p]:.2f}" if p != "P0" else "no cost"]
            for p in ("P0", "P1", "P2", "P3")
        ],
        [2.0, 1.5, 1.5, 1.5],
    )
    bullets(
        doc,
        [
            "**The four problems.** A volunteer's own report of a delay never reached the part that lists changes. A partner's stock already found unavailable stayed on the list. Some runs used up the 8 AI calls without making progress. A change refused only because the plan had just moved on needed a new AI call to try again, and the limit of 8 AI calls sometimes came first.",
            "**What changed.** Version 1.2 passes a person's delay on as something to plan around, drops stock already found unavailable, stops asking the AI again about the same unchanged list, and resends a refused change when it still fits.",
            "**A later rerun still misses two of the targeted cases in every run, and a third in two of its three runs.** In a rerun on the spent cases after the changes, our coordinator still missed the case where the look-up service is down in 3 of 3 runs, the check-all variant still missed a pantry case with duplicate and misleading quantity claims in 3 of 3, and the tool-calling model still missed a pantry case in 2 of 3. This rerun is a diagnostic, not a sealed result, and it cannot show that version 1.2 is better.",
        ],
    )
    para(
        doc,
        f"Rerun counts, for the record. Campus, our coordinator {rerun['campus']['P2']['met'].replace('/', ' of ')}, "
        f"the check-all variant {rerun['campus']['P3']['met'].replace('/', ' of ')}. Pantry, our coordinator "
        f"{rerun['pantry']['P2']['met'].replace('/', ' of ')}, the check-all variant "
        f"{rerun['pantry']['P3']['met'].replace('/', ' of ')}, the tool-calling model "
        f"{rerun['pantry']['P1']['met'].replace('/', ' of ')}.",
    )
    h2(doc, "7.3 Automated tests of the app")
    bullets(
        doc,
        [
            "951 Python tests passed on the final version of the code (896 passed on version 1.1), and 397 web tests passed.",
            "11 of the 12 small release checks pass, and the 12th does not apply because the link to bus and train alerts was not built. These checks are automated tests of the app, run separately from the final test. Among them, a change made against an old copy of the plan is refused with nothing half done, an offer or a check-in gives no say over money or bookings, text that says \"ignore your instructions\" stays text, no receipt is invented after a failure, and every receipt matches what was saved.",
            "The checks on misleading messages use a scripted, deliberately fooled AI, not the real model.",
        ],
    )


def responsible(doc) -> None:
    h1(doc, SECTIONS["responsible"])
    para(
        doc,
        "Plan B follows five practices. Each comes with what outside sources say, how Plan B meets "
        "it, and a careful note on what we do not claim.",
    )
    fig(doc, "fig_flow", "What goes where, from a message to the outside AI service, Plan B's checks, the receipt and the person who approves money, with the limits beside it.")
    practices = [
        (
            "8.1 Check the fact, and pick only what fits",
            f"OWASP, a security group, lists prompt injection (a message that tries to give the AI new orders) first among the risks of AI language apps, and among ways to reduce its impact lists separating and clearly marking untrusted content {cite(33)}. Its entry on AI that is allowed to do too much recommends that the systems around the AI decide what is allowed, rather than letting the AI decide what is allowed {cite(34)}. The UK National Cyber Security Centre says current models do not keep instructions and data apart, and that protections should rely more on fixed safeguards outside the model {cite(37)}. Anthropic warns that Claude may sometimes follow commands found in content {cite(36)}.",
            "A message is a claim, and its text is treated as data, not as instructions. Plan B looks up only the fact that could change the decision. The server lists the allowed changes and checks each, and in our coordinator the AI picks only among those that passed. A misleading message can at most lead to a choice among changes that already fit.",
            "This limits what a misleading message can do. It does not prevent prompt injection, and we do not claim it does.",
        ),
        (
            "8.2 Leave a receipt",
            f"NIST lists accountable and transparent among the qualities of trustworthy AI, including how and when decisions were made and by whom {cite(32)}. The OpenAI paper says a ledger of the actions an agent took may be particularly important {cite(35)}.",
            "The server writes a receipt for every accepted change, and the AI cannot write one. Refused attempts are recorded too. A free hold ends on its own, so it can be reviewed after the fact.",
            "Neither source requires this design. The receipt follows these ideas.",
        ),
        (
            "8.3 Money waits for a person's OK",
            f"OWASP lists human approval for high-risk actions among measures that reduce impact {cite(33, 34)}. A paper by Shavit and colleagues at OpenAI says some decisions, such as a large financial transaction, may be too important to hand to an agent, and that approving many decisions quickly makes each approval less careful {cite(35)}. Anthropic suggests asking a person to confirm decisions with real-world consequences, such as payments {cite(36)}. NIST notes that human roles in overseeing AI need to be clearly defined {cite(32)}.",
            f"{MONEY} Plan B's own spending allowance is $0 by default, so any spending waits for the organizer, who approves it in their own session. The coordinator may make free changes inside the rules and hold a backup for free, so the organizer is asked only about money.",
            "Approval before spending is common practice among the tools in section 10, so it is responsible design, not something new. The allowance is Plan B's own design choice, and the NIST passage is framing, not a requirement.",
        ),
        (
            "8.4 A rehearsal on a computer",
            f"τ-bench scores agents by the final state {cite(30)}. NIST's framework is meant for voluntary use, to bring trustworthiness into design and testing {cite(31)}, and lists valid and reliable, safe, and secure among its qualities {cite(32)}.",
            "Everything runs in the rehearsal. Every action changes a local database and nothing else. Sealed cases are scored by the final state, and paid AI calls run under limits per run and in total.",
            "Plan B's design draws on these ideas. We do not claim that it complies with the NIST framework or is certified against it.",
        ),
        (
            "8.5 No personal data",
            f"NIST lists privacy-enhanced among the qualities of trustworthy AI {cite(32)}.",
            "All events, people, rooms, stock, times and costs are made up. The pantry plans count kits only, with no names and no eligibility, allergy or medical decisions. Plan B counts kits, never people. Who gets food is always a person's call, and Plan B never decides who goes without. No real message was sent and no participant feedback was collected. No pantry, U-ACCESS staff, system or partner took part.",
            "The sources state principles and did not review Plan B. We say the rehearsal uses no personal data, not that Plan B meets a privacy standard.",
        ),
    ]
    for heading, sources, meets, careful in practices:
        h2(doc, heading)
        para(doc, f"**What the sources say.** {sources}")
        para(doc, f"**How Plan B meets it.** {meets}")
        para(doc, f"**Careful.** {careful}")
    h2(doc, "8.6 The privacy rule, and what is still missing")
    para(doc, "**Never put a name, address, health or immigration detail in a message Plan B reads. Every message goes to an outside AI service.**")
    bullets(
        doc,
        [
            "**No tricky message in the final test.** Automated release checks show that \"ignore your instructions\" text is stored as content and changes nothing, but the six sealed cases had no such message.",
            "**OpenRouter passes each call on to one of several companies that run the model,** and we did not record which one answered each call.",
            "**A poor pick that keeps every rule is not caught.** The checks stop changes that break a rule, not changes that are allowed but unwise.",
            "**\"No executed action broke a rule\" is enforced by the same server that is counted.** So it tests the server, not the AI's judgment.",
            "**If nobody answers,** the hold lapses and nothing is bought, and the evening may have no projector.",
            "**The AI service key** stays in a private file on the organizer's own computer, is read for each call and sent only to the AI service, and never reaches the browser or any record.",
        ],
    )


# ----------------------------------------------------------------------------------------------
# 9 to 12, market, competitors, why Plan B, benefit
# ----------------------------------------------------------------------------------------------


def market(doc) -> None:
    h1(doc, SECTIONS["market"])
    bullets(
        doc,
        [
            "**Who uses it.** Student club officers first, then volunteer coordinators of community groups and pantry staff, the people who run small events with little time and no operations staff.",
            f"**The first group to reach.** Student clubs at UMass Boston, which has 100+ student groups {cite(28)} and a student group portal hosted on CampusGroups {cite(14, 15)}. These counts are context, not a market size, and imply no partnership.",
            "**How a group starts.** The code is free to read and run. A group needs one laptop, an account with an AI service, and cents per run (3 to 7 cents a run for our coordinator in the final test), or no account at all with the fixed rules.",
            "**The honest effort.** Today it needs someone comfortable running code. A new event of a known kind is a settings file, and a new kind of day needs new code (the pantry needed a small stock extension).",
            "**Who else gains.** Attendees, whose evening runs on time. Volunteers, whose time is not wasted on unneeded changes. The treasurer or advisor, who can read the receipt.",
        ],
    )
    fig(doc, "fig_people", "Built first for student club officers, then volunteer coordinators and the staff of a pantry like the made-up one.")
    para(doc, "The facts below size the people and the need around these events. None of them measures demand for Plan B.")
    tab(
        doc,
        "Need facts and their limits.",
        ["Fact", "Source", "Its limit"],
        [
            ["An estimated 23 percent of US college students, about 3.8 million, experienced food insecurity in 2020", cite(21), "Data year 2020, report 2024. Shows need for campus food support, not demand for Plan B"],
            ["More than 650 colleges reported a campus food pantry", cite(22), "A count reported in 2018, not a current total"],
            ["59 percent of 74,350 students at 91 institutions had food or housing insecurity, 41 percent food insecurity", cite(23), "Institutions that chose to take part, 2023 to 2024, not a national rate"],
            ["Over 75.7 million people in the US volunteered through an organization between September 2022 and September 2023", cite(24), "Counts volunteers, not events or organizers"],
            ["Nearly 48 million people in the US experienced food insecurity, as USDA reports, and nearly half of them had incomes too high for federal nutrition help", cite(25), "Counts people, not events or organizers"],
            ["40 percent of Massachusetts households were food insecure in 2025, and over 600 pantries and partners depend on The Greater Boston Food Bank", cite(26), "An online survey with its own method, not comparable with national rates"],
            ["About 19.0 million students attended US colleges in fall 2022", cite(27), "Counts students, not clubs or organizers"],
            ["UMass Boston has 100+ student groups", cite(28), "Not evidence that any group wants Plan B"],
            ["The U-ACCESS food pantry at UMass Boston opened in 2013 and relies on community support", cite(29), "Our pantry is made up, with no partnership or data access"],
        ],
        [3.0, 0.8, 2.7],
    )


DIRECT = [
    ["Sessionboard AI Agenda Builder", "When a speaker cancels or a room is lost, its AI assesses the impact and suggests adjustments, checks changes against the agenda's rules, and sends big changes for sign-off", "The page does not describe an expiring free hold or a receipt for each decision. Plan B shows both, the hold in a separate practice case", cite(1)],
    ["Cvent Assistant (announced)", "Announced in July 2026 and expected in the third quarter of 2026. Maps an attendee change request across the platform for one-click review", "The release does not mention a look-up of the one fact, holds or receipts", cite(2)],
    ["Bizzabo agents (announced)", "Announced October 12, 2026. Agents build and update schedules, and nothing goes live until a person approves it. Broad availability planned for early 2027", "The announcement does not describe a fact check on the day or an expiring hold", cite(3)],
    ["ChatGPT agent", "Can rearrange meetings and plan and book events, and asks permission before actions with real-world consequences such as a purchase", "In Plan B the AI picks among changes the server built and checked for one event", cite(4)],
    ["Browse with Copilot", "Acts in the Edge browser and asks for the user's supervision before buying or booking", "Plan B adds the event's own checks, the hold and the receipt", cite(5)],
    ["Gemini Apps tasks", "Edits calendar events and asks for confirmation before purchases or sending messages", "Plan B checks whether a warning is true before it changes a shared event plan", cite(6)],
    ["Zapier Agents", "A user can make an agent wait for confirmation by adding that step. Zapier is moving Agents to AI by Zapier", "In Plan B the checks come built in, and spending always needs a person", cite(7)],
    ["Eventbrite AI tools (2023 post)", "Write event summaries, page copy and ads", "The post says nothing about changes on the day", cite(8)],
    ["Whova AI features", "Help write event descriptions and summaries, and tell organizers to check facts because AI can make things up", "Writing and reporting, not a last-minute problem", cite(9)],
    ["Reclaim.ai", "Adjusts personal and team calendars, with preview and approval for changes asked in conversation", "Personal calendars, not shared equipment and volunteers", cite(10)],
]
INDIRECT = [
    ["GroupMe", "A free group chat, with a campus tab for finding groups", "Where a late warning usually lands. Plan B works behind the chat", cite(11)],
    ["Google Sheets", "A shared spreadsheet with permissions and AI help", "Stands in for the shared run-of-show sheet", cite(12)],
    ["Doodle group polls", "Settle a time before the event", "Plan B handles the day itself", cite(13)],
    ["CampusGroups", "Events, membership, messages and attendance for student groups", "Plan B can sit alongside it", cite(14)],
    ["UMBeInvolved", "UMass Boston's portal for student groups, hosted on CampusGroups", "The local status quo. No integration claimed", cite(15)],
    ["Engage from Encoura, formerly Anthology Engage", "Event planning and reviewer workflows for student affairs", "Planning ahead, not recovery on the day", cite(16)],
    ["SignUpGenius", "Sign-up sheets with reminders and waitlists that fill a cancelled slot", "Does not describe how a late arrival affects the activities that depend on it", cite(17)],
    ["VolunteerHub", "Volunteer shifts, framed by the vendor as a step up from spreadsheets and email", "Vendor framing, not independent evidence", cite(18)],
    ["PantrySoft", "Campus pantry sign-up, appointments and visit tracking", "Plan B would sit beside an intake tool like this", cite(19)],
    ["Link2Feed", "Pantry software, which says pantries depend on volunteers and paper records are hard", "Vendor framing. Plan B sits beside it", cite(20)],
]


def others(doc) -> None:
    h1(doc, SECTIONS["others"])
    para(
        doc,
        f"Event platforms already check agenda changes against rules and send big changes for "
        f"sign-off {cite(1)}, and two have announced agents that turn a request into changes a person "
        f"reviews or approves {cite(2, 3)}. General assistants already ask before they buy or book "
        f"{cite(4, 5, 6)}. Each tool below is described only by what its own page says, and we have "
        "not tested any of them. Plan B does not claim to be the first of its kind.",
    )
    fig(doc, "fig_others", "Where a late text lands today, and the tools that already change plans, each with its source number.")
    h2(doc, "10.1 Direct competitors, tools that already change plans")
    tab(doc, "Direct competitors, tools that already change plans.", ["Tool", "What its own page says", "What Plan B adds", "Source"], DIRECT, [1.3, 2.7, 1.9, 0.6])
    h2(doc, "10.2 Indirect competitors and the status quo")
    para(
        doc,
        f"Today a late message lands in a group chat, a shared spreadsheet or a sign-up sheet "
        f"{cite(11, 12, 17)}. Plan B works behind these tools and does not replace them.",
    )
    tab(doc, "Indirect competitors and the status quo.", ["Tool", "What its own page says", "How Plan B relates", "Source"], INDIRECT, [1.4, 2.5, 2.0, 0.6])
    para(
        doc,
        "What Plan B shows on one community event is the look-up of the one fact the decision "
        "depends on, picking only from changes that fit, and a receipt for every change while money "
        "waits for a person's OK, free and open.",
    )


def why(doc) -> None:
    h2(doc, SECTIONS["why"])
    if COMPARISON_BRIEF.exists():
        print("note: COMPARISON_BRIEF.md exists, check this section against its What not to claim list")
    para(
        doc,
        "Safer, more flexible and more personal, for a small group on the day of an event. Safer is "
        "the payoff of the three ideas. In our design the AI can only choose, Plan B checks every "
        "change before it happens, and the AI cannot spend money unless a person allows it. More "
        "flexible means the same program runs different kinds of events, with whichever AI you pick "
        "or none at all, on your own laptop for free. More personal means your group writes down "
        "its own event, people and backups, and sets how much the AI may spend without asking, and "
        "Plan B follows that.",
    )
    fig(doc, "fig_why", "Safer, more flexible and more personal, each with one simple drawing.")
    tab(
        doc,
        "Why Plan B, each point with how we know it and what the others are built for.",
        ["Point", "Plan B's feature, in plain words", "How we know it", "What the others are built for"],
        [
            [
                "**Safer**",
                "In our coordinator the AI picks only from changes that fit, and in every approach one place checks every change before it happens. A change against an old copy of the plan is refused. Message text that says \"ignore your instructions\" changes nothing. Paying needs the organizer's OK. In the final test no executed action broke a rule in 60 runs.",
                "The release checks in the code (11 of 12 passing, 1 not applicable, Appendix C) and the final test's results",
                f"Sessionboard also checks agenda changes against rules and sends big changes for sign-off {cite(1)}, and its page does not describe a receipt for each decision. In Zapier Agents the user adds the approval step {cite(7)}. General assistants already ask before buying {cite(4, 5, 6)}, so asking is not the difference.",
            ],
            [
                "**More flexible**",
                "One core runs three kinds of event, a campus evening, a community skills exchange and a food pantry (with a small stock extension). It works with any AI service that accepts the same requests as OpenAI's, or with the fixed rules and no AI. It runs on one laptop, free and open source under GPL-3, with no vendor contract. It needs an account with an AI service unless the group uses the fixed rules or a model on its own computer.",
                "The settings file, the three kinds of practice case in the code, and the GPL-3 license file (Appendix B)",
                f"ChatGPT agent, Copilot and Gemini are each their maker's own assistant {cite(4, 5, 6)}. Sessionboard, Cvent and Bizzabo are event platforms for organizers {cite(1, 2, 3)}.",
            ],
            [
                "**More personal**",
                "Each group writes its own event, people, times, backups and stock targets, sets how much the AI may spend without asking (by default nothing, so any spending waits for a person), and picks its own AI model and AI cost limits.",
                "The example event files and the spending check in the code (Appendix B)",
                f"ChatGPT asks before actions with real-world consequences and Gemini before purchases {cite(4, 6)}. Their pages say each assistant is trained or designed to ask before such actions.",
            ],
        ],
        [0.9, 2.5, 1.5, 1.6],
    )
    para(
        doc,
        "A model on the organizer's own computer is allowed by the settings but was not tested in "
        "this project, and only one AI model was run. We have not tested the others.",
    )


def benefit(doc) -> None:
    h1(doc, SECTIONS["benefit"])
    para(doc, f"**\"{STUDENT}\"**")
    bullets(
        doc,
        [
            "**Not deciding alone.** The benefit is not the swap, which Jordan could do by hand. It is not deciding alone at 4.40 pm, with the one fact checked and only the changes that fit on the table.",
            "**No club money on a rumor.** Plan B spends nothing without a person's OK, and the $35 backup stays unbooked when it is not needed.",
            "**A record ready when someone asks.** When the treasurer or advisor asks why the program changed, the receipt is there.",
            f"**For the community.** Volunteer groups and pantries face the same late deliveries and no-shows. Community events run on volunteers, and over 75.7 million people in the US volunteered through an organization between September 2022 and September 2023 {cite(24)}. The code is free, and an evening of AI calls costs cents. Plan B can help such groups. No group uses it yet.",
            "**Easy to start for a known kind of event.** A new event of a known kind is a settings file. A new kind of day needs code.",
        ],
    )
    para(doc, "No user study was run, so we make no claim of time saved.")


# ----------------------------------------------------------------------------------------------
# 13 to 17
# ----------------------------------------------------------------------------------------------


def limits(doc) -> None:
    h1(doc, SECTIONS["limits"])
    bullets(
        doc,
        [
            "**Made-up events only.** No real bookings, rooms, purchases, messages, people or stock.",
            "**Six sealed cases.** A small check. The case is the unit, and three runs of one case are not three different evenings.",
            "**All six sealed cases repeat conditions seen in development**, with new wording.",
            "**The late-volunteer case had no look-up.** Every approach took the volunteer's word. A person's reported delay can also outlive a later check-in, a known limit of version 1.2.",
            "**One AI model**, one AI service, and the route behind it not recorded. The AI can answer differently each time, so runs cannot be repeated exactly.",
            "**No tricky message in the final test**, a poor pick that keeps every rule is not caught, and \"no executed action broke a rule\" tests the server, not the AI's judgment (section 8.6).",
            "**A later rerun still misses targeted cases** of the earlier test (section 7.2).",
            "**No trial with organizers.** No club, pantry or person has used Plan B, and no user study was run.",
            "**Not built yet.** Real delivery tracking and the transit alerts. The look-up is a rehearsal.",
            "**Only Chromium was tested** in the browser. Screen readers, Firefox and Safari were not.",
        ],
    )


def how_to_run(doc) -> None:
    h1(doc, SECTIONS["run"])
    para(
        doc,
        "You need a bash shell (tested on Linux), Python 3.11 or 3.12 with uv, and Node.js 22.18 or "
        "newer with npm. Get the code and start the board.",
    )
    code_block(
        doc,
        [
            f"git clone {REPO}",
            "cd FA26-COLLIE/apps/plan_b",
            "unset VIRTUAL_ENV",
            "uv sync --all-groups --locked",
            "(cd web && npm ci && npm run build)",
            "uv run plan-b serve                # then open http://127.0.0.1:8765",
        ],
    )
    para(
        doc,
        "Open the address on the last line in a browser and sign in with the moderator code in "
        "`var/moderator_code.txt`, which the server writes on its first start. Choose the practice "
        "case `dev01` (Jordan's evening), load it, and run the fixed rules. The server keeps its "
        "terminal busy, so run the next commands in a second terminal in `FA26-COLLIE/apps/plan_b`.",
    )
    para(doc, "Run the practice cases with the fixed rules, and check that the final test's sealed files are unchanged (version 1.2).")
    code_block(
        doc,
        [
            "uv run plan-b run-case all",
            "uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout heldout2.json --require-heldout",
        ],
    )
    para(doc, "Recompute the final test's reports from the committed records, with no AI call.")
    code_block(
        doc,
        [
            "R=evaluation/results/wave3b_fresh_20261025T2327Z",
            "uv run plan-b eval report --results $R/campus --out /tmp/campus_report",
            "uv run plan-b eval report --results $R/pantry --out /tmp/pantry_report",
        ],
    )
    para(
        doc,
        "For a demonstration after the talk, prepare a fresh state with the recorded runs on their "
        "own port. The recorded runs play back with no key and no AI call, and the board labels "
        "each one \"Recorded replay\".",
    )
    code_block(
        doc,
        [
            "uv run python scripts/demo_prep.py",
            "PLAN_B_MODERATOR_CODE='<choose one>' uv run plan-b serve --port 8790 \\",
            "    --var var/demo/state --replay-dir var/demo/replays",
            "# then open http://127.0.0.1:8790/#/replay/live_p2-live_dev02_trace.json",
        ],
    )
    para(doc, "Run the tests of the app.")
    code_block(doc, ["uv run pytest -q", "(cd web && npm test)"])
    para(
        doc,
        "The three AI approaches make paid calls. They need an OpenAI-compatible AI service such as "
        "OpenRouter, set in `.local/keys/model_endpoint.env` at the repository root (the setting "
        "names are in `apps/plan_b/.env.example`), and a key file that only the server reads. "
        "Everything above runs without a key. More commands are in `apps/plan_b/docs/EVALUATION.md`.",
    )


# What to show or say on each slide, in the order of the spoken script. The titles and the planned
# seconds are read from ../slides/pres-note.md, so the guide always follows the script.
DEMO_SHOW = [
    "Name, department, Plan B in one line",
    "The problem and the three bad moves",
    "Check the fact, pick only what fits, leave a receipt",
    "Idea 1 and its three parts",
    "Idea 2, the 16 changes and the 3 that fit",
    "Idea 3, the receipt, and money waits for a person",
    "The real board after the swap, a rehearsal with the fixed rules",
    "What a test case and a sealed case are",
    "The result, the one miss, a small check",
    "How Plan B works inside, responsible use of AI, and what is not done yet",
    "Who it is for, and the made-up pantry",
    "Who else does this",
    "Why Plan B, with \"we have not tested the others\"",
    "The close, the thanks and the ask",
]
SCRIPT = HERE.parent / "slides" / "pres-note.md"


def demo_slides() -> list[tuple[str, int, str]]:
    """Each slide of the spoken script as (title, planned seconds, what to show)."""
    parts = re.split(r"^## ", SCRIPT.read_text(encoding="utf-8"), flags=re.M)[1:]
    slides = []
    for number, part in enumerate(parts):
        heading, _, body = part.partition("\n")
        title = re.sub(r"^Slide \d+\. ", "", heading.strip())
        seconds = int(re.search(r"^_about (\d+) seconds", body, re.M).group(1))
        slides.append((title, seconds, DEMO_SHOW[number] if number < len(DEMO_SHOW) else ""))
    return slides


def demo_guide(doc) -> None:
    h1(doc, SECTIONS["demo"])
    para(
        doc,
        "The talk has no live demo inside its seven minutes. The clock below follows the planned "
        "time of each slide in the spoken script, as minutes and seconds, so \"0.46\" is 46 seconds in.",
    )
    rows, start = [], 0
    for number, (title, seconds, show) in enumerate(demo_slides(), 1):
        end = start + seconds
        rows.append([f"{start // 60}.{start % 60:02d} to {end // 60}.{end % 60:02d}", str(number), title, show])
        start = end
    tab(doc, f"The talk, slide by slide, {start // 60} minutes {start % 60} seconds planned.", ["Clock", "Slide", "Title", "What to show or say"], rows, [1.1, 0.5, 2.6, 2.3])
    para(
        doc,
        "After the talk, the board can show Jordan's practice case run by the fixed rules, or a "
        "recorded AI run played back with no AI call (section 13). Say \"recorded\" whenever a "
        "recorded run is shown, and never call it live.",
    )


def anything_else(doc) -> None:
    h1(doc, SECTIONS["else"])
    bullets(
        doc,
        [
            "**Cost.** The final test's 60 runs cost $3.61 in AI service charges, for 194 AI calls. Our coordinator cost 3 to 7 cents a run. The fixed rules cost nothing. By default Plan B caps the AI service's own bill at $0.50 a run and $20 in total, and the final test ran under a $40 total. These caps limit the AI service's bill, not event money.",
            "**What comes next.** A walk-through on paper with community staff, then a pilot with one campus event series where Plan B suggests and the organizer acts. Real delivery tracking in place of the rehearsal look-up. Transit alerts as context only, never as proof of a person's arrival. A test with tricky messages, more sealed cases and more than one AI model.",
            "**How to try it.** The code and these documents are at github.com/nocdoggo/FA26-COLLIE. Section 13 has the commands. Everything except the AI approaches runs without an AI account.",
            "**Free and open source (GPL-3).** Anyone can read, run and change the code.",
            "**The ask.** Tell us where it goes wrong.",
        ],
    )


def close(doc) -> None:
    h1(doc, SECTIONS["close"])
    para(
        doc,
        "So, three ideas. Plan B checked the fact, so Jordan did not spend club money on a maybe. "
        "The AI picked only from changes that fit. And every change left a receipt, and money "
        "waited for a person's OK. Doors opened at 5 pm, the projector arrived at 5.24 pm, and the "
        "demonstrations started at 5.30 pm.",
    )
    para(doc, f"**\"{STUDENT}\"**")


# ----------------------------------------------------------------------------------------------
# Sources, acknowledgement, appendices
# ----------------------------------------------------------------------------------------------

REFERENCES = [
    "AI Agenda Builder & Event Scheduler (2026). Sessionboard. <<https://www.sessionboard.com/capabilities/ai-agenda>>",
    "Cvent Unveils More Than 70 Product Innovations at Cvent CONNECT 2026, Backed by $1 Billion Technology Investment. Cvent press release, July 14, 2026. <<https://www.cvent.com/en/press-release/cvent-unveils-more-70-product-innovations-cvent-connect-2026-backed-1-billion>>",
    "Bizzabo Reveals Its Agentic Operating System for Events. Bizzabo, October 12, 2026. <<https://www.bizzabo.com/blog/bizzabo-reveals-its-agentic-operating-system-for-events>>",
    "Introducing ChatGPT agent. OpenAI. <<https://openai.com/index/introducing-chatgpt-agent/>> The text was checked against the Internet Archive copy saved on October 10, 2026, at <<https://web.archive.org/web/20261010075929/openai.com/index/introducing-chatgpt-agent/>>",
    "Browse with Copilot. Microsoft Support. <<https://support.microsoft.com/en-US/microsoft-copilot/browse-with-copilot>>",
    "Manage your tasks & workflows in Gemini Apps. Gemini Apps Help, Google. <<https://support.google.com/gemini/answer/16596215>>",
    "Add approval steps to your agent's instructions. Zapier Help Center. <<https://help.zapier.com/hc/en-us/articles/41776074420493>>",
    "Eventbrite Reimagines Events With the Debut of AI-Powered Tools. Eventbrite blog, May 9, 2023. <<https://www.eventbrite.com/blog/eventbrite-ai-powered-tools/>>",
    "How to Use AI for Event Planning in 2026 with Real Examples. Whova blog, last updated August 20, 2026. <<https://whova.com/blog/ai-event-planning/>>",
    "Reclaim, AI Calendar for Work & Life. Reclaim.ai home page. <<https://reclaim.ai/>>",
    "What is GroupMe? Microsoft Support. <<https://support.microsoft.com/en-us/groupme/what-is-groupme>>",
    "Collaborative, AI-powered spreadsheets. Google Workspace. <<https://workspace.google.com/products/sheets/>>",
    "Create a free group poll. Doodle. <<https://doodle.com/en/product/polls/>>",
    "What is CampusGroups? Ready Education Help Center. <<https://helpcenter.readyeducation.com/what-is-campusgroups>>",
    "Student Activities. UMass Boston. <<https://www.umb.edu/campus-life/clubs-activities/student-activities/>>",
    "Engage, Student Engagement Platform from Encoura. Encoura. <<https://www.encoura.org/student-success/engage/>> The old Anthology Engage address redirects here, and Encoura's note on the acquisition is at encoura.org/anthology.",
    "Online Sign Up Sheets. SignUpGenius. <<https://www.signupgenius.com/sign-ups>>",
    "Volunteer Management Software for Nonprofits. VolunteerHub. <<https://volunteerhub.com/platform>>",
    "Campus Pantry Software for Colleges and Universities. PantrySoft. <<https://pantrysoft.com/customer/colleges-and-universities/>>",
    "Food Bank & Pantry Software Solutions. Link2Feed. <<https://www.link2feed.com/food-banks-pantries/>>",
    "Supplemental Nutrition Assistance Program, Estimated Eligibility and Receipt among Food Insecure College Students. GAO-24-107074, U.S. Government Accountability Office, published June 24, 2024, publicly released July 24, 2024. <<https://www.gao.gov/products/gao-24-107074>>",
    "Food Insecurity, Better Information Could Help Eligible College Students Access Federal Food Assistance Benefits. GAO-19-95, U.S. Government Accountability Office, published December 21, 2018, publicly released January 9, 2019. <<https://www.gao.gov/products/gao-19-95>>",
    "2023-2024 Student Basic Needs Survey Report. The Hope Center for Student Basic Needs, February 2025. <<https://hope.temple.edu/research/hope-center-basic-needs-survey/2023-2024-student-basic-needs-survey-report>>",
    "New U.S. Census Bureau and AmeriCorps Research Tracks Virtual Volunteering for First Time. U.S. Census Bureau, November 19, 2024. <<https://www.census.gov/library/stories/2024/11/civic-engagement-and-volunteerism.html>>",
    "Food insecurity reaches every U.S. community, with rural and southern counties facing the highest rates. Feeding America press release on Map the Meal Gap 2026, July 28, 2026. <<https://www.feedingamerica.org/about-us/press-room/Map-the-Meal-Gap-2026>>",
    "Food Insecurity Rose to 40% in 2025, According to The Greater Boston Food Bank and Mass General Brigham's Sixth Annual Statewide Food Access Report. The Greater Boston Food Bank press release, April 7, 2026. <<https://www.gbfb.org/news/press-releases/hunger-on-the-rise/>>",
    "Fast Facts, Back-to-school statistics (372). National Center for Education Statistics. <<https://nces.ed.gov/fastfacts/display.asp?id=372>>",
    "Student Groups & Activities. UMass Boston, checked October 26, 2026. <<https://www.umb.edu/campus-life/clubs-activities/>>",
    "Food Pantry. UMass Boston U-ACCESS. <<https://www.umb.edu/campus-life/current-students/u-access/food-pantry/>>",
    "τ-bench, A Benchmark for Tool-Agent-User Interaction in Real-World Domains. Shunyu Yao, Noah Shinn, Pedram Razavi and Karthik Narasimhan, arXiv 2406.12045, submitted June 17, 2024. <<https://arxiv.org/abs/2406.12045>>",
    "AI Risk Management Framework. NIST. <<https://www.nist.gov/itl/ai-risk-management-framework>>",
    "Artificial Intelligence Risk Management Framework (AI RMF 1.0), NIST AI 100-1. NIST, January 2023. Section 3.4 on page 15 and Appendix C on page 40. <<https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf>>",
    "LLM01, 2025 Prompt Injection. OWASP Gen AI Security Project. <<https://genai.owasp.org/llmrisk/llm01-prompt-injection/>>",
    "LLM06, 2025 Excessive Agency. OWASP Gen AI Security Project. <<https://genai.owasp.org/llmrisk/llm062025-excessive-agency/>>",
    "Practices for Governing Agentic AI Systems. Yonadav Shavit and colleagues, OpenAI. Sections 4.2 and 4.4. <<https://cdn.openai.com/papers/practices-for-governing-agentic-ai-systems.pdf>>",
    "Computer use tool. Claude Platform Docs, Anthropic. <<https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool>>",
    "Prompt injection is not SQL injection (it may be worse). Dave Chismon, National Cyber Security Centre blog, December 8, 2025. <<https://www.ncsc.gov.uk/blog-post/prompt-injection-is-not-sql-injection>>",
]
REFERENCE_GROUPS = [(1, "Direct competitors"), (11, "Indirect competitors and the status quo"), (21, "Target market and community need"), (30, "Responsible use of AI")]


def sources(doc) -> None:
    h1(doc, SECTIONS["sources"])
    h2(doc, "Acknowledgements")
    para(
        doc,
        "Thanks to the Paul English Applied AI Institute (PEAAII) at UMass Boston for organizing the "
        "hackathon. Plan B's AI coordinator runs on Claude Sonnet 5.5, a model made by Anthropic, "
        "reached through OpenRouter. The slides use the elegant beamer theme by Lars Spreng (CC BY "
        "4.0), and the poster uses the Gemini beamerposter theme by Anish Athalye (MIT License) with "
        "the UMass Boston color theme from the Overleaf poster template. The app's server uses the "
        "open-source libraries FastAPI, uvicorn and Pydantic, and this report is built with "
        "python-docx. Thanks do not imply that any of them endorses Plan B.",
    )
    h2(doc, "References")
    para(
        doc,
        "Each tool is described only by what its own page says, and we have not tested any of them. "
        "Addresses are printed without their \"https\" prefix, and a colon inside a source's title "
        "is printed as a comma.",
    )
    assert len(REFERENCES) == 37
    groups = dict(REFERENCE_GROUPS)
    for number, text in enumerate(REFERENCES, 1):
        if number in groups:
            para(doc, f"**{groups[number]}**").paragraph_format.keep_with_next = True
        p = para(doc, f"[{number}] {text}")
        p.paragraph_format.left_indent = Inches(0.35)
        p.paragraph_format.first_line_indent = Inches(-0.35)
        p.paragraph_format.space_after = Pt(3)


def appendices(doc) -> None:
    h1(doc, "Appendix A. Glossary")
    tab(
        doc,
        "Words used in this report, in plain terms.",
        ["Word", "What it means"],
        [
            ["A change", "means one way to alter the plan, such as swapping two activities or booking the backup"],
            ["Prompt injection", "means a message that tries to give the AI new orders. Plan B treats such text as data, not as instructions"],
            ["A receipt", "means a written record of a change, made by Plan B's server, saying what changed, when, which part made it and what it cost"],
            ["Held for free", "means kept aside for ten minutes at no cost and released on its own"],
            ["A look-up", "means one question to a source of facts, such as the delivery company's status"],
            ["Plan B's server", "means the part that keeps the plan and is the only part allowed to change it"],
            ["Spending allowance", "means how much the AI may spend without asking a person, $0 by default"],
            ["The rehearsal on a computer", "means a practice copy of an event, with a clock we can speed up, where nothing real is booked or bought"],
            ["A test case", "means a small made-up event day with messages at set times, checked by code at the end"],
            ["A sealed case", "means a case written and locked before the final test and never seen by the person who changed the code"],
            ["A practice case", "means a case used while building Plan B, not part of the final test"],
            ["A run", "means one approach playing one case once"],
            ["Met the expected outcome", "means the code's checks on the final state all passed"],
            ["An executed action that broke a rule", "means an accepted change that left the plan breaking a rule on roles, stock or resources. There were none"],
            ["A refused attempt", "means a request Plan B turned away, so nothing it asked for happened"],
            ["Our coordinator", "means my design, where the AI picks one step from a list Plan B built and checked"],
            ["The check-all variant", "means our coordinator with every relevant look-up made first"],
            ["The tool-calling model", "means the AI calling Plan B's tools itself"],
            ["The fixed rules", "means written rules with no AI and no cost"],
        ],
        [2.0, 4.5],
    )
    h1(doc, "Appendix B. File map")
    para(doc, "Paths in the repository github.com/nocdoggo/FA26-COLLIE.")
    code_block(
        doc,
        [
            "apps/plan_b/                              the app (Python package plan_b, web/, tests/, scripts/, docs/)",
            "apps/plan_b/plan_b/api/                   the server's sign-in and the board's connections",
            "apps/plan_b/plan_b/store/                 the plan, versions, holds, receipts, stock",
            "apps/plan_b/plan_b/tools/                 the checks before each change, and the receipts",
            "apps/plan_b/plan_b/domain/                the change lister and the campus and pantry rules",
            "apps/plan_b/plan_b/agent/                 the AI coordinator and its settings (config.py)",
            "apps/plan_b/plan_b/scenarios/             the rehearsal clock and the practice cases",
            "apps/plan_b/plan_b/evaluation/            sealing, running and scoring the tests",
            "apps/plan_b/plan_b/store/migrations/0004_consumable_stock.sql   the pantry's stock extension",
            "apps/plan_b/web/                          the board (React, TypeScript)",
            "apps/plan_b/docs/RUNTIME_CONTRACT.md      how the app behaves, sections 1 to 21",
            "apps/plan_b/docs/EVALUATION.md            the test commands",
            "apps/plan_b/docs/RELEASE_CHECKS.md        the release checks",
            "apps/plan_b/evaluation/results/           the committed test records",
            "PEEAI_plan/submission/                    the deck, the poster, this report and their sources",
        ],
    )
    h1(doc, "Appendix C. Evidence index")
    tab(
        doc,
        "Where each number in this report comes from.",
        ["Number or claim", "Source in the repository"],
        [
            ["59 of 60 runs met, every AI run met, the one miss, refusals, cost per approach, timing of the seal", "`apps/plan_b/evaluation/results/wave3b_fresh_20261025T2327Z/README.md` and its campus and pantry `report/metrics.json`"],
            ["$3.61 and 194 AI calls", "the same folder, `spend_extract.json`"],
            ["Earlier 12-case test, its counts and its four problems", "`PEEAI_plan/handoffs/wave_3/README.md` (development repository) and `apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/`"],
            ["The rerun that still misses two targeted cases", "`apps/plan_b/evaluation/results/wave3b_rerun_spent_20261025T2345Z/`"],
            ["951 tests passed", "`PEEAI_plan/handoffs/wave_3/VERIFICATION.md` (development repository)"],
            ["Jordan's evening, its times, 16 changes and 3 that fit", "`apps/plan_b/plan_b/scenarios/private/dev01.json` and `PEEAI_plan/examples/campus_showcase.evaluator.json`"],
            ["The recorded AI run of Jordan's case, 3 AI calls, $0.0366", "`apps/plan_b/data/recorded/wave_1/dev01_trace.json` and `PEEAI_plan/handoffs/wave_2/evidence/reports/live_dev01_run.json`"],
            ["The 5.45 pm practice case", "`apps/plan_b/plan_b/scenarios/private/dev02.json`"],
            ["The made-up pantry's numbers", "`apps/plan_b/plan_b/scenarios/private/pantry_dev02.json`"],
            ["Release checks, 11 of 12 passing", "`apps/plan_b/docs/RELEASE_CHECKS.md`"],
            ["AI cost caps of $0.50 a run and $20 in total, the key handling", "`apps/plan_b/plan_b/agent/config.py`"],
            ["Outside facts [1] to [37]", "`PEEAI_plan/submission/RESEARCH_BRIEF.md`"],
        ],
        [2.6, 3.9],
    )


def main() -> None:
    render_figures()
    doc = new_document(
        title=TITLE,
        author=AUTHOR,
        subject="PEAAII AI Applications Hackathon 2026, project documentation",
        keywords="Plan B, community events, AI coordinator, receipts",
    )
    for section in (
        title_block, abstract, one_page, seven_questions, problem, ideas, evening, works, people,
        tested, results, responsible, market, others, why, benefit, limits, how_to_run, demo_guide,
        anything_else, close, sources, appendices,
    ):
        section(doc)
    doc.save(OUT)
    neutral_app_properties(OUT)
    print(f"wrote {OUT.name}, {_figure_count} figures, {_table_count} tables")


if __name__ == "__main__":
    main()
