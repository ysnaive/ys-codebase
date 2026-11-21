"""Domain tests for core.execution.runtime and core.execution.daemon."""

from __future__ import annotations

from dataclasses import dataclass, fields
import os
from pathlib import Path
import threading
import time
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
    wait_for_handoff_daemon_endpoint,
)
from core.execution.runtime import (
    BoundTask,
    CallPropagationContext,
    ClientRoutingPolicy,
    ConcurrencyMode,
    DispatchMode,
    DispatcherHostOptions,
    ExecutionPriority,
    InvokeRequest,
    LifecycleReloadGate,
    MODULE_INSTALLED_EVENT_ID,
    MODULE_REMOVING_EVENT_ID,
    ModuleDescriptor,
    PeriodicScheduleSpec,
    RuntimeDispatcher,
    Task,
    TaskContext,
    TaskMetadata,
    TaskOutcome,
    WORKSPACE_RELOADED_EVENT_ID,
    YscbModule,
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
    HostPath,
    ModuleId,
    TaskId,
)
from tests._boot import FileConfigView, build_dispatcher_for_workspace
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
                nested_out = ctx.invoke_typed(self._serial_meta, _CoordReqDto(eq_key="inner"))
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
        "        sub = ctx.invoke_task(TaskId(target), {'tag': req.tag})\n"
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
        wake_long is not None and wake_after_short is not None and wake_after_short >= wake_long - 1e-6,
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
    )
    actual_prop_fields = tuple(f.name for f in fields(CallPropagationContext))
    check(
        actual_prop_fields == expected_prop_fields and len(actual_prop_fields) == 10,
        f"CallPropagationContext 10-field contract mismatch: {actual_prop_fields}",
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


def run_runtime_daemon_suite(tmp_root: Path, venv_py: Path) -> None:
    """Run domain and live integration checks for core.execution.runtime and core.execution.daemon."""
    suite_root = tmp_root / "domain_runtime_daemon"
    suite_root.mkdir(parents=True, exist_ok=True)
    try:
        log("[RUNTIME-DAEMON] Verifying COALESCE single-flight, priority elevation, and cancel survival...")
        _verify_coalesce_and_reentrancy(suite_root)
        log("[RUNTIME-DAEMON] Verifying COALESCE edge cases, degradation, reentrancy, and PREEMPT...")
        _verify_coord_edge_cases(suite_root)
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
        log("[RUNTIME-DAEMON] All checks passed.")
    finally:
        force_reap_tmp_root_orphans(suite_root)
        assert_zero_live_stage_orphans(suite_root)


__all__ = ("run_runtime_daemon_suite",)
