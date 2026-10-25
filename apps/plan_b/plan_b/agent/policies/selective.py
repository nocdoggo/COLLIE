"""P2, the selective verify/prepare/commit controller: ``live/1.0.0``.

The policy is ``plan_b.agent.orchestrator.LivePolicy`` itself, re-exported here under the
evaluation plan's name; its ``policy_id`` stays ``live/1.0.0``. The model chooses one option of
the server-built menu (``agent/menu.py``) per step, and queries are offered only for a stated
verification need. ``agent/policies/verify_all.py`` (P3) keeps this downstream logic, menu
included, and adds one step: before each decision step the server requests every relevant
status check of the current update.
"""

from __future__ import annotations

from plan_b.agent.orchestrator import POLICY_ID, LivePolicy, live_policy_factory

SelectivePolicy = LivePolicy
selective_policy_factory = live_policy_factory

__all__ = ["POLICY_ID", "LivePolicy", "SelectivePolicy", "selective_policy_factory"]
