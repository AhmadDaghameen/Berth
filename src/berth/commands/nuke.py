"""berth nuke — tear everything down cleanly."""
from __future__ import annotations

import typer

from berth.ui.console import console, error, info, success, warn

app = typer.Typer(help="Tear down all Berth-managed resources.")


@app.callback(invoke_without_command=True)
def nuke(
    keep_data: bool = typer.Option(False, "--keep-data", help="Keep Docker volumes (data)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Stop Traefik, remove all hosts entries, and optionally remove volumes."""
    if not yes:
        typer.confirm(
            "This will stop Traefik, remove all berth hosts entries, and clear manifests. Continue?",
            abort=True,
        )

    from berth.infra.traefik import stop_traefik
    from berth.infra.hosts import clear_all_managed_hosts
    from berth.exceptions import ElevationRequiredError

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
        warn(f"Could not clear hosts entries (elevation required): {exc}")
    except Exception as exc:
        warn(f"Could not clear hosts entries: {exc}")

    success("[bold]Berth nuked.[/] Run 'berth setup' to start fresh.")
