"""Verification suite for core.surface.sdk declarative DSL, lifecycle bridging, and YscbClient."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
import inspect
import json
from pathlib import Path
from typing import Annotated, ClassVar, Optional, Sequence, get_args, get_type_hints

import core.surface.sdk as sdk
from core.execution.event import EventOrdering, EventSubscriptionSpec
from core.execution.runtime import (
    CliBindingSpec,
    PeriodicScheduleSpec,
    Task,
    TaskExposure,
    TaskMetadata,
    TaskRouteSpec,
)
from core.foundation import ErrorCode, EventId, HostPath, ModuleId, TaskId
from core.surface.sdk import (
    Arg,
    CancellationToken,
    ConcurrencyMode,
    DispatchMode,
    Empty,
    EventMetadata,
    ExitCodeProvider,
    HumanRenderable,
    InMemoryModule,
    Module,
    ModuleEnv,
    Option,
    ProgressEvent,
    SecurityTier,
    TaskContext,
    TaskGroup,
    TaskOutcome,
    YscbClient,
    YscbModule,
    define_event,
    format_output,
    on_event,
    periodic,
    task,
)
from tests._harness import assert_raises_val_error, check, expect_yscb_code, log


@dataclass(frozen=True, slots=True)
class _EchoIn:
    tag: str


@dataclass(frozen=True, slots=True)
class _EchoOut:
    text: str
    cwd: str = ""
    trace_env: str = ""


@dataclass(frozen=True, slots=True)
class _CliIn:
    target: Annotated[str, Arg(summary="Target path", name="target")]
    verbose: Annotated[bool, Option(short="-v", summary="Verbose mode", long_name="--verbose")] = False
    count: Annotated[int, Option(short="n", summary="Item count")] = 1


@dataclass(frozen=True, slots=True)
class _PairOut:
    target: str
    verbose: bool
    count: int


@dataclass(frozen=True, slots=True)
class _EvItem:
    kind: str
    count: int


@dataclass(frozen=True, slots=True)
class _MergedEvIn:
    total: int
    kinds: tuple[str, ...]


class _ToxicStrError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("toxic __str__ failure")


def _append_line(path: Path, line: str) -> None:
    prev = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(prev + line + "\n", encoding="utf-8")


def _merge_ev_items(items: Sequence[_EvItem]) -> Optional[_MergedEvIn]:
    if not items:
        return None
    return _MergedEvIn(total=sum(it.count for it in items), kinds=tuple(it.kind for it in items))


def _first_ev_item(items: Sequence[_EvItem]) -> Optional[_EvItem]:
    return items[0] if items else None


_UNORDERED_EV: EventMetadata[_EvItem] = define_event(
    "emitter.batch_ev", _EvItem, ordered=False, description="Batched item event"
)
_ORDERED_EV: EventMetadata[_EvItem] = define_event(
    "emitter.imm_ev", _EvItem, ordered=True, description="Immediate item event"
)
_WEAK_PING_EV: EventMetadata[Empty] = define_event("emitter.weak_ping")


class _TextOnlyOut:
    def __init__(self, text: str) -> None:
        self._text = text

    def render_text(self) -> str:
        return self._text


class _ExitOnlyPlain:
    def __init__(self, code: int) -> None:
        self._code = code

    def exit_code(self) -> int:
        return self._code


@dataclass(frozen=True, slots=True)
class _ExitOnlyDto:
    status: str
    code: int

    def exit_code(self) -> int:
        return self.code


@dataclass(frozen=True, slots=True)
class _DualOut:
    summary: str
    code: int

    def render_text(self) -> str:
        return f"DUAL:{self.summary}"

    def exit_code(self) -> int:
        return self.code


class _AlphaGroup(TaskGroup):
    @task("alpha ping", summary="Alpha ping")
    def alpha_ping(self, ctx: TaskContext) -> _EchoOut:
        return _EchoOut(text="alpha", cwd=str(ctx.caller_cwd))

    @periodic(5.0, enabled_config_key="alpha.en", interval_config_key="alpha.iv")
    @on_event(_UNORDERED_EV, payload_filter={"kind": ("a",)}, mapper=_merge_ev_items)
    @task(name="combo_alpha", summary="Combo task", lock="combo_lk")
    def combo_alpha(self, req: _MergedEvIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=f"combo:{req.total}")


class _BetaGroup(TaskGroup):
    @task(name="combo_beta", summary="Combo task", lock="combo_lk")
    @on_event(_UNORDERED_EV, payload_filter={"kind": ("a",)}, mapper=_merge_ev_items)
    @periodic(5.0, enabled_config_key="alpha.en", interval_config_key="alpha.iv")
    def combo_beta(self, ctx: TaskContext, req: _MergedEvIn) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=f"combo:{req.total}")

    @task("beta gated", security=SecurityTier.GATED)
    def gated_op(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=f"gated:{req.tag}")


class _ShowcaseModule(Module):
    id: ClassVar[str] = "demo"
    groups: ClassVar[tuple[type[TaskGroup], ...]] = (_AlphaGroup, _BetaGroup)

    @task
    def ping(self, ctx: TaskContext) -> None:
        _ = ctx

    @task(
        "demo run",
        aliases=("r",),
        summary="Explicit CLI",
        dispatch_mode=DispatchMode.DAEMON_ONLY,
        security=SecurityTier.CONDITIONAL,
        lock="demo_lock",
        timeout_ms=1500,
    )
    def explicit_cli(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        return _EchoOut(text=f"cli:{req.tag}", cwd=str(ctx.caller_cwd))

    @task(("demo", "cli"))
    def doc_summary_task(self, ctx: TaskContext, req: _CliIn) -> _PairOut:
        """First docstring line.

        Ignored second paragraph.
        """
        _ = ctx
        return _PairOut(target=req.target, verbose=req.verbose, count=req.count)

    @task("demo nodoc")
    def fallback_summary_task(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=req.tag)

    @on_event(_ORDERED_EV, payload_filter={"kind": ("a", "b")}, mapper=_merge_ev_items)
    @task(name="ev_above")
    def ev_above(self, req: _MergedEvIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=f"ev:{req.total}")

    @task(name="ev_below")
    @on_event(_ORDERED_EV, payload_filter={"kind": ("a", "b")}, mapper=_merge_ev_items)
    def ev_below(self, req: _MergedEvIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=f"ev:{req.total}")

    @periodic(12.5, enabled_config_key="sync.enabled", interval_config_key="sync.interval")
    @task
    def per_above(self, ctx: TaskContext) -> None:
        _ = ctx

    @task
    @periodic(12.5, enabled_config_key="sync.enabled", interval_config_key="sync.interval")
    def per_below(self, ctx: TaskContext) -> None:
        _ = ctx

    @on_event("ext.weak_ping")
    def weak_ev_no_mapper(self, ctx: TaskContext) -> None:
        _ = ctx


class _AbstractBaseMod(Module, ABC):
    @abstractmethod
    def abstract_hook(self) -> str: ...

    @task
    def inherited_ping(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="from_base")

    @task
    def dropped_ping(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="base_only")


class _NoIdAbstractMod(Module, ABC):
    @task
    def idle(self, ctx: TaskContext) -> None:
        _ = ctx


class _ConcreteChildMod(_AbstractBaseMod):
    id: ClassVar[str] = "child"

    def abstract_hook(self) -> str:
        return "implemented"

    def dropped_ping(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="plain_override")


def _raise_toxic_after_append(path: Path, line: str) -> None:
    _append_line(path, line)
    raise _ToxicStrError()


class _LifoGroupOne(TaskGroup):
    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "lifo.log"
        _append_line(self.log_path, "g1:init")
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "g1:closer"))

    def on_warmup(self, env: ModuleEnv) -> None:
        target = env.workspace_root.path / "lifo.log"
        _append_line(target, "g1:warmup")
        env.register_closer(lambda: _append_line(target, "g1:warmup_closer"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "g1:close")


class _LifoGroupTwo(TaskGroup):
    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "lifo.log"
        _append_line(self.log_path, "g2:init")
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "g2:closer"))

    def on_warmup(self, env: ModuleEnv) -> None:
        target = env.workspace_root.path / "lifo.log"
        _append_line(target, "g2:warmup")
        env.register_closer(lambda: _append_line(target, "g2:warmup_closer"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "g2:close")


class _LifoModule(Module):
    id: ClassVar[str] = "lifo"
    groups: ClassVar[tuple[type[TaskGroup], ...]] = (_LifoGroupOne, _LifoGroupTwo)

    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "lifo.log"
        _append_line(self.log_path, "mod:init")
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "mod:closer"))

    def on_warmup(self, env: ModuleEnv) -> None:
        target = env.workspace_root.path / "lifo.log"
        _append_line(target, "mod:warmup")
        env.register_closer(lambda: _append_line(target, "mod:warmup_closer"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "mod:close")

    @task
    def ping(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="lifo_ok")


class _ToxicCloserGroup(TaskGroup):
    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "toxic.log"
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "tg:closer"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _raise_toxic_after_append(self.log_path, "tg:close_boom")


class _ToxicCloserModule(Module):
    id: ClassVar[str] = "toxic"
    groups: ClassVar[tuple[type[TaskGroup], ...]] = (_ToxicCloserGroup,)

    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "toxic.log"
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "tm:closer_ok"))
        env.register_closer(lambda: _raise_toxic_after_append(target, "tm:closer_boom"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "tm:close")

    @task
    def ping(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="toxic_ready")


class _FailingInitGroup(TaskGroup):
    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "degraded.log"
        _append_line(self.log_path, "bad_grp:init")
        raise RuntimeError("group init exploded")

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "bad_grp:close")


class _FailingInitModule(Module):
    id: ClassVar[str] = "badinit"
    groups: ClassVar[tuple[type[TaskGroup], ...]] = (_FailingInitGroup,)

    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "degraded.log"
        _append_line(self.log_path, "bad_mod:init")
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "bad_mod:rollback_closer"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "bad_mod:close")

    @task
    def work(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="unreachable")


class _HealthySiblingModule(Module):
    id: ClassVar[str] = "healthy"

    def __init__(self) -> None:
        self.log_path: Optional[Path] = None

    def on_init(self, env: ModuleEnv) -> None:
        self.log_path = env.workspace_root.path / "healthy.log"
        _append_line(self.log_path, "healthy:init")
        target = self.log_path
        env.register_closer(lambda: _append_line(target, "healthy:closer"))

    def on_close(self) -> None:
        if self.log_path is not None:
            _append_line(self.log_path, "healthy:close")

    @task
    def ping(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="healthy_ok")

    @task
    def dual(self, req: _EchoIn, ctx: TaskContext) -> _DualOut:
        _ = ctx
        return _DualOut(summary=req.tag, code=7)


_SUB_TYPED_META: TaskMetadata[_EchoIn, _EchoOut] = TaskMetadata(
    TaskId("subscriber.echo"),
    _EchoIn,
    _EchoOut,
)


class _EmitterModule(Module):
    id: ClassVar[str] = "emitter"

    @task
    def fire(self, ctx: TaskContext) -> _EchoOut:
        ctx.emit(_UNORDERED_EV, _EvItem(kind="skip", count=1))
        ctx.emit(_UNORDERED_EV, _EvItem(kind="keep", count=10))
        ctx.emit(_UNORDERED_EV, _EvItem(kind="keep", count=25))
        ctx.emit_imm(_ORDERED_EV, _EvItem(kind="imm", count=7), strict=True)
        imm_inline = (ctx.workspace_root.path / "ev_imm.json").read_text(encoding="utf-8")
        ctx.emit(_WEAK_PING_EV, Empty())
        return _EchoOut(text=f"imm_inline:{imm_inline.strip()}")

    @task
    def call_sub(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        sub_one = ctx.invoke_task("subscriber.echo", _EchoIn(tag=req.tag), output_type=_EchoOut)
        sub_two = ctx.invoke_typed(_SUB_TYPED_META, _EchoIn(tag=f"{req.tag}:typed"))
        check(sub_one.ok and sub_one.value is not None)
        check(sub_two.ok and sub_two.value is not None)
        return _EchoOut(
            text=f"{sub_one.value.text}|{sub_two.value.text}",
            cwd=sub_one.value.cwd,
            trace_env=sub_one.value.trace_env,
        )

    @task
    def slow_progress(self, ctx: TaskContext) -> _EchoOut:
        ctx.report_progress(ProgressEvent(phase="work", completed=1, total=2, message="step1"))
        ctx.cancel_token.raise_if_cancelled()
        ctx.report_progress(ProgressEvent(phase="work", completed=2, total=2, message="cancel_now"))
        ctx.cancel_token.raise_if_cancelled()
        return _EchoOut(text="completed")


class _SubscriberModule(Module):
    id: ClassVar[str] = "subscriber"

    @task
    def echo(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        return _EchoOut(
            text=f"sub:{req.tag}",
            cwd=str(ctx.caller_cwd),
            trace_env=ctx.caller_env.get("YSCB_TRACE", ""),
        )

    @on_event(_UNORDERED_EV, payload_filter={"kind": ("keep",)}, mapper=_merge_ev_items)
    def on_kept(self, req: _MergedEvIn, ctx: TaskContext) -> None:
        _append_line(ctx.workspace_root.path / "ev_kept.log", f"{req.total}:{','.join(req.kinds)}")

    @on_event(_ORDERED_EV, mapper=_first_ev_item)
    def on_imm(self, req: _EvItem, ctx: TaskContext) -> None:
        (ctx.workspace_root.path / "ev_imm.json").write_text(f"{req.kind}:{req.count}", encoding="utf-8")

    @on_event("emitter.weak_ping")
    def on_weak(self, ctx: TaskContext) -> None:
        (ctx.workspace_root.path / "ev_weak.txt").write_text("weak_ok", encoding="utf-8")


def _verify_facade_and_zero_leak() -> None:
    expected_exports = frozenset(
        {
            "Arg",
            "CancellationToken",
            "ConcurrencyMode",
            "DispatchMode",
            "Empty",
            "EventMetadata",
            "ExitCodeProvider",
            "HostPath",
            "HumanRenderable",
            "InMemoryModule",
            "Module",
            "ModuleEnv",
            "Option",
            "ProgressEvent",
            "SecurityTier",
            "TaskContext",
            "TaskGroup",
            "TaskOutcome",
            "YscbClient",
            "YscbModule",
            "define_event",
            "format_output",
            "on_event",
            "periodic",
            "task",
        }
    )
    check(len(sdk.__all__) == 25)
    check(len(set(sdk.__all__)) == 25)
    check(frozenset(sdk.__all__) == expected_exports)
    tg_members = dict(inspect.getmembers_static(TaskGroup))
    check("prefix" not in tg_members)
    sdk_members = dict(inspect.getmembers_static(sdk))
    for leaked in ("BoundTask", "_DeclarativeMeta", "_DecoratedMethod", "_SdkStateRegistry", "_SdkBoundTask", "_SdkYscbModule"):
        check(leaked not in sdk.__all__)
        check(leaked not in sdk_members)
    check(all(sym in sdk_members for sym in expected_exports))
    check(TaskOutcome is not None and YscbModule is not None)


class _StubTaskContext(TaskContext):
    def __init__(self, ws: HostPath) -> None:
        self._ws = ws
        self._tok = CancellationToken()

    @property
    def workspace_root(self) -> HostPath:
        return self._ws

    @property
    def caller_cwd(self) -> HostPath:
        return self._ws

    @property
    def caller_env(self) -> dict[str, str]:
        return {}

    @property
    def cancel_token(self) -> CancellationToken:
        return self._tok

    @property
    def effective_priority(self) -> object:
        raise NotImplementedError

    def emit(self, event_meta: EventMetadata[object], payload: object) -> None:
        _ = (event_meta, payload)

    def emit_imm(self, event_meta: EventMetadata[object], payload: object, *, strict: bool = False) -> None:
        _ = (event_meta, payload, strict)

    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: Optional[type[object]] = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[object] = None,
    ) -> TaskOutcome[object]:
        _ = (task_id, input_obj, output_type, target_workspace, routing_policy)
        return TaskOutcome(ok=False)

    def report_progress(self, progress: ProgressEvent) -> None:
        _ = progress


def _require_task_meta(bt: object) -> TaskMetadata[object, object]:
    check(isinstance(bt, Task))
    return bt.metadata


def _verify_declarative_metadata_and_stacking(ws: HostPath) -> None:
    mod = _ShowcaseModule()
    y_mod = mod.to_yscb_module()
    check(isinstance(y_mod, YscbModule))
    check(y_mod.module_id == ModuleId("demo"))
    tasks_by_id = {bt.task_id.value: bt for bt in y_mod.tasks()}
    expected_ids = {
        "demo.ping",
        "demo.explicit_cli",
        "demo.doc_summary_task",
        "demo.fallback_summary_task",
        "demo.ev_above",
        "demo.ev_below",
        "demo.per_above",
        "demo.per_below",
        "demo.weak_ev_no_mapper",
        "demo.alpha_ping",
        "demo.combo_alpha",
        "demo.combo_beta",
        "demo.gated_op",
    }
    check(set(tasks_by_id) == expected_ids)

    m_ping = _require_task_meta(tasks_by_id["demo.ping"])
    check(m_ping.exposure == TaskExposure.SDK_ONLY and m_ping.cli is None)
    check(m_ping.input_type is Empty and m_ping.output_type is Empty)
    check(m_ping.dispatch_mode == DispatchMode.HYBRID and m_ping.security_tier == SecurityTier.SAFE)
    check(m_ping.concurrency_mode == ConcurrencyMode.PARALLEL)

    m_cli = _require_task_meta(tasks_by_id["demo.explicit_cli"])
    check(m_cli.exposure == TaskExposure.CLI_AND_SDK)
    check(m_cli.cli == CliBindingSpec(("demo", "run"), "Explicit CLI", ("r",)))
    check(m_cli.dispatch_mode == DispatchMode.DAEMON_ONLY and m_cli.security_tier == SecurityTier.CONDITIONAL)
    check(m_cli.resource_key == "demo_lock" and m_cli.concurrency_mode == ConcurrencyMode.SERIALIZE)
    check(m_cli.timeout_ms == 1500)

    m_doc = _require_task_meta(tasks_by_id["demo.doc_summary_task"])
    check(m_doc.cli == CliBindingSpec(("demo", "cli"), "First docstring line.", ()))
    check(m_doc.input_type is _CliIn and m_doc.output_type is _PairOut)

    m_nodoc = _require_task_meta(tasks_by_id["demo.fallback_summary_task"])
    check(m_nodoc.cli == CliBindingSpec(("demo", "nodoc"), "Execute demo.fallback_summary_task", ()))

    ev_a_bt, ev_b_bt = tasks_by_id["demo.ev_above"], tasks_by_id["demo.ev_below"]
    check(replace(ev_a_bt.route_spec, task_id=TaskId("demo.cmp")) == replace(ev_b_bt.route_spec, task_id=TaskId("demo.cmp")))
    m_ev_a, m_ev_b = _require_task_meta(ev_a_bt), _require_task_meta(ev_b_bt)
    check(replace(m_ev_a, task_id=TaskId("demo.cmp")) == replace(m_ev_b, task_id=TaskId("demo.cmp")))
    check(len(m_ev_a.subscriptions) == 1 and m_ev_a.subscriptions[0].event_id == _ORDERED_EV.event_id)
    check(m_ev_a.subscriptions[0].payload_filter == {"kind": ("a", "b")})

    p_a_bt, p_b_bt = tasks_by_id["demo.per_above"], tasks_by_id["demo.per_below"]
    check(replace(p_a_bt.route_spec, task_id=TaskId("demo.cmp")) == replace(p_b_bt.route_spec, task_id=TaskId("demo.cmp")))
    m_p_a, m_p_b = _require_task_meta(p_a_bt), _require_task_meta(p_b_bt)
    check(replace(m_p_a, task_id=TaskId("demo.cmp")) == replace(m_p_b, task_id=TaskId("demo.cmp")))
    check(m_p_a.periodic == PeriodicScheduleSpec(12.5, "sync.enabled", "sync.interval"))

    c_a_bt, c_b_bt = tasks_by_id["demo.combo_alpha"], tasks_by_id["demo.combo_beta"]
    check(replace(c_a_bt.route_spec, task_id=TaskId("demo.cmp")) == replace(c_b_bt.route_spec, task_id=TaskId("demo.cmp")))
    check(replace(_require_task_meta(c_a_bt), task_id=TaskId("demo.cmp")) == replace(_require_task_meta(c_b_bt), task_id=TaskId("demo.cmp")))

    weak_bt = tasks_by_id["demo.weak_ev_no_mapper"]
    m_weak = _require_task_meta(weak_bt)
    check(m_weak.exposure == TaskExposure.INTERNAL_TRIGGER and m_weak.input_type is Empty)
    check(len(m_weak.subscriptions) == 1 and isinstance(m_weak.subscriptions[0], EventSubscriptionSpec))
    check(m_weak.subscriptions[0].event_id == EventId("ext.weak_ping") and m_weak.subscriptions[0].payload_type is None)
    check(weak_bt.map_subscription_batch(EventId("ext.weak_ping"), [{"k": 1}]) == (False, {}))
    check(weak_bt.map_subscription_batch(EventId("ext.weak_ping"), []) == (True, {}))

    cli_hints = get_type_hints(_CliIn, include_extras=True)
    check(get_args(cli_hints["target"])[1] == Arg(summary="Target path", name="target"))
    check(get_args(cli_hints["verbose"])[1] == Option(short="-v", summary="Verbose mode", long_name="--verbose"))
    check(get_args(cli_hints["count"])[1] == Option(short="n", summary="Item count"))
    assert_raises_val_error(lambda: Arg(name="-bad"))
    assert_raises_val_error(lambda: Arg(name="bad name"))
    assert_raises_val_error(lambda: Option(short="--v"))
    assert_raises_val_error(lambda: Option(short="ab"))
    assert_raises_val_error(lambda: Option(long_name="---"))

    check(_WEAK_PING_EV.payload_type is Empty and _WEAK_PING_EV.ordering == EventOrdering.UNORDERED)
    check(_ORDERED_EV.payload_type is _EvItem and _ORDERED_EV.ordering == EventOrdering.ORDERED)
    assert_raises_val_error(lambda: define_event("", Empty))
    assert_raises_val_error(lambda: define_event("bad.none", type(None)))

    stub_ctx = _StubTaskContext(ws)
    check(isinstance(ev_a_bt.route_spec, TaskRouteSpec))
    check(mod.ping(stub_ctx) is None and _ShowcaseModule.ping(mod, stub_ctx) is None)
    check(mod.fallback_summary_task(_EchoIn(tag="direct"), stub_ctx) == _EchoOut(text="direct"))
    check(_ShowcaseModule.fallback_summary_task(mod, _EchoIn(tag="unbound"), stub_ctx) == _EchoOut(text="unbound"))
    check(tasks_by_id["demo.ping"].execute_encoded({}, stub_ctx) == {})

    child_tasks = {bt.task_id.value for bt in _ConcreteChildMod().to_yscb_module().tasks()}
    check(child_tasks == {"child.inherited_ping"})
    check(_ConcreteChildMod().dropped_ping(stub_ctx) == _EchoOut(text="plain_override"))


def _verify_compile_time_validation(ws: HostPath) -> None:
    def _blank_id() -> None:
        class _BadBlank(Module):
            id = "   "

    def _invalid_id() -> None:
        class _BadFmt(Module):
            id = "Bad Module"

    def _dup_task_id() -> None:
        class _BadDupId(Module):
            id = "dup"

            @task(name="same")
            def first_op(self, ctx: TaskContext) -> None:
                _ = ctx

            @task(name="same")
            def second_op(self, ctx: TaskContext) -> None:
                _ = ctx

    def _dup_cli_path() -> None:
        class _BadDupCli(Module):
            id = "dupcli"

            @task("grp act")
            def first_cli(self, ctx: TaskContext) -> None:
                _ = ctx

            @task(("grp", "act"))
            def second_cli(self, ctx: TaskContext) -> None:
                _ = ctx

    def _alias_collision_with_group() -> None:
        class _BadAliasMod(Module):
            id = "aliasmod"
            groups = (_AlphaGroup,)

            @task("alpha x", aliases=("ping",))
            def clash(self, ctx: TaskContext) -> None:
                _ = ctx

    def _gated_with_event() -> None:
        class _BadGatedEv(Module):
            id = "gatedev"

            @on_event(_WEAK_PING_EV)
            @task(security=SecurityTier.GATED)
            def blocked(self, ctx: TaskContext) -> None:
                _ = ctx

    def _gated_with_periodic() -> None:
        class _BadGatedPer(Module):
            id = "gatedper"

            @task(security=SecurityTier.GATED)
            @periodic(5.0)
            def blocked(self, ctx: TaskContext) -> None:
                _ = ctx

    def _cold_with_event() -> None:
        class _BadColdEv(Module):
            id = "coldev"

            @task(dispatch_mode=DispatchMode.COLD_ONLY)
            @on_event(_WEAK_PING_EV)
            def blocked(self, ctx: TaskContext) -> None:
                _ = ctx

    def _cold_with_periodic() -> None:
        class _BadColdPer(Module):
            id = "coldper"

            @periodic(5.0)
            @task(dispatch_mode=DispatchMode.COLD_ONLY)
            def blocked(self, ctx: TaskContext) -> None:
                _ = ctx

    def _event_no_mapper_with_req() -> None:
        class _BadNoMapper(Module):
            id = "nomapper"

            @on_event(_ORDERED_EV)
            def needs_mapper(self, req: _EvItem, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _dup_group_in_module() -> None:
        class _BadDupGrp(Module):
            id = "dupgrp"
            groups = (_AlphaGroup, _AlphaGroup)

    def _abstract_group_in_module() -> None:
        class _AbsGrp(TaskGroup, ABC):
            @abstractmethod
            def hook(self) -> None: ...

        class _BadAbsGrpMod(Module):
            id = "absgrp"
            groups = (_AbsGrp,)

    def _bad_sig_missing_ctx() -> None:
        class _BadCtx(Module):
            id = "badctx"

            @task
            def op(self, req: _EchoIn, other: str) -> _EchoOut:
                _ = other
                return _EchoOut(text=req.tag)

    def _bad_sig_arity_one() -> None:
        class _BadArityOne(Module):
            id = "arityone"

            @task
            def op(self) -> None:
                _ = self

    def _bad_sig_arity_four() -> None:
        class _BadArityFour(Module):
            id = "arityfour"

            @task
            def op(self, first: str, second: str, ctx: TaskContext) -> None:
                _ = (first, second, ctx)

    def _bad_sig_no_return() -> None:
        class _BadNoRet(Module):
            id = "noret"

            @task
            def op(self, ctx: TaskContext):
                _ = ctx

    def _bad_sig_bool_ret() -> None:
        class _BadBoolRet(Module):
            id = "boolret"

            @task
            def op(self, ctx: TaskContext) -> True:
                _ = ctx
                return True

    def _bad_sig_none_req() -> None:
        class _BadNoneReq(Module):
            id = "nonereq"

            @task
            def op(self, req: None, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_sig_unann_req() -> None:
        class _BadUnannReq(Module):
            id = "unannreq"

            @task
            def op(self, req, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_non_group() -> None:
        class _BadNonGrp(Module):
            id = "nongrp"
            groups = (_EchoIn,)

    def _bad_sig_default() -> None:
        class _BadDefault(Module):
            id = "baddef"

            @task
            def op(self, ctx: TaskContext, flag: int = 1) -> None:
                _ = (ctx, flag)

    for bad_fn in (
        _blank_id,
        _invalid_id,
        _dup_task_id,
        _dup_cli_path,
        _alias_collision_with_group,
        _gated_with_event,
        _gated_with_periodic,
        _cold_with_event,
        _cold_with_periodic,
        _event_no_mapper_with_req,
        _dup_group_in_module,
        _abstract_group_in_module,
        _bad_non_group,
        _bad_sig_missing_ctx,
        _bad_sig_arity_one,
        _bad_sig_arity_four,
        _bad_sig_no_return,
        _bad_sig_bool_ret,
        _bad_sig_none_req,
        _bad_sig_unann_req,
        _bad_sig_default,
        lambda: _NoIdAbstractMod().to_yscb_module(),
        lambda: YscbClient.local(ws, _HealthySiblingModule(), _HealthySiblingModule()),
        lambda: YscbClient.local(ws, _HealthySiblingModule(), InMemoryModule("healthy")),
    ):
        assert_raises_val_error(bad_fn)


def _verify_dual_track_rendering(ws: HostPath) -> None:
    text_only = _TextOnlyOut("plain rendered")
    exit_plain = _ExitOnlyPlain(42)
    exit_dto = _ExitOnlyDto(status="warn", code=3)
    dual_out = _DualOut(summary="ok", code=7)

    check(isinstance(text_only, HumanRenderable) and not isinstance(text_only, ExitCodeProvider))
    check(isinstance(exit_plain, ExitCodeProvider) and not isinstance(exit_plain, HumanRenderable))
    check(isinstance(dual_out, HumanRenderable) and isinstance(dual_out, ExitCodeProvider))

    check(format_output(text_only) == ("plain rendered", 0))
    check(format_output(exit_plain) == (str(exit_plain), 42))
    txt_dto, code_dto = format_output(exit_dto)
    check(code_dto == 3 and json.loads(txt_dto) == {"status": "warn", "code": 3})
    check(format_output(dual_out) == ("DUAL:ok", 7))

    plain_dc_txt, plain_dc_code = format_output(_EchoOut(text="json_dc"))
    check(plain_dc_code == 0 and json.loads(plain_dc_txt)["text"] == "json_dc")
    check(format_output("raw_str") == ("raw_str", 0))
    check(format_output(123) == ("123", 0))
    check(format_output(True) == ("True", 0))
    check(format_output(None) == ("", 0))
    check(format_output(Empty()) == ("", 0))

    with YscbClient.local(ws, _HealthySiblingModule()) as client:
        out = client.call("healthy.dual", _EchoIn(tag="cli_dual"), output_type=_DualOut)
        check(out.ok and out.value == _DualOut(summary="cli_dual", code=7))
        check(format_output(out.value) == ("DUAL:cli_dual", 7))


def _verify_lifecycle_and_lifo_isolation(tmp_root: Path) -> None:
    ws_lifo_p = tmp_root / "ws_lifo"
    ws_lifo_p.mkdir(parents=True, exist_ok=True)
    ws_lifo = HostPath(ws_lifo_p)
    env_probe = ModuleEnv(ws_lifo)
    check(env_probe.workspace_root == ws_lifo)
    caught_bad_env = False
    try:
        _ = ModuleEnv(str(ws_lifo_p))  # intentionally wrong arg type
    except TypeError:
        caught_bad_env = True
    check(caught_bad_env)

    y_lifo = _LifoModule().to_yscb_module()
    init_closer = y_lifo.on_init(ws_lifo)
    warm_closer = y_lifo.on_start(ws_lifo)
    check(init_closer is not None and warm_closer is not None)
    lifo_log = ws_lifo_p / "lifo.log"
    check(
        lifo_log.read_text(encoding="utf-8").splitlines()
        == ["mod:init", "g1:init", "g2:init", "mod:warmup", "g1:warmup", "g2:warmup"]
    )
    warm_closer()
    init_closer()
    check(
        lifo_log.read_text(encoding="utf-8").splitlines()
        == [
            "mod:init",
            "g1:init",
            "g2:init",
            "mod:warmup",
            "g1:warmup",
            "g2:warmup",
            "g2:warmup_closer",
            "g1:warmup_closer",
            "mod:warmup_closer",
            "g2:closer",
            "g2:close",
            "g1:closer",
            "g1:close",
            "mod:closer",
            "mod:close",
        ]
    )

    ws_tox_p = tmp_root / "ws_toxic_direct"
    ws_tox_p.mkdir(parents=True, exist_ok=True)
    ws_tox = HostPath(ws_tox_p)
    tox_closer = _ToxicCloserModule().to_yscb_module().on_init(ws_tox)
    check(tox_closer is not None)
    expect_yscb_code(tox_closer, ErrorCode.TEARDOWN_ERROR)
    check(
        (ws_tox_p / "toxic.log").read_text(encoding="utf-8").splitlines()
        == ["tg:closer", "tg:close_boom", "tm:closer_boom", "tm:closer_ok", "tm:close"]
    )

    ws_tox_cli_p = tmp_root / "ws_toxic_client"
    ws_tox_cli_p.mkdir(parents=True, exist_ok=True)
    ws_tox_cli = HostPath(ws_tox_cli_p)
    cli_tox = YscbClient.local(ws_tox_cli, _HealthySiblingModule(), _ToxicCloserModule())
    healthy_tox = cli_tox.call("healthy.ping", output_type=_EchoOut)
    check(healthy_tox.ok and not healthy_tox.teardown_diagnostics)
    tox_out = cli_tox.call("toxic.ping", output_type=_EchoOut)
    check(tox_out.ok and tox_out.value == _EchoOut(text="toxic_ready"))
    check(any(d.code == ErrorCode.TEARDOWN_ERROR for d in tox_out.teardown_diagnostics))
    cli_tox.close()
    cli_tox.close()
    check(
        (ws_tox_cli_p / "toxic.log").read_text(encoding="utf-8").splitlines()
        == ["tg:closer", "tg:close_boom", "tm:closer_boom", "tm:closer_ok", "tm:close"]
    )
    check(
        (ws_tox_cli_p / "healthy.log").read_text(encoding="utf-8").splitlines()
        == ["healthy:init", "healthy:closer", "healthy:close"]
    )

    ws_deg_p = tmp_root / "ws_degraded"
    ws_deg_p.mkdir(parents=True, exist_ok=True)
    ws_deg = HostPath(ws_deg_p)
    with YscbClient.local(ws_deg, _FailingInitModule(), _HealthySiblingModule()) as client:
        bad_first = client.call("badinit.work", output_type=_EchoOut)
        check(not bad_first.ok and bad_first.error is not None and bad_first.error.code == ErrorCode.MODULE_DEGRADED)
        deg_lines = (ws_deg_p / "degraded.log").read_text(encoding="utf-8").splitlines()
        check(deg_lines == ["bad_mod:init", "bad_grp:init", "bad_grp:close", "bad_mod:rollback_closer", "bad_mod:close"])
        good_res = client.call("healthy.ping", output_type=_EchoOut)
        check(good_res.ok and good_res.value == _EchoOut(text="healthy_ok"))


def _verify_in_memory_and_client_e2e(tmp_root: Path) -> None:
    ws_e2e_p = tmp_root / "ws_e2e"
    sub_cwd_p = ws_e2e_p / "nested_cwd"
    sub_cwd_p.mkdir(parents=True, exist_ok=True)
    ws_e2e, sub_cwd = HostPath(ws_e2e_p), HostPath(sub_cwd_p)

    def _mem_untyped(ctx: TaskContext) -> dict[str, object]:
        return {"kind": "untyped", "cwd": str(ctx.caller_cwd)}

    def _mem_req_first(req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        return _EchoOut(text=f"req_first:{req.tag}", cwd=str(ctx.caller_cwd))

    def _mem_ctx_first(ctx: TaskContext, req: _EchoIn) -> _EchoOut:
        return _EchoOut(text=f"ctx_first:{req.tag}", trace_env=ctx.caller_env.get("YSCB_TRACE", ""))

    def _mem_gated(ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="mem_gated_ok")

    mem_mod = InMemoryModule("mem")
    chained = (
        mem_mod.add_task("ctx_only", _mem_untyped, summary="Untyped context handler")
        .add_task("req_first", _mem_req_first, lock="mem_lk")
        .add_task("ctx_first", _mem_ctx_first)
        .add_task("gated", _mem_gated, security=SecurityTier.GATED)
    )
    check(chained is mem_mod)
    mem_y = mem_mod.to_yscb_module()
    mem_specs = {bt.task_id.value: bt.route_spec for bt in mem_y.tasks()}
    check(mem_specs["mem.req_first"].resource_key == "mem_lk")
    check(mem_specs["mem.req_first"].concurrency_mode == ConcurrencyMode.SERIALIZE)
    assert_raises_val_error(lambda: InMemoryModule("Bad Mod"))
    assert_raises_val_error(lambda: mem_mod.add_task("ctx_only", _mem_untyped))
    assert_raises_val_error(lambda: mem_mod.add_task("not_fn", "oops"))  # type-checked runtime guard

    with YscbClient(ws_e2e, modules=(mem_mod, _ShowcaseModule(), _EmitterModule(), _SubscriberModule())) as client:
        untyped_out = client.call("mem.ctx_only", cwd=sub_cwd)
        check(untyped_out.ok and untyped_out.value == {"kind": "untyped", "cwd": str(sub_cwd)})

        req_first_out = client.call("mem.req_first", _EchoIn(tag="a"), cwd=sub_cwd, output_type=_EchoOut)
        check(req_first_out.ok and req_first_out.value == _EchoOut(text="req_first:a", cwd=str(sub_cwd)))

        ctx_first_out = client.call(
            "mem.ctx_first",
            _EchoIn(tag="b"),
            env={"YSCB_TRACE": "tr-1", "IGNORED_SECRET": "drop"},
            output_type=_EchoOut,
        )
        check(ctx_first_out.ok and ctx_first_out.value == _EchoOut(text="ctx_first:b", trace_env="tr-1"))

        cli_dto_out = client.call(
            "demo.doc_summary_task",
            _CliIn(target="src/app.py", verbose=True, count=4),
            output_type=_PairOut,
        )
        check(cli_dto_out.ok and cli_dto_out.value == _PairOut(target="src/app.py", verbose=True, count=4))

        void_out = client.call("demo.ping", output_type=Empty)
        check(void_out.ok and void_out.value == Empty())

        daemon_out = client.call("demo.explicit_cli", _EchoIn(tag="h"), output_type=_EchoOut)
        check(not daemon_out.ok and daemon_out.error is not None and daemon_out.error.code == ErrorCode.DAEMON_UNAVAILABLE)

        denied_demo = client.call("demo.gated_op", _EchoIn(tag="sec"), output_type=_EchoOut)
        check(not denied_demo.ok and denied_demo.error is not None and denied_demo.error.code == ErrorCode.SECURITY_GATED)
        allowed_demo = client.call(
            "demo.gated_op",
            _EchoIn(tag="sec"),
            approval_scope=frozenset({TaskId("demo.gated_op")}),
            output_type=_EchoOut,
        )
        check(allowed_demo.ok and allowed_demo.value == _EchoOut(text="gated:sec"))

        denied_mem = client.call("mem.gated", output_type=_EchoOut)
        check(not denied_mem.ok and denied_mem.error is not None and denied_mem.error.code == ErrorCode.SECURITY_GATED)
        allowed_mem = client.call(
            "mem.gated",
            approval_scope=frozenset({TaskId("mem.gated")}),
            output_type=_EchoOut,
        )
        check(allowed_mem.ok and allowed_mem.value == _EchoOut(text="mem_gated_ok"))

        nested_out = client.call(
            "emitter.call_sub",
            _EchoIn(tag="sub"),
            cwd=sub_cwd,
            env={"YSCB_TRACE": "nested_tr"},
            output_type=_EchoOut,
        )
        check(
            nested_out.ok
            and nested_out.value == _EchoOut(text="sub:sub|sub:sub:typed", cwd=str(sub_cwd), trace_env="nested_tr")
        )

        cold_out = client.call("mem.ctx_first", _EchoIn(tag="cold"), force_cold=True, output_type=_EchoOut)
        check(cold_out.ok and cold_out.value == _EchoOut(text="ctx_first:cold", trace_env=""))
        expect_yscb_code(lambda: client.call("mem.ctx_only", 42), ErrorCode.CODEC_VALIDATION_FAILED)

        seen_progress: list[ProgressEvent] = []
        prog_out = client.call(
            "emitter.slow_progress",
            on_progress=seen_progress.append,
            output_type=_EchoOut,
        )
        check(prog_out.ok and prog_out.value == _EchoOut(text="completed"))
        check(
            seen_progress
            == [
                ProgressEvent(phase="work", completed=1, total=2, message="step1"),
                ProgressEvent(phase="work", completed=2, total=2, message="cancel_now"),
            ]
        )

        tok_pre = CancellationToken()
        tok_pre.cancel(reason="pre_stop")
        pre_cancel_out = client.call("emitter.slow_progress", cancel_token=tok_pre, output_type=_EchoOut)
        check(not pre_cancel_out.ok and pre_cancel_out.error is not None and pre_cancel_out.error.code == ErrorCode.TASK_CANCELLED)

        tok_mid = CancellationToken()
        mid_events: list[ProgressEvent] = []

        def _cancel_on_second_progress(ev: ProgressEvent) -> None:
            mid_events.append(ev)
            if ev.message == "cancel_now":
                tok_mid.cancel(reason="mid_abort")

        mid_cancel_out = client.call(
            "emitter.slow_progress",
            cancel_token=tok_mid,
            on_progress=_cancel_on_second_progress,
            output_type=_EchoOut,
        )
        check(not mid_cancel_out.ok and mid_cancel_out.error is not None and mid_cancel_out.error.code == ErrorCode.TASK_CANCELLED)
        check(len(mid_events) == 2)

        fire_out = client.call("emitter.fire", output_type=_EchoOut)
        check(fire_out.ok and fire_out.value == _EchoOut(text="imm_inline:imm:7"))
        check((ws_e2e_p / "ev_kept.log").read_text(encoding="utf-8").splitlines() == ["35:keep,keep"])
        check((ws_e2e_p / "ev_weak.txt").read_text(encoding="utf-8") == "weak_ok")

    expect_yscb_code(lambda: client.call("mem.ctx_only"), ErrorCode.TEARDOWN_ERROR)

    ws_disk_p = tmp_root / "ws_connect_empty"
    ws_disk_p.mkdir(parents=True, exist_ok=True)
    with YscbClient.connect(HostPath(ws_disk_p)) as conn:
        miss = conn.call("demo.ping", output_type=Empty)
        check(not miss.ok and miss.error is not None and miss.error.code == ErrorCode.TASK_NOT_FOUND)
    expect_yscb_code(lambda: conn.call("demo.ping"), ErrorCode.TEARDOWN_ERROR)


def run_surface_sdk_suite(tmp_root: Path) -> None:
    """Execute the full Surface SDK test suite covering DSL, lifecycle, and YscbClient."""
    ws_base_p = tmp_root / "ws_sdk_base"
    ws_base_p.mkdir(parents=True, exist_ok=True)
    ws_base = HostPath(ws_base_p)

    _verify_facade_and_zero_leak()
    _verify_declarative_metadata_and_stacking(ws_base)
    _verify_compile_time_validation(ws_base)
    _verify_dual_track_rendering(ws_base)
    _verify_lifecycle_and_lifo_isolation(tmp_root)
    _verify_in_memory_and_client_e2e(tmp_root)
    log("[SURFACE-SDK] Surface SDK verification suite PASSED")


__all__ = ("run_surface_sdk_suite",)
