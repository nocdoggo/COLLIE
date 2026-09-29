"""Stage A readout: the model ladder on the registered 120 pilot episodes (PLAN.md stage A).

For every rung with a complete run under ``out/``: first-proposal perception and parse
validity, the net outcomes of acting at once (arm 8) and of the registered gate (arm 10)
against arm 1, activation on the 12 false-alert nulls, provider cost and latency, all from the
real-content pilot's evaluator; plus certify-then-hedge against arm 1 from the stage B
development replay (``dev.py``, arm 10's cached answers, no calls), labelled as development.

Usage::

    uv run python -m analysis.commitment.ladder [--dev out/dev/ladder_dev.json]
"""

from __future__ import annotations

import argparse
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from analysis.commitment.endpoints import LADDER
from analysis.real_content_pilot.evaluate import evaluate


def whole(x: float) -> str:
    """Signed whole number with thousands separators, rounded half away from zero."""
    return format(Decimal(repr(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP), "+,f")


def cents(x: float) -> str:
    """Amount to the cent, rounded half away from zero."""
    return format(Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "commitment" / "out"
TOP = {"gemini-3.8-flash": "gemini-bank", "grok-4.20": "grok-bank"}
DEVELOPER = {
    "gemini": "Google",
    "grok": "xAI",
    "step": "StepFun",
    "llama": "Meta",
    "qwen": "Alibaba",
    "gemma": "Google",
    "deepseek": "DeepSeek",
    "gpt": "OpenAI",
}


def run_name(rung: str) -> str:
    return TOP.get(rung, f"ladder-{rung}")


def complete(rung: str) -> bool:
    path = OUT / run_name(rung) / "run_manifest.json"
    if not path.is_file():
        return False
    manifest = json.loads(path.read_text())
    return not manifest.get("partial") and manifest.get("episodes") == 120


def developer(rung: str) -> str:
    for prefix, name in DEVELOPER.items():
        if rung.startswith(prefix) or rung.startswith(f"{prefix}-"):
            return name
    return LADDER[rung].provider


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.ladder")
    ap.add_argument("--dev", type=Path, default=OUT / "dev" / "ladder_dev.json")
    ap.add_argument("--out", type=Path, default=OUT / "ladder.json")
    args = ap.parse_args(argv)
    rungs = [r for r in LADDER if complete(r)]
    missing = [r for r in LADDER if r not in rungs]
    ev = evaluate([run_name(r) for r in rungs], reference="scripted-bank", root=OUT)
    dev = {}
    if args.dev.is_file():
        for s in json.loads(args.dev.read_text())["summaries"]:
            if s["variant"] in ("cth", "cth_uniform"):
                dev[(s["bank"], s["variant"])] = s["vs_arm1|net"]
    rows = []
    for rung in rungs:
        name = run_name(rung)
        r = ev["runs"][name]
        q1, q4, q5, q6 = r["q1"]["shocked"], r["q4"]["overall"], r["q5"], r["q6"]["false_alert"]
        parse = q5["parse"]
        rows.append(
            {
                "rung": rung,
                "developer": developer(rung),
                "released": LADDER[rung].released,
                "tier": LADDER[rung].tier,
                "family_right": q1["family_ok"]["k"],
                "shocked": q1["family_ok"]["n"],
                "abstain_first": q1["outcomes"].get("abstain", 0),
                "parse_valid": parse.get("valid_first_attempt", parse.get("parsed")),
                "parse_attempts": parse.get("attempts"),
                "arm8_arm1_net": q4["arm8-arm1|net"],
                "arm10_arm1_net": q4["arm10-arm1|net"],
                "false_alert_active_arm8": fa(q6, "arm8"),
                "false_alert_active_arm10": fa(q6, "arm10"),
                "cth_arm1_net_dev": dev.get((name, "cth")),
                "usd": q5.get("provider", {}).get("usd"),
                "latency_p50_ms": q5.get("provider", {}).get("latency_ms", {}).get("p50"),
            }
        )
    content_free = next((v for (b, var), v in dev.items() if var == "cth_uniform"), None)
    result = {
        "analysis_class": "exploratory",
        "registered_in": "analysis/commitment/PLAN.md, stage A (with A1-A3)",
        "rungs": rows,
        "missing_or_partial": missing,
        "cth_uniform_arm1_net_dev": content_free,
    }
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    md = [
        "| model | developer | released | size | right family / 96 | first-proposal abstain | "
        "at once - arm 1 (net) | gate - arm 1 (net) | hedge - arm 1 (net, dev) | "
        "false-alert nulls acted on (at once / gate) | cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for x in sorted(rows, key=lambda x: (x["developer"], x["released"])):
        hedge = x["cth_arm1_net_dev"]
        md.append(
            f"| {x['rung']} | {x['developer']} | {x['released']} | {x['tier']} | "
            f"{x['family_right']}/{x['shocked']} | {x['abstain_first']} | "
            f"{whole(x['arm8_arm1_net']['mean'])} | {whole(x['arm10_arm1_net']['mean'])} | "
            f"{'n/a' if hedge is None else whole(hedge['mean'])} | "
            f"{x['false_alert_active_arm8']}/12, {x['false_alert_active_arm10']}/12 | "
            f"${cents(x['usd'] or 0)} |"
        )
    args.out.with_suffix(".md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    if missing:
        print("missing or partial:", ", ".join(missing))
    return 0


def fa(q6: dict, arm: str) -> int:
    return int(q6[arm]["any_active"]["k"])


if __name__ == "__main__":
    raise SystemExit(main())
