"""berth init — interactively scaffold berth.project.yaml."""
from __future__ import annotations

from pathlib import Path

import typer

from berth.constants import PROJECT_CONFIG_FILE
from berth.ui.console import console, info, success, warn

app = typer.Typer(help="Scaffold a berth.project.yaml in the current directory.")

_TEMPLATE = """\
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


@app.callback(invoke_without_command=True)
def init(
    directory: str = typer.Argument(".", help="Directory to scaffold in (default: current dir)."),
) -> None:
    """Interactively scaffold a berth.project.yaml."""
    target = Path(directory).resolve()
    config_path = target / PROJECT_CONFIG_FILE

    if config_path.exists():
        warn(f"{PROJECT_CONFIG_FILE} already exists. Edit it directly.")
        raise typer.Exit()

    # Auto-detect stack hints
    hints: list[str] = []
    if (target / "package.json").exists():
        hints.append("Node.js (package.json detected)")
    if (target / "pyproject.toml").exists() or (target / "requirements.txt").exists():
        hints.append("Python (pyproject.toml/requirements.txt detected)")
    if (target / "docker-compose.yml").exists() or (target / "docker-compose.yaml").exists():
        hints.append("Existing docker-compose.yml detected — consider 'type: compose'")

    info(f"Scaffolding in {target}")
    if hints:
        for h in hints:
            console.print(f"  [dim]Detected: {h}[/]")

    slug = typer.prompt("Project slug (e.g. myapp)", default=target.name.lower().replace(" ", "-"))
    description = typer.prompt("Short description", default="")

    config_path.write_text(_TEMPLATE.format(slug=slug, description=description), encoding="utf-8")
    success(f"Created {config_path}")
    console.print(f"\n  Edit [cyan]{PROJECT_CONFIG_FILE}[/] to configure your services, then run:")
    console.print(f"    [bold]berth register .[/]")
    console.print(f"    [bold]berth up {slug}[/]")
