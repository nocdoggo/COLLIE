"""Task 6.3 / Task 8 — build COLLIE-ShockSpec instance directories and the manifest.

Wave 3 scope: ``--split dev --limit N`` writes instance pairs (shocked + twin) for the
implemented families in a fixed round-robin order. The seed registry is provisional until
wave 5 lands ``collie/data/splits.py``; the scheme below is the one the registry will adopt,
so nothing regenerates differently when it does:

    seed(family, split, i) = family * 1_000_000 + SPLIT_BASE[split] + i

Promised lead time: generated paths carry no ``lead_time_*`` component, so the frozen loader
cannot derive one from the path. The manifest records ``promised_lead_time`` per rollout (the
twin's constant baseline lead time; research notes §6) and consumers pass it explicitly.

Usage::

    uv run python -m tools.build_shockspec --split dev --limit 18 --out /tmp/shockspec_dev
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path

from collie.data.families import generate_episode
from collie.data.families.base import FamilyParams, GeneratedEpisode
from collie.data.writer import TWIN_SUFFIX, write_pair

REPO_ROOT = Path(__file__).resolve().parents[1]
HORIZON = 50  # official synthetic horizon (docs/env_contract.md §1)

SPLIT_BASE = {"test": 0, "dev": 50_000, "cal": 60_000}
IMPLEMENTED_FAMILIES = (1, 2, 3, 4, 5, 6)
PROVISIONAL_SEEDS_PER_FAMILY = 6  # the dev pool size the registry will freeze


def seed_for(family: int, split: str, index: int) -> int:
    return family * 1_000_000 + SPLIT_BASE[split] + index


def dev_episodes(limit: int) -> Iterator[tuple[int, int, int]]:
    """Yield ``(family, seed_index, seed)`` seed-index-major so every family is covered before
    any family repeats: a limit cuts seeds, never families."""
    emitted = 0
    for index in range(PROVISIONAL_SEEDS_PER_FAMILY):
        for family in IMPLEMENTED_FAMILIES:
            if emitted >= limit:
                return
            yield family, index, seed_for(family, "dev", index)
            emitted += 1


def render_comparison(ep: GeneratedEpisode) -> str:
    """Side-by-side of the shocked series against its twin with the onset marked, so the auditor
    can see the pre-onset paths coincide."""
    onset = ep.incident.onset_period
    lines = [
        f"family={ep.incident.family} onset={onset} magnitude={ep.incident.magnitude} "
        f"duration={ep.incident.duration} seed={ep.incident.seed}",
        f"{'period':>6} {'twin':>8} {'shocked':>8}  note",
    ]
    for t in range(1, len(ep.demand) + 1):
        twin, shocked = ep.twin_demand[t - 1], ep.demand[t - 1]
        note = ""
        if t == onset:
            note = "<- onset"
        elif t > onset and twin != shocked:
            note = "*"
        lines.append(f"{t:>6} {twin:>8.0f} {shocked:>8.0f}  {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["dev"], required=True, help="only dev exists so far")
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--show",
        action="store_true",
        help="print the first episode's shocked series against its twin with the onset marked",
    )
    args = ap.parse_args(argv)

    written: list[tuple[str, GeneratedEpisode]] = []
    for family, _index, seed in dev_episodes(args.limit):
        ep = generate_episode(seed=seed, horizon=HORIZON, params=FamilyParams(family))
        relpath = f"{args.split}/f{family}/s{seed}"
        write_pair(args.out, ep, relpath=relpath)
        written.append((relpath, ep))

    per_family: dict[int, int] = {}
    for _, ep in written:
        per_family[ep.incident.family.value] = per_family.get(ep.incident.family.value, 0) + 1
    print(f"wrote {len(written)} shocked episodes (+ twins) under {args.out}")
    for name, count in sorted(per_family.items()):
        print(f"  {name}: {count}")
    if args.show and written:
        relpath, ep = written[0]
        print(f"\n{relpath} (twin at {relpath}{TWIN_SUFFIX}):")
        print(render_comparison(ep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
