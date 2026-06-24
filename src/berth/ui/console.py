"""Rich console helpers."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console(highlight=False)


def success(msg: str) -> None:
    console.print(f"[bold green]OK[/]  {msg}")


def info(msg: str) -> None:
    console.print(f"[bold blue]-->[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"[bold yellow]WARN[/] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]ERR[/]  {msg}")


def step(msg: str) -> None:
    console.print(f"  [dim]-[/] {msg}")


def header(title: str) -> None:
    console.print(Panel(f"[bold]{title}[/]", box=box.ROUNDED, expand=False))


def url_link(url: str) -> str:
    return f"[link={url}][cyan]{url}[/][/link]"


def make_table(*columns: str, title: str | None = None) -> Table:
    t = Table(title=title, box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
    for col in columns:
        t.add_column(col)
    return t


def health_badge(status: str) -> str:
    badges = {
        "healthy": "[bold green][healthy][/]",
        "unhealthy": "[bold red][unhealthy][/]",
        "starting": "[bold yellow][starting][/]",
        "running": "[bold green][running][/]",
        "stopped": "[bold red][stopped][/]",
    }
    return badges.get(status, f"[dim][{status}][/]")
