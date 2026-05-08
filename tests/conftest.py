"""Shared pytest config: register markers and skip network tests by default."""

from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "network: opt-in tests that hit external services. Skipped unless --run-network.",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Also run tests marked with @pytest.mark.network.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip_network = pytest.mark.skip(reason="network test (use --run-network to enable)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
