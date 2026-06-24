"""CRUD operations on the global registry."""
from __future__ import annotations

from pathlib import Path

from berth.exceptions import ProjectConfigError, ProjectNotFoundError
from berth.models.registry import Registry, RegistryEntry
from berth.storage.yaml_store import load_registry, save_registry, load_project_config


def register_project(project_dir: Path) -> str:
    """
    Add the project at project_dir to the registry.
    Returns the project slug.
    """
    project_dir = project_dir.resolve()
    config = load_project_config(project_dir)
    slug = config.project

    registry = load_registry()
    if slug in registry.projects:
        existing = registry.projects[slug]
        if Path(existing.path).resolve() == project_dir:
            return slug  # idempotent
        raise ProjectConfigError(
            f"Project '{slug}' is already registered at a different path: {existing.path}\n"
            "  Unregister it first: berth unregister {slug}"
        )

    registry.projects[slug] = RegistryEntry(
        path=str(project_dir),
        description=config.description,
    )
    save_registry(registry)
    return slug


def unregister_project(slug: str) -> None:
    registry = load_registry()
    if slug not in registry.projects:
        raise ProjectNotFoundError(slug)
    del registry.projects[slug]
    save_registry(registry)


def get_registry() -> Registry:
    return load_registry()


def get_project_path(slug: str) -> Path:
    registry = load_registry()
    if slug not in registry.projects:
        raise ProjectNotFoundError(slug)
    return Path(registry.projects[slug].path)
