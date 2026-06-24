"""Docker / Docker Compose wrappers."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from berth.constants import BERTH_NET
from berth.exceptions import DockerUnavailableError


def _run(args: list[str], check: bool = True, capture: bool = False, **kwargs: Any) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            check=check,
            capture_output=capture,
            text=True,
            **kwargs,
        )
    except FileNotFoundError:
        raise DockerUnavailableError()


def check_docker() -> None:
    """Raise DockerUnavailableError if Docker daemon is not reachable."""
    result = _run(["docker", "info"], check=False, capture=True)
    if result.returncode != 0:
        raise DockerUnavailableError()


def ensure_network() -> None:
    """Create berth-net if it doesn't exist."""
    result = _run(
        ["docker", "network", "inspect", BERTH_NET],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        _run(["docker", "network", "create", BERTH_NET])


def container_exists(name: str) -> bool:
    result = _run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        check=False,
        capture=True,
    )
    return name in result.stdout.strip()


def container_running(name: str) -> bool:
    result = _run(
        ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        check=False,
        capture=True,
    )
    return name in result.stdout.strip()


def start_container(name: str) -> None:
    _run(["docker", "start", name])


def stop_container(name: str, remove: bool = False) -> None:
    _run(["docker", "stop", name], check=False)
    if remove:
        _run(["docker", "rm", name], check=False)


def pull_image(image: str) -> None:
    _run(["docker", "pull", image])


def get_container_health(name: str) -> str:
    """Return health status: healthy | unhealthy | starting | unknown."""
    result = _run(
        ["docker", "inspect", "--format", "{{.State.Health.Status}}", name],
        check=False,
        capture=True,
    )
    status = result.stdout.strip()
    return status if status else "unknown"


def compose_up(
    project_dir: Path,
    project_name: str,
    compose_file: str = "docker-compose.yml",
    detach: bool = True,
    build: bool = True,
) -> None:
    cmd = ["docker", "compose", "-p", project_name, "-f", compose_file, "up"]
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")
    _run(cmd, cwd=str(project_dir))


def compose_down(
    project_dir: Path,
    project_name: str,
    compose_file: str = "docker-compose.yml",
    remove_volumes: bool = False,
) -> None:
    cmd = ["docker", "compose", "-p", project_name, "-f", compose_file, "down"]
    if remove_volumes:
        cmd.append("-v")
    _run(cmd, cwd=str(project_dir), check=False)


def run_compose(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return _run(["docker", "compose"] + args, cwd=str(cwd) if cwd else None, capture=True)
