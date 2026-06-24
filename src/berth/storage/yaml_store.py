"""Atomic YAML/JSON read-write helpers for Berth state files."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from berth.constants import PROJECT_CONFIG_FILE
from berth.exceptions import ProjectConfigError
from berth.models.config import ProjectConfig
from berth.models.manifest import Manifest
from berth.models.registry import Registry
from berth.storage.paths import paths


def load_registry() -> Registry:
    if not paths.registry.exists():
        return Registry()
    raw = yaml.safe_load(paths.registry.read_text(encoding="utf-8")) or {}
    return Registry.model_validate(raw)


def save_registry(registry: Registry) -> None:
    paths.ensure_dirs()
    data = registry.model_dump()
    paths.registry.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def load_project_config(project_dir: Path) -> ProjectConfig:
    config_path = project_dir / PROJECT_CONFIG_FILE
    if not config_path.exists():
        raise ProjectConfigError(
            f"No '{PROJECT_CONFIG_FILE}' found in {project_dir}.\n"
            "  Run: berth init   (to scaffold one)"
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return ProjectConfig.model_validate(raw)
    except Exception as exc:
        raise ProjectConfigError(f"Invalid {PROJECT_CONFIG_FILE}: {exc}") from exc


def load_manifest(project: str, env: str) -> Manifest:
    p = paths.manifest_path(project, env)
    if not p.exists():
        return Manifest(project=project, env=env)
    raw = json.loads(p.read_text(encoding="utf-8"))
    return Manifest.model_validate(raw)


def save_manifest(manifest: Manifest) -> None:
    paths.ensure_dirs()
    p = paths.manifest_path(manifest.project, manifest.env)
    p.write_text(
        manifest.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
