"""Shared test fixtures, DTOs, workspace provisioning, and embedded module templates."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Final, Iterator, Mapping, Optional, Sequence

from core.execution.rpc import FrameKind, probe_daemon_endpoint, query_daemon_control
from core.execution.runtime import (
    CliBindingSpec,
    ClientRoutingPolicy,
    ModuleDescriptor,
    RuntimeDispatcher,
    TaskMetadata,
)
from core.filesystem.fs import FileLock, atomic_write_json, read_json_dict
from core.foundation import (
    ErrorCode,
    ErrorDetail,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    TaskId,
    YscbError,
    is_process_alive,
)
from tests._boot import live_host_boot_script_path


@dataclass(frozen=True, slots=True)
class EchoInDto:
    tag: str


@dataclass(frozen=True, slots=True)
class SimpleOutDto:
    ok_msg: str
    pid: int = 0


@dataclass(frozen=True, slots=True)
class OutlineInDto:
    rel_file: str
    call_tier0: bool = False
    fail_imm_strict: bool = False
    uncoop_hang_ms: int = 0
    coop_sleep_ms: int = 0


@dataclass(frozen=True, slots=True)
class OutlineOutDto:
    resolved_path: str
    exists: bool
    worker_pid: int
    lazy_ready: bool
    module_ver: str
    helper_tag: str = ""
    tier0_echo: str = ""


@dataclass(frozen=True, slots=True)
class SearchInDto:
    query: str
    sync: bool = False
    sleep_ms: int = 0
    post_sync: bool = False


@dataclass(frozen=True, slots=True)
class SearchOutDto:
    query: str
    warm_model_ready: bool
    kdb_gen: int
    worker_pid: int


@dataclass(frozen=True, slots=True)
class IndexOutDto:
    kdb_gen: int
    observed_priority: str
    exported_to: str = ""


@dataclass(frozen=True, slots=True)
class GdriveOutDto:
    status: str
    proxy_seen: str = ""
    leaked_secret_seen: str = ""
    worker_pid: int = 0
    venv_prefix: str = ""


@dataclass(frozen=True, slots=True)
class SandboxOutDto:
    child_ok: bool
    spawned_pid: int = 0


@dataclass(frozen=True, slots=True)
class CoordProbeOut:
    ok_tag: str
    coalesced_sub: bool = False


ECHO_TIER0_META: Final[TaskMetadata[EchoInDto, SimpleOutDto]] = TaskMetadata(
    TaskId("space.echo_tier0"),
    EchoInDto,
    SimpleOutDto,
    cli=CliBindingSpec(command_path=("space", "echo"), summary="Echo tag from Tier 0"),
)
AST_OUTLINE_META: Final[TaskMetadata[OutlineInDto, OutlineOutDto]] = TaskMetadata(
    TaskId("ast.outline"),
    OutlineInDto,
    OutlineOutDto,
    cli=CliBindingSpec(command_path=("ast", "outline"), summary="Inspect Python file outline"),
)
KDB_SEARCH_META: Final[TaskMetadata[SearchInDto, SearchOutDto]] = TaskMetadata(
    TaskId("kdb.search"),
    SearchInDto,
    SearchOutDto,
)


@contextlib.contextmanager
def scoped_timer(delay_sec: float, fn: Callable[[], object]) -> Iterator[threading.Timer]:
    tm = threading.Timer(delay_sec, fn)
    tm.daemon = True
    tm.start()
    try:
        yield tm
    finally:
        tm.cancel()
        tm.join(timeout=1.0)


def check(cond: object, msg: object = "") -> None:
    if not cond:
        detail = msg() if callable(msg) else msg
        raise AssertionError(str(detail) if detail else "Verification check failed")


def log(msg: str) -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def jint(mapping: Optional[Mapping[str, JsonValue]], key: str, default: int = 0) -> int:
    if mapping is None:
        return default
    val = mapping.get(key, default)
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    return default


def jfloat(mapping: Optional[Mapping[str, JsonValue]], key: str, default: float = 0.0) -> float:
    if mapping is None:
        return default
    val = mapping.get(key, default)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return default


def jlist(mapping: Optional[Mapping[str, JsonValue]], key: str) -> list[JsonValue]:
    if mapping is None:
        return []
    val = mapping.get(key)
    if isinstance(val, list):
        return val
    return []


def expect_yscb_code(fn: Callable[[], object], expected: ErrorCode) -> None:
    try:
        fn()
    except YscbError as exc:
        check(exc.detail.code == expected, lambda: f"Expected {expected}, got {exc.detail.code}")
        return
    raise AssertionError(f"Expected YscbError({expected}), but call succeeded")


def assert_raises_val_error(fn: Callable[[], object]) -> None:
    caught = False
    try:
        _ = fn()
    except ValueError:
        caught = True
    check(caught)


def reap_popen_quietly(proc: subprocess.Popen[str] | subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        pass


class SingleProbeProvider:
    """Minimal ModuleProviderPort yielding a single ModuleDescriptor for unit tests."""

    def __init__(self, desc: ModuleDescriptor) -> None:
        self._desc = desc

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        return (self._desc,)

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        return self._desc if module_id == self._desc.module_id else None

    def reload(self) -> None:
        return None


def wait_file_marker(marker: Path, timeout_sec: float = 2.0) -> None:
    dl = time.monotonic() + timeout_sec
    while time.monotonic() < dl:
        if marker.is_file():
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for marker {marker.name}")


def wait_coalesce_count(
    coord: RuntimeDispatcher,
    resource_key: str,
    min_count: int,
    timeout_sec: float = 4.0,
) -> None:
    dl = time.monotonic() + timeout_sec
    while time.monotonic() < dl:
        if coord.coordinator.coalesce_participant_count(resource_key) >= min_count:
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for coalesce_participant_count({resource_key!r}) >= {min_count}")


def wait_for_daemon_online(ws: HostPath, timeout_sec: float = 15.0) -> JsonObject:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        res = query_daemon_control(ws.join(".cache"), ws, FrameKind.CONTROL_STATUS)
        if res and res.get("ok") and isinstance(res.get("status"), Mapping) and res["status"].get("state") == "ready":
            return res["status"]
        time.sleep(0.04)
    raise AssertionError(f"Daemon did not come online within {timeout_sec}s at {ws}")


def _recorded_daemon_pids(cache_dir: HostPath) -> tuple[int, ...]:
    pids: list[int] = []
    for fname in ("daemon.json", "spawn_lease.json"):
        doc = read_json_dict(cache_dir.join("daemon", fname))
        if doc is not None:
            pv = jint(doc, "pid", 0)
            if pv > 0 and pv not in pids:
                pids.append(pv)
    cnt_doc = read_json_dict(cache_dir.join("daemon_spawn_count.json"))
    raw_list = cnt_doc.get("pids") if isinstance(cnt_doc, Mapping) else None
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, int) and not isinstance(item, bool) and item > 0 and item not in pids:
                pids.append(item)
    return tuple(pids)


def _has_pending_daemon_lease(cache_dir: HostPath) -> bool:
    if read_json_dict(cache_dir.join("daemon", "handoff_lease.json")) is not None:
        return True
    return any(is_process_alive(p) for p in _recorded_daemon_pids(cache_dir))


def wait_until(pred: Callable[[], bool], timeout_sec: float = 4.0, step_sec: float = 0.015) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(step_sec)
    check(pred(), "Timed out waiting for asynchronous condition to converge.")


def drain_teardown_until(
    disp: RuntimeDispatcher,
    pred: Callable[[ErrorDetail], bool],
    timeout_sec: float = 3.5,
) -> tuple[ErrorDetail, ...]:
    collected: list[ErrorDetail] = []
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        collected.extend(disp.drain_teardown_diagnostics())
        if any(pred(d) for d in collected):
            return tuple(collected)
        time.sleep(0.015)
    collected.extend(disp.drain_teardown_diagnostics())
    return tuple(collected)


def _wait_daemon_lock_released(cache_dir: HostPath) -> None:
    dlock_p = cache_dir.join("daemon", "daemon.lock")
    if not dlock_p.path.exists():
        return
    lk = FileLock(dlock_p)
    if lk.acquire(shared=False, blocking=True, timeout_sec=4.0):
        lk.release()


def stop_daemon_cleanly(ws: HostPath) -> None:
    cache_dir = ws.join(".cache")
    known_pids: set[int] = set(_recorded_daemon_pids(cache_dir))
    outer_dl = time.monotonic() + 7.0
    while time.monotonic() < outer_dl:
        known_pids.update(_recorded_daemon_pids(cache_dir))
        ep = probe_daemon_endpoint(cache_dir, ws)
        if ep is not None:
            known_pids.add(ep.pid)
            query_daemon_control(cache_dir, ws, FrameKind.CONTROL_STOP)
            inner_dl = time.monotonic() + 4.0
            while time.monotonic() < inner_dl and is_process_alive(ep.pid):
                time.sleep(0.02)
            continue
        if _has_pending_daemon_lease(cache_dir) or any(is_process_alive(p) for p in known_pids):
            time.sleep(0.02)
            continue
        _wait_daemon_lock_released(cache_dir)
        known_pids.update(_recorded_daemon_pids(cache_dir))
        if (
            probe_daemon_endpoint(cache_dir, ws) is None
            and not _has_pending_daemon_lease(cache_dir)
            and not any(is_process_alive(p) for p in known_pids)
        ):
            return
    alive_pids = sorted(p for p in known_pids if is_process_alive(p))
    for pid in alive_pids:
        try:
            os.kill(pid, int(signal.SIGKILL) if os.name != "nt" else int(signal.SIGTERM))
        except OSError:
            pass
    check(not alive_pids, lambda: f"Daemon failed to stop cleanly within 7.0s at {ws}: {alive_pids}")


def run_cli_subproc(
    ws: HostPath,
    venv_py: Path,
    cwd: str,
    task_id: str,
    payload: JsonObject,
    policy: ClientRoutingPolicy,
) -> MutableJsonObject:
    cp = subprocess.run(
        [
            sys.executable,
            "-B",
            "-W",
            "error::ResourceWarning",
            str(live_host_boot_script_path()),
            "--cli-oneshot",
            str(ws),
            str(venv_py),
            cwd,
            task_id,
            json.dumps(dict(payload)),
            policy.value,
        ],
        capture_output=True,
        text=True,
        timeout=45.0,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    parsed = json.loads(cp.stdout.strip())
    check(isinstance(parsed, dict))
    return parsed


def _proc_matches_tmp_root(entry: Path, marker: str) -> Optional[str]:
    try:
        cmd = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore").strip()
    except OSError:
        cmd = ""
    if marker in cmd:
        return cmd
    try:
        cwd_target = os.readlink(entry / "cwd")
    except OSError:
        cwd_target = ""
    return f"{cmd} [cwd={cwd_target}]" if marker in cwd_target else None


def _find_ps_tmp_root_orphans(me: int, marker: str) -> list[tuple[int, str]]:
    try:
        cp = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except OSError:
        return []
    leaked: list[tuple[int, str]] = []
    for line in cp.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            pid = int(parts[0])
            if pid != me and marker in parts[1] and is_process_alive(pid):
                leaked.append((pid, parts[1]))
    return leaked


def _collect_live_tmp_root_orphans(tmp_root: Path) -> list[tuple[int, str]]:
    me = os.getpid()
    marker = str(tmp_root)
    if not Path("/proc").is_dir():
        return _find_ps_tmp_root_orphans(me, marker) if os.name != "nt" else []
    leaked: list[tuple[int, str]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == me or not is_process_alive(pid):
            continue
        matched = _proc_matches_tmp_root(entry, marker)
        if matched is not None:
            leaked.append((pid, matched))
    return leaked


def force_reap_tmp_root_orphans(tmp_root: Path) -> None:
    for pid, _cmd in _collect_live_tmp_root_orphans(tmp_root):
        try:
            os.kill(pid, int(signal.SIGKILL) if os.name != "nt" else int(signal.SIGTERM))
        except OSError:
            continue


def assert_zero_live_stage_orphans(tmp_root: Path) -> None:
    leaked = _collect_live_tmp_root_orphans(tmp_root)
    if leaked:
        force_reap_tmp_root_orphans(tmp_root)
        raise AssertionError(f"Transitional orphan process(es) still alive after stage teardown: {leaked}")
    deadline = time.monotonic() + 2.0
    leaked_threads: list[str] = []
    while time.monotonic() < deadline:
        leaked_threads = [
            t.name for t in threading.enumerate() if t is not threading.main_thread() and t.is_alive()
        ]
        if not leaked_threads:
            break
        time.sleep(0.03)
    if leaked_threads:
        raise AssertionError(f"Leaked background yscb thread(s) after stage teardown: {leaked_threads}")


def write_module(ws: Path, name: str, routes: JsonObject, code: str, helper_who: Optional[str] = None) -> None:
    mdir = ws / ".modules" / name
    mdir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(HostPath(mdir / "routes.json"), routes)
    (mdir / "module_entry.py").write_text(code, encoding="utf-8")
    if helper_who is not None:
        helper_src = (
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n\n"
            f'HELPER_WHO = "{helper_who}"\n\n'
            "class OuterHelper:\n"
            "    @dataclass(frozen=True, slots=True)\n"
            "    class InnerBox:\n"
            "        tag: str\n"
            "    @property\n"
            "    def sample_box(self) -> OuterHelper.InnerBox:\n"
            "        return OuterHelper.InnerBox(tag=HELPER_WHO)\n\n"
            "IMPORT_TIME_TUPLE = (OuterHelper.InnerBox,)\n"
        )
        (mdir / "local_util.py").write_text(helper_src, encoding="utf-8")


SPACE_MODULE_SRC: Final[str] = '''from dataclasses import dataclass
import os
import time
from typing import Callable, Optional, Sequence
import local_util
from core.execution.daemon import query_daemon_control
from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec
from core.execution.rpc import FrameKind
from core.execution.runtime import (
    BoundTask, ClientRoutingPolicy, ConcurrencyMode, DispatchMode, SecurityTier,
    SelfMutationScope, Task, TaskContext, TaskExposure, TaskMetadata, YscbModule
)
from core.filesystem.fs import atomic_write_json, read_json_dict
from core.foundation import EventId, HostPath, ModuleId, TaskId

MODULE_VER = "v1"

@dataclass(frozen=True, slots=True)
class EmptyIn:
    pass

@dataclass(frozen=True, slots=True)
class ScanIn:
    changed_paths: tuple[str, ...] = ()
    startup_catchup: bool = False

@dataclass(frozen=True, slots=True)
class SpaceEvPayload:
    space: str
    count: int

@dataclass(frozen=True, slots=True)
class SimpleOut:
    ok_msg: str
    pid: int = 0

SPACE_UPDATED_EV = EventMetadata(EventId("space.updated"), SpaceEvPayload, EventOrdering.UNORDERED)
WORKSPACE_RELOADED_EV = EventMetadata(EventId("space.reloaded"), EmptyIn, EventOrdering.UNORDERED)
MODULE_REMOVING_EV = EventMetadata(EventId("space.removing"), SpaceEvPayload, EventOrdering.ORDERED)
ORDERED_AUDIT_EV = EventMetadata(EventId("space.ordered_audit"), SpaceEvPayload, EventOrdering.ORDERED)
PING_EV = EventMetadata(EventId("space.ev_ping"), EmptyIn, EventOrdering.UNORDERED)
PONG_EV = EventMetadata(EventId("space.ev_pong"), EmptyIn, EventOrdering.UNORDERED)
MIX_CYCLE_EV = EventMetadata(EventId("space.mix_cycle_ev"), EmptyIn, EventOrdering.UNORDERED)

RELOAD_META: TaskMetadata[EmptyIn, SimpleOut] = TaskMetadata(
    TaskId("space.reload"), EmptyIn, SimpleOut,
    resource_key="installer", concurrency_mode=ConcurrencyMode.SERIALIZE
)

class ScanTask(Task[ScanIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[ScanIn, SimpleOut]:
        return TaskMetadata(TaskId("space.scan"), ScanIn, SimpleOut, exposure=TaskExposure.INTERNAL_TRIGGER)
    def run(self, req: ScanIn, ctx: TaskContext) -> SimpleOut:
        targets: list[str] = []
        if not req.changed_paths:
            targets = ["source", "docs", "ignored_logs"]
        else:
            for sp_name in ("source", "docs", "ignored_logs"):
                marker = os.sep + sp_name + os.sep
                if any(marker in p or p.endswith(os.sep + sp_name) for p in req.changed_paths):
                    targets.append(sp_name)
        for sp_name in targets:
            sp_dir = ctx.workspace_root.path / "spaces" / sp_name
            cnt = len(list(sp_dir.glob("*"))) if sp_dir.is_dir() else 0
            ctx.emit(SPACE_UPDATED_EV, SpaceEvPayload(space=sp_name, count=cnt))
        return SimpleOut(ok_msg=f"scanned:{','.join(targets)}", pid=os.getpid())

@dataclass(frozen=True, slots=True)
class ConfigChangedIn:
    changed_paths: tuple[str, ...] = ()

def _map_cfg_ev(items: Sequence[ConfigChangedIn]) -> ConfigChangedIn:
    merged: list[str] = []
    for item in items:
        merged.extend(item.changed_paths)
    return ConfigChangedIn(changed_paths=tuple(merged))

class OnConfigTask(Task[ConfigChangedIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[ConfigChangedIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.on_config"), ConfigChangedIn, SimpleOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("core.config_changed"), _map_cfg_ev, payload_type=ConfigChangedIn),),
        )
    def run(self, req: ConfigChangedIn, ctx: TaskContext) -> SimpleOut:
        cfg_f = ctx.workspace_root.join(".cache", "config_reloaded_marker.json")
        atomic_write_json(cfg_f, {"paths": list(req.changed_paths), "ts": time.time()})
        return SimpleOut(ok_msg="config_ack", pid=os.getpid())

@dataclass(frozen=True, slots=True)
class EchoIn:
    tag: str

class EchoTier0Task(Task[EchoIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EchoIn, SimpleOut]:
        return TaskMetadata(TaskId("space.echo_tier0"), EchoIn, SimpleOut)
    def run(self, req: EchoIn, ctx: TaskContext) -> SimpleOut:
        if req.tag == "record_cold_enter":
            atomic_write_json(ctx.workspace_root.join(".cache", "cold_reader_ts.json"), {"enter": time.monotonic()})
        return SimpleOut(ok_msg=f"tier0:{MODULE_VER}:{local_util.HELPER_WHO}:{req.tag}", pid=os.getpid())

class DaemonMetricsTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.daemon_metrics"), EmptyIn, SimpleOut,
            exposure=TaskExposure.SDK_ONLY, dispatch_mode=DispatchMode.DAEMON_ONLY
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        return SimpleOut(ok_msg="daemon_metrics_ok", pid=os.getpid())

@dataclass(frozen=True, slots=True)
class HoldMsIn:
    hold_ms: int
    ignore_cancel: bool = False

class HoldLockMsTask(Task[HoldMsIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[HoldMsIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.hold_lock_ms"), HoldMsIn, SimpleOut,
            resource_key="rc04_serial", concurrency_mode=ConcurrencyMode.SERIALIZE
        )
    def run(self, req: HoldMsIn, ctx: TaskContext) -> SimpleOut:
        if req.ignore_cancel:
            time.sleep(req.hold_ms / 1000.0)
            return SimpleOut(ok_msg="held_uncooperative", pid=os.getpid())
        atomic_write_json(ctx.workspace_root.join(".cache", "t0_guard_probe_enter.json"), {"enter": time.monotonic()})
        for _ in range(max(1, req.hold_ms // 20)):
            ctx.cancel_token.raise_if_cancelled()
            time.sleep(0.02)
        return SimpleOut(ok_msg="held", pid=os.getpid())

class Tier0TimeoutTask(Task[HoldMsIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[HoldMsIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.tier0_timeout"), HoldMsIn, SimpleOut,
            resource_key="rc04_serial", concurrency_mode=ConcurrencyMode.SERIALIZE, timeout_ms=60,
        )
    def run(self, req: HoldMsIn, ctx: TaskContext) -> SimpleOut:
        if req.ignore_cancel:
            time.sleep(req.hold_ms / 1000.0)
            atomic_write_json(ctx.workspace_root.join(".cache", "t0_lingering_exit.json"), {"exit": time.monotonic()})
            return SimpleOut(ok_msg="late_value")
        for _ in range(max(1, req.hold_ms // 15)):
            ctx.cancel_token.raise_if_cancelled()
            time.sleep(0.015)
        atomic_write_json(ctx.workspace_root.join(".cache", "t0_guard_probe_enter.json"), {"enter": time.monotonic()})
        return SimpleOut(ok_msg="done")

class GiantReplyTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.giant_reply"), EmptyIn, SimpleOut, dispatch_mode=DispatchMode.DAEMON_ONLY)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        return SimpleOut(ok_msg="y" * (65 * 1024 * 1024), pid=os.getpid())

@dataclass(frozen=True, slots=True)
class ChildWsIn:
    child_ws: str
    second_child_ws: str = ""
    bounce_back_ws: str = ""

class OrchestrateChildWsTask(Task[ChildWsIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[ChildWsIn, SimpleOut]:
        return TaskMetadata(TaskId("space.orchestrate_child_ws"), ChildWsIn, SimpleOut, dispatch_mode=DispatchMode.DAEMON_ONLY)
    def run(self, req: ChildWsIn, ctx: TaskContext) -> SimpleOut:
        cws = HostPath(req.child_ws)
        if req.bounce_back_ws:
            _ = ctx.invoke_task(
                "space.orchestrate_child_ws",
                {"child_ws": req.bounce_back_ws, "bounce_back_ws": str(ctx.workspace_root)},
                target_workspace=cws,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
            )
            return SimpleOut(ok_msg="swallowed_if_not_fatal")
        for target_str in (req.child_ws, req.second_child_ws):
            if not target_str:
                continue
            t_ws = HostPath(target_str)
            out = ctx.invoke_task(
                "dev.run_sandbox",
                {"child_workspace": str(t_ws), "spawn_sleep_child": False, "sync_host_install": False},
                target_workspace=t_ws,
                routing_policy=ClientRoutingPolicy.AUTO_NO_SPAWN,
            )
            if not out.ok:
                return SimpleOut(ok_msg=f"err:{out.error.code.value if out.error else ''}", pid=os.getpid())
        return SimpleOut(ok_msg="child_ok", pid=os.getpid())

@dataclass(frozen=True, slots=True)
class MutateIn:
    target_module: str
    hold_ms: int = 0
    strict_imm_fail: bool = False

class RemoveAndInstallTask(Task[MutateIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[MutateIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.remove_and_install"), MutateIn, SimpleOut,
            dispatch_mode=DispatchMode.COLD_ONLY,
            mutation_scope=SelfMutationScope.MUTATES_MODULES,
            security_tier=SecurityTier.GATED,
            resource_key="installer",
            concurrency_mode=ConcurrencyMode.SERIALIZE,
        )
    def run(self, req: MutateIn, ctx: TaskContext) -> SimpleOut:
        for seq_i in (1, 2, 3):
            ctx.emit(ORDERED_AUDIT_EV, SpaceEvPayload(space="deferred_fifo", count=seq_i))
        ctx.emit_imm(MODULE_REMOVING_EV, SpaceEvPayload(space=req.target_module, count=1), strict=req.strict_imm_fail)
        ctx.emit_imm(MODULE_REMOVING_EV, SpaceEvPayload(space=req.target_module, count=2), strict=req.strict_imm_fail)
        imm_now = read_json_dict(ctx.workspace_root.join(".cache", "remove_order.json")) or {}
        def_now = read_json_dict(ctx.workspace_root.join(".cache", "deferred_fifo.json"))
        atomic_write_json(
            ctx.workspace_root.join(".cache", "imm_inline_proof.json"),
            {"imm_seen_inline": imm_now.get("order"), "deferred_flushed_early": def_now is not None},
        )
        if req.hold_ms > 0:
            time.sleep(req.hold_ms / 1000.0)
        atomic_write_json(ctx.workspace_root.join(".cache", "installer_exit_ts.json"), {"exit": time.monotonic()})
        rel_out = ctx.invoke_typed(RELOAD_META, EmptyIn())
        if not rel_out.ok or rel_out.value is None:
            raise RuntimeError(f"Reload failed: {rel_out.error}")
        return SimpleOut(ok_msg=f"mutated_and_{rel_out.value.ok_msg}", pid=os.getpid())

@dataclass(frozen=True, slots=True)
class UpgradeCoreIn:
    version_tag: str

class UpgradeCoreTask(Task[UpgradeCoreIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[UpgradeCoreIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.upgrade_core"), UpgradeCoreIn, SimpleOut,
            dispatch_mode=DispatchMode.COLD_ONLY,
            mutation_scope=SelfMutationScope.MUTATES_CORE,
            security_tier=SecurityTier.GATED,
            resource_key="installer",
            concurrency_mode=ConcurrencyMode.SERIALIZE,
        )
    def run(self, req: UpgradeCoreIn, ctx: TaskContext) -> SimpleOut:
        atomic_write_json(ctx.workspace_root.join(".cache", "core_upgraded.json"), {"version": req.version_tag})
        ack = query_daemon_control(
            ctx.workspace_root.join(".cache"),
            ctx.workspace_root,
            FrameKind.CONTROL_RELOAD,
            {"modules": ["core"]},
        )
        return SimpleOut(ok_msg=f"core_upgraded:{req.version_tag}:handoff={bool(ack and ack.get('handoff'))}", pid=os.getpid())

class ReloadTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return RELOAD_META
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.emit(WORKSPACE_RELOADED_EV, EmptyIn())
        return SimpleOut(ok_msg="reloaded", pid=os.getpid())

class PartialCommitParentTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.partial_commit_parent"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        child_ok = ctx.invoke_typed(RELOAD_META, EmptyIn())
        if not child_ok.ok:
            raise AssertionError("embedded check failed")
        ctx.emit(ORDERED_AUDIT_EV, SpaceEvPayload(space="must_be_discarded", count=999))
        raise RuntimeError("Parent failed after child committed reload event")

class BadHotMutateTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_hot_mutate"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        out = ctx.invoke_task("space.remove_and_install", MutateIn(target_module="vsc"))
        return SimpleOut(ok_msg=out.error.code.value if (not out.ok and out.error) else "unexpected")

class BadHotCoreMutateTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_hot_core_mutate"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        out = ctx.invoke_task("space.upgrade_core", UpgradeCoreIn(version_tag="2.1.0"))
        return SimpleOut(ok_msg=out.error.code.value if (not out.ok and out.error) else "unexpected")

class BadEscalateTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_escalate"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        out = ctx.invoke_task("vsc.gated_clean", EmptyIn())
        return SimpleOut(ok_msg=f"blocked:{out.error.code.value}" if (not out.ok and out.error) else "unexpected")

class BadSelfPreemptTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_self_preempt"), EmptyIn, SimpleOut, resource_key="self_p", concurrency_mode=ConcurrencyMode.SERIALIZE)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.invoke_task("space.bad_self_preempt_inner", EmptyIn())
        return SimpleOut(ok_msg="unexpected")

class BadSelfPreemptInnerTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_self_preempt_inner"), EmptyIn, SimpleOut, resource_key="self_p", concurrency_mode=ConcurrencyMode.PREEMPT)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        return SimpleOut(ok_msg="inner")

class BadSelfCoalesceTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_self_coalesce"), EmptyIn, SimpleOut, resource_key="self_c", concurrency_mode=ConcurrencyMode.SERIALIZE)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.invoke_task("space.bad_self_coalesce_inner", EmptyIn())
        return SimpleOut(ok_msg="unexpected")

class BadSelfCoalesceInnerTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.bad_self_coalesce_inner"), EmptyIn, SimpleOut, resource_key="self_c", concurrency_mode=ConcurrencyMode.COALESCE)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        return SimpleOut(ok_msg="inner")

class CycleATask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.cycle_a"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        out = ctx.invoke_task("space.cycle_b", EmptyIn())
        if not out.ok and out.error:
            return SimpleOut(ok_msg=out.error.code.value)
        return SimpleOut(ok_msg="a")

class CycleBTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.cycle_b"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        out = ctx.invoke_task("space.cycle_a", EmptyIn())
        if not out.ok and out.error:
            return SimpleOut(ok_msg=out.error.code.value)
        return SimpleOut(ok_msg="b")

class EvCycleStartTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.ev_cycle_start"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.emit(PING_EV, EmptyIn())
        return SimpleOut(ok_msg="started")

class EvCycleSub1Task(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.ev_cycle_sub1"), EmptyIn, SimpleOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("space.ev_ping"), lambda _p: EmptyIn(), payload_type=EmptyIn),),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.emit(PONG_EV, EmptyIn())
        return SimpleOut(ok_msg="sub1")

class EvCycleSub2Task(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.ev_cycle_sub2"), EmptyIn, SimpleOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("space.ev_pong"), lambda _p: EmptyIn(), payload_type=EmptyIn),),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.emit(PING_EV, EmptyIn())
        return SimpleOut(ok_msg="sub2")

class MixCycleEmitTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(TaskId("space.mix_cycle_emit"), EmptyIn, SimpleOut)
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.emit(MIX_CYCLE_EV, EmptyIn())
        return SimpleOut(ok_msg="emitted")

class MixCycleSubTask(Task[EmptyIn, SimpleOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, SimpleOut]:
        return TaskMetadata(
            TaskId("space.mix_cycle_sub"), EmptyIn, SimpleOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("space.mix_cycle_ev"), lambda _p: EmptyIn(), payload_type=EmptyIn),),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> SimpleOut:
        ctx.invoke_task("space.mix_cycle_emit", EmptyIn())
        return SimpleOut(ok_msg="sub")

class SpaceModule(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("space")
    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        def _close_space() -> None:
            marker = workspace_root.join(".cache", "inject_teardown_error.flag")
            if marker.path.exists():
                log_f = workspace_root.join(".cache", "lifo_teardown_order.json")
                cur = read_json_dict(log_f) or {}
                items = list(cur["order"]) if isinstance(cur.get("order"), list) else []
                items.append("space_threw_first_in_lifo")
                atomic_write_json(log_f, {"order": items})
                raise RuntimeError("Simulated close() failure on top-of-LIFO entry")
        return _close_space
    def tasks(self) -> Sequence[BoundTask]:
        return (
            ScanTask(), OnConfigTask(), EchoTier0Task(), DaemonMetricsTask(), HoldLockMsTask(),
            Tier0TimeoutTask(), GiantReplyTask(), OrchestrateChildWsTask(), RemoveAndInstallTask(),
            UpgradeCoreTask(), ReloadTask(), PartialCommitParentTask(), BadHotMutateTask(),
            BadHotCoreMutateTask(), BadEscalateTask(), BadSelfPreemptTask(), BadSelfPreemptInnerTask(),
            BadSelfCoalesceTask(), BadSelfCoalesceInnerTask(), CycleATask(), CycleBTask(),
            EvCycleStartTask(), EvCycleSub1Task(), EvCycleSub2Task(), MixCycleEmitTask(), MixCycleSubTask(),
        )

def create_module() -> YscbModule:
    return SpaceModule()
'''


BROKEN_OPT_MODULE_SRC: Final[str] = '''from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from core.execution.runtime import BoundTask, Task, TaskContext, TaskMetadata, YscbModule
from core.foundation import HostPath, ModuleId, TaskId

@dataclass(frozen=True, slots=True)
class PingIn:
    pass

@dataclass(frozen=True, slots=True)
class PingOut:
    ok: bool

class PingTask(Task[PingIn, PingOut]):
    @property
    def metadata(self) -> TaskMetadata[PingIn, PingOut]:
        return TaskMetadata(TaskId("broken_opt.ping"), PingIn, PingOut)
    def run(self, req: PingIn, ctx: TaskContext) -> PingOut:
        return PingOut(ok=True)

class BrokenOptModule(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("broken_opt")
    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        raise RuntimeError("Simulated corrupt ONNX model weights in shared idx_group")
    def tasks(self) -> Sequence[BoundTask]:
        return (PingTask(),)

def create_module() -> YscbModule:
    return BrokenOptModule()
'''

VSC_MODULE_SRC: Final[str] = '''import time
from dataclasses import dataclass
from core.foundation import ProgressEvent
from typing import Callable, Optional, Sequence
import local_util
from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec
from core.execution.runtime import (
    BoundTask, ConcurrencyMode, SecurityTier, Task, TaskContext, TaskExposure, TaskMetadata, YscbModule
)
from core.filesystem.fs import atomic_write_json, read_json_dict
from core.foundation import EventId, HostPath, ModuleId, TaskId

@dataclass(frozen=True, slots=True)
class VscSyncIn:
    trace_note: str = ""
    sleep_ms: int = 0

@dataclass(frozen=True, slots=True)
class EmptyIn:
    pass

@dataclass(frozen=True, slots=True)
class RemovingPayload:
    space: str
    count: int

@dataclass(frozen=True, slots=True)
class SeqIn:
    seq: int
    batch_size: int = 1

@dataclass(frozen=True, slots=True)
class VscOut:
    synced: bool
    helper_who: str = ""

BRANCH_DONE_EV = EventMetadata(EventId("vsc.branch_done"), EmptyIn, EventOrdering.UNORDERED)

def _map_removing(items: Sequence[RemovingPayload]) -> SeqIn:
    if items[0].space == "fail_strict":
        raise RuntimeError("Strict immediate mapper failure")
    return SeqIn(seq=items[0].count, batch_size=len(items))

class VscSyncTask(Task[VscSyncIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[VscSyncIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.sync"), VscSyncIn, VscOut,
            resource_key="vsc", concurrency_mode=ConcurrencyMode.COALESCE,
            equivalence_fn=lambda _req: "vsc_canonical_all",
            subscriptions=(EventSubscriptionSpec(EventId("space.reloaded"), lambda _p: VscSyncIn(), payload_type=EmptyIn),),
        )
    def run(self, req: VscSyncIn, ctx: TaskContext) -> VscOut:
        if req.sleep_ms > 0:
            steps = max(1, req.sleep_ms // 20)
            for idx in range(steps):
                ctx.cancel_token.raise_if_cancelled()
                ctx.report_progress(ProgressEvent("vsc_sync", idx + 1, steps, "tick"))
                time.sleep(0.02)
        out_f = ctx.workspace_root.join("spaces", "docs", "_auto_schema.json")
        ledger = ctx.workspace_root.join(".cache", "echo_ledger.json")
        def _pre_register(mtime_ns: int, size: int, ino: int = -1) -> None:
            cur = read_json_dict(ledger) or {}
            cur[out_f.comparison_key] = [mtime_ns, size, ino]
            atomic_write_json(ledger, cur)
        atomic_write_json(out_f, {"managed": True}, before_replace=_pre_register)
        ctx.emit(BRANCH_DONE_EV, EmptyIn())
        return VscOut(synced=True, helper_who=local_util.HELPER_WHO)

class VscOnRemovingTask(Task[SeqIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[SeqIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.on_removing"), SeqIn, VscOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(
                EventSubscriptionSpec(
                    EventId("space.removing"),
                    _map_removing,
                    payload_filter={"space": ("vsc", "fail_strict")},
                    payload_type=RemovingPayload,
                ),
            ),
        )
    def run(self, req: SeqIn, ctx: TaskContext) -> VscOut:
        log_f = ctx.workspace_root.join(".cache", "remove_order.json")
        cur = read_json_dict(log_f) or {}
        raw_ord = cur.get("order")
        ord_list = list(raw_ord) if isinstance(raw_ord, list) else []
        ord_list.append(req.seq)
        atomic_write_json(log_f, {"order": ord_list})
        return VscOut(synced=True)

class VscOnOrderedAuditTask(Task[SeqIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[SeqIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.on_ordered_audit"), SeqIn, VscOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(
                EventSubscriptionSpec(
                    EventId("space.ordered_audit"),
                    lambda items: SeqIn(seq=items[0].count, batch_size=len(items)),
                    payload_type=RemovingPayload,
                ),
            ),
        )
    def run(self, req: SeqIn, ctx: TaskContext) -> VscOut:
        log_f = ctx.workspace_root.join(".cache", "deferred_fifo.json")
        cur = read_json_dict(log_f) or {}
        seqs = list(cur["seqs"]) if isinstance(cur.get("seqs"), list) else []
        sizes = list(cur["batch_sizes"]) if isinstance(cur.get("batch_sizes"), list) else []
        seqs.append(req.seq)
        sizes.append(req.batch_size)
        atomic_write_json(log_f, {"seqs": seqs, "batch_sizes": sizes})
        return VscOut(synced=True)

class VscSiblingOkSubTask(Task[EmptyIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.sibling_ok_sub"), EmptyIn, VscOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("kdb.trigger_step5_fail"), lambda _p: EmptyIn()),),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> VscOut:
        atomic_write_json(ctx.workspace_root.join(".cache", "sibling_sub_ok.json"), {"ok": True})
        return VscOut(synced=True)

class VscGatedCleanTask(Task[EmptyIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.gated_clean"), EmptyIn, VscOut,
            security_tier=SecurityTier.GATED,
            resource_key="vsc", concurrency_mode=ConcurrencyMode.SERIALIZE,
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> VscOut:
        return VscOut(synced=True)

class DiamondBTask(Task[EmptyIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.diamond_b"), EmptyIn, VscOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("space.reloaded"), lambda _p: EmptyIn(), payload_type=EmptyIn),),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> VscOut:
        ctx.emit(BRANCH_DONE_EV, EmptyIn())
        return VscOut(synced=True)

@dataclass(frozen=True, slots=True)
class Tier1ImmProbeDto:
    fail_strict: bool = False

class VscTier1ImmSubTask(Task[Tier1ImmProbeDto, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[Tier1ImmProbeDto, VscOut]:
        return TaskMetadata(
            TaskId("vsc.on_tier1_imm"), Tier1ImmProbeDto, VscOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(
                EventSubscriptionSpec(
                    EventId("ast.tier1_imm_probe"),
                    lambda items: Tier1ImmProbeDto(fail_strict=any(x.fail_strict for x in items)),
                    payload_type=Tier1ImmProbeDto,
                ),
            ),
        )
    def run(self, req: Tier1ImmProbeDto, ctx: TaskContext) -> VscOut:
        if req.fail_strict:
            raise RuntimeError("Tier 1 strict imm subscriber boom")
        atomic_write_json(ctx.workspace_root.join(".cache", "tier1_imm_seen.json"), {"sync_seen": True})
        return VscOut(synced=True)

class DiamondMergeTask(Task[EmptyIn, VscOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, VscOut]:
        return TaskMetadata(
            TaskId("vsc.diamond_merge"), EmptyIn, VscOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("vsc.branch_done"), lambda _p: EmptyIn(), payload_type=EmptyIn),),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> VscOut:
        f = ctx.workspace_root.join(".cache", "diamond_merged.json")
        cur = read_json_dict(f) or {}
        prev = cur.get("runs", 0)
        runs = (int(prev) if isinstance(prev, int) else 0) + 1
        atomic_write_json(f, {"runs": runs})
        return VscOut(synced=True)

class VscModule(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("vsc")
    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        wf = workspace_root.join(".cache", "vsc_tier0_warm.json")
        cur = read_json_dict(wf) or {}
        cnt = (int(cur["starts"]) if isinstance(cur.get("starts"), int) else 0) + 1
        atomic_write_json(wf, {"warm": True, "starts": cnt})
        return lambda: None
    def tasks(self) -> Sequence[BoundTask]:
        return (
            VscSyncTask(), VscOnRemovingTask(), VscOnOrderedAuditTask(),
            VscSiblingOkSubTask(), VscGatedCleanTask(), DiamondBTask(), DiamondMergeTask(),
            VscTier1ImmSubTask(),
        )

def create_module() -> YscbModule:
    return VscModule()
'''


DEV_MODULE_SRC: Final[str] = '''from dataclasses import dataclass
import os, sys, time
from typing import Callable, Optional, Sequence
from core.execution.runtime import (
    BoundTask, ClientRoutingPolicy, ConcurrencyMode, DispatchMode, Task, TaskContext, TaskMetadata, YscbModule
)
from core.filesystem.fs import atomic_write_json, read_json_dict
from core.foundation import HostPath, ModuleId, TaskId
from core.foundation import ManagedProcessTree

@dataclass(frozen=True, slots=True)
class SandboxIn:
    child_workspace: str
    spawn_sleep_child: bool = False
    sync_host_install: bool = False

@dataclass(frozen=True, slots=True)
class SandboxOut:
    child_ok: bool
    spawned_pid: int = 0

@dataclass(frozen=True, slots=True)
class HoldLockIn:
    hold_ms: int
    actor: str

class RunSandboxTask(Task[SandboxIn, SandboxOut]):
    @property
    def metadata(self) -> TaskMetadata[SandboxIn, SandboxOut]:
        return TaskMetadata(TaskId("dev.run_sandbox"), SandboxIn, SandboxOut, dispatch_mode=DispatchMode.COLD_ONLY)
    def run(self, req: SandboxIn, ctx: TaskContext) -> SandboxOut:
        child_ws = HostPath(req.child_workspace)
        if not req.spawn_sleep_child:
            if child_ws != ctx.workspace_root:
                sub = ctx.invoke_task(
                    "dev.run_sandbox",
                    SandboxIn(child_workspace=str(child_ws), spawn_sleep_child=False),
                    output_type=SandboxOut,
                    target_workspace=child_ws,
                    routing_policy=ClientRoutingPolicy.AUTO_NO_SPAWN,
                )
                if not sub.ok or sub.value is None or not sub.value.child_ok:
                    return SandboxOut(child_ok=False)
            if req.sync_host_install:
                d_try = ctx.invoke_task("space.daemon_metrics", {})
                d_fc = ctx.invoke_task("space.daemon_metrics", {}, routing_policy=ClientRoutingPolicy.FORCE_COLD)
                if d_try.ok or d_fc.ok or d_fc.error is None or d_fc.error.code.value != "cold_dispatch_forbidden":
                    return SandboxOut(child_ok=False)
                inst = ctx.invoke_task("space.remove_and_install", {"target_module": "vsc", "hold_ms": 0})
                return SandboxOut(child_ok=inst.ok)
            return SandboxOut(child_ok=True)

        ctx.invoke_task("space.echo_tier0", {"tag": "register_space_lifo"})
        tree_script = (
            "import json, os, pathlib, subprocess, sys, time; "
            "cf = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0; "
            "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], creationflags=cf); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'child_pid': os.getpid(), 'grandchild_pid': gc.pid}), encoding='utf-8'); "
            "time.sleep(30)"
        )
        tree_file = str(ctx.workspace_root.join(".cache", "grandchild_pid.json"))
        proc = ManagedProcessTree([sys.executable, "-c", tree_script, tree_file], cwd=ctx.workspace_root)
        ctx.cancel_token.register_callback(lambda _p, _r: proc.terminate_tree(grace_sec=0.2))
        try:
            for _ in range(150):
                ctx.cancel_token.raise_if_cancelled()
                time.sleep(0.02)
        finally:
            proc.terminate_tree(grace_sec=0.2)
        return SandboxOut(child_ok=True, spawned_pid=proc.pid)

class HoldSharedLockTask(Task[HoldLockIn, SandboxOut]):
    @property
    def metadata(self) -> TaskMetadata[HoldLockIn, SandboxOut]:
        return TaskMetadata(
            TaskId("dev.hold_shared_lock"), HoldLockIn, SandboxOut,
            resource_key="cross_proc_key", concurrency_mode=ConcurrencyMode.SERIALIZE
        )
    def run(self, req: HoldLockIn, ctx: TaskContext) -> SandboxOut:
        timeline_f = ctx.workspace_root.join(".cache", "cross_lock_timeline.json")
        t_enter = time.monotonic()
        time.sleep(req.hold_ms / 1000.0)
        t_exit = time.monotonic()
        cur = read_json_dict(timeline_f) or {}
        raw_spans = cur.get("spans")
        spans = list(raw_spans) if isinstance(raw_spans, list) else []
        spans.append({"actor": req.actor, "enter": t_enter, "exit": t_exit})
        atomic_write_json(timeline_f, {"spans": spans})
        return SandboxOut(child_ok=True, spawned_pid=os.getpid())

class DevModule(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("dev")
    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        def _closer() -> None:
            marker = workspace_root.join(".cache", "inject_teardown_error.flag")
            if marker.path.exists():
                log_f = workspace_root.join(".cache", "lifo_teardown_order.json")
                cur = read_json_dict(log_f) or {}
                items = list(cur["order"]) if isinstance(cur.get("order"), list) else []
                items.append("dev_closed_after_space_threw")
                atomic_write_json(log_f, {"order": items})
        return _closer
    def tasks(self) -> Sequence[BoundTask]:
        return (RunSandboxTask(), HoldSharedLockTask())

def create_module() -> YscbModule:
    return DevModule()
'''


AST_MODULE_SRC: Final[str] = '''import time
from dataclasses import dataclass
import os
from typing import Callable, Optional, Sequence
import local_util
from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec
from core.execution.runtime import BoundTask, ConcurrencyMode, Task, TaskContext, TaskMetadata, YscbModule
from core.filesystem.fs import atomic_write_json, read_json_dict
from core.foundation import DataclassCodec
from core.foundation import EventId, HostPath, ModuleId, TaskId

AST_MOD_VER = "ast_v1"

@dataclass(frozen=True, slots=True)
class EchoIn:
    tag: str

@dataclass(frozen=True, slots=True)
class SimpleOut:
    ok_msg: str
    pid: int = 0

@dataclass(frozen=True, slots=True)
class SpaceUpdatedDto:
    space: str
    count: int

@dataclass(frozen=True, slots=True)
class OutlineIn:
    rel_file: str
    call_tier0: bool = False
    fail_imm_strict: bool = False
    uncoop_hang_ms: int = 0
    coop_sleep_ms: int = 0

@dataclass(frozen=True, slots=True)
class OutlineOut:
    resolved_path: str
    exists: bool
    worker_pid: int
    lazy_ready: bool
    module_ver: str
    helper_tag: str = ""
    tier0_echo: str = ""

@dataclass(frozen=True, slots=True)
class Tier1ImmProbeDto:
    fail_strict: bool = False

@dataclass(frozen=True, slots=True)
class AstSyncIn:
    spaces: tuple[str, ...] = ("source", "docs")

@dataclass(frozen=True, slots=True)
class AstSyncOut:
    ast_gen: int
    worker_pid: int

ECHO_T0_META: TaskMetadata[EchoIn, SimpleOut] = TaskMetadata(TaskId("space.echo_tier0"), EchoIn, SimpleOut)
AST_UPDATED_EV = EventMetadata(EventId("ast.graph_updated"), AstSyncOut, EventOrdering.UNORDERED)

class AstModule(YscbModule):
    def __init__(self) -> None:
        self.lazy_parser_handle_open = False

    @property
    def module_id(self) -> ModuleId:
        return ModuleId("ast")

    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        self.lazy_parser_handle_open = True
        atomic_write_json(workspace_root.join(".cache", "ast_lazy_inited.json"), {"inited": True})
        def _close_lazy() -> None:
            self.lazy_parser_handle_open = False
            atomic_write_json(workspace_root.join(".cache", "ast_lazy_closed.json"), {"closed": True})
        return _close_lazy

    def tasks(self) -> Sequence[BoundTask]:
        mod_ref = self

        def _map_space_batch(payloads: Sequence[SpaceUpdatedDto]) -> Optional[AstSyncIn]:
            total = sum(p.count for p in payloads)
            if total == 0:
                return None
            return AstSyncIn(spaces=tuple(p.space for p in payloads))

        class OutlineTask(Task[OutlineIn, OutlineOut]):
            @property
            def metadata(self) -> TaskMetadata[OutlineIn, OutlineOut]:
                return TaskMetadata(TaskId("ast.outline"), OutlineIn, OutlineOut)
            def run(self, req: OutlineIn, ctx: TaskContext) -> OutlineOut:
                if req.uncoop_hang_ms > 0:
                    atomic_write_json(ctx.workspace_root.join(".cache", "ast_uncoop_in.json"), {"pid": os.getpid()})
                    time.sleep(req.uncoop_hang_ms / 1000.0)
                if req.coop_sleep_ms > 0:
                    for _ in range(max(1, req.coop_sleep_ms // 20)):
                        ctx.cancel_token.raise_if_cancelled()
                        time.sleep(0.02)
                full_p = ctx.caller_cwd.resolve_caller_relative(req.rel_file)
                t0 = ""
                if req.call_tier0:
                    imm_marker = ctx.workspace_root.join(".cache", "tier1_imm_seen.json")
                    imm_marker.path.unlink(missing_ok=True)
                    ctx.emit_imm(
                        EventMetadata(EventId("ast.tier1_imm_probe"), Tier1ImmProbeDto, EventOrdering.ORDERED),
                        Tier1ImmProbeDto(fail_strict=req.fail_imm_strict),
                        strict=True,
                    )
                    if not imm_marker.path.is_file():
                        raise RuntimeError("Tier 1 emit_imm did not complete synchronous subscriber before returning!")
                    cb = ctx.invoke_typed(ECHO_T0_META, EchoIn(tag="from_oneshot_tier1"))
                    t0 = cb.value.ok_msg if (cb.ok and cb.value is not None) else ""
                return OutlineOut(
                    resolved_path=str(full_p),
                    exists=full_p.path.is_file(),
                    worker_pid=os.getpid(),
                    lazy_ready=mod_ref.lazy_parser_handle_open,
                    module_ver=AST_MOD_VER,
                    helper_tag=DataclassCodec.decode(local_util.OuterHelper.InnerBox, {'tag': local_util.HELPER_WHO}).tag,
                    tier0_echo=t0,
                )

        class AstSyncTask(Task[AstSyncIn, AstSyncOut]):
            @property
            def metadata(self) -> TaskMetadata[AstSyncIn, AstSyncOut]:
                return TaskMetadata(
                    TaskId("ast.sync"), AstSyncIn, AstSyncOut,
                    resource_key="ast", concurrency_mode=ConcurrencyMode.COALESCE,
                    subscriptions=(
                        EventSubscriptionSpec(
                            EventId("space.updated"),
                            _map_space_batch,
                            payload_filter={"space": ("source", "docs")},
                            payload_type=SpaceUpdatedDto,
                        ),
                    ),
                )

            def run(self, req: AstSyncIn, ctx: TaskContext) -> AstSyncOut:
                st_f = ctx.workspace_root.join(".cache", "ast_state.json")
                cur = read_json_dict(st_f) or {}
                gen = (int(cur["ast_gen"]) if isinstance(cur.get("ast_gen"), int) else 0) + 1
                runs = (int(cur["runs"]) if isinstance(cur.get("runs"), int) else 0) + 1
                atomic_write_json(st_f, {"ast_gen": gen, "runs": runs, "last_spaces": list(req.spaces)})
                out = AstSyncOut(ast_gen=gen, worker_pid=os.getpid())
                ctx.emit(AST_UPDATED_EV, out)
                return out

        return (OutlineTask(), AstSyncTask())

def create_module() -> YscbModule:
    return AstModule()
'''

KDB_MODULE_SRC: Final[str] = '''from dataclasses import dataclass
import os, time
from typing import Callable, Optional, Sequence
from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec
from core.execution.runtime import (
    BoundTask, ConcurrencyMode, Task, TaskContext, TaskExposure, TaskMetadata, YscbModule
)
from core.filesystem.fs import FileLock, atomic_write_json, read_json_dict
from core.foundation import TaskCancelledException
from core.foundation import ProgressEvent
from core.foundation import EventId, HostPath, ModuleId, TaskId

@dataclass(frozen=True, slots=True)
class EmptyEvDto:
    pass

@dataclass(frozen=True, slots=True)
class AstSyncIn:
    spaces: tuple[str, ...] = ("source", "docs")

@dataclass(frozen=True, slots=True)
class AstSyncOut:
    ast_gen: int
    worker_pid: int

@dataclass(frozen=True, slots=True)
class SearchIn:
    query: str
    sync: bool = False
    sleep_ms: int = 0
    post_sync: bool = False

@dataclass(frozen=True, slots=True)
class SearchOut:
    query: str
    warm_model_ready: bool
    kdb_gen: int
    worker_pid: int

@dataclass(frozen=True, slots=True)
class IndexIn:
    force: bool = False
    export_path: str = ""
    sleep_ms: int = 0
    trigger_step5_error: bool = False
    fail_primary: bool = False
    trigger_ev_cycle: bool = False

@dataclass(frozen=True, slots=True)
class IndexOut:
    kdb_gen: int
    observed_priority: str
    exported_to: str = ""

@dataclass(frozen=True, slots=True)
class BgIndexIn:
    ast_gen: int
    slow_ms: int = 160

AST_SYNC_META: TaskMetadata[AstSyncIn, AstSyncOut] = TaskMetadata(
    TaskId("ast.sync"), AstSyncIn, AstSyncOut,
    resource_key="ast", concurrency_mode=ConcurrencyMode.COALESCE,
)
KDB_INDEX_META: TaskMetadata[IndexIn, IndexOut] = TaskMetadata(
    TaskId("kdb.index"), IndexIn, IndexOut,
    resource_key="kdb", concurrency_mode=ConcurrencyMode.COALESCE,
)
TRIGGER_FAIL_EV = EventMetadata(EventId("kdb.trigger_step5_fail"), SearchIn, EventOrdering.UNORDERED)

def _map_ast_updated(items: Sequence[AstSyncOut]) -> BgIndexIn:
    return BgIndexIn(ast_gen=max(item.ast_gen for item in items))

class SearchTask(Task[SearchIn, SearchOut]):
    def __init__(self, mod_ref: "KdbModule") -> None:
        self._mod_ref = mod_ref
    @property
    def metadata(self) -> TaskMetadata[SearchIn, SearchOut]:
        return TaskMetadata(TaskId("kdb.search"), SearchIn, SearchOut)
    def run(self, req: SearchIn, ctx: TaskContext) -> SearchOut:
        if req.sync:
            atomic_write_json(ctx.workspace_root.join(".cache", "search_sync_entered.json"), {"q": req.query})
            idx_in = IndexIn(
                force=False,
                sleep_ms=260,
                trigger_ev_cycle=(req.query == "ev_cyc"),
                trigger_step5_error=(req.query == "ev_err"),
            )
            idx_out = ctx.invoke_typed(KDB_INDEX_META, idx_in)
            if not idx_out.ok:
                raise RuntimeError(f"Sync index failed: {idx_out.error}")
            if req.query == "cross_layer_must_coalesce" and not idx_out.coalesced:
                raise RuntimeError("Expected nested kdb.index to coalesce with in-flight top-level kdb.index!")
        if req.sleep_ms > 0:
            atomic_write_json(ctx.workspace_root.join(".cache", "kdb_search_in.json"), {"q": req.query})
        for _ in range(req.sleep_ms // 20 if req.sleep_ms > 0 else 0):
            ctx.cancel_token.raise_if_cancelled()
            time.sleep(0.02)
        if req.post_sync:
            ps_out = ctx.invoke_typed(KDB_INDEX_META, IndexIn(force=False, sleep_ms=10))
            if not ps_out.ok:
                raise RuntimeError(f"Post-sleep nested index failed: {ps_out.error}")
        st = read_json_dict(ctx.workspace_root.join(".cache", "kdb_state.json")) or {}
        kgen = int(st["kdb_gen"]) if isinstance(st.get("kdb_gen"), int) else 0
        return SearchOut(req.query, self._mod_ref.warm_model_loaded, kgen, os.getpid())

class IndexTask(Task[IndexIn, IndexOut]):
    @property
    def metadata(self) -> TaskMetadata[IndexIn, IndexOut]:
        return KDB_INDEX_META
    def run(self, req: IndexIn, ctx: TaskContext) -> IndexOut:
        ast_out = ctx.invoke_typed(AST_SYNC_META, AstSyncIn(spaces=("source", "docs")))
        if not ast_out.ok:
            raise RuntimeError(f"Upstream ast.sync failed: {ast_out.error}")
        steps = max(1, req.sleep_ms // 20) if req.sleep_ms > 0 else 0
        for i in range(steps):
            ctx.cancel_token.raise_if_cancelled()
            ctx.report_progress(ProgressEvent("indexing", i + 1, steps, "chunk"))
            time.sleep(0.02)
        if req.fail_primary:
            raise RuntimeError("Simulated primary COALESCE leader crash")
        st_f = ctx.workspace_root.join(".cache", "kdb_state.json")
        cur = read_json_dict(st_f) or {}
        prev_gen = int(cur["kdb_gen"]) if isinstance(cur.get("kdb_gen"), int) else 0
        new_gen = prev_gen + (10 if req.force else 1)
        atomic_write_json(st_f, {"kdb_gen": new_gen})
        exp_str = ""
        if req.export_path:
            out_p = ctx.caller_cwd.resolve_caller_relative(req.export_path)
            atomic_write_json(out_p, {"kdb_gen": new_gen, "force": req.force})
            exp_str = str(out_p)
        if req.trigger_step5_error:
            ctx.emit(TRIGGER_FAIL_EV, SearchIn(query="boom"))
        if req.trigger_ev_cycle:
            ctx.emit(EventMetadata(EventId("space.ev_ping"), EmptyEvDto, EventOrdering.UNORDERED), EmptyEvDto())
        return IndexOut(kdb_gen=new_gen, observed_priority=ctx.effective_priority.value, exported_to=exp_str)

class BgPreemptIndexTask(Task[BgIndexIn, IndexOut]):
    @property
    def metadata(self) -> TaskMetadata[BgIndexIn, IndexOut]:
        return TaskMetadata(
            TaskId("kdb.bg_preempt_index"), BgIndexIn, IndexOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            resource_key="kdb_bg", concurrency_mode=ConcurrencyMode.PREEMPT,
            subscriptions=(EventSubscriptionSpec(EventId("ast.graph_updated"), _map_ast_updated, payload_type=AstSyncOut),),
        )
    def run(self, req: BgIndexIn, ctx: TaskContext) -> IndexOut:
        atomic_write_json(ctx.workspace_root.join(".cache", "kdb_bg_inflight.json"), {"in_flight_gen": req.ast_gen})
        cfg_b = read_json_dict(ctx.workspace_root.join("config", "kdb.json")) or {}
        w1_ms = int(cfg_b["bg_wave1_ms"]) if (req.ast_gen == 1 and isinstance(cfg_b.get("bg_wave1_ms"), int)) else req.slow_ms
        try:
            for _ in range(max(1, w1_ms // 20)):
                ctx.cancel_token.raise_if_cancelled()
                time.sleep(0.02)
        except TaskCancelledException:
            p_f = ctx.workspace_root.join(".cache", "kdb_preempt_stats.json")
            cur = read_json_dict(p_f) or {}
            cnt = (int(cur["preempted_count"]) if isinstance(cur.get("preempted_count"), int) else 0) + 1
            atomic_write_json(p_f, {"preempted_count": cnt, "aborted_gen": req.ast_gen})
            raise
        atomic_write_json(ctx.workspace_root.join(".cache", "kdb_bg_state.json"), {"acked_ast_gen": req.ast_gen})
        return IndexOut(kdb_gen=req.ast_gen, observed_priority=ctx.effective_priority.value)

class FailSubTask(Task[SearchIn, SearchOut]):
    @property
    def metadata(self) -> TaskMetadata[SearchIn, SearchOut]:
        return TaskMetadata(
            TaskId("kdb.fail_sub"), SearchIn, SearchOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            resource_key="kdb_fail_sub_res", concurrency_mode=ConcurrencyMode.COALESCE,
            subscriptions=(EventSubscriptionSpec(EventId("kdb.trigger_step5_fail"), lambda _p: SearchIn(query="x"), payload_type=SearchIn),),
        )
    def run(self, req: SearchIn, ctx: TaskContext) -> SearchOut:
        time.sleep(0.08)
        raise RuntimeError("Simulated Step 5 subscriber failure")

class KdbModule(YscbModule):
    def __init__(self) -> None:
        self.warm_model_loaded = False
        self._db_lock: Optional[FileLock] = None
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("kdb")
    def _unload_model(self) -> None:
        self.warm_model_loaded = False
        if self._db_lock is not None:
            self._db_lock.release()
            self._db_lock = None
    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        lk = FileLock(workspace_root.join(".cache", "locks", "kdb_exclusive_warm.lock"))
        if not lk.acquire(shared=False, blocking=False):
            raise RuntimeError("Exclusive kdb warm DB lock collision with unstopped worker!")
        self._db_lock = lk
        kdb_cfg = read_json_dict(workspace_root.join("config", "kdb.json")) or {}
        delay_ms = int(kdb_cfg["warmup_delay_ms"]) if isinstance(kdb_cfg.get("warmup_delay_ms"), int) else 0
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        self.warm_model_loaded = True
        return self._unload_model
    def tasks(self) -> Sequence[BoundTask]:
        return (SearchTask(self), IndexTask(), BgPreemptIndexTask(), FailSubTask())

def create_module() -> YscbModule:
    return KdbModule()
'''

GDRIVE_MODULE_SRC: Final[str] = '''from dataclasses import dataclass
import os, signal, sys, time
from typing import Sequence
from core.execution.runtime import (
    BoundTask, ConcurrencyMode, DispatchMode, PeriodicScheduleSpec, SecurityTier,
    Task, TaskContext, TaskExposure, TaskMetadata, YscbModule
)
from core.filesystem.fs import atomic_write_json, read_json_dict
from core.foundation import ModuleId, TaskId

@dataclass(frozen=True, slots=True)
class AuthIn:
    code: str = ""

@dataclass(frozen=True, slots=True)
class PutIn:
    local_rel: str
    crash_after_accept: bool = False
    hang_ms: int = 0

@dataclass(frozen=True, slots=True)
class GdriveOut:
    status: str
    proxy_seen: str = ""
    leaked_secret_seen: str = ""
    worker_pid: int = 0
    venv_prefix: str = ""

@dataclass(frozen=True, slots=True)
class EmptyIn:
    pass

class AuthTask(Task[AuthIn, GdriveOut]):
    @property
    def metadata(self) -> TaskMetadata[AuthIn, GdriveOut]:
        return TaskMetadata(
            TaskId("gdrive.auth"), AuthIn, GdriveOut,
            dispatch_mode=DispatchMode.COLD_ONLY, interactive_tty=True, security_tier=SecurityTier.CONDITIONAL
        )
    def run(self, req: AuthIn, ctx: TaskContext) -> GdriveOut:
        code_val = req.code
        tty_flag = bool(sys.stdin.isatty() and sys.stdout.isatty())
        if not code_val:
            sys.stdout.write("OAUTH_PROMPT>")
            sys.stdout.flush()
            code_val = sys.stdin.readline().strip()
        tok_f = ctx.workspace_root.join(".cache", "oauth_token.json")
        atomic_write_json(tok_f, {"token": f"tok_{code_val}", "tty": tty_flag})
        return GdriveOut(status="authorized", worker_pid=os.getpid())

class PeriodicSyncTask(Task[EmptyIn, GdriveOut]):
    @property
    def metadata(self) -> TaskMetadata[EmptyIn, GdriveOut]:
        return TaskMetadata(
            TaskId("gdrive.periodic_sync"), EmptyIn, GdriveOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            resource_key="gdrive_sync", concurrency_mode=ConcurrencyMode.SERIALIZE,
            periodic=PeriodicScheduleSpec(0.10, enabled_config_key="auto_sync", interval_config_key="interval_sec"),
        )
    def run(self, req: EmptyIn, ctx: TaskContext) -> GdriveOut:
        cfg_d = read_json_dict(ctx.workspace_root.join("config", "gdrive.json")) or {}
        work_ms = int(cfg_d["work_ms"]) if isinstance(cfg_d.get("work_ms"), int) else 0
        f = ctx.workspace_root.join(".cache", "gdrive_periodic.json")
        cur = read_json_dict(f) or {}
        active_now = (int(cur["in_flight"]) if isinstance(cur.get("in_flight"), int) else 0) + 1
        max_conc = max(active_now, int(cur["max_conc"]) if isinstance(cur.get("max_conc"), int) else 0)
        ticks_prev = int(cur["ticks"]) if isinstance(cur.get("ticks"), int) else 0
        atomic_write_json(f, {"ticks": ticks_prev, "in_flight": active_now, "max_conc": max_conc, "phase": "started"})
        if work_ms > 0:
            time.sleep(work_ms / 1000.0)
        cur2 = read_json_dict(f) or {}
        ticks = (int(cur2["ticks"]) if isinstance(cur2.get("ticks"), int) else 0) + 1
        atomic_write_json(f, {"ticks": ticks, "in_flight": 0, "max_conc": max_conc, "phase": "completed"})
        return GdriveOut(status="synced", worker_pid=os.getpid())

class PutTask(Task[PutIn, GdriveOut]):
    @property
    def metadata(self) -> TaskMetadata[PutIn, GdriveOut]:
        return TaskMetadata(
            TaskId("gdrive.put"), PutIn, GdriveOut,
            security_tier=SecurityTier.CONDITIONAL,
            resource_key="gdrive_sync", concurrency_mode=ConcurrencyMode.SERIALIZE,
            timeout_ms=1000,
        )
    def run(self, req: PutIn, ctx: TaskContext) -> GdriveOut:
        runs_f = ctx.workspace_root.join(".cache", "gdrive_put_runs.json")
        cur = read_json_dict(runs_f) or {}
        attempts = (int(cur["attempts"]) if isinstance(cur.get("attempts"), int) else 0) + 1
        atomic_write_json(runs_f, {"attempts": attempts})
        if req.crash_after_accept:
            sig = signal.SIGTERM if sys.platform == "win32" else signal.SIGKILL
            os.kill(os.getpid(), sig)
        if req.hang_ms > 0:
            time.sleep(req.hang_ms / 1000.0)
        resolved = ctx.caller_cwd.resolve_caller_relative(req.local_rel)
        return GdriveOut(
            status=f"uploaded:{resolved.path.name}",
            proxy_seen=ctx.caller_env.get("HTTPS_PROXY", ""),
            leaked_secret_seen=ctx.caller_env.get("AWS_SECRET_ACCESS_KEY", ""),
            worker_pid=os.getpid(),
            venv_prefix=sys.prefix,
        )

class GdriveModule(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("gdrive")
    def tasks(self) -> Sequence[BoundTask]:
        return (AuthTask(), PeriodicSyncTask(), PutTask())

def create_module() -> YscbModule:
    return GdriveModule()
'''

COORD_PROBE_MOD_SRC: Final[str] = '''from dataclasses import dataclass
import time
from typing import Sequence
from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec
from core.execution.runtime import BoundTask, ConcurrencyMode, Task, TaskContext, TaskExposure, TaskMetadata, YscbModule
from core.filesystem.fs import atomic_write_json, read_json_dict
from core.foundation import EventId, ModuleId, TaskId

@dataclass(frozen=True, slots=True)
class ProbeIn:
    mode: str = ""
    hold_ms: int = 0
    after_ms: int = 0
    fast: bool = False

@dataclass(frozen=True, slots=True)
class ProbeOut:
    ok_tag: str
    coalesced_sub: bool = False

EV_SLOW = EventMetadata(EventId("cprobe.slow_ev"), ProbeIn, EventOrdering.UNORDERED)
EV_CYC = EventMetadata(EventId("cprobe.cyc_ev"), ProbeIn, EventOrdering.UNORDERED)
EV_ORPH = EventMetadata(EventId("cprobe.orph_ev"), ProbeIn, EventOrdering.UNORDERED)
CHILD_META = TaskMetadata(TaskId("cprobe.child_slow"), ProbeIn, ProbeOut, resource_key="cp_child", concurrency_mode=ConcurrencyMode.SERIALIZE)
COAL_C1B_META = TaskMetadata(TaskId("cprobe.coal_c1b"), ProbeIn, ProbeOut, resource_key="cp_c1b", concurrency_mode=ConcurrencyMode.COALESCE)
COAL_C2_META = TaskMetadata(TaskId("cprobe.coal_c2"), ProbeIn, ProbeOut, resource_key="cp_c2", concurrency_mode=ConcurrencyMode.COALESCE, equivalence_fn=lambda r: f"c2:{r.mode}:{r.hold_ms}")
COAL_C3_META = TaskMetadata(TaskId("cprobe.coal_c3"), ProbeIn, ProbeOut, resource_key="cp_c3", concurrency_mode=ConcurrencyMode.COALESCE, timeout_ms=520)

class ChildSlowTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return CHILD_META
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "child_in.json"), {"in": True})
        for _ in range(max(1, req.hold_ms // 15)):
            if ctx.cancel_token.is_cancelled:
                atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "child_cancelled.json"), {"cancelled": True})
                ctx.cancel_token.raise_if_cancelled()
            time.sleep(0.015)
        return ProbeOut(ok_tag="child_done")

class ParentPreemptTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.parent_preempt"), ProbeIn, ProbeOut, resource_key="cp_pre", concurrency_mode=ConcurrencyMode.PREEMPT)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        if req.fast:
            return ProbeOut(ok_tag="fast_winner")
        sub = ctx.invoke_typed(CHILD_META, ProbeIn(hold_ms=req.hold_ms))
        if not sub.ok:
            ctx.cancel_token.raise_if_cancelled()
            raise RuntimeError(f"child failed: {sub.error}")
        return ProbeOut(ok_tag="slow_done")

class CoalC1bTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return COAL_C1B_META
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        sub = ctx.invoke_typed(CHILD_META, ProbeIn(hold_ms=req.hold_ms))
        if not sub.ok:
            raise RuntimeError(f"nested child aborted: {sub.error}")
        return ProbeOut(ok_tag="c1b_ok")

class OuterJoinC1bTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c1b"), ProbeIn, ProbeOut)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        r = ctx.invoke_typed(COAL_C1B_META, req)
        if not r.ok:
            raise RuntimeError(f"c1b join failed: {r.error}")
        return ProbeOut(ok_tag="joined_ok", coalesced_sub=r.coalesced)

class CoalC2Task(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return COAL_C2_META
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "c2_in.json"), {"in": True})
        time.sleep(max(0.02, req.hold_ms / 1000.0))
        if req.mode == "slow_sub":
            ctx.emit(EV_SLOW, ProbeIn(hold_ms=550))
        elif req.mode == "cyc_sub":
            ctx.emit(EV_CYC, ProbeIn(hold_ms=260))
        return ProbeOut(ok_tag="c2_step_done")

class OuterC2Task(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c2"), ProbeIn, ProbeOut)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        r = ctx.invoke_typed(COAL_C2_META, req)
        if not r.ok:
            raise RuntimeError(f"c2 failed: {r.error}")
        if req.after_ms > 0:
            atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "after_in.json"), {"in": True})
        for _ in range(req.after_ms // 15):
            ctx.cancel_token.raise_if_cancelled()
            time.sleep(0.015)
        return ProbeOut(ok_tag="outer_c2_ok", coalesced_sub=r.coalesced)

class OuterC2HopTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c2_hop"), ProbeIn, ProbeOut, resource_key="cp_hop", concurrency_mode=ConcurrencyMode.COALESCE)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        time.sleep(0.03)
        r = ctx.invoke_typed(COAL_C2_META, req)
        if not r.ok:
            raise RuntimeError(f"c2 hop failed: {r.error}")
        return ProbeOut(ok_tag="hop_ok", coalesced_sub=r.coalesced)

class OuterC2ThrowTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c2_throw"), ProbeIn, ProbeOut)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        _ = ctx.invoke_typed(COAL_C2_META, req)
        raise RuntimeError("outer non-fatal boom after joining cycle host")

class BgTrigSubTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(
            TaskId("cprobe.bg_trig_sub"), ProbeIn, ProbeOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("cprobe.bg_start"), lambda _items: ProbeIn(mode="cyc_sub", hold_ms=90)),),
        )
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        _ = ctx.invoke_typed(COAL_C2_META, req)
        return ProbeOut(ok_tag="bg_done")

class Tier0PreemptTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.t0_preempt"), ProbeIn, ProbeOut, resource_key="cp_t0p", concurrency_mode=ConcurrencyMode.PREEMPT, timeout_ms=2500)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        log_p = ctx.workspace_root.join(".cache_cprobe", "t0p_order.json")
        if req.fast:
            prev = list((read_json_dict(log_p) or {}).get("seq", []))
            prev.append("win")
            atomic_write_json(log_p, {"seq": prev})
            return ProbeOut(ok_tag="t0_preempt_won")
        atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "t0p_in.json"), {"in": True})
        time.sleep(req.hold_ms / 1000.0)
        prev = list((read_json_dict(log_p) or {}).get("seq", []))
        prev.append("old")
        atomic_write_json(log_p, {"seq": prev})
        return ProbeOut(ok_tag="t0_uncoop_done")

class OuterC2TimedTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c2_timed"), ProbeIn, ProbeOut, timeout_ms=130)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        r = ctx.invoke_typed(COAL_C2_META, req)
        if not r.ok:
            raise RuntimeError(f"c2 timed failed: {r.error}")
        return ProbeOut(ok_tag="outer_c2_timed_ok", coalesced_sub=r.coalesced)

class SlowSubTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(
            TaskId("cprobe.slow_sub"), ProbeIn, ProbeOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("cprobe.slow_ev"), lambda items: items[0]),),
        )
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "sub_in.json"), {"in": True})
        time.sleep(req.hold_ms / 1000.0)
        return ProbeOut(ok_tag="sub_done")

class CycSubTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(
            TaskId("cprobe.cyc_sub"), ProbeIn, ProbeOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("cprobe.cyc_ev"), lambda items: items[0]),),
        )
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        time.sleep(req.hold_ms / 1000.0)
        ctx.emit(EV_CYC, ProbeIn(hold_ms=10))
        return ProbeOut(ok_tag="never")

class HoldC3Task(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.hold_c3"), ProbeIn, ProbeOut, resource_key="cp_c3", concurrency_mode=ConcurrencyMode.SERIALIZE)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "blocker_in.json"), {"in": True})
        rel_f = ctx.workspace_root.join(".cache_cprobe", "blocker_release.json").path
        dl = time.monotonic() + (req.hold_ms / 1000.0)
        while time.monotonic() < dl and not rel_f.is_file():
            time.sleep(0.015)
        return ProbeOut(ok_tag="held")

class CoalC3Task(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return COAL_C3_META
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        time.sleep(req.hold_ms / 1000.0)
        ctx.emit(EV_ORPH, ProbeIn())
        return ProbeOut(ok_tag="c3_done")

class OuterC3StarterTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c3_starter"), ProbeIn, ProbeOut)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        sub = ctx.invoke_typed(COAL_C3_META, req)
        atomic_write_json(ctx.workspace_root.join(".cache_cprobe", "starter_timed_out.json"), {"ok": sub.ok})
        time.sleep(0.16)
        return ProbeOut(ok_tag="starter_survived" if not sub.ok else "unexpected")

class OuterC3FollowerTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(TaskId("cprobe.outer_c3_foll"), ProbeIn, ProbeOut)
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        sub = ctx.invoke_typed(COAL_C3_META, req)
        if not sub.ok:
            raise RuntimeError(f"c3 follower failed: {sub.error}")
        return ProbeOut(ok_tag="foll_ok", coalesced_sub=sub.coalesced)

class OrphSubTask(Task[ProbeIn, ProbeOut]):
    @property
    def metadata(self) -> TaskMetadata[ProbeIn, ProbeOut]:
        return TaskMetadata(
            TaskId("cprobe.orph_sub"), ProbeIn, ProbeOut,
            exposure=TaskExposure.INTERNAL_TRIGGER,
            subscriptions=(EventSubscriptionSpec(EventId("cprobe.orph_ev"), lambda _items: ProbeIn()),),
        )
    def run(self, req: ProbeIn, ctx: TaskContext) -> ProbeOut:
        f = ctx.workspace_root.join(".cache_cprobe", "orph_count.json")
        cur = read_json_dict(f) or {}
        prev = int(cur["n"]) if isinstance(cur.get("n"), int) else 0
        atomic_write_json(f, {"n": prev + 1})
        return ProbeOut(ok_tag="orph_ok")

class CoordProbeMod(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("cprobe")
    def tasks(self) -> Sequence[BoundTask]:
        return (
            ChildSlowTask(), ParentPreemptTask(), CoalC1bTask(), OuterJoinC1bTask(),
            CoalC2Task(), OuterC2Task(), OuterC2HopTask(), OuterC2ThrowTask(), BgTrigSubTask(), Tier0PreemptTask(), OuterC2TimedTask(), SlowSubTask(),
            CycSubTask(), HoldC3Task(), CoalC3Task(), OuterC3StarterTask(),
            OuterC3FollowerTask(), OrphSubTask(),
        )

def create_module() -> YscbModule:
    return CoordProbeMod()
'''

XGRP_OUTER_SRC: Final[str] = (
    "from dataclasses import dataclass\nimport time\nfrom typing import Sequence\n"
    "from core.execution.runtime import BoundTask, Task, TaskContext, TaskMetadata, YscbModule\n"
    "from core.filesystem.fs import atomic_write_json\n"
    "from core.foundation import ModuleId, TaskId\n"
    "@dataclass(frozen=True, slots=True)\nclass XIn:\n    hold_ms: int = 120\n"
    "@dataclass(frozen=True, slots=True)\nclass XOut:\n    inner_v: int = 0\n"
    "class OuterT(Task[XIn, XOut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[XIn, XOut]: return TaskMetadata(TaskId('xg1.outer'), XIn, XOut)\n"
    "    def run(self, req: XIn, ctx: TaskContext) -> XOut:\n"
    "        atomic_write_json(ctx.workspace_root.join('.cache', 'xg1_in.json'), {'in': True})\n"
    "        time.sleep(req.hold_ms / 1000.0)\n"
    "        res = ctx.invoke_task(TaskId('xg2.inner'), {})\n"
    "        v = res.value.get('v', 0) if (res.ok and isinstance(res.value, dict)) else -1\n"
    "        return XOut(inner_v=int(v) if isinstance(v, int) else -1)\n"
    "class Xg1Mod(YscbModule):\n"
    "    @property\n    def module_id(self) -> ModuleId: return ModuleId('xg1')\n"
    "    def tasks(self) -> Sequence[BoundTask]: return (OuterT(),)\n"
    "def create_module() -> YscbModule: return Xg1Mod()\n"
)

XGRP_INNER_SRC: Final[str] = (
    "from dataclasses import dataclass\nimport os, signal\nfrom typing import Callable, Optional, Sequence\n"
    "from core.execution.runtime import BoundTask, ConcurrencyMode, Task, TaskContext, TaskMetadata, YscbModule\n"
    "from core.filesystem.fs import atomic_write_json\n"
    "from core.foundation import HostPath, ModuleId, TaskId\n"
    "@dataclass(frozen=True, slots=True)\nclass YIn:\n    x: int = 0\n"
    "@dataclass(frozen=True, slots=True)\nclass YOut:\n    v: int = 77\n"
    "class InnerT(Task[YIn, YOut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[YIn, YOut]:\n"
    "        return TaskMetadata(TaskId('xg2.inner'), YIn, YOut, resource_key='rk_xg2', concurrency_mode=ConcurrencyMode.COALESCE)\n"
    "    def run(self, req: YIn, ctx: TaskContext) -> YOut: return YOut()\n"
    "class Xg2Mod(YscbModule):\n"
    "    @property\n    def module_id(self) -> ModuleId: return ModuleId('xg2')\n"
    "    def on_start(self, ws: HostPath) -> Optional[Callable[[], None]]:\n"
    "        if ws.join('.cache', 'crash_xg2_start.json').path.is_file(): os.kill(os.getpid(), signal.SIGTERM if os.name == 'nt' else signal.SIGKILL)\n"
    "        atomic_write_json(ws.join('.cache', 'xg2_started.json'), {'ok': True})\n"
    "        return None\n"
    "    def tasks(self) -> Sequence[BoundTask]: return (InnerT(),)\n"
    "def create_module() -> YscbModule: return Xg2Mod()\n"
)

PRIVATE_FATAL_MOD_SRC: Final[str] = (
    "from dataclasses import dataclass\nimport time\nfrom typing import Sequence\n"
    "from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec\n"
    "from core.execution.runtime import BoundTask, ConcurrencyMode, Task, TaskContext, TaskExposure, TaskMetadata, YscbModule\n"
    "from core.filesystem.fs import atomic_write_json\n"
    "from core.foundation import EventId, ModuleId, TaskId\n"
    "@dataclass(frozen=True, slots=True)\nclass PIn:\n    x: int = 0\n"
    "@dataclass(frozen=True, slots=True)\nclass POut:\n    ok: bool = True\n"
    "EV_OK = EventMetadata(EventId('pfm.ev_ok'), PIn, EventOrdering.UNORDERED)\n"
    "EV_PRE = EventMetadata(EventId('pfm.ev_pre'), PIn, EventOrdering.UNORDERED)\n"
    "def _mp(items: Sequence[PIn]) -> PIn: return items[0] if items else PIn()\n"
    "class Prod(Task[PIn, POut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[PIn, POut]:\n"
    "        return TaskMetadata(TaskId('pfm.prod'), PIn, POut, resource_key='rk_pf', concurrency_mode=ConcurrencyMode.COALESCE, equivalence_fn=lambda _r: 'p')\n"
    "    def run(self, req: PIn, ctx: TaskContext) -> POut:\n"
    "        atomic_write_json(ctx.workspace_root.join('.cache', 'pfm_in.json'), {'in': True})\n"
    "        time.sleep(0.14)\n        ctx.emit(EV_OK, PIn())\n        return POut()\n"
    "class SubOk(Task[PIn, POut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[PIn, POut]:\n"
    "        return TaskMetadata(TaskId('pfm.sub_ok'), PIn, POut, exposure=TaskExposure.INTERNAL_TRIGGER, subscriptions=(EventSubscriptionSpec(EventId('pfm.ev_ok'), _mp, payload_type=PIn),))\n"
    "    def run(self, req: PIn, ctx: TaskContext) -> POut:\n"
    "        atomic_write_json(ctx.workspace_root.join('.cache', 'pfm_ev_delivered.json'), {'ok': True})\n        return POut()\n"
    "class BadF1(Task[PIn, POut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[PIn, POut]: return TaskMetadata(TaskId('pfm.bad_f1'), PIn, POut)\n"
    "    def run(self, req: PIn, ctx: TaskContext) -> POut:\n"
    "        ctx.invoke_task(TaskId('pfm.prod'), {})\n"
    "        ctx.invoke_task(TaskId('pfm.bad_f1'), {})\n        return POut()\n"
    "class TrigF2(Task[PIn, POut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[PIn, POut]: return TaskMetadata(TaskId('pfm.trig_f2'), PIn, POut)\n"
    "    def run(self, req: PIn, ctx: TaskContext) -> POut:\n"
    "        ctx.emit(EV_PRE, PIn())\n        return POut()\n"
    "class GoodF2(Task[PIn, POut]):\n"
    "    @property\n    def metadata(self) -> TaskMetadata[PIn, POut]:\n"
    "        return TaskMetadata(TaskId('pfm.good_f2'), PIn, POut, exposure=TaskExposure.INTERNAL_TRIGGER, subscriptions=(EventSubscriptionSpec(EventId('pfm.ev_pre'), _mp, payload_type=PIn),))\n"
    "    def run(self, req: PIn, ctx: TaskContext) -> POut:\n"
    "        ctx.invoke_task(TaskId('pfm.prod'), {})\n        return POut()\n"
    "class PfMod(YscbModule):\n"
    "    @property\n    def module_id(self) -> ModuleId: return ModuleId('pfm')\n"
    "    def tasks(self) -> Sequence[BoundTask]: return (Prod(), SubOk(), BadF1(), TrigF2(), GoodF2())\n"
    "def create_module() -> YscbModule: return PfMod()\n"
)


EMBEDDED_MODULE_TEMPLATES: Final[tuple[tuple[str, str], ...]] = (
    ("space", SPACE_MODULE_SRC),
    ("broken_opt", BROKEN_OPT_MODULE_SRC),
    ("vsc", VSC_MODULE_SRC),
    ("dev", DEV_MODULE_SRC),
    ("ast", AST_MODULE_SRC),
    ("kdb", KDB_MODULE_SRC),
    ("gdrive", GDRIVE_MODULE_SRC),
    ("cprobe", COORD_PROBE_MOD_SRC),
    ("xg1", XGRP_OUTER_SRC),
    ("xg2", XGRP_INNER_SRC),
    ("pfm", PRIVATE_FATAL_MOD_SRC),
)


def provision_core_tier0_modules(ws: Path) -> None:
    write_module(
        ws,
        "space",
        {
            "tier1": False,
            "eager_warmup": False,
            "tasks": [
                {"task_id": "space.scan", "exposure": "internal_trigger"},
                {"task_id": "space.on_config", "exposure": "internal_trigger", "subscriptions": [{"event_id": "core.config_changed"}]},
                {"task_id": "space.echo_tier0", "exposure": "cli_and_sdk", "cli_path": ["space", "echo"]},
                {"task_id": "space.daemon_metrics", "exposure": "sdk_only", "dispatch_mode": "daemon_only"},
                {"task_id": "space.hold_lock_ms", "resource_key": "rc04_serial", "concurrency_mode": "serialize"},
                {"task_id": "space.tier0_timeout", "resource_key": "rc04_serial", "concurrency_mode": "serialize", "timeout_ms": 60},
                {"task_id": "space.giant_reply", "dispatch_mode": "daemon_only"},
                {"task_id": "space.orchestrate_child_ws", "dispatch_mode": "daemon_only"},
                {
                    "task_id": "space.remove_and_install",
                    "dispatch_mode": "cold_only",
                    "mutation_scope": "mutates_modules",
                    "security_tier": "gated",
                    "resource_key": "installer",
                    "concurrency_mode": "serialize",
                },
                {
                    "task_id": "space.upgrade_core",
                    "dispatch_mode": "cold_only",
                    "mutation_scope": "mutates_core",
                    "security_tier": "gated",
                    "resource_key": "installer",
                    "concurrency_mode": "serialize",
                },
                {"task_id": "space.reload", "resource_key": "installer", "concurrency_mode": "serialize"},
                {"task_id": "space.partial_commit_parent"},
                {"task_id": "space.bad_hot_mutate"},
                {"task_id": "space.bad_hot_core_mutate"},
                {"task_id": "space.bad_escalate"},
                {"task_id": "space.bad_self_preempt", "resource_key": "self_p", "concurrency_mode": "serialize"},
                {"task_id": "space.bad_self_preempt_inner", "resource_key": "self_p", "concurrency_mode": "preempt"},
                {"task_id": "space.bad_self_coalesce", "resource_key": "self_c", "concurrency_mode": "serialize"},
                {"task_id": "space.bad_self_coalesce_inner", "resource_key": "self_c", "concurrency_mode": "coalesce"},
                {"task_id": "space.cycle_a"},
                {"task_id": "space.cycle_b"},
                {"task_id": "space.ev_cycle_start"},
                {"task_id": "space.ev_cycle_sub1", "exposure": "internal_trigger", "subscriptions": [{"event_id": "space.ev_ping"}]},
                {"task_id": "space.ev_cycle_sub2", "exposure": "internal_trigger", "subscriptions": [{"event_id": "space.ev_pong"}]},
                {"task_id": "space.mix_cycle_emit"},
                {"task_id": "space.mix_cycle_sub", "exposure": "internal_trigger", "subscriptions": [{"event_id": "space.mix_cycle_ev"}]},
            ],
        },
        SPACE_MODULE_SRC,
        helper_who="SPACE_H",
    )
    provision_vsc_and_dev_modules(ws)


def provision_vsc_and_dev_modules(ws: Path) -> None:
    write_module(
        ws,
        "vsc",
        {
            "tier1": False,
            "eager_warmup": True,
            "tasks": [
                {"task_id": "vsc.sync", "resource_key": "vsc", "concurrency_mode": "coalesce", "subscriptions": [{"event_id": "space.reloaded"}]},
                {"task_id": "vsc.on_removing", "exposure": "internal_trigger", "subscriptions": [{"event_id": "space.removing", "payload_filter": {"space": ["vsc", "fail_strict"]}}]},
                {"task_id": "vsc.on_ordered_audit", "exposure": "internal_trigger", "subscriptions": [{"event_id": "space.ordered_audit"}]},
                {"task_id": "vsc.sibling_ok_sub", "exposure": "internal_trigger", "subscriptions": [{"event_id": "kdb.trigger_step5_fail"}]},
                {"task_id": "vsc.gated_clean", "security_tier": "gated", "resource_key": "vsc", "concurrency_mode": "serialize"},
                {"task_id": "vsc.diamond_b", "exposure": "internal_trigger", "subscriptions": [{"event_id": "space.reloaded"}]},
                {"task_id": "vsc.diamond_merge", "exposure": "internal_trigger", "subscriptions": [{"event_id": "vsc.branch_done"}]},
                {"task_id": "vsc.on_tier1_imm", "exposure": "internal_trigger", "subscriptions": [{"event_id": "ast.tier1_imm_probe"}]},
            ],
        },
        VSC_MODULE_SRC,
        helper_who="VSC_H",
    )
    write_module(
        ws,
        "dev",
        {
            "tier1": False,
            "eager_warmup": False,
            "tasks": [
                {"task_id": "dev.run_sandbox", "dispatch_mode": "cold_only"},
                {"task_id": "dev.hold_shared_lock", "resource_key": "cross_proc_key", "concurrency_mode": "serialize"},
            ],
        },
        DEV_MODULE_SRC,
    )


def provision_tier1_modules(ws: Path, *, include_broken_opt: bool = False) -> None:
    if include_broken_opt:
        write_module(
            ws,
            "broken_opt",
            {"tier1": True, "venv_group": "idx_group", "eager_warmup": True, "tasks": [{"task_id": "broken_opt.ping"}]},
            BROKEN_OPT_MODULE_SRC,
        )
    write_module(
        ws,
        "ast",
        {
            "tier1": True,
            "venv_group": "idx_group",
            "eager_warmup": False,
            "tasks": [
                {"task_id": "ast.outline", "cli_path": ["ast", "outline"]},
                {
                    "task_id": "ast.sync",
                    "resource_key": "ast",
                    "concurrency_mode": "coalesce",
                    "subscriptions": [{"event_id": "space.updated", "payload_filter": {"space": ["source", "docs"]}}],
                },
            ],
        },
        AST_MODULE_SRC,
        helper_who="AST_H",
    )
    write_module(
        ws,
        "kdb",
        {
            "tier1": True,
            "venv_group": "idx_group",
            "eager_warmup": True,
            "tasks": [
                {"task_id": "kdb.search"},
                {"task_id": "kdb.index", "resource_key": "kdb", "concurrency_mode": "coalesce"},
                {"task_id": "kdb.bg_preempt_index", "exposure": "internal_trigger", "resource_key": "kdb_bg", "concurrency_mode": "preempt", "subscriptions": [{"event_id": "ast.graph_updated"}]},
                {"task_id": "kdb.fail_sub", "exposure": "internal_trigger", "resource_key": "kdb_fail_sub_res", "concurrency_mode": "coalesce", "subscriptions": [{"event_id": "kdb.trigger_step5_fail"}]},
            ],
        },
        KDB_MODULE_SRC,
    )
    write_module(
        ws,
        "gdrive",
        {
            "tier1": True,
            "eager_warmup": False,
            "tasks": [
                {"task_id": "gdrive.auth", "dispatch_mode": "cold_only", "interactive_tty": True, "security_tier": "conditional"},
                {
                    "task_id": "gdrive.periodic_sync",
                    "exposure": "internal_trigger",
                    "resource_key": "gdrive_sync",
                    "concurrency_mode": "serialize",
                    "periodic": {"default_interval_sec": 0.10, "enabled_config_key": "auto_sync", "interval_config_key": "interval_sec"},
                },
                {"task_id": "gdrive.put", "security_tier": "conditional", "resource_key": "gdrive_sync", "concurrency_mode": "serialize", "timeout_ms": 1000},
            ],
        },
        GDRIVE_MODULE_SRC,
    )


def provision_live_workspace(ws: Path, *, include_broken_opt: bool = False) -> None:
    (ws / "config").mkdir(parents=True, exist_ok=True)
    (ws / ".config.local").mkdir(parents=True, exist_ok=True)
    (ws / "spaces" / "source").mkdir(parents=True, exist_ok=True)
    (ws / "spaces" / "docs").mkdir(parents=True, exist_ok=True)
    (ws / "spaces" / "ignored_logs").mkdir(parents=True, exist_ok=True)
    (ws / "sub_dir").mkdir(parents=True, exist_ok=True)
    (ws / "sub_dir" / "sample.py").write_text("def hello() -> int:\n    return 42\n", encoding="utf-8")
    atomic_write_json(HostPath(ws / "yscb.config.json"), {"workspace_version": 2})
    atomic_write_json(HostPath(ws / "config" / "gdrive.json"), {"auto_sync": False, "interval_sec": 0.10, "work_ms": 0})
    provision_core_tier0_modules(ws)
    provision_tier1_modules(ws, include_broken_opt=include_broken_opt)


__all__ = (
    "AST_MODULE_SRC",
    "AST_OUTLINE_META",
    "BROKEN_OPT_MODULE_SRC",
    "COORD_PROBE_MOD_SRC",
    "CoordProbeOut",
    "DEV_MODULE_SRC",
    "ECHO_TIER0_META",
    "EMBEDDED_MODULE_TEMPLATES",
    "EchoInDto",
    "GDRIVE_MODULE_SRC",
    "GdriveOutDto",
    "IndexOutDto",
    "KDB_MODULE_SRC",
    "KDB_SEARCH_META",
    "OutlineInDto",
    "OutlineOutDto",
    "PRIVATE_FATAL_MOD_SRC",
    "SPACE_MODULE_SRC",
    "SandboxOutDto",
    "SearchInDto",
    "SearchOutDto",
    "SimpleOutDto",
    "SingleProbeProvider",
    "VSC_MODULE_SRC",
    "XGRP_INNER_SRC",
    "XGRP_OUTER_SRC",
    "assert_raises_val_error",
    "assert_zero_live_stage_orphans",
    "check",
    "drain_teardown_until",
    "expect_yscb_code",
    "force_reap_tmp_root_orphans",
    "jfloat",
    "jint",
    "jlist",
    "log",
    "provision_core_tier0_modules",
    "provision_live_workspace",
    "provision_tier1_modules",
    "provision_vsc_and_dev_modules",
    "reap_popen_quietly",
    "run_cli_subproc",
    "scoped_timer",
    "stop_daemon_cleanly",
    "wait_coalesce_count",
    "wait_file_marker",
    "wait_for_daemon_online",
    "wait_until",
    "write_module",
)
