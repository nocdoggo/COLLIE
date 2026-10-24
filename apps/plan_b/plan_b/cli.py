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
    from plan_b.scenarios.runner import run_case
    from plan_b.store.database import Database
    from plan_b.world.world import available_cases

    cases = available_cases() if args.case == "all" else [args.case]
    out = Path(args.out) if args.out else None
    db = Database(args.db)
    ok = True
    for case_ref in cases:
        result = run_case(db, case_ref)
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
    from plan_b.evaluation.export_trace import verify_trace

    problems = verify_trace(json.loads(Path(args.trace).read_text()))
    print("intact" if not problems else "; ".join(problems))
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan-b")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the API and browser app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--var", default=str(APP_DIR / "var"))
    serve.add_argument("--replay-dir", action="append", default=[])
    serve.set_defaults(func=_serve)
    run = sub.add_parser("run-case", help="run a development case with the deterministic policy")
    run.add_argument("case", help="case ref (dev01, dev02, ...) or 'all'")
    run.add_argument("--db", default=str(APP_DIR / "var" / "runs.sqlite3"))
    run.add_argument("--out", default=None, help="write traces and reports under this directory")
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
