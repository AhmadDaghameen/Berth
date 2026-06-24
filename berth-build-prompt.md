# Claude Code Build Prompt — "Berth": A Local Release & Deployment Manager

## Role & objective

You are building **Berth**, a command-line + dashboard tool that manages local releases of local projects. It gives every project's services (frontend, backend, database, workers, etc.) a stable, human-readable HTTPS hostname and proper release semantics — versions, environments, deploy, rollback — instead of the usual mess of `localhost:3000`, `localhost:8000`, `127.0.0.1:5432`, and remembered-by-accident ports.

`Berth` is the **working name**; expose it as a single constant (`APP_NAME = "berth"`) so it can be renamed in one place. The CLI command is `berth`.

### Design philosophy (read this first — it constrains everything)

Berth is a **thin, smart glue layer**, not a from-scratch platform. Do **not** reinvent a reverse proxy, a TLS engine, a DNS server, or a container runtime. Instead orchestrate best-in-class tools:

- **Traefik** — dynamic reverse proxy and router (Docker-label provider + file provider).
- **mkcert** — locally-trusted CA and wildcard certificates so HTTPS just works.
- **Docker / Docker Compose** — container lifecycle and a shared per-project network.
- **dnsmasq** (macOS/Linux) / **Acrylic DNS Proxy** (Windows) / managed hosts file — name resolution.

Berth's own code is the orchestration, the configuration model, the **release tracking**, the **CLI/UX**, and a small **dashboard**. Everything else is delegated. If you find yourself writing an HTTP proxy or a certificate authority, stop — wire up the tool above instead.

---

## Problem statement

The developer runs many local projects simultaneously (e.g. FinanceIQ PEX, a TypeScript monorepo, internal tools, integration sandboxes). Today each service binds an arbitrary host port, services find each other by hardcoded `localhost:PORT`, port collisions are common, HTTPS is absent or untrusted, and there is no concept of "which version is running where."

Berth solves this end to end:

- **Externally**, every service is reachable at a stable URL like `https://app.financeiq.test` or `https://api.financeiq.test` — no ports, real trusted HTTPS.
- **Internally**, services in a project share a Docker network and resolve each other by name (`backend` reaches `db` at `db:5432`), so the "random IP" problem disappears inside the stack too.
- **Operationally**, each deployable build is versioned; you can deploy a specific version to an environment and roll back; Berth records the full release history and current state.

---

## Target environment

- **Cross-platform, Windows-first.** Primary target is Windows 10/11 with **Docker Desktop on the WSL2 backend**; must also work on macOS and Linux. Detect the OS and branch where behavior differs (DNS setup, hosts path, elevation).
- Assume Docker and Docker Compose v2 are installed and the daemon is reachable. Detect and fail with a clear message if not.
- Use the reserved TLD **`.test`** for all hostnames. Do **not** use `.dev` (HSTS-preloaded, forces HTTPS pre-trust and causes confusing failures) or `.local` (collides with mDNS/Bonjour). Mention in docs that `*.localhost` auto-resolves to 127.0.0.1 in Chromium/Firefox as a zero-config fallback.
- Store all Berth state under a home directory: `~/.berth/` (Linux/macOS) / `%USERPROFILE%\.berth\` (Windows): global registry, per-environment manifests, generated Traefik config, certificates, and logs.

---

## Core concepts & terminology

Model these explicitly in code (dataclasses / Pydantic models) and in the docs:

- **Project** — a unit the developer works on (e.g. `financeiq`). Has a slug, a source directory, and one or more services. Owns a hostname namespace (`*.financeiq.test`).
- **Service** — a deployable component of a project (`frontend`, `backend`, `db`, `worker`, …). Has a **type** (see service types below), a routing rule, and optional health check.
- **Environment** — a named, isolated instance of a project's stack: `local` (default), `staging`, `preview`, etc. Each environment gets its own hostname prefix and its own running stack. `local` → `financeiq.test`; `staging` → `staging.financeiq.test`.
- **Release** — an immutable, tagged build of a service (semver and/or git SHA), realized as a tagged Docker image, e.g. `berth/financeiq-backend:1.4.2`. Releases are retained so rollback is possible.
- **Route** — the mapping `https://<host>` → a service's container/port, materialized as Traefik configuration. Berth generates routes; the developer never assigns host ports by hand.

---

## Configuration model

Two layers, both human-editable YAML, both validated with clear error messages.

### 1. Per-project config — `berth.project.yaml` (lives in the project repo)

Provide this **annotated worked example** in the docs (shaped like a real FastAPI + React + Postgres + worker app):

```yaml
# berth.project.yaml
project: financeiq
description: "Financial analytics platform for PEX-listed securities"

# Hostname namespace -> https://<route>.financeiq.test
# 'local' is the default environment; others are opt-in.
environments:
  - local
  - staging

# Optional shared infrastructure this project depends on (see shared services)
uses:
  - mailpit        # local SMTP capture for email-integration testing

services:
  frontend:
    type: dockerfile            # build from a Dockerfile in context
    context: ./web
    container_port: 3000
    route: app                  # -> https://app.financeiq.test
    default_route: true         # bare https://financeiq.test also points here

  backend:
    type: dockerfile
    context: ./api
    container_port: 8000
    route: api                  # -> https://api.financeiq.test
    env_file: ./api/.env.local  # never committed; injected at deploy
    healthcheck:
      path: /health
      interval: 5s
    hooks:
      post_deploy: "alembic upgrade head"   # run migrations after deploy

  worker:
    type: dockerfile
    context: ./api
    command: ["python", "-m", "worker"]
    route: null                 # no inbound route; internal only

  db:
    type: docker-image
    image: postgres:16
    container_port: 5432
    route: null
    # Optionally publish a STABLE host port for GUI tools (DBeaver/psql).
    # Berth assigns and tracks it to avoid collisions; shown in the dashboard.
    expose_host_port: true
    env:
      POSTGRES_USER: financeiq
      POSTGRES_PASSWORD: localdev
      POSTGRES_DB: financeiq
    volumes:
      - financeiq-db-data:/var/lib/postgresql/data
```

### 2. Global registry — `~/.berth/registry.yaml`

Tracks which projects are registered and where their source lives. Managed by `berth register` / `berth unregister`; the developer rarely edits it by hand.

```yaml
projects:
  financeiq:
    path: C:\Projects\financeiq
  internal-tools:
    path: C:\Projects\internal-tools
```

### Service types (this is the "prepare for any requirements" extensibility surface)

Implement as a small strategy/plugin set so new types are easy to add:

- `dockerfile` — build an image from a Dockerfile + context.
- `docker-image` — run a prebuilt image (e.g. `postgres:16`, `redis:7`).
- `compose` — import services from an existing `docker-compose.yml` and attach Berth routing/labels (lets existing projects onboard with near-zero changes).
- `static` — serve a built frontend directory (e.g. a Vite/Next export) via a lightweight static server container.
- `external` — **do not run a container**; create a route/record that proxies to a process or host the developer runs elsewhere: a native dev server, or a remote/native database such as an existing **SQL Server** instance. Fields: `host`, `port`, optional `scheme`. This makes Berth a single front door even for things outside Docker.

---

## CLI specification

Use a typed CLI framework. Every command must be idempotent where sensible, give actionable errors, and never silently leave the system in a half-state.

Project lifecycle:
- `berth init` — interactively scaffold a `berth.project.yaml` in the current directory. Auto-detect stack hints: `package.json` → node frontend; `pyproject.toml`/`requirements.txt` → python backend; existing `docker-compose.yml` → offer to import services as `compose`.
- `berth register [PATH]` — add a project (containing `berth.project.yaml`) to the global registry.
- `berth unregister <project>` — remove from registry (does not delete source).
- `berth ls` — list registered projects and their environments.

Run / deploy:
- `berth up <project> [--env local]` — build (if needed), start the environment's stack, wire routes, wait for healthy. Print the resulting URLs.
- `berth down <project> [--env local]` — stop the stack; remove routes; keep data volumes.
- `berth restart <project> [--env local] [service]`
- `berth deploy <project> <service> --version <semver|sha> [--env staging]` — build/tag the release image, deploy it to the target environment, run hooks, health-check, and record it in the manifest.
- `berth rollback <project> <service> [--to <version>] [--env staging]` — redeploy a previously built release (defaults to the immediately previous one).
- `berth release <project> <service> --version <x.y.z>` — build and tag a release image **without** deploying (so it's available to deploy/rollback later).

Visibility:
- `berth status [project]` — table of every project/environment/service: version, URL (clickable), health, exposed host ports, uptime.
- `berth ps` — underlying container view.
- `berth logs <project> <service> [--env] [-f]`
- `berth open <project> [service]` — open the service URL in the default browser.
- `berth history <project> <service> [--env]` — chronological release history with timestamps and what is currently live.

Platform / housekeeping:
- `berth setup` — one-time bootstrap: verify Docker, install/trust the mkcert CA, generate the wildcard `*.test` cert, start the Traefik container, and configure DNS (see below). Re-runnable and idempotent.
- `berth doctor` — diagnose environment problems (Docker down, mkcert CA not trusted, DNS not resolving `*.test`, port 80/443 occupied) and suggest fixes.
- `berth nuke [--keep-data]` — tear everything down cleanly (routes, Traefik, hosts entries, optionally volumes). Must be fully reversible — never leave orphaned hosts lines or certs.

---

## Release management semantics

This is what makes Berth a *release* manager rather than just a proxy. Implement carefully:

- **Tagging.** A release is a Docker image tagged `berth/<project>-<service>:<version>`. `version` is a semver the developer supplies, optionally suffixed/aliased with the short git SHA when the source is a git repo. Keep the last N releases per service (configurable, default 10) and prune older ones.
- **Environments are isolated stacks.** `local` and `staging` of the same project run side by side with distinct hostnames, distinct container names/networks, and distinct volumes. Deploying to one never touches the other.
- **Manifests.** Persist current state per environment in `~/.berth/manifests/<project>.<env>.json` (or a small SQLite DB if cleaner): for each service, the live version, image digest, deployed-at timestamp, health, exposed host port, and route. This is the source of truth for `status`, `history`, and `rollback`.
- **Deploy is atomic-ish.** Build/pull → start new container(s) → wait for healthy → swap route → stop old. If health fails, do **not** swap the route; report the failure and leave the previous version serving. Run `post_deploy` hooks (e.g. DB migrations) after the new container is healthy but before declaring success.
- **Rollback** simply redeploys a retained release image and updates the manifest. It must be fast because the image already exists.

---

## Reverse proxy, DNS & TLS

### Traefik (routing)
Run Traefik as a Berth-managed container that owns host ports **80** and **443** (the only host ports anyone binds). Use the **Docker provider** (Berth attaches Traefik labels to each routed service so routing is dynamic as stacks come and go) plus the **file provider** for `external` service routes and the wildcard TLS cert. Individual services expose **no** host ports except optional, Berth-tracked `expose_host_port` cases for DB/GUI access. Put all Berth-managed containers on a shared Docker network (`berth-net`) so Traefik can reach them and so intra-project services resolve each other by name.

### mkcert (TLS)
During `berth setup`, run `mkcert -install` to create and trust a local CA, then issue a wildcard cert for `*.test` (and `*.financeiq.test` style per-project wildcards if a single wildcard is insufficient on the platform). Point Traefik's file provider at the generated cert/key. Result: `https://app.financeiq.test` is green-padlock trusted with no per-browser warnings.

### DNS / name resolution
Make `*.test` resolve to `127.0.0.1`. Branch by platform:
- **Default everywhere (zero extra deps): managed hosts file.** Berth writes explicit `127.0.0.1 <host>` lines for each active route, fenced between markers:
  ```
  # >>> berth managed (do not edit) >>>
  127.0.0.1 app.financeiq.test
  127.0.0.1 api.financeiq.test
  # <<< berth managed <<<
  ```
  Add/remove lines as routes come and go; never touch anything outside the fence; restore cleanly on `nuke`. Editing the hosts file needs elevation — **detect** missing privileges and tell the user exactly what to run (Windows: an elevated shell; macOS/Linux: `sudo`). Never fail silently.
- **Optional wildcard upgrade.** Document configuring **dnsmasq** (macOS/Linux) or **Acrylic DNS Proxy** (Windows) to resolve all of `*.test` → `127.0.0.1`, so new subdomains work without editing hosts at all. `berth doctor` should detect which mode is active and whether resolution actually works.

---

## Dashboard

A small local web app (served by Berth, reachable at `https://berth.test`) for visibility — this is the at-a-glance replacement for "which ports am I running again?"

- **Stack:** a FastAPI backend (reads the manifests/registry and shells to Docker) serving a minimal React frontend. Keep it self-contained; this is a utility UI, not a product.
- **Shows:** every project → environment → service, with live version, clickable HTTPS URL, health badge, exposed host port + ready-to-copy connection string (e.g. `postgresql://financeiq:localdev@localhost:<port>/financeiq`), uptime, and a recent-releases timeline per service.
- **Actions (nice-to-have, behind confirmation):** restart a service, roll back to a previous version, open logs.

---

## Shared services & cross-cutting features

- **Shared infra.** Support project-independent shared services a project can opt into via `uses:`. Ship at least: **Mailpit** (local SMTP sink + web UI at `https://mail.test`) for testing email integrations without sending real mail, and **Redis** as an optional shared cache/broker. Design so adding another shared service (e.g. MinIO) is trivial.
- **Secrets/env.** Per-service `env_file`/`env` injected at deploy time; never written into images or committed. `.env.local`, `.env.staging` conventions per environment.
- **Hooks.** `pre_deploy` / `post_deploy` shell commands run inside the service container (migrations, seeds).
- **Health & readiness.** Honor per-service healthchecks; `up`/`deploy` wait for healthy and surface failures clearly.

---

## Tech choices for Berth itself

- **Language:** Python (matches the developer's tooling and lets the CLI, the orchestration, and the FastAPI dashboard backend share one codebase). Use a typed CLI framework (e.g. Typer), Pydantic for config models, and either the Docker SDK for Python or well-wrapped `docker` / `docker compose` subprocess calls — pick one and be consistent, with robust error capture.
- **Packaging:** installable with `pipx`/`uv` as a single `berth` entry point. Provide a `pyproject.toml`.
- **Config & state:** YAML for human-edited config; JSON or SQLite for machine-managed manifests.

---

## Build in phases (verify each before moving on)

**Phase 1 — Routing foundation (must end in a working demo).**
`berth setup` (Docker check + mkcert CA + wildcard cert + Traefik container + DNS), plus `register` and a single-service `up`/`down`/`status`/`open`. Acceptance: register a tiny sample project (one Dockerfile service), run `berth up demo`, and load `https://app.demo.test` in a browser with a trusted padlock and no manual port.

**Phase 2 — Multi-service projects & release management.**
Full per-project schema (multiple services, internal network, healthchecks, hooks, `expose_host_port`), plus `deploy`/`rollback`/`release`/`history` with versioned image tags and persisted manifests. Acceptance: stand up the FinanceIQ-shaped example (frontend + backend + worker + Postgres); deploy backend `1.0.0`, then `1.1.0`, then roll back; confirm the route always served a healthy version and `history` is accurate.

**Phase 3 — Environments & dashboard.**
`--env` isolation (`local` vs `staging` side by side) and the FastAPI+React dashboard at `https://berth.test`. Acceptance: run `local` and `staging` of the same project simultaneously on distinct hostnames; dashboard shows both with correct versions, URLs, health, and DB connection strings.

**Phase 4 — Extensibility & shared infra.**
`compose` import, `static`, and `external` service types (prove `external` by routing to a host-run process and to a native/remote database endpoint), plus shared services (Mailpit, Redis) via `uses:`. Acceptance: onboard an existing project that has only a `docker-compose.yml` with minimal edits; route an `external` SQL Server endpoint through Berth; send a test email from a project and see it land in Mailpit.

---

## Constraints & guardrails

- **Don't reinvent** the proxy, CA, DNS server, or runtime — orchestrate Traefik/mkcert/dnsmasq-or-Acrylic/Docker.
- **Idempotent & reversible.** `setup`, `up`, route changes, and hosts edits must be safely re-runnable; `nuke` must leave no orphaned hosts lines, certs, containers, or networks.
- **Cross-platform correctness**, with explicit Windows handling for paths, hosts location, elevation, and DNS.
- **No surprise host ports.** Only Traefik binds 80/443; service host ports appear only via explicit, tracked `expose_host_port`.
- **Loud, actionable errors.** Docker down, port 80/443 taken, mkcert CA untrusted, DNS not resolving, missing elevation — each should produce a specific message and a suggested fix, ideally surfaced by `berth doctor`.
- **Security hygiene for a dev tool:** generated certs and `.env` files live under `~/.berth/` or the project and must be git-ignored; never embed secrets in images or logs.

## Deliverables

1. The installable `berth` CLI + dashboard, organized cleanly with the phased structure above.
2. A `README.md` quickstart: install → `berth setup` → `berth init`/`register` → `berth up` → open the URL, including the Windows DNS/elevation notes and the `.test` rationale.
3. The annotated `berth.project.yaml` example and a runnable sample project used in the Phase 1–2 acceptance demos.
4. `berth doctor` covering the common failure modes.

Start with Phase 1 and confirm the working browser demo before proceeding.
