"""Abstract platform interface."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Platform(Protocol):
    @property
    def hosts_path(self) -> Path: ...

    def is_elevated(self) -> bool: ...

    def elevation_hint(self) -> str: ...

    def open_url(self, url: str) -> None: ...
