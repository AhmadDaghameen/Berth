# Berth — How-To Guide

> Stable `*.test` HTTPS URLs, trusted TLS, and deploy/rollback for every local Docker project.

---

## Table of Contents

1. [Installation](#installation)
2. [One-time setup](#one-time-setup)
3. [Adding Berth to a project](#adding-berth-to-a-project)
4. [Service types](#service-types)
5. [Multi-service projects](#multi-service-projects)
6. [Environments](#environments)
7. [Release management](#release-management)
8. [Shared services](#shared-services)
9. [Dashboard](#dashboard)
10. [CLI reference](#cli-reference)
11. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

| Requirement | Install |
|---|---|
| WSL2 Ubuntu | `wsl --install -d Ubuntu` (PowerShell Admin) |
| Docker Engine | `curl -fsSL https://get.docker.com \| sh` (inside WSL2) |
| mkcert | `sudo apt install mkcert` or download from [GitHub](https://github.com/FiloSottile/mkcert) |
| Python 3.11+ | Ships with Ubuntu 22.04+ |
| pipx | `sudo apt install pipx` |

### Install Berth

```bash
pipx install git+https://github.com/AhmadDaghameen/Berth.git@v0.1.0
```

Or from the latest commit on main:

```bash
pipx install git+https://github.com/AhmadDaghameen/Berth.git
```

> **Note:** On Ubuntu 24.04, use a venv if pipx isn't available:
> ```bash
> python3 -m venv /opt/berth-env
> /opt/berth-env/bin/pip install git+https://github.com/AhmadDaghameen/Berth.git@v0.1.0
> # then use: sudo /opt/berth-env/bin/berth <cmd>
> ```

---

## One-time setup

Run once after installing Berth:

```bash
sudo berth setup
```

This does:
1. Checks Docker daemon is reachable
2. Installs the mkcert local CA
3. Generates a `*.test` wildcard TLS cert
4. Writes Traefik static config
5. Starts the `berth-traefik` container (ports 80 + 443)
6. Creates `berth-net` Docker network
7. Starts the management dashboard at `https://berth.test`

### Trust the CA in Windows (for the browser)

Run once in PowerShell (Admin):

```powershell
$caroot = wsl -d Ubuntu sudo mkcert -CAROOT
certutil -addstore -f "ROOT" "\\wsl$\Ubuntu$caroot\rootCA.pem"
```

### DNS

Berth manages `/etc/hosts` entries automatically. For wildcard DNS (no per-hostname entries), configure [Acrylic DNS](https://mayakron.altervista.org/support/acrylic/) on Windows with rule `*.test → 127.0.0.1`.

---

## Adding Berth to a project

### Step 1 — Create `berth.project.yaml`

Place this file in your project root:

```yaml
project: myapp                  # slug → hostnames: app.myapp.test
description: "My application"

environments:
  - local

services:
  web:
    type: dockerfile
    context: .
    container_port: 8000
    route: app
    default_route: true         # also routes myapp.test → this service
    healthcheck:
      path: /health
      interval: 5s
      timeout: 3s
      retries: 3
```

### Step 2 — Register

```bash
sudo berth register /path/to/project
# or from inside the project directory:
sudo berth register .
```

### Step 3 — Start

```bash
sudo berth up myapp
```

Berth builds images, starts containers, adds `app.myapp.test` to the hosts file, generates a TLS cert for `*.myapp.test`, and wires the Traefik route.

```
  https://app.myapp.test
  https://myapp.test
```

### Step 4 — Check status

```bash
berth status
berth doctor   # diagnose issues
```

---

## Service types

### `dockerfile` — Build from a Dockerfile

```yaml
services:
  api:
    type: dockerfile
    context: .                  # build context directory
    dockerfile: Dockerfile      # optional, relative to context
    container_port: 8000
    route: api
    healthcheck:
      path: /health
```

The `Dockerfile` must be in the specified context. Add `curl` for healthchecks:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
```

### `docker-image` — Pull from a registry

```yaml
services:
  db:
    type: docker-image
    image: postgres:16-alpine
    expose_host_port: true      # assign stable host port (for DB GUIs)
    env:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: myapp
    volumes:
      - myapp-db:/var/lib/postgresql/data
```

Named volumes (no leading `/` or `.`) are declared automatically in the compose file.

### `static` — Serve a directory via nginx

No Dockerfile needed. Berth generates an nginx:alpine container that mounts and serves the directory.

```yaml
services:
  web:
    type: static
    context: dist               # pre-built directory to serve
    container_port: 80
    route: app
    default_route: true
    healthcheck:
      path: /
```

Build your frontend first (e.g. `npm run build`), then `berth up`.

### `external` — Route to a process on the host

Creates a Traefik HTTPS route to a process running outside Docker — useful for a dev server started manually or a remote endpoint.

```yaml
services:
  devapi:
    type: external
    host: host.docker.internal  # resolves to host machine from inside Docker
    port: 3000
    scheme: http
    route: api
```

Start your process first:
```bash
python3 -m http.server 3000
# or: node server.js
```

Then `berth up` and `https://api.myapp.test` routes to it.

### `compose` — Import an existing `docker-compose.yml`

Merges services from an existing compose file into Berth's managed stack and attaches them to `berth-net`. Nothing in the original file needs to change.

```yaml
services:
  legacy:
    type: compose
    context: .                  # directory containing docker-compose.yml
```

Combine with other service types in the same `berth.project.yaml`:

```yaml
services:
  legacy:
    type: compose
    context: .

  web:
    type: static
    context: static
    container_port: 80
    route: app
    default_route: true
```

---

## Multi-service projects

### Full-stack example (FastAPI + React + Postgres + worker)

```yaml
project: myapp
description: "Full-stack application"

environments:
  - local

services:
  db:
    type: docker-image
    image: postgres:16-alpine
    expose_host_port: true
    env:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: myapp
    volumes:
      - myapp-db:/var/lib/postgresql/data

  api:
    type: dockerfile
    context: backend
    container_port: 8000
    route: api
    depends_on: [db]
    env:
      DATABASE_URL: postgresql://app:secret@db:5432/myapp
    healthcheck:
      path: /health
      interval: 5s
      timeout: 3s
      retries: 5

  worker:
    type: dockerfile
    context: backend
    depends_on: [db]
    env:
      DATABASE_URL: postgresql://app:secret@db:5432/myapp
    # No route — workers have no HTTP interface

  web:
    type: static
    context: frontend/dist
    container_port: 80
    route: app
    default_route: true
    depends_on: [api]
    healthcheck:
      path: /
```

Services address each other by name inside `berth-net`:
- `api` connects to `db:5432`
- `worker` connects to `db:5432`
- Frontend fetches from `https://api.myapp.test`

### CORS for multi-service projects

Never hardcode origins — use a regex that covers all environments:

```python
# FastAPI
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.test",
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)
```

### Derive API URL from hostname in the frontend

```js
// Works for all environments: local, staging, etc.
const apiBase = window.location.hostname.replace(/^app\./, 'api.');
const res = await fetch(`https://${apiBase}/api/data`);
```

---

## Environments

Run multiple isolated environments side by side.

```bash
# Start staging environment
sudo berth up myapp --env staging

# Start local environment  
sudo berth up myapp

# View both
berth status
```

| | Local | Staging |
|---|---|---|
| Hostname | `app.myapp.test` | `app.myapp.staging.test` |
| TLS cert | `*.myapp.test` | `*.myapp.staging.test` |
| Compose project | `berth-myapp` | `berth-myapp-staging` |
| Container names | `berth-myapp-web-1` | `berth-myapp-staging-web-1` |

### Per-environment `.env` files

```
.env              ← loaded in local
.env.staging      ← loaded in staging
```

In `berth.project.yaml`:

```yaml
services:
  api:
    type: dockerfile
    context: .
    env_file: .env              # Berth auto-checks .env.<envname> for non-local
```

### Tear down a specific environment

```bash
sudo berth down myapp --env staging
sudo berth down myapp --env staging --volumes  # also remove data volumes
```

---

## Release management

For `dockerfile` and `docker-image` services.

### Deploy a versioned release

```bash
# Build the image, deploy it, run healthcheck, record in history
sudo berth deploy myapp api --version 1.2.0
```

Berth:
1. Builds image tagged `berth/myapp-api:1.2.0`
2. Stops the old container
3. Starts the new container
4. Waits for health → if unhealthy, rolls back automatically
5. Runs `post_deploy` hook (if configured)
6. Records the release in the manifest

### Roll back

```bash
# Roll back to the previous release
sudo berth rollback myapp api

# Roll back to a specific version
sudo berth rollback myapp api --to 1.1.0
```

### History

```bash
sudo berth history myapp api
```

```
  Release history: myapp/api (local)

  Version   Deployed At            Git SHA   Image                  Current
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1.2.0     2026-06-24T10:30:00Z   a1b2c3d   berth/myapp-api:1.2.0  <-- current
  1.1.0     2026-06-23T14:00:00Z   e4f5g6h   berth/myapp-api:1.1.0
  1.0.0     2026-06-22T09:00:00Z   i7j8k9l   berth/myapp-api:1.0.0
```

### Post-deploy hooks

```yaml
services:
  api:
    type: dockerfile
    context: .
    container_port: 8000
    route: api
    hooks:
      post_deploy: "python manage.py migrate"
```

The hook runs inside the newly deployed container after it becomes healthy.

### Build without deploying

```bash
sudo berth release myapp api --version 1.3.0
# Produces image berth/myapp-api:1.3.0 (not deployed yet)
```

---

## Shared services

Berth ships two shared infrastructure services available to any project.

### Mailpit — local email testing

```bash
sudo berth shared up mailpit
```

- Web UI: `https://mail.test`
- SMTP: `localhost:1025` (from host), `berth-shared-mailpit:1025` (from containers)

### Redis

```bash
sudo berth shared up redis
```

- TCP: `localhost:6379` (from host), `redis://berth-shared-redis:6379` (from containers)

### List status

```bash
berth shared ls
```

### Auto-start with `uses:`

Declare dependencies in `berth.project.yaml` and Berth starts them automatically before your project:

```yaml
project: myapp
uses:
  - mailpit
  - redis

services:
  api:
    type: dockerfile
    context: .
    container_port: 8000
    route: api
    env:
      SMTP_HOST: berth-shared-mailpit
      SMTP_PORT: "1025"
      REDIS_URL: redis://berth-shared-redis:6379
```

---

## Dashboard

Available at `https://berth.test` after `berth setup`.

Shows:
- All registered projects and environments
- Service health badges (healthy / unhealthy / stopped)
- URLs and host ports
- Release history per service
- Restart button per service

The dashboard auto-refreshes every 15 seconds. It reads data from `~/.berth/` and queries the Docker socket.

---

## CLI reference

```
berth setup               Bootstrap Berth (run once)
berth init                Scaffold berth.project.yaml interactively
berth register <path>     Register a project
berth unregister <slug>   Remove a project from the registry
berth ls                  List registered projects

berth up <slug>           Build and start a project
  --env <name>            Target environment (default: local)

berth down <slug>         Stop a project
  --env <name>
  --volumes               Also remove data volumes

berth restart <slug>      Down then up
berth status [slug]       Show service table (all or one project)
berth ps                  Docker container view
berth logs <slug> <svc>   Stream logs
  -f / --follow
berth open <slug> [svc]   Open URL in browser

berth deploy <slug> <svc> --version <v>   Build, deploy, record
berth rollback <slug> <svc> [--to <v>]   Redeploy previous release
berth release <slug> <svc> --version <v> Build image without deploying
berth history <slug> <svc>               Show release timeline

berth shared ls           List shared services
berth shared up <name>    Start shared service (mailpit, redis)
berth shared down <name>  Stop shared service

berth doctor              Diagnose environment issues
berth nuke                Stop Traefik + clear all hosts entries
```

---

## Troubleshooting

### `berth up` — image not rebuilding

Force a rebuild:
```bash
sudo berth down myapp && sudo berth up myapp
```

### Browser shows certificate warning

The mkcert CA isn't trusted in Windows yet:
```powershell
# PowerShell (Admin)
$caroot = wsl -d Ubuntu sudo mkcert -CAROOT
certutil -addstore -f "ROOT" "\\wsl$\Ubuntu$caroot\rootCA.pem"
```

### `*.myapp.staging.test` shows cert warning

The per-env cert isn't generated yet. Running `berth up myapp --env staging` generates it automatically. Make sure `berth up` completes successfully at least once for that env.

### Service not reachable

1. `berth status` — check health column
2. `berth logs myapp web` — check container logs
3. `berth doctor` — check Traefik is running and ports 80/443 are bound
4. Check the hosts file has the entry: `grep myapp /etc/hosts` (WSL) and `grep myapp C:\Windows\System32\drivers\etc\hosts` (Windows)

### `external` service shows "not reachable"

Make sure the host process is running before `berth up`:
```bash
python3 -m http.server 9000   # in another terminal
sudo berth up myapp
```

`host.docker.internal` only resolves to the host machine from inside containers on Linux when the container is started with `--add-host host.docker.internal:host-gateway`. Berth handles this automatically for external services.

> **Note:** `host.docker.internal` may need manual setup on Linux. If the external service doesn't resolve, add to the service definition:
> ```yaml
> env:
>   HOST_IP: "172.17.0.1"  # Docker bridge gateway
> ```

### `berth doctor` fails on DNS

Add a hosts entry manually, or configure Acrylic DNS for wildcard `*.test → 127.0.0.1`.

### Traefik not starting

```bash
sudo berth nuke
sudo berth setup
```
