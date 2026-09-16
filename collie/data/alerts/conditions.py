"""Analysis-side paired messages; only AlertMessage crosses the policy boundary.

A trajectory is supplied once, never generated separately for each condition. Manifest
identity and template bindings are explicit, so fake-backed development needs no generator.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from collie.contracts import (
    AlertKind,
    AlertMessage,
    Direction,
    HiddenAlertSpec,
    InformationCondition,
    Split,
)
from collie.data.alerts.bank import AlertTemplate, draw_slots, render_alert


@dataclass(frozen=True, slots=True)
class ExogenousDraws:
    demand: tuple[float, ...]
    lead_times: tuple[float, ...]
    pause_active: tuple[bool, ...]
    onset: int
    slot_draws: tuple[tuple[str, str], ...]

    def __post_init__(self):
        # 外生轨迹使用不可变元组, 防止某个条件修改共享轨迹后破坏配对关系。
        if not isinstance(self.demand, tuple) or not isinstance(self.lead_times, tuple):
            raise ValueError("draws must be immutable tuples")
        if not self.demand or len(self.demand) != len(self.lead_times):
            raise ValueError("demand and lead times must align")
        if not isinstance(self.pause_active, tuple) or len(self.pause_active) != len(self.demand):
            raise ValueError("pause path must align")
        if not isinstance(self.slot_draws, tuple) or any(
            not isinstance(row, tuple) or len(row) != 2 or any(not isinstance(v, str) for v in row)
            for row in self.slot_draws
        ):
            raise ValueError("slot draws must be immutable string pairs")
        if type(self.onset) is not int or not 1 <= self.onset <= len(self.demand):
            raise ValueError("onset outside trajectory")
        if any(not math.isfinite(v) or v < 0 for v in self.demand):
            raise ValueError("demand must be finite and nonnegative")
        if any(math.isnan(v) or v < 0 for v in self.lead_times):
            raise ValueError("invalid lead time")
        if any(type(v) is not bool for v in self.pause_active):
            raise ValueError("pause values must be booleans")

    @property
    def losses(self):
        # 沿用模拟器语义: 实际提前期为正无穷表示该批货物丢失。
        return tuple(math.isinf(v) for v in self.lead_times)

    def fingerprint_bytes(self):
        """IEEE bytes detect changes even where float equality hides signed zero."""
        # 比较浮点数原始字节而非近似数值; 连正负零的差异也能被配对检查发现。
        return (
            struct.pack(f"!{len(self.demand)}d", *self.demand)
            + struct.pack(f"!{len(self.lead_times)}d", *self.lead_times)
            + bytes(self.pause_active)
            + struct.pack("!q", self.onset)
            + json.dumps(self.slot_draws, ensure_ascii=False).encode()
        )


@dataclass(frozen=True, slots=True)
class ConditionRollout:
    independent_unit_id: str
    seed: int
    condition: InformationCondition
    exogenous: ExogenousDraws
    message: AlertMessage | None
    template_id: str | None
    alert_spec: HiddenAlertSpec | None
    manifest_template_slot: str | None

    def runner_alerts(self):
        """Return the runner's two separate maps, excluding hidden truth."""
        # 消息和模板 ID 分两条通道: 策略只看 AlertMessage, 模板 ID 仅供记录与语言分析。
        if self.message is None:
            return {}, {}
        return {self.message.period: self.message}, {self.message.period: self.template_id}


def manifest_unit(manifest, unit_id):
    # 四种条件必须回到同一个 seed; 否则评估会把配对重放误算成四个独立样本。
    rows = [r for r in manifest["rollouts"] if r["independent_unit_id"] == unit_id]
    if not rows:
        raise ValueError(f"unknown independent unit: {unit_id}")
    for key in ("seed", "split", "shock_family", "onset"):
        if len({r[key] for r in rows}) != 1:
            raise ValueError(f"unit does not resolve to one {key}")
    conditions = [r["information_condition"] for r in rows]
    if len(conditions) != 4 or set(conditions) != {c.value for c in InformationCondition}:
        raise ValueError("unit must have exactly four manifest conditions")
    alert_rows = [r for r in rows if r["information_condition"] != "no_alert"]
    if len({r["template_id"] for r in alert_rows}) != 1 or not alert_rows[0]["template_id"]:
        raise ValueError("alert conditions must resolve to one manifest template slot")
    return alert_rows[0]


def render_conditions(
    *,
    manifest: dict,
    independent_unit_id: str,
    demand: tuple[float, ...],
    lead_times: tuple[float, ...],
    pause_active: tuple[bool, ...],
    onset: int,
    accurate: AlertTemplate,
    unreliable: AlertTemplate,
    unreliable_offset: int = -1,
):
    # 先校验 manifest 与模板绑定, 再复用同一条轨迹; 这里只改变消息及发送时间, 不重新抽取需求或供给。
    row = manifest_unit(manifest, independent_unit_id)
    if row["onset"] != onset or len(demand) != manifest["horizon"]:
        raise ValueError("trajectory onset/horizon disagrees with manifest")
    if accurate.kind is not AlertKind.ACCURATE:
        raise ValueError("accurate condition requires an accurate template")
    if unreliable.kind not in {AlertKind.OVERSTATED, AlertKind.AMBIGUOUS, AlertKind.DISTRACTOR}:
        raise ValueError("unreliable condition requires overstated/ambiguous/distractor")
    for template in (accurate, unreliable):
        if template.split != Split(row["split"]) or template.family.value != row["shock_family"]:
            raise ValueError("template split/family disagrees with manifest")
    if row["shock_family"] == "demand_level" and row.get("magnitude") is not None:
        expected_direction = Direction.DEMAND_UP if row["magnitude"] > 1 else Direction.DEMAND_DOWN
        if accurate.alert_spec.direction != expected_direction:
            raise ValueError("accurate template direction disagrees with manifest magnitude")
    if type(unreliable_offset) is not int:
        raise ValueError("unreliable offset must be an integer")
    seed = row["seed"]
    rendered = {t.template_id: render_alert(t, seed) for t in (accurate, unreliable)}
    # Precompute both candidate renderings once; no condition-specific slot RNG exists.
    draws = ExogenousDraws(
        demand,
        lead_times,
        pause_active,
        onset,
        tuple(
            (f"{t.template_id}:{key}", value)
            for t in (accurate, unreliable)
            for key, value in draw_slots(t, seed)
        ),
    )
    schedule = (
        (InformationCondition.NO_ALERT, None, None),
        (InformationCondition.EARLY_ACCURATE, accurate, onset - 1),
        (InformationCondition.LATE_ACCURATE, accurate, onset + 2),
        (InformationCondition.UNRELIABLE, unreliable, onset + unreliable_offset),
    )
    result = []
    for condition, template, period in schedule:
        if period is not None and not 1 <= period <= len(demand):
            raise ValueError("alert timestamp outside horizon; refusing to clip pairing")
        message = (
            AlertMessage("operational-alert", period, rendered[template.template_id].text)
            if template
            else None
        )
        result.append(
            ConditionRollout(
                independent_unit_id,
                seed,
                condition,
                draws,
                message,
                template.template_id if template else None,
                template.alert_spec if template else None,
                row["template_id"] if template else None,
            )
        )
    return tuple(result)


def load_manifest(path):
    return json.loads(Path(path).read_text())


def render_condition_batch(requests):
    """Validate the finite allocation before treating texts as independent stimuli."""
    # 单次渲染只能保证一个 unit 的配对; 批量分配还要检查不同 unit 是否重复使用了同一段文本。
    from collie.data.alerts.bank import RenderedAlert, validate_rollout_renderings

    requests = tuple(requests)
    result = tuple(render_conditions(**request) for request in requests)
    rows = []
    for request, rollouts in zip(requests, result, strict=True):
        templates = {t.template_id: t for t in (request["accurate"], request["unreliable"])}
        for rollout in rollouts:
            if rollout.message is not None:
                template = templates[rollout.template_id]
                rows.append(
                    (
                        rollout.independent_unit_id,
                        RenderedAlert(
                            template.template_id,
                            template.split,
                            template.wording_family,
                            rollout.message.text,
                            template.alert_spec,
                        ),
                    )
                )
    validate_rollout_renderings(rows)
    return result
