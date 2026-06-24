"""Traefik container management and configuration generation."""
from __future__ import annotations

import textwrap
import time
from pathlib import Path

import yaml

from berth.constants import BERTH_NET, TRAEFIK_CONTAINER, TRAEFIK_IMAGE
from berth.infra.docker import (
    container_exists,
    container_running,
    ensure_network,
    pull_image,
    start_container,
    stop_container,
    _run,
)
from berth.storage.paths import paths


def generate_static_config() -> str:
    """Return Traefik static config YAML."""
    cert_file = str(paths.cert_path()).replace("\\", "/")
    key_file = str(paths.key_path()).replace("\\", "/")
    dynamic_conf = str(paths.traefik_dynamic_config()).replace("\\", "/")

    return textwrap.dedent(f"""\
        global:
          checkNewVersion: false
          sendAnonymousUsage: false

        api:
          dashboard: true
          insecure: true

        entryPoints:
          web:
            address: ":80"
            http:
              redirections:
                entryPoint:
                  to: websecure
                  scheme: https
          websecure:
            address: ":443"

        providers:
          file:
            filename: /traefik/dynamic.yml
            watch: true

        log:
          level: INFO
    """)


def _collect_certs() -> list[dict]:
    """Return all cert/key pairs in ~/.berth/certs/ as Traefik certificate entries."""
    certs_dir = paths.certs
    entries = []
    for crt in sorted(certs_dir.glob("*.crt")):
        key = crt.with_suffix(".key")
        if key.exists():
            entries.append({
                "certFile": f"/certs/{crt.name}",
                "keyFile": f"/certs/{key.name}",
            })
    return entries or [{"certFile": "/certs/berth.crt", "keyFile": "/certs/berth.key"}]


def generate_dynamic_config(routes: list[dict]) -> str:
    """
    Generate Traefik dynamic config for TLS + routers.

    Each route dict must have: name, hostname, and either:
      - container_name + port  (container-based service)
      - url                    (external service or shared infra)
    """
    routers: dict = {}
    services: dict = {}

    for r in routes:
        name = r["name"]
        hostname = r["hostname"]

        if "url" in r:
            server_url = r["url"]
        else:
            server_url = f"http://{r['container_name']}:{r['port']}"

        routers[name] = {
            "rule": f"Host(`{hostname}`)",
            "entryPoints": ["websecure"],
            "service": name,
            "tls": {},
        }
        services[name] = {
            "loadBalancer": {
                "servers": [{"url": server_url}],
            }
        }

    config = {
        "tls": {
            "certificates": _collect_certs(),
        },
        "http": {
            "routers": routers,
            "services": services,
        },
    }
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def write_configs(routes: list[dict] | None = None) -> None:
    """Write static and dynamic Traefik config files."""
    paths.ensure_dirs()
    paths.traefik_static_config().write_text(generate_static_config(), encoding="utf-8")
    paths.traefik_dynamic_config().write_text(
        generate_dynamic_config(routes or []), encoding="utf-8"
    )


def start_traefik() -> None:
    """Start the Traefik container (idempotent)."""
    ensure_network()

    if container_running(TRAEFIK_CONTAINER):
        return

    if container_exists(TRAEFIK_CONTAINER):
        start_container(TRAEFIK_CONTAINER)
        return

    traefik_dir = str(paths.traefik).replace("\\", "/")
    certs_dir = str(paths.certs).replace("\\", "/")

    # Use Windows-style paths for Docker Desktop on Windows
    import sys
    if sys.platform == "win32":
        # Docker Desktop with WSL2 mounts Windows paths via /run/desktop/mnt/host
        # Easier to use the raw path which Docker Desktop translates
        pass

    _run([
        "docker", "run", "-d",
        "--name", TRAEFIK_CONTAINER,
        "--restart", "unless-stopped",
        "--network", BERTH_NET,
        "-p", "80:80",
        "-p", "443:443",
        "-p", "8080:8080",  # Traefik dashboard
        "-v", "/var/run/docker.sock:/var/run/docker.sock:ro",
        "-v", f"{traefik_dir}:/traefik",
        "-v", f"{certs_dir}:/certs",
        TRAEFIK_IMAGE,
        "--configFile=/traefik/traefik.yml",
    ])

    # Brief wait for Traefik to initialise
    time.sleep(2)


def stop_traefik(remove: bool = False) -> None:
    """Stop (and optionally remove) the Traefik container."""
    stop_container(TRAEFIK_CONTAINER, remove=remove)


def reload_dynamic_config(routes: list[dict]) -> None:
    """Regenerate dynamic config; Traefik file-watches and picks it up."""
    paths.traefik_dynamic_config().write_text(
        generate_dynamic_config(routes), encoding="utf-8"
    )
