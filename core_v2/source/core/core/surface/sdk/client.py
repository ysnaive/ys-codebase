"""High-level Surface SDK Client wrapping RuntimeDispatcher and PersistentRpcSession."""

from __future__ import annotations

import dataclasses
import threading
from typing import Callable, ClassVar, Mapping, Optional, Sequence, TypeVar, overload

from core.execution.rpc import DaemonConnectionConfig, PersistentRpcSession
from core.execution.runtime import (
    CallerSurface,
    ClientRoutingPolicy,
    DEFAULT_CACHE_DIRNAME,
    DispatcherHostOptions,
    InvokeRequest,
    ModuleDescriptor,
    ModuleProviderPort,
    RuntimeDispatcher,
    TaskOutcome,
    YscbModule,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    ErrorCode,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    ProgressEvent,
    TaskId,
    YscbError,
    clone_strict_json_object,
    require_pure_bool,
    require_pure_str,
)
from core.surface.sdk.declarative import InMemoryModule, Module

TOut = TypeVar("TOut")


class _NullModuleProvider(ModuleProviderPort):
    """Empty ModuleProviderPort used when YscbClient executes purely via in_memory_modules or RPC."""

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        _ = self
        return ()

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        _ = (self, module_id)
        return None

    def reload(self) -> None:
        _ = self
        return None


def _coerce_yscb_modules(modules: Sequence[Module | InMemoryModule]) -> tuple[YscbModule, ...]:
    if isinstance(modules, (str, bytes, bytearray, memoryview)) or not isinstance(modules, Sequence):
        raise TypeError(f"modules must be a Sequence of Module or InMemoryModule, got {type(modules).__name__}")
    converted: list[YscbModule] = []
    for item in modules:
        if isinstance(item, (Module, InMemoryModule)):
            converted.append(item.to_yscb_module())
        else:
            raise TypeError(f"Expected Module or InMemoryModule instance, got {type(item).__name__}")
    return tuple(converted)


def _encode_call_input(req: object) -> JsonObject:
    if req is None:
        return {}
    if isinstance(req, Mapping):
        return clone_strict_json_object(req)
    if dataclasses.is_dataclass(req) and not isinstance(req, type):
        return DataclassCodec.encode_object(req)
    raise YscbError(
        ErrorCode.CODEC_VALIDATION_FAILED,
        f"YscbClient.call req must be None, Mapping, or dataclass instance, got {type(req).__name__}",
    )


class _ConnectContext:
    """Thread-local staging flag so YscbClient.connect() opts into RPC cleanly."""

    _STATE: ClassVar[Optional[threading.local]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _ensure_local(cls) -> threading.local:
        if cls._STATE is None:
            with cls._INIT_LOCK:
                if cls._STATE is None:
                    cls._STATE = threading.local()
        return cls._STATE

    @classmethod
    def begin_connect(cls) -> bool:
        tls = cls._ensure_local()
        try:
            prev = bool(tls.use_rpc)
        except AttributeError:
            prev = False
        tls.use_rpc = True
        return prev

    @classmethod
    def end_connect(cls, prev: bool) -> None:
        cls._ensure_local().use_rpc = prev

    @classmethod
    def is_connect_active(cls) -> bool:
        tls = cls._ensure_local()
        try:
            return bool(tls.use_rpc)
        except AttributeError:
            return False


class YscbClient:
    """Programmatic Surface SDK client dispatching tasks across local or connected daemon runtimes."""

    def __init__(
        self,
        workspace_root: HostPath,
        *,
        modules: Sequence[Module | InMemoryModule] = (),
    ) -> None:
        if not isinstance(workspace_root, HostPath):
            raise TypeError(f"workspace_root must be HostPath, got {type(workspace_root).__name__}")
        yscb_modules = _coerce_yscb_modules(modules)
        self._workspace_root = workspace_root
        cache_dir = workspace_root.join(DEFAULT_CACHE_DIRNAME)
        use_rpc = _ConnectContext.is_connect_active()
        self._rpc_session: Optional[PersistentRpcSession] = (
            PersistentRpcSession(cache_dir=cache_dir, workspace_root=workspace_root) if use_rpc else None
        )
        conn_cfg = DaemonConnectionConfig(enabled=use_rpc, auto_spawn=False, strict_hot_dispatch=False)
        options = DispatcherHostOptions(
            connection_config=conn_cfg,
            persistent_rpc_session=self._rpc_session,
            in_memory_modules=yscb_modules,
        )
        try:
            self._dispatcher = RuntimeDispatcher(
                workspace_root=workspace_root,
                cache_dir=cache_dir,
                module_provider=_NullModuleProvider(),
                options=options,
            )
        except Exception:
            if self._rpc_session is not None:
                self._rpc_session.close()
            raise
        self._closed = False

    @classmethod
    def local(
        cls,
        workspace_root: HostPath,
        *modules: Module | InMemoryModule,
    ) -> YscbClient:
        """Create an in-process local client backed by supplied Module and InMemoryModule instances."""
        return cls(workspace_root, modules=modules)

    @classmethod
    def connect(cls, workspace_root: HostPath) -> YscbClient:
        """Create a client configured to route calls through a persistent daemon RPC session."""
        prev = _ConnectContext.begin_connect()
        try:
            return cls(workspace_root)
        finally:
            _ConnectContext.end_connect(prev)

    @overload
    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: type[TOut],
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: None = None,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...

    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: Optional[type[TOut]] = None,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]:
        """Dispatch a task synchronously through RuntimeDispatcher and return its TaskOutcome."""
        if self._closed:
            raise YscbError(ErrorCode.TEARDOWN_ERROR, "YscbClient is already closed")
        tid = task_id if isinstance(task_id, TaskId) else TaskId(require_pure_str(task_id, "task_id", non_empty=True))
        if cwd is not None and not isinstance(cwd, HostPath):
            raise TypeError(f"cwd must be HostPath or None, got {type(cwd).__name__}")
        if env is not None and not isinstance(env, Mapping):
            raise TypeError(f"env must be Mapping[str, str] or None, got {type(env).__name__}")
        if isinstance(approval_scope, (str, bytes, bytearray, memoryview)) or not isinstance(
            approval_scope, (set, frozenset, Sequence)
        ):
            raise TypeError("approval_scope must be a frozenset of TaskId")
        encoded_input = _encode_call_input(req)
        policy = (
            ClientRoutingPolicy.FORCE_COLD
            if require_pure_bool(force_cold, "force_cold")
            else ClientRoutingPolicy.AUTO_NO_SPAWN
        )
        scope = frozenset(
            item if isinstance(item, TaskId) else TaskId(require_pure_str(item, "approval_scope item", non_empty=True))
            for item in approval_scope
        )
        progress_cb: Optional[Callable[[JsonObject], None]] = None
        if on_progress is not None:
            if not callable(on_progress):
                raise TypeError("on_progress must be callable or None")

            def _forward_progress(payload: JsonObject) -> None:
                decoded = DataclassCodec.decode(ProgressEvent, payload)
                if isinstance(decoded, ProgressEvent):
                    on_progress(decoded)

            progress_cb = _forward_progress
        request = InvokeRequest(
            task_id=tid,
            raw_input=encoded_input,
            workspace_root=self._workspace_root,
            caller_cwd=cwd or self._workspace_root,
            caller_env=env if env is not None else {},
            caller_surface=CallerSurface.SDK,
            routing_policy=policy,
            approval_scope=scope,
        )
        return self._dispatcher.invoke(
            request,
            output_type=output_type,
            cancel_token=cancel_token,
            on_progress=progress_cb,
        )

    def close(self) -> None:
        """Shut down the local RuntimeDispatcher and any active RPC session idempotently."""
        if self._closed:
            return
        self._closed = True
        errors: list[str] = []
        try:
            errs = self._dispatcher.shutdown()
            errors.extend(err.message for err in errs)
        except Exception as exc:
            errors.append(str(exc))
        if self._rpc_session is not None:
            try:
                self._rpc_session.close()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise YscbError(ErrorCode.TEARDOWN_ERROR, f"YscbClient close failed: {'; '.join(errors)}")

    def __enter__(self) -> YscbClient:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        _ = (exc_type, exc_val, exc_tb)
        self.close()
