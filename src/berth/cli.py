"""Berth CLI — entry point."""
import typer

app = typer.Typer(
    name="berth",
    help="Berth — local release and deployment manager.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

shared_app = typer.Typer(
    name="shared",
    help="Manage shared Berth infrastructure (Mailpit, Redis, …).",
    no_args_is_help=True,
)
app.add_typer(shared_app, name="shared")


@app.command()
def setup(
    skip_dns: bool = typer.Option(False, "--skip-dns", help="Skip DNS configuration hints."),
) -> None:
    """One-time bootstrap: Docker check, mkcert CA, wildcard cert, Traefik, DNS."""
    from berth.services.setup_service import run_setup
    from berth.exceptions import BerthError
    from berth.ui.console import error as ui_error

    try:
        run_setup(skip_dns=skip_dns)
    except BerthError as exc:
        ui_error(str(exc))
        raise typer.Exit(1)


@app.command()
def init(
    directory: str = typer.Argument(".", help="Directory to scaffold in (default: current dir)."),
) -> None:
    """Interactively scaffold a berth.project.yaml."""
    from pathlib import Path
    from berth.constants import PROJECT_CONFIG_FILE
    from berth.ui.console import console, info, success, warn

    target = Path(directory).resolve()
    config_path = target / PROJECT_CONFIG_FILE

    if config_path.exists():
        warn(f"{PROJECT_CONFIG_FILE} already exists. Edit it directly.")
        raise typer.Exit()

    hints: list[str] = []
    if (target / "package.json").exists():
        hints.append("Node.js (package.json detected)")
    if (target / "pyproject.toml").exists() or (target / "requirements.txt").exists():
        hints.append("Python (pyproject.toml/requirements.txt detected)")
    if (target / "docker-compose.yml").exists() or (target / "docker-compose.yaml").exists():
        hints.append("Existing docker-compose.yml detected — consider 'type: compose'")

    info(f"Scaffolding in {target}")
    for h in hints:
        console.print(f"  [dim]Detected: {h}[/]")

    slug = typer.prompt("Project slug", default=target.name.lower().replace(" ", "-"))
    description = typer.prompt("Short description", default="")

    template = f"""\
# berth.project.yaml
project: {slug}
description: "{description}"

environments:
  - local

services:
  web:
    type: dockerfile
    context: .
    container_port: 3000
    route: app
    default_route: true
"""
    config_path.write_text(template, encoding="utf-8")
    success(f"Created {config_path}")
    console.print(f"\n  Edit [cyan]{PROJECT_CONFIG_FILE}[/] to configure your services, then run:")
    console.print(f"    [bold]berth register .[/]")
    console.print(f"    [bold]berth up {slug}[/]")


@app.command()
def register(
    path: str = typer.Argument(".", help="Path to the project directory (default: current dir)."),
) -> None:
    """Register a project containing berth.project.yaml."""
    from pathlib import Path
    from berth.services.registry_service import register_project
    from berth.exceptions import BerthError
    from berth.ui.console import error, success

    try:
        slug = register_project(Path(path))
        success(f"Registered project '[bold]{slug}[/]'")
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def unregister(
    project: str = typer.Argument(..., help="Project slug to remove."),
) -> None:
    """Remove a project from the registry (does not delete source files)."""
    from berth.services.registry_service import unregister_project
    from berth.exceptions import BerthError
    from berth.ui.console import error, success

    try:
        unregister_project(project)
        success(f"Unregistered project '[bold]{project}[/]'")
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command("ls")
def ls() -> None:
    """List all registered projects and their environments."""
    from berth.services.registry_service import get_registry
    from berth.ui.console import console, info, make_table

    registry = get_registry()
    if not registry.projects:
        info("No projects registered. Run 'berth register <path>' to add one.")
        return

    table = make_table("Project", "Path", "Description", title="Registered Projects")
    for slug, entry in registry.projects.items():
        table.add_row(f"[bold]{slug}[/]", entry.path, entry.description or "—")
    console.print(table)


@app.command()
def up(
    project: str = typer.Argument(..., help="Project slug."),
    env: str = typer.Option("local", "--env", "-e", help="Environment name."),
) -> None:
    """Build (if needed), start the environment stack, and wire HTTPS routes."""
    from berth.services.lifecycle_service import up as svc_up
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        svc_up(project, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def down(
    project: str = typer.Argument(..., help="Project slug."),
    env: str = typer.Option("local", "--env", "-e", help="Environment name."),
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove data volumes."),
) -> None:
    """Stop the project stack and remove its routes."""
    from berth.services.lifecycle_service import down as svc_down
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        svc_down(project, env, remove_volumes=volumes)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def restart(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Option(None, "--service", "-s", help="Specific service."),
    env: str = typer.Option("local", "--env", "-e"),
) -> None:
    """Restart an entire stack or a single service."""
    from berth.services.lifecycle_service import down as svc_down, up as svc_up
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        svc_down(project, env)
        svc_up(project, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def status(
    project: str = typer.Argument(None, help="Project slug (omit for all)."),
) -> None:
    """Show status of all registered projects / environments / services."""
    from berth.services.lifecycle_service import get_status
    from berth.exceptions import BerthError
    from berth.ui.console import console, error, info, make_table, health_badge

    try:
        rows = get_status(project)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)

    if not rows:
        info("No services deployed. Run 'berth up <project>' to start one.")
        return

    table = make_table(
        "Project", "Env", "Service", "Version", "URL", "Health", "Host Port",
        title="Berth Status",
    )
    for r in rows:
        table.add_row(
            r["project"], r["env"], r["service"], r["version"],
            f"[cyan]{r['url']}[/]" if r["url"] != "—" else "—",
            health_badge(r["health"]),
            r["host_port"],
        )
    console.print(table)


@app.command()
def ps() -> None:
    """Show underlying Docker container view for Berth-managed containers."""
    import subprocess
    from berth.ui.console import console

    result = subprocess.run(
        ["docker", "ps", "--filter", "label=traefik.enable=true",
         "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        capture_output=True, text=True,
    )
    console.print(result.stdout or "No Berth-managed containers running.")


@app.command()
def logs(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Argument(..., help="Service name."),
    env: str = typer.Option("local", "--env", "-e"),
    follow: bool = typer.Option(False, "-f", "--follow"),
) -> None:
    """Stream logs from a service container."""
    import subprocess
    from berth.storage.yaml_store import load_manifest
    from berth.ui.console import error

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
    service: str = typer.Argument(None, help="Service name (optional)."),
    env: str = typer.Option("local", "--env", "-e"),
) -> None:
    """Open the project (or service) URL in the default browser."""
    from berth.services.lifecycle_service import open_service
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        open_service(project, service, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Diagnose Berth environment issues."""
    import socket
    import subprocess
    from berth.constants import TRAEFIK_CONTAINER
    from berth.infra.docker import container_running
    from berth.infra.mkcert import check_mkcert, get_caroot
    from berth.platform import current as plat
    from berth.storage.paths import paths
    from berth.ui.console import console, error, info, success, step, warn

    console.rule("[bold]Berth Doctor[/]")
    all_ok = True

    def chk(label: str, ok: bool, ok_msg: str, fail_msg: str) -> bool:
        if ok:
            success(f"{label}: {ok_msg}")
        else:
            error(f"{label}: {fail_msg}")
        return ok

    # Docker
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        docker_ok = r.returncode == 0
    except Exception:
        docker_ok = False
    all_ok &= chk("Docker", docker_ok, "daemon reachable", "daemon NOT reachable — start Docker Desktop")

    # mkcert
    mkcert_ok = check_mkcert()
    all_ok &= chk("mkcert", mkcert_ok, "installed", "NOT found — winget install FiloSottile.mkcert")

    if mkcert_ok:
        caroot = get_caroot()
        ca_ok = caroot is not None and (caroot / "rootCA.pem").exists()
        all_ok &= chk("mkcert CA", ca_ok, f"installed ({caroot})", "not found — run: berth setup")

    # Traefik
    traefik_ok = container_running(TRAEFIK_CONTAINER)
    all_ok &= chk("Traefik", traefik_ok, "container running", "NOT running — run: berth setup")

    # Ports
    for port in (80, 443):
        try:
            with socket.socket() as s:
                s.settimeout(1); s.connect(("127.0.0.1", port))
            port_bound = True
        except (ConnectionRefusedError, OSError):
            port_bound = False
        if traefik_ok:
            all_ok &= chk(f"Port {port}", port_bound, "Traefik listening", "nothing listening")
        elif port_bound:
            warn(f"Port {port}: something else is occupying it — will conflict with Traefik")
            all_ok = False

    # DNS
    test_host = "berth-doctor-probe.test"
    try:
        ip = socket.gethostbyname(test_host)
        dns_ok = ip == "127.0.0.1"
    except socket.gaierror:
        dns_ok = False
    all_ok &= chk(
        "DNS (*.test)", dns_ok, "resolving to 127.0.0.1",
        f"'{test_host}' not resolving — add hosts entry or configure dnsmasq/Acrylic"
    )

    # TLS cert
    cert_ok = paths.cert_path().exists() and paths.key_path().exists()
    all_ok &= chk("TLS cert", cert_ok, f"found ({paths.certs})", "not found — run: berth setup")

    info(f"Hosts file: {plat.hosts_path} {'(elevated)' if plat.is_elevated() else '(not elevated)'}")

    # Shared services (informational — not blocking)
    from berth.constants import SHARED_SERVICES
    running_shared = [
        name for name, cfg in SHARED_SERVICES.items()
        if container_running(cfg["container_name"])
    ]
    if running_shared:
        info(f"Shared services running: {', '.join(running_shared)}")
    else:
        info("Shared services: none running  (berth shared up mailpit|redis)")

    console.print()
    if all_ok:
        success("[bold green]All checks passed.[/]")
    else:
        warn("[bold yellow]Some checks failed. See suggestions above.[/]")
        raise typer.Exit(1)


@app.command()
def nuke(
    keep_data: bool = typer.Option(False, "--keep-data", help="Keep Docker volumes."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Stop Traefik, remove all hosts entries, and tear down Berth state."""
    from berth.infra.traefik import stop_traefik
    from berth.infra.hosts import clear_all_managed_hosts
    from berth.exceptions import ElevationRequiredError
    from berth.ui.console import info, success, warn

    if not yes:
        typer.confirm("This will stop Traefik and clear all berth hosts entries. Continue?", abort=True)

    info("Stopping Traefik …")
    try:
        stop_traefik(remove=True)
        success("Traefik stopped and removed")
    except Exception as exc:
        warn(f"Could not stop Traefik: {exc}")

    info("Removing hosts entries …")
    try:
        clear_all_managed_hosts()
        success("Hosts entries cleared")
    except ElevationRequiredError as exc:
        warn(f"Could not clear hosts (elevation required): {exc}")

    success("[bold]Berth nuked.[/] Run 'berth setup' to start fresh.")


# ── Phase 2: Release management commands ────────────────────────────────────

@app.command()
def release(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Argument(..., help="Service name."),
    version: str = typer.Option(..., "--version", "-v", help="Semver version string (e.g. 1.0.0)."),
) -> None:
    """Build and tag a release image without deploying it."""
    from berth.services.release_service import release_build
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        release_build(project, service, version)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def deploy(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Argument(..., help="Service name."),
    version: str = typer.Option(..., "--version", "-v", help="Version to deploy."),
    env: str = typer.Option("local", "--env", "-e", help="Target environment."),
) -> None:
    """Build/tag a release, deploy it, run hooks, and record in history."""
    from berth.services.release_service import deploy as svc_deploy
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        svc_deploy(project, service, version, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def rollback(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Argument(..., help="Service name."),
    env: str = typer.Option("local", "--env", "-e", help="Environment."),
    to: str = typer.Option(None, "--to", help="Specific version to roll back to (default: previous)."),
) -> None:
    """Roll back a service to a previous release."""
    from berth.services.release_service import rollback as svc_rollback
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        svc_rollback(project, service, env, to_version=to)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command()
def history(
    project: str = typer.Argument(..., help="Project slug."),
    service: str = typer.Argument(..., help="Service name."),
    env: str = typer.Option("local", "--env", "-e", help="Environment."),
) -> None:
    """Show chronological release history for a service."""
    from berth.services.release_service import get_history
    from berth.exceptions import BerthError
    from berth.ui.console import console, error, info, make_table

    try:
        records = get_history(project, service, env)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)

    if not records:
        info(f"No release history for '{project}/{service}' ({env}).")
        return

    table = make_table("Version", "Deployed At", "Git SHA", "Image", "Current",
                       title=f"Release history: {project}/{service} ({env})")
    for r in records:
        current_marker = "[bold green]<-- current[/]" if r["current"] else ""
        table.add_row(
            f"[bold]{r['version']}[/]",
            r["deployed_at"],
            r["git_sha"],
            r["image"],
            current_marker,
        )
    console.print(table)


# ── Phase 4: Shared infrastructure commands ──────────────────────────────────

@shared_app.command("ls")
def shared_ls() -> None:
    """List shared services and their current status."""
    from berth.services.shared_service import list_services
    from berth.ui.console import console, make_table, health_badge

    rows = list_services()
    table = make_table("Service", "Container", "Status", "Description",
                       title="Berth Shared Services")
    for r in rows:
        status = health_badge("running") if r["running"] else health_badge("stopped")
        hostname_note = f"  [{r['hostname']}]" if r["hostname"] else ""
        table.add_row(
            f"[bold]{r['name']}[/]",
            r["container"],
            status,
            r["description"] + hostname_note,
        )
    console.print(table)


@shared_app.command("up")
def shared_up(
    service: str = typer.Argument(..., help="Shared service name (mailpit, redis, …)."),
) -> None:
    """Start a shared infrastructure service."""
    from berth.services.shared_service import start_shared
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        start_shared(service)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@shared_app.command("down")
def shared_down(
    service: str = typer.Argument(..., help="Shared service name (mailpit, redis, …)."),
) -> None:
    """Stop a shared infrastructure service."""
    from berth.services.shared_service import stop_shared
    from berth.exceptions import BerthError
    from berth.ui.console import error

    try:
        stop_shared(service)
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)
