"""Arm sets for the commitment study's runner.

``confirm`` is the stage C set: the real-content pilot's nine arms minus arm 9 (not part of any
stage C contrast), plus three certify-then-hedge arms:

* ``arm12_cth`` (``lam = 0.25``, the method) and ``arm12b_cth_llm`` (``lam = 0``) make their own
  module 02 calls through the shared metered client, so their first prompt of an episode is the
  same text as arms 8 and 10 and is served from the cache;
* ``ctrl_cth_uniform`` (``lam = 1``) is the content-free control: the same trigger and machinery,
  no model call.
"""

from __future__ import annotations

import analysis.real_content_pilot.runner as rcp
from analysis.commitment.cth import CertifyThenHedgeArm
from analysis.commitment.registry import ARM_SETS, register_arm_set
from collie.trigger.demo import build_wrapped
from tools.run_arms import spec_adapters

CTH_ARMS = (("arm12_cth", 0.25), ("arm12b_cth_llm", 0.0), ("ctrl_cth_uniform", 1.0))
DROPPED = ("arm9_spec_heuristic_rollback",)
NINE = ARM_SETS["nine"]
"""The nine-arm builder itself: the runner swaps ``rcp.build_arms`` while a run is in progress."""


def build_confirm_arms(instance, seed, *, metered, ledger, sink):
    arms = [
        a
        for a in NINE(instance, seed, metered=metered, ledger=ledger, sink=sink)
        if a[0] not in DROPPED
    ]
    spec = instance.spec
    for arm_id, lam in CTH_ARMS:
        kwargs = {}
        if lam < 1.0:
            prompter, parser = spec_adapters()
            channel = metered.channel(arm_id=arm_id, episode_id=spec.episode_id)
            kwargs = {
                "channel": channel,
                "prompter": prompter,
                "parser": rcp.RecordingParser(parser, channel, ledger, sink, rule_u_horizon=None),
            }
        arms.append(
            (
                arm_id,
                CertifyThenHedgeArm(
                    lam=lam,
                    promised_lead_time=spec.promised_lead_time,
                    horizon=spec.horizon,
                    train_demand=spec.train_demand,
                    order_cap=spec.order_cap,
                    trigger=build_wrapped("alert_or_detector", spec.horizon, 0, seed),
                    arm_id=arm_id,
                    **kwargs,
                ),
                True,
            )
        )
    return arms


register_arm_set("confirm", build_confirm_arms)
