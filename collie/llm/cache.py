"""Disk cache for LLM calls, keyed by model, full prompt hash, state, and decoding hash.

The key embeds a SHA-256 over the **full** prompt text (and the system message when present) —
never a truncation or a summary. A key that omitted part of the prompt would make a warm replay
return the wrong response and corrupt a rerun silently; that is the one failure mode this module
exists to make impossible (design.md, risks).

Files are content-addressed (``<root>/<hex[:2]>/<hex>.json``), written atomically (tmp +
``os.replace``), with ``sort_keys=True`` and a trailing newline, so a regenerated cache file is
byte-identical — the same discipline as the manifests.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # duck-typed at runtime; imported only for annotations
    from collie.llm.client import RawResponse

__all__ = ["DiskCache", "cache_key"]


def cache_key(
    *,
    model_id: str,
    prompt: str,
    state: str,
    decoding_hash: str,
    system: str | None = None,
) -> str:
    """The cache key: SHA-256 over a canonical envelope of every component.

    The full prompt and system text are hashed, so any change to any character of any component
    changes the key. Returns ``sha256:<hexdigest>``.
    """
    envelope = json.dumps(
        {
            "decoding_hash": decoding_hash,
            "model_id": model_id,
            "prompt": prompt,
            "state": state,
            "system": system,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(envelope.encode("utf-8")).hexdigest()


class DiskCache:
    """A content-addressed store of raw responses. Create the root on first write."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, key: str) -> Path:
        hexpart = key.removeprefix("sha256:")
        return self._root / hexpart[:2] / f"{hexpart}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """The stored payload (text plus raw token counts), or ``None`` on a miss."""
        path = self._path(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def put(self, key: str, raw: RawResponse) -> None:
        """Store a response atomically. Re-putting an identical payload is a no-op write."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "completion_tokens": raw.completion_tokens,
                    "prompt_tokens": raw.prompt_tokens,
                    "text": raw.text,
                    "total_tokens": raw.total_tokens,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def __len__(self) -> int:
        if not self._root.is_dir():
            return 0
        return sum(1 for p in self._root.rglob("*.json") if p.is_file())
