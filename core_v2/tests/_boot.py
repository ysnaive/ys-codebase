"""Standalone daemon and CLI subprocess bootstrap entrypoint for live workspace tests."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import json
import os
from pathlib import Path
import signal
import sys
import threading
from typing import Final, Mapping, Optional, Sequence

_THIS_DIR: Final[Path] = Path(__file__).resolve().parent
_CORE_V2_ROOT: Final[Path] = _THIS_DIR.parent
_CORE_SRC_ROOT: Final[Path] = _CORE_V2_ROOT / "source" / "core"
for _sys_entry in (str(_CORE_V2_ROOT), str(_CORE_SRC_ROOT)):
    if _sys_entry not in sys.path:
        sys.path.insert(0, _sys_entry)

from core.execution.daemon import DaemonWatcherConfig, SingleFlightDaemonSpawner, WorkspaceDaemon
from core.execution.rpc import DaemonConnectionConfig, PersistentRpcSession
from core.execution.runtime import (
    CallerSurface,
    CliBindingSpec,
    ClientRoutingPolicy,
    ConcurrencyMode,
    ConfigViewPort,
    DispatchMode,
    DispatcherHostOptions,
    InvokeRequest,
    ModuleDescriptor,
    ModuleProviderPort,
    PeriodicScheduleSpec,
    RuntimeDispatcher,
    SecurityTier,
    SelfMutationScope,
    SubscriptionRouteSpec,
    TaskExposure,
    TaskRouteSpec,
    VfsEchoGuardPort,
)
from core.filesystem.fs import FileLock, atomic_write_json, read_json_dict
from core.foundation import (
    EventId,
    HostPath,
    JsonPrimitive,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    TaskId,
)


def _jint(mapping: Optional[Mapping[str, JsonValue]], key: str, default: int = 0) -> int:
    if mapping is None:
        return default
    val = mapping.get(key, default)
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    return default


class FileConfigView(ConfigViewPort):
    """Reads <workspace>/config/*.json and yscb.config.json to test live and cold fingerprint reloads."""

    def __init__(self, workspace_root: HostPath) -> None:
        self._ws = workspace_root
        self._cfg_dir = workspace_root.join("config")
        self._lock = threading.Lock()
        self._data: dict[str, MutableJsonObject] = {}
        self.reload()

    def get_module_value(self, module_id: ModuleId, key: str, default: JsonValue = None) -> JsonValue:
        with self._lock:
            mod_map = self._data.get(str(module_id))
            return mod_map.get(key, default) if mod_map is not None else default

    def fingerprint(self) -> str:
        parts: list[str] = []
        root_cfg = self._ws.path / "yscb.config.json"
        if root_cfg.is_file():
            st0 = root_cfg.stat()
            parts.append(f"root:{st0.st_mtime_ns}:{st0.st_size}:{st0.st_ino}")
        if self._cfg_dir.path.is_dir():
            for p in sorted(self._cfg_dir.path.glob("*.json")):
                st = p.stat()
                parts.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}:{st.st_ino}")
        return "|".join(parts)

    def reload(self) -> None:
        fresh: dict[str, MutableJsonObject] = {}
        root_d = read_json_dict(self._ws.join("yscb.config.json"))
        if root_d is not None:
            fresh["root"] = root_d
        if self._cfg_dir.path.is_dir():
            for p in sorted(self._cfg_dir.path.glob("*.json")):
                d = read_json_dict(HostPath(p))
                if d is not None:
                    fresh[p.stem] = d
        with self._lock:
            self._data = fresh


class FileEchoLedger(VfsEchoGuardPort):
    """Suppresses self-writes recorded in <workspace>/.cache/echo_ledger.json."""

    def __init__(self, cache_dir: HostPath) -> None:
        self._ledger_file = cache_dir.join("echo_ledger.json")

    def is_suppressed(self, path: HostPath, mtime_ns: int, size: int, ino: int = -1) -> bool:
        cur = read_json_dict(self._ledger_file)
        if not cur:
            return False
        sig = cur.get(path.comparison_key)
        if not isinstance(sig, list) or len(sig) < 2 or sig[0] != mtime_ns or sig[1] != size:
            return False
        return True if (len(sig) < 3 or ino < 0) else sig[2] == ino


def _parse_payload_filter(raw_pf: JsonValue) -> Optional[Mapping[str, tuple[JsonPrimitive, ...]]]:
    if not isinstance(raw_pf, Mapping):
        return None
    parsed: dict[str, tuple[JsonPrimitive, ...]] = {}
    for k, vals in raw_pf.items():
        if isinstance(vals, Sequence) and not isinstance(vals, (str, bytes)):
            parsed[str(k)] = tuple(v for v in vals if v is None or isinstance(v, (bool, int, float, str)))
    return parsed or None


def _parse_periodic_spec(per_raw: JsonValue) -> Optional[PeriodicScheduleSpec]:
    if not isinstance(per_raw, Mapping):
        return None
    iv_raw = per_raw.get("default_interval_sec", 0.2)
    iv = float(iv_raw) if isinstance(iv_raw, (int, float)) and not isinstance(iv_raw, bool) else 0.2
    en_k = per_raw.get("enabled_config_key")
    iv_k = per_raw.get("interval_config_key")
    return PeriodicScheduleSpec(
        default_interval_sec=iv,
        enabled_config_key=str(en_k) if isinstance(en_k, str) else None,
        interval_config_key=str(iv_k) if isinstance(iv_k, str) else None,
    )


def _parse_task_route(raw_r: Mapping[str, JsonValue]) -> TaskRouteSpec:
    subs_raw = raw_r.get("subscriptions")
    subs: list[SubscriptionRouteSpec] = []
    if isinstance(subs_raw, Sequence) and not isinstance(subs_raw, (str, bytes)):
        for s in subs_raw:
            if isinstance(s, Mapping) and isinstance(s.get("event_id"), str):
                subs.append(
                    SubscriptionRouteSpec(
                        event_id=EventId(str(s["event_id"])),
                        payload_filter=_parse_payload_filter(s.get("payload_filter")),
                    )
                )
    cli_raw = raw_r.get("cli_path")
    cli_spec = (
        CliBindingSpec(command_path=tuple(str(x) for x in cli_raw), summary="cli")
        if isinstance(cli_raw, list)
        else None
    )
    rk_raw = raw_r.get("resource_key")
    tm_raw = raw_r.get("timeout_ms")
    return TaskRouteSpec(
        task_id=TaskId(str(raw_r["task_id"])),
        exposure=TaskExposure(str(raw_r.get("exposure", "cli_and_sdk"))),
        cli=cli_spec,
        dispatch_mode=DispatchMode(str(raw_r.get("dispatch_mode", "hybrid"))),
        mutation_scope=SelfMutationScope(str(raw_r.get("mutation_scope", "none"))),
        interactive_tty=bool(raw_r.get("interactive_tty", False)),
        security_tier=SecurityTier(str(raw_r.get("security_tier", "safe"))),
        resource_key=str(rk_raw) if isinstance(rk_raw, str) else None,
        concurrency_mode=ConcurrencyMode(str(raw_r.get("concurrency_mode", "parallel"))),
        timeout_ms=int(tm_raw) if isinstance(tm_raw, int) and not isinstance(tm_raw, bool) else None,
        subscriptions=tuple(subs),
        periodic=_parse_periodic_spec(raw_r.get("periodic")),
    )


class ManifestModuleProvider(ModuleProviderPort):
    """Discovers live test modules installed under <workspace>/.modules/."""

    def __init__(
        self,
        workspace_root: HostPath,
        venv_python: Optional[HostPath],
        dedicated_venv_python: Optional[HostPath] = None,
    ) -> None:
        self._ws = workspace_root
        self._venv_python = venv_python
        self._dedicated_venv = dedicated_venv_python or venv_python
        self._lock = threading.Lock()
        self._mods: dict[ModuleId, ModuleDescriptor] = {}
        self.reload()

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        with self._lock:
            return tuple(self._mods.values())

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        with self._lock:
            return self._mods.get(module_id)

    def reload(self) -> None:
        mods_root = self._ws.join(".modules")
        found: dict[ModuleId, ModuleDescriptor] = {}
        if mods_root.path.is_dir():
            for child in sorted(mods_root.path.iterdir()):
                desc = self._load_single_descriptor(child)
                if desc is not None:
                    found[desc.module_id] = desc
        with self._lock:
            self._mods = found

    def _load_single_descriptor(self, child: Path) -> Optional[ModuleDescriptor]:
        if not child.is_dir() or child.name.startswith("."):
            return None
        raw_meta = read_json_dict(HostPath(child / "routes.json")) or {}
        mid = ModuleId(child.name)
        is_tier1 = bool(raw_meta.get("tier1", False))
        eager = bool(raw_meta.get("eager_warmup", False))
        vg_raw = raw_meta.get("venv_group")
        vg_norm = str(vg_raw) if isinstance(vg_raw, str) and vg_raw else None
        tasks_raw = raw_meta.get("tasks")
        routes = [
            _parse_task_route(item)
            for item in (tasks_raw if isinstance(tasks_raw, list) else [])
            if isinstance(item, Mapping)
        ]
        return ModuleDescriptor(
            module_id=mid,
            module_dir=HostPath(child),
            entry_file=str(raw_meta["entry_file"]) if isinstance(raw_meta.get("entry_file"), str) else "module_entry.py",
            venv_group=vg_norm,
            venv_python=(self._dedicated_venv if vg_norm is None else self._venv_python) if is_tier1 else None,
            eager_warmup=eager,
            declared_tasks=tuple(routes),
        )


def live_host_boot_script_path() -> Path:
    """Return the standalone entrypoint path for daemon and CLI subprocesses."""
    return Path(__file__).resolve()


@dataclass(frozen=True, slots=True)
class WorkspaceDispatcherRig:
    dispatcher: RuntimeDispatcher
    config_view: FileConfigView
    echo_ledger: FileEchoLedger
    provider: ManifestModuleProvider


def resolve_dedicated_venv_py(hint_path: HostPath) -> HostPath:
    rel_bin = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    for anc in (hint_path.path, *hint_path.path.parents):
        cand = anc / "dedicated_gdrive_venv" / rel_bin
        if cand.is_file():
            return HostPath(cand)
    return hint_path if hint_path.path.is_file() else HostPath(Path(sys.executable))


def build_dispatcher_for_workspace(
    ws: HostPath,
    venv_python: HostPath,
    *,
    is_daemon_host: bool = False,
    sandbox_restricted: bool = False,
    ttl_sec: float = 8.0,
    persistent_session: Optional[PersistentRpcSession] = None,
) -> WorkspaceDispatcherRig:
    cache_dir = ws.join(".cache")
    cfg_view = FileConfigView(ws)
    echo_ledger = FileEchoLedger(cache_dir)
    ded_venv = resolve_dedicated_venv_py(venv_python)
    provider = ManifestModuleProvider(ws, venv_python, dedicated_venv_python=ded_venv)
    boot_script = str(live_host_boot_script_path())
    spawner = SingleFlightDaemonSpawner(
        cache_dir,
        lambda root: [
            sys.executable,
            "-B",
            "-W",
            "error::ResourceWarning",
            boot_script,
            "--daemon-entry",
            str(root),
            str(venv_python),
            str(ttl_sec),
        ],
        sandbox_restricted=sandbox_restricted,
    )

    def _child_factory(child_ws: HostPath) -> RuntimeDispatcher:
        c_cache = child_ws.join(".cache")
        c_prov = ManifestModuleProvider(child_ws, venv_python, dedicated_venv_python=ded_venv)
        c_opts = DispatcherHostOptions(
            config_view=FileConfigView(child_ws),
            daemon_spawner=None,
            connection_config=DaemonConnectionConfig(enabled=not sandbox_restricted, auto_spawn=False),
            is_daemon_host=False,
            child_dispatcher_factory=_child_factory,
        )
        return RuntimeDispatcher(workspace_root=child_ws, cache_dir=c_cache, module_provider=c_prov, options=c_opts)

    opts = DispatcherHostOptions(
        config_view=cfg_view,
        daemon_spawner=None if is_daemon_host else spawner,
        connection_config=DaemonConnectionConfig(enabled=not sandbox_restricted, auto_spawn=not sandbox_restricted),
        is_daemon_host=is_daemon_host,
        persistent_rpc_session=persistent_session,
        child_dispatcher_factory=_child_factory,
    )
    disp = RuntimeDispatcher(workspace_root=ws, cache_dir=cache_dir, module_provider=provider, options=opts)
    return WorkspaceDispatcherRig(disp, cfg_view, echo_ledger, provider)


def _record_daemon_spawn_counter(ws: HostPath) -> None:
    cnt_lock = FileLock(ws.join(".cache", "locks", "spawn_counter.lock"))
    cnt_lock.acquire(blocking=True, timeout_sec=5.0)
    try:
        cnt_f = ws.join(".cache", "daemon_spawn_count.json")
        cur = read_json_dict(cnt_f)
        prev_pids = cur.get("pids") if isinstance(cur, Mapping) else None
        pids = [int(x) for x in prev_pids if isinstance(x, int) and not isinstance(x, bool)] if isinstance(prev_pids, list) else []
        me = os.getpid()
        if me not in pids:
            pids.append(me)
        atomic_write_json(cnt_f, {"spawns": _jint(cur, "spawns", 0) + 1, "pids": pids})
    finally:
        cnt_lock.release()


def daemon_process_main(ws_str: str, venv_py_str: str, ttl_str: str) -> int:
    ws = HostPath(ws_str)
    venv_py = HostPath(venv_py_str)
    ttl = float(ttl_str)
    _record_daemon_spawn_counter(ws)
    rig = build_dispatcher_for_workspace(ws, venv_py, is_daemon_host=True, ttl_sec=ttl)
    disp, cfg_view, echo_ledger = rig.dispatcher, rig.config_view, rig.echo_ledger
    watch_cfg = DaemonWatcherConfig(
        echo_guard=echo_ledger,
        space_watch_roots=(ws.join("spaces"),),
        config_watch_roots=(ws.join("config"), ws.join("yscb.config.json"), ws.join(".config.local")),
        on_space_changed_task=TaskId("space.scan"),
        on_config_changed_task=None,
        watcher_debounce_sec=0.08,
    )
    daemon = WorkspaceDaemon(
        workspace_root=ws,
        cache_dir=ws.join(".cache"),
        dispatcher=disp,
        config_view=cfg_view,
        watch_config=watch_cfg,
        self_restart_argv=[
            sys.executable,
            "-B",
            "-W",
            "error::ResourceWarning",
            str(live_host_boot_script_path()),
            "--daemon-entry",
            ws_str,
            venv_py_str,
            ttl_str,
        ],
    )
    return daemon.run_forever(ttl_override_sec=ttl)


def _scan_static_route_manifest(rfile: Path, known_ids: list[str], cli_cmds: list[str]) -> None:
    meta = read_json_dict(HostPath(rfile)) or {}
    t_list = meta.get("tasks")
    for item in (t_list if isinstance(t_list, list) else []):
        if isinstance(item, dict) and isinstance(item.get("task_id"), str):
            known_ids.append(str(item["task_id"]))
            if isinstance(item.get("cli_path"), list):
                cli_cmds.append(" ".join(str(x) for x in item["cli_path"]))


def _handle_static_cli_meta(ws: HostPath, task_str: str) -> Optional[int]:
    if task_str != "--help" and not task_str.startswith("unknown."):
        return None
    cli_cmds: list[str] = []
    known_ids: list[str] = []
    mods_dir = ws.path / ".modules"
    for rfile in (sorted(mods_dir.glob("*/routes.json")) if mods_dir.is_dir() else []):
        _scan_static_route_manifest(rfile, known_ids, cli_cmds)
    if task_str == "--help":
        sys.stdout.write(json.dumps({"ok": True, "cli_commands": cli_cmds}) + "\n")
        return 0
    hints = difflib.get_close_matches(task_str, known_ids, n=2, cutoff=0.3)
    sys.stdout.write(json.dumps({"ok": False, "error": "task_not_found", "suggestions": hints}) + "\n")
    return 2


def cli_oneshot_main(
    ws_str: str,
    venv_py_str: str,
    cwd_str: str,
    task_str: str,
    payload_json: str,
    policy_str: str,
) -> int:
    ws = HostPath(ws_str)
    static_rc = _handle_static_cli_meta(ws, task_str)
    if static_rc is not None:
        return static_rc
    venv_py = HostPath(venv_py_str)
    prev_sigbreak = (
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
        if sys.platform == "win32"
        else None
    )
    disp = build_dispatcher_for_workspace(ws, venv_py, is_daemon_host=False).dispatcher
    try:
        raw_obj = json.loads(payload_json)
        if not isinstance(raw_obj, dict):
            raise ValueError("CLI payload must be a JSON object")
        out = disp.invoke(
            InvokeRequest(
                task_id=TaskId(task_str),
                raw_input=raw_obj,
                workspace_root=ws,
                caller_cwd=HostPath(cwd_str),
                caller_surface=CallerSurface.CLI,
                routing_policy=ClientRoutingPolicy(policy_str),
            )
        )
        is_sigint = bool(out.error and "SIGINT" in out.error.message)
        sys.stdout.write(
            json.dumps(
                {
                    "ok": out.ok,
                    "value": out.value,
                    "executed_hot": out.executed_hot,
                    "coalesced": out.coalesced,
                    "error": out.error.code.value if out.error else None,
                    "teardown_count": len(out.teardown_diagnostics),
                }
            )
            + "\n"
        )
        return 0 if out.ok else (130 if is_sigint else 1)
    finally:
        disp.shutdown(grace_ms=300)
        if sys.platform == "win32" and prev_sigbreak is not None:
            signal.signal(signal.SIGBREAK, prev_sigbreak)


__all__ = (
    "FileConfigView",
    "FileEchoLedger",
    "ManifestModuleProvider",
    "WorkspaceDispatcherRig",
    "build_dispatcher_for_workspace",
    "cli_oneshot_main",
    "daemon_process_main",
    "live_host_boot_script_path",
    "resolve_dedicated_venv_py",
)


def _main(argv: Sequence[str]) -> int:
    if argv and argv[0] == "--daemon-entry":
        return daemon_process_main(argv[1], argv[2], argv[3])
    if argv and argv[0] == "--cli-oneshot":
        return cli_oneshot_main(argv[1], argv[2], argv[3], argv[4], argv[5], argv[6])
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
