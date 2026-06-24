"""berth up / down / restart / status / ps / logs / open commands."""
from __future__ import annotations

from typing import Optional

import typer

from berth.constants import DEFAULT_ENV
from berth.exceptions import BerthError
from berth.ui.console import console, error, info

app = typer.Typer(help="Run and manage project stacks.")


@app.command("up")
def up(
    project: str = typer.Argument(..., help="Project slug."),
    env: str = typer.Option(DEFAULT_ENV, "--env", "-e", help="Environment name."),
) -> None:
    """Build (if needed), start the environment stack, and wire HTTPS routes."""
    from berth.services.lifecycle_service import up as svc_up

    try:
        svc_up(project, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command("down")
def down(
    project: str = typer.Argument(..., help="Project slug."),
    env: str = typer.Option(DEFAULT_ENV, "--env", "-e", help="Environment name."),
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove data volumes."),
) -> None:
    """Stop the project stack and remove its routes."""
    from berth.services.lifecycle_service import down as svc_down

    try:
        svc_down(project, env, remove_volumes=volumes)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command("restart")
def restart(
    project: str = typer.Argument(..., help="Project slug."),
    service: Optional[str] = typer.Argument(None, help="Specific service to restart (optional)."),
    env: str = typer.Option(DEFAULT_ENV, "--env", "-e", help="Environment name."),
) -> None:
    """Restart an entire stack or a single service."""
    from berth.services.lifecycle_service import down as svc_down, up as svc_up

    try:
        svc_down(project, env)
        svc_up(project, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command("status")
def status(
    project: Optional[str] = typer.Argument(None, help="Project slug (omit for all)."),
) -> None:
    """Show status of all registered projects / environments / services."""
    from berth.services.lifecycle_service import get_status
    from berth.ui.console import make_table, health_badge

    try:
        rows = get_status(project)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)

    if not rows:
        info("No services found. Run 'berth up <project>' to start one.")
        return

    table = make_table(
        "Project", "Env", "Service", "Version", "URL", "Health", "Host Port", "Deployed",
        title="Berth Status",
    )
    for r in rows:
        table.add_row(
            r["project"],
            r["env"],
            r["service"],
            r["version"],
            f"[cyan]{r['url']}[/]" if r["url"] != "—" else "—",
            health_badge(r["health"]),
            r["host_port"],
            r["deployed_at"],
        )
    console.print(table)


@app.command("ps")
def ps() -> None:
    """Show underlying Docker container view for Berth-managed containers."""
    import subprocess

    result = subprocess.run(
        ["docker", "ps", "--filter", "label=traefik.enable=true", "--format",
         "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        capture_output=True,
        text=True,
    )
    console.print(result.stdout or "No containers running.")


@app.command("logs")
def logs(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Argument(..., help="Service name."),
    env: str = typer.Option(DEFAULT_ENV, "--env", "-e"),
    follow: bool = typer.Option(False, "-f", "--follow"),
) -> None:
    """Stream logs from a service container."""
    import subprocess
    from berth.storage.yaml_store import load_manifest

    manifest = load_manifest(project, env)
    state = manifest.services.get(service)
    if not state or not state.container_name:
        error(f"No running container found for '{project}/{service}' ({env}).")
        raise typer.Exit(1)

    cmd = ["docker", "logs", state.container_name]
    if follow:
        cmd.append("-f")
    subprocess.run(cmd)


@app.command("open")
def open_cmd(
    project: str = typer.Argument(..., help="Project slug."),
    service: Optional[str] = typer.Argument(None, help="Service name (optional)."),
    env: str = typer.Option(DEFAULT_ENV, "--env", "-e"),
) -> None:
    """Open the project (or service) URL in the default browser."""
    from berth.services.lifecycle_service import open_service

    try:
        open_service(project, service, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)
