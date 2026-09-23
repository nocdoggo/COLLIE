"""JSONL storage for evaluation records.

The evaluator consumes :class:`collie.contracts.EpisodeResult` objects, but module 06 needs a
plain file contract it can write after a run.  JSONL keeps that boundary simple: one episode
result per line, with every reported number still traceable to stored period records and call
logs.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from collie.contracts import (
    AnalysisClass,
    CallLog,
    ControlConfig,
    EpisodeResult,
    InformationCondition,
    LifecycleState,
    ParseOutcome,
    RunRecord,
    ShockFamily,
    ShockSpec,
    Split,
)

__all__ = [
    "RECORD_SCHEMA_VERSION",
    "episode_result_from_dict",
    "episode_result_to_dict",
    "load_episode_results_jsonl",
    "write_episode_results_jsonl",
]

RECORD_SCHEMA_VERSION = 1


def _enum_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _enum_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple | list):
        return [_enum_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _enum_value(item) for key, item in value.items()}
    return value


def episode_result_to_dict(result: EpisodeResult) -> dict[str, Any]:
    """Convert an episode result to a stable JSON-compatible mapping."""
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "type": "EpisodeResult",
        "episode_id": result.episode_id,
        "arm_id": result.arm_id,
        "total_profit": result.total_profit,
        "total_holding_cost": result.total_holding_cost,
        "total_reward": result.total_reward,
        "total_demand": result.total_demand,
        "total_sold": result.total_sold,
        "total_lost_sales": result.total_lost_sales,
        "perfect_foresight": result.perfect_foresight,
        "normalized_reward": result.normalized_reward,
        "records": [_enum_value(record) for record in result.records],
        "calls": [_enum_value(call) for call in result.calls],
        "independent_unit_id": result.independent_unit_id,
        "split": _enum_value(result.split),
        "family": _enum_value(result.family),
        "information_condition": _enum_value(result.information_condition),
        "analysis_class": result.analysis_class.value,
    }


def _optional_enum(enum_type: type[StrEnum], value: str | None) -> StrEnum | None:
    return None if value is None else enum_type(value)


def _control_config(data: Mapping[str, Any] | None) -> ControlConfig | None:
    if data is None:
        return None
    return ControlConfig(
        m=float(data["m"]),
        l_eff=int(data["l_eff"]),
        gamma=float(data["gamma"]),
        predictive_model=str(data["predictive_model"]),
    )


def _run_record(data: Mapping[str, Any]) -> RunRecord:
    active_spec = data.get("active_spec")
    return RunRecord(
        episode_id=str(data["episode_id"]),
        arm_id=str(data["arm_id"]),
        period=int(data["period"]),
        date=str(data["date"]),
        on_hand_start=float(data["on_hand_start"]),
        in_transit_start=float(data["in_transit_start"]),
        order_quantity=float(data["order_quantity"]),
        arrivals=float(data["arrivals"]),
        demand=float(data["demand"]),
        units_sold=float(data["units_sold"]),
        lost_sales=float(data["lost_sales"]),
        on_hand_end=float(data["on_hand_end"]),
        period_profit=float(data["period_profit"]),
        period_holding=float(data["period_holding"]),
        triggered=bool(data.get("triggered", False)),
        llm_called=bool(data.get("llm_called", False)),
        lifecycle_state=_optional_enum(LifecycleState, data.get("lifecycle_state")),
        active_spec_id=data.get("active_spec_id"),
        active_spec=None if active_spec is None else ShockSpec.model_validate(active_spec),
        control_config=_control_config(data.get("control_config")),
        template_id=data.get("template_id"),
    )


def _call_log(data: Mapping[str, Any]) -> CallLog:
    outcome = data.get("outcome")
    return CallLog(
        call_id=str(data["call_id"]),
        arm_id=str(data["arm_id"]),
        episode_id=str(data["episode_id"]),
        period=int(data["period"]),
        model_id=str(data["model_id"]),
        prompt_hash=str(data["prompt_hash"]),
        decoding_hash=str(data["decoding_hash"]),
        attempt_index=int(data["attempt_index"]),
        outcome=None if outcome is None else ParseOutcome(outcome),
        input_tokens=int(data.get("input_tokens", 0)),
        output_tokens=int(data.get("output_tokens", 0)),
        latency_ms=float(data.get("latency_ms", 0.0)),
        usd_cost=float(data.get("usd_cost", 0.0)),
        cache_hit=bool(data.get("cache_hit", False)),
        physical=bool(data.get("physical", True)),
    )


def episode_result_from_dict(data: Mapping[str, Any]) -> EpisodeResult:
    """Rehydrate an episode result from the JSONL representation."""
    if data.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise ValueError(f"unsupported record schema_version: {data.get('schema_version')!r}")
    if data.get("type") != "EpisodeResult":
        raise ValueError(f"unsupported record type: {data.get('type')!r}")
    return EpisodeResult(
        episode_id=str(data["episode_id"]),
        arm_id=str(data["arm_id"]),
        total_profit=float(data["total_profit"]),
        total_holding_cost=float(data["total_holding_cost"]),
        total_reward=float(data["total_reward"]),
        total_demand=float(data["total_demand"]),
        total_sold=float(data["total_sold"]),
        total_lost_sales=float(data["total_lost_sales"]),
        perfect_foresight=float(data["perfect_foresight"]),
        normalized_reward=float(data["normalized_reward"]),
        records=tuple(_run_record(record) for record in data.get("records", [])),
        calls=tuple(_call_log(call) for call in data.get("calls", [])),
        independent_unit_id=data.get("independent_unit_id"),
        split=_optional_enum(Split, data.get("split")),
        family=_optional_enum(ShockFamily, data.get("family")),
        information_condition=_optional_enum(
            InformationCondition, data.get("information_condition")
        ),
        analysis_class=AnalysisClass(data.get("analysis_class", AnalysisClass.EXPLORATORY.value)),
    )


def write_episode_results_jsonl(path: Path, results: Sequence[EpisodeResult]) -> None:
    """Write one episode result per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for result in results:
            payload = episode_result_to_dict(result)
            fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def load_episode_results_jsonl(path: Path) -> tuple[EpisodeResult, ...]:
    """Load all episode results from a JSONL record file."""
    results: list[EpisodeResult] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(payload, Mapping):
                raise ValueError(f"{path}:{line_no}: record must be a JSON object")
            results.append(episode_result_from_dict(payload))
    return tuple(results)
