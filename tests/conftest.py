"""Shared command-line options for checkpoint calibration tests."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--replications",
        action="store",
        default=200,
        type=int,
        help="Monte Carlo replication count for verifier calibration tests",
    )
