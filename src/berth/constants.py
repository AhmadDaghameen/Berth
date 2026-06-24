APP_NAME = "berth"
TLD = "test"
BERTH_NET = "berth-net"
TRAEFIK_CONTAINER = "berth-traefik"
TRAEFIK_IMAGE = "traefik:v3.1"
HOSTS_MARKER_BEGIN = "# >>> berth managed (do not edit) >>>"
HOSTS_MARKER_END = "# <<< berth managed <<<"
PROJECT_CONFIG_FILE = "berth.project.yaml"
REGISTRY_FILE = "registry.yaml"
MANIFEST_DIR = "manifests"
CERTS_DIR = "certs"
TRAEFIK_DIR = "traefik"
LOGS_DIR = "logs"
DEFAULT_ENV = "local"
DEFAULT_KEEP_RELEASES = 10

# Shared infrastructure services available to all projects via `uses:` directive.
SHARED_SERVICES: dict[str, dict] = {
    "mailpit": {
        "image": "axllent/mailpit:latest",
        "container_name": "berth-shared-mailpit",
        "hostname": "mail.test",
        "http_port": 8025,   # Mailpit web UI
        "smtp_port": 1025,   # SMTP port for application use
        "description": "Local email testing — SMTP on :1025, web UI at mail.test",
    },
    "redis": {
        "image": "redis:7-alpine",
        "container_name": "berth-shared-redis",
        "hostname": None,    # TCP only — no HTTP route
        "port": 6379,
        "description": "Shared Redis cache/queue — redis://localhost:6379",
    },
}
