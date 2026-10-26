"""Compact digest of every non-success episode of a results directory (for FAILURES.md)."""

import collections
import gzip
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
m = json.loads((out / "report" / "metrics.json").read_text())
only = set(sys.argv[2:])
for e in sorted(m["episodes"], key=lambda e: (e["case_id"], e["policy"], e.get("seed") or 0)):
    if e["success"] and not only:
        continue
    if only and e["key"] not in only:
        continue
    key = e["key"]
    rec = json.loads((out / "episodes" / key / "record.json").read_text())
    priv = json.loads((out / "runner_private" / f"{key}.runner.json").read_text())
    t = json.loads(gzip.decompress((out / "episodes" / key / "trace.json.gz").read_bytes()))
    mod = rec.get("model") or {}
    print("=" * 100)
    print(
        f"{key}  {e['case_id']} class={e['outcome_class']} status={e['status']}"
        f" policy={e['policy']} seed={e.get('seed')}"
    )
    print(
        f"  failure_reasons={e.get('failure_reasons')} caps={e.get('caps_reached')}"
        f" decided_by={e.get('decided_by')}"
        f" infeas_reported={e.get('infeasibility_reported')} goal={e.get('goal_complete')}"
    )
    print(
        f"  model outcomes={mod.get('outcomes')} calls={mod.get('calls')}"
        f" failed={mod.get('failed')} usd={mod.get('cost_usd')}"
    )
    failed = [(p["predicate_id"], p["detail"]) for p in priv["predicates"] if not p["passed"]]
    print(f"  failed predicates: {failed}")
    ex = [
        (x["source_record_id"], x["label"], x.get("mismatched")) for x in e.get("extraction") or []
    ]
    print(f"  extraction: {ex}")
    errs = collections.Counter((x.get("failure") or x.get("kind")) for x in rec.get("errors") or [])
    print(f"  record errors: {dict(errs)}  invalid_attempts={e['invalid_attempts']}")
    if e.get("pantry"):
        p = e["pantry"]
        print(f"  pantry: {json.dumps({k: p[k] for k in p if k not in ('pools',)})[:900]}")
    if (e.get("unnecessary_committed_changes") or {}).get("committed_changes"):
        print(f"  unnecessary: {e['unnecessary_committed_changes']}")
    print(f"  churn={e.get('plan_churn')} recovery={e.get('recovery')}")
    for d in t["decisions"]:
        det = d["details"]
        extra = ""
        if det.get("failure"):
            extra += f" failure={det['failure']}"
        if det.get("chosen_by"):
            extra += f" by={det['chosen_by']}"
        print(
            f"   {d['decision_id']} {d['at'][11:16]} {d['kind']:<11}{extra} | {d['summary'][:260]}"
        )
    rej = [
        (c["seq"], c["requested_at"][11:16], c["tool"], c["error_code"])
        for c in t["tool_calls"]
        if c.get("envelope_status") != "succeeded"
    ]
    if rej:
        print(f"  rejected tool calls: {rej}")
    rc = [
        (r["executed_at"][11:16], r["actor_id"], r["tool"], r["status"], r["summary"][:120])
        for r in t["receipts"]
        if r["actor_role"] != "participant" or r["tool"] not in ("check_in",)
    ]
    print(f"  receipts: {rc}")
