"""Command line: serve the sandbox, run development cases, verify traces."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from plan_b.api.app import create_app, load_moderator_code

    var = Path(args.var)
    app = create_app(var / "plan_b.sqlite3", var_dir=var, replay_dirs=args.replay_dir)
    load_moderator_code(var)
    where = (
        "the PLAN_B_MODERATOR_CODE environment variable"
        if os.environ.get("PLAN_B_MODERATOR_CODE")
        else f"{var / 'moderator_code.txt'} (mode 0600)"
    )
    print(f"Plan B sandbox on http://{args.host}:{args.port}; moderator code is in {where}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _run_case(args: argparse.Namespace) -> int:
    from plan_b.evaluation.export_trace import build_trace, write_trace
    from plan_b.evaluation.scoring import public_summary
    from plan_b.scenarios.policy_host import EpisodeCaps
    from plan_b.scenarios.runner import run_case
    from plan_b.store.database import Database
    from plan_b.world.world import available_cases

    try:
        caps = EpisodeCaps(
            max_tool_calls=args.max_episode_tool_calls,
            max_model_calls=args.max_episode_model_calls,
        )
    except ValueError as exc:
        print(f"invalid caps: {exc}")
        return 2
    live_config = None
    if args.policy == "live":
        from plan_b.agent.config import ModelConfigError, load_model_config

        try:
            live_config = load_model_config()  # server-side; the key itself is not read here
        except ModelConfigError as exc:
            print(f"the live policy is not configured: {exc}")
            return 2
    cases = available_cases() if args.case == "all" else [args.case]
    out = Path(args.out) if args.out else None
    db = Database(args.db)
    ok = True
    for case_ref in cases:
        result = run_case(db, case_ref, policy=args.policy, caps=caps, live_config=live_config)
        report = result.report
        line = (
            f"{case_ref}: goal_complete={report.goal_complete} "
            f"infeasibility_reported={report.infeasibility_reported} "
            f"applied_plans={report.applied_plans} committed={report.committed_cents} "
            f"violations={len(report.violations)} matches_expectation={report.matches_expectation}"
        )
        print(line)
        ok = ok and bool(report.matches_expectation)
        if out is not None:
            trace = build_trace(db, result.episode_id, policy_id=report.policy_id)
            write_trace(trace, out / "traces" / f"{case_ref}_trace.json")
            public = out / "reports" / f"{case_ref}_outcome.public.json"
            public.parent.mkdir(parents=True, exist_ok=True)
            public.write_text(json.dumps(public_summary(report), indent=2, sort_keys=True) + "\n")
            private = out / "private" / f"{case_ref}_outcome.runner.json"
            private.parent.mkdir(parents=True, exist_ok=True)
            private.write_text(report.model_dump_json(indent=2) + "\n")
    return 0 if ok else 1


def _demo_rejections(args: argparse.Namespace) -> int:
    from plan_b.evaluation.export_trace import build_trace, write_trace
    from plan_b.evaluation.scoring import public_summary, score_episode
    from plan_b.scenarios.demos import rejected_actions_run
    from plan_b.scenarios.runner import audit_view, episode_history
    from plan_b.store.database import Database

    db = Database(args.db)
    episode_id, log = rejected_actions_run(db)
    ok = True
    for row in log:
        actual = row["receipt_status"] or row["envelope_status"]
        if row["code"]:
            actual += f" {row['code']}"
        ok = ok and row["expected"].split(" (")[0] == actual
        print(f"{row['step']}: expected {row['expected']}; got {actual}")
    report = score_episode(audit_view(db, episode_id), episode_history(db, episode_id), None)
    print(
        f"final: goal_complete={report.goal_complete} committed={report.committed_cents}"
        f" rejected_receipts={report.rejected_receipts}"
        f" attempts_without_receipt={report.rejected_attempts_without_receipt}"
        f" violations={len(report.violations)}"
    )
    if args.out:
        out = Path(args.out)
        write_trace(build_trace(db, episode_id), out / "traces" / "rejected_actions_trace.json")
        path = out / "reports" / "rejected_actions_steps.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"steps": log, "outcome": public_summary(report)}, indent=2, sort_keys=True)
            + "\n"
        )
    return 0 if ok and not report.violations else 1


def _verify(args: argparse.Namespace) -> int:
    from plan_b.evaluation.export_trace import verify_trace_bytes

    # The exact bytes, as the browser replay checks them: decoding is part of the verdict.
    try:
        data = Path(args.trace).read_bytes()
    except OSError as exc:
        print(f"cannot read {args.trace}: {exc.strerror or exc}")
        return 1
    problems = verify_trace_bytes(data)
    print("intact" if not problems else "; ".join(problems))
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    from plan_b.scenarios.policy_host import DEVELOPMENT_CAPS

    parser = argparse.ArgumentParser(prog="plan-b")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the API and browser app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--var", default=str(APP_DIR / "var"))
    serve.add_argument("--replay-dir", action="append", default=[])
    serve.set_defaults(func=_serve)
    run = sub.add_parser("run-case", help="run a development case to the hard end")
    run.add_argument("case", help="case ref (dev01, dev02, ...) or 'all'")
    run.add_argument("--db", default=str(APP_DIR / "var" / "runs.sqlite3"))
    run.add_argument("--out", default=None, help="write traces and reports under this directory")
    run.add_argument(
        "--policy",
        choices=("rules", "live"),
        default="rules",
        help="rules: the profile's deterministic baseline (default); live: the live agent"
        " (paid model calls; needs the model endpoint configuration)",
    )
    run.add_argument(
        "--max-episode-tool-calls",
        type=int,
        default=DEVELOPMENT_CAPS.max_tool_calls,
        help="per-episode tool-call cap for every policy (development value: %(default)s)",
    )
    run.add_argument(
        "--max-episode-model-calls",
        type=int,
        default=DEVELOPMENT_CAPS.max_model_calls,
        help="per-episode model-call cap of the live policy (development value: %(default)s)",
    )
    run.set_defaults(func=_run_case)
    demo = sub.add_parser("demo-rejections", help="executed run exercising rejected actions")
    demo.add_argument("--db", default=str(APP_DIR / "var" / "runs.sqlite3"))
    demo.add_argument("--out", default=None)
    demo.set_defaults(func=_demo_rejections)
    verify = sub.add_parser("verify-trace", help="check a trace's integrity hashes")
    verify.add_argument("trace")
    verify.set_defaults(func=_verify)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
