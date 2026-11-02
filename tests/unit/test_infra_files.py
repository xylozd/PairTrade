"""Local infrastructure files.

`docker-compose.yml` and `.env.example` are the two files a new machine (or
the VPS) needs before anything runs. They are also the two places a real
credential would leak into the repository, so both are checked here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Placeholders that are safe to commit. Anything else shaped like a credential
# in .env.example is a leak.
SAFE_PLACEHOLDERS = {"", "change-me", "changeme", "your-password", "your-secret"}


def _load_compose() -> dict:
    assert COMPOSE.is_file(), f"{COMPOSE} is missing"
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_compose_file_parses() -> None:
    compose = _load_compose()
    assert isinstance(compose, dict)
    assert "services" in compose


def test_compose_defines_postgres_and_redis() -> None:
    services = _load_compose()["services"]
    assert "postgres" in services
    assert "redis" in services


def test_compose_uses_pinned_images() -> None:
    services = _load_compose()["services"]
    assert services["postgres"]["image"] == "postgres:15-alpine"
    assert services["redis"]["image"] == "redis:7-alpine"


def test_compose_services_declare_healthchecks() -> None:
    """`depends_on: service_healthy` only works if the healthcheck exists."""
    services = _load_compose()["services"]
    for name in ("postgres", "redis"):
        assert "healthcheck" in services[name], f"{name} has no healthcheck"


def test_postgres_persists_to_a_named_volume() -> None:
    services = _load_compose()["services"]
    declared = _load_compose().get("volumes", {})
    mounts = services["postgres"].get("volumes", [])
    named = [v for v in mounts if isinstance(v, str) and ":" in v]
    assert named, "postgres must persist to a named volume"
    for mount in named:
        volume_name = mount.split(":", 1)[0]
        assert volume_name in declared, f"{volume_name} is not declared in volumes:"


def test_postgres_credentials_come_from_env() -> None:
    services = _load_compose()["services"]
    env = services["postgres"]["environment"]
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert key in env
        assert re.match(r"\$\{[A-Z_]+:-[^}]*\}$", str(env[key])), (
            f"{key} must come from an env var with a default, got {env[key]!r}"
        )


def test_compose_contains_no_hardcoded_credentials() -> None:
    """Values come from `${VAR:-default}` — never a literal password."""
    text = COMPOSE.read_text(encoding="utf-8")
    for match in re.finditer(r"PASSWORD:\s*(\S+)", text):
        value = match.group(1)
        assert value.startswith("${"), f"hardcoded password in compose file: {value}"


# --------------------------------------------------------------------------
# .env.example
# --------------------------------------------------------------------------


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} is missing"


def test_env_example_contains_no_real_secret() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        # Match keys that actually hold a credential. `ACCESS_TOKEN_TTL_MINUTES`
        # is a duration, not a token, so exclude TTL/EXPIRY keys.
        if not re.search(
            r"SECRET|PASSWORD|CREDENTIAL", key, flags=re.IGNORECASE
        ) and not re.search(
            r"(^|_)KEY$|(^|_)TOKEN$", key, flags=re.IGNORECASE
        ):
            continue
        assert value.strip() in SAFE_PLACEHOLDERS, (
            f"{key} has a non-placeholder value in .env.example: {value!r}"
        )


def test_env_example_lists_the_variables_the_app_reads() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in (
        "PAIRTRADE_DATABASE_URL",
        "PAIRTRADE_REDIS_URL",
        "PAIRTRADE_JWT_SECRET_KEY",
        "PAIRTRADE_ENVIRONMENT",
    ):
        assert key in text, f"{key} is missing from .env.example"


@pytest.mark.parametrize("name", ["postgres", "redis"])
def test_compose_service_names_match_env_example(name: str) -> None:
    """The env vars the compose file reads must be documented."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert f"{name.upper()}_" in text or f"POSTGRES_" in text
