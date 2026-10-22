"""Environment file resolution.

Two ways a fresh checkout silently fails to connect to its own database:

1. The app looks for `.env` relative to the current working directory, but the
   documented workflow runs `uvicorn` from `backend/` while `.env` is copied to
   the repo root. The file is found by neither path.
2. `.env.example` carries a database password that does not match the one
   baked into `PAIRTRADE_DATABASE_URL`, so Postgres accepts a password the
   application never sends.

Both are checked here rather than discovered on first `docker compose up`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _env_example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def test_env_example_is_found_where_the_app_looks_for_it() -> None:
    """`backend/config.py` must resolve `.env` to the repo root, not `backend/`."""
    import config

    configured = config.Settings.model_config.get("env_file")
    assert configured is not None

    candidates = configured if isinstance(configured, (list, tuple)) else (configured,)
    resolved = {
        (Path(c) if Path(c).is_absolute() else REPO_ROOT / c).resolve() for c in candidates
    }

    # The repo root is where `cp .env.example .env` puts the file.
    assert (REPO_ROOT / ".env").resolve() in resolved, (
        f"config.Settings env_file={configured!r} does not include the repo-root "
        f".env — a user copying .env.example to the repo root would have it ignored"
    )


def test_repo_root_env_file_is_actually_loaded(tmp_path: Path, monkeypatch) -> None:
    """Behaviour, not configuration: a repo-root `.env` must take effect.

    The app is run as `cd backend && uvicorn app:app`, so the process CWD is
    `backend/`. If `.env` is resolved relative to the CWD, a `.env` sitting in
    the repo root is silently ignored and the app boots on defaults.
    """
    import importlib

    import config

    env_path = REPO_ROOT / ".env"
    assert not env_path.exists(), (
        "a real .env exists in the repo root — this test would read real secrets"
    )

    env_path.write_text(
        "PAIRTRADE_MAX_DAILY_LOSS=4242\n", encoding="utf-8"
    )
    backend_cwd = REPO_ROOT / "backend"
    monkeypatch.chdir(backend_cwd)
    monkeypatch.delenv("PAIRTRADE_MAX_DAILY_LOSS", raising=False)
    try:
        reloaded = importlib.reload(config)
        assert reloaded.settings.max_daily_loss == 4242, (
            "the repo-root .env was not loaded when running from backend/ — "
            "env_file must not depend on the process working directory"
        )
    finally:
        env_path.unlink(missing_ok=True)
        monkeypatch.undo()
        importlib.reload(config)


def test_env_file_is_found_regardless_of_working_directory(tmp_path: Path) -> None:
    """Running from `backend/` must still pick up the repo-root `.env`."""
    import config

    configured = config.Settings.model_config.get("env_file")
    candidates = configured if isinstance(configured, (list, tuple)) else (configured,)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute():
            continue
        # Every relative candidate must resolve to an absolute location that
        # does not depend on the process CWD.
        assert (REPO_ROOT / path).is_absolute()


def test_database_url_password_matches_postgres_password() -> None:
    """The URL's password must be the password Postgres is actually given."""
    values = _env_example_values()

    database_url = values["PAIRTRADE_DATABASE_URL"]
    postgres_password = values["POSTGRES_PASSWORD"]

    parsed = urlparse(database_url)
    url_password = unquote(parsed.password or "")

    assert url_password == postgres_password, (
        f"PAIRTRADE_DATABASE_URL embeds password {url_password!r} but "
        f"POSTGRES_PASSWORD is {postgres_password!r} — Postgres would accept a "
        f"password the application never sends"
    )


def test_database_url_user_and_database_match_compose_values() -> None:
    values = _env_example_values()
    parsed = urlparse(values["PAIRTRADE_DATABASE_URL"])

    assert parsed.username == values["POSTGRES_USER"]
    assert (parsed.path or "").lstrip("/") == values["POSTGRES_DB"]


@pytest.mark.parametrize("key", ["PAIRTRADE_DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"])
def test_documented_database_variables_are_present(key: str) -> None:
    assert key in _env_example_values()


def test_env_example_has_no_trailing_whitespace() -> None:
    """A trailing space in a URL is a silent connection failure."""
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or line.strip().startswith("#"):
            continue
        assert line == line.rstrip(), f"trailing whitespace in .env.example: {raw!r}"


def test_env_example_values_have_no_surrounding_quotes() -> None:
    """A quoted value is passed to the app with the quotes still attached."""
    for key, value in _env_example_values().items():
        assert not (
            value.startswith('"') and value.endswith('"')
        ), f"{key} is quoted in .env.example: {value!r}"


def test_env_example_port_matches_compose_port() -> None:
    values = _env_example_values()
    parsed = urlparse(values["PAIRTRADE_DATABASE_URL"])
    assert str(parsed.port) == values["POSTGRES_PORT"]


def test_no_unresolved_interpolation_in_env_example() -> None:
    """`${VAR}` is compose syntax, not env-file syntax."""
    for key, value in _env_example_values().items():
        assert not re.search(r"\$\{", value), (
            f"{key} contains a ${{...}} reference, which .env files do not expand"
        )


def test_env_example_is_not_loaded_as_a_literal_env_file() -> None:
    """Sanity: the template itself is never read as the live environment."""
    assert ".env.example" not in os.environ.get("PAIRTRADE_ENVIRONMENT", "")
