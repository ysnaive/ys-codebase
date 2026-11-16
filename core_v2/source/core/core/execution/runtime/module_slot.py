"""Compile-time isolated module loader (_ScopedModuleFinder) and epoch-guarded LocalModuleSlotRegistry."""

from __future__ import annotations

import builtins
import dataclasses
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import importlib
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder, SourceFileLoader
from importlib.util import spec_from_file_location
import os
from pathlib import Path
import sys
import threading
import time
import types
from typing import Callable, ClassVar, Mapping, Optional, Sequence, TypeVar, overload
import uuid

from core.execution.event import CausalLineage, EventMetadata, TaskLocalOutbox
from core.execution.lifecycle import ContainerState, LifoResourceStack, WorkerContainerLifecycle
from core.execution.runtime.contracts import (
    BoundTask,
    ClientRoutingPolicy,
    ExecutionPriority,
    ModuleDescriptor,
    TaskContext,
    TaskOutcome,
    TaskRouteSpec,
    YscbModule,
    decode_outcome_as,
)
from core.execution.runtime.wire import WorkerEquivReply, WorkerMapBatchReply, WorkerStepReply
from core.filesystem.fs import (
    is_contained_nonsymlink_path,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    resolve_contained_child_dir,
    try_resolve_contained_subpath,
    walk_nonsymlink_dir_tree,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError, is_fatal_error_code, safe_exception_summary
from core.foundation.observability import CancellationToken, ProgressEvent, clamp_wait_sec, guard_standard_streams
from core.foundation.primitives import (
    EventId,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    TaskId,
    invoke_observer_safely,
    require_non_none,
)

TOut = TypeVar("TOut")
TPayload = TypeVar("TPayload")

_SCOPED_PKG_PREFIX = "_yscb_v2_mod_"
TaggedCloser = tuple[str, Callable[[], Sequence[ErrorDetail]]]


def _infer_caller_scoped_pkg() -> Optional[str]:
    frame: Optional[types.FrameType] = sys._getframe(1)
    while frame is not None:
        mod_name = frame.f_globals.get("__name__")
        is_int = isinstance(mod_name, str) and (
            mod_name in (__name__, "importlib") or mod_name.startswith(("importlib.", "_frozen_importlib"))
        )
        if not is_int:
            return mod_name.split(".", 1)[0] if (isinstance(mod_name, str) and mod_name.startswith(_SCOPED_PKG_PREFIX)) else None
        frame = frame.f_back
    return None


@dataclass(slots=True)
class LoadedModuleArtifact:
    """Pairs an instantiated YscbModule with its isolated sys.modules package key and generation refcount."""

    instance: YscbModule
    package_key: str
    in_flight: int = 0


@dataclass(frozen=True, slots=True)
class StepContextCallbacks:
    """Structured callbacks bridging a running TaskContext back to Master or local TurnEngine."""

    on_emit_imm: Callable[[EventId, JsonObject, CausalLineage, bool], None]
    on_invoke_task: Callable[[TaskId, JsonObject, Optional[HostPath], Optional[ClientRoutingPolicy]], TaskOutcome[JsonValue]]
    on_progress: Callable[[JsonObject], None]


@dataclass(frozen=True, slots=True)
class LocalStepExecutionSpec:
    """Encapsulated specification for executing one BoundTask step inside a slot registry."""

    task_id: TaskId
    raw_input: JsonObject
    caller_cwd: HostPath
    caller_env: Mapping[str, str]
    base_lineage: CausalLineage
    cancel_token: CancellationToken
    priority_getter: Callable[[], ExecutionPriority]
    callbacks: StepContextCallbacks
    interactive_tty: bool = False


def _entry_is_contained_py(ent: os.DirEntry[str], mod_dir: Path) -> bool:
    if not ent.name.endswith(".py") or ent.is_symlink() or is_symlink_or_reparse(ent.path):
        return False
    try:
        return ent.is_file(follow_symlinks=False) and is_contained_nonsymlink_path(mod_dir, ent.path)
    except OSError:
        return False


def _subdir_has_nonsymlink_py(sub_dir: Path, mod_dir: Path) -> bool:
    if not is_contained_nonsymlink_path(mod_dir, sub_dir, is_dir=True):
        return False
    for _cur_dir, entries in walk_nonsymlink_dir_tree(str(sub_dir), ignored_dir_prefixes=(".", "__pycache__")):
        if any(_entry_is_contained_py(ent, mod_dir) for ent in entries):
            return True
    return False


def _dir_is_scoped_package(sub_dir: Path, mod_dir: Path, top_name: Optional[str]) -> bool:
    if not sub_dir.is_dir() or not is_contained_nonsymlink_path(mod_dir, sub_dir, is_dir=True):
        return False
    init_py = sub_dir / "__init__.py"
    if init_py.is_file() and is_contained_nonsymlink_path(mod_dir, init_py):
        return True
    if top_name is not None and (
        top_name in sys.stdlib_module_names or PathFinder.find_spec(top_name) is not None
    ):
        return False
    try:
        return _subdir_has_nonsymlink_py(sub_dir, mod_dir)
    except OSError:
        return False


def _has_contained_sibling(mod_dir: Path, top_name: str) -> bool:
    if not top_name or top_name.startswith((".", "__pycache__")) or top_name in sys.stdlib_module_names:
        return False
    py_file = mod_dir / f"{top_name}.py"
    if py_file.is_file() and is_contained_nonsymlink_path(mod_dir, py_file):
        return True
    return _dir_is_scoped_package(mod_dir / top_name, mod_dir, top_name=top_name)


def _resolve_scoped_sibling_target(
    unique_pkg: str,
    mod_dir: Path,
    name: str,
) -> Optional[tuple[str, str]]:
    if not name or name.startswith("."):
        return None
    top = name.split(".", 1)[0]
    if top == "core" or top.startswith(_SCOPED_PKG_PREFIX) or not _has_contained_sibling(mod_dir, top):
        return None
    return (f"{unique_pkg}.{name}", f"{unique_pkg}.{top}")


def _make_scoped_builtins(unique_pkg: str, mod_dir: Path) -> dict[str, object]:
    std_import = importlib.__import__

    def _scoped_import(
        name: str,
        globals_ns: Optional[Mapping[str, object]] = None,
        locals_ns: Optional[Mapping[str, object]] = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> object:
        if level == 0 and isinstance(name, str):
            resolved = _resolve_scoped_sibling_target(unique_pkg, mod_dir, name)
            if resolved is not None:
                scoped_full, scoped_top = resolved
                if fromlist:
                    return std_import(scoped_full, globals_ns, locals_ns, fromlist, 0)
                std_import(scoped_full, globals_ns, locals_ns, ("__doc__",), 0)
                return sys.modules[scoped_top]
        return std_import(name, globals_ns, locals_ns, fromlist, level)

    ns = dict(builtins.__dict__)
    ns["__import__"] = _scoped_import
    return ns


class _ScopedSourceLoader(SourceFileLoader):
    """Compiles and executes module & sibling files directly under their isolated package namespace."""

    def __init__(self, fullname: str, path_str: str, unique_pkg: str, mod_dir: Path) -> None:
        super().__init__(fullname, path_str)
        self._unique_pkg = unique_pkg
        self._mod_dir = mod_dir

    def get_data(self, path: str) -> bytes:
        if not is_contained_nonsymlink_path(self._mod_dir, path):
            raise OSError(f"Module source path escaped or traversed symlink: {path}")
        data = read_nofollow_regular_bytes(path)
        if data is None:
            raise OSError(f"Module source is not a readable non-symlink regular file: {path}")
        return data

    def get_code(self, fullname: str) -> types.CodeType:
        src_path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(src_path), src_path)

    def exec_module(self, module: types.ModuleType) -> None:
        module.__dict__["__builtins__"] = _make_scoped_builtins(self._unique_pkg, self._mod_dir)
        super().exec_module(module)


def _build_contained_subspec(
    fullname: str,
    unique_pkg: str,
    mod_dir: Path,
    rel_parts: Sequence[str],
) -> Optional[ModuleSpec]:
    rel_target = mod_dir.joinpath(*rel_parts)
    init_py = rel_target / "__init__.py"
    if init_py.is_file() and is_contained_nonsymlink_path(mod_dir, init_py):
        loader = _ScopedSourceLoader(fullname, str(init_py), unique_pkg, mod_dir)
        pkg_spec = spec_from_file_location(
            fullname,
            str(init_py),
            loader=loader,
            submodule_search_locations=[],
        )
        if pkg_spec is not None and pkg_spec.submodule_search_locations is not None:
            pkg_spec.submodule_search_locations.clear()
        return pkg_spec
    mod_py = rel_target.with_suffix(".py")
    if mod_py.is_file() and is_contained_nonsymlink_path(mod_dir, mod_py):
        loader = _ScopedSourceLoader(fullname, str(mod_py), unique_pkg, mod_dir)
        return spec_from_file_location(fullname, str(mod_py), loader=loader)
    top_chk = rel_parts[0] if len(rel_parts) == 1 else None
    if not rel_parts[-1].startswith((".", "__pycache__")) and _dir_is_scoped_package(
        rel_target, mod_dir, top_name=top_chk
    ):
        ns_spec = ModuleSpec(fullname, None, is_package=True)
        ns_spec.submodule_search_locations = []
        return ns_spec
    return None


class _ScopedModuleFinder(MetaPathFinder):
    """Process-wide MetaPathFinder exclusively owning _yscb_v2_mod_<id>_<hex>.* packages."""

    def __init__(self, lock: threading.RLock) -> None:
        self._lock = lock
        self._roots: dict[str, Path] = {}

    def register_package(self, unique_pkg: str, mod_dir: Path) -> None:
        with self._lock:
            self._roots[unique_pkg] = mod_dir

    def get_package_root(self, unique_pkg: str) -> Optional[Path]:
        with self._lock:
            return self._roots.get(unique_pkg)

    def unregister_package(self, pkg_or_entry: str) -> bool:
        unique_pkg = pkg_or_entry.split(".", 1)[0]
        prefix = f"{unique_pkg}."
        with self._lock:
            self._roots.pop(unique_pkg, None)
            sys.modules.pop(unique_pkg, None)
            for key, val in list(sys.modules.items()):
                if key.startswith(prefix) or (isinstance(val, types.ModuleType) and val.__name__.startswith(prefix)):
                    sys.modules.pop(key, None)
            return bool(self._roots)

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]] = None,
        target: Optional[types.ModuleType] = None,
    ) -> Optional[ModuleSpec]:
        _ = (path, target)
        if not fullname.startswith(_SCOPED_PKG_PREFIX):
            return None
        parts = fullname.split(".")
        if len(parts) < 2:
            raise ImportError(f"Missing scoped package '{fullname}'", name=fullname)
        mod_dir = self.get_package_root(parts[0])
        if mod_dir is None:
            raise ImportError(f"Unregistered scoped package '{fullname}'", name=fullname)
        spec = _build_contained_subspec(fullname, parts[0], mod_dir, parts[1:])
        if spec is None:
            raise ImportError(f"Blocked uncontained or missing scoped module '{fullname}'", name=fullname)
        return spec


def _resolve_scoped_relative_package(
    orig_fn: Callable[[str, Optional[str]], types.ModuleType],
    active_pkg: str,
    mod_dir: Path,
    package: Optional[str],
) -> Optional[str]:
    if not package or package == "__entry__" or package == f"{active_pkg}.__entry__":
        return active_pkg
    if package.endswith(".__entry__") and package.startswith(f"{active_pkg}."):
        return package[: -len(".__entry__")]
    if package == active_pkg or package.startswith(f"{active_pkg}."):
        return package
    pkg_top = package.split(".", 1)[0]
    if not package.startswith(_SCOPED_PKG_PREFIX) and _has_contained_sibling(mod_dir, pkg_top):
        scoped_pkg = f"{active_pkg}.{package}"
        orig_fn(scoped_pkg, None)
        return scoped_pkg
    return None


def _try_import_in_scoped_package(
    orig_fn: Callable[[str, Optional[str]], types.ModuleType],
    active_pkg: str,
    mod_dir: Path,
    name: str,
    package: Optional[str],
) -> Optional[types.ModuleType]:
    if name.startswith("."):
        scoped_pkg = _resolve_scoped_relative_package(orig_fn, active_pkg, mod_dir, package)
        return orig_fn(name, scoped_pkg) if scoped_pkg is not None else None
    resolved = _resolve_scoped_sibling_target(active_pkg, mod_dir, name)
    return orig_fn(resolved[0], None) if resolved is not None else None


class ProtectedModuleLoader:
    """Loads YscbModule instances strictly from <workspace_root>/.modules/<module_id>/ with zero sys.path or global sys.modules pollution."""

    _FINDER_LOCK: ClassVar[threading.RLock] = threading.RLock()
    _FINDER: ClassVar[Optional[_ScopedModuleFinder]] = None
    _ORIG_IMPORT_MODULE: ClassVar[Optional[Callable[[str, Optional[str]], types.ModuleType]]] = None

    def __init__(self, workspace_root: HostPath) -> None:
        self._workspace_root = workspace_root

    @classmethod
    def _scoped_import_module(cls, name: str, package: Optional[str] = None) -> types.ModuleType:
        orig_fn = require_non_none(cls._ORIG_IMPORT_MODULE)
        finder = cls._FINDER
        if finder is None:
            return orig_fn(name, package)
        active_pkg = _infer_caller_scoped_pkg()
        mod_root = finder.get_package_root(active_pkg) if active_pkg is not None else None
        if mod_root is not None and active_pkg is not None and isinstance(name, str) and name:
            scoped_mod = _try_import_in_scoped_package(orig_fn, active_pkg, mod_root, name, package)
            if scoped_mod is not None:
                return scoped_mod
        return orig_fn(name, package)

    @classmethod
    def _ensure_finder(cls) -> _ScopedModuleFinder:
        with cls._FINDER_LOCK:
            if cls._FINDER is None:
                cls._FINDER = _ScopedModuleFinder(cls._FINDER_LOCK)
            if cls._FINDER not in sys.meta_path:
                sys.meta_path.append(cls._FINDER)
            if cls._ORIG_IMPORT_MODULE is None:
                cls._ORIG_IMPORT_MODULE = importlib.import_module
            if importlib.import_module != cls._scoped_import_module:
                importlib.import_module = cls._scoped_import_module
            return cls._FINDER

    @classmethod
    def _deactivate_finder_if_empty_locked(cls, finder: _ScopedModuleFinder) -> None:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        if cls._ORIG_IMPORT_MODULE is not None and importlib.import_module == cls._scoped_import_module:
            importlib.import_module = cls._ORIG_IMPORT_MODULE

    @classmethod
    def cleanup_package(cls, pkg_or_entry: str) -> None:
        unique_pkg = pkg_or_entry.split(".", 1)[0]
        if not unique_pkg:
            return
        DataclassCodec.evict_module_prefix(unique_pkg)
        with cls._FINDER_LOCK:
            finder = cls._FINDER
            if finder is None:
                return
            still_has_pkgs = finder.unregister_package(unique_pkg)
            if not still_has_pkgs:
                cls._deactivate_finder_if_empty_locked(finder)

    def load_module_artifact(self, descriptor: ModuleDescriptor) -> LoadedModuleArtifact:
        entry_path, mod_hp = self._verify_containment_and_resolve_entry(descriptor)
        safe_id = str(descriptor.module_id).replace("-", "_")
        unique_pkg = f"{_SCOPED_PKG_PREFIX}{safe_id}_{uuid.uuid4().hex[:8]}"
        mod_dir = mod_hp.path
        with self._FINDER_LOCK:
            finder = self._ensure_finder()
            finder.register_package(unique_pkg, mod_dir)
        try:
            pkg_mod = types.ModuleType(unique_pkg)
            pkg_mod.__path__ = []
            pkg_mod.__package__ = unique_pkg
            sys.modules[unique_pkg] = pkg_mod
            rel_parts = entry_path.path.relative_to(mod_dir).parts[:-1]
            parent_pkg = ".".join((unique_pkg, *rel_parts)) if rel_parts else unique_pkg
            if rel_parts:
                importlib.import_module(parent_pkg)
            entry_mod_name = f"{parent_pkg}.__entry__"
            loader = _ScopedSourceLoader(entry_mod_name, str(entry_path), unique_pkg, mod_dir)
            spec = spec_from_file_location(entry_mod_name, str(entry_path), loader=loader)
            if spec is None:
                raise YscbError(ErrorCode.MODULE_DEGRADED, f"Cannot create module spec for {entry_path}")
            py_mod = importlib.util.module_from_spec(spec)
            py_mod.__package__ = parent_pkg
            sys.modules[entry_mod_name] = py_mod
            loader.exec_module(py_mod)
            factory = py_mod.__dict__.get("create_module")
            if not callable(factory):
                raise YscbError(
                    ErrorCode.MODULE_DEGRADED,
                    f"Module '{descriptor.module_id}' must define create_module() -> YscbModule.",
                )
            instance = factory()
            if not isinstance(instance, YscbModule):
                raise YscbError(
                    ErrorCode.MODULE_DEGRADED,
                    f"create_module() in '{descriptor.module_id}' did not return a YscbModule.",
                )
            return LoadedModuleArtifact(instance=instance, package_key=entry_mod_name)
        except BaseException:
            self.cleanup_package(unique_pkg)
            raise

    def _verify_containment_and_resolve_entry(self, descriptor: ModuleDescriptor) -> tuple[HostPath, HostPath]:
        mods_hp = try_resolve_contained_subpath(self._workspace_root, ".modules")
        mod_hp = (
            resolve_contained_child_dir(mods_hp, descriptor.module_dir, guarded_name=str(descriptor.module_id))
            if mods_hp is not None
            else None
        )
        if mod_hp is None or str(descriptor.module_id) == "core" or mod_hp.path.name.lower() == "core":
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                f"Module '{descriptor.module_id}' directory '{descriptor.module_dir}' violates .modules/ boundary.",
            )
        rel_entry = Path(descriptor.entry_file)
        raw_entry = mod_hp.path.joinpath(*rel_entry.parts) if not rel_entry.is_absolute() else rel_entry
        if rel_entry.is_absolute() or ".." in rel_entry.parts or not is_contained_nonsymlink_path(
            mod_hp.path, raw_entry
        ):
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                f"Module '{descriptor.module_id}' entry_file '{descriptor.entry_file}' escapes or traverses symlink.",
            )
        if not raw_entry.is_file():
            raise YscbError(ErrorCode.TASK_NOT_FOUND, f"Module entry file missing: {raw_entry}")
        return (HostPath(raw_entry), mod_hp)


class _StepTaskContext(TaskContext):
    """Concrete per-step TaskContext forwarding emit, emit_imm, invoke_task, and progress."""

    def __init__(self, workspace_root: HostPath, spec: LocalStepExecutionSpec, outbox: TaskLocalOutbox) -> None:
        self._workspace_root = workspace_root
        self._spec = spec
        self._caller_env = dict(spec.caller_env)
        self._outbox = outbox

    @property
    def workspace_root(self) -> HostPath:
        return self._workspace_root

    @property
    def caller_cwd(self) -> HostPath:
        return self._spec.caller_cwd

    @property
    def caller_env(self) -> Mapping[str, str]:
        return self._caller_env

    @property
    def cancel_token(self) -> CancellationToken:
        return self._spec.cancel_token

    @property
    def effective_priority(self) -> ExecutionPriority:
        return self._spec.priority_getter()

    def _encode_typed_event_payload(self, event_meta: EventMetadata[TPayload], payload: object) -> JsonObject:
        if not isinstance(event_meta, EventMetadata):
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"emit requires EventMetadata instance, got {event_meta!r}",
                source_task=str(self._spec.task_id),
            )
        try:
            return DataclassCodec.encode_object(payload, expected_type=event_meta.payload_type)
        except YscbError as exc:
            det = exc.detail.with_fallback_task(str(self._spec.task_id))
            raise YscbError(det.code, det.message, remediation=det.remediation, source_task=det.source_task) from exc

    def emit(self, event_meta: EventMetadata[TPayload], payload: TPayload) -> None:
        raw_obj = self._encode_typed_event_payload(event_meta, payload)
        self._outbox.stage(event_meta.event_id, raw_obj, ordering=event_meta.ordering)

    def emit_imm(self, event_meta: EventMetadata[TPayload], payload: TPayload, *, strict: bool = False) -> None:
        if not isinstance(strict, bool):
            raise ValueError(f"emit_imm strict must be a bool, got {strict!r}")
        raw_obj = self._encode_typed_event_payload(event_meta, payload)
        imm_lin = self._outbox.compute_immediate_lineage(event_meta.event_id)
        self._spec.callbacks.on_emit_imm(event_meta.event_id, raw_obj, imm_lin, strict)

    @overload
    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: type[TOut],
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: None = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[JsonValue]: ...

    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: Optional[type[TOut]] = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]:
        try:
            tid = task_id if isinstance(task_id, TaskId) else TaskId(task_id)
        except ValueError as exc:
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, safe_exception_summary(exc), source_task=str(self._spec.task_id)),
            )
        if target_workspace is not None and not isinstance(target_workspace, HostPath):
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"target_workspace must be HostPath or None, got {target_workspace!r}",
                    source_task=str(tid),
                ),
            )
        if routing_policy is not None and not isinstance(routing_policy, ClientRoutingPolicy):
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"routing_policy must be ClientRoutingPolicy or None, got {routing_policy!r}",
                    source_task=str(tid),
                ),
            )
        try:
            encoded_in = DataclassCodec.encode_object(input_obj)
        except YscbError as exc:
            return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(tid)))
        raw_out = self._spec.callbacks.on_invoke_task(tid, encoded_in, target_workspace, routing_policy)
        if output_type is not None:
            return decode_outcome_as(raw_out, output_type, source_task=str(tid))
        return raw_out

    def report_progress(self, progress: ProgressEvent) -> None:
        encoded = DataclassCodec.encode_object(progress, expected_type=ProgressEvent)
        invoke_observer_safely(lambda: self._spec.callbacks.on_progress(encoded))


class _SlotPhase(Enum):
    UNLOADED = "unloaded"
    ARTIFACT_LOADED = "artifact_loaded"
    INITIALIZED = "initialized"
    STARTED = "started"


@dataclass(slots=True)
class _ModuleSlot:
    """Single epoch-checked state machine per module preventing concurrent quiesce/unload resurrection."""

    module_id: ModuleId
    descriptor: Optional[ModuleDescriptor] = None
    phase: _SlotPhase = _SlotPhase.UNLOADED
    epoch: int = 0
    starting: bool = False
    load_lock: threading.RLock = field(default_factory=threading.RLock)
    artifact: Optional[LoadedModuleArtifact] = None
    tasks: dict[TaskId, BoundTask] = field(default_factory=dict)
    retiring: list[tuple[LoadedModuleArtifact, tuple[TaggedCloser, ...]]] = field(default_factory=list)

    def has_active_or_retiring_work(self) -> bool:
        if self.artifact is not None and self.artifact.in_flight > 0:
            return True
        return any(r_art.in_flight > 0 for r_art, _rc in self.retiring)


@dataclass(frozen=True, slots=True)
class _SlotInitClaim:
    matched: bool
    need_init: bool = False
    need_start: bool = False
    start_epoch: int = 0
    ready_instance: Optional[YscbModule] = None
    pinned_artifact: Optional[LoadedModuleArtifact] = None


def _routes_match_manifest(declared: TaskRouteSpec, actual: TaskRouteSpec) -> bool:
    if actual.cli is not None and declared.cli != actual.cli:
        return False
    return dataclasses.replace(declared, cli=None) == dataclasses.replace(actual, cli=None)


def _validate_and_bind_module_tasks(
    module_id: ModuleId,
    desc: ModuleDescriptor,
    instance: YscbModule,
) -> dict[TaskId, BoundTask]:
    if instance.module_id != module_id:
        raise YscbError(
            ErrorCode.MODULE_DEGRADED,
            f"Module '{module_id}' returned mismatched YscbModule.module_id '{instance.module_id}'.",
        )
    raw_seq = instance.tasks()
    if isinstance(raw_seq, (str, bytes, bytearray, memoryview)) or not isinstance(raw_seq, Sequence):
        raise YscbError(ErrorCode.MODULE_DEGRADED, f"Module '{module_id}'.tasks() must return a Sequence of BoundTask.")
    raw_by_id: dict[TaskId, BoundTask] = {}
    for item in raw_seq:
        if not isinstance(item, BoundTask):
            raise YscbError(ErrorCode.MODULE_DEGRADED, f"Module '{module_id}'.tasks() yielded non-BoundTask {item!r}.")
        if item.task_id.module_id != module_id:
            raise YscbError(
                ErrorCode.MODULE_DEGRADED,
                f"Module '{module_id}' cannot register foreign task '{item.task_id}'.",
            )
        rspec = item.route_spec
        if not isinstance(rspec, TaskRouteSpec) or rspec.task_id != item.task_id:
            raise YscbError(ErrorCode.MODULE_DEGRADED, f"Task '{item.task_id}' in '{module_id}' returned invalid route_spec.")
        if item.task_id in raw_by_id:
            raise YscbError(ErrorCode.MODULE_DEGRADED, f"Module '{module_id}' registered duplicate task '{item.task_id}'.")
        raw_by_id[item.task_id] = item
    if not desc.declared_tasks:
        return raw_by_id
    bound: dict[TaskId, BoundTask] = {}
    for decl_spec in desc.declared_tasks:
        actual_task = raw_by_id.get(decl_spec.task_id)
        if actual_task is None or not _routes_match_manifest(decl_spec, actual_task.route_spec):
            raise YscbError(
                ErrorCode.MODULE_DEGRADED,
                f"Task '{decl_spec.task_id}' in module '{module_id}' diverges from declared TaskRouteSpec.",
            )
        bound[decl_spec.task_id] = actual_task
    return bound


class LocalModuleSlotRegistry:
    """Manages loaded YscbModule instances with epoch-checked load/unload transitions and shared container SSOT."""

    def __init__(
        self,
        workspace_root: HostPath,
        lifo_stack: LifoResourceStack,
        *,
        container: Optional[WorkerContainerLifecycle] = None,
        is_module_quiesced: Optional[Callable[[ModuleId], bool]] = None,
        require_eager_start: bool = False,
        on_module_initialized: Optional[Callable[[ModuleId], None]] = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._loader = ProtectedModuleLoader(workspace_root)
        self._lifo_stack = lifo_stack
        self._container = container or WorkerContainerLifecycle()
        self._is_quiesced_fn = is_module_quiesced
        self._require_eager_start = require_eager_start
        self._on_module_initialized = on_module_initialized
        self._lock = threading.RLock()
        self._drain_cond = threading.Condition(self._lock)
        self._slots: dict[ModuleId, _ModuleSlot] = {}
        self._pending_teardown_diags: deque[ErrorDetail] = deque(maxlen=256)

    @property
    def workspace_root(self) -> HostPath:
        return self._workspace_root

    def _record_pending_teardown_diags(self, diags: Sequence[ErrorDetail]) -> None:
        if not diags:
            return
        with self._lock:
            self._pending_teardown_diags.extend(diags)

    def drain_pending_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        with self._lock:
            if not self._pending_teardown_diags:
                return ()
            out = tuple(self._pending_teardown_diags)
            self._pending_teardown_diags.clear()
            return out

    def _slot_locked(self, module_id: ModuleId) -> _ModuleSlot:
        slot = self._slots.get(module_id)
        if slot is None:
            slot = _ModuleSlot(module_id=module_id)
            self._slots[module_id] = slot
        return slot

    def _is_unavailable_locked(self, slot: _ModuleSlot) -> bool:
        if self._container.state == ContainerState.STOPPED:
            return True
        return (
            slot.module_id != ModuleId("core")
            and self._is_quiesced_fn is not None
            and self._is_quiesced_fn(slot.module_id)
        )

    def register_descriptors(self, descriptors: Sequence[ModuleDescriptor]) -> None:
        changed_slots: list[_ModuleSlot] = []
        with self._lock:
            new_map = {d.module_id: d for d in descriptors}
            for mid, slot in list(self._slots.items()):
                new_d = new_map.get(mid)
                old_d = slot.descriptor
                changed = (
                    new_d is None
                    or old_d is None
                    or new_d.module_dir != old_d.module_dir
                    or new_d.entry_file != old_d.entry_file
                    or new_d.declared_tasks != old_d.declared_tasks
                )
                if changed and (slot.artifact is not None or old_d is not None):
                    slot.epoch += 1
                    changed_slots.append(slot)
                slot.descriptor = new_d
            cleared_mods = frozenset(s.module_id for s in changed_slots)
            to_close, to_purge = self._detach_slots_batch_locked(changed_slots)
            for mid, slot in list(self._slots.items()):
                if slot.descriptor is None and slot.artifact is None and not slot.retiring:
                    self._slots.pop(mid, None)
            for mid, desc in new_map.items():
                self._slot_locked(mid).descriptor = desc
        if cleared_mods:
            self._container.clear_degraded(cleared_mods)
        try:
            if to_close:
                self._record_pending_teardown_diags(LifoResourceStack.run_closers(to_close))
        finally:
            for pkg in to_purge:
                ProtectedModuleLoader.cleanup_package(pkg)

    def _detach_slots_batch_locked(
        self,
        slots: Sequence[_ModuleSlot],
    ) -> tuple[tuple[TaggedCloser, ...], list[str]]:
        if not slots:
            return ((), [])
        idle_prefixes: set[str] = set()
        immediate_pkgs: list[str] = []
        for slot in slots:
            art = slot.artifact
            slot.artifact = None
            slot.phase = _SlotPhase.UNLOADED
            slot.tasks.clear()
            prefix = str(slot.module_id)
            if art is not None and art.in_flight > 0:
                slot.retiring.append((art, self._lifo_stack.pop_tagged_by_prefixes(frozenset({prefix}))))
            else:
                idle_prefixes.add(prefix)
                if art is not None:
                    immediate_pkgs.append(art.package_key)
        immediate_closers = self._lifo_stack.pop_tagged_by_prefixes(frozenset(idle_prefixes))
        return (immediate_closers, immediate_pkgs)

    def _raise_if_degraded(self, module_id: ModuleId, fallback_task: Optional[str] = None) -> None:
        deg = self._container.get_degraded(module_id)
        if deg is not None:
            raise YscbError(
                deg.code,
                deg.message,
                remediation=deg.remediation,
                source_task=deg.source_task or fallback_task,
            )

    def ensure_module_artifact_loaded(self, module_id: ModuleId, *, record_runtime_degraded: bool = True) -> YscbModule:
        with self._lock:
            slot = self._slot_locked(module_id)
            if self._is_unavailable_locked(slot):
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' is quiesced.")
            if slot.artifact is not None:
                return slot.artifact.instance
            load_lk = slot.load_lock

        with load_lk:
            deg = (
                self._container.get_degraded(module_id)
                if record_runtime_degraded
                else self._container.get_runtime_degraded(module_id)
            )
            if deg is not None:
                raise YscbError(deg.code, deg.message, remediation=deg.remediation, source_task=deg.source_task)
            for _attempt in range(3):
                loaded = self._try_load_artifact_once(module_id, record_runtime_degraded=record_runtime_degraded)
                if loaded is not None:
                    return loaded
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' concurrently reloaded during load.")

    def _try_load_artifact_once(
        self,
        module_id: ModuleId,
        *,
        record_runtime_degraded: bool = True,
    ) -> Optional[YscbModule]:
        with self._lock:
            slot = self._slot_locked(module_id)
            if self._is_unavailable_locked(slot):
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' is quiesced.")
            if slot.artifact is not None:
                return slot.artifact.instance
            desc, start_ep = slot.descriptor, slot.epoch
        if desc is None:
            raise YscbError(ErrorCode.TASK_NOT_FOUND, f"Module '{module_id}' is not registered.")
        art, bound_tasks = self._load_and_bind_tasks(
            module_id, desc, record_runtime_degraded=record_runtime_degraded
        )
        return self._commit_loaded_artifact(module_id, slot, art, bound_tasks, start_ep)

    def introspect_bound_route_specs(self, module_id: ModuleId) -> tuple[TaskRouteSpec, ...]:
        self.ensure_module_artifact_loaded(module_id, record_runtime_degraded=False)
        with self._lock:
            slot = self._slots.get(module_id)
            return tuple(t.route_spec for t in slot.tasks.values()) if slot is not None else ()

    def _load_and_bind_tasks(
        self,
        module_id: ModuleId,
        desc: ModuleDescriptor,
        *,
        record_runtime_degraded: bool,
    ) -> tuple[LoadedModuleArtifact, dict[TaskId, BoundTask]]:
        try:
            art = self._loader.load_module_artifact(desc)
            try:
                return (art, _validate_and_bind_module_tasks(module_id, desc, art.instance))
            except BaseException:
                ProtectedModuleLoader.cleanup_package(art.package_key)
                raise
        except TaskCancelledException:
            raise
        except YscbError as exc:
            if record_runtime_degraded and exc.detail.code not in (ErrorCode.DAEMON_UNAVAILABLE, ErrorCode.TASK_NOT_FOUND):
                self._container.record_degraded(module_id, exc.detail)
            raise
        except (Exception, SystemExit, GeneratorExit) as exc:
            det = ErrorDetail(ErrorCode.MODULE_DEGRADED, f"Module '{module_id}' failed to load: {safe_exception_summary(exc)}")
            if record_runtime_degraded:
                self._container.record_degraded(module_id, det)
            raise YscbError(det.code, det.message) from exc

    def _commit_loaded_artifact(
        self,
        module_id: ModuleId,
        slot: _ModuleSlot,
        art: LoadedModuleArtifact,
        bound_tasks: dict[TaskId, BoundTask],
        start_ep: int,
    ) -> Optional[YscbModule]:
        with self._lock:
            quiesced = self._is_unavailable_locked(slot)
            epoch_ok = not quiesced and slot.epoch == start_ep
            if epoch_ok:
                slot.artifact, slot.tasks, slot.phase = art, bound_tasks, _SlotPhase.ARTIFACT_LOADED
                return art.instance
        ProtectedModuleLoader.cleanup_package(art.package_key)
        if quiesced:
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' quiesced during load.")
        return None

    def ensure_module_loaded_and_initialized(self, module_id: ModuleId) -> YscbModule:
        with self._lock:
            slot = self._slot_locked(module_id)
            if self._is_unavailable_locked(slot):
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' is quiesced.")
            eager_unstarted = (
                self._require_eager_start
                and slot.descriptor is not None
                and slot.descriptor.eager_warmup
                and slot.phase != _SlotPhase.STARTED
            )
            if (
                not slot.starting
                and not eager_unstarted
                and slot.artifact is not None
                and slot.phase in (_SlotPhase.INITIALIZED, _SlotPhase.STARTED)
            ):
                return slot.artifact.instance
            load_lk = slot.load_lock

        with load_lk:
            return self._load_and_init_under_slot_lock(module_id)

    def _claim_loaded_slot_for_init(
        self,
        module_id: ModuleId,
        inst: YscbModule,
    ) -> _SlotInitClaim:
        with self._drain_cond:
            slot = self._slot_locked(module_id)
            if slot.artifact is None or slot.artifact.instance is not inst:
                return _SlotInitClaim(matched=False)
            if slot.phase == _SlotPhase.STARTED:
                return _SlotInitClaim(matched=True, start_epoch=slot.epoch, ready_instance=slot.artifact.instance)
            need_init = slot.phase != _SlotPhase.INITIALIZED
            need_start = (
                self._require_eager_start
                and not slot.starting
                and slot.descriptor is not None
                and slot.descriptor.eager_warmup
            )
            slot.artifact.in_flight += 1
            return _SlotInitClaim(
                matched=True,
                need_init=need_init,
                need_start=need_start,
                start_epoch=slot.epoch,
                pinned_artifact=slot.artifact,
            )

    def _load_and_init_under_slot_lock(self, module_id: ModuleId) -> YscbModule:
        for _attempt in range(3):
            self._raise_if_degraded(module_id)
            inst = self.ensure_module_artifact_loaded(module_id)
            claim = self._claim_loaded_slot_for_init(module_id, inst)
            if not claim.matched:
                continue
            if claim.ready_instance is not None:
                return claim.ready_instance
            try:
                if claim.need_init:
                    inst = self._run_slot_lifecycle_hook(
                        module_id, inst, claim.start_epoch, _SlotPhase.INITIALIZED, "on_init"
                    )
                if claim.need_start:
                    self._run_slot_lifecycle_hook(
                        module_id, inst, claim.start_epoch, _SlotPhase.STARTED, "on_start"
                    )
                return inst
            finally:
                self._release_artifact_in_flight(module_id, require_non_none(claim.pinned_artifact))
        raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' concurrently reloaded during init.")

    def _release_artifact_in_flight(
        self,
        mod_id: ModuleId,
        art: LoadedModuleArtifact,
        *,
        attach_to_step: bool = False,
    ) -> tuple[ErrorDetail, ...]:
        to_clean: list[tuple[LoadedModuleArtifact, tuple[TaggedCloser, ...]]] = []
        with self._drain_cond:
            slot = self._slot_locked(mod_id)
            art.in_flight = max(0, art.in_flight - 1)
            if slot.retiring:
                ready = [entry for entry in slot.retiring if entry[0].in_flight == 0]
                if ready:
                    to_clean = ready
                    slot.retiring = [entry for entry in slot.retiring if entry[0].in_flight > 0]
            if slot.descriptor is None and slot.artifact is None and not slot.retiring:
                self._slots.pop(mod_id, None)
            self._drain_cond.notify_all()
        retire_diags: list[ErrorDetail] = []
        deferred_base: Optional[BaseException] = None
        for r_art, r_closers in to_clean:
            try:
                retire_diags.extend(LifoResourceStack.run_closers(r_closers))
            except BaseException as base_exc:
                if deferred_base is None:
                    deferred_base = base_exc
            finally:
                ProtectedModuleLoader.cleanup_package(r_art.package_key)
        if retire_diags and not attach_to_step:
            self._record_pending_teardown_diags(retire_diags)
        if deferred_base is not None:
            raise deferred_base
        return tuple(retire_diags)

    def _run_slot_lifecycle_hook(
        self,
        module_id: ModuleId,
        inst: YscbModule,
        start_ep: int,
        target_phase: _SlotPhase,
        hook_tag: str,
    ) -> YscbModule:
        try:
            close_fn = (
                inst.on_init(self._workspace_root)
                if target_phase == _SlotPhase.INITIALIZED
                else inst.on_start(self._workspace_root)
            )
        except TaskCancelledException:
            self._evict_failed_slot(module_id, start_ep)
            raise
        except YscbError as exc:
            self._evict_failed_slot(module_id, start_ep)
            if exc.detail.code not in (ErrorCode.DAEMON_UNAVAILABLE, ErrorCode.TASK_NOT_FOUND):
                self._container.record_degraded(module_id, exc.detail)
            raise
        except (Exception, SystemExit, GeneratorExit) as exc:
            self._evict_failed_slot(module_id, start_ep)
            label = "on_init" if target_phase == _SlotPhase.INITIALIZED else "warmup"
            det = ErrorDetail(ErrorCode.MODULE_DEGRADED, f"Module '{module_id}' {label} failed: {safe_exception_summary(exc)}")
            self._container.record_degraded(module_id, det)
            raise YscbError(det.code, det.message) from exc
        except BaseException:
            self._evict_failed_slot(module_id, start_ep)
            raise
        return self._commit_phase_or_abort(module_id, inst, start_ep, target_phase, close_fn, hook_tag)

    def _commit_phase_or_abort(
        self,
        module_id: ModuleId,
        inst: YscbModule,
        start_ep: int,
        target_phase: _SlotPhase,
        close_fn: Optional[Callable[[], None]],
        hook_tag: str,
    ) -> YscbModule:
        committed = False
        with self._lock:
            slot = self._slot_locked(module_id)
            quiesced = self._is_unavailable_locked(slot)
            valid = (
                not quiesced
                and slot.epoch == start_ep
                and slot.artifact is not None
                and slot.artifact.instance is inst
            )
            if valid:
                slot.phase = target_phase
                if close_fn is not None:
                    self._lifo_stack.push_closeable(f"{module_id}.{hook_tag}", close_fn)
                committed = True
        if committed:
            if target_phase == _SlotPhase.INITIALIZED and self._on_module_initialized is not None:
                self._on_module_initialized(module_id)
            return inst
        if close_fn is not None:
            self._record_pending_teardown_diags(LifoResourceStack.run_void_closer(f"{module_id}.{hook_tag}", close_fn))
        raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{module_id}' invalidated during {hook_tag}.")

    def _evict_failed_slot(self, module_id: ModuleId, expected_epoch: int) -> None:
        to_close: tuple[TaggedCloser, ...] = ()
        to_purge: list[str] = []
        with self._lock:
            slot = self._slot_locked(module_id)
            if slot.epoch == expected_epoch:
                slot.epoch += 1
                to_close, to_purge = self._detach_slots_batch_locked((slot,))
        try:
            if to_close:
                self._record_pending_teardown_diags(LifoResourceStack.run_closers(to_close))
        finally:
            for pkg in to_purge:
                ProtectedModuleLoader.cleanup_package(pkg)

    def warmup_modules(
        self,
        only_modules: Optional[frozenset[ModuleId]] = None,
    ) -> Mapping[ModuleId, Callable[[], None]]:
        with self._lock:
            mod_ids = [
                m
                for m, s in self._slots.items()
                if s.descriptor is not None
                and s.descriptor.eager_warmup
                and not self._container.has_index_degraded(m)
                and (only_modules is None or m in only_modules)
            ]
        return {mid: self._build_idempotent_start_hook(mid) for mid in mod_ids}

    def _execute_start_under_load_lock(self, mod_id: ModuleId) -> None:
        inst = self.ensure_module_loaded_and_initialized(mod_id)
        with self._drain_cond:
            slot = self._slot_locked(mod_id)
            if slot.phase == _SlotPhase.STARTED or slot.artifact is None or slot.artifact.instance is not inst:
                return
            start_ep = slot.epoch
            pinned_art = slot.artifact
            pinned_art.in_flight += 1
        try:
            self._run_slot_lifecycle_hook(mod_id, inst, start_ep, _SlotPhase.STARTED, "on_start")
        finally:
            self._release_artifact_in_flight(mod_id, pinned_art)

    def _build_idempotent_start_hook(self, mod_id: ModuleId) -> Callable[[], None]:
        def _run() -> None:
            with self._lock:
                load_lk = self._slot_locked(mod_id).load_lock
            with load_lk:
                with self._lock:
                    slot = self._slot_locked(mod_id)
                    if slot.phase == _SlotPhase.STARTED and slot.artifact is not None:
                        return
                    slot.starting = True
                try:
                    self._execute_start_under_load_lock(mod_id)
                finally:
                    with self._lock:
                        self._slot_locked(mod_id).starting = False

        return _run

    def lookup_task(self, task_id: TaskId, *, require_initialized: bool = True) -> BoundTask:
        self._raise_if_degraded(task_id.module_id, str(task_id))
        for _attempt in range(3):
            if require_initialized:
                self.ensure_module_loaded_and_initialized(task_id.module_id)
            else:
                self.ensure_module_artifact_loaded(task_id.module_id)
            with self._lock:
                slot = self._slot_locked(task_id.module_id)
                ready = slot.artifact is not None and (
                    not require_initialized or slot.phase in (_SlotPhase.INITIALIZED, _SlotPhase.STARTED)
                )
                task = slot.tasks.get(task_id) if ready else None
            if not ready:
                continue
            if task is None:
                raise YscbError(
                    ErrorCode.TASK_NOT_FOUND,
                    f"Task '{task_id}' not found in module '{task_id.module_id}'.",
                    source_task=str(task_id),
                )
            return task
        raise YscbError(
            ErrorCode.DAEMON_UNAVAILABLE,
            f"Module '{task_id.module_id}' concurrently reloaded during lookup.",
            source_task=str(task_id),
        )

    def compute_equiv_locally(self, task_id: TaskId, raw_input: JsonObject) -> WorkerEquivReply:
        try:
            task = self.lookup_task(task_id, require_initialized=False)
            return WorkerEquivReply(ok=True, equiv_key=task.compute_normalized_equivalence(raw_input))
        except (TaskCancelledException, YscbError) as exc:
            return WorkerEquivReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
        except (Exception, SystemExit, GeneratorExit) as exc:
            det = ErrorDetail(
                ErrorCode.BUSINESS_FAILURE,
                f"Equivalence failed for '{task_id}': {safe_exception_summary(exc)}",
                source_task=str(task_id),
            )
            return WorkerEquivReply(ok=False, error=det)

    def map_batch_locally(
        self,
        task_id: TaskId,
        event_id: EventId,
        event_payloads: Sequence[JsonObject],
    ) -> WorkerMapBatchReply:
        try:
            task = self.lookup_task(task_id, require_initialized=False)
            skip, mapped_obj = task.map_subscription_batch(event_id, event_payloads)
            return WorkerMapBatchReply(ok=True, skip=skip, mapped_input=mapped_obj)
        except (TaskCancelledException, YscbError) as exc:
            return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
        except (Exception, SystemExit, GeneratorExit) as exc:
            err = ErrorDetail(
                code=ErrorCode.BUSINESS_FAILURE,
                message=f"Event batch_mapper failed in '{task_id}': {safe_exception_summary(exc)}",
                source_task=str(task_id),
            )
            return WorkerMapBatchReply(ok=False, error=err)

    def unload_all_modules(self, *, grace_sec: float = 0.2) -> tuple[ErrorDetail, ...]:
        with self._lock:
            all_ids = frozenset(self._slots.keys())
        diags: list[ErrorDetail] = []
        if all_ids:
            diags.extend(self.unload_modules(all_ids, drain_in_flight=True, grace_sec=grace_sec, force_retire=True))
        else:
            diags.extend(self.drain_pending_teardown_diagnostics())
        return tuple(diags)


    def unload_modules(
        self,
        modules: frozenset[ModuleId],
        *,
        drain_in_flight: bool = False,
        grace_sec: float = 2.0,
        force_retire: bool = False,
    ) -> tuple[ErrorDetail, ...]:
        safe_grace = require_non_none(clamp_wait_sec(grace_sec, min_sec=0.05))
        deadline = time.monotonic() + safe_grace
        forced_retiring: list[tuple[LoadedModuleArtifact, tuple[TaggedCloser, ...]]] = []
        with self._drain_cond:
            target_slots = [self._slot_locked(m) for m in modules]
            for s in target_slots:
                s.epoch += 1
            while (
                drain_in_flight
                and any(s.has_active_or_retiring_work() for s in target_slots)
                and time.monotonic() < deadline
            ):
                self._drain_cond.wait(timeout=0.02)
            immediate_closers, evicted_pkgs = self._detach_slots_batch_locked(target_slots)
            if force_retire:
                for s in target_slots:
                    forced_retiring.extend(s.retiring)
                    s.retiring.clear()
        self._container.clear_degraded(modules)
        return self._finalize_unloaded_batches(immediate_closers, evicted_pkgs, forced_retiring)

    def _finalize_unloaded_batches(
        self,
        immediate_closers: tuple[TaggedCloser, ...],
        evicted_pkgs: list[str],
        forced_retiring: list[tuple[LoadedModuleArtifact, tuple[TaggedCloser, ...]]],
    ) -> tuple[ErrorDetail, ...]:
        diags: list[ErrorDetail] = list(self.drain_pending_teardown_diagnostics())
        deferred_base: Optional[BaseException] = None
        try:
            if immediate_closers:
                diags.extend(LifoResourceStack.run_closers(immediate_closers))
        except BaseException as base_exc:
            deferred_base = base_exc
        finally:
            for pkg in evicted_pkgs:
                ProtectedModuleLoader.cleanup_package(pkg)
        for r_art, r_closers in forced_retiring:
            try:
                if r_closers:
                    diags.extend(LifoResourceStack.run_closers(r_closers))
            except BaseException as base_exc:
                if deferred_base is None:
                    deferred_base = base_exc
            finally:
                ProtectedModuleLoader.cleanup_package(r_art.package_key)
        if deferred_base is not None:
            raise deferred_base
        return tuple(diags)

    def _acquire_pinned_task(self, task_id: TaskId) -> tuple[BoundTask, LoadedModuleArtifact]:
        self._raise_if_degraded(task_id.module_id, str(task_id))
        for _attempt in range(3):
            self.ensure_module_loaded_and_initialized(task_id.module_id)
            with self._drain_cond:
                slot = self._slot_locked(task_id.module_id)
                ready = slot.artifact is not None and slot.phase in (_SlotPhase.INITIALIZED, _SlotPhase.STARTED)
                if not ready:
                    continue
                task = slot.tasks.get(task_id)
                if task is None:
                    raise YscbError(
                        ErrorCode.TASK_NOT_FOUND,
                        f"Task '{task_id}' not found in module '{task_id.module_id}'.",
                        source_task=str(task_id),
                    )
                art = require_non_none(slot.artifact)
                art.in_flight += 1
                return (task, art)
        raise YscbError(
            ErrorCode.DAEMON_UNAVAILABLE,
            f"Module '{task_id.module_id}' concurrently reloaded during lookup.",
            source_task=str(task_id),
        )

    def execute_step_locally(self, spec: LocalStepExecutionSpec) -> WorkerStepReply:
        pinned_box: list[LoadedModuleArtifact] = []
        step_reply: Optional[WorkerStepReply] = None
        try:
            step_reply = self._run_counted_local_step(spec, pinned_box)
        finally:
            if pinned_box:
                retire_diags = self._release_artifact_in_flight(
                    spec.task_id.module_id, pinned_box[0], attach_to_step=(step_reply is not None)
                )
                if step_reply is not None and retire_diags:
                    step_reply = replace(
                        step_reply,
                        teardown_diagnostics=(*step_reply.teardown_diagnostics, *retire_diags),
                    )
        return require_non_none(step_reply)

    def _run_counted_local_step(
        self,
        spec: LocalStepExecutionSpec,
        pinned_box: list[LoadedModuleArtifact],
    ) -> WorkerStepReply:
        outbox = TaskLocalOutbox(
            spec.task_id,
            spec.base_lineage,
            workspace_scope=self._workspace_root.comparison_key,
        )
        ctx = _StepTaskContext(self._workspace_root, spec, outbox)
        try:
            spec.cancel_token.raise_if_cancelled()
            task, pinned_art = self._acquire_pinned_task(spec.task_id)
            pinned_box.append(pinned_art)
            allow_tty = task.interactive_tty or spec.interactive_tty
            with guard_standard_streams(allow_interactive_tty=allow_tty):
                raw_out = task.execute_encoded(spec.raw_input, ctx)
            return WorkerStepReply(
                ok=True,
                raw_output=raw_out,
                committed_events=outbox.drain_committed(),
            )
        except TaskCancelledException as exc:
            outbox.discard()
            return WorkerStepReply(
                ok=False,
                preempted=(exc.detail.code == ErrorCode.TASK_PREEMPTED),
                fatal_abort_turn=False,
                error=exc.detail.with_fallback_task(str(spec.task_id)),
            )
        except YscbError as exc:
            outbox.discard()
            is_fatal = is_fatal_error_code(exc.detail.code)
            return WorkerStepReply(
                ok=False,
                preempted=(exc.detail.code == ErrorCode.TASK_PREEMPTED),
                fatal_abort_turn=is_fatal,
                error=exc.detail.with_fallback_task(str(spec.task_id)),
            )
        except (Exception, SystemExit, GeneratorExit) as exc:
            outbox.discard()
            return WorkerStepReply(
                ok=False,
                error=ErrorDetail(
                    code=ErrorCode.BUSINESS_FAILURE,
                    message=safe_exception_summary(exc),
                    source_task=str(spec.task_id),
                ),
            )
