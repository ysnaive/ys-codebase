"""
Core Platform - Cross-Platform Python Environment & Virtualenv Primitives.
"""

import os
import platform
import sys


def ensure_private_venv(yscb_root: str) -> None:
    """
    Ensures that the private virtual environment for the current Python interpreter
    version is added to sys.path, recursively parsing any host_venv.pth files.

    Args:
        yscb_root: Absolute or relative path to the YSCB project root directory.
    """
    tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    sys_name = platform.system()
    sub = (
        os.path.join(".venv", tag, "Lib", "site-packages")
        if sys_name == "Windows"
        else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    )
    site_pkg = os.path.join(yscb_root, sub)
    if os.path.isdir(site_pkg) and site_pkg not in sys.path:
        sys.path.insert(0, site_pkg)
        pth = os.path.join(site_pkg, "host_venv.pth")
        if os.path.isfile(pth):
            try:
                with open(pth, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        t = line.strip()
                        if t and os.path.isdir(t) and t not in sys.path:
                            sys.path.insert(0, t)
            except Exception:
                pass
