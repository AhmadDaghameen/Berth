"""Resolves all ~/.berth/ paths in one place."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from berth.constants import REGISTRY_FILE, MANIFEST_DIR, CERTS_DIR, TRAEFIK_DIR, LOGS_DIR


def _berth_home() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", Path.home()))
    else:
        base = Path.home()
    return base / ".berth"


class BerthPaths:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or _berth_home()

    @property
    def registry(self) -> Path:
        return self.home / REGISTRY_FILE

    @property
    def manifests(self) -> Path:
        return self.home / MANIFEST_DIR

    @property
    def certs(self) -> Path:
        return self.home / CERTS_DIR

    @property
    def traefik(self) -> Path:
        return self.home / TRAEFIK_DIR

    @property
    def logs(self) -> Path:
        return self.home / LOGS_DIR

    def manifest_path(self, project: str, env: str) -> Path:
        return self.manifests / f"{project}.{env}.json"

    def cert_path(self) -> Path:
        return self.certs / "berth.crt"

    def key_path(self) -> Path:
        return self.certs / "berth.key"

    def project_cert_path(self, project: str, env: str = "local") -> Path:
        if env == "local":
            return self.certs / f"{project}.crt"
        return self.certs / f"{project}.{env}.crt"

    def project_key_path(self, project: str, env: str = "local") -> Path:
        if env == "local":
            return self.certs / f"{project}.key"
        return self.certs / f"{project}.{env}.key"

    def traefik_dynamic_config(self) -> Path:
        return self.traefik / "dynamic.yml"

    def traefik_static_config(self) -> Path:
        return self.traefik / "traefik.yml"

    def ensure_dirs(self) -> None:
        for d in [self.home, self.manifests, self.certs, self.traefik, self.logs]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton-ish default paths instance
paths = BerthPaths()
