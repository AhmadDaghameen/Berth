"""Hosts file management with fenced berth-managed block.

On plain Linux/macOS, writes /etc/hosts.
On WSL2, writes both the WSL2 distro /etc/hosts AND the Windows hosts file
at /mnt/c/Windows/System32/drivers/etc/hosts so that *.test resolves in the
Windows browser as well.
"""
from __future__ import annotations

import os
from pathlib import Path

from berth.constants import HOSTS_MARKER_BEGIN, HOSTS_MARKER_END
from berth.exceptions import ElevationRequiredError
from berth.platform import current as platform


# ── WSL2 detection ─────────────────────────────────────────────────────────

def _is_wsl2() -> bool:
    """Return True when running inside a WSL2 distro."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
        return "microsoft" in version.lower() and "wsl2" in version.lower()
    except OSError:
        return False


def _windows_hosts_path() -> Path:
    """Path to the Windows hosts file as seen from WSL2."""
    # Respect WSL2 custom mount point; default is /mnt
    wsl_root = os.environ.get("WSL_INTEROP_PREFIX", "/mnt")
    return Path(wsl_root) / "c" / "Windows" / "System32" / "drivers" / "etc" / "hosts"


def _hosts_files() -> list[Path]:
    """Return all hosts files that need to be updated."""
    primary = platform.hosts_path
    files = [primary]
    if _is_wsl2():
        win_hosts = _windows_hosts_path()
        if win_hosts.exists() and win_hosts != primary:
            files.append(win_hosts)
    return files


# ── Low-level read / write ──────────────────────────────────────────────────

def _read(hosts_path: Path) -> str:
    return hosts_path.read_text(encoding="utf-8", errors="replace")


def _write(hosts_path: Path, content: str) -> None:
    if not platform.is_elevated():
        raise ElevationRequiredError()
    hosts_path.write_text(content, encoding="utf-8")


# ── Fence parsing ───────────────────────────────────────────────────────────

def _parse_fence(content: str) -> tuple[str, list[str], str]:
    """Split content into (before, managed_lines, after)."""
    before_parts: list[str] = []
    after_parts: list[str] = []
    managed: list[str] = []
    in_block = False
    after_block = False

    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")
        if stripped == HOSTS_MARKER_BEGIN:
            in_block = True
            continue
        if stripped == HOSTS_MARKER_END:
            in_block = False
            after_block = True
            continue
        if in_block:
            managed.append(stripped)
        elif after_block:
            after_parts.append(line)
        else:
            before_parts.append(line)

    return "".join(before_parts), managed, "".join(after_parts)


def _build_content(before: str, managed: list[str], after: str) -> str:
    if not managed:
        return before + after
    block = (
        HOSTS_MARKER_BEGIN + "\n"
        + "\n".join(managed) + "\n"
        + HOSTS_MARKER_END + "\n"
    )
    sep = "\n" if before and not before.endswith("\n") else ""
    return before + sep + block + after


# ── Internal single-file helpers ────────────────────────────────────────────

def _add_to_file(hosts_path: Path, hostnames: list[str]) -> None:
    content = _read(hosts_path) if hosts_path.exists() else ""
    before, managed_raw, after = _parse_fence(content)
    existing = {line.split()[-1] for line in managed_raw if line.strip()}
    for hostname in hostnames:
        if hostname not in existing:
            managed_raw.append(f"127.0.0.1 {hostname}")
    _write(hosts_path, _build_content(before, managed_raw, after))


def _remove_from_file(hosts_path: Path, hostnames: list[str]) -> None:
    if not hosts_path.exists():
        return
    content = _read(hosts_path)
    before, managed_raw, after = _parse_fence(content)
    to_remove = set(hostnames)
    managed_raw = [
        line for line in managed_raw
        if not any(line.endswith(h) for h in to_remove)
    ]
    _write(hosts_path, _build_content(before, managed_raw, after))


def _clear_file(hosts_path: Path) -> None:
    if not hosts_path.exists():
        return
    content = _read(hosts_path)
    before, _, after = _parse_fence(content)
    _write(hosts_path, before + after)


# ── Public API ──────────────────────────────────────────────────────────────

def get_managed_hosts() -> list[str]:
    hosts_path = platform.hosts_path
    if not hosts_path.exists():
        return []
    content = _read(hosts_path)
    _, managed, _ = _parse_fence(content)
    return [line for line in managed if line.strip() and not line.startswith("#")]


def add_hosts(hostnames: list[str]) -> None:
    """Add 127.0.0.1 entries for each hostname (idempotent, all relevant files)."""
    errors: list[str] = []
    for hosts_path in _hosts_files():
        try:
            _add_to_file(hosts_path, hostnames)
        except ElevationRequiredError:
            raise
        except OSError as exc:
            errors.append(f"{hosts_path}: {exc}")

    if errors:
        from berth.ui.console import warn
        for msg in errors:
            warn(f"Could not write hosts entry: {msg}")


def remove_hosts(hostnames: list[str]) -> None:
    """Remove entries for the given hostnames from all relevant files."""
    for hosts_path in _hosts_files():
        try:
            _remove_from_file(hosts_path, hostnames)
        except ElevationRequiredError:
            raise
        except OSError:
            pass  # best-effort removal


def clear_all_managed_hosts() -> None:
    """Remove the entire managed block from all relevant files (used by nuke)."""
    for hosts_path in _hosts_files():
        try:
            _clear_file(hosts_path)
        except ElevationRequiredError:
            raise
        except OSError:
            pass
