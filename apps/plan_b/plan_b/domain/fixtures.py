"""Public fixture loading. Private runner cases are loaded only by ``plan_b.world``."""

from __future__ import annotations

from pathlib import Path

from plan_b.domain.digest import file_sha256
from plan_b.domain.models import PublicScenario

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"
PUBLIC_DIR = SCENARIO_DIR / "public"

# scenario_id -> public fixture file. The profile, not the file, selects the domain adapter
# (registry.adapter_for): the campus showcase and the skills exchange share the campus
# adapter; Pantry Continuity (W2.3) has its own.
PUBLIC_SCENARIOS = {
    "dev_fixture_01": "campus_showcase.json",
    "dev_fixture_02": "community_skills_exchange.json",
    "dev_fixture_03": "pantry_continuity.json",
}


def public_scenario_path(scenario_id: str) -> Path:
    try:
        return PUBLIC_DIR / PUBLIC_SCENARIOS[scenario_id]
    except KeyError as exc:
        raise KeyError(f"unknown public scenario {scenario_id!r}") from exc


def load_public_scenario(scenario_id: str = "dev_fixture_01") -> PublicScenario:
    return PublicScenario.model_validate_json(public_scenario_path(scenario_id).read_text())


def public_scenario_sha256(scenario_id: str = "dev_fixture_01") -> str:
    return file_sha256(str(public_scenario_path(scenario_id)))
