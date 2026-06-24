"""Shared Berth infrastructure: Mailpit, Redis — managed outside project manifests."""
from __future__ import annotations

import subprocess

from berth.constants import BERTH_NET, SHARED_SERVICES
from berth.exceptions import BerthError
from berth.infra.docker import container_exists, container_running, start_container, stop_container
from berth.infra.hosts import add_hosts, remove_hosts
from berth.ui.console import info, success, warn


def list_services() -> list[dict]:
    """Return status of all shared services."""
    results = []
    for name, cfg in SHARED_SERVICES.items():
        running = container_running(cfg["container_name"])
        results.append({
            "name": name,
            "container": cfg["container_name"],
            "description": cfg["description"],
            "running": running,
            "hostname": cfg.get("hostname"),
        })
    return results


def start_shared(name: str) -> None:
    """Start a named shared service, creating its container if needed."""
    cfg = SHARED_SERVICES.get(name)
    if not cfg:
        available = ", ".join(SHARED_SERVICES)
        raise BerthError(f"Unknown shared service '{name}'. Available: {available}")

    container = cfg["container_name"]

    if container_running(container):
        info(f"Shared service '{name}' is already running")
        _sync_routes()
        return

    if container_exists(container):
        start_container(container)
    else:
        _create_container(name, cfg)

    if cfg.get("hostname"):
        try:
            add_hosts([cfg["hostname"]])
        except Exception as exc:
            warn(f"Could not add hosts entry for {cfg['hostname']}: {exc}")

    _sync_routes()
    success(f"Shared service '{name}' started")
    _print_access_info(name, cfg)


def stop_shared(name: str) -> None:
    """Stop a named shared service (container is preserved for fast restart)."""
    cfg = SHARED_SERVICES.get(name)
    if not cfg:
        available = ", ".join(SHARED_SERVICES)
        raise BerthError(f"Unknown shared service '{name}'. Available: {available}")

    stop_container(cfg["container_name"])

    if cfg.get("hostname"):
        try:
            remove_hosts([cfg["hostname"]])
        except Exception as exc:
            warn(f"Could not remove hosts entry: {exc}")

    _sync_routes()
    success(f"Shared service '{name}' stopped")


def _create_container(name: str, cfg: dict) -> None:
    cmd = [
        "docker", "run", "-d",
        "--name", cfg["container_name"],
        "--network", BERTH_NET,
        "--restart", "unless-stopped",
    ]

    if name == "mailpit":
        cmd += ["-p", f"{cfg['smtp_port']}:{cfg['smtp_port']}"]
    elif name == "redis":
        cmd += ["-p", f"{cfg['port']}:{cfg['port']}"]

    cmd.append(cfg["image"])
    subprocess.run(cmd, check=True)


def _print_access_info(name: str, cfg: dict) -> None:
    if name == "mailpit":
        info(f"  Web UI  : https://{cfg['hostname']}")
        info(f"  SMTP    : localhost:{cfg['smtp_port']}")
        info(f"  SMTP host for containers: {cfg['container_name']}:{cfg['smtp_port']}")
    elif name == "redis":
        info(f"  TCP     : localhost:{cfg['port']}")
        info(f"  Redis URL for containers: redis://{cfg['container_name']}:{cfg['port']}")


def _sync_routes() -> None:
    from berth.services.lifecycle_service import _sync_traefik_routes
    _sync_traefik_routes()
