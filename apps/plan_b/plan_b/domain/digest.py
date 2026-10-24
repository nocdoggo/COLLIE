"""The one canonical request digest convention.

``sha256(UTF-8 JSON with sorted keys, compact separators, non-ASCII preserved)``. This is the
convention used by the planning examples: applied to
``PEEAI_plan/examples/commit_request.json`` it yields the ``request_digest`` recorded in
``commit_receipt.json``. ``tests/test_contracts.py`` checks that equality.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_digest(body: dict[str, Any]) -> str:
    """Digest of a mutation request body exactly as validated (``model_dump(mode='json')``)."""
    return sha256_hex(canonical_json(body))


def file_sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()
