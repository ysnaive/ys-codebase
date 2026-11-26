"""Domain tests for core.execution.runtime and core.execution.daemon."""

from __future__ import annotations

from dataclasses import dataclass, fields
import os
from pathlib import Path
import sys
import threading
import time
import tracemalloc
from typing import Callable, Optional, Sequence

from core.execution.daemon import (
    DaemonQuiesceControl,
    DaemonReloadControl,
    DaemonResumeControl,
    DaemonRunState,
    DaemonStatusSnapshot,
    DaemonStopControl,
    DaemonWatcherConfig,
    IdleTtlMonitor,
    PeriodicTriggerLoop,
    WorkspaceDaemon,
    query_daemon_control,
)
from core.execution.event import EventMetadata, EventSubscriptionSpec
from core.execution.lifecycle import ContainerState
from core.execution.rpc import (
    DaemonConnectionConfig,
    FrameKind,
    read_active_handoff_boot_id,
    wait_for_handoff_daemon_endpoint,
)
from core.execution.runtime import (
    BoundTask,
    CallPropagationContext,
    CallerSurface,
    ClientRoutingPolicy,
    ConcurrencyMode,
    CoordinatedExecution,
    DaemonRpcInvokeReply,
    DispatchMode,
    DispatcherHostOptions,
    EnvLeaseAcquireFn,
    EnvTouchUsedFn,
    ExecutionPriority,
    FlightCallerRegistration,
    InvokeRequest,
    LifecycleReloadGate,
    MODULE_INSTALLED_EVENT_ID,
    MODULE_REMOVING_EVENT_ID,
    ModuleDescriptor,
    PeriodicScheduleSpec,
    PriorityHandle,
    ProcessResult,
    ProtectedModuleLoader,
    ResourceAcquireSpec,
    ResourceCoordinator,
    RuntimeDispatcher,
    StepFlight,
    Task,
    TaskContext,
    TaskMetadata,
    TaskOutcome,
    WORKSPACE_RELOADED_EVENT_ID,
    WorkerStepReply,
    YscbModule,
    build_workspace_module_services_factory,
)
from core.filesystem.fs import (
    CrossProcessLockPaths,
    PollingDirectoryWatcher,
    atomic_write_json,
    read_json_dict,
    resolve_contained_subpath,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    ErrorCode,
    ErrorDetail,
    EventId,
    FlightLogConfig,
    FlightLogRouter,
    HostPath,
    JsonObject,
    LogLevel,
    ModuleId,
    ProfilerNodeSnapshot,
    ProfilerRingBuffer,
    ProfilerSession,
    TaskCancelledException,
    TaskId,
    YscbError,
    is_process_alive,
    strict_parse_json_object,
)
from core.filesystem.vfs import MemoryVfsProvider, MountRule, UriMountTable, VfsHub, build_standard_mount_rules
from tests._boot import (
    FileConfigView,
    ManifestModuleProvider,
    build_dispatcher_for_workspace,
    resolve_dedicated_venv_py,
)
from tests._harness import (
    AST_OUTLINE_META,
    ECHO_TIER0_META,
    EchoInDto,
    KDB_SEARCH_META,
    OutlineInDto,
    OutlineOutDto,
    SearchInDto,
    SimpleOutDto,
    assert_raises_val_error,
    assert_zero_live_stage_orphans,
    check,
    expect_yscb_code,
    force_reap_tmp_root_orphans,
    jint,
    log,
    provision_live_workspace,
    stop_daemon_cleanly,
    wait_coalesce_count,
    wait_for_daemon_online,
    wait_until,
    write_module,
)


class _ToxicStrRuntimeError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("toxic __str__ in runtime test")


@dataclass(frozen=True, slots=True)
class _InMemReqDto:
    key: str


@dataclass(frozen=True, slots=True)
class _InMemRespDto:
    echo: str


class _InMemProbeTask(Task[_InMemReqDto, _InMemRespDto]):
    def __init__(self, mod_name: str, out_log: list[str]) -> None:
        self._meta = TaskMetadata(
            task_id=TaskId(f"{mod_name}.ping"),
            input_type=_InMemReqDto,
            output_type=_InMemRespDto,
            dispatch_mode=DispatchMode.HYBRID,
        )
        self._out_log = out_log

    @property
    def metadata(self) -> TaskMetadata[_InMemReqDto, _InMemRespDto]:
        return self._meta

    def run(self, req: _InMemReqDto, _ctx: TaskContext) -> _InMemRespDto:
        self._out_log.append(req.key)
        return _InMemRespDto(echo=f"mem:{req.key}")


class _InMemProbeModule(YscbModule):
    def __init__(self, mod_name: str, out_log: list[str], *, toxic_close: bool = False) -> None:
        self._mod_id = ModuleId(mod_name)
        self._tasks = (_InMemProbeTask(mod_name, out_log),)
        self._toxic_close = toxic_close

    @property
    def module_id(self) -> ModuleId:
        return self._mod_id

    def tasks(self) -> Sequence[BoundTask]:
        return self._tasks

    def on_init(self, _workspace_root: HostPath) -> Optional[Callable[[], None]]:
        if not self._toxic_close:
            return None

        def _fail_close() -> None:
            raise _ToxicStrRuntimeError("teardown fail")

        return _fail_close
@dataclass(frozen=True, slots=True)
class _CoordReqDto:
    eq_key: str
    mode_tag: str = "normal"
    emit_bad_event: bool = False


@dataclass(frozen=True, slots=True)
class _CoordOutDto:
    seen_priority: str
    run_seq: int


@dataclass(frozen=True, slots=True)
class _EvFailDto:
    msg: str


class _CoalesceControl:
    def __init__(self) -> None:
        self.runs = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.saw_cancelled = False


def _build_coord_test_module(ctrl: _CoalesceControl) -> YscbModule:
    ev_fail = EventMetadata(EventId("cmod.fail_ev"), _EvFailDto)

    class _SerialSameKeyTask(Task[_CoordReqDto, _CoordOutDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("cmod.serial_same_key"),
                input_type=_CoordReqDto,
                output_type=_CoordOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                resource_key="shared.slot",
                concurrency_mode=ConcurrencyMode.SERIALIZE,
            )

        @property
        def metadata(self) -> TaskMetadata[_CoordReqDto, _CoordOutDto]:
            return self._meta

        def run(self, _req: _CoordReqDto, ctx: TaskContext) -> _CoordOutDto:
            ctrl.runs += 1
            return _CoordOutDto(seen_priority=ctx.effective_priority.value, run_seq=ctrl.runs)

    class _CoalTask(Task[_CoordReqDto, _CoordOutDto]):
        def __init__(self, serial_meta: TaskMetadata[_CoordReqDto, _CoordOutDto]) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("cmod.coal"),
                input_type=_CoordReqDto,
                output_type=_CoordOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                resource_key="shared.slot",
                concurrency_mode=ConcurrencyMode.COALESCE,
                equivalence_fn=lambda r: r.eq_key,
            )
            self._serial_meta = serial_meta

        @property
        def metadata(self) -> TaskMetadata[_CoordReqDto, _CoordOutDto]:
            return self._meta

        def run(self, req: _CoordReqDto, ctx: TaskContext) -> _CoordOutDto:
            ctrl.runs += 1
            seq = ctrl.runs
            if req.mode_tag in ("wait", "wait_cycle"):
                ctrl.entered.set()
                ctrl.release.wait(timeout=3.0)
            if req.mode_tag == "reenter_illegal":
                nested_out = ctx.call(
                    self._serial_meta.task_id,
                    _CoordReqDto(eq_key="inner"),
                    output_type=self._serial_meta.output_type,
                )
                if not nested_out.ok and nested_out.error is not None:
                    nested_out.error.raise_as_exception()
            if req.emit_bad_event:
                msg_val = "cycle" if req.mode_tag == "wait_cycle" else "bad_sub"
                ctx.emit(ev_fail, _EvFailDto(msg=msg_val))
            if ctx.cancel_token.is_cancelled:
                ctrl.saw_cancelled = True
                ctx.cancel_token.raise_if_cancelled()
            return _CoordOutDto(seen_priority=ctx.effective_priority.value, run_seq=seq)

    class _CoalFailSubTask(Task[_EvFailDto, _CoordOutDto]):
        def __init__(self) -> None:
            sub = EventSubscriptionSpec(ev_fail, lambda items: items[0] if items else None)
            self._meta = TaskMetadata(
                task_id=TaskId("cmod.sub_fail"),
                input_type=_EvFailDto,
                output_type=_CoordOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                subscriptions=(sub,),
            )

        @property
        def metadata(self) -> TaskMetadata[_EvFailDto, _CoordOutDto]:
            return self._meta

        def run(self, _item: _EvFailDto, ctx: TaskContext) -> _CoordOutDto:
            if _item.msg == "cycle":
                ctx.emit(ev_fail, _EvFailDto(msg="cycle_derived"))
                return _CoordOutDto(seen_priority=ctx.effective_priority.value, run_seq=0)
            raise _ToxicStrRuntimeError("step5 derived failure")

    class _PreemptTask(Task[_CoordReqDto, _CoordOutDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("cmod.preempt"),
                input_type=_CoordReqDto,
                output_type=_CoordOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                resource_key="preempt.slot",
                concurrency_mode=ConcurrencyMode.PREEMPT,
            )

        @property
        def metadata(self) -> TaskMetadata[_CoordReqDto, _CoordOutDto]:
            return self._meta

        def run(self, req: _CoordReqDto, ctx: TaskContext) -> _CoordOutDto:
            if req.mode_tag == "wait":
                ctrl.entered.set()
                if ctx.cancel_token.wait(timeout_sec=3.0):
                    ctrl.saw_cancelled = True
                    ctx.cancel_token.raise_if_cancelled()
            return _CoordOutDto(seen_priority=ctx.effective_priority.value, run_seq=0)

    class _CoalModule(YscbModule):
        def __init__(self) -> None:
            serial_t = _SerialSameKeyTask()
            self._tasks = (_CoalTask(serial_t.metadata), serial_t, _CoalFailSubTask(), _PreemptTask())

        @property
        def module_id(self) -> ModuleId:
            return ModuleId("cmod")

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    return _CoalModule()


class _EmptyModuleProvider:
    def list_modules(self) -> Sequence[ModuleDescriptor]:
        return ()

    def get_module(self, _module_id: ModuleId) -> Optional[ModuleDescriptor]:
        return None

    def reload(self) -> None:
        return None


def _verify_coalesce_and_reentrancy(tmp_root: Path) -> None:
    ws_hp = HostPath(tmp_root / "ws_coord")
    ws_hp.path.mkdir(parents=True, exist_ok=True)
    ctrl = _CoalesceControl()
    coal_mod = _build_coord_test_module(ctrl)
    assert_raises_val_error(
        lambda: DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(coal_mod, coal_mod),
        )
    )
    disp = RuntimeDispatcher(
        workspace_root=ws_hp,
        cache_dir=ws_hp.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(coal_mod,),
        ),
    )
    try:
        disp.container_lifecycle.transition_boot_phase(ContainerState.READY)
        res_pair: list[TaskOutcome[object]] = []
        res_diff: list[TaskOutcome[object]] = []

        def _invoke_coal(
            eq_key: str,
            mode_tag: str,
            prio: ExecutionPriority,
            sink: list[TaskOutcome[object]],
            tok: Optional[CancellationToken] = None,
            emit_bad: bool = False,
            prop: Optional[CallPropagationContext] = None,
        ) -> None:
            req = InvokeRequest(
                task_id=TaskId("cmod.coal"),
                raw_input={"eq_key": eq_key, "mode_tag": mode_tag, "emit_bad_event": emit_bad},
                workspace_root=ws_hp,
                caller_cwd=ws_hp,
                routing_policy=ClientRoutingPolicy.AUTO_SPAWN,
                priority=prio,
                propagation=prop if prop is not None else CallPropagationContext(),
            )
            sink.append(disp.invoke(req, cancel_token=tok))

        t_lead = threading.Thread(
            target=_invoke_coal, args=("k_alpha", "wait", ExecutionPriority.BACKGROUND, res_pair)
        )
        t_lead.start()
        check(ctrl.entered.wait(timeout=2.0), "Leader did not enter COALESCE")
        t_follow = threading.Thread(
            target=_invoke_coal, args=("k_alpha", "normal", ExecutionPriority.FOREGROUND, res_pair)
        )
        t_diff = threading.Thread(
            target=_invoke_coal, args=("k_beta", "normal", ExecutionPriority.BACKGROUND, res_diff)
        )
        t_follow.start()
        t_diff.start()
        wait_coalesce_count(disp, "shared.slot", 2, timeout_sec=2.0)
        ctrl.release.set()
        t_lead.join(timeout=3.0)
        t_follow.join(timeout=3.0)
        t_diff.join(timeout=3.0)
        check(len(res_pair) == 2 and all(o.ok for o in res_pair), f"COALESCE pair failed: {res_pair}")
        check(any(o.coalesced for o in res_pair) and any(not o.coalesced for o in res_pair), "Expected 1 leader + 1 follower")
        check(
            all(isinstance(o.value, dict) and o.value.get("seen_priority") == "foreground" for o in res_pair),
            f"PriorityHandle elevation missing: {res_pair}",
        )
        check(len(res_diff) == 1 and res_diff[0].ok and not res_diff[0].coalesced, "Different eq_key must not coalesce")
        check(ctrl.runs == 2, f"Expected 2 runs (1 alpha + 1 beta), got {ctrl.runs}")

        ctrl.entered.clear()
        ctrl.release.clear()
        ctrl.saw_cancelled = False
        surv_out: list[TaskOutcome[object]] = []
        lead_tok = CancellationToken()
        wait_tok = CancellationToken()
        t_s1 = threading.Thread(
            target=_invoke_coal, args=("k_surv", "wait", ExecutionPriority.BACKGROUND, surv_out, lead_tok)
        )
        t_s1.start()
        check(ctrl.entered.wait(timeout=2.0), "Leader survival step did not start")
        t_s2 = threading.Thread(
            target=_invoke_coal, args=("k_surv", "normal", ExecutionPriority.BACKGROUND, surv_out, wait_tok)
        )
        t_s2.start()
        wait_coalesce_count(disp, "shared.slot", 2, timeout_sec=2.0)
        lead_tok.cancel(reason="leader_aborted")
        ctrl.release.set()
        t_s1.join(timeout=3.0)
        t_s2.join(timeout=3.0)
        check(not ctrl.saw_cancelled, "Leader cancel must NOT abort active waiter")
        ok_surv = [o for o in surv_out if o.ok]
        err_surv = [o for o in surv_out if not o.ok]
        check(
            len(ok_surv) == 1 and ok_surv[0].coalesced and len(err_surv) == 1 and err_surv[0].error is not None
            and err_surv[0].error.code == ErrorCode.TASK_CANCELLED,
            f"Leader cancel survival mismatch: {surv_out}",
        )
    finally:
        disp.shutdown(grace_ms=200)


def _verify_coord_edge_cases(tmp_root: Path) -> None:
    ws_hp = HostPath(tmp_root / "ws_coord_edges")
    ws_hp.path.mkdir(parents=True, exist_ok=True)
    ctrl = _CoalesceControl()
    coal_mod = _build_coord_test_module(ctrl)
    disp = RuntimeDispatcher(
        workspace_root=ws_hp,
        cache_dir=ws_hp.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(coal_mod,),
        ),
    )
    try:
        disp.container_lifecycle.transition_boot_phase(ContainerState.READY)

        def _invoke(
            task_name: str,
            eq_key: str,
            mode_tag: str = "normal",
            prio: ExecutionPriority = ExecutionPriority.FOREGROUND,
            tok: Optional[CancellationToken] = None,
            emit_bad: bool = False,
            prop: Optional[CallPropagationContext] = None,
        ) -> TaskOutcome[object]:
            req = InvokeRequest(
                task_id=TaskId(task_name),
                raw_input={"eq_key": eq_key, "mode_tag": mode_tag, "emit_bad_event": emit_bad},
                workspace_root=ws_hp,
                caller_cwd=ws_hp,
                routing_policy=ClientRoutingPolicy.AUTO_SPAWN,
                priority=prio,
                propagation=prop if prop is not None else CallPropagationContext(),
            )
            return disp.invoke(req, cancel_token=tok)

        all_abort_res: list[TaskOutcome[object]] = []
        tok_a = CancellationToken()
        tok_b = CancellationToken()
        t_a = threading.Thread(
            target=lambda: all_abort_res.append(_invoke("cmod.coal", "k_abort", "wait", ExecutionPriority.BACKGROUND, tok_a))
        )
        t_a.start()
        check(ctrl.entered.wait(timeout=2.0), "All-waiter abort step did not start")
        t_b = threading.Thread(
            target=lambda: all_abort_res.append(_invoke("cmod.coal", "k_abort", "normal", ExecutionPriority.FOREGROUND, tok_b))
        )
        t_b.start()
        wait_coalesce_count(disp, "shared.slot", 2, timeout_sec=2.0)
        tok_a.cancel(reason="abort_a")
        tok_b.cancel(reason="abort_b")
        ctrl.release.set()
        t_a.join(timeout=3.0)
        t_b.join(timeout=3.0)
        check(ctrl.saw_cancelled, "All-waiter cancel must cancel host step token")
        check(
            len(all_abort_res) == 2 and all((not o.ok) and o.error is not None and o.error.code == ErrorCode.TASK_CANCELLED for o in all_abort_res),
            f"All-waiter cancel results mismatch: {all_abort_res}",
        )

        ctrl.entered.clear()
        ctrl.release.clear()
        ctrl.saw_cancelled = False
        diag_res: list[TaskOutcome[object]] = []
        t_d1 = threading.Thread(
            target=lambda: diag_res.append(_invoke("cmod.coal", "k_diag", "wait", ExecutionPriority.BACKGROUND, emit_bad=True))
        )
        t_d1.start()
        check(ctrl.entered.wait(timeout=2.0), "Diag coalesce step did not start")
        t_d2 = threading.Thread(
            target=lambda: diag_res.append(_invoke("cmod.coal", "k_diag", "normal", ExecutionPriority.FOREGROUND, emit_bad=True))
        )
        t_d2.start()
        wait_coalesce_count(disp, "shared.slot", 2, timeout_sec=2.0)
        ctrl.release.set()
        t_d1.join(timeout=3.0)
        t_d2.join(timeout=3.0)
        check(
            len(diag_res) == 2 and all(any("<unprintable exception>" in d.message for d in o.event_diagnostics) for o in diag_res),
            f"Step 5 event diagnostics failed to propagate to all coalesce callers: {diag_res}",
        )

        before_runs = ctrl.runs
        for prop_flag in (
            CallPropagationContext(turn_id="tn", call_tree_id="tn", is_nested_call=True),
            CallPropagationContext(turn_id="te", call_tree_id="te", in_event_chain=True),
        ):
            ctrl.entered.clear()
            ctrl.release.clear()
            deg_res: list[TaskOutcome[object]] = []
            t_deg1 = threading.Thread(
                target=lambda p=prop_flag: deg_res.append(_invoke("cmod.coal", "k_deg", "wait", ExecutionPriority.BACKGROUND, prop=p))
            )
            t_deg1.start()
            check(ctrl.entered.wait(timeout=2.0), "Degraded SERIALIZE step did not enter")
            t_deg2 = threading.Thread(
                target=lambda p=prop_flag: deg_res.append(_invoke("cmod.coal", "k_deg", "normal", ExecutionPriority.FOREGROUND, prop=p))
            )
            t_deg2.start()
            time.sleep(0.08)
            ctrl.release.set()
            t_deg1.join(timeout=3.0)
            t_deg2.join(timeout=3.0)
            check(len(deg_res) == 2 and all(o.ok and not o.coalesced for o in deg_res), f"Degraded call coalesced: {deg_res}")
        check(ctrl.runs == before_runs + 4, f"Expected 4 sequential runs after degradation, got {ctrl.runs - before_runs}")

        ill_out = _invoke("cmod.coal", "k_ill", "reenter_illegal")
        check(
            (not ill_out.ok) and ill_out.error is not None and ill_out.error.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY,
            f"Expected ILLEGAL_LOCK_REENTRANCY, got {ill_out}",
        )

        ctrl.entered.clear()
        ctrl.saw_cancelled = False
        bg_out: list[TaskOutcome[object]] = []
        t_bg = threading.Thread(
            target=lambda: bg_out.append(_invoke("cmod.preempt", "p1", "wait", ExecutionPriority.BACKGROUND))
        )
        t_bg.start()
        check(ctrl.entered.wait(timeout=2.0), "PREEMPT background task did not enter")
        fg_out = _invoke("cmod.preempt", "p2", "normal", ExecutionPriority.FOREGROUND)
        t_bg.join(timeout=3.0)
        check(fg_out.ok and ctrl.saw_cancelled, "PREEMPT foreground did not cancel background waiter")
        check(
            len(bg_out) == 1 and (not bg_out[0].ok) and bg_out[0].error is not None
            and bg_out[0].error.code == ErrorCode.TASK_PREEMPTED,
            f"Background preempt outcome mismatch: {bg_out}",
        )
        post_out = _invoke("cmod.preempt", "p3", "normal", ExecutionPriority.BACKGROUND)
        check(post_out.ok, f"Lingering lock blocked post-preempt call: {post_out}")
    finally:
        disp.shutdown(grace_ms=200)


def _verify_step5_cycle_and_cross_proc_reentrancy(tmp_root: Path, venv_py: Path) -> None:
    ws_cyc = HostPath(tmp_root / "ws_step5_cycle")
    ws_cyc.path.mkdir(parents=True, exist_ok=True)
    ctrl_c = _CoalesceControl()
    disp_c = RuntimeDispatcher(
        workspace_root=ws_cyc,
        cache_dir=ws_cyc.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(_build_coord_test_module(ctrl_c),),
        ),
    )
    try:
        disp_c.container_lifecycle.transition_boot_phase(ContainerState.READY)
        cyc_res: list[TaskOutcome[object]] = []

        def _run_cyc(prio: ExecutionPriority, mode_tag: str) -> None:
            req = InvokeRequest(
                task_id=TaskId("cmod.coal"),
                raw_input={"eq_key": "k_cyc", "mode_tag": mode_tag, "emit_bad_event": True},
                workspace_root=ws_cyc,
                caller_cwd=ws_cyc,
                routing_policy=ClientRoutingPolicy.AUTO_SPAWN,
                priority=prio,
            )
            cyc_res.append(disp_c.invoke(req))

        t_c1 = threading.Thread(target=_run_cyc, args=(ExecutionPriority.BACKGROUND, "wait_cycle"))
        t_c1.start()
        check(ctrl_c.entered.wait(timeout=2.0), "Cycle coalesce step did not start")
        t_c2 = threading.Thread(target=_run_cyc, args=(ExecutionPriority.FOREGROUND, "normal"))
        t_c2.start()
        wait_coalesce_count(disp_c, "shared.slot", 2, timeout_sec=2.0)
        ctrl_c.release.set()
        t_c1.join(timeout=3.0)
        t_c2.join(timeout=3.0)
        check(
            len(cyc_res) == 2
            and all((not o.ok) and o.error is not None and o.error.code == ErrorCode.EVENT_CYCLE_DETECTED for o in cyc_res),
            f"Step 5 derived EventCycleError failed to propagate across coalesce: {cyc_res}",
        )
    finally:
        disp_c.shutdown(grace_ms=200)

    ws_cp = HostPath(tmp_root / "ws_cross_proc")
    provision_live_workspace(ws_cp.path)
    locks_dir = resolve_contained_subpath(ws_cp, "locks")
    cp_paths = CrossProcessLockPaths.for_stem(locks_dir, "res_probe")
    check(str(cp_paths.lock_file.lock_path).endswith(".lock"), "CrossProcessLockPaths missing .lock")
    check(str(cp_paths.owner_path).endswith(".owner.json"), "CrossProcessLockPaths missing .owner.json")
    check(str(cp_paths.pin_path).endswith(".pin"), "CrossProcessLockPaths missing .pin")

    outer_code = (
        "from dataclasses import dataclass\n"
        "import os\n"
        "from typing import Sequence\n"
        "from core.execution.runtime import (\n"
        "    BoundTask, ConcurrencyMode, DispatchMode, SelfMutationScope,\n"
        "    Task, TaskContext, TaskMetadata, YscbModule,\n"
        ")\n"
        "from core.filesystem.fs import atomic_write_json\n"
        "from core.foundation import ModuleId, TaskId\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class OuterReq:\n"
        "    tag: str\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class OuterOut:\n"
        "    outer_pid: int\n"
        "    inner_pid: int\n"
        "    ok_nested: bool\n"
        "    err_code: str = ''\n\n"
        "class ReentOuterTask(Task[OuterReq, OuterOut]):\n"
        "    def __init__(self) -> None:\n"
        "        self._meta = TaskMetadata(\n"
        "            TaskId('xs_outer.run'), OuterReq, OuterOut,\n"
        "            resource_key='xre.shared', concurrency_mode=ConcurrencyMode.SERIALIZE,\n"
        "        )\n"
        "    @property\n"
        "    def metadata(self) -> TaskMetadata[OuterReq, OuterOut]:\n"
        "        return self._meta\n"
        "    def run(self, req: OuterReq, ctx: TaskContext) -> OuterOut:\n"
        "        target = 'xs_inner.coal' if req.tag == 'bad_mode' else 'xs_inner.step'\n"
        "        sub = ctx.call(TaskId(target), {'tag': req.tag})\n"
        "        if sub.ok and isinstance(sub.value, dict):\n"
        "            ipid = int(sub.value.get('inner_pid', 0))\n"
        "            return OuterOut(outer_pid=os.getpid(), inner_pid=ipid, ok_nested=True)\n"
        "        ecode = sub.error.code.value if sub.error is not None else ''\n"
        "        return OuterOut(outer_pid=os.getpid(), inner_pid=0, ok_nested=False, err_code=ecode)\n\n"
        "class ColdMutTask(Task[OuterReq, OuterOut]):\n"
        "    def __init__(self) -> None:\n"
        "        self._meta = TaskMetadata(\n"
        "            TaskId('xs_outer.mut'), OuterReq, OuterOut,\n"
        "            dispatch_mode=DispatchMode.COLD_ONLY,\n"
        "            mutation_scope=SelfMutationScope.MUTATES_MODULES,\n"
        "        )\n"
        "    @property\n"
        "    def metadata(self) -> TaskMetadata[OuterReq, OuterOut]:\n"
        "        return self._meta\n"
        "    def run(self, req: OuterReq, ctx: TaskContext) -> OuterOut:\n"
        "        atomic_write_json(ctx.workspace_root.join('.cache', 'mut_done.json'), {'tag': req.tag})\n"
        "        return OuterOut(outer_pid=os.getpid(), inner_pid=0, ok_nested=True)\n\n"
        "class XsOuterMod(YscbModule):\n"
        "    def __init__(self) -> None:\n"
        "        self._tasks = (ReentOuterTask(), ColdMutTask())\n"
        "    @property\n"
        "    def module_id(self) -> ModuleId:\n"
        "        return ModuleId('xs_outer')\n"
        "    def tasks(self) -> Sequence[BoundTask]:\n"
        "        return self._tasks\n\n"
        "def create_module() -> YscbModule:\n"
        "    return XsOuterMod()\n"
    )
    inner_code = (
        "from dataclasses import dataclass\n"
        "import os\n"
        "from typing import Sequence\n"
        "from core.execution.runtime import (\n"
        "    BoundTask, ConcurrencyMode, Task, TaskContext, TaskMetadata, YscbModule,\n"
        ")\n"
        "from core.foundation import ModuleId, TaskId\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class InnerReq:\n"
        "    tag: str\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class InnerOut:\n"
        "    inner_pid: int\n"
        "    tag: str\n\n"
        "class InnerStepTask(Task[InnerReq, InnerOut]):\n"
        "    def __init__(self) -> None:\n"
        "        self._meta = TaskMetadata(\n"
        "            TaskId('xs_inner.step'), InnerReq, InnerOut,\n"
        "            resource_key='xre.shared', concurrency_mode=ConcurrencyMode.SERIALIZE,\n"
        "        )\n"
        "    @property\n"
        "    def metadata(self) -> TaskMetadata[InnerReq, InnerOut]:\n"
        "        return self._meta\n"
        "    def run(self, req: InnerReq, _ctx: TaskContext) -> InnerOut:\n"
        "        return InnerOut(inner_pid=os.getpid(), tag=req.tag)\n\n"
        "class InnerCoalTask(Task[InnerReq, InnerOut]):\n"
        "    def __init__(self) -> None:\n"
        "        self._meta = TaskMetadata(\n"
        "            TaskId('xs_inner.coal'), InnerReq, InnerOut,\n"
        "            resource_key='xre.shared', concurrency_mode=ConcurrencyMode.COALESCE,\n"
        "        )\n"
        "    @property\n"
        "    def metadata(self) -> TaskMetadata[InnerReq, InnerOut]:\n"
        "        return self._meta\n"
        "    def run(self, req: InnerReq, _ctx: TaskContext) -> InnerOut:\n"
        "        return InnerOut(inner_pid=os.getpid(), tag=req.tag)\n\n"
        "class XsInnerMod(YscbModule):\n"
        "    def __init__(self) -> None:\n"
        "        self._tasks = (InnerStepTask(), InnerCoalTask())\n"
        "    @property\n"
        "    def module_id(self) -> ModuleId:\n"
        "        return ModuleId('xs_inner')\n"
        "    def tasks(self) -> Sequence[BoundTask]:\n"
        "        return self._tasks\n\n"
        "def create_module() -> YscbModule:\n"
        "    return XsInnerMod()\n"
    )
    write_module(
        ws_cp.path,
        "xs_outer",
        {
            "tier1": False,
            "tasks": [
                {"task_id": "xs_outer.run", "resource_key": "xre.shared", "concurrency_mode": "serialize"},
                {
                    "task_id": "xs_outer.mut",
                    "dispatch_mode": "cold_only",
                    "mutation_scope": "mutates_modules",
                },
            ],
        },
        outer_code,
    )
    write_module(
        ws_cp.path,
        "xs_inner",
        {
            "tier1": True,
            "venv_group": "grp_xre",
            "tasks": [
                {"task_id": "xs_inner.step", "resource_key": "xre.shared", "concurrency_mode": "serialize"},
                {"task_id": "xs_inner.coal", "resource_key": "xre.shared", "concurrency_mode": "coalesce"},
            ],
        },
        inner_code,
    )
    rig_cp = build_dispatcher_for_workspace(ws_cp, HostPath(venv_py), is_daemon_host=False, ttl_sec=8.0)
    try:
        warm_cp = rig_cp.dispatcher.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="warm_cp"))
        check(warm_cp.ok, f"Cross-proc daemon boot failed: {warm_cp}")
        wait_for_daemon_online(ws_cp, timeout_sec=10.0)
        req_re = InvokeRequest(
            task_id=TaskId("xs_outer.run"),
            raw_input={"tag": "cross_ok"},
            workspace_root=ws_cp,
            caller_cwd=ws_cp,
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
        )
        out_re = rig_cp.dispatcher.invoke(req_re)
        check(
            out_re.ok and out_re.executed_hot and isinstance(out_re.value, dict) and out_re.value.get("ok_nested") is True,
            f"Cross-proc SERIALIZE reentrancy failed: {out_re}",
        )
        outer_pid = jint(out_re.value, "outer_pid")
        inner_pid = jint(out_re.value, "inner_pid")
        check(outer_pid > 0 and inner_pid > 0 and outer_pid != inner_pid, f"Expected separate OS pids: {out_re}")

        req_bad = InvokeRequest(
            task_id=TaskId("xs_outer.run"),
            raw_input={"tag": "bad_mode"},
            workspace_root=ws_cp,
            caller_cwd=ws_cp,
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
        )
        out_bad = rig_cp.dispatcher.invoke(req_bad)
        check(
            (not out_bad.ok) and out_bad.error is not None
            and out_bad.error.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY,
            f"Expected cross-proc ILLEGAL_LOCK_REENTRANCY on SERIALIZE->COALESCE, got {out_bad}",
        )

        hot_mut = rig_cp.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("xs_outer.mut"),
                raw_input={"tag": "hot_deny"},
                workspace_root=ws_cp,
                caller_cwd=ws_cp,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
            )
        )
        check(
            (not hot_mut.ok) and hot_mut.error is not None and hot_mut.error.code == ErrorCode.COLD_DISPATCH_FORBIDDEN,
            f"COLD_ONLY must reject STRICT_HOT: {hot_mut}",
        )
        cold_mut = rig_cp.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("xs_outer.mut"),
                raw_input={"tag": "cold_ok"},
                workspace_root=ws_cp,
                caller_cwd=ws_cp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            )
        )
        check(cold_mut.ok and read_json_dict(ws_cp.join(".cache", "mut_done.json")) == {"tag": "cold_ok"}, "Cold MUTATES_MODULES failed")
    finally:
        rig_cp.dispatcher.shutdown(grace_ms=300)
        stop_daemon_cleanly(ws_cp)


def _verify_global_quiesce_and_controls(tmp_root: Path, venv_py: Path) -> None:
    ws_gate = HostPath(tmp_root / "ws_gate_unit")
    ws_gate.path.mkdir(parents=True, exist_ok=True)
    gate = LifecycleReloadGate(ws_gate)
    check(gate.try_begin_global_quiesce(leased=True), "Initial global quiesce failed")
    ep_first = gate.quiesce_epoch
    gate.record_quiesce_lease(5.0)
    wake_long = gate.next_quiesce_wakeup()
    gate.record_quiesce_lease(0.05)
    wake_after_short = gate.next_quiesce_wakeup()
    check(
        wake_long is not None and wake_after_short is not None and wake_after_short >= wake_long - 0.5,
        "Short quiesce lease shrank active long lease",
    )
    ep_cur = gate.quiesce_epoch
    check(ep_cur > ep_first, "record_quiesce_lease must advance epoch")
    stale_resume = gate.run_global_resume_guarded(ep_first, lambda: False)
    check(not stale_resume.started, "Stale expected_epoch should not resume")
    ok_resume = gate.run_global_resume_guarded(ep_cur, lambda: False)
    check(ok_resume.started and not ok_resume.need_handoff, "Matching expected_epoch failed to resume")

    gate_exp = LifecycleReloadGate(ws_gate)
    check(gate_exp.try_begin_global_quiesce(leased=True), "Second gate quiesce failed")
    gate_exp.record_quiesce_lease(0.04)
    wait_until(lambda: gate_exp.due_quiesce_epoch() == gate_exp.quiesce_epoch, timeout_sec=1.5)

    ws_q = HostPath(tmp_root / "ws_live_quiesce")
    provision_live_workspace(ws_q.path)
    rig_q = build_dispatcher_for_workspace(ws_q, HostPath(venv_py), is_daemon_host=False, ttl_sec=10.0)
    cdir_q = ws_q.join(".cache")
    try:
        boot_out = rig_q.dispatcher.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot_quiesce"))
        check(boot_out.ok, f"Warm boot call failed: {boot_out}")
        wait_for_daemon_online(ws_q, timeout_sec=10.0)

        ctrl_req_ack = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_REQUEST, {"action": "ping"})
        check(
            ctrl_req_ack is not None and ctrl_req_ack.get("error") == ErrorCode.CODEC_VALIDATION_FAILED.value,
            f"CONTROL_REQUEST must reject codec_validation_failed: {ctrl_req_ack}",
        )
        legacy_q = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_QUIESCE, {"modules": ["space"], "lease_sec": 3.0})
        check(
            legacy_q is not None and legacy_q.get("error") == ErrorCode.CODEC_VALIDATION_FAILED.value,
            f"CONTROL_QUIESCE must reject legacy modules field: {legacy_q}",
        )
        legacy_res = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_RESUME, {"modules": ["space"]})
        check(
            legacy_res is not None and legacy_res.get("error") == ErrorCode.CODEC_VALIDATION_FAILED.value,
            f"CONTROL_RESUME must reject legacy modules field: {legacy_res}",
        )

        q_short = query_daemon_control(
            cdir_q, ws_q, FrameKind.CONTROL_QUIESCE, {"lease_sec": 0.2, "drain_timeout_sec": 2.0}
        )
        check(q_short is not None and q_short.get("ok") and q_short.get("state") == "quiesced", f"Short quiesce failed: {q_short}")
        wait_until(
            lambda: (
                (st := query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_STATUS)) is not None
                and isinstance(st.get("status"), dict)
                and st["status"].get("state") == "ready"
            ),
            timeout_sec=3.0,
        )

        q_hold = query_daemon_control(
            cdir_q, ws_q, FrameKind.CONTROL_QUIESCE, {"lease_sec": 8.0, "drain_timeout_sec": 2.0}
        )
        check(q_hold is not None and q_hold.get("ok"), f"Hold quiesce failed: {q_hold}")
        ep_hold = jint(q_hold, "epoch")
        rel_def = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_RELOAD, {})
        check(
            rel_def is not None and rel_def.get("ok") is True and rel_def.get("reloaded") is False and rel_def.get("deferred") is True,
            f"CONTROL_RELOAD while QUIESCED must defer: {rel_def}",
        )

        queued_res: list[TaskOutcome[SimpleOutDto]] = []
        queued_hot: list[TaskOutcome[OutlineOutDto]] = []
        t_hyb = threading.Thread(
            target=lambda: queued_res.append(
                rig_q.dispatcher.invoke_typed(
                    ECHO_TIER0_META, EchoInDto(tag="queued_hyb"), routing_policy=ClientRoutingPolicy.AUTO_SPAWN
                )
            )
        )
        t_strict = threading.Thread(
            target=lambda: queued_hot.append(
                rig_q.dispatcher.invoke_typed(
                    AST_OUTLINE_META, OutlineInDto(rel_file="sub_dir/sample.py"), routing_policy=ClientRoutingPolicy.STRICT_HOT
                )
            )
        )
        t_hyb.start()
        t_strict.start()
        time.sleep(0.15)
        check((not queued_res) and (not queued_hot), "HYBRID/STRICT_HOT requests executed while QUIESCED")

        wrong_res = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_RESUME, {"expected_epoch": ep_hold + 77})
        check(
            wrong_res is not None and wrong_res.get("state") == "quiesced",
            f"Wrong expected_epoch unlocked quiesce: {wrong_res}",
        )
        time.sleep(0.1)
        check((not queued_res) and (not queued_hot), "Queued calls ran after wrong expected_epoch resume")

        right_res = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_RESUME, {"expected_epoch": ep_hold})
        check(
            right_res is not None and right_res.get("ok") and right_res.get("state") == "ready",
            f"Matching expected_epoch resume failed: {right_res}",
        )
        t_hyb.join(timeout=6.0)
        t_strict.join(timeout=6.0)
        check(
            len(queued_res) == 1 and queued_res[0].ok and queued_res[0].executed_hot,
            f"Queued HYBRID call failed after resume: {queued_res}",
        )
        check(
            len(queued_hot) == 1 and queued_hot[0].ok and queued_hot[0].executed_hot,
            f"Queued STRICT_HOT call failed after resume: {queued_hot}",
        )
        rel_now = query_daemon_control(cdir_q, ws_q, FrameKind.CONTROL_RELOAD, {})
        check(
            rel_now is not None and rel_now.get("ok") and rel_now.get("reloaded") is True,
            f"Immediate CONTROL_RELOAD failed: {rel_now}",
        )
    finally:
        rig_q.dispatcher.shutdown(grace_ms=300)
        stop_daemon_cleanly(ws_q)


def _verify_core_diff_handoff_and_diagnostics(tmp_root: Path, venv_py: Path) -> None:
    expected_prop_fields = (
        "turn_id",
        "call_tree_id",
        "call_stack",
        "lineage",
        "is_internal_trigger",
        "is_nested_call",
        "in_event_chain",
        "from_hot_container",
        "hot_workspaces",
        "cold_shared_workspaces",
        "profile_mem",
    )
    actual_prop_fields = tuple(f.name for f in fields(CallPropagationContext))
    check(
        actual_prop_fields == expected_prop_fields and len(actual_prop_fields) == 11,
        f"CallPropagationContext 11-field contract mismatch: {actual_prop_fields}",
    )
    check(WORKSPACE_RELOADED_EVENT_ID == EventId("core.workspace_reloaded"), "Bad WORKSPACE_RELOADED_EVENT_ID")
    check(MODULE_INSTALLED_EVENT_ID == EventId("core.module_installed"), "Bad MODULE_INSTALLED_EVENT_ID")
    check(MODULE_REMOVING_EVENT_ID == EventId("core.module_removing"), "Bad MODULE_REMOVING_EVENT_ID")

    ws_inmem = HostPath(tmp_root / "ws_inmem_tox")
    ws_inmem.path.mkdir(parents=True, exist_ok=True)
    mem_log: list[str] = []
    mem_mod = _InMemProbeModule("inmem_tox", mem_log, toxic_close=True)
    disp_mem = RuntimeDispatcher(
        workspace_root=ws_inmem,
        cache_dir=ws_inmem.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(mem_mod,),
        ),
    )
    disp_mem.container_lifecycle.transition_boot_phase(ContainerState.READY)
    mem_res = disp_mem.invoke(
        InvokeRequest(
            task_id=TaskId("inmem_tox.ping"),
            raw_input={"key": "hi"},
            workspace_root=ws_inmem,
            caller_cwd=ws_inmem,
            routing_policy=ClientRoutingPolicy.AUTO_SPAWN,
        )
    )
    check(mem_res.ok and mem_res.value == {"echo": "mem:hi"} and mem_log == ["hi"], f"In-memory task failed: {mem_res}")
    sd_diags = disp_mem.shutdown(grace_ms=200)
    check(
        any(d.code == ErrorCode.TEARDOWN_ERROR and "<unprintable exception>" in d.message for d in sd_diags),
        f"Toxic teardown closer not isolated in TEARDOWN_ERROR: {sd_diags}",
    )

    ws_deg = HostPath(tmp_root / "ws_mod_degraded")
    provision_live_workspace(ws_deg.path)
    bad_start_src = (
        "from dataclasses import dataclass\n"
        "from typing import Callable, Optional, Sequence\n"
        "from core.execution.runtime import BoundTask, Task, TaskContext, TaskMetadata, YscbModule\n"
        "from core.foundation import HostPath, ModuleId, TaskId\n\n"
        "class ToxicStartErr(RuntimeError):\n"
        "    def __str__(self) -> str:\n"
        "        raise RuntimeError('toxic str in start')\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class DegIn:\n"
        "    tag: str\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class DegOut:\n"
        "    ok: bool\n\n"
        "class DegTask(Task[DegIn, DegOut]):\n"
        "    def __init__(self) -> None:\n"
        "        self._meta = TaskMetadata(TaskId('deg_mod.ping'), DegIn, DegOut)\n"
        "    @property\n"
        "    def metadata(self) -> TaskMetadata[DegIn, DegOut]:\n"
        "        return self._meta\n"
        "    def run(self, _req: DegIn, _ctx: TaskContext) -> DegOut:\n"
        "        return DegOut(ok=True)\n\n"
        "class DegMod(YscbModule):\n"
        "    @property\n"
        "    def module_id(self) -> ModuleId:\n"
        "        return ModuleId('deg_mod')\n"
        "    def on_init(self, _ws: HostPath) -> Optional[Callable[[], None]]:\n"
        "        raise ToxicStartErr('init boom')\n"
        "    def tasks(self) -> Sequence[BoundTask]:\n"
        "        return (DegTask(),)\n\n"
        "def create_module() -> YscbModule:\n"
        "    return DegMod()\n"
    )
    write_module(ws_deg.path, "deg_mod", {"tier1": False, "tasks": [{"task_id": "deg_mod.ping"}]}, bad_start_src)
    rig_deg = build_dispatcher_for_workspace(ws_deg, HostPath(venv_py), is_daemon_host=True, sandbox_restricted=True)
    try:
        rig_deg.dispatcher.container_lifecycle.transition_boot_phase(ContainerState.READY)
        deg_out = rig_deg.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("deg_mod.ping"),
                raw_input={"tag": "check"},
                workspace_root=ws_deg,
                caller_cwd=ws_deg,
                routing_policy=ClientRoutingPolicy.AUTO_SPAWN,
            )
        )
        check(
            (not deg_out.ok) and deg_out.error is not None and deg_out.error.code == ErrorCode.MODULE_DEGRADED
            and "<unprintable exception>" in deg_out.error.message,
            f"Toxic on_start should isolate as MODULE_DEGRADED: {deg_out}",
        )
    finally:
        rig_deg.dispatcher.shutdown(grace_ms=200)

    ws_core = HostPath(tmp_root / "ws_core_handoff")
    provision_live_workspace(ws_core.path)
    core_extra = ws_core.path / ".modules" / "core" / "core_probe.py"
    core_extra.parent.mkdir(parents=True, exist_ok=True)
    core_extra.write_text("CORE_PROBE_VER = 1\n", encoding="utf-8")
    rig_c = build_dispatcher_for_workspace(ws_core, HostPath(venv_py), is_daemon_host=False, ttl_sec=10.0)
    cdir_c = ws_core.join(".cache")
    try:
        w_out = rig_c.dispatcher.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot_core"))
        check(w_out.ok, f"Core handoff test boot failed: {w_out}")
        ep_first = wait_for_daemon_online(ws_core, timeout_sec=10.0)
        first_boot_id = str(ep_first.get("boot_id", ""))
        check(bool(first_boot_id), f"Missing initial daemon boot_id: {ep_first}")

        st_core = core_extra.stat()
        os.utime(core_extra, ns=(st_core.st_atime_ns, st_core.st_mtime_ns + 50_000_000))
        rep_touch = query_daemon_control(cdir_c, ws_core, FrameKind.CONTROL_RELOAD, {})
        check(
            rep_touch is not None and rep_touch.get("handoff") is not True,
            f"mtime-only touch on .modules/core triggered false core handoff: {rep_touch}",
        )

        core_extra.write_text("CORE_PROBE_VER = 2\n", encoding="utf-8")
        rep_handoff = query_daemon_control(cdir_c, ws_core, FrameKind.CONTROL_RELOAD, {})
        check(rep_handoff is not None and rep_handoff.get("handoff") is True, f"Core content change missed handoff: {rep_handoff}")
        ep_second = wait_for_handoff_daemon_endpoint(
            cdir_c, ws_core, max_wait_sec=10.0, previous_boot_id=first_boot_id
        )
        check(ep_second is not None and ep_second.boot_id != first_boot_id, f"Successor daemon did not replace boot_id: {ep_second}")
    finally:
        rig_c.dispatcher.shutdown(grace_ms=300)
        stop_daemon_cleanly(ws_core)


def _verify_ttl_periodic_and_worker_pool_stop(tmp_root: Path, venv_py: Path) -> None:
    ttl_mon = IdleTtlMonitor(0.15)
    check(ttl_mon.ttl_sec == 0.15, f"Unexpected ttl_sec: {ttl_mon.ttl_sec}")
    rem_first = ttl_mon.remaining_sec()
    check(rem_first is not None and 0.0 < rem_first <= 0.15, f"Unexpected remaining_sec: {rem_first}")
    time.sleep(0.06)
    ttl_mon.record_external_activity()
    rem_reset = ttl_mon.remaining_sec()
    check(rem_reset is not None and rem_reset > 0.08, f"record_external_activity failed: {rem_reset}")
    time.sleep(0.18)
    check(ttl_mon.is_expired(), "IdleTtlMonitor failed to expire")

    ws_per = HostPath(tmp_root / "ws_periodic")
    ws_per.path.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ws_per.join("config", "per_mod.json"), {"enabled": False})
    per_state = {"ticks": 0, "in_flight": 0, "max_conc": 0, "fail_once": False}
    per_lock = threading.Lock()
    two_ticks = threading.Event()

    class _PerTask(Task[_InMemReqDto, _InMemRespDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("per_mod.tick"),
                input_type=_InMemReqDto,
                output_type=_InMemRespDto,
                dispatch_mode=DispatchMode.HYBRID,
                periodic=PeriodicScheduleSpec(0.04, enabled_config_key="enabled"),
            )

        @property
        def metadata(self) -> TaskMetadata[_InMemReqDto, _InMemRespDto]:
            return self._meta

        def run(self, _req: _InMemReqDto, _ctx: TaskContext) -> _InMemRespDto:
            with per_lock:
                per_state["in_flight"] += 1
                if per_state["in_flight"] > per_state["max_conc"]:
                    per_state["max_conc"] = per_state["in_flight"]
                should_fail = per_state["fail_once"]
                if should_fail:
                    per_state["fail_once"] = False
            try:
                time.sleep(0.03)
                if should_fail:
                    raise _ToxicStrRuntimeError("periodic boom")
                with per_lock:
                    per_state["ticks"] += 1
                    if per_state["ticks"] >= 2:
                        two_ticks.set()
            finally:
                with per_lock:
                    per_state["in_flight"] -= 1
            return _InMemRespDto(echo="tick")

    class _PerMod(YscbModule):
        def __init__(self) -> None:
            self._tasks = (_PerTask(),)

        @property
        def module_id(self) -> ModuleId:
            return ModuleId("per_mod")

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    cfg_view = FileConfigView(ws_per)
    disp_per = RuntimeDispatcher(
        workspace_root=ws_per,
        cache_dir=ws_per.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            config_view=cfg_view,
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(_PerMod(),),
        ),
    )
    disp_per.container_lifecycle.transition_boot_phase(ContainerState.READY)
    per_errors: list[ErrorDetail] = []

    def _run_per_tick(tid: TaskId) -> None:
        out = disp_per.invoke(
            InvokeRequest(
                task_id=tid,
                raw_input={"key": "tick"},
                workspace_root=ws_per,
                caller_cwd=ws_per,
                routing_policy=ClientRoutingPolicy.AUTO_SPAWN,
                priority=ExecutionPriority.BACKGROUND,
            )
        )
        if not out.ok and out.error is not None:
            per_errors.append(out.error)

    loop = PeriodicTriggerLoop(
        dispatcher=disp_per,
        config_view=cfg_view,
        can_run_background=lambda: True,
        execute_periodic_task=_run_per_tick,
        on_error=per_errors.append,
    )
    try:
        loop.start()
        time.sleep(0.12)
        check(per_state["ticks"] == 0, f"Disabled periodic task ran unexpectedly: {per_state}")
        with per_lock:
            per_state["fail_once"] = True
        atomic_write_json(ws_per.join("config", "per_mod.json"), {"enabled": True})
        cfg_view.reload()
        loop.refresh_schedules()
        check(two_ticks.wait(timeout=3.0), f"PeriodicTriggerLoop failed to reach 2 ticks: {per_state}")
        check(per_state["max_conc"] == 1, f"Periodic ticks overlapped: {per_state}")
        check(any("<unprintable exception>" in e.message for e in per_errors), f"Toxic periodic error lost: {per_errors}")
    finally:
        loop.stop(drain_timeout_sec=2.0)
        disp_per.shutdown(grace_ms=200)

    ws_pool = HostPath(tmp_root / "ws_worker_pool_stop")
    provision_live_workspace(ws_pool.path)
    rig_pool = build_dispatcher_for_workspace(ws_pool, HostPath(venv_py), is_daemon_host=True, sandbox_restricted=True)
    try:
        rig_pool.dispatcher.container_lifecycle.transition_boot_phase(ContainerState.READY)
        pool_out = rig_pool.dispatcher.invoke_typed(KDB_SEARCH_META, SearchInDto(query="pool_check"))
        check(pool_out.ok and pool_out.value is not None and pool_out.value.worker_pid > 0, f"Tier1 invoke failed: {pool_out}")
        snaps = rig_pool.dispatcher.tier1_pool.active_worker_snapshots()
        check(
            any(s.group == "idx_group" and s.alive and s.pid > 0 for s in snaps),
            f"Expected live idx_group Tier1 worker snapshot: {snaps}",
        )
        stop_diags = rig_pool.dispatcher.tier1_pool.stop_groups_for_modules(
            frozenset({ModuleId("kdb")}),
            rig_pool.dispatcher.module_provider.list_modules(),
            grace_ms=1500,
        )
        check(stop_diags == (), f"Tier1WorkerPool stop returned diagnostics: {stop_diags}")
        wait_until(lambda: not rig_pool.dispatcher.tier1_pool.active_worker_snapshots(), timeout_sec=3.0)
    finally:
        rig_pool.dispatcher.shutdown(grace_ms=200)


def _verify_daemon_shell_and_controls(tmp_root: Path, venv_py: Path) -> None:
    check(DaemonRunState.QUIESCED == ContainerState.QUIESCED, "DaemonRunState must alias ContainerState")
    expect_yscb_code(
        lambda: DataclassCodec.decode_envelope(DaemonQuiesceControl, {"modules": ["ast"]}),
        ErrorCode.CODEC_VALIDATION_FAILED,
    )
    expect_yscb_code(
        lambda: DataclassCodec.decode_envelope(DaemonResumeControl, {"modules": ["ast"]}),
        ErrorCode.CODEC_VALIDATION_FAILED,
    )
    rel_ctrl = DataclassCodec.decode_envelope(DaemonReloadControl, {})
    stop_ctrl = DataclassCodec.decode_envelope(DaemonStopControl, {"force": True, "core_handoff": False})
    check(rel_ctrl.modules == () and stop_ctrl.force and not stop_ctrl.core_handoff, "Daemon control DTO decode failed")

    ws_sh = HostPath(tmp_root / "ws_daemon_shell")
    provision_live_workspace(ws_sh.path)
    rig_sh = build_dispatcher_for_workspace(ws_sh, HostPath(venv_py), is_daemon_host=True, sandbox_restricted=True)
    daemon = WorkspaceDaemon(
        workspace_root=ws_sh,
        cache_dir=ws_sh.join(".cache"),
        dispatcher=rig_sh.dispatcher,
        config_view=rig_sh.config_view,
        watch_config=DaemonWatcherConfig(
            echo_guard=rig_sh.echo_ledger,
            space_watch_roots=(ws_sh.join("spaces"),),
            config_watch_roots=(ws_sh.join("config"),),
            watcher_debounce_sec=0.05,
        ),
    )
    try:
        rig_sh.dispatcher.container_lifecycle.transition_boot_phase(ContainerState.READY)
        snap = daemon.snapshot_status()
        check(isinstance(snap, DaemonStatusSnapshot) and snap.state == DaemonRunState.READY, f"Bad status snapshot: {snap}")
        bg_errs = daemon.drain_background_errors()
        check(isinstance(bg_errs, tuple) and all(isinstance(e, ErrorDetail) for e in bg_errs), "Bad background error tuple")
        ctrl_bad = daemon.on_control(FrameKind.CONTROL_REQUEST, {"action": "status"})
        check(ctrl_bad.get("error") == ErrorCode.CODEC_VALIDATION_FAILED.value, f"Expected codec reject: {ctrl_bad}")

        w_events: list[frozenset[HostPath]] = []
        watcher = PollingDirectoryWatcher((ws_sh.join("spaces"),), w_events.append, debounce_sec=0.04, poll_interval_sec=0.02)
        watcher.start()
        try:
            atomic_write_json(ws_sh.join("spaces", "source", "resync_probe.json"), {"v": 1})
            flushed = watcher.resync_paths((ws_sh.join("spaces"),))
            check(ws_sh.join("spaces", "source", "resync_probe.json") in flushed, f"Watcher resync missed change: {flushed}")
            time.sleep(0.1)
            check(not w_events, f"Resynced change fired duplicate callback: {w_events}")
        finally:
            watcher.stop()
    finally:
        daemon.request_shutdown(force=True)
        rig_sh.dispatcher.shutdown(grace_ms=200)

    # Verify CONTROL_RELOAD during pending config watcher debounce does not swallow on_config_changed_task & cleans handoff_lease when self_restart_argv is None
    ws_rel_cfg = HostPath(tmp_root / "ws_reload_preserves_cfg_notify")
    provision_live_workspace(ws_rel_cfg.path)
    cfg_seen: list[list[str]] = []
    cfg_ev_seen: list[list[str]] = []
    hold_cfg_gate = threading.Event()
    hold_cfg_gate.set()
    entered_cfg_gate = threading.Event()

    @dataclass(frozen=True, slots=True)
    class _CfgNotifyIn:
        changed_paths: list[str]

    class _CoreCfgNotifyTask(Task[_CfgNotifyIn, bool]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("core.on_cfg"),
                input_type=_CfgNotifyIn,
                output_type=bool,
            )

        @property
        def metadata(self) -> TaskMetadata[_CfgNotifyIn, bool]:
            return self._meta

        def run(self, req: _CfgNotifyIn, _ctx: TaskContext) -> bool:
            cfg_seen.append(list(req.changed_paths))
            if not hold_cfg_gate.is_set():
                entered_cfg_gate.set()
                hold_cfg_gate.wait(timeout=5.0)
            return True

    class _CoreCfgMod(YscbModule):
        def __init__(self) -> None:
            self._mid = ModuleId("core")
            self._tasks = (_CoreCfgNotifyTask(),)

        @property
        def module_id(self) -> ModuleId:
            return self._mid

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    class _CfgEventSubTask(Task[_CfgNotifyIn, bool]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("cfgprobe.on_cfg_ev"),
                input_type=_CfgNotifyIn,
                output_type=bool,
                subscriptions=(
                    EventSubscriptionSpec(
                        EventId("core.config_changed"),
                        lambda items: _CfgNotifyIn(changed_paths=[x for it in items for x in it.changed_paths]),
                        payload_type=_CfgNotifyIn,
                    ),
                ),
            )

        @property
        def metadata(self) -> TaskMetadata[_CfgNotifyIn, bool]:
            return self._meta

        def run(self, req: _CfgNotifyIn, _ctx: TaskContext) -> bool:
            cfg_ev_seen.append(list(req.changed_paths))
            return True

    class _CfgProbeMod(YscbModule):
        def __init__(self) -> None:
            self._mid = ModuleId("cfgprobe")
            self._tasks = (_CfgEventSubTask(),)

        @property
        def module_id(self) -> ModuleId:
            return self._mid

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    rig_rc = build_dispatcher_for_workspace(
        ws_rel_cfg,
        HostPath(venv_py),
        is_daemon_host=True,
        sandbox_restricted=True,
    )
    rig_rc.dispatcher.shutdown(grace_ms=100)
    disp_rc = RuntimeDispatcher(
        workspace_root=ws_rel_cfg,
        cache_dir=ws_rel_cfg.join(".cache"),
        module_provider=rig_rc.provider,
        options=DispatcherHostOptions(
            config_view=rig_rc.config_view,
            is_daemon_host=True,
            in_memory_modules=(_CoreCfgMod(), _CfgProbeMod()),
        ),
    )
    daemon_rc = WorkspaceDaemon(
        workspace_root=ws_rel_cfg,
        cache_dir=ws_rel_cfg.join(".cache"),
        dispatcher=disp_rc,
        config_view=rig_rc.config_view,
        watch_config=DaemonWatcherConfig(
            echo_guard=rig_rc.echo_ledger,
            config_watch_roots=(ws_rel_cfg.join("config"),),
            on_config_changed_task=TaskId("core.on_cfg"),
            watcher_debounce_sec=0.35,
        ),
        self_restart_argv=None,
    )
    ready_ev = threading.Event()
    th_rc = threading.Thread(
        target=lambda: daemon_rc.run_forever(ready_callback=ready_ev.set),
        name="test-daemon-reload-cfg",
        daemon=True,
    )
    th_rc.start()
    try:
        check(ready_ev.wait(timeout=5.0), "Embedded daemon failed to reach ready state")
        target_cfg = ws_rel_cfg.join("config", "gdrive.json")
        atomic_write_json(target_cfg, {"custom_flag": "debounced_reload_check"})
        rel_ack = query_daemon_control(
            ws_rel_cfg.join(".cache"),
            ws_rel_cfg,
            FrameKind.CONTROL_RELOAD,
            {"modules": ["ast"]},
        )
        check(rel_ack is not None and rel_ack.get("reloaded") is True, f"Expected module reload ack: {rel_ack}")
        wait_until(lambda: len(cfg_seen) >= 1, timeout_sec=3.0)
        check(
            any(str(target_cfg) in batch for batch in cfg_seen),
            f"Expected on_config_changed_task to receive debounced config path despite concurrent CONTROL_RELOAD: {cfg_seen}",
        )
        # Verify async config notification interrupted by QUIESCED requeues cleanly and delivers core.config_changed after CONTROL_RESUME
        wait_until(lambda: len(cfg_ev_seen) >= 1, timeout_sec=3.0)
        cfg_ev_seen.clear()
        entered_cfg_gate.clear()
        hold_cfg_gate.clear()
        atomic_write_json(target_cfg, {"custom_flag": "quiesce_interrupted_notify"})
        check(entered_cfg_gate.wait(timeout=4.0), "Expected core.on_cfg to enter before QUIESCED")
        q_ack = query_daemon_control(
            ws_rel_cfg.join(".cache"),
            ws_rel_cfg,
            FrameKind.CONTROL_QUIESCE,
            {"lease_sec": 15.0, "drain_timeout_sec": 3.0},
        )
        check(q_ack is not None and q_ack.get("ok") is True, f"Expected CONTROL_QUIESCE ack: {q_ack}")
        q_epoch = q_ack["epoch"]
        hold_cfg_gate.set()
        time.sleep(0.05)
        check(len(cfg_ev_seen) == 0, f"Subscriber must not fire while globally QUIESCED: {cfg_ev_seen}")
        r_ack = query_daemon_control(
            ws_rel_cfg.join(".cache"),
            ws_rel_cfg,
            FrameKind.CONTROL_RESUME,
            {"expected_epoch": q_epoch},
        )
        check(r_ack is not None and r_ack.get("ok") is True, f"Expected CONTROL_RESUME ack: {r_ack}")
        wait_until(lambda: len(cfg_ev_seen) >= 1, timeout_sec=3.0)
        check(
            any(str(target_cfg) in batch for batch in cfg_ev_seen),
            f"Deferred core.config_changed event must deliver after CONTROL_RESUME without loss: {cfg_ev_seen}",
        )
        daemon_rc.request_shutdown(core_handoff=True)
        th_rc.join(timeout=5.0)
        check(not th_rc.is_alive(), "Embedded daemon thread did not exit cleanly")
        check(
            read_active_handoff_boot_id(ws_rel_cfg.join(".cache")) is None,
            "Dangling handoff_lease.json must be cleaned up when run_forever exits with self_restart_argv=None",
        )
    finally:
        daemon_rc.request_shutdown(force=True)
        th_rc.join(timeout=2.0)
        disp_rc.shutdown(grace_ms=200)


@dataclass(frozen=True, slots=True)
class _Step5DrainEvDto:
    stage: str


@dataclass(frozen=True, slots=True)
class _Step5DrainOutDto:
    stage: str


def _verify_queued_coalesce_leader_cancel_and_timeout(tmp_root: Path) -> None:
    ws_q = HostPath(tmp_root / "ws_queued_coal_cancel")
    ws_q.path.mkdir(parents=True, exist_ok=True)
    blk_entered = threading.Event()
    blk_release = threading.Event()
    coal_runs = [0]

    class _HoldSerialTask(Task[_CoordReqDto, _CoordOutDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("qmod.hold_serial"),
                input_type=_CoordReqDto,
                output_type=_CoordOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                resource_key="queued.slot",
                concurrency_mode=ConcurrencyMode.SERIALIZE,
            )

        @property
        def metadata(self) -> TaskMetadata[_CoordReqDto, _CoordOutDto]:
            return self._meta

        def run(self, _req: _CoordReqDto, ctx: TaskContext) -> _CoordOutDto:
            blk_entered.set()
            blk_release.wait(timeout=3.0)
            return _CoordOutDto(seen_priority=ctx.effective_priority.value, run_seq=0)

    class _QueuedCoalTask(Task[_CoordReqDto, _CoordOutDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("qmod.coal_work"),
                input_type=_CoordReqDto,
                output_type=_CoordOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                resource_key="queued.slot",
                concurrency_mode=ConcurrencyMode.COALESCE,
                equivalence_fn=lambda r: r.eq_key,
            )

        @property
        def metadata(self) -> TaskMetadata[_CoordReqDto, _CoordOutDto]:
            return self._meta

        def run(self, _req: _CoordReqDto, ctx: TaskContext) -> _CoordOutDto:
            coal_runs[0] += 1
            return _CoordOutDto(seen_priority=ctx.effective_priority.value, run_seq=coal_runs[0])

    class _QueuedMod(YscbModule):
        def __init__(self) -> None:
            self._tasks = (_HoldSerialTask(), _QueuedCoalTask())

        @property
        def module_id(self) -> ModuleId:
            return ModuleId("qmod")

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    disp = RuntimeDispatcher(
        workspace_root=ws_q,
        cache_dir=ws_q.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(_QueuedMod(),),
        ),
    )
    try:
        disp.container_lifecycle.transition_boot_phase(ContainerState.READY)
        blk_res: list[TaskOutcome[object]] = []
        lead_res: list[TaskOutcome[object]] = []
        foll_res: list[TaskOutcome[object]] = []
        lead_tok = CancellationToken()
        foll_tok = CancellationToken()

        t_blk = threading.Thread(
            target=lambda: blk_res.append(
                disp.invoke(InvokeRequest(TaskId("qmod.hold_serial"), {"eq_key": "blk"}, ws_q, ws_q))
            )
        )
        t_blk.start()
        check(blk_entered.wait(timeout=2.0), "Blocker did not acquire queued.slot")

        t_lead = threading.Thread(
            target=lambda: lead_res.append(
                disp.invoke(
                    InvokeRequest(TaskId("qmod.coal_work"), {"eq_key": "same"}, ws_q, ws_q),
                    cancel_token=lead_tok,
                )
            )
        )
        t_lead.start()
        wait_coalesce_count(disp, "queued.slot", 1, timeout_sec=2.0)

        t_foll = threading.Thread(
            target=lambda: foll_res.append(
                disp.invoke(
                    InvokeRequest(TaskId("qmod.coal_work"), {"eq_key": "same"}, ws_q, ws_q),
                    cancel_token=foll_tok,
                )
            )
        )
        t_foll.start()
        wait_coalesce_count(disp, "queued.slot", 2, timeout_sec=2.0)

        lead_tok.cancel(reason="queued_leader_cancelled")
        time.sleep(0.05)
        blk_release.set()
        t_blk.join(timeout=3.0)
        t_lead.join(timeout=3.0)
        t_foll.join(timeout=3.0)

        check(len(blk_res) == 1 and blk_res[0].ok, f"Blocker failed: {blk_res}")
        check(
            len(lead_res) == 1 and (not lead_res[0].ok) and lead_res[0].error is not None
            and lead_res[0].error.code == ErrorCode.TASK_CANCELLED,
            f"Cancelled queued leader mismatch: {lead_res}",
        )
        check(
            len(foll_res) == 1 and foll_res[0].ok and foll_res[0].coalesced and coal_runs[0] == 1,
            f"Surviving follower failed after queued leader cancel: {foll_res}, runs={coal_runs[0]}",
        )
    finally:
        disp.shutdown(grace_ms=200)

    coord = ResourceCoordinator(cache_dir=ws_q.join(".cache"), workspace_root=ws_q, is_daemon_host=True)
    os_blk_in = threading.Event()
    os_blk_rel = threading.Event()
    lead_err_box: list[BaseException] = []
    foll_exec_box: list[CoordinatedExecution[str]] = []

    def _run_blk() -> None:
        blk_spec = ResourceAcquireSpec(
            resource_key="queued.timeout.slot",
            mode=ConcurrencyMode.SERIALIZE,
            equiv_key="blk",
            priority=ExecutionPriority.FOREGROUND,
            turn_id="turn_blk",
            call_stack=((ws_q, TaskId("qmod.hold_serial")),),
            cancel_token=CancellationToken(),
        )
        def _blk_body(_ph: PriorityHandle, _tok: CancellationToken, _fl: Optional[StepFlight[str]]) -> str:
            os_blk_in.set()
            os_blk_rel.wait(timeout=3.0)
            return "blk"

        coord.execute(blk_spec, _blk_body)

    def _run_short_leader() -> None:
        short_spec = ResourceAcquireSpec(
            resource_key="queued.timeout.slot",
            mode=ConcurrencyMode.COALESCE,
            equiv_key="same_timeout",
            priority=ExecutionPriority.BACKGROUND,
            turn_id="turn_short",
            call_stack=((ws_q, TaskId("qmod.coal_work")),),
            cancel_token=CancellationToken(),
            timeout_ms=60,
        )
        try:
            coord.execute(short_spec, lambda _ph, _tok, _fl: "shared_ok")
        except BaseException as exc:
            lead_err_box.append(exc)

    def _run_long_follower() -> None:
        long_spec = ResourceAcquireSpec(
            resource_key="queued.timeout.slot",
            mode=ConcurrencyMode.COALESCE,
            equiv_key="same_timeout",
            priority=ExecutionPriority.FOREGROUND,
            turn_id="turn_long",
            call_stack=((ws_q, TaskId("qmod.coal_work")),),
            cancel_token=CancellationToken(),
            timeout_ms=4000,
        )
        foll_exec_box.append(coord.execute(long_spec, lambda _ph, _tok, _fl: "unused"))

    t_ob = threading.Thread(target=_run_blk)
    t_ob.start()
    check(os_blk_in.wait(timeout=2.0), "Coordinator blocker did not enter")
    t_sl = threading.Thread(target=_run_short_leader)
    t_sl.start()
    wait_until(lambda: coord.coalesce_participant_count("queued.timeout.slot") == 1, timeout_sec=2.0)
    t_lf = threading.Thread(target=_run_long_follower)
    t_lf.start()
    wait_until(lambda: coord.coalesce_participant_count("queued.timeout.slot") == 2, timeout_sec=2.0)
    time.sleep(0.10)
    os_blk_rel.set()
    t_ob.join(timeout=3.0)
    t_sl.join(timeout=3.0)
    t_lf.join(timeout=3.0)
    check(
        len(foll_exec_box) == 1 and foll_exec_box[0].is_follower and foll_exec_box[0].outcome == "shared_ok",
        f"Follower did not survive queued short-timeout leader: {foll_exec_box}",
    )
    check(
        len(lead_err_box) == 1 and isinstance(lead_err_box[0], YscbError)
        and lead_err_box[0].detail.code == ErrorCode.TASK_TIMEOUT,
        f"Timed-out queued leader did not receive TASK_TIMEOUT: {lead_err_box}",
    )


def _verify_step5_quiesce_draining_no_deadlock(tmp_root: Path) -> None:
    ws_s5 = HostPath(tmp_root / "ws_step5_quiesce")
    ws_s5.path.mkdir(parents=True, exist_ok=True)
    ev_step5_first = EventMetadata(EventId("qstep5.ev_first"), _Step5DrainEvDto)
    ev_step5_second = EventMetadata(EventId("qstep5.ev_second"), _Step5DrainEvDto)
    sub_a_entered = threading.Event()
    sub_a_release = threading.Event()
    sub_b_ran = threading.Event()

    class _CoalStep5Task(Task[_CoordReqDto, _Step5DrainOutDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("qstep5.primary"),
                input_type=_CoordReqDto,
                output_type=_Step5DrainOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                resource_key="qstep5.slot",
                concurrency_mode=ConcurrencyMode.COALESCE,
                equivalence_fn=lambda r: r.eq_key,
            )

        @property
        def metadata(self) -> TaskMetadata[_CoordReqDto, _Step5DrainOutDto]:
            return self._meta

        def run(self, _req: _CoordReqDto, ctx: TaskContext) -> _Step5DrainOutDto:
            ctx.emit(ev_step5_first, _Step5DrainEvDto(stage="wave_first"))
            return _Step5DrainOutDto(stage="primary_done")

    class _Step5SubATask(Task[_Step5DrainEvDto, _Step5DrainOutDto]):
        def __init__(self) -> None:
            sub = EventSubscriptionSpec(ev_step5_first, lambda items: items[0] if items else None)
            self._meta = TaskMetadata(
                task_id=TaskId("qstep5.sub_a"),
                input_type=_Step5DrainEvDto,
                output_type=_Step5DrainOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                subscriptions=(sub,),
            )

        @property
        def metadata(self) -> TaskMetadata[_Step5DrainEvDto, _Step5DrainOutDto]:
            return self._meta

        def run(self, _req: _Step5DrainEvDto, ctx: TaskContext) -> _Step5DrainOutDto:
            sub_a_entered.set()
            sub_a_release.wait(timeout=3.0)
            ctx.emit(ev_step5_second, _Step5DrainEvDto(stage="wave_second"))
            return _Step5DrainOutDto(stage="sub_a_done")

    class _Step5SubBTask(Task[_Step5DrainEvDto, _Step5DrainOutDto]):
        def __init__(self) -> None:
            sub = EventSubscriptionSpec(ev_step5_second, lambda items: items[0] if items else None)
            self._meta = TaskMetadata(
                task_id=TaskId("qstep5.sub_b"),
                input_type=_Step5DrainEvDto,
                output_type=_Step5DrainOutDto,
                dispatch_mode=DispatchMode.HYBRID,
                subscriptions=(sub,),
            )

        @property
        def metadata(self) -> TaskMetadata[_Step5DrainEvDto, _Step5DrainOutDto]:
            return self._meta

        def run(self, _req: _Step5DrainEvDto, _ctx: TaskContext) -> _Step5DrainOutDto:
            sub_b_ran.set()
            return _Step5DrainOutDto(stage="sub_b_done")

    class _Step5Mod(YscbModule):
        def __init__(self) -> None:
            self._tasks = (_CoalStep5Task(), _Step5SubATask(), _Step5SubBTask())

        @property
        def module_id(self) -> ModuleId:
            return ModuleId("qstep5")

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    disp = RuntimeDispatcher(
        workspace_root=ws_s5,
        cache_dir=ws_s5.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(_Step5Mod(),),
        ),
    )
    try:
        disp.container_lifecycle.transition_boot_phase(ContainerState.READY)
        coal_out: list[TaskOutcome[object]] = []
        quiesce_ok: list[bool] = []
        t_coal = threading.Thread(
            target=lambda: coal_out.append(
                disp.invoke(InvokeRequest(TaskId("qstep5.primary"), {"eq_key": "k_q"}, ws_s5, ws_s5))
            )
        )
        t_coal.start()
        check(sub_a_entered.wait(timeout=2.0), "Step 5 wave_first subscriber did not enter")
        t_quiesce = threading.Thread(
            target=lambda: quiesce_ok.append(
                disp.try_quiesce_global(drain_deadline=time.monotonic() + 3.0, leased=True)
            )
        )
        t_quiesce.start()
        wait_until(disp.reload_gate.is_globally_quiesced, timeout_sec=2.0)
        sub_a_release.set()
        t_coal.join(timeout=3.0)
        t_quiesce.join(timeout=3.0)
        check(len(coal_out) == 1 and coal_out[0].ok, f"COALESCE Step 5 failed during QUIESCE drain: {coal_out}")
        check(sub_b_ran.is_set(), "Step 5 second-wave subscriber blocked by QUIESCE draining")
        check(quiesce_ok == [True], f"Global QUIESCE failed to drain cleanly across Step 5: {quiesce_ok}")
    finally:
        disp.shutdown(grace_ms=200)

    fl: StepFlight[str] = StepFlight(PriorityHandle(ExecutionPriority.FOREGROUND))
    step_tok = CancellationToken()
    turn_tok = CancellationToken()
    slot_id, det_step4 = fl.add_caller(
        FlightCallerRegistration("t_cancel", "t_cancel", (), step_tok, turn_tok, deadline=time.monotonic() + 5.0),
        None,
    )
    check(slot_id >= 0 and det_step4 is not None, "StepFlight add_caller failed")
    step_tok.cancel(reason="all_step_cancelled")
    turn_tok.cancel(reason="all_turn_cancelled")
    check(fl.effective_deadline() is None, f"Cancelled StepFlight must not return expired 0.0 deadline: {fl.effective_deadline()}")
    check(fl.effective_post_step_deadline() is None, f"Cancelled StepFlight post_step deadline must be None: {fl.effective_post_step_deadline()}")
    got_cancelled = False
    try:
        fl.run_or_await_post_step(slot_id, turn_tok, 1.0, lambda _c, _dl: "never")
    except TaskCancelledException:
        got_cancelled = True
    check(got_cancelled, "Cancelled StepFlight post_step must raise TaskCancelledException")


def _verify_watcher_poll_interval_and_env_lease_di(tmp_root: Path, venv_py: Path) -> None:
    default_cfg = DaemonWatcherConfig()
    check(
        default_cfg.poll_interval_sec is None and default_cfg.effective_poll_interval_sec() > 0.1,
        f"Default DaemonWatcherConfig poll interval still capped at 100ms: {default_cfg.effective_poll_interval_sec()}",
    )
    slow_cfg = DaemonWatcherConfig(watcher_debounce_sec=1.0)
    check(
        abs(slow_cfg.effective_poll_interval_sec() - 0.5) < 1e-6,
        f"Expected 0.5s poll interval for 1.0s debounce, got {slow_cfg.effective_poll_interval_sec()}",
    )
    explicit_cfg = DaemonWatcherConfig(watcher_debounce_sec=0.5, poll_interval_sec=0.75)
    check(
        abs(explicit_cfg.effective_poll_interval_sec() - 0.75) < 1e-6,
        f"Explicit poll_interval_sec not honored: {explicit_cfg.effective_poll_interval_sec()}",
    )
    fast_cfg = DaemonWatcherConfig(watcher_debounce_sec=0.05)
    check(
        0.02 <= fast_cfg.effective_poll_interval_sec() <= 0.05,
        f"Fast test debounce lost responsiveness: {fast_cfg.effective_poll_interval_sec()}",
    )
    for bad_poll in (0.0, -0.5, float("nan"), float("inf")):
        assert_raises_val_error(lambda bp=bad_poll: DaemonWatcherConfig(poll_interval_sec=bp))

    ws_lease = HostPath(tmp_root / "ws_env_lease_di")
    provision_live_workspace(ws_lease.path)
    venv_hp = HostPath(venv_py)
    provider = ManifestModuleProvider(ws_lease, venv_hp, dedicated_venv_python=resolve_dedicated_venv_py(venv_hp))

    lease_lock = threading.Lock()
    acquired: list[HostPath] = []
    released: list[HostPath] = []
    touched: list[HostPath] = []
    active_leases = [0]

    def _acquire_spy(vp: HostPath) -> Optional[Callable[[], None]]:
        with lease_lock:
            acquired.append(vp)
            active_leases[0] += 1

        def _release() -> None:
            with lease_lock:
                active_leases[0] -= 1
                released.append(vp)

        return _release

    def _touch_spy(vp: HostPath) -> None:
        with lease_lock:
            touched.append(vp)

    acquire_cb: EnvLeaseAcquireFn = _acquire_spy
    touch_cb: EnvTouchUsedFn = _touch_spy

    disp_hot = RuntimeDispatcher(
        workspace_root=ws_lease,
        cache_dir=ws_lease.join(".cache"),
        module_provider=provider,
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            env_lease_acquire=acquire_cb,
            env_touch_used=touch_cb,
        ),
    )
    try:
        disp_hot.container_lifecycle.transition_boot_phase(ContainerState.READY)
        out_hot_first = disp_hot.invoke_typed(KDB_SEARCH_META, SearchInDto(query="lease_hot_first"))
        out_hot_second = disp_hot.invoke_typed(KDB_SEARCH_META, SearchInDto(query="lease_hot_second"))
        check(
            out_hot_first.ok and out_hot_second.ok and out_hot_first.value is not None and out_hot_second.value is not None,
            f"Hot Tier 1 lease calls failed: {(out_hot_first, out_hot_second)}",
        )
        check(
            out_hot_first.value.worker_pid == out_hot_second.value.worker_pid,
            f"Expected warm worker reuse: {(out_hot_first.value, out_hot_second.value)}",
        )
        with lease_lock:
            check(
                len(acquired) == 1 and active_leases[0] == 1 and len(released) == 0 and len(touched) >= 2,
                f"HotWorkerPool lease/touch mismatch while alive: acq={len(acquired)} active={active_leases[0]} rel={len(released)} touch={len(touched)}",
            )
    finally:
        disp_hot.shutdown(grace_ms=500)
    with lease_lock:
        check(
            len(released) == 1 and active_leases[0] == 0 and released == acquired,
            f"HotWorkerPool failed to release env lease on shutdown: acq={acquired} rel={released} active={active_leases[0]}",
        )
        acquired.clear()
        released.clear()
        touched.clear()

    disp_cold = RuntimeDispatcher(
        workspace_root=ws_lease,
        cache_dir=ws_lease.join(".cache"),
        module_provider=provider,
        options=DispatcherHostOptions(
            is_daemon_host=False,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            env_lease_acquire=acquire_cb,
            env_touch_used=touch_cb,
        ),
    )
    try:
        out_cold = disp_cold.invoke_typed(
            KDB_SEARCH_META,
            SearchInDto(query="lease_cold"),
            routing_policy=ClientRoutingPolicy.FORCE_COLD,
        )
        check(out_cold.ok and not out_cold.executed_hot, f"Cold Tier 1 lease call failed: {out_cold}")
        with lease_lock:
            check(
                len(acquired) == 1 and len(released) == 1 and active_leases[0] == 0
                and released == acquired and len(touched) >= 1,
                f"OneShotVenvHost lease/touch mismatch: acq={len(acquired)} rel={len(released)} active={active_leases[0]} touch={len(touched)}",
            )
    finally:
        disp_cold.shutdown(grace_ms=300)


def _read_jsonl_records(path: Path) -> list[JsonObject]:
    if not path.is_file():
        return []
    out: list[JsonObject] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        text = raw_line.strip()
        if text:
            out.append(strict_parse_json_object(text))
    return out


def _collect_prof_names(node: ProfilerNodeSnapshot) -> set[str]:
    names = {node.name}
    for child in node.children:
        names.update(_collect_prof_names(child))
    return names


def _verify_observability_logs_and_single_owner(tmp_root: Path) -> None:
    ws_obs = HostPath(tmp_root / "ws_obs_logs")
    ws_obs.path.mkdir(parents=True, exist_ok=True)
    caller_fields_info: dict[str, object] = {"token": "tok_raw_secret_val", "ok": True}
    caller_fields_warn: dict[str, object] = {"api_key": "ak_raw_secret_val"}

    class _ObsWorkTask(Task[_InMemReqDto, _InMemRespDto]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(
                task_id=TaskId("obsmod.work"),
                input_type=_InMemReqDto,
                output_type=_InMemRespDto,
                dispatch_mode=DispatchMode.HYBRID,
            )

        @property
        def metadata(self) -> TaskMetadata[_InMemReqDto, _InMemRespDto]:
            return self._meta

        def run(self, req: _InMemReqDto, ctx: TaskContext) -> _InMemRespDto:
            ctx.logger.log(LogLevel.INFO, "obs_info_msg", fields=caller_fields_info)
            ctx.logger.log(LogLevel.WARNING, "obs_warn_msg", fields=caller_fields_warn)
            with ctx.profiler.scope("obs_sub_scope"):
                time.sleep(0.004)
            if req.key == "fail":
                raise RuntimeError("boom Bearer super_secret_token_999")
            return _InMemRespDto(echo=f"obs:{req.key}")

    class _ObsMod(YscbModule):
        def __init__(self) -> None:
            self._tasks = (_ObsWorkTask(),)

        @property
        def module_id(self) -> ModuleId:
            return ModuleId("obsmod")

        def tasks(self) -> Sequence[BoundTask]:
            return self._tasks

    cfg_view = FileConfigView(ws_obs)
    logs_dir = ws_obs.join(".cache", "logs")
    router = FlightLogRouter(
        logs_dir,
        config=FlightLogConfig(respect_sandbox=False, slow_threshold_ms=5000.0),
        daemon_boot_id="boot_obs_01",
    )
    ring = ProfilerRingBuffer(maxlen=32)
    disp = RuntimeDispatcher(
        workspace_root=ws_obs,
        cache_dir=ws_obs.join(".cache"),
        module_provider=_EmptyModuleProvider(),
        options=DispatcherHostOptions(
            config_view=cfg_view,
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(_ObsMod(),),
            module_services_factory=build_workspace_module_services_factory(ws_obs, ws_obs),
            flight_log_router=router,
            daemon_boot_id="boot_obs_01",
            profiler_ring_buffer=ring,
        ),
    )
    try:
        disp.container_lifecycle.transition_boot_phase(ContainerState.READY)
        ok_out = disp.invoke(InvokeRequest(TaskId("obsmod.work"), {"key": "fast"}, ws_obs, ws_obs))
        check(ok_out.ok and ok_out.value == {"echo": "obs:fast"}, f"Obs direct task failed: {ok_out}")
        check(caller_fields_info["token"] == "tok_raw_secret_val", "Logger mutated caller info dict")
        check(caller_fields_warn["api_key"] == "ak_raw_secret_val", "Logger mutated caller warn dict")

        mod_log = logs_dir.path / "modules" / "obsmod.jsonl"
        check(mod_log.is_file(), f"Missing module log at {mod_log}")
        mod_raw = mod_log.read_text(encoding="utf-8")
        check("tok_raw_secret_val" not in mod_raw and "ak_raw_secret_val" not in mod_raw, "Raw secret leaked to module log")
        mod_recs = _read_jsonl_records(mod_log)
        check(len(mod_recs) == 2, f"Expected 2 module log lines, got {len(mod_recs)}")
        first_tid = str(mod_recs[0].get("trace_id", ""))
        check(
            bool(first_tid)
            and str(mod_recs[0].get("task_id")) == "obsmod.work"
            and str(mod_recs[0].get("exec_mode")) == "hot"
            and str(mod_recs[0].get("daemon_boot_id")) == "boot_obs_01"
            and mod_recs[0].get("pid") == os.getpid()
            and "Task/obsmod.work" in str(mod_recs[0].get("span_id", "")),
            f"Module log correlation mismatch: {mod_recs[0]}",
        )

        daily_files = sorted((logs_dir.path / "daily").glob("*.jsonl"))
        perf_files = sorted((logs_dir.path / "perf").glob("*.jsonl"))
        check(len(daily_files) == 1 and len(perf_files) == 1, f"Missing daily/perf files: {(daily_files, perf_files)}")
        daily_recs = _read_jsonl_records(daily_files[0])
        perf_recs = _read_jsonl_records(perf_files[0])
        check(
            [str(r.get("kind")) for r in daily_recs] == ["IN", "ALERT", "OUT"]
            and all(str(r.get("trace_id")) == first_tid for r in daily_recs),
            f"Expected IN/ALERT/OUT with correlated trace_id, got {daily_recs}",
        )
        check(
            len(perf_recs) == 1 and perf_recs[0].get("ok") is True
            and perf_recs[0].get("error_detail") is None and perf_recs[0].get("runtime_snapshot") is None,
            f"Fast perf trace unexpected diagnostics: {perf_recs}",
        )

        ext_prof = ProfilerSession(root_name="cli_owner")
        ext_out = disp.invoke(
            InvokeRequest(
                TaskId("obsmod.work"), {"key": "ext"}, ws_obs, ws_obs,
                external_flight_owner=True, active_profiler=ext_prof,
            )
        )
        check(ext_out.ok, f"External owner invoke failed: {ext_out}")
        daily_after_ext = _read_jsonl_records(daily_files[0])
        perf_after_ext = _read_jsonl_records(perf_files[0])
        check(
            sum(1 for r in daily_after_ext if r.get("kind") in ("IN", "OUT")) == 2 and len(perf_after_ext) == 1,
            f"external_flight_owner=True wrote duplicate daily/perf records: {(daily_after_ext, perf_after_ext)}",
        )
        ext_names = _collect_prof_names(ext_prof.snapshot())
        check("obs_sub_scope" in ext_names and "obsmod.work" in ext_names, f"External profiler missed scopes: {ext_names}")

        fail_out = disp.invoke(InvokeRequest(TaskId("obsmod.work"), {"key": "fail"}, ws_obs, ws_obs))
        check(not fail_out.ok, f"Expected failure outcome: {fail_out}")
        perf_after_fail = _read_jsonl_records(perf_files[0])
        fail_rec = perf_after_fail[-1]
        check(
            fail_rec.get("ok") is False and isinstance(fail_rec.get("error_detail"), dict)
            and isinstance(fail_rec.get("runtime_snapshot"), dict)
            and "super_secret_token_999" not in str(fail_rec.get("error_detail")),
            f"Failure perf trace missing redacted diagnostics: {fail_rec}",
        )

        atomic_write_json(ws_obs.join("config", "core.json"), {"observability": {"slow_threshold_ms": 0.0}})
        cfg_view.reload()
        slow_out = disp.invoke(InvokeRequest(TaskId("obsmod.work"), {"key": "slow"}, ws_obs, ws_obs))
        check(slow_out.ok, f"Slow threshold invoke failed: {slow_out}")
        slow_rec = _read_jsonl_records(perf_files[0])[-1]
        check(
            slow_rec.get("ok") is True and isinstance(slow_rec.get("runtime_snapshot"), dict),
            f"Slow trace missing runtime_snapshot: {slow_rec}",
        )
    finally:
        disp.shutdown(grace_ms=200)
        router.close()


def _verify_tier1_profiler_merge_mem_and_fail_open(tmp_root: Path, venv_py: Path) -> None:
    deep_tree: dict[str, object] = {
        "name": "leaf", "self_ms": 0.1, "total_ms": 0.1, "calls": 1, "alloc_kb": 0.0, "callers": [], "children": [],
    }
    for depth_idx in range(45):
        deep_tree = {
            "name": f"lv_{depth_idx}", "self_ms": 0.0, "total_ms": 0.1,
            "calls": 1, "alloc_kb": 0.0, "callers": [], "children": [deep_tree],
        }
    for bad_tree in ({"bad": 123}, "not_a_dict", deep_tree):
        ws_rep = WorkerStepReply(ok=True, raw_output={"ok": True}, profiler_tree=bad_tree)
        rpc_rep = DaemonRpcInvokeReply(ok=True, raw_value={"ok": True}, profiler_tree=bad_tree)
        check(ws_rep.profiler_tree is None, f"Malformed WorkerStepReply.profiler_tree not sanitized: {ws_rep}")
        check(rpc_rep.profiler_tree is None, f"Malformed DaemonRpcInvokeReply.profiler_tree not sanitized: {rpc_rep}")

    ws_t1 = HostPath(tmp_root / "ws_t1_prof")
    provision_live_workspace(ws_t1.path)
    t1_code = (
        "from dataclasses import dataclass\n"
        "import os\n"
        "import time\n"
        "from typing import Sequence\n"
        "from core.execution.runtime import BoundTask, Task, TaskContext, TaskMetadata, YscbModule\n"
        "from core.foundation import LogLevel, ModuleId, TaskId\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class ProfIn:\n"
        "    tag: str\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class ProfOut:\n"
        "    worker_pid: int\n"
        "    span_path: str\n"
        "    buf_len: int\n\n"
        "class ProfComputeTask(Task[ProfIn, ProfOut]):\n"
        "    def __init__(self) -> None:\n"
        "        self._meta = TaskMetadata(TaskId('prof_t1.compute'), ProfIn, ProfOut)\n"
        "    @property\n"
        "    def metadata(self) -> TaskMetadata[ProfIn, ProfOut]:\n"
        "        return self._meta\n"
        "    def run(self, _req: ProfIn, ctx: TaskContext) -> ProfOut:\n"
        "        ctx.logger.log(LogLevel.WARNING, 'worker_prof_warn', fields={'secret': 'worker_secret_val'})\n"
        "        with ctx.profiler.scope('t1_inner_work'):\n"
        "            buf = [bytes(64) for _ in range(128)]\n"
        "            time.sleep(0.005)\n"
        "            span_now = ctx.profiler.current_span_path()\n"
        "        return ProfOut(worker_pid=os.getpid(), span_path=span_now, buf_len=len(buf))\n\n"
        "class ProfT1Mod(YscbModule):\n"
        "    def __init__(self) -> None:\n"
        "        self._tasks = (ProfComputeTask(),)\n"
        "    @property\n"
        "    def module_id(self) -> ModuleId:\n"
        "        return ModuleId('prof_t1')\n"
        "    def tasks(self) -> Sequence[BoundTask]:\n"
        "        return self._tasks\n\n"
        "def create_module() -> YscbModule:\n"
        "    return ProfT1Mod()\n"
    )
    write_module(
        ws_t1.path,
        "prof_t1",
        {"tier1": True, "venv_group": "prof_grp", "tasks": [{"task_id": "prof_t1.compute"}]},
        t1_code,
    )
    venv_hp = HostPath(venv_py)
    provider = ManifestModuleProvider(ws_t1, venv_hp, dedicated_venv_python=resolve_dedicated_venv_py(venv_hp))
    logs_dir = ws_t1.join(".cache", "logs")
    router = FlightLogRouter(logs_dir, config=FlightLogConfig(respect_sandbox=False), daemon_boot_id="boot_t1_01")
    ring = ProfilerRingBuffer(maxlen=16)
    disp = RuntimeDispatcher(
        workspace_root=ws_t1,
        cache_dir=ws_t1.join(".cache"),
        module_provider=provider,
        options=DispatcherHostOptions(
            is_daemon_host=True,
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            worker_host_dir=ws_t1,
            flight_log_router=router,
            daemon_boot_id="boot_t1_01",
            profiler_ring_buffer=ring,
        ),
    )
    try:
        disp.container_lifecycle.transition_boot_phase(ContainerState.READY)
        prof_root = ProfilerSession(root_name="root_t1", track_memory=True)
        out = disp.invoke(
            InvokeRequest(
                TaskId("prof_t1.compute"), {"tag": "mem"}, ws_t1, ws_t1,
                profile_mem=True, active_profiler=prof_root,
            )
        )
        check(
            out.ok and isinstance(out.value, dict) and jint(out.value, "worker_pid") != os.getpid(),
            f"Tier 1 profiler task failed: {out}",
        )
        check("t1_inner_work" in str(out.value.get("span_path", "")), f"Worker span path missing scope: {out.value}")
        check(not tracemalloc.is_tracing(), "MemoryTrackingGuard leaked tracemalloc active state")
        names = _collect_prof_names(prof_root.snapshot())
        check(
            {"WorkerSpawn", "WorkerStep", "Worker/prof_t1.compute", "LoadModule", "Task", "t1_inner_work"}.issubset(names),
            f"Merged Tier 1 profiler tree missing expected scopes: {sorted(names)}",
        )
        perf_files = sorted((logs_dir.path / "perf").glob("*.jsonl"))
        check(len(perf_files) == 1, f"Missing Tier 1 perf log: {perf_files}")
        perf_recs = _read_jsonl_records(perf_files[0])
        check(len(perf_recs) == 1 and perf_recs[0].get("mem_tracked") is True, f"Expected mem_tracked=True: {perf_recs}")
        mod_log = logs_dir.path / "modules" / "prof_t1.jsonl"
        check(mod_log.is_file(), f"Missing Tier 1 worker module log: {mod_log}")
        check("worker_secret_val" not in mod_log.read_text(encoding="utf-8"), "Worker secret leaked to module log")
        w_recs = _read_jsonl_records(mod_log)
        check(
            len(w_recs) >= 1 and w_recs[0].get("exec_mode") == "worker" and w_recs[0].get("daemon_boot_id") == "boot_t1_01",
            f"Worker module log correlation mismatch: {w_recs}",
        )
        daily_files = sorted((logs_dir.path / "daily").glob("*.jsonl"))
        daily_recs = _read_jsonl_records(daily_files[0]) if daily_files else []
        check(any(r.get("kind") == "ALERT" and r.get("exec_mode") == "worker" for r in daily_recs), f"Worker ALERT missing: {daily_recs}")
    finally:
        disp.shutdown(grace_ms=400)
        router.close()


def _verify_daemon_flight_logs_ring_summary_and_core_sig_cache(tmp_root: Path, venv_py: Path) -> None:
    ws_df = HostPath(tmp_root / "ws_daemon_flight")
    provision_live_workspace(ws_df.path)
    sig_probe = ws_df.path / ".modules" / "core" / "sig_probe.py"
    sig_probe.parent.mkdir(parents=True, exist_ok=True)
    sig_probe.write_text("SIG_VER = 1\n", encoding="utf-8")
    settled_ns = time.time_ns() - 5_000_000_000
    os.utime(sig_probe, ns=(settled_ns, settled_ns))

    venv_hp = HostPath(venv_py)
    provider = ManifestModuleProvider(ws_df, venv_hp, dedicated_venv_python=resolve_dedicated_venv_py(venv_hp))
    cfg_view = FileConfigView(ws_df)
    logs_dir = ws_df.join(".cache", "logs")
    router = FlightLogRouter(logs_dir, config=FlightLogConfig(respect_sandbox=False), daemon_boot_id="boot_df_01")
    disp_host = RuntimeDispatcher(
        workspace_root=ws_df,
        cache_dir=ws_df.join(".cache"),
        module_provider=provider,
        options=DispatcherHostOptions(config_view=cfg_view, is_daemon_host=True),
    )
    daemon = WorkspaceDaemon(
        workspace_root=ws_df,
        cache_dir=ws_df.join(".cache"),
        dispatcher=disp_host,
        config_view=cfg_view,
        flight_log_router=router,
        daemon_boot_id="boot_df_01",
    )
    disp_cli = RuntimeDispatcher(
        workspace_root=ws_df,
        cache_dir=ws_df.join(".cache"),
        module_provider=provider,
        options=DispatcherHostOptions(
            config_view=cfg_view,
            is_daemon_host=False,
            connection_config=DaemonConnectionConfig(enabled=True, auto_spawn=False),
        ),
    )
    ready_ev = threading.Event()
    th_df = threading.Thread(target=lambda: daemon.run_forever(ready_callback=ready_ev.set), daemon=True)
    th_df.start()
    try:
        check(ready_ev.wait(timeout=6.0), "Flight-log WorkspaceDaemon failed to reach READY")
        sig_cache_hp = ws_df.join(".cache", "daemon", "core_sig_cache.json")
        sig_doc = read_json_dict(sig_cache_hp)
        check(
            sig_doc is not None and isinstance(sig_doc.get("sig_probe.py"), list) and len(sig_doc["sig_probe.py"]) == 4,
            f"Missing persisted core_sig_cache.json entry: {sig_doc}",
        )

        cli_prof = ProfilerSession(root_name="cli_rpc_root")
        cli_out = disp_cli.invoke(
            InvokeRequest(
                task_id=TaskId("space.echo_tier0"),
                raw_input={"tag": "cli_rpc"},
                workspace_root=ws_df,
                caller_cwd=ws_df,
                caller_surface=CallerSurface.CLI,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
                external_flight_owner=True,
                active_profiler=cli_prof,
            )
        )
        check(cli_out.ok and cli_out.executed_hot, f"CLI RPC invoke failed: {cli_out}")
        cli_names = _collect_prof_names(cli_prof.snapshot())
        check("RpcCall" in cli_names and "space.echo_tier0" in cli_names, f"RPC profiler subtree not merged: {cli_names}")

        st_ack = query_daemon_control(ws_df.join(".cache"), ws_df, FrameKind.CONTROL_STATUS)
        check(st_ack is not None and isinstance(st_ack.get("status"), dict), f"Missing CONTROL_STATUS: {st_ack}")
        st_obj = st_ack["status"]
        prof_sum = st_obj.get("profiler_summary")
        check(
            st_obj.get("boot_id") == "boot_df_01"
            and isinstance(prof_sum, dict)
            and jint(prof_sum, "total_traces") >= 2
            and isinstance(prof_sum.get("by_task"), dict)
            and "daemon.boot" in prof_sum["by_task"]
            and "space.echo_tier0" in prof_sum["by_task"],
            f"DaemonStatusSnapshot missing boot_id or profiler_summary: {st_obj}",
        )
        q_ack = query_daemon_control(ws_df.join(".cache"), ws_df, FrameKind.CONTROL_QUIESCE, {"lease_sec": 5.0})
        check(q_ack is not None and q_ack.get("ok") is True, f"Quiesce ack failed: {q_ack}")
        r_ack = query_daemon_control(ws_df.join(".cache"), ws_df, FrameKind.CONTROL_RESUME, {})
        check(r_ack is not None and r_ack.get("ok") is True, f"Resume ack failed: {r_ack}")
        rel_ack = query_daemon_control(ws_df.join(".cache"), ws_df, FrameKind.CONTROL_RELOAD, {})
        check(rel_ack is not None and rel_ack.get("reloaded") is True, f"Reload ack failed: {rel_ack}")
        daemon.request_shutdown(force=False)
        th_df.join(timeout=6.0)
        check(not th_df.is_alive(), "Flight-log WorkspaceDaemon did not stop cleanly")
    finally:
        daemon.request_shutdown(force=True)
        th_df.join(timeout=2.0)
        disp_cli.shutdown(grace_ms=200)
        disp_host.shutdown(grace_ms=200)
        router.close()

    daemon_files = sorted((logs_dir.path / "daemon").glob("daemon_*.jsonl"))
    check(len(daemon_files) == 1, f"Expected 1 daemon stream file, got {daemon_files}")
    d_recs = _read_jsonl_records(daemon_files[0])
    d_events = {str(r.get("event")) for r in d_recs}
    check(
        {"boot_start", "ready", "rpc_done", "quiesce", "reload_start", "reload_done", "shutdown"}.issubset(d_events),
        f"Daemon stream missing lifecycle events: {sorted(d_events)}",
    )
    perf_files = sorted((logs_dir.path / "perf").glob("*.jsonl"))
    perf_recs = _read_jsonl_records(perf_files[0]) if perf_files else []
    perf_tids = [str(r.get("task_id")) for r in perf_recs]
    check("daemon.boot" in perf_tids and "daemon.reload" in perf_tids, f"Missing daemon boot/reload perf traces: {perf_tids}")
    check("space.echo_tier0" not in perf_tids, f"Daemon duplicated CLI-owned task perf record: {perf_tids}")

    st_set = sig_probe.stat()
    sentinel_a = "a" * 64
    cached_doc = dict(read_json_dict(sig_cache_hp) or {})
    cached_doc["sig_probe.py"] = [st_set.st_mtime_ns, st_set.st_size, st_set.st_ino, sentinel_a]
    atomic_write_json(sig_cache_hp, cached_doc)

    def _boot_and_read_sig_entry() -> list[object]:
        d_probe = RuntimeDispatcher(
            workspace_root=ws_df, cache_dir=ws_df.join(".cache"), module_provider=provider,
            options=DispatcherHostOptions(is_daemon_host=True),
        )
        r_probe = FlightLogRouter(logs_dir, config=FlightLogConfig(enabled=False), daemon_boot_id="boot_cache")
        wd_probe = WorkspaceDaemon(
            workspace_root=ws_df, cache_dir=ws_df.join(".cache"), dispatcher=d_probe,
            flight_log_router=r_probe, daemon_boot_id="boot_cache",
        )
        wd_probe.request_shutdown(force=True)
        d_probe.shutdown(grace_ms=100)
        r_probe.close()
        after_doc = read_json_dict(sig_cache_hp) or {}
        entry = after_doc.get("sig_probe.py")
        check(isinstance(entry, list) and len(entry) == 4, f"Corrupted sig cache entry: {entry}")
        return list(entry)

    # 1. Settled file (-5s) with freshly written cache -> cache HIT
    e_settled = _boot_and_read_sig_entry()
    check(e_settled[3] == sentinel_a, f"Settled file ignored persisted core_sig_cache: {e_settled}")

    # 2. Cross-boot cache_mtime_ns Racy-Clean: file & cache share stale timestamp (-5s, outside now_ns-20ms window)
    sig_probe.write_text("SIG_VER = 2\n", encoding="utf-8")
    stale_racy_ns = time.time_ns() - 5_000_000_000
    os.utime(sig_probe, ns=(stale_racy_ns, stale_racy_ns))
    st_stale = sig_probe.stat()
    racy_cache_doc = dict(read_json_dict(sig_cache_hp) or {})
    racy_cache_doc["sig_probe.py"] = [st_stale.st_mtime_ns, st_stale.st_size, st_stale.st_ino, "b" * 64]
    atomic_write_json(sig_cache_hp, racy_cache_doc)
    os.utime(sig_cache_hp.path, ns=(stale_racy_ns, stale_racy_ns))
    e_racy_cache = _boot_and_read_sig_entry()
    check(e_racy_cache[3] != "b" * 64, f"Cross-boot cache_mtime_ns Racy-Clean failed to recompute live SHA-256: {e_racy_cache}")
    check(
        sig_cache_hp.path.stat().st_mtime_ns > stale_racy_ns + 1_000_000_000,
        "core_sig_cache.json mtime was not refreshed after cross-boot Racy-Clean recompute",
    )

    # 2b. Once refreshed cache mtime is ahead of file mtime, subsequent boot hits cache (no infinite re-hash)
    sentinel_c = "c" * 64
    post_doc = dict(read_json_dict(sig_cache_hp) or {})
    post_doc["sig_probe.py"] = [st_stale.st_mtime_ns, st_stale.st_size, st_stale.st_ino, sentinel_c]
    atomic_write_json(sig_cache_hp, post_doc)
    e_post = _boot_and_read_sig_entry()
    check(e_post[3] == sentinel_c, f"Refreshed core_sig_cache failed to settle after racy recompute: {e_post}")

    # 3. Current-scan fresh/future Racy-Clean (+5s symmetric margin immune to Windows NTFS fsync jitter)
    sig_probe.write_text("SIG_VER = 3\n", encoding="utf-8")
    fresh_ns = time.time_ns() + 5_000_000_000
    os.utime(sig_probe, ns=(fresh_ns, fresh_ns))
    st_fresh = sig_probe.stat()
    racy_fresh_doc = dict(read_json_dict(sig_cache_hp) or {})
    racy_fresh_doc["sig_probe.py"] = [st_fresh.st_mtime_ns, st_fresh.st_size, st_fresh.st_ino, "d" * 64]
    atomic_write_json(sig_cache_hp, racy_fresh_doc)
    e_fresh = _boot_and_read_sig_entry()
    check(e_fresh[3] != "d" * 64, f"Fresh-mtime Racy-Clean guard failed to recompute live SHA-256: {e_fresh}")


def _verify_loader_autodiscovery(suite_root: Path) -> None:
    ws_ld = HostPath(suite_root / "loader_autodiscovery_ws")
    ws_ld.path.mkdir(parents=True, exist_ok=True)
    loader = ProtectedModuleLoader(ws_ld)

    def _mk_mod(mod_id: str, entry_src: str, extra_files: Optional[dict[str, str]] = None) -> ModuleDescriptor:
        mdir = ws_ld.path / ".modules" / mod_id
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "module_entry.py").write_text(entry_src, encoding="utf-8")
        if extra_files:
            for rel_f, content in extra_files.items():
                (mdir / rel_f).write_text(content, encoding="utf-8")
        return ModuleDescriptor(module_id=ModuleId(mod_id), module_dir=HostPath(mdir))

    d_single = _mk_mod(
        "auto_one",
        "from core.surface.sdk import Module, TaskContext, task\n"
        "class AutoOne(Module):\n"
        "    id = 'auto_one'\n"
        "    @task\n"
        "    def hi(self, ctx: TaskContext) -> str:\n"
        "        return ctx.module_id.value\n",
    )
    art_one = loader.load_module_artifact(d_single)
    try:
        check(art_one.instance.module_id == ModuleId("auto_one") and len(art_one.instance.tasks()) == 1)
    finally:
        loader.cleanup_package(art_one.package_key)

    d_abc = _mk_mod(
        "auto_abc",
        "from abc import ABC\n"
        "from typing import Protocol\n"
        "from core.surface.sdk import Module, TaskContext, task\n"
        "class LocalProto(Protocol):\n"
        "    def to_yscb_module(self) -> object: ...\n"
        "class BaseMod(Module, ABC):\n"
        "    pass\n"
        "class ConcreteMod(BaseMod):\n"
        "    id = 'auto_abc'\n"
        "    @task\n"
        "    def ok(self, ctx: TaskContext) -> str:\n"
        "        return ctx.module_id.value\n",
    )
    art_abc = loader.load_module_artifact(d_abc)
    try:
        check(art_abc.instance.module_id == ModuleId("auto_abc"))
    finally:
        loader.cleanup_package(art_abc.package_key)

    d_imp = _mk_mod(
        "auto_imp",
        "from .helper_mod import ForeignMod\n"
        "from core.surface.sdk import Module\n"
        "_ = ForeignMod\n"
        "class LocalOnly(Module):\n"
        "    id = 'auto_imp'\n",
        extra_files={
            "helper_mod.py": "from core.surface.sdk import Module\nclass ForeignMod(Module):\n    id = 'foreign'\n"
        },
    )
    art_imp = loader.load_module_artifact(d_imp)
    try:
        check(art_imp.instance.module_id == ModuleId("auto_imp"))
    finally:
        loader.cleanup_package(art_imp.package_key)

    d_prec = _mk_mod(
        "auto_prec",
        "from core.surface.sdk import Module\n"
        "class IgnoredAuto(Module):\n"
        "    id = 'wrong_id'\n"
        "class ExplicitAuto(Module):\n"
        "    id = 'auto_prec'\n"
        "def create_module():\n"
        "    return ExplicitAuto().to_yscb_module()\n",
    )
    art_prec = loader.load_module_artifact(d_prec)
    try:
        check(art_prec.instance.module_id == ModuleId("auto_prec"))
    finally:
        loader.cleanup_package(art_prec.package_key)

    before_mods = set(sys.modules.keys())
    d_zero = _mk_mod("auto_zero", "X = 1\n")
    expect_yscb_code(lambda: loader.load_module_artifact(d_zero), ErrorCode.MODULE_DEGRADED)
    d_two = _mk_mod(
        "auto_two",
        "from core.surface.sdk import Module\n"
        "class A(Module):\n"
        "    id = 'a'\n"
        "class B(Module):\n"
        "    id = 'b'\n",
    )
    expect_yscb_code(lambda: loader.load_module_artifact(d_two), ErrorCode.MODULE_DEGRADED)
    leaked_keys = [k for k in sys.modules if k not in before_mods and ("auto_zero" in k or "auto_two" in k)]
    check(not leaked_keys, f"Failed auto-discovery leaked sys.modules keys: {leaked_keys}")


def _verify_run_process_contracts(suite_root: Path, venv_py: Path) -> None:
    rp_base = suite_root / "run_process_ws"
    proj_dir = rp_base / "repo"
    yscb_dir = proj_dir / ".yscb"
    sub_dir = proj_dir / "sub"
    outside_dir = rp_base / "outside"
    sub_dir.mkdir(parents=True, exist_ok=True)
    yscb_dir.mkdir(parents=True, exist_ok=True)
    outside_dir.mkdir(parents=True, exist_ok=True)

    rules = (
        *build_standard_mount_rules(
            host_dir=HostPath(proj_dir),
            yscb_root=HostPath(yscb_dir),
            project_root=HostPath(proj_dir),
        ),
        MountRule(scheme="virt.test"),
    )
    hub = VfsHub(UriMountTable(rules, providers={"virt.test": MemoryVfsProvider("virt.test")}))
    svc_factory = build_workspace_module_services_factory(HostPath(proj_dir), HostPath(yscb_dir), vfs_hub=hub)

    @dataclass(frozen=True, slots=True)
    class _RpReq:
        mode: str

    @dataclass(frozen=True, slots=True)
    class _RpOut:
        ok: bool
        rc: int
        stdout: str
        stderr: str
        timed_out: bool
        truncated: bool

    grandchild_pid_file = proj_dir / "grandchild.pid"
    cancel_gc_file = proj_dir / "cancel_gc.pid"
    preempt_gc_file = proj_dir / "preempt_gc.pid"

    class _RpTask(Task[_RpReq, _RpOut]):
        def __init__(self) -> None:
            self._meta = TaskMetadata(TaskId("rpmod.exec"), _RpReq, _RpOut, dispatch_mode=DispatchMode.HYBRID)

        @property
        def metadata(self) -> TaskMetadata[_RpReq, _RpOut]:
            return self._meta

        def run(self, req: _RpReq, ctx: TaskContext) -> _RpOut:
            if req.mode == "ok_env":
                code = (
                    "import os, sys; "
                    "sys.stdout.write(f'{os.getcwd()}|{os.environ.get(\"YSCB_TRACE\",\"\")}|{os.environ.get(\"CUSTOM_VAR\",\"\")}|{os.environ.get(\"PYTHONNOUSERSITE\",\"\")}|{bool(os.environ.get(\"PATH\"))}'); "
                    "sys.stderr.write('err_ok')"
                )
                res = ctx.run_process([sys.executable, "-c", code], cwd="project://sub", env={"CUSTOM_VAR": "hello"})
                assert_raises_val_error(lambda: ctx.run_process([sys.executable, "-c", "pass"], env={"_YSCB_SECRET": "1"}))
                expect_yscb_code(lambda: ctx.run_process([sys.executable, "-c", "pass"], cwd="virt.test://x"), ErrorCode.ACCESS_DENIED)
                expect_yscb_code(lambda: ctx.run_process([sys.executable, "-c", "pass"], cwd=HostPath(outside_dir)), ErrorCode.ACCESS_DENIED)
                expect_yscb_code(lambda: ctx.run_process([sys.executable, "-c", "pass"], cwd="yscb://"), ErrorCode.ACCESS_DENIED)
                return _RpOut(res.ok, res.returncode, res.stdout, res.stderr, res.timed_out, res.truncated)
            if req.mode == "nonzero":
                res = ctx.run_process([sys.executable, "-c", "import sys; sys.exit(7)"])
                return _RpOut(res.ok, res.returncode, res.stdout, res.stderr, res.timed_out, res.truncated)
            if req.mode == "truncate":
                res = ctx.run_process(
                    [sys.executable, "-c", "import sys; sys.stdout.write('A'*160000); sys.stderr.write('B'*160000)"],
                    max_output_bytes=128,
                )
                return _RpOut(res.ok, res.returncode, res.stdout, res.stderr, res.timed_out, res.truncated)
            if req.mode in ("timeout_tree", "cancel_tree", "preempt_tree"):
                pid_out = (
                    grandchild_pid_file
                    if req.mode == "timeout_tree"
                    else (cancel_gc_file if req.mode == "cancel_tree" else preempt_gc_file)
                )
                tmp_out = pid_out.with_suffix(".tmp")
                spawner = (
                    "import pathlib, subprocess, sys, time; "
                    "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                    f"t = pathlib.Path({str(tmp_out)!r}); "
                    "t.write_text(str(p.pid), encoding='utf-8'); "
                    f"t.replace(pathlib.Path({str(pid_out)!r})); "
                    "time.sleep(30)"
                )
                res = ctx.run_process([sys.executable, "-c", spawner], timeout_sec=1.5 if req.mode == "timeout_tree" else 10.0)
                return _RpOut(res.ok, res.returncode, res.stdout, res.stderr, res.timed_out, res.truncated)
            raise ValueError(req.mode)

    class _RpMod(YscbModule):
        @property
        def module_id(self) -> ModuleId:
            return ModuleId("rpmod")

        def tasks(self) -> Sequence[BoundTask]:
            return (_RpTask(),)

    disp = RuntimeDispatcher(
        workspace_root=HostPath(yscb_dir),
        cache_dir=HostPath(yscb_dir / ".cache"),
        module_provider=ManifestModuleProvider(HostPath(yscb_dir), HostPath(venv_py)),
        options=DispatcherHostOptions(in_memory_modules=(_RpMod(),), module_services_factory=svc_factory),
    )
    try:
        out_ok = disp.invoke(
            InvokeRequest(
                TaskId("rpmod.exec"),
                {"mode": "ok_env"},
                HostPath(yscb_dir),
                HostPath(proj_dir),
                caller_env={"YSCB_TRACE": "tr42"},
            ),
            output_type=_RpOut,
        )
        check(out_ok.ok and out_ok.value is not None and out_ok.value.ok and out_ok.value.stderr == "err_ok", f"run_process ok_env failed: {out_ok}")
        parts = out_ok.value.stdout.split("|")
        check(
            len(parts) == 5 and HostPath(parts[0]) == HostPath(sub_dir) and parts[1:] == ["tr42", "hello", "1", "True"],
            f"Unexpected isolated env/cwd output: {parts}",
        )

        out_nz = disp.invoke(InvokeRequest(TaskId("rpmod.exec"), {"mode": "nonzero"}, HostPath(yscb_dir), HostPath(proj_dir)), output_type=_RpOut)
        check(out_nz.ok and out_nz.value is not None and (not out_nz.value.ok) and out_nz.value.rc == 7 and not out_nz.value.timed_out)

        out_tr = disp.invoke(InvokeRequest(TaskId("rpmod.exec"), {"mode": "truncate"}, HostPath(yscb_dir), HostPath(proj_dir)), output_type=_RpOut)
        check(
            out_tr.ok and out_tr.value is not None and out_tr.value.ok and out_tr.value.truncated
            and len(out_tr.value.stdout) == 128 and len(out_tr.value.stderr) == 128,
            f"Bounded pipe truncation failed: {out_tr}",
        )

        out_to = disp.invoke(InvokeRequest(TaskId("rpmod.exec"), {"mode": "timeout_tree"}, HostPath(yscb_dir), HostPath(proj_dir)), output_type=_RpOut)
        check(
            out_to.ok and out_to.value is not None and (not out_to.value.ok) and out_to.value.timed_out and out_to.value.rc == -1,
            f"Expected timed_out ProcessResult: {out_to}",
        )
        check(grandchild_pid_file.is_file(), "Timeout test must unconditionally verify spawned grandchild cleanup")
        gc_pid = int(grandchild_pid_file.read_text(encoding="utf-8").strip())
        wait_until(lambda: not is_process_alive(gc_pid), timeout_sec=3.0)

        for mode_nm, pid_f, is_preempt, exp_code in (
            ("cancel_tree", cancel_gc_file, False, ErrorCode.TASK_CANCELLED),
            ("preempt_tree", preempt_gc_file, True, ErrorCode.TASK_PREEMPTED),
        ):
            c_tok = CancellationToken()

            def _trigger_tok(target_f: Path = pid_f, tok: CancellationToken = c_tok, pre: bool = is_preempt) -> None:
                wait_until(lambda: target_f.is_file() and bool(target_f.read_text(encoding="utf-8").strip()), timeout_sec=5.0)
                tok.cancel(reason="abort_proc_tree", preempted=pre)

            t_can = threading.Thread(target=_trigger_tok, daemon=True)
            t_can.start()
            out_can = disp.invoke(
                InvokeRequest(TaskId("rpmod.exec"), {"mode": mode_nm}, HostPath(yscb_dir), HostPath(proj_dir)),
                output_type=_RpOut,
                cancel_token=c_tok,
            )
            t_can.join(timeout=3.0)
            check(
                not out_can.ok and out_can.error is not None and out_can.error.code == exp_code,
                f"Expected {exp_code} on run_process {mode_nm}: {out_can}",
            )
            check(pid_f.is_file(), f"Expected grandchild pid file for {mode_nm}")
            c_gc_pid = int(pid_f.read_text(encoding="utf-8").strip())
            wait_until(lambda p=c_gc_pid: not is_process_alive(p), timeout_sec=3.0)
        check(ProcessResult(0, "", "", 1.0).ok and not ProcessResult(0, "", "", 1.0, timed_out=True).ok)
    finally:
        disp.shutdown(grace_ms=300)


def run_runtime_daemon_suite(tmp_root: Path, venv_py: Path) -> None:
    """Run domain and live integration checks for core.execution.runtime and core.execution.daemon."""
    suite_root = tmp_root / "domain_runtime_daemon"
    suite_root.mkdir(parents=True, exist_ok=True)
    try:
        log("[RUNTIME-DAEMON] Verifying COALESCE single-flight, priority elevation, and cancel survival...")
        _verify_coalesce_and_reentrancy(suite_root)
        log("[RUNTIME-DAEMON] Verifying COALESCE edge cases, degradation, reentrancy, and PREEMPT...")
        _verify_coord_edge_cases(suite_root)
        log("[RUNTIME-DAEMON] Verifying queued COALESCE leader cancel and short-timeout survival...")
        _verify_queued_coalesce_leader_cancel_and_timeout(suite_root)
        log("[RUNTIME-DAEMON] Verifying Step 5 QUIESCE draining exemption and cancel deadline semantics...")
        _verify_step5_quiesce_draining_no_deadlock(suite_root)
        log("[RUNTIME-DAEMON] Verifying Step 5 cycle error, CrossProcessLockPaths, and cross-proc SERIALIZE...")
        _verify_step5_cycle_and_cross_proc_reentrancy(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying Global QUIESCE barrier, lease auto-heal, and reload deferral...")
        _verify_global_quiesce_and_controls(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying diagnostics isolation, core diff SHA-256, and handoff...")
        _verify_core_diff_handoff_and_diagnostics(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying IdleTtlMonitor, PeriodicTriggerLoop, and Tier1WorkerPool stop...")
        _verify_ttl_periodic_and_worker_pool_stop(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying WorkspaceDaemon shell controls, status snapshot, and watcher resync...")
        _verify_daemon_shell_and_controls(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying watcher poll cadence and Tier 1 env lease DI callbacks...")
        _verify_watcher_poll_interval_and_env_lease_di(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying module log correlation, single-owner flight matrix, and slow/error diagnostics...")
        _verify_observability_logs_and_single_owner(suite_root)
        log("[RUNTIME-DAEMON] Verifying Tier 1 profiler subtree merge, profile_mem propagation, and fail-open wire...")
        _verify_tier1_profiler_merge_mem_and_fail_open(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying daemon Stream 1 lifecycle logs, profiler_summary, and core_sig_cache...")
        _verify_daemon_flight_logs_ring_summary_and_core_sig_cache(suite_root, venv_py)
        log("[RUNTIME-DAEMON] Verifying ProtectedModuleLoader auto-discovery and TaskContext.run_process...")
        _verify_loader_autodiscovery(suite_root)
        _verify_run_process_contracts(suite_root, venv_py)
        log("[RUNTIME-DAEMON] All checks passed.")
    finally:
        force_reap_tmp_root_orphans(suite_root)
        assert_zero_live_stage_orphans(suite_root)


__all__ = ("run_runtime_daemon_suite",)
