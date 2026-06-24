"""Orchestrates berth setup — idempotent one-time bootstrap."""
from __future__ import annotations

from pathlib import Path

from berth.infra import docker as docker_infra
from berth.infra import mkcert as mkcert_infra
from berth.infra.hosts import add_hosts
from berth.infra.traefik import write_configs, start_traefik
from berth.storage.paths import paths
from berth.ui.console import console, success, info, warn, step, error

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


_BERTH_SETUP_HOSTS = ["berth.test", "traefik.berth.test"]


def run_setup(skip_dns: bool = False) -> None:
    """Run full Berth setup. Safe to re-run."""
    console.rule("[bold]Berth Setup[/]")

    # 1. Check Docker
    info("Checking Docker …")
    try:
        docker_infra.check_docker()
        success("Docker daemon is reachable")
    except Exception as exc:
        error(str(exc))
        raise SystemExit(1)

    # 2. Ensure ~/.berth dirs
    info("Creating Berth data directories …")
    paths.ensure_dirs()
    step(str(paths.home))
    success("Directories ready")

    # 3. mkcert CA install
    info("Installing mkcert local CA …")
    if not mkcert_infra.check_mkcert():
        import sys
        if sys.platform == "win32":
            hint = "  Windows: winget install FiloSottile.mkcert"
        elif sys.platform == "darwin":
            hint = "  macOS:   brew install mkcert"
        else:
            hint = (
                "  Linux/WSL2:\n"
                "    curl -JLO 'https://dl.filippo.io/mkcert/latest?for=linux/amd64'\n"
                "    chmod +x mkcert-* && sudo mv mkcert-* /usr/local/bin/mkcert"
            )
        error(f"mkcert not found. Install it and re-run 'berth setup'.\n{hint}")
        raise SystemExit(1)
    mkcert_infra.install_ca()
    success("mkcert CA installed and trusted")

    # 4. Generate wildcard cert
    info("Generating wildcard *.test certificate …")
    cert, key = mkcert_infra.generate_wildcard_cert()
    step(f"cert -> {cert}")
    step(f"key  -> {key}")
    success("TLS certificate ready")

    # 5. Write Traefik configs
    info("Writing Traefik configuration …")
    write_configs()
    success("Traefik config written")

    # 6. Ensure berth-net network
    info("Ensuring Docker network 'berth-net' …")
    docker_infra.ensure_network()
    success("Network ready")

    # 7. Start Traefik
    info("Starting Traefik container …")
    try:
        start_traefik()
        success("Traefik is running (ports 80, 443, 8080)")
    except Exception as exc:
        error(f"Failed to start Traefik: {exc}")
        warn("Ports 80/443 may already be in use. Run 'berth doctor' for diagnosis.")
        raise SystemExit(1)

    # 8. Add berth.test / traefik.berth.test hosts entries
    if not skip_dns:
        info("Writing berth.test hosts entries …")
        from berth.exceptions import ElevationRequiredError
        try:
            add_hosts(_BERTH_SETUP_HOSTS)
            for h in _BERTH_SETUP_HOSTS:
                step(f"127.0.0.1 {h}")
            success("Hosts entries written")
        except ElevationRequiredError:
            warn(
                "Could not write hosts entries — elevation required.\n"
                "  Re-run 'berth setup' as root/Administrator, or add manually:\n"
                + "\n".join(f"    127.0.0.1 {h}" for h in _BERTH_SETUP_HOSTS)
            )

    # 9. Register and start the Berth dashboard
    info("Starting Berth dashboard …")
    try:
        from berth.services.registry_service import register_project, get_registry
        from berth.services.lifecycle_service import up as lifecycle_up

        registry = get_registry()
        if "berth-dashboard" not in registry.projects:
            register_project(DASHBOARD_DIR)
            step("Dashboard registered")

        lifecycle_up("berth-dashboard")
        success("Dashboard running at https://berth.test")
    except Exception as exc:
        warn(f"Could not start dashboard: {exc}")
        warn("  Run manually: berth register <berth-src>/dashboard && berth up berth-dashboard")

    console.print()
    success("[bold]Berth setup complete![/]")
    console.print("  Dashboard:          [cyan]https://berth.test[/]")
    console.print("  Traefik dashboard:  http://localhost:8080")
    console.print("  Run [cyan]berth init[/] or [cyan]berth register <path>[/] to add a project.")
