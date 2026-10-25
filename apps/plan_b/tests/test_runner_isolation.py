"""Public/private isolation, reset, deterministic replay and trace integrity."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plan_b.api.app import create_app
from plan_b.domain.timeutil import parse_ts
from plan_b.evaluation.export_trace import build_trace, verify_trace, write_trace
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import ScriptedActors, audit_view, tick_loop
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.episodes import create_episode
from plan_b.store.projection_db import build_snapshot
from plan_b.world.leakcheck import find_leaks
from plan_b.world.world import load_case

PKG = Path(__file__).resolve().parents[1] / "plan_b"
APP = PKG.parent

FORBIDDEN_FOR_POLICY_AND_PLANNER = (
    "plan_b.world",
    "plan_b.store",
    "plan_b.scenarios",
    "plan_b.tools",
    "plan_b.api",
    "plan_b.evaluation.scoring",
    "plan_b.evaluation.export_trace",
)
ISOLATED_MODULES = (
    "evaluation/policies/__init__.py",
    "evaluation/policies/parser.py",
    "evaluation/policies/rules.py",
    "evaluation/policies/pantry_rules.py",
    "evaluation/policies/base.py",
    "domain/candidates.py",
    "domain/constraints.py",
    "domain/objective.py",
    "domain/adapters/base.py",
    "domain/adapters/campus.py",
    "domain/adapters/campus_outcome.py",
    "domain/adapters/outcome.py",
    "domain/adapters/registry.py",
    "domain/adapters/pantry.py",
    "domain/projection.py",
    "domain/readiness.py",
    "domain/stock.py",
    "domain/timeutil.py",
    # The model-driven policies (Wave 2): everything under agent/ except the G-LLM gate, which
    # is a harness like the runner (it creates its own temporary episode through the store).
    "agent/__init__.py",
    "agent/config.py",
    "agent/interpret.py",
    "agent/attention.py",
    "agent/menu.py",
    "agent/orchestrator.py",
    "agent/provider.py",
    "agent/prompts/__init__.py",
    "agent/policies/__init__.py",
    "agent/policies/selective.py",
    "agent/policies/tool_use.py",
    "agent/policies/verify_all.py",
)
# Modules whose own job is file or network I/O (the provider's spend ledger, its lock file and
# its HTTP transport): the import rule and the private-path checks still apply; only the
# literal ``open(`` check does not.
FILE_IO_MODULES = frozenset({"agent/provider.py"})
# Harnesses outside the rule (they create their own episodes through the store).
HARNESS_MODULES = frozenset({"agent/gate.py"})


def _imports(path: Path, source: str | None = None) -> set[str]:
    """Every module a file names in an import: absolute and relative ones (resolved against its
    package), and each name a ``from`` import binds (``from plan_b import store`` names
    ``plan_b.store``)."""
    tree = ast.parse(path.read_text() if source is None else source)
    package = ["plan_b", *path.relative_to(PKG).parent.parts]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            parts = package[: len(package) - node.level + 1] if node.level else []
            base = ".".join([*parts, *([node.module] if node.module else [])])
            out.add(base)
            out.update(f"{base}.{a.name}" for a in node.names)
    return out


def test_the_import_rule_resolves_relative_and_from_imports() -> None:
    probe = PKG / "agent" / "policies" / "probe.py"  # never written: the source is given
    source = "from plan_b import store\nfrom ...scenarios import runner\nfrom .. import menu\n"
    imports = _imports(probe, source)
    assert {"plan_b.store", "plan_b.scenarios.runner", "plan_b.agent.menu"} <= imports


@pytest.mark.parametrize("module", ISOLATED_MODULES)
def test_policy_and_planner_cannot_reach_private_input(module: str) -> None:
    path = PKG / module
    imports = _imports(path)
    bad = [
        m
        for m in imports
        if any(m == f or m.startswith(f + ".") for f in FORBIDDEN_FOR_POLICY_AND_PLANNER)
    ]
    assert bad == [], f"{module} imports {bad}"
    text = path.read_text()
    assert "PrivateCase" not in text and "scenarios/private" not in text
    assert "import_module" not in text and "__import__" not in text
    assert module in FILE_IO_MODULES or "open(" not in text


def test_every_policy_module_is_covered_by_the_isolation_rule() -> None:
    covered = sorted(
        str(p.relative_to(PKG))
        for d in ("agent", "evaluation/policies")
        for p in (PKG / d).rglob("*.py")
        if "__pycache__" not in p.parts
    )
    missing = set(covered) - set(ISOLATED_MODULES) - HARNESS_MODULES
    assert missing == set(), sorted(missing)


def test_leak_checker_detects_planted_leaks() -> None:
    case = load_case("dev01")
    early = parse_ts("2026-11-05T16:41:00-05:00")
    assert find_leaks('{"x":"receipt_P17"}', case, [], early) == ["receipt_P17"]
    assert find_leaks('{"never_expose_to_agent":true}', case, [], early)
    assert find_leaks('{"ok":"projector"}', case, [], early) == []


def _run(db: Database, case_ref: str) -> tuple[str, PolicyHost]:
    with db.write() as conn:
        episode_id = create_episode(conn, case_ref=case_ref)
    host = PolicyHost(db)
    tick_loop(
        db,
        host,
        episode_id,
        minutes=None,
        run_policy=True,
        actors=ScriptedActors(db, episode_id, load_case(case_ref).actor_scripts),
    )
    return episode_id, host


@pytest.mark.parametrize("case_ref", ["dev01", "dev02", "dev04", "dev05", "dev06"])
def test_policy_inputs_and_planner_inputs_exclude_private_data(db: Database, case_ref: str) -> None:
    episode_id, host = _run(db, case_ref)
    client = host.client(episode_id)
    assert client.calls, "the policy made no calls"
    final = audit_view(db, episode_id)
    case = load_case(case_ref)
    for env in client.calls:
        leaks = find_leaks(env.model_dump_json(), case, final.observations, env.scenario_time)
        assert leaks == [], (env.tool, env.scenario_time, leaks)
    with db.read() as conn:
        snap = build_snapshot(conn, episode_id)
    assert find_leaks(snap.model_dump_json(), case, final.observations, snap.clock) == []


def test_trace_is_sanitized_intact_and_matches_the_run(db: Database, tmp_path: Path) -> None:
    episode_id, _ = _run(db, "dev01")
    trace = build_trace(db, episode_id, policy_id="rules/1.0.0")
    assert verify_trace(trace) == []
    text = json.dumps(trace)
    for secret_like in ("token", "join_code", "moderator_code", "dev01", "DEV01"):
        assert secret_like not in text, secret_like
    case = load_case("dev01")
    assert find_leaks(text, case, audit_view(db, episode_id).observations, None) == []
    fresh = audit_view(db, episode_id).model_dump(mode="json")
    assert trace["final_state"] == fresh
    assert trace["frames"][-1]["state"]["revision"] == fresh["revision"]
    tampered = json.loads(json.dumps(trace))
    tampered["frames"][3]["summary"] = "edited"
    assert verify_trace(tampered)


def test_replay_endpoints_perform_no_writes(tmp_path: Path) -> None:
    var = tmp_path / "var"
    app = create_app(
        var / "plan_b.sqlite3", var_dir=var, moderator_code="c", web_dist=tmp_path / "none"
    )
    db: Database = app.state.db
    episode_id, _ = _run(db, "dev01")
    write_trace(build_trace(db, episode_id), var / "traces" / "dev01_trace.json")

    def counts() -> dict[str, int]:
        with db.read() as conn:
            tables = [
                r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            return {
                t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in tables
            }

    before = counts()
    c = TestClient(app)
    assert c.get("/api/replays").json() == [{"name": "dev01_trace.json"}]
    body = c.get("/api/replays/dev01_trace.json").json()
    assert body["mode_label"] == "Recorded replay" and verify_trace(body) == []
    assert counts() == before


def test_runs_are_deterministic(tmp_path: Path) -> None:
    def signature(db_path: Path) -> list[object]:
        db = Database(db_path)
        episode_id, _ = _run(db, "dev02")
        with db.read() as conn:
            calls = [
                (t.tool, t.actor_id, t.envelope_status, t.error_code, t.requested_at)
                for t in repo.tool_calls(conn, episode_id)
            ]
            decisions = [(d.kind, d.summary, d.at) for d in repo.decisions(conn, episode_id)]
            receipts = [
                (
                    r.tool,
                    r.status,
                    r.error_code,
                    r.revision_before,
                    r.revision_after,
                    r.committed_delta_cents,
                )
                for r in repo.receipts(conn, episode_id)
            ]
            transitions = [
                (t.revision, t.at, t.cause_kind, t.summary)
                for t in repo.transitions(conn, episode_id)
            ]
        return [calls, decisions, receipts, transitions]

    assert signature(tmp_path / "a.sqlite3") == signature(tmp_path / "b.sqlite3")


def test_reset_clears_policy_memory_and_episode_records(db: Database) -> None:
    episode_id, host = _run(db, "dev02")
    first_policy = host.policy(episode_id)
    with db.write() as conn:
        new_id = create_episode(conn, case_ref="dev02")
        assert repo.get_episode(conn, episode_id).status == "closed"
        assert repo.receipts(conn, new_id) == () and repo.decisions(conn, new_id) == ()
        assert repo.holds(conn, new_id) == () and repo.latest_evaluation(conn, new_id) is None
        assert len(repo.observations(conn, new_id)) == 1  # only the fixture notice
        assert repo.receipts(conn, episode_id)  # the closed episode keeps its audit trail
    assert host.policy(new_id) is not first_policy


def test_browser_bundle_carries_no_private_data() -> None:
    dist = APP / "web" / "dist"
    if not dist.is_dir():
        pytest.skip(
            "web/dist not built; run `npm run build` in web/ (checked in the browser walkthrough)"
        )
    blob = "\n".join(p.read_text(errors="ignore") for p in dist.rglob("*") if p.is_file())
    for ref in ("dev01", "dev02", "dev04", "dev05", "dev06"):
        case = load_case(ref)
        assert find_leaks(blob, case, [], None) == []
    for marker in ("Bearer ey", "moderator_code.txt", "test-moderator-code"):
        assert marker not in blob
