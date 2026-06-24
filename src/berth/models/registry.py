"""Pydantic models for ~/.berth/registry.yaml."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RegistryEntry(BaseModel):
    path: str
    description: str = ""


class Registry(BaseModel):
    projects: dict[str, RegistryEntry] = Field(default_factory=dict)
