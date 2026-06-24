"""Release management — deploy, rollback, release, history."""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from berth.constants import DEFAULT_ENV, DEFAULT_KEEP_RELEASES
from berth.exceptions import BerthError, ServiceNotFoundError
from berth.models.manifest import Manifest, ReleaseRecord, ServiceState
from berth.services.lifecycle_service import (
    _assign_host_port,
    _build_compose_config,
    _compose_project_name,
    _container_name,
    _get_all_hostnames,
    _sync_traefik_routes,
    _wait_for_healthy,
    _write_compose_file,
)
from berth.services.registry_service import get_project_path
from berth.storage.paths import paths
from berth.storage.yaml_store import load_manifest, load_project_config, save_manifest
from berth.ui.console import console, error, info, step, success, warn


def _image_tag(project: str, service: str, version: str) -> str:
    return f"berth/{project}-{service}:{version}"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, text=True, cwd=str(cwd) if cwd else None)


def _git_sha(project_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(project_dir),
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except FileNotFoundError:
        return None


def _build_image(
    project_dir: Path,
    service_name: str,
    svc_context: str | None,
    svc_dockerfile: str | None,
    image_tag: str,
) -> None:
    context = str((project_dir / svc_context).resolve()) if svc_context else str(project_dir)
    cmd = ["docker", "build", "-t", image_tag, context]
    if svc_dockerfile:
        cmd += ["-f", str((project_dir / svc_dockerfile).resolve())]
    info(f"Building image {image_tag} …")
    _run(cmd)


def _prune_old_releases(project: str, service: str, keep: int = DEFAULT_KEEP_RELEASES) -> None:
    """Remove Docker images for releases beyond the keep limit."""
    manifest_files = list(paths.manifests.glob(f"{project}.*.json"))
    all_versions: list[str] = []
    for mf in manifest_files:
        from berth.storage.yaml_store import load_manifest as lm
        import json
        raw = json.loads(mf.read_text(encoding="utf-8"))
        for rec in raw.get("releases", []):
            if rec.get("image", "").startswith(f"berth/{project}-{service}:"):
                all_versions.append(rec["image"])

    if len(all_versions) <= keep:
        return

    to_remove = all_versions[:-keep]
    for image in to_remove:
        subprocess.run(["docker", "rmi", "--no-prune", image], capture_output=True)


def release_build(
    slug: str,
    service_name: str,
    version: str,
    env: str = DEFAULT_ENV,
) -> str:
    """Build and tag a release image without deploying. Returns the image tag."""
    project_dir = get_project_path(slug)
    config = load_project_config(project_dir)

    if service_name not in config.services:
        raise ServiceNotFoundError(service_name, slug)

    svc = config.services[service_name]
    if svc.type not in ("dockerfile", "static"):
        raise BerthError(
            f"Service '{service_name}' has type '{svc.type}' — only dockerfile/static services can be built."
        )

    tag = _image_tag(slug, service_name, version)
    _build_image(project_dir, service_name, svc.context, svc.dockerfile, tag)
    success(f"Release image ready: {tag}")
    return tag


def deploy(
    slug: str,
    service_name: str,
    version: str,
    env: str = DEFAULT_ENV,
) -> None:
    """
    Build/tag the release image, start new container, wait healthy,
    run post_deploy hook, record in manifest.
    """
    project_dir = get_project_path(slug)
    config = load_project_config(project_dir)

    if service_name not in config.services:
        raise ServiceNotFoundError(service_name, slug)

    svc = config.services[service_name]
    tag = _image_tag(slug, service_name, version)

    # Build if not already present
    check = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
    )
    if check.returncode != 0:
        if svc.type in ("dockerfile", "static"):
            _build_image(project_dir, service_name, svc.context, svc.dockerfile, tag)
        elif svc.type == "docker-image":
            info(f"Pulling {svc.image} …")
            _run(["docker", "pull", svc.image or tag])
        else:
            raise BerthError(f"Cannot build service type '{svc.type}'.")

    container = _container_name(slug, service_name, env)
    hostname = config.hostname(svc.route, env) if svc.route else None

    # Stop old container (keep image for rollback)
    old_running = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"name=^{container}$"],
        capture_output=True, text=True,
    ).stdout.strip()
    if old_running:
        info(f"Stopping old container {container} …")
        subprocess.run(["docker", "stop", container], capture_output=True)
        subprocess.run(["docker", "rm", container], capture_output=True)

    # Start new container
    info(f"Starting {container} ({tag}) …")
    run_cmd = [
        "docker", "run", "-d",
        "--name", container,
        "--network", "berth-net",
        "--restart", "unless-stopped",
    ]

    # Environment
    if svc.env_file:
        env_file_path = project_dir / svc.env_file
        if env_file_path.exists():
            run_cmd += ["--env-file", str(env_file_path)]
    for k, v in svc.env.items():
        run_cmd += ["-e", f"{k}={v}"]

    # Volumes
    for vol in svc.volumes:
        run_cmd += ["-v", vol]

    # Host port
    if svc.expose_host_port and svc.container_port:
        host_port = _assign_host_port(slug, service_name, env)
        run_cmd += ["-p", f"{host_port}:{svc.container_port}"]

    # Healthcheck
    if svc.healthcheck and svc.container_port:
        run_cmd += [
            "--health-cmd", f"curl -sf http://localhost:{svc.container_port}{svc.healthcheck.path} || exit 1",
            "--health-interval", svc.healthcheck.interval,
            "--health-timeout", svc.healthcheck.timeout,
            "--health-retries", str(svc.healthcheck.retries),
        ]

    if svc.command:
        run_cmd += [tag] + svc.command
    else:
        run_cmd.append(tag)

    _run(run_cmd)

    # Wait for healthy
    step(f"Waiting for {service_name} to be ready …")
    healthy = _wait_for_healthy(container, has_healthcheck=svc.healthcheck is not None)
    if not healthy:
        warn(f"Service '{service_name}' did not become healthy.")
        warn(f"  Route NOT swapped. Previous version still serving.")
        warn(f"  Check: berth logs {slug} {service_name} --env {env}")
        # Stop the failed new container
        subprocess.run(["docker", "stop", container], capture_output=True)
        subprocess.run(["docker", "rm", container], capture_output=True)
        raise BerthError(f"Deploy of '{service_name}' v{version} failed health check.")

    success(f"Service is healthy")

    # Run post_deploy hook
    if svc.hooks and svc.hooks.post_deploy:
        info(f"Running post_deploy hook: {svc.hooks.post_deploy}")
        result = subprocess.run(
            ["docker", "exec", container, "sh", "-c", svc.hooks.post_deploy],
            text=True,
        )
        if result.returncode != 0:
            raise BerthError(f"post_deploy hook failed (exit {result.returncode}).")
        success("post_deploy hook complete")

    # Record release in manifest
    manifest = load_manifest(slug, env)
    git_sha = _git_sha(project_dir)
    now = datetime.now(timezone.utc)

    bare = config.bare_hostname(env) if svc.default_route and not svc.hostname_override else None
    manifest.services[service_name] = ServiceState(
        service=service_name,
        version=version,
        image=tag,
        container_name=container,
        container_port=svc.container_port,
        route=svc.route,
        hostname=hostname,
        bare_hostname=bare,
        host_port=_assign_host_port(slug, service_name, env) if svc.expose_host_port else None,
        health="healthy",
        deployed_at=now,
    )
    manifest.releases.append(ReleaseRecord(
        version=version,
        image=tag,
        deployed_at=now,
        env=env,
        git_sha=git_sha,
    ))
    manifest.updated_at = now
    save_manifest(manifest)

    _sync_traefik_routes()
    _prune_old_releases(slug, service_name)

    if hostname:
        console.print(f"\n  [bold cyan]https://{hostname}[/]")
    success(f"Deployed {slug}/{service_name} v{version} to {env}")


def rollback(
    slug: str,
    service_name: str,
    env: str = DEFAULT_ENV,
    to_version: str | None = None,
) -> None:
    """Redeploy a previously built release image."""
    manifest = load_manifest(slug, env)

    # Find target release
    service_releases = [
        r for r in manifest.releases
        if r.image.startswith(f"berth/{slug}-{service_name}:")
    ]
    if not service_releases:
        raise BerthError(
            f"No release history found for '{slug}/{service_name}' in env '{env}'."
        )

    if to_version:
        target = next(
            (r for r in reversed(service_releases) if r.version == to_version),
            None,
        )
        if not target:
            available = ", ".join(r.version for r in service_releases)
            raise BerthError(
                f"Version '{to_version}' not found. Available: {available}"
            )
    else:
        # Default to the version before the current one
        current_version = manifest.services.get(service_name, ServiceState(service=service_name)).version
        candidates = [r for r in service_releases if r.version != current_version]
        if not candidates:
            raise BerthError("No previous release to roll back to.")
        target = candidates[-1]

    info(f"Rolling back {slug}/{service_name} to v{target.version} …")

    # Check the image still exists locally
    check = subprocess.run(
        ["docker", "image", "inspect", target.image],
        capture_output=True,
    )
    if check.returncode != 0:
        raise BerthError(
            f"Image '{target.image}' not found locally. It may have been pruned.\n"
            "  Rebuild it: berth release {slug} {service_name} --version {target.version}"
        )

    # Re-use deploy logic with the existing image
    deploy(slug, service_name, target.version, env)


def get_history(slug: str, service_name: str, env: str = DEFAULT_ENV) -> list[dict]:
    """Return chronological release history for a service."""
    manifest = load_manifest(slug, env)
    current = manifest.services.get(service_name)
    current_version = current.version if current else None

    records = [
        r for r in manifest.releases
        if r.image.startswith(f"berth/{slug}-{service_name}:")
    ]

    return [
        {
            "version": r.version,
            "image": r.image,
            "deployed_at": r.deployed_at.isoformat(),
            "env": r.env,
            "git_sha": r.git_sha or "—",
            "current": r.version == current_version,
        }
        for r in reversed(records)  # newest first
    ]
