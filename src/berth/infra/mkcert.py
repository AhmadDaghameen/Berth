"""mkcert operations — CA install and wildcard cert generation."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from berth.constants import TLD
from berth.exceptions import MkcertNotFoundError
from berth.storage.paths import paths


def _run_mkcert(*args: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["mkcert", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise subprocess.CalledProcessError(result.returncode, ["mkcert", *args], detail)
        return result
    except FileNotFoundError:
        raise MkcertNotFoundError()


def check_mkcert() -> bool:
    """Return True if mkcert is available."""
    try:
        _run_mkcert("-version")
        return True
    except MkcertNotFoundError:
        return False


def install_ca() -> None:
    """Install the mkcert local CA so browsers trust generated certs."""
    _run_mkcert("-install")


def generate_wildcard_cert() -> tuple[Path, Path]:
    """
    Generate the base wildcard cert covering *.test and berth.test.
    Returns (cert_path, key_path).
    """
    paths.ensure_dirs()
    cert = paths.cert_path()
    key = paths.key_path()

    # Single-level wildcard only — multi-level (*.*.test) is not valid X.509.
    # Per-project certs (*.project.test) are generated in generate_project_cert().
    domains = [f"*.{TLD}", f"berth.{TLD}"]

    _run_mkcert(
        "-cert-file", str(cert),
        "-key-file", str(key),
        *domains,
    )
    return cert, key


def generate_project_cert(project_name: str, env: str = "local") -> tuple[Path, Path]:
    """
    Generate a wildcard cert for *.project.test (local) or *.project.env.test (other envs).
    Returns (cert_path, key_path).
    """
    paths.ensure_dirs()
    cert = paths.project_cert_path(project_name, env)
    key = paths.project_key_path(project_name, env)

    if env == "local":
        domains = [f"*.{project_name}.{TLD}", f"{project_name}.{TLD}"]
    else:
        domains = [f"*.{project_name}.{env}.{TLD}", f"{project_name}.{env}.{TLD}"]

    _run_mkcert(
        "-cert-file", str(cert),
        "-key-file", str(key),
        *domains,
    )
    return cert, key


def get_caroot() -> Path | None:
    """Return the mkcert CAROOT path, or None if unavailable."""
    try:
        result = _run_mkcert("-CAROOT")
        return Path(result.stdout.strip())
    except Exception:
        return None
