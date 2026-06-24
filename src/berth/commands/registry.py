"""berth register / unregister / ls commands."""
from __future__ import annotations

from pathlib import Path

import typer

from berth.exceptions import BerthError
from berth.ui.console import console, error, info, success

app = typer.Typer(help="Manage the project registry.")


@app.command("register")
def register(
    path: str = typer.Argument(".", help="Path to the project directory (default: current dir)."),
) -> None:
    """Register a project containing berth.project.yaml."""
    from berth.services.registry_service import register_project

    try:
        slug = register_project(Path(path))
        success(f"Registered project '[bold]{slug}[/]'")
    except BerthError as exc:
        error(str(exc))
        raise typer.Exit(1)


@app.command("unregister")
def unregister(
    project: str = typer.Argument(..., help="Project slug to remove."),
) -> None:
    """Remove a project from the registry (does not delete source files)."""
    from berth.services.registry_service import unregister_project

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
    from berth.storage.yaml_store import load_project_config
    from berth.ui.console import make_table

    registry = get_registry()
    if not registry.projects:
        info("No projects registered. Run 'berth register <path>' to add one.")
        return

    table = make_table("Project", "Path", "Description", title="Registered Projects")
    for slug, entry in registry.projects.items():
        desc = entry.description or "—"
        table.add_row(f"[bold]{slug}[/]", entry.path, desc)

    console.print(table)
