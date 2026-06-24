import sys

from .base import Platform

if sys.platform == "win32":
    from .windows import WindowsPlatform as _Impl
elif sys.platform == "darwin":
    from .macos import MacOSPlatform as _Impl
else:
    from .linux import LinuxPlatform as _Impl

current: Platform = _Impl()

__all__ = ["current", "Platform"]
