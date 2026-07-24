"""Pytest bootstrap for the release-pipeline tests.

Adds ``02_atlas/workers/release`` to ``sys.path`` so the tests import
``sy_scrub`` / ``sy_leak_gate`` / ``sy_extract`` directly, and exposes the repo
layout plus the real (gitignored) denylist as a fixture.

This file carries NO real monolith token. The neutral config used by the mutation
tests lives next to them in ``test_scrub_mutation.py`` for the same reason: a
committed test must not name a real tenant/path/schema.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# tests/ -> 00_ourobouros -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = _REPO_ROOT / "02_atlas" / "workers" / "release"
for _p in (_RELEASE, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sy_scrub  # noqa: E402  (also validates the import at collection time)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _REPO_ROOT


@pytest.fixture(scope="session")
def release_dir() -> Path:
    return _RELEASE


@pytest.fixture(scope="session")
def real_denylist() -> list[str]:
    """The gitignored real denylist if present, else the shipped ``.example``.

    Iterated (never hardcoded) by the integration test so that no real codename
    is ever written into a committed source file.
    """
    path = sy_scrub.resolve_denylist_path(_RELEASE / "sy_codename_denylist.txt")
    return sy_scrub.load_denylist(path)


@pytest.fixture(scope="session")
def real_private_config() -> dict:
    """The gitignored real private release config if present, else the shipped
    ``.example.json`` — mirrors real_denylist. Read as a dict (never a hardcoded
    literal here), used by the integration test to prove path/schema/SQL-message
    scrubbing end-to-end without naming Alex's monolith in this committed file.
    """
    path = sy_scrub.resolve_private_config_path(_RELEASE / "sy_private_config.json")
    return sy_scrub.load_private_config(path)


@pytest.fixture
def monolith_root():
    """The private source tree.

    Skipped when ``SY_SRC_ROOT`` is unset: external contributors do not have the
    monolith, so the mutation layer (which is the actual regression gate) runs
    everywhere while the integration layer only runs in-house.
    """
    root = os.environ.get("SY_SRC_ROOT")
    if not root:
        pytest.skip("SY_SRC_ROOT unset — integration test needs the monolith")
    return Path(root)
