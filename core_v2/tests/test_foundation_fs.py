"""Domain tests for core.foundation, core.filesystem.fs, and core.execution.{event,lifecycle,rpc}."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Callable, Optional, Sequence, Union

from core.execution.event import (
    CausalLineage,
    DoubleBufferedEventQueue,
    EventMetadata,
    EventOrdering,
    RawEventRecord,
    TaskLocalOutbox,
    hop_conflicts,
)
from core.execution.lifecycle import (
    ColdTurnRunner,
    ContainerState,
    LifoResourceStack,
    StepExecutionResult,
    TurnEngine,
    TurnExecutionReport,
    TurnKind,
    TurnScope,
    WorkerContainerLifecycle,
)
from core.execution.rpc import (
    FrameKind,
    InboundCallHandler,
    MAX_FRAME_BYTES,
    MultiplexedChannel,
    RpcServerListener,
    accept_worker_handshake,
    bind_loopback_ephemeral,
    connect_and_handshake,
)
from core.filesystem.fs import (
    CrossProcessLockPaths,
    FileLock,
    IGNORED_FS_PREFIXES,
    PollingDirectoryWatcher,
    atomic_write_bytes,
    atomic_write_json,
    hash_nofollow_regular_sha256,
    is_contained_nonsymlink_path,
    is_symlink_or_reparse,
    read_json_dict,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    DeadlineGuard,
    ErrorCode,
    ErrorDetail,
    EventId,
    HostPath,
    INT64_MAX,
    INT64_MIN,
    IS_WINDOWS,
    MAX_USER_JSON_DEPTH,
    ManagedProcessTree,
    ModuleId,
    SignalWakeupGuard,
    TaskCancelledException,
    TaskId,
    YscbError,
    clone_strict_json_object,
    get_process_start_tag,
    infer_sequence_element_dataclass,
    is_process_alive,
    require_pure_bool,
    require_pure_int,
    safe_exception_summary,
    sanitize_utf8_text,
    spawn_detached,
    strict_parse_json_object,
)
from tests._harness import assert_raises_val_error, check, expect_yscb_code, log, wait_until


@dataclass(frozen=True, slots=True)
class _CodecLeafDto:
    count: int
    ratio: float
    flag: bool
    label: str = "def"


@dataclass(frozen=True, slots=True)
class _UnionLeftDto:
    tag: str
    score: int


@dataclass(frozen=True, slots=True)
class _UnionRightDto:
    tag: str
    note: str


@dataclass(frozen=True, slots=True)
class _CodecCompositeDto:
    title: str
    item: Optional[_CodecLeafDto]
    choice: Union[_UnionLeftDto, _UnionRightDto]
    extras: tuple[_CodecLeafDto, ...] = ()


class _ToxicStrError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("toxic __str__ failure")


def _expect_codec_or_val_err(fn: Callable[[], object]) -> None:
    try:
        fn()
    except (YscbError, ValueError) as exc:
        if isinstance(exc, YscbError):
            check(exc.detail.code == ErrorCode.CODEC_VALIDATION_FAILED, f"Unexpected YscbError code: {exc.detail.code}")
        return
    raise AssertionError("Expected YscbError(CODEC_VALIDATION_FAILED) or ValueError")


def _sample_mapper(items: Sequence[_CodecLeafDto]) -> Optional[_CodecLeafDto]:
    return items[0] if items else None


def _unresolved_mapper_base(items: object) -> None:
    _ = items


def _build_nested_dict(depth: int) -> dict[str, object]:
    cur: dict[str, object] = {"leaf": 1}
    for _ in range(depth):
        cur = {"n": cur}
    return cur


def _verify_codec_contracts() -> None:
    sample = _CodecCompositeDto(
        title="alpha",
        item=_CodecLeafDto(count=42, ratio=1.5, flag=True, label="x"),
        choice=_UnionLeftDto(tag="left", score=99),
        extras=(_CodecLeafDto(count=-7, ratio=0.25, flag=False),),
    )
    raw = DataclassCodec.encode(sample)
    typed_raw = DataclassCodec.encode_typed(_CodecCompositeDto, sample)
    env = DataclassCodec.encode_envelope(sample)
    check(raw == typed_raw, "encode and encode_typed mismatch")
    check(DataclassCodec.decode_envelope(_CodecCompositeDto, env) == sample, "decode_envelope round-trip mismatch")
    check(DataclassCodec.decode(_CodecCompositeDto, raw) == sample, "decode round-trip mismatch")

    right_raw = DataclassCodec.encode(
        _CodecCompositeDto(
            title="beta",
            item=None,
            choice=_UnionRightDto(tag="right", note="ok"),
        )
    )
    decoded_right = DataclassCodec.decode(_CodecCompositeDto, right_raw)
    check(isinstance(decoded_right, _CodecCompositeDto), "Expected _CodecCompositeDto")
    check(decoded_right.item is None and isinstance(decoded_right.choice, _UnionRightDto), "Optional/Union decode mismatch")

    _expect_codec_or_val_err(
        lambda: DataclassCodec.decode(
            _CodecLeafDto, {"count": True, "ratio": 1.0, "flag": False, "label": "bad_bool"}
        )
    )
    _expect_codec_or_val_err(lambda: require_pure_int(True, "flag_as_int"))
    _expect_codec_or_val_err(lambda: require_pure_bool(1, "int_as_bool"))
    for bad_num in (math.nan, math.inf, -math.inf):
        _expect_codec_or_val_err(
            lambda v=bad_num: DataclassCodec.encode(_CodecLeafDto(count=1, ratio=v, flag=False))
        )
    _expect_codec_or_val_err(lambda: strict_parse_json_object('{"ratio": NaN}'))

    min_ok = DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MIN, "ratio": 0.0, "flag": False})
    max_ok = DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MAX, "ratio": 0.0, "flag": True})
    check(min_ok == _CodecLeafDto(count=INT64_MIN, ratio=0.0, flag=False), "INT64_MIN failed")
    check(max_ok == _CodecLeafDto(count=INT64_MAX, ratio=0.0, flag=True), "INT64_MAX failed")
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MAX + 1, "ratio": 0.0, "flag": True}))
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MIN - 1, "ratio": 0.0, "flag": False}))

    _expect_codec_or_val_err(lambda: DataclassCodec.encode(_CodecLeafDto(count=1, ratio=0.0, flag=True, label="\ud800")))
    _expect_codec_or_val_err(lambda: strict_parse_json_object('{"bad": "\\ud800"}'))
    check("\ud800" not in sanitize_utf8_text("pre\ud800post"), "sanitize_utf8_text kept lone surrogate")

    ok_depth = _build_nested_dict(MAX_USER_JSON_DEPTH - 1)
    too_deep = _build_nested_dict(MAX_USER_JSON_DEPTH)
    check(clone_strict_json_object(ok_depth) == ok_depth, "Exact max JSON depth failed")
    _expect_codec_or_val_err(lambda: clone_strict_json_object(too_deep))

    h_first = DataclassCodec.canonical_hash({"b": [1, 2], "a": {"y": True, "x": 1}})
    h_second = DataclassCodec.canonical_hash({"a": {"x": 1, "y": True}, "b": [1, 2]})
    h_bool_diff = DataclassCodec.canonical_hash({"a": {"x": True, "y": True}, "b": [1, 2]})
    check(h_first == h_second and h_first != h_bool_diff, "canonical_hash invariant failed")

    DataclassCodec.evict_module_prefix(__name__)
    check(DataclassCodec.decode(_CodecCompositeDto, raw) == sample, "decode after evict_module_prefix failed")

    ok_res, elem_cls = infer_sequence_element_dataclass(_sample_mapper, strict_unresolved=True)
    check(ok_res and elem_cls is _CodecLeafDto, f"Expected _CodecLeafDto inference, got {elem_cls!r}")
    _unresolved_mapper_base.__annotations__["items"] = "Sequence[MissingRefDto]"
    ok_unres, unres_cls = infer_sequence_element_dataclass(_unresolved_mapper_base, strict_unresolved=False)
    check((not ok_unres) and unres_cls is None, "Unresolved lenient inference should return (False, None)")
    expect_yscb_code(
        lambda: infer_sequence_element_dataclass(_unresolved_mapper_base, strict_unresolved=True),
        ErrorCode.CODEC_VALIDATION_FAILED,
    )


def _verify_foundation_primitives_errors_proc(tmp_root: Path) -> None:
    ws_hp = HostPath(tmp_root / "ws_found")
    ws_hp.path.mkdir(parents=True, exist_ok=True)

    check(safe_exception_summary(_ToxicStrError()) == "_ToxicStrError: <unprintable exception>", "Toxic str leak")
    detail = ErrorDetail(ErrorCode.BUSINESS_FAILURE, "boom", remediation="retry")
    fb_detail = detail.with_fallback_task("mod.task")
    check(fb_detail.source_task == "mod.task" and fb_detail.code == ErrorCode.BUSINESS_FAILURE, "ErrorDetail fallback failed")
    y_err = YscbError(ErrorCode.SECURITY_GATED, "denied", source_task="sec.op")
    check(y_err.detail.code == ErrorCode.SECURITY_GATED and "denied" in safe_exception_summary(y_err), "YscbError detail mismatch")

    tok_a = CancellationToken()
    tok_b = CancellationToken()
    cb_events: list[tuple[bool, str]] = []
    unreg = tok_a.register_callback(lambda p, r: cb_events.append((p, r)))
    unreg()
    tok_a.register_callback(lambda p, r: cb_events.append((p, r)))
    combined, unbind_comb = CancellationToken.combine(tok_a, tok_b)
    try:
        tok_b.cancel(preempted=True, reason="preempt_now")
        check(combined.is_cancelled and combined.is_preempted and combined.reason == "preempt_now", "combine failed")
        try:
            combined.raise_if_cancelled()
        except TaskCancelledException as exc:
            check(exc.detail.code == ErrorCode.TASK_PREEMPTED, f"Expected TASK_PREEMPTED, got {exc.detail.code}")
        else:
            raise AssertionError("Expected TaskCancelledException")
    finally:
        unbind_comb()
    tok_a.cancel(reason="manual_stop")
    check(cb_events == [(False, "manual_stop")], f"Unexpected cancel callbacks: {cb_events}")

    dg = DeadlineGuard.from_timeout_ms(250, cancel_token=CancellationToken())
    rem = dg.remaining_ms()
    check(rem is not None and 0 < rem <= 250, f"Unexpected remaining_ms: {rem}")

    assert_raises_val_error(lambda: HostPath("relative/path"))
    assert_raises_val_error(lambda: ws_hp.join("..", "escape"))
    assert_raises_val_error(lambda: ws_hp.join("bad:stream"))
    if IS_WINDOWS:
        assert_raises_val_error(lambda: ws_hp.join("CON"))
    rel_resolved = ws_hp.resolve_caller_relative("sub/item.txt")
    check(rel_resolved == ws_hp.join("sub", "item.txt"), "resolve_caller_relative mismatch")

    mod_id = ModuleId("alpha_mod")
    tid = TaskId("alpha_mod.run")
    eid = EventId("alpha_mod.evt")
    check(tid.module_id == mod_id and eid.module_id == mod_id, "module_id property mismatch")
    for bad_id in ("", "bad/slash", "no_dot", ".lead", "trail."):
        assert_raises_val_error(lambda v=bad_id: TaskId(v))
        assert_raises_val_error(lambda v=bad_id: EventId(v))
    assert_raises_val_error(lambda: ModuleId("a.b"))

    orig_sigint = signal.getsignal(signal.SIGINT)
    hits: list[str] = []
    guard = SignalWakeupGuard(
        (signal.SIGINT,),
        lambda: hits.append("first"),
        on_second_signal=lambda: hits.append("second"),
    )
    try:
        guard.install()
        signal.raise_signal(signal.SIGINT)
        wait_until(lambda: "first" in hits, timeout_sec=1.5)
        signal.raise_signal(signal.SIGINT)
        wait_until(lambda: "second" in hits, timeout_sec=1.5)
        check(hits == ["first", "second"], f"SignalWakeupGuard hits mismatch: {hits}")
    finally:
        guard.close()
        if signal.getsignal(signal.SIGINT) is not orig_sigint:
            signal.signal(signal.SIGINT, orig_sigint)
    check(signal.getsignal(signal.SIGINT) is orig_sigint, "SignalWakeupGuard failed to restore SIGINT")
    ctx_hits: list[int] = []
    with SignalWakeupGuard((signal.SIGINT,), lambda: ctx_hits.append(1)):
        signal.raise_signal(signal.SIGINT)
        wait_until(lambda: len(ctx_hits) == 1, timeout_sec=1.5)
    if signal.getsignal(signal.SIGINT) is not orig_sigint:
        signal.signal(signal.SIGINT, orig_sigint)
    check(signal.getsignal(signal.SIGINT) is orig_sigint, "Context manager failed to restore SIGINT")

    tree = ManagedProcessTree(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=ws_hp,
    )
    try:
        check(tree.pid > 0, "Invalid ManagedProcessTree pid")
        check(is_process_alive(tree.pid), "Child should be alive")
        start_tag = get_process_start_tag(tree.pid)
        check(isinstance(start_tag, str) and len(start_tag) > 0, f"Invalid start tag: {start_tag!r}")
        tree.snapshot_descendants()
        check(tree.poll() is None, "Sleep child exited prematurely")
    finally:
        tree.terminate_tree(grace_sec=0.5)
        if tree.poll() is None:
            tree.kill_tree_now()
    wait_until(lambda: not is_process_alive(tree.pid), timeout_sec=3.0)

    det_pid = spawn_detached([sys.executable, "-c", "import time; time.sleep(30)"], cwd=ws_hp)
    try:
        check(det_pid > 0 and is_process_alive(det_pid), "spawn_detached child not alive")
    finally:
        try:
            os.kill(det_pid, signal.SIGTERM)
        except OSError:
            pass
    wait_until(lambda: not is_process_alive(det_pid), timeout_sec=3.0)


def _try_create_symlink_or_junction(link_path: Path, target_path: Path, *, is_dir: bool) -> bool:
    try:
        link_path.symlink_to(target_path, target_is_directory=is_dir)
        return True
    except OSError:
        if not IS_WINDOWS or not is_dir:
            return False
        res = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
            check=False,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return res.returncode == 0


def _verify_filesystem_fs(tmp_root: Path) -> None:
    fs_root = HostPath(tmp_root / "ws_fs_root")
    outside_root = HostPath(tmp_root / "outside_fs_root")
    fs_root.path.mkdir(parents=True, exist_ok=True)
    outside_root.path.mkdir(parents=True, exist_ok=True)

    json_target = resolve_contained_subpath(fs_root, "cfg", "settings.json")
    atomic_write_json(json_target, {"version": 2, "items": ["a", "b"]})
    loaded_json = read_json_dict(fs_root, "cfg", "settings.json")
    check(loaded_json == {"version": 2, "items": ["a", "b"]}, f"Atomic JSON mismatch: {loaded_json}")

    bin_target = resolve_contained_subpath(fs_root, "cfg", "blob.bin")
    atomic_write_bytes(bin_target, b"hello-sha256")
    digest = hash_nofollow_regular_sha256(str(bin_target))
    check(len(digest) == 64, f"Unexpected sha256 digest: {digest}")

    corrupt_target = resolve_contained_subpath(fs_root, "cfg", "corrupt.json")
    atomic_write_bytes(corrupt_target, b"{not_valid_json")
    check(read_json_dict(corrupt_target) is None, "Corrupt JSON must return None")

    assert_raises_val_error(lambda: resolve_contained_subpath(fs_root, "..", "outside"))
    check(try_resolve_contained_subpath(fs_root, "..", "outside") is None, "Escape subpath must return None")
    check(is_contained_nonsymlink_path(fs_root, bin_target), "Normal file containment check failed")
    check(not is_contained_nonsymlink_path(fs_root, outside_root), "Outside path passed containment")

    secret_file = outside_root.path / "secret.txt"
    secret_file.write_text("secret", encoding="utf-8")
    link_dir = fs_root.path / "escape_dir"
    if _try_create_symlink_or_junction(link_dir, outside_root.path, is_dir=True):
        try:
            check(is_symlink_or_reparse(str(link_dir)), "Reparse/symlink not detected")
            check(not is_contained_nonsymlink_path(fs_root, link_dir, is_dir=True), "Symlink dir passed containment")
            check(
                not is_contained_nonsymlink_path(fs_root, link_dir / "secret.txt"),
                "Symlink intermediate passed containment",
            )
        finally:
            if IS_WINDOWS:
                os.rmdir(link_dir)
            else:
                link_dir.unlink(missing_ok=True)

    locks_dir = resolve_contained_subpath(fs_root, "locks")
    lock_paths = CrossProcessLockPaths.for_stem(locks_dir, "domain_res")
    lk_main = lock_paths.lock_file
    lk_peer = FileLock(lock_paths.lock_file.lock_path)
    check(lk_main.acquire(shared=False, blocking=False), "Initial exclusive lock failed")
    try:
        try:
            lk_main.acquire(shared=False, blocking=False)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Same-instance double acquire must raise RuntimeError")
        check(not lk_peer.acquire(shared=False, blocking=False), "Non-blocking lock succeeded while held")
        expect_yscb_code(lambda: lk_peer.acquire(shared=False, blocking=True, timeout_sec=0.0), ErrorCode.TASK_TIMEOUT)
        lk_main.downgrade_to_shared()
        check(lk_main.is_shared, "Lock should be shared after downgrade")
        check(lk_peer.acquire(shared=True, blocking=False), "Peer shared lock failed while downgraded")
        lk_peer.release()
        lk_main.upgrade_to_exclusive()
        check(not lk_main.is_shared, "Lock should be exclusive after upgrade")
    finally:
        if lk_peer.is_acquired:
            lk_peer.release()
        if lk_main.is_acquired:
            lk_main.release()
    child_lock_script = (
        "import sys, time\n"
        "from core.filesystem.fs import FileLock\n"
        "from core.foundation import HostPath\n"
        "lk = FileLock(HostPath(sys.argv[1]))\n"
        "assert lk.acquire(shared=False, blocking=False)\n"
        "try:\n"
        "    with open(sys.argv[2], 'w', encoding='utf-8') as f: f.write('held')\n"
        "    while not open_ok(sys.argv[3]): time.sleep(0.02)\n"
        "finally:\n"
        "    lk.release()\n"
    ).replace(
        "while not open_ok(sys.argv[3])",
        "import os\n    while not os.path.exists(sys.argv[3])",
    )
    held_marker = fs_root.path / "child_held.flag"
    release_marker = fs_root.path / "child_release.flag"
    env_cp = os.environ.copy()
    env_cp["PYTHONPATH"] = os.pathsep.join(sys.path)
    lock_proc = subprocess.Popen(
        [sys.executable, "-c", child_lock_script, str(lock_paths.lock_file.lock_path), str(held_marker), str(release_marker)],
        env=env_cp,
        creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
    )
    try:
        wait_until(lambda: held_marker.exists(), timeout_sec=5.0)
        check(not lk_peer.acquire(shared=False, blocking=False), "Cross-process lock must fail while child holds it")
        release_marker.write_text("go", encoding="utf-8")
        check(lock_proc.wait(timeout=5.0) == 0, "Lock holder child failed")
        check(lk_peer.acquire(shared=False, blocking=True, timeout_sec=2.0), "Lock acquire failed after child exited")
    finally:
        if lk_peer.is_acquired:
            lk_peer.release()
        if lock_proc.poll() is None:
            lock_proc.kill()
            lock_proc.wait(timeout=3.0)

    watch_dir = fs_root.join("watch_root")
    watch_dir.path.mkdir(parents=True, exist_ok=True)
    ignored_sub = watch_dir.path / (IGNORED_FS_PREFIXES[0] + "scratch")
    ignored_sub.mkdir(parents=True, exist_ok=True)
    suppressed_file = watch_dir.join("echo_skip.txt")
    normal_file = watch_dir.join("tracked.txt")
    batches: list[frozenset[HostPath]] = []
    batch_evt = threading.Event()
    suppressed_flag = [True]

    def _on_watch(paths: frozenset[HostPath]) -> None:
        batches.append(paths)
        batch_evt.set()

    def _is_suppressed(p: HostPath, _m: int, _s: int, _i: int) -> bool:
        return suppressed_flag[0] and p == suppressed_file

    watcher = PollingDirectoryWatcher(
        (watch_dir,),
        _on_watch,
        debounce_sec=0.04,
        poll_interval_sec=0.02,
        is_suppressed=_is_suppressed,
    )
    watcher.start()
    try:
        (ignored_sub / "temp.txt").write_text("ignored", encoding="utf-8")
        atomic_write_bytes(suppressed_file, b"suppressed_v1")
        time.sleep(0.15)
        check(not batches, f"Ignored/suppressed writes triggered watcher: {batches}")

        suppressed_flag[0] = False
        resynced = watcher.resync_paths((watch_dir,))
        check(not resynced or suppressed_file not in resynced, f"Spurious resync leakage: {resynced}")
        batches.clear()
        batch_evt.clear()

        atomic_write_bytes(normal_file, b"real_change")
        check(batch_evt.wait(timeout=2.5), "Watcher did not emit debounced batch")
        seen_paths = {p for batch in batches for p in batch}
        check(normal_file in seen_paths, f"Normal file missing in watcher batches: {seen_paths}")
        check(normal_file in watcher.tracked_paths, "Normal file missing from tracked_paths")
    finally:
        watcher.stop()


class _SampleStepExecutor:
    def __init__(self, *, fail_event: bool = False) -> None:
        self.calls: list[str] = []
        self._fail_event = fail_event

    def run_primary_step(self, request: str, turn: TurnScope) -> StepExecutionResult[str]:
        self.calls.append(f"primary:{request}")
        turn.scoped_stack.push_closeable("primary.res", lambda: self.calls.append("close:primary"))
        outbox = TaskLocalOutbox(TaskId("demo.primary"), CausalLineage())
        outbox.stage(EventId("demo.ev"), {"item": request}, ordering=EventOrdering.ORDERED)
        return StepExecutionResult(ok=True, outcome=f"done:{request}", committed_events=outbox.drain_committed())

    def run_event_step(self, batch: object, turn: TurnScope) -> Sequence[StepExecutionResult[str]]:
        _ = batch
        self.calls.append("event")
        if self._fail_event:
            diag = ErrorDetail(ErrorCode.BUSINESS_FAILURE, "event failed", source_task="demo.sub")
            turn.record_event_diagnostic(diag)
            return (StepExecutionResult(ok=False, error=diag, fatal_abort_turn=True),)
        return (StepExecutionResult(ok=True, outcome="sub_ok"),)

    def finalize_turn_events(self, _turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]:
        self.calls.append(f"finalize:{abort_only}")
        return None
class _CustomFatalBaseError(BaseException):
    pass


def _verify_event_and_lifecycle(tmp_root: Path) -> None:
    _ = tmp_root
    ev_u = EventId("mod.unord")
    ev_o = EventId("mod.ord")
    ev_meta = EventMetadata(ev_o, _CodecLeafDto, ordering=EventOrdering.ORDERED, description="ordered ev")
    check(ev_meta.event_id == ev_o and ev_meta.ordering == EventOrdering.ORDERED, "EventMetadata mismatch")

    queue = DoubleBufferedEventQueue()
    check(not queue.has_pending, "New queue should be empty")
    lin_root = CausalLineage().advance(EventId("mod.seed"), workspace_scope="ws_a")
    rec_first = RawEventRecord(ev_o, TaskId("mod.emit"), {"seq": 1}, EventOrdering.ORDERED, lin_root)
    rec_u_first = RawEventRecord(ev_u, TaskId("mod.emit"), {"k": "a"}, EventOrdering.UNORDERED, lin_root)
    rec_u_second = RawEventRecord(ev_u, TaskId("mod.emit"), {"k": "b"}, EventOrdering.UNORDERED, lin_root)
    rec_second = RawEventRecord(ev_o, TaskId("mod.emit"), {"seq": 2}, EventOrdering.ORDERED, lin_root)
    queue.append_committed((rec_first, rec_u_first, rec_u_second, rec_second))
    check(queue.has_pending, "Queue must report pending records")

    envelopes = queue.freeze_and_swap()
    check(not queue.has_pending, "Queue must empty after swap")
    ordered_seqs = [e.payloads[0]["seq"] for e in envelopes if e.event_id == ev_o]
    check(ordered_seqs == [1, 2], f"ORDERED batches broke FIFO: {ordered_seqs}")
    unord_envs = [e for e in envelopes if e.event_id == ev_u]
    check(len(unord_envs) == 1 and len(unord_envs[0].payloads) == 2, f"UNORDERED should merge: {unord_envs}")
    queue.append_committed((rec_first,))
    queue.clear()
    check(not queue.has_pending, "Queue clear failed")

    hop_a = lin_root.scoped_hops()[0]
    check(hop_conflicts(hop_a, "ws_a", EventId("mod.seed")), "Same scope+event should conflict")
    check(not hop_conflicts(hop_a, "ws_b", EventId("mod.seed")), "Different workspace scope should not conflict")
    lin_next = lin_root.advance(EventId("mod.step"), workspace_scope="ws_b")
    lin_merged = CausalLineage.merge((lin_root, lin_next))
    check(len(lin_merged.chain) >= 2, "CausalLineage merge lost hops")

    order: list[str] = []
    stack = LifoResourceStack()
    stack.push_closeable("first", lambda: order.append("first"))
    stack.push_closeable("toxic", lambda: (_ for _ in ()).throw(_ToxicStrError()))
    stack.push_closeable("sys_exit", lambda: (_ for _ in ()).throw(SystemExit(3)))
    stack.push_closeable("last", lambda: order.append("last"))
    teardown_errs = stack.close_all_lifo()
    check(order == ["last", "first"], f"LIFO order mismatch: {order}")
    check(len(teardown_errs) == 2, f"Expected 2 TEARDOWN_ERROR entries: {teardown_errs}")
    check(all(err.code == ErrorCode.TEARDOWN_ERROR for err in teardown_errs), "Wrong teardown error code")
    check(any("<unprintable exception>" in err.message for err in teardown_errs), "Toxic str leaked in teardown")

    base_order: list[str] = []
    base_stack = LifoResourceStack()
    base_stack.push_closeable("bottom", lambda: base_order.append("bottom"))
    base_stack.push_closeable("fatal", lambda: (_ for _ in ()).throw(_CustomFatalBaseError("ctrl_break")))
    base_stack.push_closeable("top", lambda: base_order.append("top"))
    try:
        base_stack.close_all_lifo()
    except _CustomFatalBaseError:
        pass
    else:
        raise AssertionError("Custom BaseException must propagate after LIFO cleanup")
    check(base_order == ["top", "bottom"], f"BaseException skipped LIFO closers: {base_order}")

    life = WorkerContainerLifecycle()
    check(life.state == ContainerState.UNINITIALIZED, "Initial state must be UNINITIALIZED")
    assert_raises_val_error(lambda: life.transition_boot_phase(ContainerState.DRAINING))
    life.transition_boot_phase(ContainerState.BOOTING)
    life.transition_boot_phase(ContainerState.WARMING)
    warm_ok: list[str] = []
    life.warmup(
        {
            ModuleId("bad_mod"): lambda: (_ for _ in ()).throw(_ToxicStrError()),
            ModuleId("good_mod"): lambda: warm_ok.append("good"),
        }
    )
    check(warm_ok == ["good"], "Warmup must isolate failing module hook")
    check(ModuleId("bad_mod") in life.degraded_modules, "Failed warmup must mark module degraded")
    life.transition_boot_phase(ContainerState.READY)
    hot_scope = life.begin_hot_turn(TurnKind.HOT_FOREGROUND, turn_id="hot_t1")
    check(hot_scope is not None and hot_scope.turn_id == "hot_t1", "begin_hot_turn failed in READY")
    life.quiesce()
    check(life.state == ContainerState.QUIESCED and life.base_state == ContainerState.READY, "Lifecycle failed to enter QUIESCED")
    life.resume()
    check(life.state == ContainerState.READY, "Lifecycle resume did not restore READY")
    drain_errs = life.drain_and_stop(grace_period_ms=500)
    check(life.state == ContainerState.STOPPED and drain_errs == (), "drain_and_stop failed")
    check(life.begin_hot_turn(TurnKind.HOT_FOREGROUND) is None, "STOPPED must reject new hot turns")

    ok_exec = _SampleStepExecutor(fail_event=False)
    ok_engine = TurnEngine(ok_exec)
    ok_rep: TurnExecutionReport = ok_engine.execute_turn("alpha", TurnKind.COLD, turn_id="cold_t1")
    check(ok_rep.primary_result.ok and ok_rep.fatal_event_error is None, "TurnEngine turn failed")
    check("event" in ok_exec.calls and "close:primary" in ok_exec.calls, f"Missing turn stages: {ok_exec.calls}")

    fail_exec = _SampleStepExecutor(fail_event=True)
    fail_runner = ColdTurnRunner(
        TurnEngine(fail_exec),
        on_bootstrap_check=lambda st: st.push_closeable("boot", lambda: fail_exec.calls.append("close:boot")),
    )
    bad_scope = TurnScope("cold_t2", TurnKind.COLD, CancellationToken())
    bad_rep = fail_runner.execute_leased_turn("beta", scope=bad_scope, fallback_task="demo.primary")
    check(bad_rep.fatal_event_error is not None, "Fatal event error not surfaced")
    check("close:boot" in fail_exec.calls, "ColdTurnRunner failed to close bootstrap closer")


class _RpcProbeHandler(InboundCallHandler):
    def __init__(self) -> None:
        self.call_started = threading.Event()
        self.allow_finish = threading.Event()
        self.saw_peer_cancel = threading.Event()

    def on_call(
        self,
        _stream_id: int,
        payload: dict[str, object],
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[dict[str, object]], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, dict[str, object]]:
        _ = ack_accepted()
        self.call_started.set()
        mode = str(payload.get("mode", "fast"))
        emit_progress({"phase": mode})
        if mode == "hold":
            self.allow_finish.wait(timeout=4.0)
        elif mode == "wait_cancel":
            if peer_cancel_token.wait(timeout_sec=3.0):
                self.saw_peer_cancel.set()
            return (False, {"cancelled": True})
        return (True, {"echo": payload.get("val")})

    def on_control(self, kind: FrameKind, payload: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "kind": kind.value, "keys": list(payload.keys())}
def _verify_execution_rpc(tmp_root: Path) -> None:
    check(MAX_FRAME_BYTES == 67108864, f"Unexpected MAX_FRAME_BYTES: {MAX_FRAME_BYTES}")
    rpc_ws = HostPath(tmp_root / "ws_rpc")
    rpc_ws.path.mkdir(parents=True, exist_ok=True)
    probe_handler = _RpcProbeHandler()

    srv = RpcServerListener(rpc_ws, probe_handler, boot_id="boot_rpc_1", auth_token="rpc_secret")
    ep = srv.start()
    cli_ep_ch = None
    try:
        cli_ep_ch = connect_and_handshake(ep, handler=probe_handler, connect_timeout_sec=2.0)
        check(cli_ep_ch is not None and cli_ep_ch.ping(timeout_ms=2000), "RpcServerListener handshake/ping failed")
    finally:
        if cli_ep_ch is not None:
            cli_ep_ch.close()
        srv.close_all()

    hs_sock = bind_loopback_ephemeral()
    bad_cli: Optional[socket.socket] = None
    accepted_conn: Optional[socket.socket] = None
    try:
        hs_addr = hs_sock.getsockname()
        bad_cli = socket.create_connection((str(hs_addr[0]), int(hs_addr[1])), timeout=2.0)
        bad_cli.sendall(struct.pack(">I", 65537) + b"{}")
        accepted_conn, _addr = hs_sock.accept()
        accepted_ch = accept_worker_handshake(
            accepted_conn,
            expected_auth_token="rpc_secret",
            boot_id="boot_hs",
            handler=probe_handler,
            expected_workspace_root=rpc_ws,
        )
        check(accepted_ch is None, "Pre-auth oversized frame must be rejected")
    finally:
        for sock_obj in (accepted_conn, bad_cli, hs_sock):
            if sock_obj is not None:
                try:
                    sock_obj.close()
                except OSError:
                    pass

    left_sock, right_sock = socket.socketpair()
    cli_ch: Optional[MultiplexedChannel] = None
    srv_ch: Optional[MultiplexedChannel] = None
    try:
        cli_ch = MultiplexedChannel(left_sock, is_initiator=True, handler=probe_handler, max_frame_bytes=512)
        srv_ch = MultiplexedChannel(right_sock, is_initiator=False, handler=probe_handler, max_frame_bytes=512)
        nodelay_val = left_sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        check(nodelay_val != 0, f"TCP_NODELAY not enabled on MultiplexedChannel: {nodelay_val}")

        big_out = cli_ch.call({"mode": "fast", "val": "x" * 1024})
        check(
            (not big_out.was_accepted) and big_out.error_code == ErrorCode.PAYLOAD_TOO_LARGE,
            f"Oversized payload should fail PAYLOAD_TOO_LARGE: {big_out}",
        )

        pre_cancel = CancellationToken()
        pre_cancel.cancel(reason="pre_aborted")
        unsent_out = cli_ch.call({"mode": "fast", "val": 1}, cancel_token=pre_cancel)
        check(
            (not unsent_out.was_accepted) and unsent_out.error_code == ErrorCode.TASK_CANCELLED,
            f"Pre-cancelled call should never be accepted: {unsent_out}",
        )

        probe_handler.call_started.clear()
        hold_res: list[object] = []

        def _run_hold() -> None:
            hold_res.append(cli_ch.call({"mode": "hold", "val": 99}))

        hold_thr = threading.Thread(target=_run_hold, daemon=True)
        hold_thr.start()
        check(probe_handler.call_started.wait(timeout=2.0), "Hold call did not start")
        srv_ch.close_when_idle()
        check(not srv_ch.is_closed, "close_when_idle must keep retiring channel alive while call in-flight")
        probe_handler.allow_finish.set()
        hold_thr.join(timeout=3.0)
        check(bool(hold_res) and srv_ch.wait_until_closed(timeout_sec=3.0), "Retiring channel failed to drain and close")
    finally:
        if cli_ch is not None:
            cli_ch.close()
        if srv_ch is not None:
            srv_ch.close()
        for raw_s in (left_sock, right_sock):
            try:
                raw_s.close()
            except OSError:
                pass

    c_left, c_right = socket.socketpair()
    cancel_cli: Optional[MultiplexedChannel] = None
    cancel_srv: Optional[MultiplexedChannel] = None
    try:
        probe_handler.call_started.clear()
        probe_handler.saw_peer_cancel.clear()
        cancel_cli = MultiplexedChannel(c_left, is_initiator=True, handler=probe_handler)
        cancel_srv = MultiplexedChannel(c_right, is_initiator=False, handler=probe_handler)
        live_tok = CancellationToken()
        progress_seen = threading.Event()

        def _trigger_cancel() -> None:
            if progress_seen.wait(timeout=2.0):
                live_tok.cancel(reason="abort_in_flight")

        canceller = threading.Thread(target=_trigger_cancel, daemon=True)
        canceller.start()
        in_flight_out = cancel_cli.call(
            {"mode": "wait_cancel"},
            on_progress=lambda _p: progress_seen.set(),
            cancel_token=live_tok,
        )
        canceller.join(timeout=2.0)
        check(in_flight_out.was_accepted and probe_handler.saw_peer_cancel.is_set(), "Accepted cancel failed to propagate")
    finally:
        if cancel_cli is not None:
            cancel_cli.close()
        if cancel_srv is not None:
            cancel_srv.close()
        for raw_s in (c_left, c_right):
            try:
                raw_s.close()
            except OSError:
                pass


def run_foundation_fs_suite(tmp_root: Path) -> None:
    """Run all domain unit checks for foundation, filesystem.fs, and execution.{event,lifecycle,rpc}."""
    suite_root = tmp_root / "domain_foundation_fs"
    suite_root.mkdir(parents=True, exist_ok=True)
    log("[FOUNDATION-FS] Verifying DataclassCodec contracts...")
    _verify_codec_contracts()
    log("[FOUNDATION-FS] Verifying foundation primitives, errors, signals, and process trees...")
    _verify_foundation_primitives_errors_proc(suite_root)
    log("[FOUNDATION-FS] Verifying filesystem atomic I/O, containment, locks, and watcher...")
    _verify_filesystem_fs(suite_root)
    log("[FOUNDATION-FS] Verifying execution event queue, lifecycle, and RPC channels...")
    _verify_event_and_lifecycle(suite_root)
    _verify_execution_rpc(suite_root)
    log("[FOUNDATION-FS] All domain checks passed.")


__all__ = ("run_foundation_fs_suite",)
