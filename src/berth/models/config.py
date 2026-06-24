"""Pydantic models for berth.project.yaml."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from berth.constants import DEFAULT_ENV

ServiceType = Literal["dockerfile", "docker-image", "compose", "static", "external"]


class HealthCheckConfig(BaseModel):
    path: str = "/health"
    interval: str = "5s"
    timeout: str = "3s"
    retries: int = 3


class HooksConfig(BaseModel):
    pre_deploy: str | None = None
    post_deploy: str | None = None


class ServiceConfig(BaseModel):
    type: ServiceType
    # dockerfile / compose / static
    context: str | None = None
    dockerfile: str | None = None
    # docker-image
    image: str | None = None
    # external
    host: str | None = None
    port: int | None = None
    scheme: str = "http"
    # common
    container_port: int | None = None
    command: list[str] | None = None
    route: str | None = None
    hostname_override: str | None = None  # use instead of generated route.project.test
    default_route: bool = False
    env_file: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list)
    expose_host_port: bool = False
    healthcheck: HealthCheckConfig | None = None
    hooks: HooksConfig | None = None
    depends_on: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_type_fields(self) -> "ServiceConfig":
        if self.type == "dockerfile" and self.context is None:
            raise ValueError("dockerfile services must specify 'context'")
        if self.type == "docker-image" and self.image is None:
            raise ValueError("docker-image services must specify 'image'")
        if self.type == "external" and (self.host is None or self.port is None):
            raise ValueError("external services must specify 'host' and 'port'")
        return self


class ProjectConfig(BaseModel):
    project: str
    description: str = ""
    environments: list[str] = Field(default_factory=lambda: [DEFAULT_ENV])
    uses: list[str] = Field(default_factory=list)
    services: dict[str, ServiceConfig]

    @model_validator(mode="after")
    def ensure_default_env(self) -> "ProjectConfig":
        if DEFAULT_ENV not in self.environments:
            self.environments.insert(0, DEFAULT_ENV)
        return self

    def hostname(self, route: str, env: str = DEFAULT_ENV) -> str:
        """Return the full hostname for a route in a given environment."""
        from berth.constants import TLD

        if env == DEFAULT_ENV:
            return f"{route}.{self.project}.{TLD}"
        return f"{route}.{self.project}.{env}.{TLD}"

    def bare_hostname(self, env: str = DEFAULT_ENV) -> str:
        """Return the bare project hostname (for default_route)."""
        from berth.constants import TLD

        if env == DEFAULT_ENV:
            return f"{self.project}.{TLD}"
        return f"{self.project}.{env}.{TLD}"
