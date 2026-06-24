"""Berth dashboard — FastAPI backend."""
from __future__ import annotations

import json
from pathlib import Path

import docker as docker_sdk
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BERTH_DATA = Path("/berth-data")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Berth Dashboard", docs_url=None, redoc_url=None)


# ── helpers ──────────────────────────────────────────────────────────────────

def _registry() -> dict:
    p = BERTH_DATA / "registry.yaml"
    if not p.exists():
        return {"projects": {}}
    import yaml
    return yaml.safe_load(p.read_text()) or {"projects": {}}


def _manifest(project: str, env: str) -> dict:
    p = BERTH_DATA / "manifests" / f"{project}.{env}.json"
    if not p.exists():
        return {"project": project, "env": env, "services": {}, "releases": []}
    return json.loads(p.read_text())


def _project_config(project_path: str) -> dict:
    import yaml
    cfg = Path(project_path) / "berth.project.yaml"
    if not cfg.exists():
        return {}
    return yaml.safe_load(cfg.read_text()) or {}


def _docker_client():
    try:
        return docker_sdk.from_env()
    except Exception:
        return None


def _container_running(name: str) -> bool:
    client = _docker_client()
    if not client:
        return False
    try:
        c = client.containers.get(name)
        return c.status == "running"
    except docker_sdk.errors.NotFound:
        return False
    except Exception:
        return False


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "healthy", "service": "berth-dashboard"}


@app.get("/api/projects")
def list_projects():
    reg = _registry()
    projects = []
    for slug, entry in reg.get("projects", {}).items():
        cfg = _project_config(entry.get("path", ""))
        envs = cfg.get("environments", ["local"])
        project_data = {
            "slug": slug,
            "description": entry.get("description", ""),
            "path": entry.get("path", ""),
            "environments": envs,
            "services": [],
        }
        for env in envs:
            manifest = _manifest(slug, env)
            for svc_name, state in manifest.get("services", {}).items():
                container = state.get("container_name")
                live = _container_running(container) if container else False
                project_data["services"].append({
                    "project": slug,
                    "env": env,
                    "service": svc_name,
                    "version": state.get("version") or "—",
                    "url": f"https://{state['hostname']}" if state.get("hostname") else None,
                    "health": "running" if live else state.get("health", "stopped"),
                    "host_port": state.get("host_port"),
                    "container_name": container,
                    "deployed_at": state.get("deployed_at"),
                })
        projects.append(project_data)
    return {"projects": projects}


@app.get("/api/status")
def full_status():
    reg = _registry()
    rows = []
    for slug, entry in reg.get("projects", {}).items():
        cfg = _project_config(entry.get("path", ""))
        for env in cfg.get("environments", ["local"]):
            manifest = _manifest(slug, env)
            for svc_name, state in manifest.get("services", {}).items():
                container = state.get("container_name")
                live = _container_running(container) if container else False
                rows.append({
                    "project": slug,
                    "env": env,
                    "service": svc_name,
                    "version": state.get("version") or "—",
                    "url": f"https://{state['hostname']}" if state.get("hostname") else None,
                    "health": "running" if live else state.get("health", "stopped"),
                    "host_port": state.get("host_port"),
                    "deployed_at": state.get("deployed_at"),
                })
    return {"services": rows}


@app.get("/api/projects/{project}/history/{service}")
def service_history(project: str, service: str, env: str = "local"):
    manifest = _manifest(project, env)
    current_svc = manifest.get("services", {}).get(service, {})
    current_version = current_svc.get("version")
    releases = [
        r for r in reversed(manifest.get("releases", []))
        if r.get("image", "").startswith(f"berth/{project}-{service}:")
    ]
    for r in releases:
        r["current"] = r.get("version") == current_version
    return {"releases": releases}


@app.post("/api/projects/{project}/services/{service}/restart")
def restart_service(project: str, service: str, env: str = "local"):
    manifest = _manifest(project, env)
    state = manifest.get("services", {}).get(service)
    if not state or not state.get("container_name"):
        raise HTTPException(404, f"No running container for {project}/{service}")
    container_name = state["container_name"]
    client = _docker_client()
    if not client:
        raise HTTPException(503, "Docker socket unavailable")
    try:
        c = client.containers.get(container_name)
        c.restart()
    except docker_sdk.errors.NotFound:
        raise HTTPException(404, f"Container {container_name} not found")
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"restarted": container_name}


# ── static files ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
