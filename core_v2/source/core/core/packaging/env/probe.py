"""Tiered virtual environment health probes: O(1) quick marker verification, deep subprocess import checks, and repair."""

from __future__ import annotations

import re
import time
from typing import Final, Optional, Sequence

from core.foundation.errors import safe_exception_summary
from core.foundation.observability import CancellationToken, require_non_negative_sec
from core.foundation.primitives import (
    HostPath,
    require_pure_bool,
    require_typed_tuple,
)
from core.foundation.proc import ManagedProcessTree, build_isolated_python_env
from core.packaging.env.pool import ImmutableVenvPool, env_repair_under_lock
from core.packaging.env.spec import (
    EnvBuildResult,
    EnvHealthReport,
    EnvSpec,
    env_quick_probe_issues,
)

_IMPORT_MODULE_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
_DEEP_PROBE_CODE: Final[str] = (
    "import sys\n"
    "if sys.prefix == sys.base_prefix:\n"
    "    sys.exit(2)\n"
    "for mod_name in sys.argv[1:]:\n"
    "    __import__(mod_name)\n"
)


def _validate_import_module_names(import_modules: Sequence[str]) -> tuple[str, ...]:
    names = require_typed_tuple(import_modules, str, "import_modules")
    for mod_name in names:
        if _IMPORT_MODULE_NAME_RE.fullmatch(mod_name) is None:
            raise ValueError(f"Invalid Python module path in import_modules: {mod_name!r}")
    return names


class EnvHealthProbe:
    """分級健康探針：日常 O(1) 標記檔快速檢查，異常或 env check 時才開子進程深度驗證。"""

    def __init__(self, pool: ImmutableVenvPool) -> None:
        if not isinstance(pool, ImmutableVenvPool):
            raise ValueError(f"pool must be ImmutableVenvPool, got {pool!r}")
        self._pool = pool

    def check_quick(self, spec: EnvSpec) -> EnvHealthReport:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        env_dir = self._pool.get_env_dir(spec)
        issues = env_quick_probe_issues(env_dir, spec)
        return EnvHealthReport(
            spec=spec,
            env_dir=env_dir,
            quick_ok=(len(issues) == 0),
            deep_import_ok=None,
            issues=issues,
        )

    def check_deep(
        self,
        spec: EnvSpec,
        *,
        import_modules: Sequence[str] = (),
        timeout_sec: float = 15.0,
    ) -> EnvHealthReport:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        validated_mods = _validate_import_module_names(import_modules)
        safe_timeout = require_non_negative_sec(timeout_sec, label="timeout_sec")
        quick_report = self.check_quick(spec)
        if not quick_report.quick_ok:
            return EnvHealthReport(
                spec=spec,
                env_dir=quick_report.env_dir,
                quick_ok=False,
                deep_import_ok=False,
                issues=quick_report.issues,
            )
        python_exe = self._pool.get_python_executable(spec)
        if python_exe is None:
            return EnvHealthReport(
                spec=spec,
                env_dir=quick_report.env_dir,
                quick_ok=False,
                deep_import_ok=False,
                issues=("Python executable became unavailable prior to deep probe.",),
            )
        deadline = time.monotonic() + safe_timeout
        if time.monotonic() >= deadline:
            return EnvHealthReport(
                spec=spec,
                env_dir=quick_report.env_dir,
                quick_ok=True,
                deep_import_ok=False,
                issues=(f"Deep health probe timed out after {safe_timeout:.2f}s.",),
            )
        argv = [str(python_exe), "-I", "-c", _DEEP_PROBE_CODE, *validated_mods]
        try:
            proc_tree = ManagedProcessTree(
                argv,
                cwd=quick_report.env_dir,
                env=build_isolated_python_env(),
                inherit_tty=False,
            )
        except OSError as exc:
            return EnvHealthReport(
                spec=spec,
                env_dir=quick_report.env_dir,
                quick_ok=True,
                deep_import_ok=False,
                issues=(f"Failed to launch environment Python executable: {safe_exception_summary(exc)}",),
            )
        with proc_tree:
            while True:
                exit_code = proc_tree.poll()
                if exit_code is not None:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    proc_tree.kill_tree_now()
                    return EnvHealthReport(
                        spec=spec,
                        env_dir=quick_report.env_dir,
                        quick_ok=True,
                        deep_import_ok=False,
                        issues=(f"Deep health probe timed out after {safe_timeout:.2f}s.",),
                    )
                time.sleep(min(0.015, max(0.002, remaining)))
        if exit_code != 0:
            return EnvHealthReport(
                spec=spec,
                env_dir=quick_report.env_dir,
                quick_ok=True,
                deep_import_ok=False,
                issues=(f"Deep health probe failed with exit code {exit_code}.",),
            )
        return EnvHealthReport(
            spec=spec,
            env_dir=quick_report.env_dir,
            quick_ok=True,
            deep_import_ok=True,
            issues=(),
        )

    def repair(
        self,
        spec: EnvSpec,
        *,
        offline: bool = False,
        wheel_cache_dir: Optional[HostPath] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> EnvBuildResult:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        require_pure_bool(offline, "offline")
        if wheel_cache_dir is not None and not isinstance(wheel_cache_dir, HostPath):
            raise ValueError(f"wheel_cache_dir must be HostPath or None, got {wheel_cache_dir!r}")
        if cancel_token is not None and not isinstance(cancel_token, CancellationToken):
            raise ValueError(f"cancel_token must be CancellationToken or None, got {cancel_token!r}")
        return env_repair_under_lock(
            self._pool,
            spec,
            offline=offline,
            wheel_cache_dir=wheel_cache_dir,
            cancel_token=cancel_token,
        )
