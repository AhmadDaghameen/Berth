from __future__ import annotations

import os
import subprocess
from pathlib import Path


class MacOSPlatform:
    @property
    def hosts_path(self) -> Path:
        return Path("/etc/hosts")

    def is_elevated(self) -> bool:
        return os.geteuid() == 0

    def elevation_hint(self) -> str:
        return "Re-run with: sudo berth <command>"

    def open_url(self, url: str) -> None:
        subprocess.Popen(["open", url])
