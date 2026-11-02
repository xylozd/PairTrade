"""Requirements pin drift guard.

`backend/requirements.txt` is the declaration of what the backend depends on.
The installed virtualenv is what actually runs. If they disagree, the code
"works on my machine" and breaks on the VPS. This test pins the two together.
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
PYTEST_INI = REPO_ROOT / "pytest.ini"

# Every package the backend depends on, grouped by the stack it serves.
# Mirrors docs/STRATEGY.md §10 (verified stack versions).
EXPECTED_PACKAGES: dict[str, str] = {
    # Web / API
    "fastapi": "0.159.1",
    "uvicorn": "0.54.0",
    "orjson": "3.13.0",
    "websockets": "17.3",
    "httpx": "0.28.1",
    "python-multipart": "0.0.32",
    # Config / models
    "pydantic": "2.14.1",
    "pydantic-settings": "2.16.1",
    "python-dotenv": "1.2.4",
    # Database
    "sqlalchemy": "2.1.6",
    "alembic": "1.20.1",
    "asyncpg": "0.32.0",
    # Cache / scheduling
    "redis": "8.1.0",
    "apscheduler": "3.11.3",
    # Auth
    "pyjwt": "2.15.1",
    "argon2-cffi": "25.1.0",
    # Quant
    "numpy": "2.5.4",
    "pandas": "3.0.6",
    "scipy": "1.18.1",
    "statsmodels": "0.15.0",
    "arch": "8.0.0",
    "numba": "0.68.0",
    # Market data
    "polars": "2.0.0",
    "duckdb": "2.0.0",
    "pyarrow": "26.0.0",
    "yfinance": "1.7.0",
    # Test
    "pytest": "9.1.1",
    "pytest-asyncio": "1.4.0",
    "pyyaml": "6.0.3",
}

PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(?:\[[A-Za-z0-9_.,\-]*\])?\s*==\s*([^\s;]+)\s*$")


def _parse_requirements() -> dict[str, str]:
    """Parse `name==version` pins, ignoring comments, blank lines and extras."""
    pins: dict[str, str] = {}
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = PIN_RE.match(line)
        assert match is not None, f"unparseable requirement line: {raw!r}"
        name, version = match.group(1), match.group(2)
        # `uvicorn[standard]` pins under the bare distribution name.
        base = name.split("[", 1)[0]
        pins[base] = version
    return pins


def test_requirements_file_exists() -> None:
    assert REQUIREMENTS.is_file(), f"{REQUIREMENTS} is missing"


def test_every_expected_package_is_pinned() -> None:
    pins = _parse_requirements()
    missing = sorted(set(EXPECTED_PACKAGES) - set(pins))
    assert not missing, f"not pinned in requirements.txt: {missing}"


def test_pinned_versions_match_strategy_doc() -> None:
    pins = _parse_requirements()
    wrong = {
        name: (pins[name], version)
        for name, version in EXPECTED_PACKAGES.items()
        if name in pins and pins[name] != version
    }
    assert not wrong, f"requirements.txt pins differ from STRATEGY.md §10: {wrong}"


@pytest.mark.parametrize("package,version", sorted(EXPECTED_PACKAGES.items()))
def test_installed_version_matches_pin(package: str, version: str) -> None:
    installed = importlib.metadata.version(package)
    assert installed == version, (
        f"{package}: requirements.txt pins {version} but the venv has {installed}. "
        "Run: python -m pip install -r backend/requirements.txt"
    )


def test_no_unpinned_requirements() -> None:
    """Every requirement is an exact `==` pin — no floats, no ranges."""
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        assert "==" in line, f"requirement is not exactly pinned: {raw!r}"


def test_pytest_ini_configures_backend_import_path() -> None:
    assert PYTEST_INI.is_file(), f"{PYTEST_INI} is missing"
    content = PYTEST_INI.read_text(encoding="utf-8")
    assert "pythonpath = backend" in content
    assert "testpaths = tests" in content
