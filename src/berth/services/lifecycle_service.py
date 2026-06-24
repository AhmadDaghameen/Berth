"""Lifecycle operations: up, down, status, open."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from berth.constants import BERTH_NET, DEFAULT_ENV
from berth.exceptions import ElevationRequiredError
from berth.infra import docker as docker_infra
from berth.infra.hosts import add_hosts, remove_hosts
from berth.infra.mkcert import generate_project_cert
from berth.infra.traefik import reload_dynamic_config
from berth.models.config import ProjectConfig, ServiceConfig
from berth.models.manifest import Manifest, ServiceState
from berth.platform import current as platform
from berth.services.registry_service import get_project_path
from berth.storage.yaml_store import (
    load_manifest,
    load_project_config,
    save_manifest,
)
from berth.ui.console import console, error, info, step, success, warn


def _compose_project_name(project: str, env: str) -> str:
    if env == DEFAULT_ENV:
        return f"berth-{project}"
    return f"berth-{project}-{env}"


def _container_name(project: str, service: str, env: str) -> str:
    return f"{_compose_project_name(project, env)}-{service}-1"


def _build_compose_config(
    config: ProjectConfig,
    env: str,
    project_dir: Path,
) -> dict:
    """Build a docker-compose dict for the project services."""
    services_dict: dict = {}

    for svc_name, svc in config.services.items():
        if svc.type == "external":
            continue  # external services don't run containers

        if svc.type == "compose":
            # Import services from an existing docker-compose.yml and attach them to berth-net.
            compose_path = project_dir / (svc.context or ".") / "docker-compose.yml"
            if not compose_path.exists():
                compose_path = compose_path.with_suffix(".yaml")
            if compose_path.exists():
                existing = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
                for ext_name, ext_def in (existing.get("services") or {}).items():
                    ext_def = dict(ext_def)
                    # Attach to berth-net
                    nets = ext_def.get("networks", [])
                    if isinstance(nets, list):
                        if BERTH_NET not in nets:
                            nets.append(BERTH_NET)
                        ext_def["networks"] = nets
                    elif isinstance(nets, dict):
                        nets.setdefault(BERTH_NET, None)
                        ext_def["networks"] = nets
                    else:
                        ext_def["networks"] = [BERTH_NET]
                    services_dict[ext_name] = ext_def
            continue  # the compose pseudo-service has no container of its own

        svc_def: dict = {}

        if svc.type == "dockerfile":
            svc_def["build"] = {
                "context": str((project_dir / svc.context).resolve()) if svc.context else str(project_dir),
                **({"dockerfile": svc.dockerfile} if svc.dockerfile else {}),
            }
        elif svc.type == "docker-image":
            svc_def["image"] = svc.image
        elif svc.type == "static":
            svc_def["image"] = "nginx:alpine"
            if svc.context:
                svc_def["volumes"] = [
                    f"{(project_dir / svc.context).resolve()}:/usr/share/nginx/html:ro"
                ]

        if svc.command:
            svc_def["command"] = svc.command

        # Environment
        env_vars = dict(svc.env)
        if svc.env_file:
            env_file_path = project_dir / svc.env_file
            if not env_file_path.exists():
                env_suffix = f".env.{env}"
                alt = project_dir / env_suffix
                if alt.exists():
                    svc.env_file = str(alt.relative_to(project_dir))
        if svc.env_file:
            svc_def["env_file"] = [str((project_dir / svc.env_file).resolve())]
        if env_vars:
            svc_def["environment"] = env_vars

        # Volumes
        if svc.volumes:
            svc_def.setdefault("volumes", [])
            svc_def["volumes"].extend(svc.volumes)

        # Host port exposure
        if svc.expose_host_port and svc.container_port:
            # Assign a deterministic port based on hash to avoid collisions
            host_port = _assign_host_port(config.project, svc_name, env)
            svc_def["ports"] = [f"{host_port}:{svc.container_port}"]

        # Traefik labels for routed services
        effective_hostname = (
            svc.hostname_override
            if svc.hostname_override
            else (config.hostname(svc.route, env) if svc.route else None)
        )
        if effective_hostname and svc.container_port:
            svc_def.setdefault("labels", {})
            svc_def["labels"].update({
                "traefik.enable": "true",
                f"traefik.http.routers.{config.project}-{svc_name}-{env}.rule": f"Host(`{effective_hostname}`)",
                f"traefik.http.routers.{config.project}-{svc_name}-{env}.entrypoints": "websecure",
                f"traefik.http.routers.{config.project}-{svc_name}-{env}.tls": "true",
                f"traefik.http.services.{config.project}-{svc_name}-{env}.loadbalancer.server.port": str(svc.container_port),
            })
            if svc.default_route and not svc.hostname_override:
                bare = config.bare_hostname(env)
                svc_def["labels"].update({
                    f"traefik.http.routers.{config.project}-{svc_name}-{env}-bare.rule": f"Host(`{bare}`)",
                    f"traefik.http.routers.{config.project}-{svc_name}-{env}-bare.entrypoints": "websecure",
                    f"traefik.http.routers.{config.project}-{svc_name}-{env}-bare.tls": "true",
                    f"traefik.http.services.{config.project}-{svc_name}-{env}-bare.loadbalancer.server.port": str(svc.container_port),
                })

        # Networks
        svc_def["networks"] = [BERTH_NET]

        # Healthcheck
        if svc.healthcheck:
            svc_def["healthcheck"] = {
                "test": ["CMD-SHELL", f"curl -sf http://localhost:{svc.container_port}{svc.healthcheck.path} || exit 1"],
                "interval": svc.healthcheck.interval,
                "timeout": svc.healthcheck.timeout,
                "retries": svc.healthcheck.retries,
            }

        # depends_on (reference other services by compose service name)
        if svc.depends_on:
            svc_def["depends_on"] = svc.depends_on

        # Container name
        svc_def["container_name"] = _container_name(config.project, svc_name, env)

        services_dict[svc_name] = svc_def

    # Top-level volumes referenced by services
    named_volumes: dict = {}
    for svc in config.services.values():
        for vol in svc.volumes:
            if ":" in vol:
                vol_name = vol.split(":")[0]
                if not vol_name.startswith("/") and not vol_name.startswith("."):
                    named_volumes[vol_name] = None  # use default driver

    compose: dict = {
        "services": services_dict,
        "networks": {
            BERTH_NET: {"external": True},
        },
    }
    if named_volumes:
        compose["volumes"] = named_volumes

    return compose


def _wait_for_healthy(
    container_name: str,
    has_healthcheck: bool,
    timeout: int = 60,
    interval: int = 2,
) -> bool:
    """
    Poll until the container is healthy (or just running if no healthcheck).
    Returns True if healthy/running within timeout, False otherwise.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "inspect", "--format",
             "{{.State.Status}} {{.State.Health.Status}}", container_name],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            time.sleep(interval)
            continue

        parts = result.stdout.strip().split()
        state = parts[0] if parts else ""
        health = parts[1] if len(parts) > 1 else ""

        if has_healthcheck:
            if health == "healthy":
                return True
            if health == "unhealthy":
                return False
        else:
            if state == "running":
                return True

        time.sleep(interval)

    return False


def _assign_host_port(project: str, service: str, env: str) -> int:
    """Assign a stable host port in the range 54000-54999 based on name hash."""
    key = f"{project}-{service}-{env}"
    return 54000 + (hash(key) % 1000)


def _sync_traefik_routes() -> None:
    """Rebuild Traefik dynamic config from all active manifests and reload."""
    from berth.storage.paths import paths
    from berth.storage.yaml_store import load_registry, load_manifest
    from berth.constants import SHARED_SERVICES
    from berth.infra.docker import container_running

    routes: list[dict] = []
    try:
        registry = load_registry()
    except Exception:
        registry = None

    if registry:
        for proj_name in registry.projects:
            for manifest_file in paths.manifests.glob(f"{proj_name}.*.json"):
                env = manifest_file.stem[len(proj_name) + 1:]
                try:
                    manifest = load_manifest(proj_name, env)
                except Exception:
                    continue
                for svc_name, state in manifest.services.items():
                    if state.health in ("stopped", "unknown"):
                        continue
                    if state.external_url and state.hostname:
                        # External service — Traefik proxies to a host process or remote endpoint.
                        routes.append({
                            "name": f"{proj_name}-{svc_name}-{env}",
                            "hostname": state.hostname,
                            "url": state.external_url,
                        })
                    elif state.hostname and state.container_name and state.container_port:
                        routes.append({
                            "name": f"{proj_name}-{svc_name}-{env}",
                            "hostname": state.hostname,
                            "container_name": state.container_name,
                            "port": state.container_port,
                        })
                        if state.bare_hostname:
                            routes.append({
                                "name": f"{proj_name}-{svc_name}-{env}-bare",
                                "hostname": state.bare_hostname,
                                "container_name": state.container_name,
                                "port": state.container_port,
                            })

    # Add routes for running shared services that expose an HTTP interface.
    for shared_name, cfg in SHARED_SERVICES.items():
        if cfg.get("hostname") and cfg.get("http_port"):
            if container_running(cfg["container_name"]):
                routes.append({
                    "name": f"berth-shared-{shared_name}",
                    "hostname": cfg["hostname"],
                    "container_name": cfg["container_name"],
                    "port": cfg["http_port"],
                })

    reload_dynamic_config(routes)


def _get_all_hostnames(config: ProjectConfig, env: str) -> list[str]:
    hostnames = []
    for svc_name, svc in config.services.items():
        if svc.hostname_override:
            hostnames.append(svc.hostname_override)
        elif svc.route:
            hostnames.append(config.hostname(svc.route, env))
            if svc.default_route:
                hostnames.append(config.bare_hostname(env))
    return hostnames


def _write_compose_file(compose_dir: Path, compose_config: dict) -> Path:
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_file = compose_dir / "docker-compose.yml"
    compose_file.write_text(yaml.dump(compose_config, default_flow_style=False), encoding="utf-8")
    return compose_file


def up(slug: str, env: str = DEFAULT_ENV) -> list[str]:
    """Start the project stack. Returns list of URLs."""
    from berth.storage.paths import paths

    project_dir = get_project_path(slug)
    config = load_project_config(project_dir)

    info(f"Starting [bold]{slug}[/] ({env}) …")

    # Auto-start any shared services declared in `uses:`
    if config.uses:
        from berth.services.shared_service import start_shared
        from berth.constants import SHARED_SERVICES
        from berth.infra.docker import container_running as _cr
        for shared_name in config.uses:
            if shared_name not in SHARED_SERVICES:
                warn(f"Unknown shared service '{shared_name}' in uses: — skipping")
                continue
            cfg = SHARED_SERVICES[shared_name]
            if not _cr(cfg["container_name"]):
                step(f"Starting shared service: {shared_name}")
                start_shared(shared_name)

    # Build compose config
    compose_config = _build_compose_config(config, env, project_dir)

    # Write generated compose file to ~/.berth/
    compose_dir = paths.home / "compose" / slug / env
    compose_file = _write_compose_file(compose_dir, compose_config)

    # Generate per-project TLS cert if not already present
    cert_path = paths.project_cert_path(slug, env)
    if not cert_path.exists():
        domain = f"*.{slug}.{env}.test" if env != "local" else f"*.{slug}.test"
        info(f"Generating TLS cert for {domain} …")
        try:
            generate_project_cert(slug, env)
            step(f"cert -> {cert_path}")
        except Exception as exc:
            warn(f"Could not generate project cert: {exc}")

    # Add hosts entries (requires elevation on first run per host)
    hostnames = _get_all_hostnames(config, env)
    if hostnames:
        try:
            add_hosts(hostnames)
            step(f"Hosts entries: {', '.join(hostnames)}")
        except ElevationRequiredError as exc:
            warn(f"Could not update hosts file: {exc}")
            warn("You may need to add these entries manually or re-run elevated.")

    # Start containers
    docker_infra.compose_up(compose_dir, _compose_project_name(slug, env))

    # Wait for each routed service to become healthy before printing URLs
    manifest = load_manifest(slug, env)
    now = datetime.now(timezone.utc)

    for svc_name, svc in config.services.items():
        if svc.type == "external":
            hostname = config.hostname(svc.route, env) if svc.route else None
            ext_url = f"{svc.scheme}://{svc.host}:{svc.port}"
            manifest.services[svc_name] = ServiceState(
                service=svc_name,
                hostname=hostname,
                external_url=ext_url,
                health="running",
                deployed_at=now,
            )
            continue

        if svc.type == "compose":
            # Compose services are imported into the stack; no per-service manifest entry.
            continue

        container = _container_name(slug, svc_name, env)
        hostname = (
            svc.hostname_override
            if svc.hostname_override
            else (config.hostname(svc.route, env) if svc.route else None)
        )
        host_port = _assign_host_port(slug, svc_name, env) if svc.expose_host_port else None
        has_hc = svc.healthcheck is not None

        if hostname:
            step(f"Waiting for {svc_name} to be ready …")
            healthy = _wait_for_healthy(container, has_healthcheck=has_hc)
            health_status = "healthy" if healthy else "unhealthy"
            if not healthy:
                warn(f"Service '{svc_name}' did not become healthy within 60s.")
                warn(f"  Check logs: berth logs {slug} {svc_name}")
        else:
            # Non-routed service (worker, db); just confirm it started
            healthy = _wait_for_healthy(container, has_healthcheck=has_hc, timeout=30)
            health_status = "running" if healthy else "starting"

        bare = config.bare_hostname(env) if svc.default_route and not svc.hostname_override else None
        manifest.services[svc_name] = ServiceState(
            service=svc_name,
            container_name=container,
            container_port=svc.container_port,
            route=svc.route,
            hostname=hostname,
            bare_hostname=bare,
            host_port=host_port,
            health=health_status,
            deployed_at=now,
        )

    save_manifest(manifest)

    # Sync Traefik file-provider routes from all active manifests
    _sync_traefik_routes()

    success("Stack is up")

    # Print URLs for all routed services
    urls = [f"https://{h}" for h in hostnames]
    if urls:
        console.print()
        for url in urls:
            console.print(f"  [bold cyan]{url}[/]")

    return urls


def down(slug: str, env: str = DEFAULT_ENV, remove_volumes: bool = False) -> None:
    """Stop the project stack."""
    from berth.storage.paths import paths

    project_dir = get_project_path(slug)
    config = load_project_config(project_dir)

    info(f"Stopping [bold]{slug}[/] ({env}) …")

    compose_dir = paths.home / "compose" / slug / env
    if compose_dir.exists():
        docker_infra.compose_down(
            compose_dir,
            _compose_project_name(slug, env),
            remove_volumes=remove_volumes,
        )

    # Remove hosts entries
    hostnames = _get_all_hostnames(config, env)
    if hostnames:
        try:
            remove_hosts(hostnames)
        except ElevationRequiredError as exc:
            warn(f"Could not remove hosts entries: {exc}")

    # Clear manifest service states
    manifest = load_manifest(slug, env)
    for svc_name in manifest.services:
        manifest.services[svc_name].health = "stopped"
    save_manifest(manifest)

    # Remove stopped routes from Traefik
    _sync_traefik_routes()

    success(f"Stack stopped")


def get_status(slug: str | None = None) -> list[dict]:
    """Return status rows for all (or a specific) project."""
    from berth.storage.paths import paths
    from berth.storage.yaml_store import load_registry

    rows = []
    registry = load_registry()
    projects = [slug] if slug else list(registry.projects.keys())

    for proj in projects:
        try:
            proj_path = Path(registry.projects[proj].path)
            config = load_project_config(proj_path)
        except Exception:
            continue

        for env in config.environments:
            manifest = load_manifest(proj, env)
            for svc_name, state in manifest.services.items():
                # Refresh health from Docker if container known
                health = state.health
                if state.container_name:
                    live = docker_infra.container_running(state.container_name)
                    health = "running" if live else "stopped"

                rows.append({
                    "project": proj,
                    "env": env,
                    "service": svc_name,
                    "version": state.version or "—",
                    "url": f"https://{state.hostname}" if state.hostname else "—",
                    "health": health,
                    "host_port": str(state.host_port) if state.host_port else "—",
                    "deployed_at": state.deployed_at.isoformat() if state.deployed_at else "—",
                })

    return rows


def open_service(slug: str, service_name: str | None = None, env: str = DEFAULT_ENV) -> None:
    """Open the service URL in the default browser."""
    manifest = load_manifest(slug, env)
    if not manifest.services:
        error(f"No services found for '{slug}' ({env}). Run 'berth up {slug}' first.")
        return

    target = None
    if service_name:
        state = manifest.services.get(service_name)
        if state and state.hostname:
            target = f"https://{state.hostname}"
    else:
        # Pick default_route service or first with a hostname
        for state in manifest.services.values():
            if state.hostname:
                target = f"https://{state.hostname}"
                break

    if not target:
        error("No URL found. Check 'berth status'.")
        return

    info(f"Opening {target} …")
    platform.open_url(target)
