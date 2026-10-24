"""Non-secret model endpoint configuration for the live agent.

Each ``PLAN_B_MODEL_*`` setting comes from the process environment when set there, else from
the local endpoint file ``.local/keys/model_endpoint.env``, else from its default. Only the six
names below are read from that file. Relative paths resolve against the repository root.

The key file is named here but never read here: ``provider`` reads it per call, server-side,
and sends it only in the ``Authorization`` header. ``ModelConfig.public()`` is the form that
may appear in records: it carries no key and no absolute local path.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_DIR.parents[1]
ENDPOINT_FILE = Path(".local/keys/model_endpoint.env")
DEFAULT_LEDGER = APP_DIR / "var" / "model_spend.json"

ENV_NAMES = (
    "PLAN_B_MODEL_PROVIDER",
    "PLAN_B_MODEL_BASE_URL",
    "PLAN_B_MODEL_KEY_FILE",
    "PLAN_B_MODEL_ID",
    "PLAN_B_MODEL_MAX_RUN_COST_USD",
    "PLAN_B_MODEL_MAX_TOTAL_COST_USD",
)
DEFAULT_MODEL_ID = "anthropic/claude-sonnet-5.5"
DEFAULT_MAX_RUN_COST_USD = 0.50
DEFAULT_MAX_TOTAL_COST_USD = 20.00
PROVIDERS = ("openrouter", "openai_compatible")
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

Source = Literal["environment", "endpoint_file", "default"]


class ModelConfigError(ValueError):
    """The configuration is missing or invalid. Messages never contain a key value."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str
    key_file: Path  # absolute; read per call by the provider only
    model_id: str
    max_run_cost_usd: float
    max_total_cost_usd: float
    ledger_path: Path
    repo_root: Path
    sources: Mapping[str, Source]

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def public(self) -> dict[str, Any]:
        """Configuration without secrets or absolute local paths."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "key_file": _display_path(self.key_file, self.repo_root),
            "key_file_present": self.key_file.is_file(),
            "model_id": self.model_id,
            "max_run_cost_usd": self.max_run_cost_usd,
            "max_total_cost_usd": self.max_total_cost_usd,
            "ledger": _display_path(self.ledger_path, self.repo_root),
            "sources": dict(self.sources),
        }


def read_endpoint_file(path: Path) -> dict[str, str]:
    """``NAME=value`` lines of the endpoint file (comments and unknown names ignored)."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if name in ENV_NAMES:
            values[name] = value.strip().strip("'\"")
    return values


def load_model_config(
    env: Mapping[str, str] | None = None,
    *,
    repo_root: Path | None = None,
    endpoint_file: Path | None = None,
    ledger_path: Path | None = None,
) -> ModelConfig:
    """Resolve the configuration (environment, then endpoint file, then defaults)."""
    environ = os.environ if env is None else env
    root = (repo_root or REPO_ROOT).resolve()
    file_values = read_endpoint_file(_resolve(endpoint_file or ENDPOINT_FILE, root))
    values: dict[str, str] = {}
    sources: dict[str, Source] = {}
    for name in ENV_NAMES:
        if environ.get(name, "").strip():
            values[name], sources[name] = environ[name].strip(), "environment"
        elif file_values.get(name, ""):
            values[name], sources[name] = file_values[name], "endpoint_file"
    for name, default in (
        ("PLAN_B_MODEL_ID", DEFAULT_MODEL_ID),
        ("PLAN_B_MODEL_MAX_RUN_COST_USD", str(DEFAULT_MAX_RUN_COST_USD)),
        ("PLAN_B_MODEL_MAX_TOTAL_COST_USD", str(DEFAULT_MAX_TOTAL_COST_USD)),
    ):
        if name not in values:
            values[name], sources[name] = default, "default"
    missing = [
        n
        for n in ("PLAN_B_MODEL_PROVIDER", "PLAN_B_MODEL_BASE_URL", "PLAN_B_MODEL_KEY_FILE")
        if n not in values
    ]
    if missing:
        raise ModelConfigError(f"not configured: {', '.join(missing)}")
    provider = values["PLAN_B_MODEL_PROVIDER"]
    if provider not in PROVIDERS:
        raise ModelConfigError(f"PLAN_B_MODEL_PROVIDER must be one of {', '.join(PROVIDERS)}")
    base_url = _check_base_url(values["PLAN_B_MODEL_BASE_URL"])
    model_id = values["PLAN_B_MODEL_ID"]
    if not model_id or any(c.isspace() for c in model_id) or len(model_id) > 200:
        raise ModelConfigError("PLAN_B_MODEL_ID must be a non-empty identifier without spaces")
    run_cap = _cost(values, "PLAN_B_MODEL_MAX_RUN_COST_USD")
    total_cap = _cost(values, "PLAN_B_MODEL_MAX_TOTAL_COST_USD")
    if run_cap > total_cap:
        raise ModelConfigError("the per-run cost cap exceeds the cumulative cap")
    return ModelConfig(
        provider=provider,
        base_url=base_url,
        key_file=_resolve(Path(values["PLAN_B_MODEL_KEY_FILE"]), root),
        model_id=model_id,
        max_run_cost_usd=run_cap,
        max_total_cost_usd=total_cap,
        ledger_path=(ledger_path or DEFAULT_LEDGER).resolve(),
        repo_root=root,
        sources=sources,
    )


def _resolve(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else (root / path).resolve()


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return f"<outside the repository>/{path.name}"


def _check_base_url(url: str) -> str:
    """HTTPS only, except plain HTTP to this machine (local test servers). No credentials,
    query or fragment in the URL."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("https", "http") or not host:
        raise ModelConfigError("PLAN_B_MODEL_BASE_URL must be an absolute https URL")
    if parts.scheme == "http" and host not in LOCAL_HOSTS:
        raise ModelConfigError("PLAN_B_MODEL_BASE_URL must use https (http only for 127.0.0.1)")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ModelConfigError("PLAN_B_MODEL_BASE_URL must not carry credentials or a query")
    return url.rstrip("/")


def _cost(values: Mapping[str, str], name: str) -> float:
    try:
        value = float(values[name])
    except ValueError:
        raise ModelConfigError(f"{name} must be a number of US dollars") from None
    if not math.isfinite(value) or value <= 0:
        raise ModelConfigError(f"{name} must be a positive number of US dollars")
    return value
