import typer
from berth.services.setup_service import run_setup
from berth.exceptions import BerthError

app = typer.Typer(help="Bootstrap the Berth platform (run once).")


@app.callback(invoke_without_command=True)
def setup(
    skip_dns: bool = typer.Option(False, "--skip-dns", help="Skip DNS configuration hints."),
) -> None:
    """One-time bootstrap: Docker check, mkcert CA, wildcard cert, Traefik, DNS."""
    try:
        run_setup(skip_dns=skip_dns)
    except BerthError as exc:
        from berth.ui.console import error
        error(str(exc))
        raise typer.Exit(1)
