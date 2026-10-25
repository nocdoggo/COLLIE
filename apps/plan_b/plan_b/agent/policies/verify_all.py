"""P3, the verify-all ablation: ``verify-all/1.0.0``.

P2's downstream planner and action logic (``LivePolicy``: interpretation, evaluation, the
robustness restriction, the closed menu and its execution) with one change. Before each
decision step the policy requests every relevant available status check once for the current
unresolved update, without asking the model which; only then does the step build the menu. A
failed check is retried under P2's bound (``MAX_STATUS_FAILURES`` attempts per check since the
update) and then left unverified: the policy never waits for a failed source, and the menu and
the robustness rule decide as in P2.

Relevance (``RELEVANCE_RULE``, fixed before any run; it names event and resource identifiers
only):

* The current unresolved update is the set of notices the server holds as claims or as
  verify-only notices about this event (never ``inapplicable``, ``duplicate`` or retracted) that
  no successful check of their subject requested at or after their arrival has answered; on a
  consumable profile also an open supply gap of a service target.
* Its relevant resources are each such notice's subject resource, each registered approved
  substitute of that subject, and, for a supply gap, every pool a declared stock option of that
  target names (its pool and its transfer source). A resource named by several such notices
  belongs to the latest one's arrival.
* A relevant check is ``(resource, fact)`` for such a resource whose registered status source
  lists it, in the coordinator grant's resource scope, for each fact both the source and the
  resource's terms declare, while ``query_status`` is granted.
* A check is due when no successful check of it was requested at or after the update's arrival
  (any successful check, for a supply gap) and fewer than ``MAX_STATUS_FAILURES`` of this
  principal's checks of it since then failed; only the remaining attempts are made.

Notices that arrive while the checks run are part of the update: the relevant checks are
recomputed after each batch, at most ``MAX_VERIFY_ROUNDS`` batches per step. Each check is
recorded as a ``verify`` decision chosen by the server (``details.verify_all``), and its result
is carried to the next model call like any tool result.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from plan_b.agent.config import ModelConfig, load_model_config
from plan_b.agent.menu import own_grant
from plan_b.agent.orchestrator import (
    _EPOCH,
    DEFAULT_MAX_MODEL_CALLS,
    DEFAULT_MAX_TOOL_CALLS,
    MAX_STATUS_FAILURES,
    LivePolicy,
    _envelope_summary,
    _resources,
    _Run,
    _status_text,
)
from plan_b.agent.provider import (
    DEFAULT_TIMEOUT_S,
    OpenAICompatibleProvider,
    SpendGuard,
    SpendLedger,
)
from plan_b.domain.models import EventStateView, ObservationRecord

POLICY_ID = "verify-all/1.0.0"
RELEVANCE_RULE = "verify-all-relevance/1.0.0"
MAX_VERIFY_ROUNDS = 3  # batches of checks per step (notices arriving during a batch)


@dataclass(frozen=True)
class RelevantCheck:
    entity_id: str
    fact: str
    since: datetime
    why: str
    refs: tuple[str, ...] = ()
    failures: int = 0  # this principal's failed checks of it since ``since``


class VerifyAllPolicy(LivePolicy):
    """``verify-all/1.0.0``: every relevant status check first, then P2's menu and choice."""

    policy_id = POLICY_ID

    def relevant_checks(self, view: EventStateView) -> list[RelevantCheck]:
        """The relevant checks of the current unresolved update (``RELEVANCE_RULE``)."""
        grant = own_grant(view, self._principal)
        if grant is None or "query_status" not in grant.grant.allowed_tools:
            return []
        scope = set(grant.grant.resource_ids)
        resources = _resources(view)
        wanted: dict[str, tuple[datetime, str, tuple[str, ...]]] = {}

        def want(rid: str, since: datetime, why: str, refs: tuple[str, ...] = ()) -> None:
            # A resource belongs to the latest unanswered notice that names it.
            if rid in resources and (rid not in wanted or since > wanted[rid][0]):
                wanted[rid] = (since, why, refs)

        for claim in self._claims(view):
            rid = claim.subject_resource_id
            if rid is None or self._answer(view, claim) is not None:
                continue
            oid = claim.observation_id
            want(rid, claim.received_at, f"subject of unanswered notice {oid}", (oid,))
            for sub in (
                resources[rid].definition.approved_substitute_ids if rid in resources else ()
            ):
                want(sub, claim.received_at, f"approved substitute of {rid} ({oid})", (oid,))
        stock = view.stock
        if stock is not None:
            for service in stock.service:
                if not service.supply_gap_quantity:
                    continue
                for option in view.stock_options:
                    if option.service_target_id != service.target_id:
                        continue
                    why = f"pool of a stock option for {service.target_id} (supply gap)"
                    for rid in (option.resource_id, option.source_resource_id):
                        if rid is not None:
                            want(rid, _EPOCH, why)
        out: list[RelevantCheck] = []
        for rid, (since, why, refs) in wanted.items():
            terms = resources[rid].definition.terms
            source = next(
                (
                    s
                    for s in view.status_sources
                    if s.source_id == terms.status_source_id and rid in s.entity_ids
                ),
                None,
            )
            if source is None or rid not in scope:
                continue
            for fact in source.facts:
                failures = self._failures(view, rid, fact, since)
                if fact in terms.queryable_facts and failures is not None:
                    out.append(RelevantCheck(rid, fact, since, why, refs, failures))
        return out

    def _failures(self, view: EventStateView, rid: str, fact: str, since: datetime) -> int | None:
        """This principal's failed checks since ``since`` while the check is due, else None."""
        checks = [
            c
            for c in view.status_checks
            if c.entity_id == rid
            and c.fact == fact
            and c.requested_at is not None
            and c.requested_at >= since
        ]
        if any(c.envelope_status == "succeeded" for c in checks):
            return None
        failed = sum(1 for c in checks if c.actor_id == self._principal)
        return failed if failed < MAX_STATUS_FAILURES else None

    def _verify_first(self, view: EventStateView, run: _Run) -> EventStateView:
        """Request every due relevant check (with P2's retry bound), then re-read the state;
        repeat while notices that arrived meanwhile make further checks due."""
        for _ in range(MAX_VERIFY_ROUNDS):
            checks = self.relevant_checks(view)
            if not checks:
                break
            self._check_all(view, run, checks)
            view = self._refresh(run)
            self._interpret_new(view, run)
        return view

    def _check_all(self, view: EventStateView, run: _Run, checks: list[RelevantCheck]) -> None:
        for check in checks:
            for attempt in range(check.failures + 1, MAX_STATUS_FAILURES + 1):
                envelope = run.read(
                    "query_status", {"entity_id": check.entity_id, "fact": check.fact}
                )
                record = None
                data = envelope.data or {}
                if envelope.status == "succeeded" and data.get("observation"):
                    record = ObservationRecord.model_validate(data["observation"])
                self._pending_results.append(_envelope_summary(envelope, view, record))
                code = envelope.error.code if envelope.error is not None else None
                self._record(
                    run,
                    "verify",
                    f"Verify-all check of {check.entity_id} {check.fact} ({check.why}): "
                    f"{_status_text(envelope, record, view)}.",
                    observation_refs=check.refs
                    + ((record.observation.observation_id,) if record is not None else ()),
                    tool_call_refs=(envelope.call_id,),
                    details={
                        "verify_all": {
                            "rule": RELEVANCE_RULE,
                            "why": check.why,
                            "attempt": attempt,
                            "max_attempts": MAX_STATUS_FAILURES,
                        },
                        "entity_id": check.entity_id,
                        "fact": check.fact,
                        "outcome": envelope.status,
                        "error_code": code,
                    },
                )
                if envelope.status == "succeeded":
                    break


def verify_all_policy_factory(
    config: ModelConfig | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_model_calls: int = DEFAULT_MAX_MODEL_CALLS,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ledger_path: Path | None = None,
) -> Callable[[], VerifyAllPolicy]:
    """As ``live_policy_factory``: one provider and spend guard per instance (episode)."""
    cfg = config or load_model_config()
    ledger = SpendLedger(ledger_path or cfg.ledger_path)

    def make() -> VerifyAllPolicy:
        guard = SpendGuard(
            ledger,
            max_run_usd=cfg.max_run_cost_usd,
            max_total_usd=cfg.max_total_cost_usd,
            run_id=f"verify-all-{uuid.uuid4().hex[:12]}",
        )
        provider = OpenAICompatibleProvider(cfg, guard, timeout_s=timeout_s)
        return VerifyAllPolicy(
            provider, max_model_calls=max_model_calls, max_tool_calls=max_tool_calls
        )

    return make
