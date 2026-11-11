"""User credentials shared by every harness and working directory."""

from __future__ import annotations

import os
import sys
import tempfile
import tomllib
from pathlib import Path


class ConfigError(Exception):
    """A credential or config problem, safe to show without exposing its value."""


def config_path() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("APPDATA", "")
        base = Path(root) if root else Path.home() / "AppData" / "Roaming"
    else:
        root = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(root) if root and Path(root).is_absolute() else Path.home() / ".config"
    return base / "slophound" / "config.toml"


def _read_config() -> str:
    try:
        return config_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeError):
        raise ConfigError("Cannot read the slophound config file.") from None


def _validate_key(value: str) -> str:
    key = value.strip()
    if not key or any(not 33 <= ord(ch) <= 126 for ch in key):
        raise ConfigError("The API key must be nonempty ASCII text without spaces or control characters.")
    return key


DEFAULT_JEV_BASE_URL = "https://api.typesafe.ai"


def _jev_setting(name: str) -> str:
    try:
        config = tomllib.loads(_read_config())
    except tomllib.TOMLDecodeError:
        raise ConfigError("Invalid TOML in the slophound config file.") from None
    section = config.get("jev", {})
    if not isinstance(section, dict) or not isinstance(section.get(name, ""), str):
        raise ConfigError(f"The slophound config must store jev.{name} as a string in a [jev] table.")
    return section.get(name, "").strip()


def read_jev_key() -> str | None:
    """Environment first, then the user config; an absent or blank key is unset."""
    environment = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if environment:
        return _validate_key(environment)
    value = _jev_setting("api_key")
    return _validate_key(value) if value else None


def _validate_base_url(value: str) -> str:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(value)
        valid = parts.scheme == "https" and bool(parts.hostname)
    except ValueError:
        valid = False
    if not valid or parts.username or parts.password or parts.query or parts.fragment:
        raise ConfigError("The Jev base URL must be an https:// URL without credentials, query, or fragment.")
    return value.rstrip("/")


def read_jev_base_url() -> str:
    """Environment first, then the user config; unset means the TypeSafe API.

    SLOPHOUND_JEV_BASE_URL is deliberately separate from the SDK's own
    TYPESAFE_BASE_URL, so an unrelated override never receives the key.
    """
    environment = os.environ.get("SLOPHOUND_JEV_BASE_URL", "").strip()
    value = environment or _jev_setting("base_url")
    return _validate_base_url(value) if value else DEFAULT_JEV_BASE_URL


def save_jev_key(value: str) -> Path:
    """Replace the key atomically, preserving other TOML settings and comments."""
    import tomlkit
    from tomlkit.exceptions import ParseError

    key = _validate_key(value)
    try:
        config = tomlkit.parse(_read_config())
    except ParseError:
        raise ConfigError("Invalid TOML in the slophound config file; it was not changed.") from None
    if "jev" not in config:
        config["jev"] = tomlkit.table()
    if not isinstance(config["jev"], dict):
        raise ConfigError("Expected a [jev] table in the slophound config file; it was not changed.")
    config["jev"]["api_key"] = key
    path = config_path()
    temporary: Path | None = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # mkstemp creates a 0600 file on POSIX. Replace in the same directory
        # so a failed write cannot truncate an existing key or other settings.
        fd, name = tempfile.mkstemp(prefix=".config-", suffix=".toml", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(tomlkit.dumps(config))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise ConfigError("Cannot save the API key in the slophound config file.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
