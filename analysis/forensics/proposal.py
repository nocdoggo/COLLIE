"""Sizing for the proposed real-content exploratory pilot (Q4). Exploratory; nothing is run.

Run: ``uv run python -m analysis.forensics.proposal`` (writes ``out/proposal.json``).

Reads the stored call ledger (every ``calls`` entry in ``reports/pilot_records.jsonl``) and
prices the calls each LLM arm would make at each registered endpoint's dated list prices.

* Under scripted transport the *prompts* are the real module-02 / arm prompts, so the recorded
  input-token counts (``len(prompt) // 4 + 1``) are a usable size estimate. The output-token
  counts are the length of the scripted JSON answer, only a floor for a real model, so every
  cost is also shown with fixed output multipliers (longer answers, billed thinking tokens).
* The stored records carry the ledger's *charged* entries (``tools/run_arms.py::_attach_calls``),
  whose ``physical`` flag is False throughout, so the physical volume of the shared arm 8/9/10
  proposal call is bracketed instead: distinct prompt hashes (the cache serves repeats; a lower
  bound, since real content moves trajectories apart) and charged calls (every copy physical;
  an upper bound), plus the upper bound with one repair attempt per call.

Constructing an ``EndpointConfig`` reads no credential: keys are resolved only by
``EndpointConfig.resolve_key``, which this module never calls.
"""

from __future__ import annotations

import json
from collections import Counter

import numpy as np

from analysis.forensics.common import ARM8, ARM9, ARM10, load_raw, write_json
from collie.llm.client import gemini_primary, grok_hosted_confirmation, zai_endpoint

PROPOSAL_ARMS = (ARM8, ARM9, ARM10)
OUTPUT_MULTIPLIERS = (1.0, 5.0, 20.0)
"""Output-token cases for a real model: the scripted JSON size, and two fixed allowances for
longer answers and billed thinking tokens (Gemini bills thinking as output)."""


def _endpoints() -> dict:
    return {
        "gemini_primary": gemini_primary(),
        "grok_confirmation": grok_hosted_confirmation(),
        "zai_optional": zai_endpoint(),
    }


def _usd(n_calls: int, mean_in: float, mean_out: float, endpoint, multiplier: float) -> float:
    per_call = (
        mean_in * endpoint.price_input_per_mtok
        + mean_out * multiplier * endpoint.price_output_per_mtok
    )
    return n_calls * per_call / 1e6


def _priced(n_calls: int, mean_in: float, mean_out: float) -> dict:
    return {
        name: {
            f"output_x{m:g}": _usd(n_calls, mean_in, mean_out, ep, m) for m in OUTPUT_MULTIPLIERS
        }
        for name, ep in _endpoints().items()
    }


def main() -> None:
    raw = load_raw()
    calls = [c for r in raw for c in r["calls"]]
    per_arm = {}
    for arm in sorted({c["arm_id"] for c in calls}):
        cs = [c for c in calls if c["arm_id"] == arm]
        mean_in = float(np.mean([c["input_tokens"] for c in cs]))
        mean_out = float(np.mean([c["output_tokens"] for c in cs]))
        per_arm[arm] = {
            "charged_calls": len(cs),
            "physical_flag_true": sum(1 for c in cs if c["physical"]),
            "distinct_prompts": len({c["prompt_hash"] for c in cs}),
            "episodes_with_calls": len({c["episode_id"] for c in cs}),
            "mean_input_tokens": mean_in,
            "mean_output_tokens_scripted": mean_out,
            "attempt_indices": dict(Counter(str(c["attempt_index"]) for c in cs)),
            "usd_if_every_charged_call_physical": _priced(len(cs), mean_in, mean_out),
        }
    shockspec = [c for c in calls if c["arm_id"] in PROPOSAL_ARMS]
    mean_in = float(np.mean([c["input_tokens"] for c in shockspec]))
    mean_out = float(np.mean([c["output_tokens"] for c in shockspec]))
    volumes = {
        "lower_distinct_prompts": len({c["prompt_hash"] for c in shockspec}),
        "upper_all_charged_physical": len(shockspec),
        "upper_with_one_repair_each": 2 * len(shockspec),
    }
    out = {
        "per_arm_ledger": per_arm,
        "shared_proposal_call_arms_8_9_10": {
            "arms": list(PROPOSAL_ARMS),
            "episodes_with_a_proposal": len({c["episode_id"] for c in shockspec}),
            "mean_input_tokens": mean_in,
            "mean_output_tokens_scripted": mean_out,
            "volumes": volumes,
            "usd": {v: _priced(n, mean_in, mean_out) for v, n in volumes.items()},
        },
        "endpoints": {
            name: {
                "model_id": ep.model_id,
                "price_date": ep.price_date,
                "price_input_per_mtok": ep.price_input_per_mtok,
                "price_output_per_mtok": ep.price_output_per_mtok,
                "supports_seed": ep.supports_seed,
            }
            for name, ep in _endpoints().items()
        },
    }
    path = write_json("proposal.json", out)
    print(json.dumps(out["shared_proposal_call_arms_8_9_10"], indent=2, default=float))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
