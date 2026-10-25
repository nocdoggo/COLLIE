"""Command line: serve the sandbox, run development cases, verify traces, and the Wave 3
evaluation (``plan-b eval``: freeze, lock-heldout, verify-freeze, run, report)."""

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
    if args.policy != "rules":
        from plan_b.agent.config import ModelConfigError, load_model_config

        try:
            live_config = load_model_config()  # server-side; the key itself is not read here
        except ModelConfigError as exc:
            print(f"the {args.policy} policy is not configured: {exc}")
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


def _ints(values: list[str]) -> list[int]:
    return [int(v) for item in values for v in item.split(",") if v.strip()]


def _eval_freeze(args: argparse.Namespace) -> int:
    from plan_b.evaluation import manifest

    data = manifest.write_freeze(
        Path(args.out), seeds=_ints(args.seeds), order_seed=args.order_seed
    )
    print(
        f"wrote {args.out}: {len(data['files'])} measured files, files_sha256"
        f" {data['files_sha256']}, seeds {data['seeds']}, order seed {data['order_seed']},"
        f" model {data['model']['model_id']} via {data['model']['provider']}"
    )
    return 0


def _eval_lock_heldout(args: argparse.Namespace) -> int:
    from plan_b.evaluation import manifest
    from plan_b.evaluation.run import RunRefused

    try:
        data = manifest.write_heldout(Path(args.out), freeze_path=Path(args.freeze))
    except (manifest.FreezeError, RunRefused) as exc:
        print(f"cannot lock the held-out suites: {exc}")
        return 1
    counts = ", ".join(f"{suite} {len(cases)}" for suite, cases in data["suites"].items())
    print(
        f"wrote {args.out}: {counts} cases; {len(data['files'])} files; locked {data['locked_at']}"
    )
    return 0


def _eval_verify_freeze(args: argparse.Namespace) -> int:
    from plan_b.evaluation import manifest

    checks = [manifest.verify_freeze(Path(args.freeze))]
    heldout = Path(args.heldout)
    if heldout.is_file() or args.require_heldout:
        checks.append(manifest.verify_heldout(heldout, freeze_path=Path(args.freeze)))
    ok = True
    for check in checks:
        if check.ok:
            print(f"{check.manifest}: verified ({check.detail})")
            continue
        ok = False
        print(f"{check.manifest}: DRIFT ({len(check.drift)} problems)")
        for line in check.drift:
            print(f"  {line}")
    if not ok:
        print("FREEZE VERIFICATION FAILED: frozen files or settings differ from the manifest")
    return 0 if ok else 1


def _eval_run(args: argparse.Namespace) -> int:
    from plan_b.evaluation import manifest
    from plan_b.evaluation.run import RunRefused, run_evaluation

    try:
        summary = run_evaluation(
            suite=args.suite,
            cases=[c for item in args.cases for c in item.split(",") if c.strip()]
            if args.cases
            else None,
            policies=[p for item in args.policies for p in item.split(",")],
            seeds=_ints(args.seeds) if args.seeds else list(manifest.DEFAULT_SEEDS),
            out=Path(args.out),
            jobs=args.jobs,
            order_seed=args.order_seed,
            timeout_s=args.timeout,
            policy_factory=args.policy_factory,
            freeze_path=Path(args.freeze),
            heldout_path=Path(args.heldout),
        )
    except RunRefused as exc:
        print(f"run refused: {exc}")
        return 2
    print(
        f"{summary.planned} planned, {summary.skipped} already finished, {summary.ran} run:"
        f" {summary.statuses}"
    )
    return 0


def _eval_report(args: argparse.Namespace) -> int:
    from plan_b.evaluation.report import write_report

    paths = write_report(Path(args.results), Path(args.out) if args.out else None)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


def _add_eval(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from plan_b.evaluation import manifest

    ev = sub.add_parser("eval", help="the Wave 3 evaluation: freeze, run, report")
    group = ev.add_subparsers(dest="eval_command", required=True)
    freeze = group.add_parser("freeze", help="write the freeze manifest of the measured code")
    freeze.add_argument("--out", default=str(manifest.FREEZE_PATH))
    freeze.add_argument("--seeds", nargs="+", default=[str(s) for s in manifest.DEFAULT_SEEDS])
    freeze.add_argument("--order-seed", type=int, default=manifest.DEFAULT_ORDER_SEED)
    freeze.set_defaults(func=_eval_freeze)
    lock = group.add_parser("lock-heldout", help="write the held-out suites' manifest")
    lock.add_argument("--out", default=str(manifest.HELDOUT_PATH))
    lock.add_argument("--freeze", default=str(manifest.FREEZE_PATH))
    lock.set_defaults(func=_eval_lock_heldout)
    verify = group.add_parser("verify-freeze", help="recompute the manifests; fail on any drift")
    verify.add_argument("--freeze", default=str(manifest.FREEZE_PATH))
    verify.add_argument("--heldout", default=str(manifest.HELDOUT_PATH))
    verify.add_argument("--require-heldout", action="store_true")
    verify.set_defaults(func=_eval_verify_freeze)
    run = group.add_parser("run", help="run a suite's episodes (P1-P3 make paid model calls)")
    run.add_argument("--suite", required=True, choices=("campus", "pantry"))
    run.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="held-out case ids or refs (default: every held-out case of the suite), or"
        " development case refs for a dry run",
    )
    run.add_argument("--policies", nargs="+", default=["P0,P1,P2,P3"])
    run.add_argument("--seeds", nargs="+", default=None, help="default: the preregistered seeds")
    run.add_argument("--jobs", type=int, default=1)
    run.add_argument("--out", required=True, help="results directory (rerun it to resume)")
    run.add_argument("--order-seed", type=int, default=None)
    run.add_argument("--timeout", type=float, default=None, help="episode wall-time limit (s)")
    run.add_argument(
        "--policy-factory",
        default=None,
        metavar="MODULE:CALLABLE",
        help="dry runs on development cases only: build P1-P3 around a scripted provider",
    )
    run.add_argument("--freeze", default=str(manifest.FREEZE_PATH))
    run.add_argument("--heldout", default=str(manifest.HELDOUT_PATH))
    run.set_defaults(func=_eval_run)
    report = group.add_parser("report", help="write the results tables and figure")
    report.add_argument("--results", required=True)
    report.add_argument("--out", default=None, help="default: <results>/report")
    report.set_defaults(func=_eval_report)


def main(argv: list[str] | None = None) -> int:
    from plan_b.scenarios.policy_host import DEVELOPMENT_CAPS, POLICY_CHOICES

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
        choices=POLICY_CHOICES,
        default="rules",
        help="rules: the profile's deterministic baseline, P0 (default); tool-use: the"
        " tool-using model baseline, P1; live or selective: the live agent, P2; verify-all: the"
        " verify-all ablation, P3 (the model-driven ones make paid model calls and need the"
        " model endpoint configuration)",
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
        help="per-episode model-call cap of the model-driven policies (development value:"
        " %(default)s)",
    )
    run.set_defaults(func=_run_case)
    demo = sub.add_parser("demo-rejections", help="executed run exercising rejected actions")
    demo.add_argument("--db", default=str(APP_DIR / "var" / "runs.sqlite3"))
    demo.add_argument("--out", default=None)
    demo.set_defaults(func=_demo_rejections)
    verify = sub.add_parser("verify-trace", help="check a trace's integrity hashes")
    verify.add_argument("trace")
    verify.set_defaults(func=_verify)
    _add_eval(sub)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
