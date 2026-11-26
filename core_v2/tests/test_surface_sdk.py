"""Verification suite for core.surface.sdk declarative DSL, lifecycle bridging, and YscbClient."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
import inspect
import json
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Literal, Annotated, ClassVar, Optional, Sequence, TypeVar, cast, get_args, get_type_hints

import core.execution.runtime as rt_mod
import core.surface.sdk as sdk
import core.surface.sdk.advanced as sdk_adv
from core.execution.event import EventOrdering, EventSubscriptionSpec
from core.execution.runtime import (
    CallPropagationContext,
    CliBindingSpec,
    DispatcherHostOptions,
    InvokeRequest,
    ModuleDescriptor,
    ModuleProviderPort,
    PeriodicScheduleSpec,
    RuntimeDispatcher,
    Task,
    TaskExposure,
    TaskRouteSpec,
    build_default_module_services,
    build_workspace_module_services_factory,
)
from core.foundation import SECRET_FIELD_METADATA_KEY, SchemaExporter
from core.metadata.contributes import compile_extension_points
from core.surface.bootstrap import (
    ClearDynamicSpaceInput,
    SetDynamicSpaceInput,
    SpaceAckCursorInput,
    SpaceScanInput,
)
from core.surface.sdk import (
    CONFIG_CHANGED_EVENT,
    MODULE_INSTALLED_EVENT,
    MODULE_REMOVING_EVENT,
    SPACE_REGISTRY_CHANGED_EVENT,
    SPACE_UPDATED_EVENT,
    WORKSPACE_RELOADED_EVENT,
    Arg,
    BlobVault,
    CancellationToken,
    ConcurrencyMode,
    ConfigChangedEventPayload,
    ContribField,
    DispatchMode,
    Empty,
    ErrorCode,
    EventMetadata,
    ExitCodeProvider,
    ExtensionPointSpec,
    HostPath,
    HumanRenderable,
    MergeStrategy,
    MigrationRequest,
    Module,
    ModuleDatabase,
    ModuleEnv,
    ModuleLifecycleEventPayload,
    Option,
    ProcessResult,
    ProgressEvent,
    SchemaMigration,
    ScopedVfs,
    SecurityTier,
    SemanticUri,
    SpaceClient,
    SpaceDiffBatch,
    SpaceFileEntry,
    SpaceId,
    SpacePath,
    SpaceSpec,
    SpaceStatusSnapshot,
    SpaceUpdatedEventPayload,
    TaskCancelledException,
    TaskContext,
    TaskGroup,
    TaskOutcome,
    TaskRef,
    YscbError,
    define_event,
    on_event,
    on_migrate,
    periodic,
    secret_field,
    task,
)
from core.surface.sdk.advanced import (
    CONFIG_CHANGED_EVENT_ID,
    MODULE_INSTALLED_EVENT_ID,
    MODULE_REMOVING_EVENT_ID,
    SPACE_REGISTRY_CHANGED_EVENT_ID,
    SPACE_UPDATED_EVENT_ID,
    WORKSPACE_RELOADED_EVENT_ID,
    AggregatedContributes,
    ClientRoutingPolicy,
    ConsumerCursor,
    ErrorDetail,
    EventId,
    ExecutionPriority,
    HashPolicy,
    InMemoryModule,
    JsonValue,
    LocaleCatalog,
    LogLevel,
    ModuleId,
    NullProfiler,
    Profiler,
    ProfilerNodeSnapshot,
    ProfilerSession,
    ProvenanceGraph,
    SemVer4,
    SnapshotGen,
    SnapshotReader,
    StorageOpenOptions,
    StructuredLogger,
    TaskId,
    TaskMetadata,
    VersionConstraint,
    VfsCapabilities,
    VfsStat,
    WriteTransaction,
    YscbClient,
    YscbModule,
    format_output,
    render_profiler_tree,
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
        sub_one = ctx.call("subscriber.echo", _EchoIn(tag=req.tag), output_type=_EchoOut)
        sub_ref = TaskRef(_SUB_TYPED_META.task_id, _SUB_TYPED_META.input_type, _SUB_TYPED_META.output_type)
        sub_two = ctx.call(sub_ref, _EchoIn(tag=f"{req.tag}:typed"))
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
    expected_primary = frozenset(
        {
            "Arg",
            "BlobVault",
            "CONFIG_CHANGED_EVENT",
            "CancellationToken",
            "ConcurrencyMode",
            "ConfigChangedEventPayload",
            "ContribField",
            "DispatchMode",
            "Empty",
            "ErrorCode",
            "EventMetadata",
            "ExitCodeProvider",
            "ExtensionPointSpec",
            "HostPath",
            "HumanRenderable",
            "MODULE_INSTALLED_EVENT",
            "MODULE_REMOVING_EVENT",
            "MergeStrategy",
            "MigrationRequest",
            "Module",
            "ModuleDatabase",
            "ModuleEnv",
            "ModuleLifecycleEventPayload",
            "Option",
            "ProcessResult",
            "ProgressEvent",
            "SPACE_REGISTRY_CHANGED_EVENT",
            "SPACE_UPDATED_EVENT",
            "SchemaMigration",
            "ScopedVfs",
            "SecurityTier",
            "SemanticUri",
            "SpaceClient",
            "SpaceDiffBatch",
            "SpaceFileEntry",
            "SpaceId",
            "SpacePath",
            "SpaceSpec",
            "SpaceStatusSnapshot",
            "SpaceUpdatedEventPayload",
            "TaskCancelledException",
            "TaskContext",
            "TaskGroup",
            "TaskOutcome",
            "TaskRef",
            "WORKSPACE_RELOADED_EVENT",
            "YscbError",
            "define_event",
            "on_event",
            "on_migrate",
            "periodic",
            "secret_field",
            "task",
        }
    )
    expected_advanced = frozenset(
        {
            "AggregatedContributes",
            "CONFIG_CHANGED_EVENT_ID",
            "ClientRoutingPolicy",
            "ConsumerCursor",
            "ErrorDetail",
            "EventId",
            "ExecutionPriority",
            "HashPolicy",
            "InMemoryModule",
            "JsonValue",
            "LocaleCatalog",
            "LogLevel",
            "MODULE_INSTALLED_EVENT_ID",
            "MODULE_REMOVING_EVENT_ID",
            "ModuleId",
            "NullProfiler",
            "Profiler",
            "ProfilerNodeSnapshot",
            "ProfilerSession",
            "ProvenanceGraph",
            "SPACE_REGISTRY_CHANGED_EVENT_ID",
            "SPACE_UPDATED_EVENT_ID",
            "SemVer4",
            "SnapshotGen",
            "SnapshotReader",
            "StorageOpenOptions",
            "StructuredLogger",
            "TaskId",
            "TaskMetadata",
            "VersionConstraint",
            "VfsCapabilities",
            "VfsStat",
            "WORKSPACE_RELOADED_EVENT_ID",
            "WriteTransaction",
            "YscbClient",
            "YscbModule",
            "format_output",
            "render_profiler_tree",
        }
    )
    check(len(sdk.__all__) == 53 and len(set(sdk.__all__)) == 53)
    check(frozenset(sdk.__all__) == expected_primary)
    check(len(sdk_adv.__all__) == 38 and len(set(sdk_adv.__all__)) == 38)
    check(frozenset(sdk_adv.__all__) == expected_advanced)
    check(expected_primary.isdisjoint(expected_advanced))
    check(secret_field is not None)
    check(
        all(
            sym is not None
            for sym in (
                BlobVault,
                CONFIG_CHANGED_EVENT,
                CONFIG_CHANGED_EVENT_ID,
                ClientRoutingPolicy,
                ConfigChangedEventPayload,
                ConsumerCursor,
                ContribField,
                ErrorDetail,
                ExecutionPriority,
                ExtensionPointSpec,
                HashPolicy,
                JsonValue,
                LogLevel,
                MODULE_INSTALLED_EVENT,
                MODULE_INSTALLED_EVENT_ID,
                MODULE_REMOVING_EVENT,
                MODULE_REMOVING_EVENT_ID,
                MergeStrategy,
                MigrationRequest,
                ModuleDatabase,
                ModuleLifecycleEventPayload,
                NullProfiler,
                ProcessResult,
                Profiler,
                ProfilerNodeSnapshot,
                ProfilerSession,
                ProvenanceGraph,
                SPACE_REGISTRY_CHANGED_EVENT,
                SPACE_REGISTRY_CHANGED_EVENT_ID,
                SPACE_UPDATED_EVENT,
                SPACE_UPDATED_EVENT_ID,
                SchemaMigration,
                SemVer4,
                SemanticUri,
                SnapshotGen,
                SnapshotReader,
                SpaceClient,
                SpaceDiffBatch,
                SpaceFileEntry,
                SpaceId,
                SpacePath,
                SpaceSpec,
                SpaceStatusSnapshot,
                SpaceUpdatedEventPayload,
                StorageOpenOptions,
                TaskCancelledException,
                TaskMetadata,
                TaskRef,
                VersionConstraint,
                VfsCapabilities,
                VfsStat,
                WORKSPACE_RELOADED_EVENT,
                WORKSPACE_RELOADED_EVENT_ID,
                WriteTransaction,
                YscbError,
                on_migrate,
                render_profiler_tree,
            )
        )
    )
    tg_members = dict(inspect.getmembers_static(TaskGroup))
    check("prefix" not in tg_members and "parent_module" in tg_members and "module" in tg_members)
    sdk_members = dict(inspect.getmembers_static(sdk))
    adv_members = dict(inspect.getmembers_static(sdk_adv))
    for leaked in (
        "BoundTask",
        "_DeclarativeMeta",
        "_DecoratedMethod",
        "_SdkStateRegistry",
        "_SdkBoundTask",
        "_SdkYscbModule",
        "ClearDynamicSpaceInput",
        "SetDynamicSpaceInput",
        "SpaceAckCursorInput",
        "SpaceScanInput",
        "SPACE_UPDATED_EVENT_ID_STR",
        "SPACE_REGISTRY_CHANGED_EVENT_ID_STR",
    ):
        check(leaked not in sdk.__all__ and leaked not in sdk_members)
        check(leaked not in sdk_adv.__all__ and leaked not in adv_members)
    for adv_only in ("YscbClient", "InMemoryModule", "format_output", "ProfilerSession", "TaskMetadata", "YscbModule"):
        check(adv_only not in sdk.__all__ and adv_only in sdk_adv.__all__)
    check(all(sym in sdk_members for sym in expected_primary))
    check(all(sym in adv_members for sym in expected_advanced))
    check(TaskOutcome is not None and YscbModule is not None)


_TStubCfg = TypeVar("_TStubCfg")


class _StubTaskContext(TaskContext):
    def __init__(self, ws: HostPath) -> None:
        self._ws = ws
        self._tok = CancellationToken()
        self._svc = build_default_module_services(ws, ModuleId("demo"))

    @property
    def module_id(self) -> ModuleId:
        return self._svc.module_id

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

    @property
    def vfs(self) -> ScopedVfs:
        return self._svc.vfs

    @property
    def logger(self) -> StructuredLogger:
        return self._svc.logger

    @property
    def locale(self) -> LocaleCatalog:
        return self._svc.locale

    def load_config(self, config_cls: type[_TStubCfg]) -> _TStubCfg:
        return cast(_TStubCfg, self._svc.config_loader(config_cls))

    def load_contributes(self) -> AggregatedContributes:
        return self._svc.contributes_loader()

    def emit(self, event_meta: EventMetadata[object], payload: object) -> None:
        _ = (event_meta, payload)

    def emit_imm(self, event_meta: EventMetadata[object], payload: object, *, strict: bool = False) -> None:
        _ = (event_meta, payload, strict)

    def call(
        self,
        target: TaskRef[object, object] | TaskId | str,
        input_obj: object = None,
        *,
        output_type: Optional[type[object]] = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[object] = None,
    ) -> TaskOutcome[object]:
        _ = (target, input_obj, output_type, target_workspace, routing_policy)
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
    try:
        healthy_tox = cli_tox.call("healthy.ping", output_type=_EchoOut)
        check(healthy_tox.ok and not healthy_tox.teardown_diagnostics)
        tox_out = cli_tox.call("toxic.ping", output_type=_EchoOut)
        check(tox_out.ok and tox_out.value == _EchoOut(text="toxic_ready"))
        check(any(d.code == ErrorCode.TEARDOWN_ERROR for d in tox_out.teardown_diagnostics))
        cli_tox.close()
        cli_tox.close()
    finally:
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


@dataclass(frozen=True, slots=True)
class _Wave12ModCfg:
    greeting: str = "hello"
    limit: int = 5


@dataclass(frozen=True, slots=True)
class _Wave12ExtItem:
    tag: str
    weight: int = 1


class _Wave12StorageAndMigrateModule(Module):
    id = "w12mod"
    aliases = ("w12",)
    description = "Wave 1.2 showcase module"
    config_type = _Wave12ModCfg
    extension_points = (
        ExtensionPointSpec(
            name="items",
            payload_type=tuple[_Wave12ExtItem, ...],
            merge_strategy=MergeStrategy.EXTEND,
            description="Extension items",
        ),
    )

    def __init__(self) -> None:
        self._db: Optional[ModuleDatabase] = None
        self._vault: Optional[BlobVault] = None

    def is_db_closed(self) -> bool:
        return self._db is not None and self._db.is_closed

    def on_init(self, env: ModuleEnv) -> None:
        check(env.module_id == ModuleId("w12mod"))
        self._db = env.open_database(
            "items",
            migrations=(SchemaMigration(1, "init_kv", ("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)",)),),
        )
        self._vault = env.open_blob_vault("blobs")
        with self._db.write_transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", ("boot", env.load_config(_Wave12ModCfg).greeting))
        _ = self._vault.put_keyed("seed/note.txt", b"vault-ok")

    @task(
        "w12 query",
        usage_pros=("Fast snapshot read",),
        usage_cons=("Read-only inspection",),
    )
    def query_state(self, ctx: TaskContext) -> _EchoOut:
        assert_db = self._db
        assert_vault = self._vault
        check(assert_db is not None and assert_vault is not None)
        if assert_db is None or assert_vault is None:
            raise RuntimeError("uninitialized")
        cfg = ctx.load_config(_Wave12ModCfg)
        contrib = ctx.load_contributes()
        ctx.logger.info("querying state", fields={"limit": cfg.limit})
        msg = ctx.locale.translate("w12mod:hello_key")
        ctx.vfs.write_text("cache://@/probe.txt", "cached")
        cached = ctx.vfs.read_text("cache://@/probe.txt")
        with assert_db.read_snapshot() as snap:
            row = snap.query_one("SELECT v FROM kv WHERE k = ?", ("boot",))
        raw_blob = assert_vault.get_bytes("seed/note.txt")
        blob_txt = raw_blob.decode("utf-8") if raw_blob is not None else ""
        pts = len(contrib.decode_point("items", tuple[_Wave12ExtItem, ...])) if contrib.has_point("items") else 0
        return _EchoOut(text=f"{row[0] if row else ''}|{cfg.limit}|{pts}|{msg}|{cached}|{blob_txt}")

    @task("w12 wipe", security=SecurityTier.CRITICAL)
    def critical_wipe(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text="wiped")

    @task("w12 nested-crit")
    def nested_call_critical(self, ctx: TaskContext) -> _EchoOut:
        out = ctx.call("w12mod.critical_wipe", {}, output_type=_EchoOut)
        return _EchoOut(text=out.error.code.value if out.error is not None else "unexpected_ok")

    @on_migrate()
    def handle_upgrade(self, req: MigrationRequest, ctx: TaskContext) -> None:
        assert_db = self._db
        if assert_db is not None:
            with assert_db.write_transaction() as tx:
                tx.execute(
                    "INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)",
                    ("migrated", f"{req.old_version}->{req.new_version}:{ctx.load_config(_Wave12ModCfg).greeting}"),
                )


class _SingleDirModuleProvider(ModuleProviderPort):
    def __init__(self, descriptors: Sequence[ModuleDescriptor]) -> None:
        self._descs = tuple(descriptors)

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        return self._descs

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        return next((d for d in self._descs if d.module_id == module_id), None)

    def reload(self) -> None:
        return None


def _verify_wave12_sdk_extensions(tmp_root: Path) -> None:
    opt_grp = Option(short="-f", summary="Force", group="mode")
    check(opt_grp.group == "mode")
    assert_raises_val_error(lambda: Option(group="   "))

    def _bad_mutable_cfg() -> None:
        @dataclass
        class _MutableCfg:
            x: int = 1

        class _BadCfgMod(Module):
            id = "badcfg"
            config_type = _MutableCfg

    def _bad_dup_migrate() -> None:
        class _BadDupMig(Module):
            id = "dupmig"

            @on_migrate()
            def m1(self, req: MigrationRequest, ctx: TaskContext) -> None:
                _ = (req, ctx)

            @on_migrate()
            def m2(self, req: MigrationRequest, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_critical_event() -> None:
        class _BadCritEv(Module):
            id = "critev"

            @on_event(_WEAK_PING_EV)
            @task(security=SecurityTier.CRITICAL)
            def op(self, ctx: TaskContext) -> None:
                _ = ctx

    def _bad_group_migrate() -> None:
        class _BadMigGrp(TaskGroup):
            @on_migrate()
            def m1(self, req: MigrationRequest, ctx: TaskContext) -> None:
                _ = (req, ctx)

    for bad_w12 in (_bad_mutable_cfg, _bad_dup_migrate, _bad_critical_event, _bad_group_migrate):
        assert_raises_val_error(bad_w12)

    ws_db_p = tmp_root / "ws_w12_lifo_db"
    ws_db_p.mkdir(parents=True, exist_ok=True)
    ws_db = HostPath(ws_db_p)
    w12_inst = _Wave12StorageAndMigrateModule()
    with YscbClient.local(ws_db, w12_inst) as client:
        q_out = client.call("w12mod.query_state", output_type=_EchoOut)
        check(q_out.ok and q_out.value == _EchoOut(text="hello|5|0|w12mod:hello_key|cached|vault-ok"))
        denied_crit = client.call("w12mod.critical_wipe", output_type=_EchoOut)
        check(not denied_crit.ok and denied_crit.error is not None and denied_crit.error.code == ErrorCode.SECURITY_GATED)
        nested_crit = client.call(
            "w12mod.nested_call_critical",
            approval_scope=frozenset({TaskId("w12mod.critical_wipe")}),
            output_type=_EchoOut,
        )
        check(nested_crit.ok and nested_crit.value == _EchoOut(text=ErrorCode.SECURITY_GATED.value))
        allowed_crit = client.call(
            "w12mod.critical_wipe",
            approval_scope=frozenset({TaskId("w12mod.critical_wipe")}),
            output_type=_EchoOut,
        )
        check(allowed_crit.ok and allowed_crit.value == _EchoOut(text="wiped"))
    check(w12_inst.is_db_closed())
    shutil.rmtree(ws_db_p)
    check(not ws_db_p.exists())

    ws_tier_p = tmp_root / "ws_w12_cross_tier"
    (ws_tier_p / "config" / "tmod").mkdir(parents=True, exist_ok=True)
    (ws_tier_p / "config" / "core").mkdir(parents=True, exist_ok=True)
    (ws_tier_p / "config" / "tmod" / "config.project.json").write_text(
        json.dumps({"greeting": "configured", "limit": 42}),
        encoding="utf-8",
    )
    (ws_tier_p / "config" / "tmod" / "contribute.json").write_text(
        json.dumps({"items": [{"tag": "ext1", "weight": 9}]}),
        encoding="utf-8",
    )
    (ws_tier_p / "yscb.config.json").write_text(
        json.dumps(
            {
                "yscb_root": ".",
                "default_provider": "./prov",
                "installed_modules": {
                    "tmod": {
                        "version": "1.0.0.0",
                        "installed_at": "2026-11-22T00:00:00Z",
                        "provider": "./prov",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    mod_dir_p = ws_tier_p / ".modules" / "tmod"
    (mod_dir_p / "locales").mkdir(parents=True, exist_ok=True)
    (mod_dir_p / "locales" / "zh.json").write_text(json.dumps({"hello_key": "你好世界"}), encoding="utf-8")
    (mod_dir_p / "manifest.json").write_text(
        json.dumps(
            {
                "id": "tmod",
                "version": "1.0.0.0",
                "entry_file": "module_entry.py",
                "eager_warmup": False,
                "dependencies": {},
                "optional_dependencies": {},
                "pip_dependencies": [],
            }
        ),
        encoding="utf-8",
    )
    mod_src = "\n".join(
        (
            "from dataclasses import dataclass",
            "from core.surface.sdk import (",
            "    ExtensionPointSpec, MergeStrategy, MigrationRequest, Module, SchemaMigration,",
            "    TaskContext, on_migrate, task,",
            ")",
            "from core.surface.sdk.advanced import SemVer4",
            "@dataclass(frozen=True, slots=True)",
            "class TModCfg:",
            "    greeting: str = 'dflt'",
            "    limit: int = 1",
            "@dataclass(frozen=True, slots=True)",
            "class TExtItem:",
            "    tag: str",
            "    weight: int = 1",
            "@dataclass(frozen=True, slots=True)",
            "class TProbeOut:",
            "    summary: str",
            "class TMod(Module):",
            "    id = 'tmod'",
            "    config_type = TModCfg",
            "    extension_points = (ExtensionPointSpec('items', tuple[TExtItem, ...], merge_strategy=MergeStrategy.EXTEND),)",
            "    def on_init(self, env):",
            "        self._db = env.open_database('state', migrations=(SchemaMigration(1, 'init_st', ('CREATE TABLE st (k TEXT PRIMARY KEY, v TEXT)',)),))",
            "    @task('tmod inspect')",
            "    def inspect_all(self, ctx: TaskContext) -> TProbeOut:",
            "        cfg = ctx.load_config(TModCfg)",
            "        items = ctx.load_contributes().decode_point('items', tuple[TExtItem, ...])",
            "        loc = ctx.locale.translate('hello_key')",
            "        ctx.logger.info('inspect_all_called')",
            "        ctx.vfs.write_text('cache://@/ok.txt', 'v1')",
            "        with self._db.read_snapshot() as snap:",
            "            mig = snap.query_one('SELECT v FROM st WHERE k = ?', ('mig',))",
            "        mig_txt = mig[0] if mig else 'none'",
            "        cached_txt = ctx.vfs.read_text('cache://@/ok.txt')",
            "        return TProbeOut(summary=f'{cfg.greeting}|{cfg.limit}|{items[0].tag}:{items[0].weight}|{loc}|{cached_txt}|{mig_txt}')",
            "    @on_migrate()",
            "    def upgrade(self, req: MigrationRequest, ctx: TaskContext) -> None:",
            "        _ = ctx",
            "        with self._db.write_transaction() as tx:",
            "            tx.execute('INSERT OR REPLACE INTO st (k, v) VALUES (?, ?)', ('mig', f'{req.old_version}->{req.new_version}'))",
            "def create_module():",
            "    return TMod().to_yscb_module()",
            "",
        )
    )
    (mod_dir_p / "module_entry.py").write_text(mod_src, encoding="utf-8")
    (mod_dir_p / "contributes").mkdir(parents=True, exist_ok=True)
    bundle = compile_extension_points(
        ModuleId("tmod"),
        (ExtensionPointSpec("items", tuple[_Wave12ExtItem, ...], merge_strategy=MergeStrategy.EXTEND),),
    )
    (mod_dir_p / "contributes" / "_schema.json").write_text(
        json.dumps(bundle.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ws_hp = HostPath(ws_tier_p)
    svc_factory = build_workspace_module_services_factory(ws_hp, ws_hp)
    results: list[str] = []
    for venv_py in (None, HostPath(sys.executable)):
        desc = ModuleDescriptor(
            module_id=ModuleId("tmod"),
            module_dir=HostPath(mod_dir_p),
            venv_python=venv_py,
            declared_tasks=(
                TaskRouteSpec(
                    task_id=TaskId("tmod.inspect_all"),
                    cli=CliBindingSpec(("tmod", "inspect"), "Execute tmod.inspect_all"),
                ),
                TaskRouteSpec(
                    task_id=TaskId("tmod.yscb_on_migrate"),
                    exposure=TaskExposure.INTERNAL_TRIGGER,
                ),
            ),
        )
        prov = _SingleDirModuleProvider((desc,))
        disp = RuntimeDispatcher(
            workspace_root=ws_hp,
            cache_dir=ws_hp.join(".cache"),
            module_provider=prov,
            options=DispatcherHostOptions(module_services_factory=svc_factory, worker_host_dir=ws_hp),
        )
        try:
            mig_out = disp.invoke(
                InvokeRequest(
                    task_id=TaskId("tmod.yscb_on_migrate"),
                    raw_input={"old_version": "0.9.0.0", "new_version": "1.0.0.0"},
                    workspace_root=ws_hp,
                    caller_cwd=ws_hp,
                    propagation=CallPropagationContext(is_internal_trigger=True),
                )
            )
            check(mig_out.ok)
            res = disp.invoke(
                InvokeRequest(
                    task_id=TaskId("tmod.inspect_all"),
                    raw_input={},
                    workspace_root=ws_hp,
                    caller_cwd=ws_hp,
                )
            )
            check(res.ok and isinstance(res.value, dict))
            if isinstance(res.value, dict):
                results.append(str(res.value.get("summary", "")))
        finally:
            disp.shutdown()
    check(len(results) == 2 and results[0] == results[1])
    check(results[0] == "configured|42|ext1:9|你好世界|v1|0.9.0.0->1.0.0.0")

    ws_unready_p = tmp_root / "ws_unready_t1"
    (ws_unready_p / ".modules" / "badt1").mkdir(parents=True, exist_ok=True)
    (ws_unready_p / ".modules" / "badt1" / "manifest.json").write_text(
        json.dumps(
            {
                "id": "badt1",
                "version": "1.0.0.0",
                "description": "Unbuilt tier1 module",
                "pip_dependencies": {"fakepkg": ">=1.0"},
            }
        ),
        encoding="utf-8",
    )
    (ws_unready_p / ".modules" / "badt1" / "tasks.index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module_id": "badt1",
                "module_aliases": [],
                "description": "Unbuilt tier1",
                "tasks": [
                    {
                        "task_id": "badt1.run",
                        "command_path": ["run"],
                        "aliases": [],
                        "summary": "Run",
                        "usage_pros": [],
                        "usage_cons": [],
                        "exposure": "cli_and_sdk",
                        "security_tier": "safe",
                        "dispatch_mode": "hybrid",
                        "interactive_tty": False,
                        "args": [],
                        "options": [],
                        "subscriptions": [],
                        "periodic": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (ws_unready_p / ".modules" / "badt1" / "module_entry.py").write_text(
        "raise RuntimeError('MUST_NEVER_IMPORT_IN_TIER0_HOST')\ndef create_module():\n    return None\n",
        encoding="utf-8",
    )
    with YscbClient(HostPath(ws_unready_p), modules=(_HealthySiblingModule(),)) as unready_cli:
        ok_sib = unready_cli.call("healthy.ping", output_type=_EchoOut)
        check(ok_sib.ok and ok_sib.value == _EchoOut(text="healthy_ok"))
        blocked_t1 = unready_cli.call("badt1.run")
        check(
            not blocked_t1.ok
            and blocked_t1.error is not None
            and blocked_t1.error.code == ErrorCode.WORKER_CRASHED
            and ".yscb_unready_tier1_badt1" in blocked_t1.error.message,
            f"Unverified Tier 1 module must fail closed via unready Tier 1 sentinel: {blocked_t1}",
        )

    def _bad_cli_scalar_vo_in() -> None:
        class _BadCliVoMod(Module):
            id = "badclivo"

            @task("inspect mod")
            def op(self, req: ModuleId, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_sdk_scalar_vo_in() -> None:
        class _BadSdkVoMod(Module):
            id = "badsdkvo"

            @task
            def op(self, req: ModuleId, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_sdk_prim_in() -> None:
        class _BadSdkPrimMod(Module):
            id = "badsdkprim"

            @task
            def op(self, req: int, ctx: TaskContext) -> None:
                _ = (req, ctx)

    for bad_in_fn in (_bad_cli_scalar_vo_in, _bad_sdk_scalar_vo_in, _bad_sdk_prim_in):
        try:
            bad_in_fn()
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for invalid task input_type in {bad_in_fn.__name__}")

    class _DictInputSdkMod(Module):
        id = "dictin"

        @task
        def count_keys(self, req: dict[str, object], ctx: TaskContext) -> int:
            _ = ctx
            return len(req)

    ws_corrupt_p = tmp_root / "ws_sdk_corrupt_index"
    (ws_corrupt_p / ".modules" / "corruptmod").mkdir(parents=True, exist_ok=True)
    (ws_corrupt_p / ".modules" / "foreignmod").mkdir(parents=True, exist_ok=True)
    for m_name in ("corruptmod", "foreignmod"):
        (ws_corrupt_p / ".modules" / m_name / "manifest.json").write_text(
            json.dumps({"id": m_name, "version": "1.0.0.0", "description": m_name}),
            encoding="utf-8",
        )
    (ws_corrupt_p / ".modules" / "corruptmod" / "module_entry.py").write_text(
        "\n".join(
            (
                "from core.execution.runtime import TaskContext",
                "from core.surface.sdk import Module, task",
                "class CMod(Module):",
                "    id = 'corruptmod'",
                "    @task",
                "    def first(self, ctx: TaskContext) -> str:",
                "        return 'ok_first'",
                "    @task",
                "    def second(self, ctx: TaskContext) -> str:",
                "        return 'ok_second'",
                "def create_module():",
                "    return CMod().to_yscb_module()",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (ws_corrupt_p / ".modules" / "corruptmod" / "tasks.index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module_id": "corruptmod",
                "tasks": [
                    {
                        "task_id": "corruptmod.first",
                        "exposure": "sdk_only",
                        "security_tier": "safe",
                        "dispatch_mode": "hybrid",
                    },
                    "NOT_AN_OBJECT",
                ],
            }
        ),
        encoding="utf-8",
    )
    (ws_corrupt_p / ".modules" / "foreignmod" / "module_entry.py").write_text(
        "\n".join(
            (
                "from core.execution.runtime import TaskContext",
                "from core.surface.sdk import Module, task",
                "class FMod(Module):",
                "    id = 'foreignmod'",
                "    @task",
                "    def own(self, ctx: TaskContext) -> str:",
                "        return 'ok_own'",
                "def create_module():",
                "    return FMod().to_yscb_module()",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (ws_corrupt_p / ".modules" / "foreignmod" / "tasks.index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module_id": "foreignmod",
                "tasks": [
                    {
                        "task_id": "other.hijack",
                        "exposure": "sdk_only",
                        "security_tier": "safe",
                        "dispatch_mode": "hybrid",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with YscbClient(HostPath(ws_corrupt_p), modules=(_DictInputSdkMod(),)) as c_cli:
        d_out = c_cli.call("dictin.count_keys", {"a": 1, "b": 2}, output_type=int)
        check(d_out.ok and d_out.value == 2, f"Expected SDK_ONLY dict input to succeed: {d_out}")
        try:
            _ = c_cli.call("dictin.count_keys", ModuleId("probe"))
        except YscbError as exc_vo:
            check(exc_vo.detail.code == ErrorCode.CODEC_VALIDATION_FAILED, f"Expected CODEC_VALIDATION_FAILED, got {exc_vo}")
        else:
            raise AssertionError("Expected YscbError(CODEC_VALIDATION_FAILED) when passing scalar VO to YscbClient.call")
        c_second = c_cli.call("corruptmod.second", output_type=str)
        check(
            c_second.ok and c_second.value == "ok_second",
            f"Corrupted tasks.index.json must be discarded atomically so Tier 0 dynamically discovers all tasks: {c_second}",
        )
        f_own = c_cli.call("foreignmod.own", output_type=str)
        check(f_own.ok and f_own.value == "ok_own", f"Foreign task_id in tasks.index.json must not crash YscbClient: {f_own}")

    # Reentrant close() guard & concurrent call/close drain safety on YscbClient
    reentrant_mod = InMemoryModule("reent")
    reentrant_client_holder: list[YscbClient] = []

    def _reentrant_close_task(_ctx: TaskContext) -> str:
        reentrant_client_holder[0].close()
        return "unreachable"

    call_entered = threading.Event()
    allow_finish = threading.Event()

    def _slow_drain_task(_ctx: TaskContext) -> str:
        call_entered.set()
        allow_finish.wait(timeout=5.0)
        return "drained_ok"

    reentrant_mod.add_task("self_close", _reentrant_close_task)
    reentrant_mod.add_task("slow", _slow_drain_task)
    ws_life = tmp_root / "ws_sdk_lifecycle_gate"
    ws_life.mkdir(parents=True, exist_ok=True)
    life_cli = YscbClient.local(HostPath(ws_life), reentrant_mod)
    reentrant_client_holder.append(life_cli)
    reent_out = life_cli.call("reent.self_close")
    check(
        not reent_out.ok and reent_out.error is not None and reent_out.error.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY,
        f"Reentrant YscbClient.close() inside active call must fail with ILLEGAL_LOCK_REENTRANCY: {reent_out}",
    )
    drain_res: list[object] = []
    t_worker = threading.Thread(target=lambda: drain_res.append(life_cli.call("reent.slow", output_type=str)))
    t_worker.start()
    check(call_entered.wait(timeout=5.0), "Worker call failed to start")
    close_done = threading.Event()

    def _close_bg() -> None:
        life_cli.close()
        close_done.set()

    t_closer = threading.Thread(target=_close_bg)
    t_closer.start()
    check(not close_done.wait(timeout=0.05), "close() must wait for in-flight call to drain")
    try:
        _ = life_cli.call("reent.slow")
    except YscbError as exc_cl:
        check(exc_cl.detail.code == ErrorCode.TEARDOWN_ERROR)
    else:
        raise AssertionError("New calls while closing must raise TEARDOWN_ERROR")
    allow_finish.set()
    t_worker.join(timeout=5.0)
    t_closer.join(timeout=5.0)
    check(close_done.is_set() and len(drain_res) == 1, "Expected drained call completion and clean close")

    # Subclass omitting slots=True under a frozen+slots base must be rejected
    @dataclass(frozen=True, slots=True)
    class _BaseSlotsCfg:
        alpha: int = 1

    @dataclass(frozen=True)
    class _SubMissingSlotsCfg(_BaseSlotsCfg):
        beta: str = "x"

    try:
        class _BadInheritedConfigMod(Module):
            id = "bad_inh_cfg"
            config_type = _SubMissingSlotsCfg

            @task
            def noop(self, ctx: TaskContext) -> None:
                _ = ctx
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for config_type subclass missing slots=True")

    # CLI DTO definition-time validation: optional Arg before required Arg, duplicate markers, fixed tuple, nested list
    def _bad_opt_before_req_arg() -> None:
        @dataclass(frozen=True, slots=True)
        class _DtoOptBeforeReq:
            first: Annotated[Optional[str], Arg()]
            second: Annotated[str, Arg()]

        class _M1(Module):
            id = "bad_arg_ord"

            @task(cli="run")
            def run_it(self, req: _DtoOptBeforeReq, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_dup_marker() -> None:
        @dataclass(frozen=True, slots=True)
        class _DtoDupMarker:
            x: Annotated[str, Arg(), Option()]

        class _M2(Module):
            id = "bad_dup_mk"

            @task(cli="run")
            def run_it(self, req: _DtoDupMarker, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_fixed_tuple() -> None:
        @dataclass(frozen=True, slots=True)
        class _DtoFixedTup:
            pair: Annotated[tuple[int, str], Option()]

        class _M3(Module):
            id = "bad_fix_tup"

            @task(cli="run")
            def run_it(self, req: _DtoFixedTup, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_nested_seq() -> None:
        @dataclass(frozen=True, slots=True)
        class _DtoNestedSeq:
            matrix: Annotated[list[list[int]], Option()]

        class _M4(Module):
            id = "bad_nest_seq"

            @task(cli="run")
            def run_it(self, req: _DtoNestedSeq, ctx: TaskContext) -> None:
                _ = (req, ctx)

    def _bad_literal_true_neg_collision() -> None:
        @dataclass(frozen=True, slots=True)
        class _DtoLitTrueNeg:
            force: Annotated[Literal[True], Option()] = True
            no_force: Annotated[str, Option()] = ""

        class _M5(Module):
            id = "bad_lit_neg"

            @task(cli="run")
            def run_it(self, req: _DtoLitTrueNeg, ctx: TaskContext) -> None:
                _ = (req, ctx)

    for fn_bad_cli in (_bad_opt_before_req_arg, _bad_dup_marker, _bad_fixed_tuple, _bad_nested_seq, _bad_literal_true_neg_collision):
        try:
            fn_bad_cli()
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError in {fn_bad_cli.__name__}")


class _SharedWriterGroup(TaskGroup):
    def on_init(self, env: ModuleEnv) -> None:
        _ = env
        owner = self.parent_module
        check(isinstance(owner, _SharedParentModule))
        if isinstance(owner, _SharedParentModule):
            owner.append_trace("writer:init")

    def on_close(self) -> None:
        owner = self.parent_module
        if isinstance(owner, _SharedParentModule):
            owner.append_trace("writer:close")

    @task("shared write")
    def write_note(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        owner = self.parent_module
        check(isinstance(owner, _SharedParentModule))
        if not isinstance(owner, _SharedParentModule):
            raise RuntimeError("missing parent_module")
        owner.append_trace(f"write:{req.tag}")
        sub = ctx.call("shparent.read_trace", {}, output_type=_EchoOut)
        check(sub.ok and sub.value is not None)
        sub_txt = sub.value.text if sub.value is not None else ""
        return _EchoOut(text=f"{owner.shared_label}:{req.tag}|{sub_txt}")


class _SharedReaderGroup(TaskGroup):
    def on_warmup(self) -> None:
        owner = self.parent_module
        if isinstance(owner, _SharedParentModule):
            owner.append_trace("reader:warmup")

    @task("shared read")
    def read_trace(self, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        owner = self.parent_module
        check(isinstance(owner, _SharedParentModule))
        if not isinstance(owner, _SharedParentModule):
            raise RuntimeError("missing parent_module")
        return _EchoOut(text=",".join(owner.trace_snapshot()))


class _SharedParentModule(Module):
    id = "shparent"
    groups = (_SharedWriterGroup, _SharedReaderGroup)

    def __init__(self, label: str = "init") -> None:
        self._label = label
        self._trace: list[str] = []

    @property
    def shared_label(self) -> str:
        return self._label

    def append_trace(self, entry: str) -> None:
        self._trace.append(entry)

    def trace_snapshot(self) -> tuple[str, ...]:
        return tuple(self._trace)

    def on_init(self, env: ModuleEnv) -> None:
        _ = env
        self._label = "ready"
        self.append_trace("parent:init")

    def on_close(self) -> None:
        self.append_trace("parent:close")


def _verify_taskgroup_parent_module_and_new_contracts(tmp_root: Path) -> None:
    standalone_grp = _SharedWriterGroup()
    check(standalone_grp.parent_module is None, "Standalone TaskGroup() must keep parent_module=None")

    ws_shared_p = tmp_root / "ws_sdk_shared_parent"
    ws_shared_p.mkdir(parents=True, exist_ok=True)
    parent_mod = _SharedParentModule()
    with YscbClient.local(HostPath(ws_shared_p), parent_mod) as client:
        w_out = client.call("shparent.write_note", _EchoIn(tag="alpha"), output_type=_EchoOut)
        check(
            w_out.ok and w_out.value == _EchoOut(text="ready:alpha|parent:init,writer:init,write:alpha"),
            f"Expected sibling TaskGroup to read shared parent state in same turn: {w_out}",
        )
    check(
        parent_mod.trace_snapshot() == ("parent:init", "writer:init", "write:alpha", "writer:close", "parent:close"),
        f"Unexpected shared parent lifecycle trace: {parent_mod.trace_snapshot()}",
    )

    check(SPACE_UPDATED_EVENT_ID == EventId("core.space_updated"))
    check(SPACE_REGISTRY_CHANGED_EVENT_ID == EventId("core.space_registry_changed"))
    check(SPACE_UPDATED_EVENT.event_id == SPACE_UPDATED_EVENT_ID and SPACE_UPDATED_EVENT.payload_type is SpaceUpdatedEventPayload)
    check(SPACE_REGISTRY_CHANGED_EVENT.event_id == SPACE_REGISTRY_CHANGED_EVENT_ID and SPACE_REGISTRY_CHANGED_EVENT.payload_type is SpaceUpdatedEventPayload)
    check(CONFIG_CHANGED_EVENT.event_id == CONFIG_CHANGED_EVENT_ID and CONFIG_CHANGED_EVENT.payload_type is ConfigChangedEventPayload)
    check(MODULE_INSTALLED_EVENT.event_id == MODULE_INSTALLED_EVENT_ID and MODULE_INSTALLED_EVENT.payload_type is ModuleLifecycleEventPayload)
    check(
        MODULE_REMOVING_EVENT.event_id == MODULE_REMOVING_EVENT_ID
        and MODULE_REMOVING_EVENT.payload_type is ModuleLifecycleEventPayload
        and MODULE_REMOVING_EVENT.ordering == EventOrdering.ORDERED
    )
    check(WORKSPACE_RELOADED_EVENT.event_id == WORKSPACE_RELOADED_EVENT_ID and WORKSPACE_RELOADED_EVENT.payload_type is Empty)
    check(WORKSPACE_RELOADED_EVENT_ID == EventId("core.workspace_reloaded"))
    check(MODULE_INSTALLED_EVENT_ID == EventId("core.module_installed"))
    check(MODULE_REMOVING_EVENT_ID == EventId("core.module_removing"))
    check(CONFIG_CHANGED_EVENT_ID == EventId("core.config_changed"))
    check(ClientRoutingPolicy.AUTO_SPAWN.value == "auto_spawn")
    check(ExecutionPriority.FOREGROUND.value == "foreground")

    ack_ok = SpaceAckCursorInput(
        space="  core/workspace  ",
        consumer="  ast_idx  ",
        from_gen=0,
        to_gen=3,
        config_hash="cfg_abc",
        merkle_root="mrk_123",
    )
    check(ack_ok.space == "core/workspace" and ack_ok.consumer == "ast_idx" and ack_ok.from_gen == 0 and ack_ok.to_gen == 3)
    ack_same_gen = SpaceAckCursorInput(
        space="core/workspace",
        consumer="ast_idx",
        from_gen=4,
        to_gen=4,
        config_hash="",
        merkle_root="",
    )
    check(ack_same_gen.from_gen == 4 and ack_same_gen.to_gen == 4)
    for bad_ack_fn in (
        lambda: SpaceAckCursorInput(space="not-a-space", consumer="c", from_gen=0, to_gen=1, config_hash="", merkle_root=""),
        lambda: SpaceAckCursorInput(space="core/workspace", consumer="   ", from_gen=0, to_gen=1, config_hash="", merkle_root=""),
        lambda: SpaceAckCursorInput(space="core/workspace", consumer="c", from_gen=-1, to_gen=1, config_hash="", merkle_root=""),
        lambda: SpaceAckCursorInput(space="core/workspace", consumer="c", from_gen=5, to_gen=4, config_hash="", merkle_root=""),
        lambda: SpaceAckCursorInput(space="core/workspace", consumer="c", from_gen=True, to_gen=2, config_hash="", merkle_root=""),
    ):
        assert_raises_val_error(bad_ack_fn)

    dyn_in = SetDynamicSpaceInput(
        owner=ModuleId("core"),
        name="tmp_sp",
        spec=SpaceSpec(space_id=SpaceId("core", "tmp_sp"), entries=(SemanticUri("project", ""),)),
    )
    clr_in = ClearDynamicSpaceInput(owner=ModuleId("core"), name="tmp_sp")
    scan_in = SpaceScanInput(space_id="core/workspace", force=True)
    check(dyn_in.name == "tmp_sp" and clr_in.name == "tmp_sp" and scan_in.space_id == "core/workspace" and scan_in.force)


class _ProfilerChildGroup(TaskGroup):
    def __init__(self) -> None:
        self.init_span_path: str = ""

    def on_init(self, env: ModuleEnv) -> None:
        prof: Profiler = env.profiler
        check(callable(prof.scope) and callable(prof.scope_relative) and callable(prof.snapshot))
        with prof.scope_relative("GroupInit"):
            self.init_span_path = prof.current_span_path()

    @task("prof group_work")
    def group_work(self, ctx: TaskContext) -> _EchoOut:
        prof: Profiler = ctx.profiler
        check(callable(prof.scope) and callable(prof.merge_subtree) and callable(prof.current_span_path))
        with prof.scope("GroupWork/Inner"):
            cur_path = prof.current_span_path()
        snap = prof.snapshot()
        rendered = render_profiler_tree(snap)
        check("GroupWork" in rendered and "Inner" in rendered, f"Expected profiler tree output: {rendered}")
        return _EchoOut(text=f"{self.init_span_path}|{cur_path}")


class _ProfilerShowcaseModule(Module):
    id: ClassVar[str] = "profmod"
    groups: ClassVar[tuple[type[TaskGroup], ...]] = (_ProfilerChildGroup,)

    def __init__(self) -> None:
        self.env_init_seen: bool = False

    def on_init(self, env: ModuleEnv) -> None:
        prof: Profiler = env.profiler
        check(callable(prof.scope))
        with prof.scope("ModInit"):
            self.env_init_seen = True

    @task("prof work")
    def work(self, ctx: TaskContext) -> _EchoOut:
        with ctx.profiler.scope("WorkRoot"):
            with ctx.profiler.scope_relative("SubStep"):
                span_path = ctx.profiler.current_span_path()
        snap = ctx.profiler.snapshot()
        check(isinstance(snap, ProfilerNodeSnapshot))
        check(any(ch.name == "WorkRoot" for ch in snap.children), f"Missing WorkRoot in {snap}")
        return _EchoOut(text=span_path)


def _verify_sdk_profiler_contracts(tmp_root: Path) -> None:
    null_p: Profiler = NullProfiler()
    check(callable(null_p.scope) and callable(null_p.snapshot))
    with null_p.scope("Noop"):
        check(null_p.current_span_path() == "")
    sess = ProfilerSession(root_name="sdk_unit")
    with sess.scope("StageA"):
        with sess.scope_relative("Step1"):
            check(sess.current_span_path() == "StageA/Step1")
    tree_txt = render_profiler_tree(sess.snapshot())
    check("sdk_unit" in tree_txt and "StageA" in tree_txt and "Step1" in tree_txt)

    ws_prof = tmp_root / "ws_sdk_profiler"
    ws_prof.mkdir(parents=True, exist_ok=True)
    mod = _ProfilerShowcaseModule()
    with YscbClient.local(HostPath(ws_prof), mod) as client:
        out_mod = client.call("profmod.work", output_type=_EchoOut)
        check(out_mod.ok and out_mod.value == _EchoOut(text="WorkRoot/SubStep"), f"Unexpected mod profiler output: {out_mod}")
        check(mod.env_init_seen, "Expected Module.on_init to receive env.profiler")
        out_grp = client.call("profmod.group_work", output_type=_EchoOut)
        check(
            out_grp.ok and out_grp.value is not None and out_grp.value.text.endswith("|GroupWork/Inner"),
            f"Unexpected group profiler output: {out_grp}",
        )


@dataclass(frozen=True, slots=True)
class _EqCoalesceIn:
    bucket: str
    detail: str


class _TypedParentModule(Module):
    id: ClassVar[str] = "typedp"

    def __init__(self) -> None:
        self.shared_label: str = "init_pending"

    def on_init(self, env: ModuleEnv) -> None:
        _ = env
        self.shared_label = "parent_ready"


class _TypedChildGroup(TaskGroup[_TypedParentModule]):
    @task
    def read_typed_parent(self, ctx: TaskContext) -> _EchoOut:
        check(self.parent_module is self.module)
        check(ctx.module_id == ModuleId("typedp"))
        return _EchoOut(text=f"{self.module.shared_label}:{ctx.module_id.value}")


class _TypedHostModule(_TypedParentModule):
    id: ClassVar[str] = "typedp"
    groups: ClassVar[tuple[type[TaskGroup[Module]], ...]] = (_TypedChildGroup,)


class _ErgonomicsProbeModule(Module):
    id: ClassVar[str] = "ergo"

    def __init__(self) -> None:
        self.runs: list[str] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    @task
    def ping_empty(self, ctx: TaskContext) -> _EchoOut:
        return _EchoOut(text=f"pong:{ctx.module_id.value}")

    @task
    def echo_req(self, req: _EchoIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        return _EchoOut(text=f"echo:{req.tag}")

    @task
    def call_via_refs(self, ctx: TaskContext) -> _EchoOut:
        empty_ref = TaskRef("ergo.ping_empty", Empty, _EchoOut)
        echo_ref = TaskRef("ergo.echo_req", _EchoIn, _EchoOut)
        r_empty = ctx.call(empty_ref)
        r_echo = ctx.call(echo_ref, _EchoIn(tag="typed_ok"))
        r_wrong = ctx.call(echo_ref, Empty())
        r_missing = ctx.call(echo_ref)
        r_conflict = ctx.call(echo_ref, _EchoIn(tag="x"), output_type=Empty)
        check(r_empty.ok and r_empty.value == _EchoOut(text="pong:ergo"), f"TaskRef Empty call failed: {r_empty}")
        check(r_echo.ok and r_echo.value == _EchoOut(text="echo:typed_ok"), f"TaskRef typed call failed: {r_echo}")
        check(
            not r_wrong.ok and r_wrong.error is not None and r_wrong.error.code == ErrorCode.CODEC_VALIDATION_FAILED,
            f"Wrong input_type must fail validation: {r_wrong}",
        )
        check(
            not r_missing.ok and r_missing.error is not None and r_missing.error.code == ErrorCode.CODEC_VALIDATION_FAILED,
            f"Missing non-Empty input must fail validation: {r_missing}",
        )
        check(
            not r_conflict.ok and r_conflict.error is not None and r_conflict.error.code == ErrorCode.CODEC_VALIDATION_FAILED,
            f"Conflicting output_type must fail validation: {r_conflict}",
        )
        return _EchoOut(text=f"{r_empty.value.text}|{r_echo.value.text}")

    @task(
        lock="ergo.eq_slot",
        concurrency=ConcurrencyMode.COALESCE,
        equivalence_fn=lambda req: req.bucket,
    )
    def coalesced_bucket(self, req: _EqCoalesceIn, ctx: TaskContext) -> _EchoOut:
        _ = ctx
        self.runs.append(f"{req.bucket}:{req.detail}")
        self.entered.set()
        self.release.wait(timeout=3.0)
        return _EchoOut(text=f"bucket:{req.bucket}")


def _verify_sdk_ergonomics_taskref_group_and_equivalence(tmp_root: Path) -> None:
    unbound = _TypedChildGroup()
    check(unbound.parent_module is None, "Unbound TaskGroup.parent_module must be None")
    raised_rt = False
    try:
        _ = unbound.module
    except RuntimeError:
        raised_rt = True
    check(raised_rt, "Unbound TaskGroup.module must raise RuntimeError")

    assert_raises_val_error(lambda: task(equivalence_fn=cast(object, 123)))
    for bad_ref_fn in (
        lambda: TaskRef("no_dot", Empty, _EchoOut),
        lambda: TaskRef("ergo.ping", type(None), _EchoOut),
        lambda: TaskRef("ergo.ping", Empty, type(None)),
        lambda: TaskRef("ergo.ping", cast(type[object], 123), _EchoOut),
    ):
        assert_raises_val_error(bad_ref_fn)

    ev_err_msg = ""
    try:
        class _BadNoMapperMod(Module):
            id: ClassVar[str] = "badnomap"

            @on_event(SPACE_UPDATED_EVENT)
            def on_ev(self, req: _EchoIn, ctx: TaskContext) -> None:
                _ = (req, ctx)
    except ValueError as exc:
        ev_err_msg = str(exc)
    check("mapper=" in ev_err_msg, f"Expected actionable mapper= hint in @on_event error: {ev_err_msg!r}")

    ws_ergo = tmp_root / "ws_sdk_ergonomics"
    ws_ergo.mkdir(parents=True, exist_ok=True)
    ergo_mod = _ErgonomicsProbeModule()
    with YscbClient.local(HostPath(ws_ergo), _TypedHostModule(), ergo_mod) as client:
        tp_out = client.call("typedp.read_typed_parent", output_type=_EchoOut)
        check(tp_out.ok and tp_out.value == _EchoOut(text="parent_ready:typedp"), f"Typed TaskGroup failed: {tp_out}")

        empty_ref = TaskRef("ergo.ping_empty", Empty, _EchoOut)
        echo_ref = TaskRef("ergo.echo_req", _EchoIn, _EchoOut)
        c_empty = client.call(empty_ref)
        c_echo = client.call(echo_ref, _EchoIn(tag="cli_ref"))
        c_bad = client.call(echo_ref, Empty())
        check(c_empty.ok and c_empty.value == _EchoOut(text="pong:ergo"), f"YscbClient TaskRef Empty failed: {c_empty}")
        check(c_echo.ok and c_echo.value == _EchoOut(text="echo:cli_ref"), f"YscbClient TaskRef typed failed: {c_echo}")
        check(
            not c_bad.ok and c_bad.error is not None and c_bad.error.code == ErrorCode.CODEC_VALIDATION_FAILED,
            f"YscbClient TaskRef wrong input must fail: {c_bad}",
        )

        ref_e2e = client.call("ergo.call_via_refs", output_type=_EchoOut)
        check(ref_e2e.ok and ref_e2e.value == _EchoOut(text="pong:ergo|echo:typed_ok"), f"ctx.call TaskRef failed: {ref_e2e}")

    ergo_ymod = ergo_mod.to_yscb_module()
    eq_bt = next(t for t in ergo_ymod.tasks() if t.task_id == TaskId("ergo.coalesced_bucket"))
    check(
        eq_bt.compute_normalized_equivalence({"bucket": "same", "detail": "a"})
        == eq_bt.compute_normalized_equivalence({"bucket": "same", "detail": "b"})
        == "ergo.coalesced_bucket:custom:same",
        "Custom equivalence_fn must normalize equal bucket keys identically",
    )
    check(
        eq_bt.compute_normalized_equivalence({"bucket": "other", "detail": "a"}) == "ergo.coalesced_bucket:custom:other",
        "Custom equivalence_fn must distinguish distinct bucket keys",
    )

    hot_ws = HostPath(ws_ergo / "hot_eq")
    hot_ws.path.mkdir(parents=True, exist_ok=True)

    class _EmptyModProvider(ModuleProviderPort):
        def list_modules(self) -> Sequence[ModuleDescriptor]:
            return ()

        def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
            _ = module_id
            return None

        def reload(self) -> None:
            pass

    hot_disp = RuntimeDispatcher(
        workspace_root=hot_ws,
        cache_dir=hot_ws.join(".cache"),
        module_provider=_EmptyModProvider(),
        options=DispatcherHostOptions(is_daemon_host=True, in_memory_modules=(ergo_ymod,)),
    )
    try:
        results: list[TaskOutcome[_EchoOut]] = []

        def _invoke_eq(detail: str) -> None:
            results.append(
                hot_disp.invoke(
                    InvokeRequest(
                        TaskId("ergo.coalesced_bucket"),
                        {"bucket": "same", "detail": detail},
                        hot_ws,
                        hot_ws,
                    ),
                    output_type=_EchoOut,
                )
            )

        t1 = threading.Thread(target=_invoke_eq, args=("first",))
        t2 = threading.Thread(target=_invoke_eq, args=("second_different_detail",))
        t1.start()
        check(ergo_mod.entered.wait(timeout=2.0), "First coalesced task did not enter")
        t2.start()
        time.sleep(0.15)
        ergo_mod.release.set()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)
        check(
            len(results) == 2 and all(r.ok and r.value == _EchoOut(text="bucket:same") for r in results),
            f"Coalesced equivalence_fn calls failed: {results}",
        )
        check(len(ergo_mod.runs) == 1, f"Expected custom equivalence_fn to coalesce into 1 run, got {ergo_mod.runs}")
        check(any(r.coalesced for r in results), f"Expected coalesced=True on follower outcome: {results}")
    finally:
        hot_disp.shutdown(grace_ms=300)


def _verify_secret_field_and_presentation_ssot() -> None:
    check(sdk.HumanRenderable is rt_mod.HumanRenderable)
    check(sdk.ExitCodeProvider is rt_mod.ExitCodeProvider)
    check(sdk_adv.format_output is rt_mod.format_output)

    @dataclass(frozen=True, slots=True)
    class _SecretCfgDto:
        endpoint: str = "https://api.example.test"
        api_token: str = secret_field(default="", metadata={"hint": "Bearer token"})
        extra_keys: tuple[str, ...] = secret_field(default_factory=tuple)

    @dataclass(frozen=True, slots=True)
    class _RequiredSecretDto:
        passphrase: str = secret_field()

    cfg = _SecretCfgDto(api_token="super-secret-value", extra_keys=("k1",))
    check(cfg.api_token == "super-secret-value" and cfg.extra_keys == ("k1",))
    check("super-secret-value" not in repr(cfg) and "k1" not in repr(cfg), f"secret_field leaked in repr: {repr(cfg)}")
    req_cfg = _RequiredSecretDto(passphrase="top-secret")
    check(req_cfg.passphrase == "top-secret" and "top-secret" not in repr(req_cfg))

    f_map = {f.name: f for f in _SecretCfgDto.__dataclass_fields__.values()}
    check(f_map["api_token"].metadata.get(SECRET_FIELD_METADATA_KEY) is True)
    check(f_map["api_token"].metadata.get("hint") == "Bearer token")
    check(f_map["extra_keys"].metadata.get(SECRET_FIELD_METADATA_KEY) is True)

    exported = SchemaExporter.export(_SecretCfgDto)
    props = exported["properties"]
    check(isinstance(props, dict))
    check(props["api_token"].get("writeOnly") is True and props["api_token"].get("x-yscb-secret") is True)
    check(props["extra_keys"].get("writeOnly") is True and props["extra_keys"].get("x-yscb-secret") is True)
    check("writeOnly" not in props["endpoint"] and "x-yscb-secret" not in props["endpoint"])

    assert_raises_val_error(lambda: secret_field(default="a", default_factory=lambda: "b"))
    assert_raises_val_error(lambda: secret_field(default_factory="not_callable"))
    assert_raises_val_error(lambda: secret_field(repr=cast(bool, "no")))
    assert_raises_val_error(lambda: secret_field(metadata=cast(object, ["bad"])))


def run_surface_sdk_suite(tmp_root: Path) -> None:
    """Execute the full Surface SDK test suite covering DSL, lifecycle, and YscbClient."""
    ws_base_p = tmp_root / "ws_sdk_base"
    ws_base_p.mkdir(parents=True, exist_ok=True)
    ws_base = HostPath(ws_base_p)

    _verify_facade_and_zero_leak()
    _verify_secret_field_and_presentation_ssot()
    _verify_declarative_metadata_and_stacking(ws_base)
    _verify_compile_time_validation(ws_base)
    _verify_dual_track_rendering(ws_base)
    _verify_lifecycle_and_lifo_isolation(tmp_root)
    _verify_in_memory_and_client_e2e(tmp_root)
    _verify_wave12_sdk_extensions(tmp_root)
    _verify_taskgroup_parent_module_and_new_contracts(tmp_root)
    _verify_sdk_profiler_contracts(tmp_root)
    _verify_sdk_ergonomics_taskref_group_and_equivalence(tmp_root)
    log("[SURFACE-SDK] Surface SDK verification suite PASSED")


__all__ = ("run_surface_sdk_suite",)
