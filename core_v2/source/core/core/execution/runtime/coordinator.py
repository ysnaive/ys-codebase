"""Single-point step coordinator unifying same-stack/single-hop SERIALIZE reentrancy, PREEMPT, and top-level COALESCE."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import os
import threading
import time
from typing import Callable, Generic, Iterator, Optional, Sequence, TypeVar
import uuid

from core.execution.runtime.contracts import DEFAULT_CACHE_DIRNAME, LOCKS_SUBDIR, ConcurrencyMode, ExecutionPriority
from core.filesystem.fs import (
    CrossProcessLockPaths, FileLock, acquire_verified_cross_proc_pin, read_live_owner_dict,
    resolve_contained_subpath, silent_unlink, unlink_owner_under_pin, write_cross_proc_owner_json,
)
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.observability import CancellationToken, ms_to_safe_sec
from core.foundation.primitives import HostPath, JsonObject, TaskId, invoke_observer_safely, require_non_none

TResult = TypeVar("TResult")
TVal = TypeVar("TVal")


class PriorityHandle:
    """Thread-safe mutable priority view allowing dynamic elevation across coalesced waiters."""

    def __init__(self, initial: ExecutionPriority) -> None:
        self._lock, self._priority = threading.Lock(), initial
        self._listeners: list[Callable[[ExecutionPriority], None]] = []

    @property
    def current(self) -> ExecutionPriority:
        with self._lock:
            return self._priority

    def __call__(self) -> ExecutionPriority:
        return self.current

    def elevate_to_foreground(self) -> bool:
        with self._lock:
            if self._priority == ExecutionPriority.FOREGROUND:
                return False
            self._priority = ExecutionPriority.FOREGROUND
            listeners = list(self._listeners)
        for listener in listeners:
            invoke_observer_safely(lambda fn=listener: fn(ExecutionPriority.FOREGROUND))
        return True

    def register_listener(self, cb: Callable[[ExecutionPriority], None]) -> Callable[[], None]:
        with self._lock:
            already_fg = self._priority == ExecutionPriority.FOREGROUND
            if not already_fg:
                self._listeners.append(cb)
        if already_fg:
            invoke_observer_safely(lambda: cb(ExecutionPriority.FOREGROUND))
            return lambda: None

        def _unregister() -> None:
            with self._lock:
                if cb in self._listeners:
                    self._listeners.remove(cb)

        return _unregister


class SharedCancelGroup:
    """Shared cancellation hub cancelling host_token only when every active participant cancels or detaches."""

    def __init__(self) -> None:
        self.host_token = CancellationToken()
        self._lock, self._closed, self._next_id = threading.Lock(), False, 0
        self._active_ids: set[int] = set()
        self._unregs: dict[int, Callable[[], None]] = {}

    def add_participants(self, caller_tokens: Sequence[CancellationToken]) -> tuple[Optional[Callable[[], None]], ...]:
        if not caller_tokens:
            return ()
        pids: list[int] = []
        with self._lock:
            if self._closed or self.host_token.is_cancelled:
                return tuple(None for _ in caller_tokens)
            for _tok in caller_tokens:
                pid = self._next_id
                self._next_id += 1
                self._active_ids.add(pid)
                pids.append(pid)
        return tuple(self._bind_participant_callback(pid, tok) for pid, tok in zip(pids, caller_tokens))

    def try_add_participant(self, caller_token: CancellationToken) -> Optional[Callable[[], None]]:
        return self.add_participants((caller_token,))[0]

    def _bind_participant_callback(self, pid: int, caller_token: CancellationToken) -> Callable[[], None]:
        def _finish(should_cancel: bool, preempted: bool, reason: str) -> None:
            if should_cancel:
                self.host_token.cancel(preempted=preempted, reason=reason)
                self.close_all()

        def _on_cancelled(preempted: bool, reason: str) -> None:
            with self._lock:
                self._active_ids.discard(pid)
                should_c = not self._active_ids and not self._closed
                if should_c:
                    self._closed = True
            _finish(should_c, preempted, reason)

        unreg = caller_token.register_callback(_on_cancelled)
        with self._lock:
            should_unreg = self._closed or pid not in self._active_ids
            if not should_unreg:
                self._unregs[pid] = unreg
        if should_unreg:
            unreg()

        def _detach() -> None:
            with self._lock:
                u = self._unregs.pop(pid, None)
                self._active_ids.discard(pid)
                should_c = not self._active_ids and not self._closed
                if should_c:
                    self._closed = True
            if u is not None:
                u()
            _finish(should_c, False, "all shared participants detached")

        return _detach

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_ids)

    def close_all(self) -> None:
        with self._lock:
            self._closed = True
            unregs = list(self._unregs.values())
            self._unregs.clear()
            self._active_ids.clear()
        for u in unregs:
            u()
@dataclass(frozen=True, slots=True)
class FlightCallerRegistration:
    """Caller registration metadata attached to a top-level StepFlight."""

    caller_turn_id: str
    call_tree_id: str
    caller_stack: tuple[tuple[HostPath, TaskId], ...]
    step_cancel: CancellationToken
    turn_cancel: CancellationToken
    in_event_chain: bool = False
    deadline: Optional[float] = None


@dataclass(frozen=True, slots=True)
class HolderIdentity:
    """Typed holder stack identity matching same-stack reentrant locks."""

    turn_id: str
    tree_id: str
    stack: tuple[tuple[HostPath, TaskId], ...] = ()


def wait_on_event_with_cancel(ev: threading.Event, cancel_token: CancellationToken, timeout_sec: Optional[float]) -> None:
    deadline = (time.monotonic() + timeout_sec) if timeout_sec is not None else None
    while not ev.is_set():
        cancel_token.raise_if_cancelled()
        rem = 0.02
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting in ResourceCoordinator.")
            rem = min(rem, left)
        ev.wait(timeout=rem)
    cancel_token.raise_if_cancelled()


class StepFlight(Generic[TVal]):
    """Top-level same-workspace single-flight latch sharing cancellation, priority elevation, progress, and Step 5 drain."""

    def __init__(self, priority_handle: PriorityHandle) -> None:
        self.flight_id: str = f"flight_{uuid.uuid4().hex}"
        self.priority_handle = priority_handle
        self.cancel_group, self.post_step_cancel = SharedCancelGroup(), SharedCancelGroup()
        self.done, self._post_done = threading.Event(), threading.Event()
        self.outcome: Optional[TVal] = None
        self.raised_exc: Optional[BaseException] = None
        self._lock, self._sealed, self._next_pid = threading.Lock(), False, 0
        self._callers: dict[int, FlightCallerRegistration] = {}
        self._slot_wakes: dict[int, threading.Event] = {}
        self._slot_detachers: dict[int, Callable[[], None]] = {}
        self._post_detachers: dict[int, Callable[[], None]] = {}
        self._prog_listeners: dict[int, Callable[[JsonObject], None]] = {}
        self._post_started = False
        self._post_result: object = None
        self._post_exc: Optional[BaseException] = None

    def slot_wake_event(self, slot_id: int) -> threading.Event:
        with self._lock:
            return self._slot_wakes.get(slot_id, self.done)

    def seal(self) -> None:
        with self._lock:
            self._sealed = True

    def active_caller_count(self) -> int:
        with self._lock:
            return len(self._callers)

    def _live_deadline(self, *, post_step: bool) -> Optional[float]:
        with self._lock:
            live = [
                c for pid, c in self._callers.items()
                if not c.turn_cancel.is_cancelled and (post_step or (pid in self._slot_detachers and not c.step_cancel.is_cancelled))
            ]
        if not live:
            return 0.0
        return None if any(c.deadline is None for c in live) else max(c.deadline for c in live if c.deadline is not None)

    def effective_deadline(self) -> Optional[float]:
        return self._live_deadline(post_step=False)

    def effective_post_step_deadline(self) -> Optional[float]:
        return self._live_deadline(post_step=True)

    def add_caller(
        self, reg: FlightCallerRegistration, on_progress: Optional[Callable[[JsonObject], None]],
    ) -> tuple[int, Optional[Callable[[], None]]]:
        with self._lock:
            if self._sealed:
                return (-1, None)
            cg_det = self.cancel_group.try_add_participant(reg.step_cancel)
            if cg_det is None:
                return (-1, None)
            post_det = self.post_step_cancel.try_add_participant(reg.turn_cancel)
            if post_det is None:
                cg_det()
                return (-1, None)
            pid = self._next_pid
            self._next_pid += 1
            wake_ev = threading.Event()
            if self.done.is_set():
                wake_ev.set()
            self._callers[pid], self._slot_wakes[pid], self._slot_detachers[pid], self._post_detachers[pid] = reg, wake_ev, cg_det, post_det
            if on_progress is not None:
                self._prog_listeners[pid] = on_progress

        def _detach_step4() -> None:
            with self._lock:
                self._prog_listeners.pop(pid, None)
                det_fn = self._slot_detachers.pop(pid, None)
            if det_fn is not None:
                det_fn()

        return (pid, _detach_step4)

    def detach_post_step(self, slot_id: int) -> None:
        if slot_id < 0:
            return
        with self._lock:
            self._callers.pop(slot_id, None)
            self._prog_listeners.pop(slot_id, None)
            det4, det5 = self._slot_detachers.pop(slot_id, None), self._post_detachers.pop(slot_id, None)
        for det in (det4, det5):
            if det is not None:
                det()

    def broadcast_progress(self, payload: JsonObject) -> None:
        with self._lock:
            cbs = list(self._prog_listeners.values())
        for cb in cbs:
            invoke_observer_safely(lambda fn=cb: fn(payload))

    def complete(self, *, outcome: Optional[TVal] = None, raised_exc: Optional[BaseException] = None) -> None:
        with self._lock:
            self._sealed = True
            wakes = list(self._slot_wakes.values())
        self.outcome, self.raised_exc = outcome, raised_exc
        if raised_exc is not None:
            self.post_step_cancel.close_all()
            self._post_done.set()
        self.done.set()
        for w_ev in wakes:
            w_ev.set()
    def run_or_await_post_step(
        self, slot_id: int, turn_cancel: CancellationToken, timeout_sec: Optional[float],
        drain_fn: Callable[[CancellationToken, Callable[[], Optional[float]]], object],
    ) -> object:
        with self._lock:
            start_worker = not self._post_started
            self._post_started = True
        if start_worker:
            def _run_post() -> None:
                try:
                    self._post_result = drain_fn(self.post_step_cancel.host_token, self.effective_post_step_deadline)
                except BaseException as exc:
                    self._post_exc = exc
                finally:
                    self.post_step_cancel.close_all()
                    self._post_done.set()

            try:
                threading.Thread(target=_run_post, name=f"yscb-step5-{self.flight_id}", daemon=True).start()
            except BaseException as exc:
                self._post_exc = exc
                self.post_step_cancel.close_all()
                self._post_done.set()
        try:
            wait_on_event_with_cancel(self._post_done, turn_cancel, timeout_sec)
        finally:
            self.detach_post_step(slot_id)
        if self._post_exc is not None:
            raise self._post_exc
        return self._post_result


@dataclass(frozen=True, slots=True)
class CoordinatedExecution(Generic[TResult]):
    """Typed outcome returned by ResourceCoordinator.execute without anonymous tuple indexing."""

    is_follower: bool
    caller_slot_id: int
    outcome: Optional[TResult]


@dataclass(frozen=True, slots=True)
class ResourceAcquireSpec:
    """Structured acquisition specification encapsulating resource key, mode, stack, and priority."""

    resource_key: Optional[str]
    mode: ConcurrencyMode
    equiv_key: str
    priority: ExecutionPriority
    turn_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...]
    cancel_token: CancellationToken
    turn_cancel_token: Optional[CancellationToken] = None
    timeout_ms: Optional[int] = None
    external_priority_handle: Optional[PriorityHandle] = None
    allow_step_coalesce: bool = True
    call_tree_id: str = ""
    in_event_chain: bool = False
    on_progress: Optional[Callable[[JsonObject], None]] = None


@dataclass(slots=True)
class _ActiveHolder:
    turn_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...]
    mode: ConcurrencyMode
    equiv_key: str
    priority_handle: PriorityHandle
    cancel_token: CancellationToken
    allow_step_coalesce: bool = True
    flight: Optional[StepFlight[object]] = None
    call_tree_id: str = ""
    deadline: Optional[float] = None
    os_lock_live: bool = False
    pin_path: Optional[HostPath] = None
    self_exit_guard: Optional[threading.Event] = None
    lingering_guards: list[threading.Event] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ReentrantGrant:
    holder: _ActiveHolder
    step_guard: threading.Event


@dataclass(slots=True)
class _QueuedWaiter:
    seq: int
    holder: _ActiveHolder
    wake_event: threading.Event = field(default_factory=threading.Event)
    aborted_preempt: bool = False
    promoted: bool = False


@dataclass(slots=True)
class _BucketAdmission:
    joined_flight: Optional[StepFlight[object]] = None
    caller_slot_id: int = -1
    detach_fn: Optional[Callable[[], None]] = None
    holder: Optional[_ActiveHolder] = None
    waiter: Optional[_QueuedWaiter] = None


class _ResourceBucket:
    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.active: Optional[_ActiveHolder] = None
        self.cross_proc_reentrant: list[_ActiveHolder] = []
        self.serial_stack_chain: list[HolderIdentity] = []
        self.waiters: list[_QueuedWaiter] = []
        self.seq_counter = 0


def _has_lingering_guards(holder: _ActiveHolder) -> bool:
    return (holder.self_exit_guard is not None and not holder.self_exit_guard.is_set()) or any(not g.is_set() for g in holder.lingering_guards)
def _await_step_flight(
    flight: StepFlight[TResult], adm: _BucketAdmission, cancel_token: CancellationToken,
    timeout_sec: Optional[float], *, is_follower: bool,
) -> CoordinatedExecution[TResult]:
    slot_wake = flight.slot_wake_event(adm.caller_slot_id)
    try:
        wait_on_event_with_cancel(slot_wake, cancel_token, timeout_sec)
    except BaseException:
        if adm.detach_fn is not None:
            adm.detach_fn()
            adm.detach_fn = None
        flight.detach_post_step(adm.caller_slot_id)
        raise
    finally:
        if adm.detach_fn is not None:
            adm.detach_fn()
    if flight.raised_exc is not None:
        flight.detach_post_step(adm.caller_slot_id)
        raise flight.raised_exc
    return CoordinatedExecution(is_follower, adm.caller_slot_id, flight.outcome)


def _spec_matches_ident(
    call_tree_id: str, turn_id: str, call_stack: tuple[tuple[HostPath, TaskId], ...], ident: HolderIdentity,
) -> bool:
    same_tree = (bool(call_tree_id) and ident.tree_id == call_tree_id) or (bool(ident.turn_id) and ident.turn_id == turn_id)
    return same_tree and bool(ident.stack) and len(call_stack) > len(ident.stack) and call_stack[: len(ident.stack)] == ident.stack


def _drain_holder_lingering_guards(bucket: _ResourceBucket, holder: _ActiveHolder, *, max_wait_sec: float = 30.0) -> None:
    deadline = time.monotonic() + max_wait_sec
    while True:
        with bucket.cond:
            pending = [g for g in holder.lingering_guards if not g.is_set()]
            holder.lingering_guards = pending
            if holder.self_exit_guard is not None and holder.self_exit_guard.is_set():
                holder.self_exit_guard = None
            next_g = pending[0] if pending else holder.self_exit_guard
            timed_out = next_g is not None and time.monotonic() >= deadline
            if next_g is None or timed_out:
                holder.os_lock_live = False
        if next_g is None or timed_out:
            return
        next_g.wait(timeout=max(0.01, min(0.25, deadline - time.monotonic())))


def _defer_lingering_release(
    bucket: _ResourceBucket, holder: _ActiveHolder, thread_name: str,
    cleanup_fn: Callable[[], None], on_done: Callable[[], None],
) -> None:
    def _worker() -> None:
        try:
            _drain_holder_lingering_guards(bucket, holder)
        finally:
            try:
                cleanup_fn()
            finally:
                on_done()

    try:
        threading.Thread(target=_worker, name=thread_name, daemon=True).start()
    except BaseException:
        _worker()
        raise


def _finalize_holder_os_lock(
    bucket: _ResourceBucket, holder: _ActiveHolder, paths: CrossProcessLockPaths,
    owns_os_lock: bool, has_lingering: bool, reentrant_pin: Optional[FileLock],
    on_released: Callable[[_ResourceBucket, _ActiveHolder], None],
) -> tuple[bool, Optional[FileLock]]:
    if has_lingering and owns_os_lock:
        if reentrant_pin is not None:
            reentrant_pin.release()
        _defer_lingering_release(
            bucket, holder, "yscb-lock-lingering",
            lambda: unlink_owner_under_pin(paths.owner_path, paths.pin_path, paths.lock_file.release),
            lambda: on_released(bucket, holder),
        )
        return (True, None)
    if has_lingering:
        _defer_lingering_release(
            bucket, holder, "yscb-pin-lingering",
            lambda: reentrant_pin.release() if reentrant_pin is not None else None,
            lambda: on_released(bucket, holder),
        )
        return (True, None)
    if reentrant_pin is not None:
        reentrant_pin.release()
    if owns_os_lock:
        unlink_owner_under_pin(paths.owner_path, paths.pin_path, paths.lock_file.release)
    return (False, None)


@contextmanager
def _serial_execution_turn(
    bucket: _ResourceBucket, turn_id: str, tree_id: str, call_stack: tuple[tuple[HostPath, TaskId], ...],
    matches_top_fn: Optional[Callable[[HolderIdentity], bool]], cancel_token: CancellationToken,
    timeout_sec: Optional[float], resource_key: Optional[str], *, reset_root: bool = False,
) -> Iterator[None]:
    deadline = (time.monotonic() + timeout_sec) if timeout_sec is not None else None
    my_ident = HolderIdentity(turn_id=turn_id, tree_id=tree_id or turn_id, stack=call_stack)

    def _wake(_p: bool, _r: str) -> None:
        with bucket.cond:
            bucket.cond.notify_all()

    unreg = cancel_token.register_callback(_wake)
    try:
        with bucket.cond:
            while not reset_root and bucket.serial_stack_chain and (matches_top_fn is None or not matches_top_fn(bucket.serial_stack_chain[-1])):
                cancel_token.raise_if_cancelled()
                rem = 0.03 if deadline is None else min(0.03, deadline - time.monotonic())
                if rem <= 0.0:
                    raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting on serialized reentrant turn for '{resource_key}'.")
                bucket.cond.wait(timeout=rem)
            cancel_token.raise_if_cancelled()
            if reset_root:
                bucket.serial_stack_chain[:] = [my_ident]
            else:
                bucket.serial_stack_chain.append(my_ident)
        yield
    finally:
        unreg()
        with bucket.cond:
            if bucket.serial_stack_chain and bucket.serial_stack_chain[-1] is my_ident:
                bucket.serial_stack_chain.pop()
            elif my_ident in bucket.serial_stack_chain:
                bucket.serial_stack_chain.remove(my_ident)
            bucket.cond.notify_all()
def _wait_active_borrowed_guards_for_caller(
    bucket: _ResourceBucket, spec: ResourceAcquireSpec, *, deadline: Optional[float] = None,
) -> None:
    eff_dl = deadline if deadline is not None else (time.monotonic() + 2.0)
    pins_to_wait: list[HostPath] = []
    while True:
        with bucket.cond:
            cands = (*((bucket.active,) if bucket.active is not None else ()), *bucket.cross_proc_reentrant)
            matched = [c for c in cands if _spec_matches_ident(spec.call_tree_id, spec.turn_id, spec.call_stack, HolderIdentity(c.turn_id, c.call_tree_id, c.call_stack))]
            if not matched:
                return
            next_g: Optional[threading.Event] = None
            for act in matched:
                pending = [g for g in act.lingering_guards if not g.is_set()]
                act.lingering_guards = pending
                if next_g is None and pending:
                    next_g = pending[0]
            if next_g is None:
                pins_to_wait = [act.pin_path for act in matched if act.os_lock_live and act.pin_path is not None]
        if next_g is None or time.monotonic() >= eff_dl:
            break
        next_g.wait(timeout=max(0.01, min(0.2, eff_dl - time.monotonic())))
    for pin_path in pins_to_wait:
        rem_pin = eff_dl - time.monotonic()
        if rem_pin <= 0.0:
            break
        pin_gate = FileLock(pin_path, allow_transitions=False)
        try:
            if pin_gate.acquire(shared=False, blocking=True, timeout_sec=max(0.02, rem_pin)):
                pin_gate.release()
        except YscbError:
            return


def _check_same_stack_reentrancy(bucket: _ResourceBucket, spec: ResourceAcquireSpec) -> Optional[_ReentrantGrant]:
    conflict = False
    with bucket.cond:
        for cand in (*((bucket.active,) if bucket.active is not None else ()), *bucket.cross_proc_reentrant):
            if not _spec_matches_ident(spec.call_tree_id, spec.turn_id, spec.call_stack, HolderIdentity(cand.turn_id, cand.call_tree_id, cand.call_stack)):
                continue
            if cand.mode == ConcurrencyMode.SERIALIZE and spec.mode == ConcurrencyMode.SERIALIZE:
                if cand.os_lock_live:
                    step_guard = threading.Event()
                    cand.lingering_guards.append(step_guard)
                    return _ReentrantGrant(cand, step_guard)
                continue
            conflict = True
            break
    if not conflict:
        return None
    src_tid = str(spec.call_stack[-1][1]) if spec.call_stack else None
    raise YscbError(ErrorCode.ILLEGAL_LOCK_REENTRANCY, f"Cannot re-enter resource_key '{spec.resource_key}' with {spec.mode.value} on same CallStack.", source_task=src_tid)


def _decode_owner_stack(raw_stack: object) -> tuple[tuple[HostPath, TaskId], ...]:
    if not isinstance(raw_stack, list):
        return ()
    entries: list[tuple[HostPath, TaskId]] = []
    for item in raw_stack:
        if not (isinstance(item, list) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], str)):
            return ()
        try:
            entries.append((HostPath(item[0]), TaskId(item[1])))
        except (ValueError, OSError):
            return ()
    return tuple(entries)


def _read_live_cross_proc_owner(owner_path: HostPath) -> Optional[tuple[HolderIdentity, str]]:
    doc = read_live_owner_dict(owner_path)
    if doc is None or type(doc.get("call_tree_id")) is not str or not doc.get("call_tree_id"):
        return None
    raw_turn, raw_mode = doc.get("turn_id"), doc.get("mode")
    ident = HolderIdentity(
        turn_id=raw_turn if type(raw_turn) is str else "", tree_id=str(doc["call_tree_id"]), stack=_decode_owner_stack(doc.get("call_stack")),
    )
    return (ident, raw_mode if type(raw_mode) is str else "")


def _try_acquire_incoming_cross_proc_reentry(locks_dir: HostPath, spec: ResourceAcquireSpec, timeout_sec: Optional[float]) -> Optional[FileLock]:
    if not spec.resource_key:
        return None
    paths = CrossProcessLockPaths.for_stem(locks_dir, f"res_{hashlib.sha256(spec.resource_key.encode('utf-8')).hexdigest()[:24]}", allow_transitions=False)
    live_owner = _read_live_cross_proc_owner(paths.owner_path)
    if live_owner is None or not _spec_matches_ident(spec.call_tree_id, spec.turn_id, spec.call_stack, live_owner[0]):
        return None
    if live_owner[1] == ConcurrencyMode.SERIALIZE.value and spec.mode == ConcurrencyMode.SERIALIZE:
        return acquire_verified_cross_proc_pin(
            paths.owner_path, paths.pin_path,
            lambda ow: (lo := _read_live_cross_proc_owner(ow)) is not None and lo[1] == ConcurrencyMode.SERIALIZE.value and _spec_matches_ident(spec.call_tree_id, spec.turn_id, spec.call_stack, lo[0]),
            timeout_sec=timeout_sec if timeout_sec is not None else 10.0, cancel_token=spec.cancel_token,
        )
    src_tid = str(spec.call_stack[-1][1]) if spec.call_stack else None
    raise YscbError(ErrorCode.ILLEGAL_LOCK_REENTRANCY, f"Cannot re-enter resource_key '{spec.resource_key}' with {spec.mode.value} across process CallStack.", source_task=src_tid)


def _remove_borrowed_locked(bucket: _ResourceBucket, holder: _ActiveHolder) -> None:
    with bucket.cond:
        if holder in bucket.cross_proc_reentrant:
            bucket.cross_proc_reentrant.remove(holder)


def _run_reentrant_or_borrowed_step(
    bucket: _ResourceBucket, holder: _ActiveHolder, spec: ResourceAcquireSpec, prio: PriorityHandle,
    timeout_sec: Optional[float], leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
    extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]],
    *, step_guard: Optional[threading.Event] = None, pin_lk: Optional[FileLock] = None,
) -> CoordinatedExecution[TResult]:
    if pin_lk is not None:
        with bucket.cond:
            bucket.cross_proc_reentrant.append(holder)
    deferred_pin, guard_ev = False, None
    try:
        if prio.current == ExecutionPriority.FOREGROUND:
            holder.priority_handle.elevate_to_foreground()
        with _serial_execution_turn(
            bucket, spec.turn_id, spec.call_tree_id, spec.call_stack,
            lambda top: _spec_matches_ident(spec.call_tree_id, spec.turn_id, spec.call_stack, top),
            spec.cancel_token, timeout_sec, spec.resource_key,
        ):
            res = leader_fn(holder.priority_handle, spec.cancel_token, None)
        guard_ev = extract_release_guard(res) if extract_release_guard is not None else None
        return CoordinatedExecution(False, -1, res)
    finally:
        if step_guard is not None:
            step_guard.set()
        if guard_ev is not None and not guard_ev.is_set():
            with bucket.cond:
                if pin_lk is not None:
                    holder.self_exit_guard = guard_ev
                else:
                    holder.lingering_guards.append(guard_ev)
        if pin_lk is not None:
            with bucket.cond:
                has_ling = _has_lingering_guards(holder)
                if not has_ling:
                    holder.os_lock_live = False
            if has_ling:
                deferred_pin = True
                _defer_lingering_release(bucket, holder, "yscb-borrowed-pin", pin_lk.release, lambda: _remove_borrowed_locked(bucket, holder))
            if not deferred_pin:
                _remove_borrowed_locked(bucket, holder)
                pin_lk.release()
def _can_preempt_holder(incoming_prio: ExecutionPriority, target: _ActiveHolder) -> bool:
    if target.mode == ConcurrencyMode.SERIALIZE or (target.mode == ConcurrencyMode.COALESCE and not target.allow_step_coalesce):
        return False
    return not (incoming_prio == ExecutionPriority.BACKGROUND and target.priority_handle.current == ExecutionPriority.FOREGROUND)


def _try_join_existing_coalesce(
    bucket: _ResourceBucket, spec: ResourceAcquireSpec, own_prio: PriorityHandle,
    elevate_targets: list[PriorityHandle], prio_forwards: list[tuple[PriorityHandle, PriorityHandle]], adm: _BucketAdmission,
) -> bool:
    dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
    reg = FlightCallerRegistration(
        spec.turn_id, spec.call_tree_id, spec.call_stack, spec.cancel_token,
        spec.turn_cancel_token or spec.cancel_token, spec.in_event_chain, dl,
    )
    candidates = ([((bucket.active), True)] if bucket.active is not None else []) + [(w.holder, False) for w in bucket.waiters]
    for h, is_active in candidates:
        if not (h.mode == ConcurrencyMode.COALESCE and h.allow_step_coalesce and h.equiv_key == spec.equiv_key and h.flight is not None and not h.flight.done.is_set()):
            continue
        pid, det = h.flight.add_caller(reg, spec.on_progress)
        if det is None:
            continue
        if own_prio.current == ExecutionPriority.FOREGROUND:
            elevate_targets.append(h.priority_handle)
            if not is_active and bucket.active is not None:
                elevate_targets.append(bucket.active.priority_handle)
        else:
            prio_forwards.append((own_prio, h.priority_handle))
        adm.joined_flight, adm.caller_slot_id, adm.detach_fn = h.flight, pid, det
        return True
    return False


def _compose_detach(base_detach: Optional[Callable[[], None]], extra_unreg: Callable[[], None]) -> Callable[[], None]:
    def _detach_both() -> None:
        try:
            if base_detach is not None:
                base_detach()
        finally:
            extra_unreg()

    return _detach_both


def _admit_or_enqueue_in_bucket(bucket: _ResourceBucket, spec: ResourceAcquireSpec, own_prio: PriorityHandle) -> _BucketAdmission:
    adm = _BucketAdmission()
    elevate_targets: list[PriorityHandle] = []
    prio_forwards: list[tuple[PriorityHandle, PriorityHandle]] = []
    tokens_to_cancel: list[tuple[CancellationToken, str]] = []
    dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
    with bucket.cond:
        spec.cancel_token.raise_if_cancelled()
        joined = bool(spec.mode == ConcurrencyMode.COALESCE and spec.allow_step_coalesce and _try_join_existing_coalesce(bucket, spec, own_prio, elevate_targets, prio_forwards, adm))
        if not joined:
            if spec.mode == ConcurrencyMode.PREEMPT:
                rkey = str(spec.resource_key)
                if bucket.active is not None and _can_preempt_holder(own_prio.current, bucket.active):
                    tokens_to_cancel.append((bucket.active.cancel_token, f"Preempted on '{rkey}'"))
                for w in list(bucket.waiters):
                    if w.holder.mode == ConcurrencyMode.PREEMPT and _can_preempt_holder(own_prio.current, w.holder):
                        w.aborted_preempt = True
                        tokens_to_cancel.append((w.holder.cancel_token, f"Superseded in queue on '{rkey}'"))
                        bucket.waiters.remove(w)
                if tokens_to_cancel:
                    bucket.cond.notify_all()
            flight: Optional[StepFlight[object]] = None
            eff_token, holder_prio = spec.cancel_token, own_prio
            if spec.mode == ConcurrencyMode.COALESCE and spec.allow_step_coalesce:
                holder_prio = PriorityHandle(own_prio.current)
                if own_prio.current != ExecutionPriority.FOREGROUND:
                    prio_forwards.append((own_prio, holder_prio))
                flight = StepFlight(holder_prio)
                reg = FlightCallerRegistration(
                    spec.turn_id, spec.call_tree_id, spec.call_stack, spec.cancel_token,
                    spec.turn_cancel_token or spec.cancel_token, spec.in_event_chain, dl,
                )
                adm.caller_slot_id, adm.detach_fn = flight.add_caller(reg, spec.on_progress)
                eff_token = flight.cancel_group.host_token
            new_holder = _ActiveHolder(
                turn_id=flight.flight_id if flight is not None else spec.turn_id,
                call_stack=spec.call_stack[-1:] if flight is not None else spec.call_stack,
                mode=spec.mode, equiv_key=spec.equiv_key, priority_handle=holder_prio, cancel_token=eff_token,
                allow_step_coalesce=spec.allow_step_coalesce, flight=flight,
                call_tree_id=flight.flight_id if flight is not None else spec.call_tree_id, deadline=dl,
            )
            if bucket.active is None and not bucket.waiters:
                adm.holder = bucket.active = new_holder
            else:
                if own_prio.current == ExecutionPriority.FOREGROUND and bucket.active is not None:
                    elevate_targets.append(bucket.active.priority_handle)
                bucket.seq_counter += 1
                adm.waiter = _QueuedWaiter(seq=bucket.seq_counter, holder=new_holder)
                bucket.waiters.append(adm.waiter)
                bucket.waiters.sort(key=lambda w: (0 if w.holder.priority_handle.current == ExecutionPriority.FOREGROUND else 1, w.seq))
    for ph in elevate_targets:
        ph.elevate_to_foreground()
    if elevate_targets:
        with bucket.cond:
            if bucket.waiters:
                bucket.waiters.sort(key=lambda w: (0 if w.holder.priority_handle.current == ExecutionPriority.FOREGROUND else 1, w.seq))
    for src_ph, dst_ph in prio_forwards:
        adm.detach_fn = _compose_detach(adm.detach_fn, src_ph.register_listener(lambda _p, dst=dst_ph: dst.elevate_to_foreground()))
    for tok, reason_msg in tokens_to_cancel:
        tok.cancel(preempted=True, reason=reason_msg)
    return adm


def _release_and_promote_next_locked(bucket: _ResourceBucket, holder: _ActiveHolder) -> None:
    with bucket.cond:
        if bucket.active is holder:
            bucket.active = None
            while bucket.waiters:
                nxt = bucket.waiters.pop(0)
                if not nxt.aborted_preempt:
                    bucket.active, nxt.promoted = nxt.holder, True
                    nxt.wake_event.set()
                    break
        bucket.cond.notify_all()


def _release_holder_if_active(
    bucket: _ResourceBucket, holder: Optional[_ActiveHolder], paths: Optional[CrossProcessLockPaths],
    owns_os_lock: bool, pin_lk: Optional[FileLock],
) -> None:
    if holder is None:
        return
    with bucket.cond:
        has_ling = _has_lingering_guards(holder)
        if not has_ling:
            holder.os_lock_live = False
    if paths is not None:
        deferred, _ = _finalize_holder_os_lock(bucket, holder, paths, owns_os_lock, has_ling, pin_lk, _release_and_promote_next_locked)
        if deferred:
            return
    elif has_ling:
        _defer_lingering_release(bucket, holder, "yscb-local-lingering", lambda: None, lambda: _release_and_promote_next_locked(bucket, holder))
        return
    _release_and_promote_next_locked(bucket, holder)
def _acquire_or_reenter_os_lock(
    locks_dir: Optional[HostPath], spec: ResourceAcquireSpec, bucket: _ResourceBucket,
    holder: _ActiveHolder, timeout_sec: Optional[float],
) -> tuple[Optional[CrossProcessLockPaths], bool, Optional[FileLock]]:
    if locks_dir is None or not spec.resource_key:
        return (None, False, None)
    paths = CrossProcessLockPaths.for_stem(locks_dir, f"res_{hashlib.sha256(spec.resource_key.encode('utf-8')).hexdigest()[:24]}", allow_transitions=False)
    pin_lk = _try_acquire_incoming_cross_proc_reentry(locks_dir, spec, timeout_sec)
    if pin_lk is not None:
        with bucket.cond:
            holder.os_lock_live = True
        return (paths, False, pin_lk)
    paths.lock_file.acquire(shared=False, blocking=True, timeout_sec=timeout_sec, cancel_token=spec.cancel_token)
    owner_doc: JsonObject = {
        "pid": os.getpid(), "call_tree_id": holder.call_tree_id or holder.turn_id, "turn_id": holder.turn_id,
        "mode": holder.mode.value, "call_stack": [[str(ws), str(tid)] for ws, tid in holder.call_stack],
    }
    try:
        write_cross_proc_owner_json(paths.owner_path, owner_doc)
    except BaseException:
        silent_unlink(paths.owner_path)
        paths.lock_file.release()
        raise
    with bucket.cond:
        holder.os_lock_live, holder.pin_path = True, paths.pin_path
    return (paths, True, None)


def _await_queued_promotion(
    bucket: _ResourceBucket, waiter: _QueuedWaiter, cancel_token: CancellationToken,
    timeout_sec: Optional[float], resource_key: Optional[str],
) -> None:
    try:
        wait_on_event_with_cancel(waiter.wake_event, cancel_token, timeout_sec)
    except BaseException:
        with bucket.cond:
            is_active = bucket.active is waiter.holder
            if waiter in bucket.waiters:
                bucket.waiters.remove(waiter)
            bucket.cond.notify_all()
        if is_active:
            _release_and_promote_next_locked(bucket, waiter.holder)
        raise
    if waiter.aborted_preempt:
        raise YscbError(ErrorCode.TASK_PREEMPTED, f"Preempted in queue on '{resource_key}'.")


def _run_bucket_holder_execution(
    bucket: _ResourceBucket, spec: ResourceAcquireSpec, adm: _BucketAdmission, locks_dir: Optional[HostPath],
    timeout_sec: Optional[float], leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
    extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]],
) -> CoordinatedExecution[TResult]:
    holder = require_non_none(adm.holder if adm.holder is not None else (adm.waiter.holder if adm.waiter is not None else None))
    paths: Optional[CrossProcessLockPaths] = None
    owns_os_lock, pin_lk = False, None
    try:
        if adm.waiter is not None:
            _await_queued_promotion(bucket, adm.waiter, spec.cancel_token, timeout_sec, spec.resource_key)
        paths, owns_os_lock, pin_lk = _acquire_or_reenter_os_lock(locks_dir, spec, bucket, holder, timeout_sec)
        with _serial_execution_turn(
            bucket, holder.turn_id, holder.call_tree_id, holder.call_stack, None,
            holder.cancel_token, timeout_sec, spec.resource_key, reset_root=True,
        ):
            res = leader_fn(holder.priority_handle, holder.cancel_token, holder.flight)
        guard_ev = extract_release_guard(res) if extract_release_guard is not None else None
        if guard_ev is not None and not guard_ev.is_set():
            with bucket.cond:
                holder.self_exit_guard = guard_ev
        if holder.flight is not None:
            holder.flight.complete(outcome=res)
        return CoordinatedExecution(False, adm.caller_slot_id, res)
    except BaseException as exc:
        if holder.flight is not None:
            holder.flight.complete(raised_exc=exc)
        raise
    finally:
        if adm.detach_fn is not None:
            adm.detach_fn()
        _release_holder_if_active(bucket, holder, paths, owns_os_lock, pin_lk)


class ResourceCoordinator:
    """In-process + cross-process step coordinator enforcing SERIALIZE, PREEMPT, and COALESCE."""

    def __init__(
        self, *, cache_dir: Optional[HostPath] = None, workspace_root: Optional[HostPath] = None,
        resolve_cache_dir: Optional[Callable[[HostPath], Optional[HostPath]]] = None, is_daemon_host: bool = False,
    ) -> None:
        self._cache_dir, self._workspace_root, self._resolve_cache_dir, self._is_daemon_host = (
            cache_dir, workspace_root, resolve_cache_dir, is_daemon_host
        )
        self._map_lock = threading.Lock()
        self._buckets: dict[str, _ResourceBucket] = {}

    @property
    def is_daemon_host(self) -> bool:
        return self._is_daemon_host

    def _effective_locks_dir(self, call_stack: tuple[tuple[HostPath, TaskId], ...]) -> Optional[HostPath]:
        base_cache: Optional[HostPath] = None
        if call_stack:
            anchor_ws = call_stack[0][0]
            if self._workspace_root is not None and anchor_ws == self._workspace_root:
                base_cache = self._cache_dir or resolve_contained_subpath(self._workspace_root, DEFAULT_CACHE_DIRNAME)
            elif self._resolve_cache_dir is not None:
                base_cache = self._resolve_cache_dir(anchor_ws)
            if base_cache is None:
                base_cache = resolve_contained_subpath(anchor_ws, DEFAULT_CACHE_DIRNAME)
        elif self._cache_dir is not None:
            base_cache = self._cache_dir
        elif self._workspace_root is not None:
            base_cache = resolve_contained_subpath(self._workspace_root, DEFAULT_CACHE_DIRNAME)
        return resolve_contained_subpath(base_cache, LOCKS_SUBDIR) if base_cache is not None else None

    def _get_bucket(self, resource_key: str) -> _ResourceBucket:
        with self._map_lock:
            bucket = self._buckets.get(resource_key)
            if bucket is None:
                bucket = _ResourceBucket()
                self._buckets[resource_key] = bucket
            return bucket

    def coalesce_participant_count(self, resource_key: str) -> int:
        with self._map_lock:
            bucket = self._buckets.get(resource_key)
        if bucket is None:
            return 0
        with bucket.cond:
            holders = ([bucket.active] if bucket.active is not None else []) + [w.holder for w in bucket.waiters]
        return sum(h.flight.active_caller_count() for h in holders if h.flight is not None)

    def execute(
        self, spec: ResourceAcquireSpec,
        leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
        *, extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]] = None,
    ) -> CoordinatedExecution[TResult]:
        own_prio = spec.external_priority_handle or PriorityHandle(spec.priority)
        timeout_sec = ms_to_safe_sec(spec.timeout_ms) if spec.timeout_ms is not None else None
        if not spec.resource_key:
            return CoordinatedExecution(False, -1, leader_fn(own_prio, spec.cancel_token, None))
        bucket = self._get_bucket(spec.resource_key)
        reent = _check_same_stack_reentrancy(bucket, spec)
        if reent is not None:
            return _run_reentrant_or_borrowed_step(
                bucket, reent.holder, spec, own_prio, timeout_sec, leader_fn, extract_release_guard, step_guard=reent.step_guard,
            )
        _wait_active_borrowed_guards_for_caller(bucket, spec, deadline=(time.monotonic() + timeout_sec) if timeout_sec is not None else None)
        locks_dir = self._effective_locks_dir(spec.call_stack)
        if locks_dir is not None:
            pin_lk = _try_acquire_incoming_cross_proc_reentry(locks_dir, spec, timeout_sec)
            if pin_lk is not None:
                borrowed = _ActiveHolder(
                    turn_id=spec.turn_id, call_stack=spec.call_stack, mode=spec.mode, equiv_key=spec.equiv_key,
                    priority_handle=own_prio, cancel_token=spec.cancel_token, call_tree_id=spec.call_tree_id, os_lock_live=True,
                )
                return _run_reentrant_or_borrowed_step(
                    bucket, borrowed, spec, own_prio, timeout_sec, leader_fn, extract_release_guard, pin_lk=pin_lk,
                )
        adm = _admit_or_enqueue_in_bucket(bucket, spec, own_prio)
        if adm.joined_flight is not None:
            return _await_step_flight(adm.joined_flight, adm, spec.cancel_token, timeout_sec, is_follower=True)
        return _run_bucket_holder_execution(bucket, spec, adm, locks_dir, timeout_sec, leader_fn, extract_release_guard)
