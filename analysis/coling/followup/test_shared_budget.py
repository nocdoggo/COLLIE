"""Invented inputs only; these tests never use a provider, runner or real ledger."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import threading

import pytest

from analysis.coling.followup import shared_budget as sb


USD = sb.MICRODOLLARS


def evidence(name, actor="auditor"):
    return sb.Evidence(f"synthetic:evidence:{name}", f"synthetic:actor:{actor}")


def item(name):
    return f"synthetic:item:{name}"


def request(name):
    return f"synthetic:request:{name}"


def lane(name):
    return f"synthetic:lane:{name}"


def default_lanes():
    return (
        sb.Lane(lane("llama-a"), sb.Target.LLAMA, sb.Role.ORIGINAL),
        sb.Lane(lane("llama-b"), sb.Target.LLAMA, sb.Role.ORIGINAL),
        sb.Lane(lane("deepseek"), sb.Target.DEEPSEEK, sb.Role.ORIGINAL),
        sb.Lane(lane("oss-20b"), sb.Target.OSS_20B, sb.Role.ORIGINAL),
        sb.Lane(lane("oss-20b-judge"), sb.Target.OSS_20B, sb.Role.JUDGE),
        sb.Lane(lane("oss-120b"), sb.Target.OSS_120B, sb.Role.JUDGE),
        sb.Lane(lane("judge-a"), sb.Target.JUDGE_A, sb.Role.JUDGE),
        sb.Lane(lane("judge-b"), sb.Target.JUDGE_B, sb.Role.JUDGE),
        sb.Lane(lane("admin"), sb.Target.ADMIN, sb.Role.ADMIN),
    )


def snapshot(*, preflight=0, allowance=3, settled=(), liabilities=(), lanes=None):
    billing = None if preflight is None else evidence("preflight-bill", "billing")
    return sb.HistoricalSnapshot(
        snapshot_id="synthetic:snapshot:invented",
        prepared_by="synthetic:actor:preparer",
        attestation=evidence("snapshot-attestation", "reviewer"),
        attests_complete=True,
        attests_disjoint=True,
        global_retry_allowance=allowance,
        preflight=sb.Preflight(item("preflight"), evidence("preflight-sent", "observer"), preflight, billing),
        lanes=default_lanes() if lanes is None else lanes,
        settled=tuple(settled),
        liabilities=tuple(liabilities),
    )


def historical(name, target, amount, *, programme=False, request_name=None, lane_name=None, retry=False):
    return sb.HistoricalCharge(
        item(name), amount, target, programme, evidence(f"historical-{name}", "billing"),
        request(request_name) if request_name is not None else None,
        lane(lane_name) if lane_name is not None else None,
        retry,
    )


def liability(name, target, upper, *, programme=False, request_name=None, lane_name=None, retry=False):
    return sb.ExternalLiability(
        item(name), target, programme, evidence(f"observed-{name}", "observer"), upper,
        None if upper is None else evidence(f"external-bound-{name}", "bounds"),
        request(request_name) if request_name is not None else None,
        lane(lane_name) if lane_name is not None else None,
        retry,
    )


def connect(path=":memory:"):
    return sqlite3.connect(str(path), isolation_level=None, timeout=10)


@pytest.fixture
def make_budget():
    connections = []

    def make(snap=None):
        connection = connect()
        connections.append(connection)
        return sb.SyntheticBudget(connection, snap if snap is not None else snapshot())

    yield make
    for connection in connections:
        connection.close()


@pytest.fixture
def scratch():
    # A newly created, exclusively synthetic directory, removed after this test.
    with tempfile.TemporaryDirectory(prefix="synthetic-budget-test-", dir="/tmp/opencode") as path:
        yield Path(path)


def reserve(coordinator, name, lane_name, amount, *, request_name=None, retry_of=None, bound_evidence=None):
    return coordinator.reserve(
        attempt_id=item(name),
        request_id=request(request_name or name),
        lane_id=lane(lane_name),
        worst_case=sb.WorstCase(amount, bound_evidence or evidence(f"bound-{name}", "bounds")),
        retry_of=item(retry_of) if retry_of is not None else None,
    )


def final_bill(coordinator, name, amount, *, evidence_name=None, actor="billing"):
    return coordinator.record_final_bill(
        item(name), amount, evidence(evidence_name or f"bill-{name}", actor)
    )


def nonreturn(coordinator, name, *, evidence_name=None, actor="termination"):
    coordinator.record_nonreturn(item(name), evidence(evidence_name or f"nonreturn-{name}", actor))


def test_fixed_caps_and_synthetic_scope():
    assert sb.SYNTHETIC_ONLY is True
    assert sb.STUDY_CAP == 200 * USD
    assert sb.PROGRAMME_CAP == 10 * USD
    assert sb.HTTP_ATTEMPT_CAP == 1_400
    assert sb.SYNTHETIC_GLOBAL_RETRY_CEILING == 3
    assert dict(sb.MODEL_CAPS) == {
        sb.Target.LLAMA: 5 * USD,
        sb.Target.DEEPSEEK: 12 * USD,
        sb.Target.OSS_20B: 6 * USD,
    }
    assert sb.Target.OSS_120B not in sb.MODEL_CAPS
    with pytest.raises(TypeError):
        sb.MODEL_CAPS[sb.Target.OSS_20B] = 99 * USD


@pytest.mark.parametrize(
    "target,lane_name,old_amount,new_amount",
    [
        (sb.Target.LLAMA, "llama-a", 0, 5 * USD),
        (sb.Target.DEEPSEEK, "deepseek", 3 * USD, 9 * USD),
        (sb.Target.OSS_20B, "oss-20b", 0, 6 * USD),
    ],
)
def test_exact_original_model_cap_and_one_microdollar_over(
    make_budget, target, lane_name, old_amount, new_amount
):
    old = (historical("old-model", target, old_amount),) if old_amount else ()
    coordinator = make_budget(snapshot(settled=old))
    reserve(coordinator, "on-cap", lane_name, new_amount)
    state = coordinator.status()
    assert state.known_subtotal.for_target(target) == sb.MODEL_CAPS[target]
    assert state.attempt_holds.for_target(target) == new_amount
    with pytest.raises(sb.Blocked, match="original model cap"):
        reserve(coordinator, "over-cap", lane_name, 1)
    # At the exact cap, a separately evidenced zero-cost attempt is permitted.
    reserve(coordinator, "zero-at-cap", lane_name, 0)
    assert coordinator.status().attempts_used == 3


def test_study_and_programme_caps_are_separate_and_include_admin(make_budget):
    old = historical("other-study", sb.Target.OTHER_STUDY, 197 * USD)
    study = make_budget(snapshot(settled=(old,)))
    reserve(study, "judge-study", "judge-a", 3 * USD)
    assert study.status().known_subtotal.study == 200 * USD
    assert study.status().known_subtotal.programme == 3 * USD
    with pytest.raises(sb.Blocked, match="study cap"):
        reserve(study, "study-over", "judge-b", 1)

    programme = make_budget(snapshot(preflight=USD))
    reserve(programme, "judge-programme", "judge-a", 9 * USD)
    state = programme.status()
    assert state.initial_settled.programme == USD
    assert state.known_subtotal.programme == 10 * USD
    assert state.attempts_used == 2
    with pytest.raises(sb.Blocked, match="programme cap"):
        reserve(programme, "programme-over", "judge-b", 1)


def test_multiple_lanes_share_original_and_study_budgets(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "llama-one", "llama-a", 3 * USD)
    reserve(coordinator, "llama-two", "llama-b", 2 * USD)
    assert coordinator.status().known_subtotal.for_target(sb.Target.LLAMA) == 5 * USD
    with pytest.raises(sb.Blocked, match="original model cap"):
        reserve(coordinator, "llama-three", "llama-b", 1)
    reserve(coordinator, "judge-one", "judge-a", 5 * USD)
    assert coordinator.status().known_subtotal.programme == 10 * USD
    with pytest.raises(sb.Blocked, match="programme cap"):
        reserve(coordinator, "judge-two", "judge-b", 1)


def test_20b_remains_capped_while_120b_is_a_distinct_pinned_target(make_budget):
    old = historical("original-20b", sb.Target.OSS_20B, 6 * USD)
    coordinator = make_budget(snapshot(settled=(old,)))
    with pytest.raises(sb.Blocked, match="original model cap"):
        reserve(coordinator, "20b-over", "oss-20b", 1)
    with pytest.raises(sb.Blocked, match="original model cap"):
        reserve(coordinator, "20b-judge-over", "oss-20b-judge", 1)

    reserve(coordinator, "20b-zero", "oss-20b", 0, request_name="same-job")
    final_bill(coordinator, "20b-zero", 0)
    nonreturn(coordinator, "20b-zero")
    with pytest.raises(sb.Blocked, match="pinned lane or target"):
        reserve(coordinator, "switched", "oss-120b", 1, request_name="same-job", retry_of="20b-zero")
    with pytest.raises(sb.InvalidInput, match="existing logical request"):
        reserve(coordinator, "relabeled", "oss-120b", 1, request_name="same-job")

    distinct = reserve(coordinator, "actual-synthetic-120b", "oss-120b", 4 * USD)
    assert distinct.role is sb.Role.JUDGE
    reserve(coordinator, "separate-judge", "judge-b", 6 * USD)
    state = coordinator.status()
    assert state.known_subtotal.for_target(sb.Target.OSS_20B) == 6 * USD
    assert state.known_subtotal.for_target(sb.Target.OSS_120B) == 4 * USD
    assert state.known_subtotal.programme == 10 * USD
    with pytest.raises(sb.Blocked, match="programme cap"):
        reserve(coordinator, "judge-over", "judge-a", 1)


def test_unknown_preflight_blocks_until_separately_evidenced(make_budget):
    coordinator = make_budget(snapshot(preflight=None))
    state = coordinator.status()
    assert state.attempts_used == 1
    assert state.unbounded_unknown_items == (item("preflight"),)
    assert state.initial_settled.programme == 0  # This is NOT a known zero bill.
    with pytest.raises(sb.Blocked, match="unknown preflight"):
        reserve(coordinator, "before-bill", "judge-a", 0)

    bill_ev = evidence("later-preflight-bill", "billing")
    assert coordinator.record_external_final(item("preflight"), USD, bill_ev) is sb.BillingResult.RECORDED
    assert coordinator.record_external_final(item("preflight"), USD, bill_ev) is sb.BillingResult.UNCHANGED
    state = coordinator.status()
    assert state.unbounded_unknown_items == ()
    assert state.initial_settled.programme == 0
    assert state.external_settled.programme == USD
    assert state.known_subtotal.study == USD
    assert state.attempts_used == 1
    reserve(coordinator, "after-bill", "judge-a", 9 * USD)
    assert coordinator.status().known_subtotal.programme == 10 * USD


def test_unknown_liabilities_are_separate_from_history_and_holds(make_budget):
    old = historical("old-llama", sb.Target.LLAMA, USD)
    pending = liability("unknown-llama", sb.Target.LLAMA, 3 * USD)
    coordinator = make_budget(snapshot(settled=(old,), liabilities=(pending,)))
    reserve(coordinator, "new-llama", "llama-a", USD)
    state = coordinator.status()
    assert state.initial_settled.for_target(sb.Target.LLAMA) == USD
    assert state.external_holds.for_target(sb.Target.LLAMA) == 3 * USD
    assert state.attempt_holds.for_target(sb.Target.LLAMA) == USD
    assert state.bounded_unknown_items == (item("unknown-llama"),)
    assert state.known_subtotal.for_target(sb.Target.LLAMA) == 5 * USD
    with pytest.raises(sb.Blocked, match="original model cap"):
        reserve(coordinator, "before-resolution", "llama-b", 1)

    ev = evidence("external-final-llama", "billing")
    assert coordinator.record_external_final(item("unknown-llama"), 2 * USD, ev) is sb.BillingResult.RECORDED
    state = coordinator.status()
    assert state.external_holds.study == 0
    assert state.external_settled.for_target(sb.Target.LLAMA) == 2 * USD
    assert state.bounded_unknown_items == ()
    assert state.known_subtotal.for_target(sb.Target.LLAMA) == 4 * USD
    reserve(coordinator, "after-resolution", "llama-b", USD)
    assert coordinator.status().known_subtotal.for_target(sb.Target.LLAMA) == 5 * USD


def test_unbounded_external_liability_blocks_all_lanes(make_budget):
    pending = liability("unbounded", sb.Target.LLAMA, None)
    coordinator = make_budget(snapshot(liabilities=(pending,)))
    assert coordinator.status().unbounded_unknown_items == (item("unbounded"),)
    with pytest.raises(sb.Blocked, match="unknown external cost"):
        reserve(coordinator, "other-lane", "judge-a", 0)
    assert coordinator.record_external_final(
        item("unbounded"), 2 * USD, evidence("unbounded-final", "billing")
    ) is sb.BillingResult.RECORDED
    reserve(coordinator, "now-allowed", "judge-a", USD)
    assert coordinator.status().known_subtotal.study == 3 * USD


def test_observed_bill_above_external_bound_is_preserved_and_freezes(make_budget):
    pending = liability("external-breach", sb.Target.DEEPSEEK, USD)
    coordinator = make_budget(snapshot(liabilities=(pending,)))
    result = coordinator.record_external_final(
        item("external-breach"), 2 * USD, evidence("external-breach-final", "billing")
    )
    assert result is sb.BillingResult.BOUND_BREACH
    state = coordinator.status()
    assert state.external_holds.study == 0
    assert state.external_settled.study == 2 * USD
    assert state.conflicts[0].amount == 2 * USD
    with pytest.raises(sb.Blocked, match="breached billing"):
        reserve(coordinator, "frozen", "judge-a", 0)


def test_only_evidenced_final_bill_releases_a_hold_and_nonreturn_does_not(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "first", "llama-a", 5 * USD)
    nonreturn(coordinator, "first")
    assert coordinator.status().attempt_holds.study == 5 * USD
    with pytest.raises(sb.Blocked, match="final billing"):
        reserve(coordinator, "early-retry", "llama-a", 0, request_name="first", retry_of="first")
    assert final_bill(coordinator, "first", 2 * USD) is sb.BillingResult.RECORDED
    assert final_bill(coordinator, "first", 2 * USD) is sb.BillingResult.UNCHANGED
    state = coordinator.status()
    assert state.attempt_holds.study == 0
    assert state.attempt_settled.study == 2 * USD
    reserve(coordinator, "new-request", "llama-b", 3 * USD)
    assert coordinator.status().known_subtotal.for_target(sb.Target.LLAMA) == 5 * USD


def test_retry_requires_distinct_billing_and_nonreturn_evidence_and_global_quota(make_budget):
    coordinator = make_budget(snapshot(allowance=1))
    reserve(coordinator, "first", "judge-a", USD, request_name="job-one")
    final_bill(coordinator, "first", 0)
    with pytest.raises(sb.Blocked, match="non-return"):
        reserve(coordinator, "first-retry", "judge-a", 1, request_name="job-one", retry_of="first")
    with pytest.raises(sb.InvalidInput, match="already used"):
        nonreturn(coordinator, "first", evidence_name="bill-first", actor="billing")
    nonreturn(coordinator, "first", evidence_name="same-source", actor="billing")
    with pytest.raises(sb.Blocked, match="another attester"):
        reserve(coordinator, "first-retry", "judge-a", 1, request_name="job-one", retry_of="first")
    nonreturn(coordinator, "first", evidence_name="independent-nonreturn", actor="termination")
    reserve(coordinator, "first-retry", "judge-a", 1, request_name="job-one", retry_of="first")
    assert coordinator.status().retries_used == 1
    assert coordinator.status().attempts_used == 3  # preflight, initial and retry

    reserve(coordinator, "second", "judge-b", 2, request_name="job-two")
    final_bill(coordinator, "second", 0)
    nonreturn(coordinator, "second")
    with pytest.raises(sb.Blocked, match="global retry allowance"):
        reserve(coordinator, "second-retry", "judge-b", 2, request_name="job-two", retry_of="second")
    # Exhausting retries does not consume all remaining initial-attempt slots.
    reserve(coordinator, "third-initial", "judge-b", 0)


def test_retry_must_name_latest_attempt_and_cannot_reuse_bound_evidence(make_budget):
    coordinator = make_budget(snapshot(allowance=3))
    reserve(coordinator, "initial", "judge-a", USD, request_name="job")
    final_bill(coordinator, "initial", 0)
    nonreturn(coordinator, "initial")
    with pytest.raises(sb.InvalidInput, match="bound evidence"):
        reserve(
            coordinator, "reuse-bound", "judge-a", 1, request_name="job", retry_of="initial",
            bound_evidence=evidence("bound-initial", "bounds"),
        )
    reserve(coordinator, "retry-one", "judge-a", USD, request_name="job", retry_of="initial")
    with pytest.raises(sb.Blocked, match="latest attempt"):
        reserve(coordinator, "fork", "judge-a", 1, request_name="job", retry_of="initial")
    with pytest.raises(sb.Blocked, match="final billing"):
        reserve(coordinator, "too-early", "judge-a", 1, request_name="job", retry_of="retry-one")
    assert coordinator.status().attempt_holds.study == USD


def test_administrative_attempts_count_toward_http_and_programme(make_budget):
    coordinator = make_budget(snapshot(preflight=USD))
    assert coordinator.status().attempts_used == 1
    reserve(coordinator, "admin-request", "admin", 2 * USD)
    state = coordinator.status()
    assert state.attempts_used == 2
    assert state.initial_settled.programme == USD
    assert state.attempt_holds.programme == 2 * USD
    assert state.known_subtotal.study == 3 * USD


def _snapshot_with_1399_attempts():
    # One preflight plus 1,398 invented, distinct, zero-billed programme attempts.
    old = tuple(
        historical(
            f"prior-{i}", sb.Target.JUDGE_A, 0, programme=True,
            request_name=f"prior-{i}", lane_name="judge-a",
        )
        for i in range(1_398)
    )
    return snapshot(settled=old)


def test_exact_1400_http_attempt_limit_includes_preflight(make_budget):
    coordinator = make_budget(_snapshot_with_1399_attempts())
    assert coordinator.status().attempts_used == 1_399
    reserve(coordinator, "last-attempt", "admin", 0)
    assert coordinator.status().attempts_used == 1_400
    with pytest.raises(sb.Blocked, match="HTTP-attempt allowance"):
        reserve(coordinator, "too-many", "judge-a", 0)
    assert coordinator.status().attempts_used == 1_400


def test_snapshot_counts_historical_retries_but_will_not_retry_historical_jobs(make_budget):
    old = (
        historical("old-initial", sb.Target.JUDGE_A, 0, programme=True,
                   request_name="old-job", lane_name="judge-a"),
        historical("old-retry", sb.Target.JUDGE_A, 0, programme=True,
                   request_name="old-job", lane_name="judge-a", retry=True),
    )
    coordinator = make_budget(snapshot(settled=old, allowance=1))
    assert coordinator.status().attempts_used == 3
    assert coordinator.status().retries_used == 1
    with pytest.raises(sb.Blocked, match="historical programme requests"):
        reserve(coordinator, "old-again", "judge-a", 0, request_name="old-job")
    reserve(coordinator, "new-initial", "judge-a", 0, request_name="new-job")
    final_bill(coordinator, "new-initial", 0)
    nonreturn(coordinator, "new-initial")
    with pytest.raises(sb.Blocked, match="global retry allowance"):
        reserve(coordinator, "new-retry", "judge-a", 0, request_name="new-job", retry_of="new-initial")


def test_already_exceeded_retry_allowance_blocks_even_new_initials(make_budget):
    old = (
        historical("old-initial", sb.Target.JUDGE_A, 0, programme=True,
                   request_name="old-job", lane_name="judge-a"),
        historical("old-retry-one", sb.Target.JUDGE_A, 0, programme=True,
                   request_name="old-job", lane_name="judge-a", retry=True),
        historical("old-retry-two", sb.Target.JUDGE_A, 0, programme=True,
                   request_name="old-job", lane_name="judge-a", retry=True),
    )
    coordinator = make_budget(snapshot(settled=old, allowance=1))
    assert coordinator.status().retries_used == 2
    with pytest.raises(sb.Blocked, match="existing synthetic state exceeds the global retry"):
        reserve(coordinator, "new-initial", "judge-b", 0)


def test_conflicting_bills_are_retained_and_permanently_freeze_reservations(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "first", "llama-a", 5 * USD)
    final_bill(coordinator, "first", 2 * USD)
    reserve(coordinator, "other", "llama-b", USD)
    result = final_bill(coordinator, "first", 3 * USD, evidence_name="conflicting-bill")
    assert result is sb.BillingResult.CONFLICT
    state = coordinator.status()
    assert state.attempt_settled.study == 2 * USD
    assert state.attempt_holds.study == USD
    assert state.conflicts[0].item_id == item("first")
    assert state.conflicts[0].amount == 3 * USD
    assert state.conflicts[0].evidence_id == "synthetic:evidence:conflicting-bill"
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "must-not-spend", "judge-a", 0)


def test_bill_above_attempt_bound_is_not_silently_rejected(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "bounded", "judge-a", USD)
    assert final_bill(coordinator, "bounded", 2 * USD) is sb.BillingResult.BOUND_BREACH
    state = coordinator.status()
    assert state.attempt_settled.study == 2 * USD
    assert state.attempt_holds.study == 0
    assert state.conflicts[0].amount == 2 * USD
    with pytest.raises(sb.Blocked, match="breached billing"):
        reserve(coordinator, "after-breach", "judge-b", 0)


def test_reused_final_billing_evidence_freezes_and_preserves_other_hold(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "one", "judge-a", USD)
    reserve(coordinator, "two", "judge-b", USD)
    final_bill(coordinator, "one", 0, evidence_name="shared-bill")
    assert final_bill(coordinator, "two", 0, evidence_name="shared-bill") is sb.BillingResult.CONFLICT
    state = coordinator.status()
    assert state.attempt_holds.study == USD
    assert state.conflicts[0].item_id == item("two")
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "blocked", "judge-a", 0)


def test_conflicting_preflight_bill_is_retained_not_overwritten(make_budget):
    coordinator = make_budget(snapshot(preflight=USD))
    assert coordinator.record_external_final(
        item("preflight"), 2 * USD, evidence("different-preflight-bill", "billing")
    ) is sb.BillingResult.CONFLICT
    state = coordinator.status()
    assert state.initial_settled.programme == USD
    assert state.conflicts[0].amount == 2 * USD
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "blocked", "judge-a", 0)


def test_schema_changes_after_initialization_block_reservations(make_budget):
    coordinator = make_budget()
    connection = coordinator._connection  # Invented, caller-owned test database.
    connection.execute(
        "CREATE TRIGGER synthetic_erase AFTER INSERT ON synthetic_attempts "
        "BEGIN DELETE FROM synthetic_attempts WHERE attempt_id = NEW.attempt_id; END"
    )
    with pytest.raises(sb.InvalidInput, match="schema"):
        reserve(coordinator, "silently-erased", "judge-a", USD)
    assert connection.execute("SELECT COUNT(*) FROM main.synthetic_attempts").fetchone()[0] == 0


def test_temporary_shadow_after_initialization_blocks_reservations(make_budget):
    coordinator = make_budget()
    connection = coordinator._connection
    connection.execute("CREATE TEMP TABLE synthetic_attempts AS SELECT * FROM main.synthetic_attempts WHERE 0")
    with pytest.raises(sb.InvalidInput):
        reserve(coordinator, "shadowed", "judge-a", USD)
    assert connection.execute("SELECT COUNT(*) FROM main.synthetic_attempts").fetchone()[0] == 0


@pytest.mark.parametrize("source", ["attempt", "preflight"])
@pytest.mark.parametrize("bad", [None, -1, True, float("nan"), 1 << 63, "1"])
def test_malformed_late_bill_quarantines_even_a_settled_item(make_budget, source, bad):
    coordinator = make_budget()
    if source == "attempt":
        reserve(coordinator, "settled", "judge-a", USD)
        final_bill(coordinator, "settled", 0)
        report = lambda: coordinator.record_final_bill(item("settled"), bad, evidence("late-invalid", "billing"))
    else:
        report = lambda: coordinator.record_external_final(item("preflight"), bad, evidence("late-invalid", "billing"))
    with pytest.raises(sb.InvalidInput):
        report()
    state = coordinator.status()
    assert state.conflicts and state.conflicts[-1].amount is None
    assert state.attempt_settled.study == 0 and state.initial_settled.study == 0
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "blocked-after-invalid", "judge-b", 0)


def test_malformed_unsettled_bill_keeps_hold_and_stops_even_after_later_bill(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "pending", "llama-a", USD)
    with pytest.raises(sb.InvalidInput, match="quarantined"):
        coordinator.record_final_bill(item("pending"), None, evidence("bad-pending-bill", "billing"))
    assert coordinator.status().attempt_holds.study == USD
    assert final_bill(coordinator, "pending", 0) is sb.BillingResult.RECORDED
    assert coordinator.status().attempt_settled.study == 0
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "still-blocked", "judge-a", 0)


@pytest.mark.parametrize("claim", ["attempt_bill", "external_bill", "return", "nonreturn",
                                    "malformed_bill", "malformed_external"])
def test_unrecognized_physical_claim_is_quarantined_instead_of_ignored(make_budget, claim):
    coordinator = make_budget()
    unknown = item("outside-snapshot")
    ev = evidence("unknown-claim", "observer")
    if claim == "attempt_bill":
        assert coordinator.record_final_bill(unknown, USD, ev) is sb.BillingResult.CONFLICT
    elif claim == "external_bill":
        assert coordinator.record_external_final(unknown, USD, ev) is sb.BillingResult.CONFLICT
    elif claim == "return":
        assert coordinator.record_return(unknown, ev) is sb.ObservationResult.CONFLICT
    elif claim == "nonreturn":
        assert coordinator.record_nonreturn(unknown, ev) is sb.ObservationResult.CONFLICT
    elif claim == "malformed_bill":
        with pytest.raises(sb.InvalidInput, match="quarantined"):
            coordinator.record_final_bill(unknown, None, ev)
    else:
        with pytest.raises(sb.InvalidInput, match="quarantined"):
            coordinator.record_external_final(unknown, None, ev)
    state = coordinator.status()
    assert state.conflicts[-1].item_id == unknown
    assert state.conflicts[-1].amount == (USD if claim in {"attempt_bill", "external_bill"} else None)
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "not-after-unrecognized-claim", "judge-a", 0)


def test_return_before_nonreturn_blocks_retry_and_preserves_conflict(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "returned", "judge-a", USD, request_name="job")
    returned = evidence("returned-response", "worker")
    assert coordinator.record_return(item("returned"), returned) is sb.ObservationResult.RECORDED
    assert coordinator.record_return(item("returned"), returned) is sb.ObservationResult.UNCHANGED
    final_bill(coordinator, "returned", 0)
    with pytest.raises(sb.Blocked, match="returned"):
        reserve(coordinator, "must-not-retry", "judge-a", 1, request_name="job", retry_of="returned")
    assert coordinator.record_nonreturn(item("returned"), evidence("wrong-nonreturn", "other")) is sb.ObservationResult.CONFLICT
    state = coordinator.status()
    assert state.returned_attempts == (item("returned"),)
    assert state.conflicts[-1].amount is None
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "other-blocked", "judge-b", 0)


def test_late_return_after_evidenced_retry_preserves_hold_and_freezes(make_budget):
    coordinator = make_budget()
    reserve(coordinator, "initial", "judge-a", USD, request_name="job")
    final_bill(coordinator, "initial", 0)
    nonreturn(coordinator, "initial")
    reserve(coordinator, "retry", "judge-a", USD, request_name="job", retry_of="initial")
    assert coordinator.record_return(item("initial"), evidence("late-return", "worker")) is sb.ObservationResult.CONFLICT
    state = coordinator.status()
    assert state.attempts_used == 3 and state.attempt_holds.study == USD
    assert state.returned_attempts == (item("initial"),)
    assert state.conflicts[-1].amount is None
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "after-conflict", "judge-b", 0)


@pytest.mark.parametrize("claim", ["bill", "return"])
def test_malformed_positive_evidence_quarantines_without_exporting_input(make_budget, claim):
    coordinator = make_budget()
    reserve(coordinator, "pending", "judge-a", USD)
    invalid_evidence = {"untrusted": "invented private-looking text"}
    with pytest.raises(sb.InvalidInput, match="quarantined"):
        if claim == "bill":
            coordinator.record_final_bill(item("pending"), 0, invalid_evidence)
        else:
            coordinator.record_return(item("pending"), invalid_evidence)
    state = coordinator.status()
    assert state.attempt_holds.study == USD and state.conflicts[-1].amount is None
    assert "private-looking" not in repr(state)
    with pytest.raises(sb.Blocked, match="conflicting"):
        reserve(coordinator, "blocked", "judge-b", 0)


@pytest.mark.parametrize("bad", [-1, True, 1.25, float("nan"), 1 << 63, "1"])
def test_malformed_amounts_do_not_consume_or_release_anything(make_budget, bad):
    coordinator = make_budget()
    with pytest.raises(sb.InvalidInput):
        reserve(coordinator, "bad", "judge-a", bad)
    assert coordinator.status().attempts_used == 1
    reserve(coordinator, "good", "judge-a", USD)
    with pytest.raises(sb.InvalidInput):
        coordinator.record_final_bill(item("good"), bad, evidence("bad-bill", "billing"))
    assert coordinator.status().attempt_holds.study == USD


def test_snapshot_rejects_ambiguous_overlap_and_wrong_partitions(make_budget):
    one = historical("one", sb.Target.LLAMA, USD)
    repeated = liability("one", sb.Target.LLAMA, USD)
    with pytest.raises(sb.InvalidInput, match="overlap"):
        make_budget(snapshot(settled=(one,), liabilities=(repeated,)))
    with pytest.raises(sb.InvalidInput, match="overlap"):
        make_budget(snapshot(settled=(historical("preflight", sb.Target.LLAMA, USD),)))
    with pytest.raises(sb.InvalidInput, match="partitions"):
        make_budget(replace(snapshot(), settled=(repeated,)))
    same_evidence = replace(one, billing_evidence=evidence("preflight-sent", "observer"))
    with pytest.raises(sb.InvalidInput, match="reuses evidence"):
        make_budget(snapshot(settled=(same_evidence,)))
    coordinator = make_budget(snapshot(settled=(one,)))
    with pytest.raises(sb.InvalidInput, match="overlaps historical"):
        reserve(coordinator, "one", "judge-a", 0)


def test_ambiguous_historical_request_classification_is_rejected(make_budget):
    initial = historical("a", sb.Target.JUDGE_A, 0, programme=True,
                         request_name="same", lane_name="judge-a")
    second_initial = historical("b", sb.Target.JUDGE_A, 0, programme=True,
                                request_name="same", lane_name="judge-a")
    retry_only = replace(second_initial, is_retry=True)
    with pytest.raises(sb.InvalidInput, match="exactly one initial"):
        make_budget(snapshot(settled=(initial, second_initial)))
    with pytest.raises(sb.InvalidInput, match="exactly one initial"):
        make_budget(snapshot(settled=(retry_only,)))
    switched_retry = historical("c", sb.Target.JUDGE_B, 0, programme=True,
                                request_name="same", lane_name="judge-b", retry=True)
    with pytest.raises(sb.InvalidInput, match="cannot change lane"):
        make_budget(snapshot(settled=(initial, switched_retry)))


def test_synthetic_tags_attesters_and_snapshot_structure_are_mandatory(make_budget):
    base = snapshot()
    with pytest.raises(sb.InvalidInput, match="attester must differ"):
        make_budget(replace(base, attestation=evidence("same-actor", "preparer")))
    for changes in ({"attests_complete": False}, {"attests_disjoint": None}, {"attests_disjoint": 1}):
        with pytest.raises(sb.InvalidInput, match="completeness and disjointness"):
            make_budget(replace(base, **changes))
    with pytest.raises(sb.InvalidInput, match="synthetic snapshot"):
        make_budget(replace(base, snapshot_id="not-synthetic"))
    with pytest.raises(sb.InvalidInput, match="closed synthetic Target"):
        make_budget(replace(base, lanes=(
            sb.Lane(lane("alias"), "synthetic:model:gpt-oss-20b-alias", sb.Role.ORIGINAL),
        )))
    with pytest.raises(sb.InvalidInput, match="cannot be used in that synthetic lane role"):
        make_budget(replace(base, lanes=(
            sb.Lane(lane("120b-original"), sb.Target.OSS_120B, sb.Role.ORIGINAL),
        )))
    with pytest.raises(sb.InvalidInput, match="closed synthetic Role"):
        make_budget(replace(base, lanes=(
            sb.Lane(lane("false-role"), sb.Target.OSS_20B, "original"),
        )))
    with pytest.raises(sb.InvalidInput, match="retry allowance"):
        make_budget(replace(base, global_retry_allowance=True))
    with pytest.raises(sb.InvalidInput, match="retry allowance"):
        make_budget(replace(base, global_retry_allowance=4))
    with pytest.raises(sb.InvalidInput, match="independent attester"):
        make_budget(snapshot(liabilities=(replace(
            liability("bad-bound", sb.Target.LLAMA, 1), bound_evidence=evidence("weak-bound", "preparer")
        ),)))
    coordinator = make_budget()
    with pytest.raises(sb.InvalidInput, match="bound attester"):
        reserve(coordinator, "not-independent", "judge-a", 1,
                bound_evidence=evidence("not-independent", "preparer"))


def test_existing_over_cap_state_is_preserved_and_blocks_every_lane(make_budget):
    old = historical("over-already", sb.Target.LLAMA, 5 * USD + 1)
    coordinator = make_budget(snapshot(settled=(old,)))
    assert coordinator.status().initial_settled.for_target(sb.Target.LLAMA) == 5 * USD + 1
    with pytest.raises(sb.Blocked, match="already above a cap"):
        reserve(coordinator, "other-model", "judge-a", 0)


def test_preflight_cost_above_programme_cap_is_retained_and_blocks(make_budget):
    coordinator = make_budget(snapshot(preflight=10 * USD + 1))
    state = coordinator.status()
    assert state.initial_settled.programme == 10 * USD + 1
    assert state.attempts_used == 1
    with pytest.raises(sb.Blocked, match="already above a cap"):
        reserve(coordinator, "no-headroom", "judge-a", 0)


def test_liability_bound_cannot_be_missing_or_double_used(make_budget):
    bounded = liability("bounded", sb.Target.LLAMA, USD)
    with pytest.raises(sb.InvalidInput, match="expected synthetic evidence"):
        make_budget(snapshot(liabilities=(replace(bounded, bound_evidence=None),)))
    with pytest.raises(sb.InvalidInput, match="reuses evidence"):
        make_budget(snapshot(liabilities=(replace(
            bounded, bound_evidence=bounded.observation_evidence
        ),)))
    unbounded = liability("unbounded", sb.Target.LLAMA, None)
    with pytest.raises(sb.InvalidInput, match="unbounded liability"):
        make_budget(snapshot(liabilities=(replace(
            unbounded, bound_evidence=evidence("fictional-bound", "bounds")
        ),)))


def test_connection_scope_rejects_unrelated_schema_files_and_attachments(scratch):
    connection = connect(scratch / "ordinary.sqlite3")
    try:
        with pytest.raises(sb.InvalidInput, match="synthetic scratch"):
            sb.SyntheticBudget(connection, snapshot())
    finally:
        connection.close()

    connection = connect(scratch / "synthetic-shared-budget-unsafe.sqlite3")
    try:
        connection.execute("PRAGMA synchronous = OFF")
        with pytest.raises(sb.InvalidInput, match="durable SQLite settings"):
            sb.SyntheticBudget(connection, snapshot())
    finally:
        connection.close()

    connection = connect()
    try:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        with pytest.raises(sb.InvalidInput, match="synthetic-only schema"):
            sb.SyntheticBudget(connection, snapshot())
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == [("unrelated",)]
    finally:
        connection.close()

    connection = connect()
    try:
        connection.execute("BEGIN")
        with pytest.raises(sb.InvalidInput, match="idle"):
            sb.SyntheticBudget(connection, snapshot())
        connection.rollback()
    finally:
        connection.close()

    connection = connect()
    try:
        connection.execute("ATTACH DATABASE ':memory:' AS extra")
        with pytest.raises(sb.InvalidInput, match="attached databases"):
            sb.SyntheticBudget(connection, snapshot())
    finally:
        connection.close()


@pytest.mark.parametrize(
    "lane_names,amount,reason",
    [
        (("llama-a", "llama-b"), 3 * USD, "original model cap"),
        (("judge-a", "judge-b"), 6 * USD, "programme cap"),
    ],
)
def test_concurrent_connections_cannot_double_reserve(scratch, lane_names, amount, reason):
    path = scratch / "synthetic-shared-budget-concurrent.sqlite3"
    snap = snapshot()
    connection = connect(path)
    sb.SyntheticBudget(connection, snap)
    connection.close()
    barrier = threading.Barrier(2)

    def worker(index):
        local = connect(path)
        try:
            coordinator = sb.SyntheticBudget(local, snap)
            barrier.wait(timeout=10)
            try:
                reserve(coordinator, f"concurrent-{index}", lane_names[index], amount)
                return "reserved"
            except sb.Blocked as error:
                assert reason in str(error)
                return "blocked"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sorted(results) == ["blocked", "reserved"]
    connection = connect(path)
    try:
        state = sb.SyntheticBudget(connection, snap).status()
        assert state.attempts_used == 2
        assert state.attempt_holds.study == amount
    finally:
        connection.close()


def test_concurrent_retries_share_one_global_allowance(scratch):
    path = scratch / "synthetic-shared-budget-retries.sqlite3"
    snap = snapshot(allowance=1)
    connection = connect(path)
    coordinator = sb.SyntheticBudget(connection, snap)
    for name in ("one", "two"):
        reserve(coordinator, name, "judge-a", 0, request_name=name)
        final_bill(coordinator, name, 0)
        nonreturn(coordinator, name)
    connection.close()
    barrier = threading.Barrier(2)

    def worker(name):
        local = connect(path)
        try:
            coordinator = sb.SyntheticBudget(local, snap)
            barrier.wait(timeout=10)
            try:
                reserve(coordinator, f"retry-{name}", "judge-a", 0, request_name=name, retry_of=name)
                return "reserved"
            except sb.Blocked as error:
                assert "global retry allowance" in str(error)
                return "blocked"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ("one", "two")))
    assert sorted(results) == ["blocked", "reserved"]
    connection = connect(path)
    try:
        state = sb.SyntheticBudget(connection, snap).status()
        assert state.retries_used == 1
        assert state.attempts_used == 4
    finally:
        connection.close()


def test_concurrent_last_http_attempt_is_reserved_only_once(scratch):
    path = scratch / "synthetic-shared-budget-last-attempt.sqlite3"
    snap = _snapshot_with_1399_attempts()
    connection = connect(path)
    sb.SyntheticBudget(connection, snap)
    connection.close()
    barrier = threading.Barrier(2)

    def worker(index):
        local = connect(path)
        try:
            coordinator = sb.SyntheticBudget(local, snap)
            barrier.wait(timeout=10)
            try:
                reserve(coordinator, f"last-{index}", "admin", 0)
                return "reserved"
            except sb.Blocked as error:
                assert "HTTP-attempt allowance" in str(error)
                return "blocked"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sorted(results) == ["blocked", "reserved"]
    connection = connect(path)
    try:
        assert sb.SyntheticBudget(connection, snap).status().attempts_used == 1_400
    finally:
        connection.close()


def test_restart_and_interrupted_transaction_keep_committed_holds(scratch):
    path = scratch / "synthetic-shared-budget-recovery.sqlite3"
    snap = snapshot()
    first = connect(path)
    original = sb.SyntheticBudget(first, snap)
    fingerprint = original.snapshot_hash
    reserve(original, "committed", "llama-a", 2 * USD)
    first.close()

    interrupted = connect(path)
    reopened = sb.SyntheticBudget(interrupted, snap)
    assert reopened.snapshot_hash == fingerprint
    assert reopened.status().attempt_holds.study == 2 * USD
    assert reopened.status().attempts_used == 2
    # Simulate interruption after uncommitted SQL, not a process or power failure.
    interrupted.execute("BEGIN IMMEDIATE")
    interrupted.execute(
        "UPDATE synthetic_attempts SET final_amount = 0, billing_evidence = ?, billing_attester = ? "
        "WHERE attempt_id = ?",
        ("synthetic:evidence:uncommitted-bill", "synthetic:actor:billing", item("committed")),
    )
    interrupted.execute(
        "INSERT INTO synthetic_evidence VALUES (?, ?, ?, ?)",
        ("synthetic:evidence:bound-phantom", "attempt-bound", item("phantom"), "synthetic:actor:bounds"),
    )
    interrupted.execute(
        "INSERT INTO synthetic_attempts (attempt_id, request_id, lane_id, target, retry_of, ordinal, "
        "bound, bound_evidence, bound_attester) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item("phantom"), request("phantom"), lane("llama-a"), sb.Target.LLAMA.value,
         None, 0, USD, "synthetic:evidence:bound-phantom", "synthetic:actor:bounds"),
    )
    interrupted.close()  # SQLite rolls the incomplete transaction back.

    recovered = connect(path)
    try:
        coordinator = sb.SyntheticBudget(recovered, snap)
        state = coordinator.status()
        assert state.attempt_holds.study == 2 * USD
        assert state.attempt_settled.study == 0
        assert state.attempts_used == 2
        reserve(coordinator, "phantom", "llama-a", 3 * USD)
        assert coordinator.status().attempts_used == 3
        with pytest.raises(sb.SnapshotMismatch):
            sb.SyntheticBudget(recovered, replace(snap, global_retry_allowance=2))
        assert coordinator.status().attempt_holds.study == 5 * USD
    finally:
        recovered.close()


def test_retry_evidence_and_conflicts_survive_reopening(scratch):
    path = scratch / "synthetic-shared-budget-evidence.sqlite3"
    snap = snapshot()
    first = connect(path)
    coordinator = sb.SyntheticBudget(first, snap)
    reserve(coordinator, "initial", "judge-a", USD, request_name="job")
    final_bill(coordinator, "initial", 0)
    first.close()
    second = connect(path)
    coordinator = sb.SyntheticBudget(second, snap)
    with pytest.raises(sb.Blocked, match="non-return"):
        reserve(coordinator, "retry", "judge-a", 1, request_name="job", retry_of="initial")
    nonreturn(coordinator, "initial")
    reserve(coordinator, "retry", "judge-a", 1, request_name="job", retry_of="initial")
    assert final_bill(coordinator, "initial", 1, evidence_name="contradiction") is sb.BillingResult.CONFLICT
    second.close()
    third = connect(path)
    try:
        reopened = sb.SyntheticBudget(third, snap)
        assert reopened.status().retries_used == 1
        assert reopened.status().conflicts[0].amount == 1
        with pytest.raises(sb.Blocked, match="conflicting"):
            reserve(reopened, "after-restart", "judge-b", 0)
    finally:
        third.close()


def test_return_conflict_and_holds_survive_reopening(scratch):
    path = scratch / "synthetic-shared-budget-return-recovery.sqlite3"
    snap = snapshot()
    first = connect(path)
    coordinator = sb.SyntheticBudget(first, snap)
    reserve(coordinator, "initial", "judge-a", USD, request_name="job")
    final_bill(coordinator, "initial", 0)
    nonreturn(coordinator, "initial")
    reserve(coordinator, "retry", "judge-a", USD, request_name="job", retry_of="initial")
    assert coordinator.record_return(item("initial"), evidence("late-response", "worker")) is sb.ObservationResult.CONFLICT
    first.close()
    reopened = connect(path)
    try:
        coordinator = sb.SyntheticBudget(reopened, snap)
        state = coordinator.status()
        assert state.returned_attempts == (item("initial"),)
        assert state.attempt_holds.study == USD and state.conflicts[-1].amount is None
        with pytest.raises(sb.Blocked, match="conflicting"):
            reserve(coordinator, "after-reopen", "judge-b", 0)
    finally:
        reopened.close()


def test_second_connection_schema_change_is_seen_before_reservation(scratch):
    path = scratch / "synthetic-shared-budget-schema-change.sqlite3"
    first, second = connect(path), connect(path)
    try:
        coordinator = sb.SyntheticBudget(first, snapshot())
        second.execute(
            "CREATE TRIGGER synthetic_external_erase AFTER INSERT ON synthetic_attempts "
            "BEGIN DELETE FROM synthetic_attempts WHERE attempt_id = NEW.attempt_id; END"
        )
        with pytest.raises(sb.InvalidInput, match="schema"):
            reserve(coordinator, "blocked-by-schema", "judge-a", USD)
        assert second.execute("SELECT COUNT(*) FROM main.synthetic_attempts").fetchone()[0] == 0
    finally:
        second.close()
        first.close()
