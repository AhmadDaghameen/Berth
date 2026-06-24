# Berth — Work Plan & Build Status

> Last updated: 2026-06-23

---

## Docker Strategy — WSL2 + Docker Engine (Option 2)

**Decision:** Docker Desktop is not usable on this VM (no hardware virtualization). We will use **Docker Engine installed directly inside WSL2** — no daemon virtualization required, Docker runs as a native Linux process inside the WSL2 distro.

### WSL2 Setup Steps (one-time, must be done before `berth setup`)

Run these in PowerShell (admin) to install WSL2 and Ubuntu, then inside the WSL2 shell to install Docker Engine:

```powershell
# 1. Enable WSL2 (PowerShell — Admin)
wsl --install -d Ubuntu
# Reboot if prompted, then open Ubuntu from Start Menu to complete setup
```

```bash
# 2. Inside WSL2 (Ubuntu shell) — install Docker Engine
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Exit and re-open WSL2 shell to apply group membership

# 3. Start Docker daemon (WSL2 doesn't auto-start services)
sudo service docker start

# 4. Verify
docker ps
```

```powershell
# 5. In PowerShell — point Docker CLI at the WSL2 socket
# Add this to your PowerShell profile ($PROFILE) for persistence:
$env:DOCKER_HOST = "npipe:////./pipe/docker_engine"
# OR use the wsl socket bridge (if above doesn't work):
# $env:DOCKER_HOST = "unix:///var/run/docker.sock"
```

> **Note on `DOCKER_HOST`:** With Docker Engine in WSL2, the recommended bridge is to install
> the `wsl-docker` socket relay or use Docker CLI context. The simplest approach is to run
> `berth` commands from **inside the WSL2 shell** where the socket is native.

### Recommended Workflow on This Machine

Run `berth` commands from the **WSL2 Ubuntu terminal**, not from PowerShell:

```bash
# Inside WSL2
cd /mnt/c/Projects/Berth
pip install -e ".[dev]"
berth setup
berth register sample/demo
berth up demo
```

This avoids all socket bridging complexity — Docker, mkcert, Traefik, and the hosts file all work natively in the Linux environment.

> **Hosts file note (WSL2):** Inside WSL2, `/etc/hosts` is the WSL2 distro's hosts file, not
> `C:\Windows\System32\drivers\etc\hosts`. For `*.test` to resolve in the **Windows browser**,
> berth must also write to the Windows hosts file. The `berth up` command will attempt both.
> See the updated `hosts.py` task below.

### Impact on Traefik Volume Mounts

Running from inside WSL2, `~/.berth/` resolves to the WSL2 home (`/root/.berth/` or `/home/<user>/.berth/`). Docker Engine inside WSL2 mounts these as native Linux paths — **no path translation needed**. This resolves the previously noted volume mount uncertainty.

---

## Overall Phases

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 0 | WSL2 + Docker Engine setup | **Done** |
| Phase 1 | Routing foundation (setup, register, up/down/status/open) | **Done** |
| Phase 2 | Multi-service projects & release management | **Done** |
| Phase 3 | Environments & dashboard | **Done** |
| Phase 4 | Extensibility & shared infra | **Done** |

---

## Phase 1 — Routing Foundation

**Goal:** `berth setup` → `berth register` → `berth up demo` → `https://app.demo.test` loads in browser with trusted padlock.

### Completed

- [x] **Project scaffold** — `pyproject.toml`, `src/berth/` layout, `hatchling` build backend
- [x] **`berth` CLI entry point** — Typer app, all 15 commands wired, `berth --help` works
- [x] **Constants** — `APP_NAME`, `TLD`, `BERTH_NET`, `TRAEFIK_CONTAINER`, hosts markers, paths
- [x] **Exception hierarchy** — `BerthError`, `DockerUnavailableError`, `ElevationRequiredError`, `MkcertNotFoundError`, `ProjectNotFoundError`, `ProjectConfigError`
- [x] **Pydantic models**
  - `ProjectConfig` + `ServiceConfig` (parses `berth.project.yaml`)
  - `Registry` + `RegistryEntry` (parses `~/.berth/registry.yaml`)
  - `Manifest` + `ServiceState` + `ReleaseRecord`
- [x] **Storage layer** — `BerthPaths` (all `~/.berth/` paths), `yaml_store` (atomic load/save for registry, manifests, project config)
- [x] **Platform abstraction** — `Platform` protocol, `WindowsPlatform`, `MacOSPlatform`, `LinuxPlatform` (hosts path, elevation check, `open_url`)
- [x] **Infra — Docker** (`docker.py`) — `check_docker`, `ensure_network`, `container_exists/running`, `start/stop_container`, `compose_up/down`
- [x] **Infra — mkcert** (`mkcert.py`) — `check_mkcert`, `install_ca`, `generate_wildcard_cert`, `get_caroot`
- [x] **Infra — Hosts** (`hosts.py`) — fenced block read/write, `add_hosts`, `remove_hosts`, `clear_all_managed_hosts` (idempotent, elevation-aware)
- [x] **Infra — Traefik** (`traefik.py`) — static config generation, dynamic config generation (Docker labels + file provider), `start_traefik`, `stop_traefik`, `reload_dynamic_config`
- [x] **Rich UI console** — `success`, `info`, `warn`, `error`, `step`, `header`, `make_table`, `health_badge` (ASCII-safe for Windows legacy terminal)
- [x] **`berth setup`** — Docker check → dirs → mkcert CA → wildcard `*.test` cert → Traefik config → `berth-net` network → Traefik container start
- [x] **`berth init`** — scaffold `berth.project.yaml` with stack auto-detection (Node/Python/docker-compose hints)
- [x] **`berth register` / `unregister` / `ls`** — project registry CRUD
- [x] **`berth up` / `down`** — compose config generation, Docker Compose up/down, hosts entries, manifest persistence
- [x] **`berth status`** — Rich table of project/env/service/URL/health/host-port
- [x] **`berth ps` / `logs` / `open`** — container view, log streaming, browser launch
- [x] **`berth doctor`** — checks Docker, mkcert, CA, Traefik, ports 80/443, DNS, TLS cert
- [x] **`berth nuke`** — stop Traefik, clear hosts block, manifest cleanup
- [x] **Sample demo project** — `sample/demo/` with `berth.project.yaml`, `Dockerfile`, `app.py` (Python HTTP echo server on port 8000 with `/health`)
- [x] **README.md** — quickstart, .test TLD rationale, Windows DNS notes, phase roadmap
- [x] **Package installs** — `pip install -e .[dev]` succeeds; `berth --help` shows all 15 commands cleanly

### Remaining (Phase 1)

#### Pre-requisite — WSL2 environment
- [x] **WSL2 + Ubuntu installed**
- [x] **Docker Engine installed in WSL2** (via `scripts/setup-wsl2-docker.sh`)
- [x] **`berth` installed inside WSL2** — venv at `/opt/berth-env`
- [x] **mkcert installed inside WSL2**

#### Code fixes landed during Phase 1
- [x] **Dual hosts file write** (`infra/hosts.py`)
- [x] **`berth setup` — adds `berth.test` hosts entry**
- [x] **`berth up` — wait-for-healthy polling**
- [x] **WSL2 bootstrap script** (`scripts/setup-wsl2-docker.sh`)
- [x] **Traefik Docker provider removed** — switched to file-provider-only routing; Traefik v3.1 Docker client (API 1.24) was incompatible with Docker Engine's minimum (1.40)
- [x] **Per-project TLS certs** — `generate_project_cert(project)` generates `*.project.test`; called automatically by `berth up`; `_collect_certs()` in traefik.py includes all certs in dynamic config
- [x] **`_sync_traefik_routes()`** — rebuilds Traefik dynamic config from all active manifests on every `berth up`/`down`
- [x] **`ServiceState.container_port`** — stored in manifest so routes can be reconstructed without re-reading project config
- [x] **mkcert error surfacing** — `_run_mkcert` now raises with stderr detail instead of swallowing it
- [x] **Demo Dockerfile** — added curl for healthcheck

#### Acceptance demo — PASSED ✅
- [x] `berth setup` — all checks green
- [x] `berth register /mnt/c/Projects/Berth/sample/demo`
- [x] `berth up demo` — image builds, container starts, hosts entry added
- [x] Open `https://app.demo.test` in Windows browser — JSON response, no cert warnings
- [x] mkcert CA trusted in Windows via `certutil`

---

## Phase 2 — Multi-service Projects & Release Management

**Goal:** Full `financeiq`-shaped example (frontend + backend + worker + Postgres); `deploy`/`rollback`/`release`/`history` with versioned image tags.

### To Do

- [ ] **Multi-service compose generation** — `depends_on`, internal service-to-service routing (by container name on `berth-net`), worker services with `route: null`
- [ ] **`berth deploy <project> <service> --version`** — build/tag `berth/<project>-<service>:<version>`, start new container, wait-healthy, swap route, run `post_deploy` hook, record `ReleaseRecord` in manifest
- [ ] **`berth rollback <project> <service> [--to <version>]`** — redeploy retained image, update manifest
- [ ] **`berth release <project> <service> --version`** — build+tag without deploying
- [ ] **`berth history <project> <service>`** — chronological release timeline from manifest
- [ ] **`expose_host_port` tracking** — assign stable host ports, persist in manifest, show DB connection strings in status
- [ ] **`post_deploy` / `pre_deploy` hooks** — run shell commands inside the new container after healthy
- [ ] **Release image retention** — prune images older than N (default 10) per service
- [ ] **Sample FinanceIQ project** — multi-service `berth.project.yaml` (FastAPI + React + Postgres + worker) as acceptance demo

---

## Phase 3 — Environments & Dashboard

**Goal:** `local` and `staging` running simultaneously on distinct hostnames; dashboard at `https://berth.test`.

### To Do

- [ ] **`--env` isolation** — per-env compose project names, container names, networks, volumes, hostnames (`staging.financeiq.test`)
- [ ] **FastAPI dashboard backend** (`src/berth/dashboard/api.py`) — endpoints: `GET /api/projects`, `GET /api/status`, `POST /api/restart`, `POST /api/rollback`
- [ ] **React dashboard frontend** — project list → env tabs → service cards (version, URL, health badge, host-port connection string, release timeline); Vite build, served by FastAPI static files
- [ ] **`berth.test` route** — register dashboard as a Berth service on `berth.test` during setup
- [ ] **Acceptance test** — `local` + `staging` side-by-side, dashboard shows both with correct state

---

## Phase 4 — Extensibility & Shared Infra

**Goal:** `compose` import, `static` + `external` service types, Mailpit + Redis shared services.

### Completed

- [x] **`compose` service type** — `_build_compose_config()` reads and merges an existing `docker-compose.yml`, attaching all its services to `berth-net`
- [x] **`static` service type** — serves a directory via `nginx:alpine`; `berth up` injects the right volume mount, no Dockerfile needed
- [x] **`external` service type** — `up()` stores `external_url` in `ServiceState`; `_sync_traefik_routes()` and `generate_dynamic_config()` produce a Traefik file-provider route pointing to the host process
- [x] **Shared services** — `berth shared up|down|ls` commands; Mailpit at `mail.test`, Redis on `:6379`; shared routes auto-injected into Traefik when running
- [x] **`uses:` directive** — `berth up` auto-starts declared shared services before the project stack
- [x] **`berth doctor`** — reports running shared services
- [x] **Sample projects** — `sample/extdemo` (static + external), `sample/legacyapp` (compose import), `sample/maildemo` (uses: mailpit)

---

## Known Issues / Blockers

| Issue | Impact | Resolution |
|-------|--------|------------|
| WSL2 not yet set up on this machine | Blocks live acceptance test | Run `scripts/setup-wsl2-docker.sh` inside a WSL2 Ubuntu shell |
| Traefik volume mounts unverified | Traefik container may not start | Expected to work natively; needs first live run to confirm |

---

## File Tree (current state)

```
Berth/
├── pyproject.toml
├── README.md
├── WORK_PLAN.md                      <- this file
├── berth-build-prompt.md
├── sample/
│   └── demo/
│       ├── berth.project.yaml
│       ├── Dockerfile
│       └── app.py
└── src/
    └── berth/
        ├── __init__.py
        ├── __main__.py
        ├── cli.py                    <- all 15 commands
        ├── constants.py
        ├── exceptions.py
        ├── commands/                 <- (legacy stubs, inlined into cli.py)
        ├── models/
        │   ├── config.py             <- ProjectConfig, ServiceConfig
        │   ├── registry.py           <- Registry, RegistryEntry
        │   └── manifest.py           <- Manifest, ServiceState, ReleaseRecord
        ├── services/
        │   ├── setup_service.py      <- berth setup orchestration
        │   ├── registry_service.py   <- register/unregister/get
        │   └── lifecycle_service.py  <- up/down/status/open
        ├── infra/
        │   ├── docker.py             <- docker/compose subprocess wrappers
        │   ├── mkcert.py             <- CA install + cert generation
        │   ├── hosts.py              <- fenced hosts file management
        │   └── traefik.py            <- Traefik config + container management
        ├── platform/
        │   ├── base.py               <- Platform protocol
        │   ├── windows.py
        │   ├── macos.py
        │   └── linux.py
        ├── storage/
        │   ├── paths.py              <- BerthPaths (~/.berth/ layout)
        │   └── yaml_store.py         <- atomic YAML/JSON I/O
        └── ui/
            └── console.py            <- Rich helpers (ASCII-safe for Windows)
```
