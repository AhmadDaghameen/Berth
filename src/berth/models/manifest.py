"""Per-environment deployment manifest stored in ~/.berth/manifests/<project>.<env>.json."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ServiceState(BaseModel):
    service: str
    version: str | None = None
    image: str | None = None
    container_name: str | None = None
    container_port: int | None = None
    external_url: str | None = None  # for external service type routing
    route: str | None = None
    hostname: str | None = None
    bare_hostname: str | None = None  # project.test bare route when default_route: true
    host_port: int | None = None
    health: str = "unknown"  # healthy | unhealthy | starting | unknown
    deployed_at: datetime | None = None
    uptime_seconds: float | None = None


class ReleaseRecord(BaseModel):
    version: str
    image: str
    deployed_at: datetime
    env: str
    git_sha: str | None = None


class Manifest(BaseModel):
    project: str
    env: str
    services: dict[str, ServiceState] = Field(default_factory=dict)
    releases: list[ReleaseRecord] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
