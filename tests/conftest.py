"""Shared command-line options for checkpoint calibration tests."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--replications",
        action="store",
        default=2000,
        type=int,
        help="Monte Carlo replication count (CP2 default: 2,000 per registered null)",
    )
