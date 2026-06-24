class BerthError(Exception):
    """Base error for all Berth failures."""


class DockerUnavailableError(BerthError):
    def __init__(self) -> None:
        super().__init__(
            "Docker daemon is not reachable. Start Docker Desktop (or dockerd) and retry.\n"
            "  Verify: docker info"
        )


class ElevationRequiredError(BerthError):
    def __init__(self, action: str = "modify the hosts file") -> None:
        import sys

        if sys.platform == "win32":
            hint = "Re-run this command in an elevated (Administrator) terminal."
        else:
            hint = f"Re-run with: sudo berth {action}"
        super().__init__(
            f"Administrator / root privileges are required to {action}.\n  {hint}"
        )


class MkcertNotFoundError(BerthError):
    def __init__(self) -> None:
        super().__init__(
            "mkcert is not installed or not on PATH.\n"
            "  Install: https://github.com/FiloSottile/mkcert#installation\n"
            "  Windows (winget): winget install FiloSottile.mkcert\n"
            "  macOS (brew):     brew install mkcert"
        )


class ProjectNotFoundError(BerthError):
    def __init__(self, slug: str) -> None:
        super().__init__(
            f"Project '{slug}' is not registered.\n"
            "  Run: berth ls   (to see registered projects)\n"
            "       berth register <path>  (to add a project)"
        )


class ProjectConfigError(BerthError):
    """Invalid berth.project.yaml."""


class ServiceNotFoundError(BerthError):
    def __init__(self, service: str, project: str) -> None:
        super().__init__(f"Service '{service}' not found in project '{project}'.")
