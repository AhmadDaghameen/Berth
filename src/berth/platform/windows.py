from __future__ import annotations

import ctypes
import os
import subprocess
from pathlib import Path


class WindowsPlatform:
    @property
    def hosts_path(self) -> Path:
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        return Path(system_root) / "System32" / "drivers" / "etc" / "hosts"

    def is_elevated(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
        except Exception:
            return False

    def elevation_hint(self) -> str:
        return (
            "Re-run this command in an elevated (Administrator) terminal.\n"
            "  Right-click Command Prompt / PowerShell → 'Run as administrator'"
        )

    def open_url(self, url: str) -> None:
        os.startfile(url)  # type: ignore[attr-defined]
