"""berth doctor — diagnose environment problems."""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import typer

from berth.constants import TRAEFIK_CONTAINER
from berth.infra.docker import container_running
from berth.infra.mkcert import check_mkcert, get_caroot
from berth.platform import current as platform
from berth.ui.console import console, error, info, step, success, warn

app = typer.Typer(help="Diagnose Berth environment issues.")


def _check(label: str, ok: bool, ok_msg: str, fail_msg: str) -> bool:
    if ok:
        success(f"{label}: {ok_msg}")
    else:
        error(f"{label}: {fail_msg}")
    return ok


@app.callback(invoke_without_command=True)
def doctor() -> None:
    """Run environment diagnostics and report any issues."""
    console.rule("[bold]Berth Doctor[/]")
    all_ok = True

    # 1. Docker
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        ok = result.returncode == 0
    except Exception:
        ok = False
    all_ok &= _check("Docker", ok, "daemon reachable", "daemon NOT reachable — start Docker Desktop")

    # 2. mkcert
    mkcert_ok = check_mkcert()
    all_ok &= _check("mkcert", mkcert_ok, "installed", "NOT found — run: winget install FiloSottile.mkcert")

    # 3. mkcert CA trusted
    if mkcert_ok:
        caroot = get_caroot()
        ca_ok = caroot is not None and (caroot / "rootCA.pem").exists()
        all_ok &= _check(
            "mkcert CA",
            ca_ok,
            f"installed ({caroot})",
            "CA not found — run: berth setup",
        )

    # 4. Traefik running
    traefik_ok = container_running(TRAEFIK_CONTAINER)
    all_ok &= _check(
        "Traefik", traefik_ok, "container running", "NOT running — run: berth setup"
    )

    # 5. Ports 80 / 443
    for port in (80, 443):
        try:
            with socket.socket() as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", port))
            port_ok = True
        except (ConnectionRefusedError, OSError):
            port_ok = False

        if traefik_ok:
            all_ok &= _check(
                f"Port {port}",
                port_ok,
                "bound (Traefik is listening)",
                "nothing listening — Traefik may have failed to start",
            )
        else:
            if port_ok:
                warn(f"Port {port}: something else is listening — will conflict with Traefik")
                all_ok = False
            else:
                step(f"Port {port}: free (Traefik not started yet)")

    # 6. DNS resolution — does *.test resolve to 127.0.0.1?
    test_host = "berth-doctor-probe.test"
    try:
        ip = socket.gethostbyname(test_host)
        dns_ok = ip == "127.0.0.1"
    except socket.gaierror:
        dns_ok = False
    all_ok &= _check(
        "DNS (*.test → 127.0.0.1)",
        dns_ok,
        "resolving correctly",
        f"'{test_host}' does NOT resolve — add hosts entry or configure dnsmasq/Acrylic",
    )

    # 7. Hosts file elevation
    hosts = platform.hosts_path
    hosts_writable = hosts.exists() and platform.is_elevated()
    info(f"Hosts file: {hosts} {'(elevated)' if hosts_writable else '(not elevated — hosts writes need admin)'}")

    # 8. Berth certs
    from berth.storage.paths import paths

    cert_ok = paths.cert_path().exists() and paths.key_path().exists()
    all_ok &= _check(
        "TLS cert",
        cert_ok,
        f"found ({paths.certs})",
        "certs NOT found — run: berth setup",
    )

    console.print()
    if all_ok:
        success("[bold green]All checks passed. Berth is healthy.[/]")
    else:
        warn("[bold yellow]Some checks failed. See suggestions above.[/]")
        raise typer.Exit(1)
