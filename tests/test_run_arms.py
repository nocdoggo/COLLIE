"""tools/run_arms.py — the demo's argument guards and a small end-to-end smoke."""

from __future__ import annotations

import pytest

from collie.contracts import Split
from collie.data.splits import FAMILIES, build_units
from tools.run_arms import dev_instances, main


def _pool_size() -> int:
    units = build_units(Split.DEV)
    return min(len([u for u in units if u.family == f]) for f in FAMILIES) * len(FAMILIES)


def test_episodes_above_the_dev_pool_fails_loudly(tmp_path) -> None:
    """The CP2-audit finding: an unguarded IndexError above the pool, now a named bound."""
    pool = _pool_size()
    with pytest.raises(ValueError, match=f"exceeds the dev episode pool of {pool}"):
        dev_instances(tmp_path, pool + len(FAMILIES))


def test_episodes_must_be_a_multiple_of_six(tmp_path) -> None:
    with pytest.raises(ValueError, match="positive multiple of 6"):
        dev_instances(tmp_path, 7)


def test_demo_smoke_six_episodes(capsys) -> None:
    """One cycle of six: the ladder runs, the table prints, the ledger balances."""
    rc = main(["--split", "dev", "--episodes", "6", "--table"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "arm1_capped_base_stock" in out
    assert "oracle_shockspec_headroom" in out
    assert "conserved" in out
