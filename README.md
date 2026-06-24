# Berth

**Berth** is a local release and deployment manager. It gives every project's services a stable, human-readable HTTPS hostname and proper release semantics — versions, environments, deploy, rollback — instead of the usual mess of `localhost:3000`, `localhost:8000`, and remembered-by-accident ports.

## Quickstart

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with WSL2 backend on Windows)
- [mkcert](https://github.com/FiloSottile/mkcert) — `winget install FiloSottile.mkcert` (Windows) / `brew install mkcert` (macOS)
- Python 3.11+

### 2. Install Berth

```sh
pipx install git+https://github.com/AhmadDaghameen/Berth.git
```

Or pin to a release:

```sh
pipx install git+https://github.com/AhmadDaghameen/Berth.git@v0.1.0
```

### 3. Bootstrap

```sh
berth setup
```

This installs the mkcert CA, generates a wildcard `*.test` certificate, starts the Traefik reverse proxy on ports 80/443, and creates the `berth-net` Docker network.

### 4. Register a project

```sh
# In a directory containing berth.project.yaml:
berth register .

# Or scaffold a new one:
berth init
```

### 5. Start a project

```sh
berth up myproject
```

Berth builds images, starts containers, adds hosts entries for all routes, and prints the HTTPS URLs — all with a trusted padlock, no manual port management.

```
  https://app.myproject.test
  https://api.myproject.test
```

### 6. Check status

```sh
berth status
berth doctor     # diagnose issues
```

## .test TLD rationale

Berth uses the reserved `.test` TLD (RFC 2606). Do **not** use:

- `.dev` — HSTS-preloaded in browsers; causes HTTPS trust failures.
- `.local` — collides with mDNS/Bonjour on macOS/Linux.

`*.localhost` auto-resolves to 127.0.0.1 in Chromium/Firefox as a zero-config fallback, but subdomain nesting (e.g. `app.myproject.localhost`) is not universally supported.

## Windows DNS notes

By default, Berth manages hosts entries fenced between `# >>> berth managed <<<` markers.
Editing the hosts file requires an elevated (Administrator) terminal.

For a wildcard upgrade (no per-hostname hosts edits), install [Acrylic DNS Proxy](https://mayakron.altervista.org/support/acrylic/) and add a rule: `*.test → 127.0.0.1`.

## Dashboard

Once Berth is set up, the dashboard is available at `https://berth.test` (Phase 3).

## Phase roadmap

- **Phase 1** ✅ Routing foundation: setup, register, up/down/status/open
- **Phase 2** ✅ Multi-service projects, release management (deploy/rollback/history)
- **Phase 3** ✅ Environments & dashboard
- **Phase 4** ✅ Compose import, static/external service types, shared infra (Mailpit, Redis)
