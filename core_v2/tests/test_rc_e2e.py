"""End-to-end live verification suite covering daemon lifecycle, locking, events, and isolation."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from enum import IntEnum
import functools
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import typing
from typing import Callable, Final, Mapping, Optional, Sequence

if os.name != "nt":
    import pty

from core.execution.event import EventSubscriptionSpec
from core.execution.rpc import (
    FrameKind,
    PersistentRpcSession,
    probe_daemon_endpoint,
    query_daemon_control,
    read_daemon_endpoint_file,
    wait_for_handoff_daemon_endpoint,
)
from core.execution.runtime import (
    CallPropagationContext,
    ClientRoutingPolicy,
    ExecutionPriority,
    InvokeRequest,
    RuntimeDispatcher,
    TaskMetadata,
)
from core.filesystem.fs import FileLock, atomic_write_bytes, atomic_write_json, read_json_dict
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    ErrorCode,
    EventId,
    HostPath,
    JsonObject,
    ModuleId,
    TaskId,
    is_process_alive,
)
from tests._boot import (
    build_dispatcher_for_workspace,
    live_host_boot_script_path,
    resolve_dedicated_venv_py,
)
from tests._harness import (
    AST_OUTLINE_META,
    ECHO_TIER0_META,
    EchoInDto,
    GdriveOutDto,
    IndexOutDto,
    KDB_SEARCH_META,
    OutlineInDto,
    SandboxOutDto,
    SearchInDto,
    SearchOutDto,
    SimpleOutDto,
    assert_zero_live_stage_orphans,
    check,
    expect_yscb_code,
    force_reap_tmp_root_orphans,
    jfloat,
    jint,
    jlist,
    log,
    provision_live_workspace,
    reap_popen_quietly,
    run_cli_subproc,
    scoped_timer,
    stop_daemon_cleanly,
    wait_file_marker,
    wait_for_daemon_online,
    wait_until,
)


@dataclass(frozen=True, slots=True)
class Rc02StageRig:
    """Shared live workspace and dispatcher rig handed from stage 02 to stage 03."""

    ws: HostPath
    ws_path: Path
    dispatcher: RuntimeDispatcher


class _SampleIntEnum(IntEnum):
    FAST = 1
    SAFE = 2


@dataclass(frozen=True, slots=True)
class _MapperLeafDto:
    val: int


_TGenEnv = typing.TypeVar("_TGenEnv")


@dataclass(frozen=True, slots=True)
class _GenEnvelopeBase(typing.Generic[_TGenEnv]):
    payload: _TGenEnv
    label: str = "ok"


def _map_concrete_gen_payload(items: Sequence[_GenEnvelopeBase[int]]) -> int:
    return sum(x.payload for x in items)


@dataclass(frozen=True, slots=True)
class _UnionKeyMapDto:
    entries: dict[_SampleIntEnum | int, str]


def _make_repeated_local_codec_pair(scale: int) -> tuple[tuple[type, dict[str, type]], object]:
    @dataclass(frozen=True, slots=True)
    class LocalLeaf:
        v: int

    @dataclass(frozen=True, slots=True)
    class LocalHolder:
        item: LocalLeaf

    def _map_items(items: Sequence[LocalLeaf]) -> int:
        return sum(x.v for x in items if isinstance(x, LocalLeaf)) * scale

    spec = EventSubscriptionSpec(EventId("unionmod.local_union"), _map_items)
    return ((LocalHolder, {"LocalLeaf": LocalLeaf}), spec)


def verify_rc01_cold_storm_and_sandbox(tmp_root: Path, venv_py: Path) -> None:
    """Verify static CLI short-circuit, cold no-spawn, 10-process spawn storm, warming queue, and restricted sandbox."""
    log("[RC-01] Testing static help, AUTO_NO_SPAWN, 10-proc storm (spawn_count==1), stale JSON & sandbox...")
    ws1_path = tmp_root / "ws_rc01"
    provision_live_workspace(ws1_path)
    ws1 = HostPath(ws1_path)
    stale_json = ws1.join(".cache", "daemon", "daemon.json")
    atomic_write_json(stale_json, {"pid": 999999, "host": "127.0.0.1", "port": 65431, "boot_id": "s", "auth_token": "s", "workspace_root": str(ws1)})
    check(query_daemon_control(ws1.join(".cache"), ws1, FrameKind.CONTROL_STATUS) is None)
    check(stale_json.path.is_file())

    help_r = run_cli_subproc(ws1, venv_py, str(ws1), "--help", {}, ClientRoutingPolicy.AUTO_SPAWN)
    check(help_r["ok"] is True and not ws1.join(".cache", "ast_lazy_inited.json").path.exists())
    check(jint(read_json_dict(ws1.join(".cache", "daemon_spawn_count.json")), "spawns", 0) == 0)

    sub_cwd = str(ws1_path / "sub_dir")
    nospawn_cold = run_cli_subproc(ws1, venv_py, sub_cwd, "ast.outline", {"rel_file": "./sample.py"}, ClientRoutingPolicy.AUTO_NO_SPAWN)
    check(nospawn_cold["ok"] is True and nospawn_cold["executed_hot"] is False)
    check(jint(read_json_dict(ws1.join(".cache", "daemon_spawn_count.json")), "spawns", 0) == 0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        storm_results = list(
            pool.map(lambda _i: run_cli_subproc(ws1, venv_py, sub_cwd, "ast.outline", {"rel_file": "./sample.py"}, ClientRoutingPolicy.AUTO_SPAWN), range(10))
        )
    for r in storm_results:
        val = r["value"]
        check(r["ok"] is True and isinstance(val, dict) and val["exists"] is True and val["lazy_ready"] is True)
        check(Path(str(val["resolved_path"])) == (ws1_path / "sub_dir" / "sample.py").resolve())

    st1 = wait_for_daemon_online(ws1)
    check(st1["state"] == "ready")
    check(jint(read_json_dict(ws1.join(".cache", "daemon_spawn_count.json")), "spawns", 0) == 1)
    time.sleep(0.15)
    ttl_before = jfloat(wait_for_daemon_online(ws1), "idle_ttl_remaining_sec", 99.0)
    check(run_cli_subproc(ws1, venv_py, str(ws1), "--help", {}, ClientRoutingPolicy.AUTO_SPAWN)["ok"] is True)
    ttl_after = jfloat(wait_for_daemon_online(ws1), "idle_ttl_remaining_sec", 99.0)
    check(ttl_after <= ttl_before + 0.02)
    typo_r = run_cli_subproc(ws1, venv_py, str(ws1), "unknown.outline", {}, ClientRoutingPolicy.AUTO_SPAWN)
    check(typo_r["ok"] is False and isinstance(typo_r.get("suggestions"), list) and len(typo_r["suggestions"]) >= 1)
    nospawn_hot = run_cli_subproc(ws1, venv_py, sub_cwd, "ast.outline", {"rel_file": "./sample.py"}, ClientRoutingPolicy.AUTO_NO_SPAWN)
    check(nospawn_hot["ok"] is True and nospawn_hot["executed_hot"] is True)
    stop_daemon_cleanly(ws1)
    _verify_rc01_booting_warming_queue(tmp_root, venv_py)
    _verify_rc01_restricted_sandbox(tmp_root, venv_py)
    log("  -> PASS: RC-01 verified.")


def _poll_warming_state(ws_w: HostPath, warming_ev: threading.Event, stop_ev: threading.Event) -> None:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and not stop_ev.is_set():
        st_raw = query_daemon_control(ws_w.join(".cache"), ws_w, FrameKind.CONTROL_STATUS)
        if st_raw and isinstance(st_raw.get("status"), Mapping) and st_raw["status"].get("state") == "warming":
            warming_ev.set()
            return
        time.sleep(0.015)


def _verify_rc01_booting_warming_queue(tmp_root: Path, venv_py: Path) -> None:
    ws_w_path = tmp_root / "ws_rc01_warming"
    provision_live_workspace(ws_w_path)
    ws_w = HostPath(ws_w_path)
    atomic_write_json(ws_w.join("config", "kdb.json"), {"warmup_delay_ms": 650})
    disp_w = build_dispatcher_for_workspace(ws_w, HostPath(venv_py), ttl_sec=8.0).dispatcher
    warming_ev = threading.Event()
    stop_poll = threading.Event()
    poller = threading.Thread(target=_poll_warming_state, args=(ws_w, warming_ev, stop_poll), daemon=True)
    poller.start()
    try:
        disp_w.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="trigger_spawn"))
        check(warming_ev.wait(timeout=5.0), "Expected observable DaemonRunState.WARMING window!")
        queued_hot = disp_w.invoke_typed(
            AST_OUTLINE_META,
            OutlineInDto(rel_file="./sample.py"),
            caller_cwd=HostPath(ws_w_path / "sub_dir"),
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
        )
        check(queued_hot.ok and queued_hot.executed_hot is True)
    finally:
        stop_poll.set()
        poller.join(timeout=1.0)
        stop_daemon_cleanly(ws_w)
        disp_w.shutdown()


def _verify_rc01_restricted_sandbox(tmp_root: Path, venv_py: Path) -> None:
    ws_sb_path = tmp_root / "ws_rc01_sb"
    provision_live_workspace(ws_sb_path)
    disp_sb = build_dispatcher_for_workspace(HostPath(ws_sb_path), HostPath(venv_py), sandbox_restricted=True).dispatcher
    try:
        d_only = disp_sb.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=HostPath(ws_sb_path), caller_cwd=HostPath(ws_sb_path)))
        check(not d_only.ok and d_only.error is not None and d_only.error.code == ErrorCode.DAEMON_UNAVAILABLE)

        sb_out = disp_sb.invoke_typed(
            AST_OUTLINE_META,
            OutlineInDto(rel_file="./sample.py", call_tier0=True),
            caller_cwd=HostPath(ws_sb_path / "sub_dir"),
            routing_policy=ClientRoutingPolicy.AUTO_NO_SPAWN,
        )
        check(sb_out.ok and sb_out.value is not None and sb_out.value.lazy_ready is True)
        check(sb_out.value.tier0_echo == "tier0:v1:SPACE_H:from_oneshot_tier1")
        check((ws_sb_path / ".cache" / "tier1_imm_seen.json").is_file())
        sb_strict_fail = disp_sb.invoke_typed(
            AST_OUTLINE_META,
            OutlineInDto(rel_file="./sample.py", call_tier0=True, fail_imm_strict=True),
            caller_cwd=HostPath(ws_sb_path / "sub_dir"),
            routing_policy=ClientRoutingPolicy.AUTO_NO_SPAWN,
        )
        check(not sb_strict_fail.ok and sb_strict_fail.error is not None)
        check(not (ws_sb_path / ".cache" / "daemon" / "daemon.json").exists())
    finally:
        disp_sb.shutdown()


def verify_rc02_warmup_events_and_preempt(tmp_root: Path, venv_py: Path) -> Rc02StageRig:
    """Verify co-located Tier 1 fault isolation, lazy/stateless zero-boot, static filter, and PREEMPT."""
    log("[RC-02] Testing co-located Tier 1 warmup fault isolation, lazy/stateless zero-boot, Tier 0 filter & PREEMPT proof...")
    ws2_path = tmp_root / "ws_rc02"
    provision_live_workspace(ws2_path, include_broken_opt=True)
    ws2 = HostPath(ws2_path)
    disp2 = build_dispatcher_for_workspace(ws2, HostPath(venv_py), ttl_sec=20.0).dispatcher
    try:
        check(disp2.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot")).ok)
        st2 = wait_for_daemon_online(ws2)

        check("broken_opt" in jlist(st2, "degraded_modules"))
        workers_boot = jlist(st2, "active_tier1_workers")
        check(len(workers_boot) == 1 and isinstance(workers_boot[0], dict) and workers_boot[0].get("group") == "idx_group")

        time.sleep(0.22)
        check(not ws2.join(".cache", "ast_state.json").path.exists())
        check(not ws2.join(".cache", "ast_lazy_inited.json").path.exists())

        deg_out = disp2.invoke(InvokeRequest(task_id=TaskId("broken_opt.ping"), raw_input={}, workspace_root=ws2, caller_cwd=ws2))
        check(not deg_out.ok and deg_out.error is not None and deg_out.error.code == ErrorCode.MODULE_DEGRADED)
        exp_denied = disp2.invoke(InvokeRequest(task_id=TaskId("space.scan"), raw_input={}, workspace_root=ws2, caller_cwd=ws2))
        check(not exp_denied.ok and exp_denied.error is not None and exp_denied.error.code == ErrorCode.EXPOSURE_DENIED)

        _verify_rc02_preempt_and_static_filter(ws2, ws2_path, disp2)
        log("  -> PASS: RC-02 verified.")
        return Rc02StageRig(ws2, ws2_path, disp2)
    except BaseException:
        stop_daemon_cleanly(ws2)
        disp2.shutdown()
        raise


def _verify_rc02_preempt_and_static_filter(ws2: HostPath, ws2_path: Path, disp2: RuntimeDispatcher) -> None:
    (ws2_path / "spaces" / "ignored_logs" / "noise.log").write_text("isolated_noise\n", encoding="utf-8")
    time.sleep(0.24)
    check(not ws2.join(".cache", "ast_state.json").path.exists())
    check(not ws2.join(".cache", "ast_lazy_inited.json").path.exists())

    atomic_write_json(ws2.join("config", "kdb.json"), {"bg_wave1_ms": 1800})
    (ws2_path / "spaces" / "source" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (ws2_path / "spaces" / "docs" / "b.md").write_text("# doc\n", encoding="utf-8")
    deadline_in = time.monotonic() + 4.0
    while time.monotonic() < deadline_in:
        if jint(read_json_dict(ws2.join(".cache", "kdb_bg_inflight.json")), "in_flight_gen", 0) >= 1:
            break
        time.sleep(0.02)
    check(jint(read_json_dict(ws2.join(".cache", "kdb_bg_inflight.json")), "in_flight_gen", 0) == 1)
    (ws2_path / "spaces" / "ignored_logs" / "inflight_noise.log").write_text("no_preempt\n", encoding="utf-8")
    time.sleep(0.14)
    check(jint(read_json_dict(ws2.join(".cache", "kdb_preempt_stats.json")), "preempted_count", 0) == 0)

    (ws2_path / "spaces" / "source" / "a.py").write_text("x = 2\n", encoding="utf-8")

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        bg_st = read_json_dict(ws2.join(".cache", "kdb_bg_state.json"))
        ast_st = read_json_dict(ws2.join(".cache", "ast_state.json"))
        if bg_st and ast_st and jint(ast_st, "ast_gen") >= 2 and jint(bg_st, "acked_ast_gen") == jint(ast_st, "ast_gen"):
            break
        time.sleep(0.04)
    bg_st = read_json_dict(ws2.join(".cache", "kdb_bg_state.json"))
    ast_st = read_json_dict(ws2.join(".cache", "ast_state.json"))
    p_stats = read_json_dict(ws2.join(".cache", "kdb_preempt_stats.json"))
    check(jint(ast_st, "ast_gen") >= 2 and jint(bg_st, "acked_ast_gen") == jint(ast_st, "ast_gen"))
    check(jint(p_stats, "preempted_count") >= 1, lambda: f"Expected real PREEMPT abort proof, got {p_stats}")

    check(disp2.invoke(InvokeRequest(task_id=TaskId("vsc.sync"), raw_input={}, workspace_root=ws2, caller_cwd=ws2)).ok)
    runs_after_vsc = jint(read_json_dict(ws2.join(".cache", "ast_state.json")), "runs")
    time.sleep(0.25)
    check(jint(read_json_dict(ws2.join(".cache", "ast_state.json")), "runs") == runs_after_vsc)


def verify_rc03_coalesce_priority_and_nested_group(ws2: HostPath, ws2_path: Path, disp2: RuntimeDispatcher) -> None:
    """Verify snapshot reads, priority inheritance, COALESCE semantics, and nested SERIALIZE fallback."""
    log("[RC-03] Testing snapshot read, priority inheritance, normalized/custom COALESCE, leader-cancel & subscriber fault isolation...")
    progress_seen: list[JsonObject] = []
    follower_progress: list[JsonObject] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        f_bg = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 240}, workspace_root=ws2, caller_cwd=ws2, priority=ExecutionPriority.BACKGROUND),
            output_type=IndexOutDto,
        )
        time.sleep(0.04)
        f_fg_eq = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": False, "export_path": "", "sleep_ms": 240}, workspace_root=ws2, caller_cwd=ws2),
            output_type=IndexOutDto,
            on_progress=follower_progress.append,
        )
        f_fg_diff = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": True, "export_path": "./exported_bundle.json", "sleep_ms": 60}, workspace_root=ws2, caller_cwd=HostPath(ws2_path / "sub_dir")),
            output_type=IndexOutDto,
            on_progress=progress_seen.append,
        )
        time.sleep(0.03)
        read_out = disp2.invoke_typed(KDB_SEARCH_META, SearchInDto(query="fast", sync=False))
        check(not f_bg.done(), "Lock-free read should finish while slow kdb.index still holds kdb lock!")
        r_bg, r_fg_eq, r_fg_diff = f_bg.result(timeout=10), f_fg_eq.result(timeout=10), f_fg_diff.result(timeout=10)

    check(read_out.ok and read_out.value is not None and read_out.value.warm_model_ready is True)
    check(r_bg.ok and r_bg.value is not None and r_bg.value.observed_priority == "foreground")
    check(r_fg_eq.ok and r_fg_eq.coalesced is True and len(follower_progress) >= 1)
    check(r_fg_diff.ok and r_fg_diff.coalesced is False and (ws2_path / "sub_dir" / "exported_bundle.json").is_file())
    check(len(progress_seen) >= 2 and progress_seen[0].get("phase") == "indexing")

    _verify_rc03_custom_equiv_cancel_and_step5(ws2, ws2_path, disp2)
    _verify_rc03_cross_layer_and_step5_fatal_coalesce(ws2, disp2)
    log("  -> PASS: RC-03 verified.")


def _verify_rc03_custom_equiv_cancel_and_step5(ws2: HostPath, ws2_path: Path, disp2: RuntimeDispatcher) -> None:
    leader_tok = CancellationToken()
    fl_in = threading.Event()
    ff_joined = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fl = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("vsc.sync"), raw_input={"trace_note": "alpha", "sleep_ms": 360}, workspace_root=ws2, caller_cwd=ws2),
            cancel_token=leader_tok,
            on_progress=lambda _p: fl_in.set(),
        )
        check(fl_in.wait(timeout=5.0))
        ff = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("vsc.sync"), raw_input={"trace_note": "beta", "sleep_ms": 360}, workspace_root=ws2, caller_cwd=ws2),
            on_progress=lambda _p: ff_joined.set(),
        )
        check(ff_joined.wait(timeout=5.0))
        leader_tok.cancel()
        out_l, out_f = fl.result(timeout=10), ff.result(timeout=10)
    check(not out_l.ok and out_l.error is not None and out_l.error.code == ErrorCode.TASK_CANCELLED)
    check(out_f.ok and out_f.coalesced is True)

    nested_prog: list[JsonObject] = []
    ast_probe = disp2.invoke_typed(AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py"), caller_cwd=HostPath(ws2_path / "sub_dir"))
    synced = disp2.invoke(
        InvokeRequest(task_id=TaskId("kdb.search"), raw_input={"query": "aligned", "sync": True}, workspace_root=ws2, caller_cwd=ws2),
        output_type=SearchOutDto,
        on_progress=nested_prog.append,
    )
    check(ast_probe.ok and ast_probe.value is not None and synced.ok and synced.value is not None)
    check(ast_probe.value.worker_pid == synced.value.worker_pid and len(nested_prog) >= 1)

    sub_fault_in = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 260, "trigger_step5_error": True}, workspace_root=ws2, caller_cwd=ws2), on_progress=lambda _p: sub_fault_in.set())
        check(sub_fault_in.wait(timeout=5.0))
        f2 = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 260, "trigger_step5_error": True}, workspace_root=ws2, caller_cwd=ws2))
        o1, o2 = f1.result(timeout=10), f2.result(timeout=10)
    check(o1.ok and o2.ok and o2.coalesced is True)
    check(len(o1.event_diagnostics) == 1 and len(o2.event_diagnostics) == 1)
    check(ws2.join(".cache", "sibling_sub_ok.json").path.is_file())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fb1 = pool.submit(disp2.emit_background_event, EventId("kdb.trigger_step5_fail"), {"query": "x"})
        fb2 = pool.submit(disp2.emit_background_event, EventId("kdb.trigger_step5_fail"), {"query": "x"})
        rb1, rb2 = fb1.result(timeout=10), fb2.result(timeout=10)
    check(len(rb1.event_diagnostics) == 1 and len(rb2.event_diagnostics) == 1)

    fc1_in = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fc1 = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 260, "fail_primary": True}, workspace_root=ws2, caller_cwd=ws2), on_progress=lambda _p: fc1_in.set())
        check(fc1_in.wait(timeout=5.0))
        fc2 = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 260, "fail_primary": True}, workspace_root=ws2, caller_cwd=ws2))
        oc1, oc2 = fc1.result(timeout=10), fc2.result(timeout=10)
    check(not oc1.ok and oc1.error is not None and oc1.error.code == ErrorCode.BUSINESS_FAILURE)
    check(not oc2.ok and oc2.coalesced is True and oc2.error is not None and oc2.error.code == ErrorCode.BUSINESS_FAILURE)


def _verify_rc03_cross_layer_and_step5_fatal_coalesce(ws2: HostPath, disp2: RuntimeDispatcher) -> None:
    gen_before = jint(read_json_dict(ws2.join(".cache", "kdb_state.json")), "kdb_gen", 0)
    entered_1 = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        ft = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": False, "sleep_ms": 260}, workspace_root=ws2, caller_cwd=ws2),
            on_progress=lambda _p: entered_1.set(),
        )
        check(entered_1.wait(timeout=5.0))
        fn = pool.submit(disp2.invoke_typed, KDB_SEARCH_META, SearchInDto(query="nested_serialize", sync=True))
        r_ft, r_fn = ft.result(timeout=10), fn.result(timeout=10)
        check(r_ft.ok and not r_ft.coalesced and r_fn.ok and r_fn.value is not None)
    check(jint(read_json_dict(ws2.join(".cache", "kdb_state.json")), "kdb_gen", 0) == gen_before + 2)

    ws2.join(".cache", "sibling_sub_ok.json").path.unlink(missing_ok=True)
    sync_m = ws2.path / ".cache" / "search_sync_entered.json"
    sync_m.unlink(missing_ok=True)
    tok_top_c = CancellationToken()
    entered_2 = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        ftc = pool.submit(
            disp2.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": False, "sleep_ms": 260, "trigger_step5_error": True}, workspace_root=ws2, caller_cwd=ws2),
            cancel_token=tok_top_c,
            on_progress=lambda _p: entered_2.set(),
        )
        check(entered_2.wait(timeout=5.0))
        fnc = pool.submit(disp2.invoke_typed, KDB_SEARCH_META, SearchInDto(query="ev_err", sync=True))
        wait_file_marker(sync_m, timeout_sec=5.0)
        time.sleep(0.04)
        tok_top_c.cancel()
        rtc, rnc = ftc.result(timeout=10), fnc.result(timeout=10)
    check(not rtc.ok and rtc.error is not None and rtc.error.code == ErrorCode.TASK_CANCELLED)
    check(rnc.ok and ws2.join(".cache", "sibling_sub_ok.json").path.is_file())

    fe1_in = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fe1 = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 260, "trigger_ev_cycle": True}, workspace_root=ws2, caller_cwd=ws2), on_progress=lambda _p: fe1_in.set())
        check(fe1_in.wait(timeout=5.0))
        fe2 = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"sleep_ms": 260, "trigger_ev_cycle": True}, workspace_root=ws2, caller_cwd=ws2))
        oe1, oe2 = fe1.result(timeout=10), fe2.result(timeout=10)
    check(not oe1.ok and oe1.error is not None and oe1.error.code == ErrorCode.EVENT_CYCLE_DETECTED)
    check(not oe2.ok and oe2.coalesced is True and oe2.error is not None and oe2.error.code == ErrorCode.EVENT_CYCLE_DETECTED)

    sync_m.unlink(missing_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fn_first = pool.submit(disp2.invoke_typed, KDB_SEARCH_META, SearchInDto(query="ev_cyc", sync=True))
        wait_file_marker(sync_m, timeout_sec=5.0)
        time.sleep(0.04)
        ft_second = pool.submit(disp2.invoke, InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": False, "sleep_ms": 260, "trigger_ev_cycle": True}, workspace_root=ws2, caller_cwd=ws2))
        r_nf, r_ts = fn_first.result(timeout=10), ft_second.result(timeout=10)
    check(not r_nf.ok and r_nf.error is not None and r_nf.error.code == ErrorCode.EVENT_CYCLE_DETECTED)
    check(not r_ts.ok and r_ts.coalesced is False and r_ts.error is not None and r_ts.error.code == ErrorCode.EVENT_CYCLE_DETECTED)


def verify_rc04_multiplex_cancel_and_ttl(tmp_root: Path, venv_py: Path) -> None:
    """Verify multiplexed RPC streams, cancellation, idle TTL expiry, reconnect, and graceful draining."""
    log("[RC-04] Testing multiplexed streams, P2/P3 CANCEL, Idle TTL, hot session reconnect & graceful DRAINING...")
    ws4_path = tmp_root / "ws_rc04"
    provision_live_workspace(ws4_path)
    ws4 = HostPath(ws4_path)
    sess4 = PersistentRpcSession(ws4.join(".cache"), ws4)
    disp4 = build_dispatcher_for_workspace(ws4, HostPath(venv_py), ttl_sec=1.50, persistent_session=sess4).dispatcher
    try:
        disp4.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="init"))
        old_boot_id = wait_for_daemon_online(ws4)["boot_id"]
        check(disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.STRICT_HOT)).ok)
        _verify_rc04_streams_and_cancels(ws4, disp4)

        time.sleep(0.32)
        bg_ext = disp4.invoke(InvokeRequest(task_id=TaskId("space.echo_tier0"), raw_input={"tag": "bg"}, workspace_root=ws4, caller_cwd=ws4, priority=ExecutionPriority.BACKGROUND))
        check(bg_ext.ok)
        _ = query_daemon_control(ws4.join(".cache"), ws4, FrameKind.CONTROL_STATUS)
        wait_until(lambda: probe_daemon_endpoint(ws4.join(".cache"), ws4) is None, timeout_sec=4.0)

        strict_fail = disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.STRICT_HOT))
        check(not strict_fail.ok and strict_fail.error is not None and strict_fail.error.code == ErrorCode.DAEMON_UNAVAILABLE)
        daemon_cold = disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.FORCE_COLD))
        check(not daemon_cold.ok and daemon_cold.error is not None and daemon_cold.error.code == ErrorCode.COLD_DISPATCH_FORBIDDEN)

        _verify_rc04_hot_reconnect_and_draining(ws4, venv_py, disp4, str(old_boot_id))
    finally:
        sess4.close()
        stop_daemon_cleanly(ws4)
        disp4.shutdown()
    log("  -> PASS: RC-04 verified.")


def _verify_rc04_streams_and_cancels(ws4: HostPath, disp4: RuntimeDispatcher) -> None:
    finish_order: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fs = pool.submit(lambda: (disp4.invoke_typed(KDB_SEARCH_META, SearchInDto(query="slow", sleep_ms=220)), finish_order.append("slow"))[0])
        time.sleep(0.03)
        ff = pool.submit(
            lambda: (
                disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.STRICT_HOT)),
                finish_order.append("fast"),
            )[0]
        )
        check(ff.result(timeout=5).ok and fs.result(timeout=5).ok)
    check(finish_order == ["fast", "slow"])

    p2_cancel = CancellationToken()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fh = pool.submit(disp4.invoke, InvokeRequest(task_id=TaskId("space.hold_lock_ms"), raw_input={"hold_ms": 260}, workspace_root=ws4, caller_cwd=ws4))
        time.sleep(0.04)
        with scoped_timer(0.04, p2_cancel.cancel):
            p2_out = disp4.invoke(InvokeRequest(task_id=TaskId("space.hold_lock_ms"), raw_input={"hold_ms": 80}, workspace_root=ws4, caller_cwd=ws4), cancel_token=p2_cancel)
        check(fh.result(timeout=5).ok)
    check(not p2_out.ok and p2_out.error is not None and p2_out.error.code == ErrorCode.TASK_CANCELLED)

    p3_cancel = CancellationToken()
    with scoped_timer(0.05, p3_cancel.cancel):
        p3_out = disp4.invoke_typed(KDB_SEARCH_META, SearchInDto(query="cancel_me", sleep_ms=600), cancel_token=p3_cancel)
    check(not p3_out.ok and p3_out.error is not None and p3_out.error.code == ErrorCode.TASK_CANCELLED)


def _verify_rc04_hot_reconnect_and_draining(
    ws4: HostPath,
    venv_py: Path,
    disp4: RuntimeDispatcher,
    old_boot_id: str,
) -> None:
    run_cli_subproc(ws4, venv_py, str(ws4), "space.echo_tier0", {"tag": "boot2"}, ClientRoutingPolicy.AUTO_SPAWN)
    st_b2 = wait_for_daemon_online(ws4)
    check(st_b2["boot_id"] != old_boot_id)
    hot_b2 = disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.STRICT_HOT))
    check(hot_b2.ok and hot_b2.executed_hot)
    query_daemon_control(ws4.join(".cache"), ws4, FrameKind.CONTROL_RELOAD, {"modules": ["core"]})
    deadline = time.monotonic() + (12.0 if os.name == "nt" else 6.0)
    while time.monotonic() < deadline:
        st_cand = query_daemon_control(ws4.join(".cache"), ws4, FrameKind.CONTROL_STATUS)
        if st_cand and st_cand.get("ok") and isinstance(st_cand.get("status"), Mapping) and st_cand["status"].get("boot_id") != st_b2["boot_id"]:
            break
        time.sleep(0.05)
    hot_b3 = disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.STRICT_HOT))
    check(hot_b3.ok and hot_b3.executed_hot)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        inflight_f = pool.submit(disp4.invoke, InvokeRequest(task_id=TaskId("space.hold_lock_ms"), raw_input={"hold_ms": 800}, workspace_root=ws4, caller_cwd=ws4))
        fg_dl = time.monotonic() + 2.0
        while time.monotonic() < fg_dl:
            st_fg = query_daemon_control(ws4.join(".cache"), ws4, FrameKind.CONTROL_STATUS)
            if (
                st_fg
                and st_fg.get("ok")
                and isinstance(st_fg.get("status"), Mapping)
                and jint(st_fg["status"], "active_foreground_calls") >= 1
            ):
                break
            time.sleep(0.01)
        stop_f = pool.submit(query_daemon_control, ws4.join(".cache"), ws4, FrameKind.CONTROL_STOP, {"force": False})
        drain_dl = time.monotonic() + 3.0
        while time.monotonic() < drain_dl and probe_daemon_endpoint(ws4.join(".cache"), ws4) is not None:
            time.sleep(0.01)
        drain_strict = disp4.invoke(InvokeRequest(task_id=TaskId("space.daemon_metrics"), raw_input={}, workspace_root=ws4, caller_cwd=ws4, routing_policy=ClientRoutingPolicy.STRICT_HOT))
        drain_hybrid = disp4.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="during_drain"), routing_policy=ClientRoutingPolicy.AUTO_NO_SPAWN)
        check(
            not drain_strict.ok and drain_strict.error is not None and drain_strict.error.code == ErrorCode.DAEMON_UNAVAILABLE,
            lambda: f"Expected STRICT_HOT during DRAINING to fail with DAEMON_UNAVAILABLE, got {drain_strict}",
        )
        check(
            drain_hybrid.ok and drain_hybrid.executed_hot is False,
            lambda: f"Expected HYBRID during DRAINING to fall back cold, got {drain_hybrid}",
        )
        check(inflight_f.result(timeout=5).ok)
        stop_rep = stop_f.result(timeout=5)
        check(isinstance(stop_rep, Mapping) and stop_rep.get("ok") is True)


def _verify_real_pty_tty_auth(ws5: HostPath, venv_py: Path) -> None:
    if os.name == "nt":
        return

    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        [
            sys.executable, "-B", "-W", "error::ResourceWarning", str(live_host_boot_script_path()),
            "--cli-oneshot", str(ws5), str(venv_py), str(ws5),
            "gdrive.auth", json.dumps({"code": ""}), ClientRoutingPolicy.AUTO_SPAWN.value,
        ],
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True,
    )
    os.close(slave_fd)
    try:
        buf = b""
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and b"OAUTH_PROMPT>" not in buf:
            chunk = os.read(master_fd, 256)
            if not chunk:
                break
            buf += chunk
        check(b"OAUTH_PROMPT>" in buf, lambda: f"Tier 1 interactive PTY prompt missing: {buf!r}")
        os.write(master_fd, b"PTY_SECRET_999\n")
        check(proc.wait(timeout=10.0) == 0)
    finally:
        os.close(master_fd)
        reap_popen_quietly(proc)
    tok = read_json_dict(ws5.join(".cache", "oauth_token.json"))
    check(tok is not None and tok.get("token") == "tok_PTY_SECRET_999" and tok.get("tty") is True)


def verify_rc05_tty_periodic_and_worker_crashes(tmp_root: Path, venv_py: Path) -> None:
    """Verify PTY TTY auth, periodic non-overlap & TTL drain safety, env allowlist, and worker crashes."""
    log("[RC-05] Testing real PTY Tier 1 auth, periodic fixed-delay/TTL/drain safety, env allowlist & P0/P3 crashes...")
    ws5_path = tmp_root / "ws_rc05"
    provision_live_workspace(ws5_path)
    ws5 = HostPath(ws5_path)
    _verify_real_pty_tty_auth(ws5, venv_py)
    check(probe_daemon_endpoint(ws5.join(".cache"), ws5) is None)

    disp5 = build_dispatcher_for_workspace(ws5, HostPath(venv_py), ttl_sec=2.4).dispatcher
    try:
        auth_bad = disp5.invoke(InvokeRequest(task_id=TaskId("gdrive.auth"), raw_input={"code": "x"}, workspace_root=ws5, caller_cwd=ws5, propagation=CallPropagationContext(is_nested_call=True)))
        check(not auth_bad.ok and auth_bad.error is not None and auth_bad.error.code == ErrorCode.TTY_REQUIRED)

        disp5.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot"))
        wait_for_daemon_online(ws5)
        atomic_write_json(ws5.join("config", "gdrive.json"), {"auto_sync": True, "interval_sec": 0.06, "work_ms": 140})
        deadline = time.monotonic() + 5.5
        while time.monotonic() < deadline and jint(read_json_dict(ws5.join(".cache", "gdrive_periodic.json")), "ticks") < 2:
            time.sleep(0.04)
        check(jint(read_json_dict(ws5.join(".cache", "gdrive_periodic.json")), "ticks") >= 2)
        put_co = disp5.invoke(
            InvokeRequest(
                task_id=TaskId("gdrive.put"),
                raw_input={"local_rel": "./sample.py"},
                workspace_root=ws5,
                caller_cwd=HostPath(ws5_path / "sub_dir"),
                caller_env={"HTTPS_PROXY": "http://corp-proxy:3128", "AWS_SECRET_ACCESS_KEY": "TOP_SECRET"},
            ),
            output_type=GdriveOutDto,
        )
        kdb_w = disp5.invoke_typed(KDB_SEARCH_META, SearchInDto(query="pid_check"))
        check(put_co.ok and put_co.value is not None and kdb_w.ok and kdb_w.value is not None)
        check(put_co.value.worker_pid != kdb_w.value.worker_pid)
        ded_hp = resolve_dedicated_venv_py(HostPath(venv_py))
        check(Path(put_co.value.venv_prefix).resolve() == ded_hp.path.parent.parent.resolve())
        check(put_co.value.proxy_seen == "http://corp-proxy:3128" and put_co.value.leaked_secret_seen == "")

        deadline_ttl = time.monotonic() + (8.0 if os.name == "nt" else 5.0)
        while time.monotonic() < deadline_ttl and (
            probe_daemon_endpoint(ws5.join(".cache"), ws5) is not None
            or read_daemon_endpoint_file(ws5.join(".cache"), ws5) is not None
        ):
            time.sleep(0.05)
        check(probe_daemon_endpoint(ws5.join(".cache"), ws5) is None)
        per_final = read_json_dict(ws5.join(".cache", "gdrive_periodic.json")) or {}
        check(per_final.get("max_conc") == 1 and per_final.get("phase") == "completed")

        _verify_rc05_worker_p0_p3_and_timeout(tmp_root, venv_py)
    finally:
        stop_daemon_cleanly(ws5)
        disp5.shutdown()
    log("  -> PASS: RC-05 verified.")


def _verify_rc05_worker_p0_p3_and_timeout(tmp_root: Path, venv_py: Path) -> None:
    ws5b_path = tmp_root / "ws_rc05_crash"
    provision_live_workspace(ws5b_path)
    ws5b = HostPath(ws5b_path)
    disp5b = build_dispatcher_for_workspace(ws5b, HostPath(venv_py), ttl_sec=15.0).dispatcher
    try:
        disp5b.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot"))
        wait_for_daemon_online(ws5b)
        put_init = disp5b.invoke(
            InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py"}, workspace_root=ws5b, caller_cwd=HostPath(ws5b_path / "sub_dir")),
            output_type=GdriveOutDto,
        )
        check(put_init.ok and put_init.executed_hot and put_init.value is not None)
        warm_pid = put_init.value.worker_pid

        att0 = jint(read_json_dict(ws5b.join(".cache", "gdrive_put_runs.json")), "attempts")
        os.kill(warm_pid, signal.SIGTERM if sys.platform == "win32" else signal.SIGKILL)
        while is_process_alive(warm_pid):
            time.sleep(0.02)
        put_p0 = disp5b.invoke(
            InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py"}, workspace_root=ws5b, caller_cwd=HostPath(ws5b_path / "sub_dir")),
            output_type=GdriveOutDto,
        )
        check(put_p0.ok and put_p0.value is not None and put_p0.value.worker_pid != warm_pid)
        check(jint(read_json_dict(ws5b.join(".cache", "gdrive_put_runs.json")), "attempts") == att0 + 1)

        att1 = jint(read_json_dict(ws5b.join(".cache", "gdrive_put_runs.json")), "attempts")
        put_p3 = disp5b.invoke(InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py", "crash_after_accept": True}, workspace_root=ws5b, caller_cwd=HostPath(ws5b_path / "sub_dir")))
        check(not put_p3.ok and put_p3.error is not None and put_p3.error.code == ErrorCode.TRANSPORT_LOST)
        check(jint(read_json_dict(ws5b.join(".cache", "gdrive_put_runs.json")), "attempts") == att1 + 1)

        put_pre_to = disp5b.invoke(
            InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py"}, workspace_root=ws5b, caller_cwd=HostPath(ws5b_path / "sub_dir")),
            output_type=GdriveOutDto,
        )
        check(put_pre_to.ok and put_pre_to.value is not None)
        hung_pid = put_pre_to.value.worker_pid
        put_to = disp5b.invoke(InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py", "hang_ms": 1500}, workspace_root=ws5b, caller_cwd=HostPath(ws5b_path / "sub_dir")))
        check(not put_to.ok and put_to.error is not None and put_to.error.code == ErrorCode.TASK_TIMEOUT)
        check(not is_process_alive(hung_pid))
        check(disp5b.invoke(InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py"}, workspace_root=ws5b, caller_cwd=HostPath(ws5b_path / "sub_dir"))).ok)
    finally:
        stop_daemon_cleanly(ws5b)
        disp5b.shutdown()


def verify_rc06_quiesce_hot_reload_and_core_mutation(tmp_root: Path, venv_py: Path) -> None:
    """Verify global QUIESCED reload guard, FIFO event ordering, emit_imm order, live reload, and core handoff."""
    log("[RC-06] Testing QUIESCED reload guard, ORDERED_FIFO, emit_imm inline order, .modules reload & MUTATES_CORE...")
    ws6_path = tmp_root / "ws_rc06"
    provision_live_workspace(ws6_path)
    ws6 = HostPath(ws6_path)
    disp6 = build_dispatcher_for_workspace(ws6, HostPath(venv_py), ttl_sec=15.0).dispatcher
    try:
        disp6.invoke_typed(AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py"), caller_cwd=HostPath(ws6_path / "sub_dir"))
        st6_before = wait_for_daemon_online(ws6)
        _verify_rc06_quiesce_and_ordered_events(ws6, ws6_path, venv_py, disp6)
        st6_after = _verify_rc06_live_reload_and_core_handoff(ws6, ws6_path, disp6, st6_before)
        _verify_rc06_empty_quiesce_fast_core_handoff(ws6, ws6_path, disp6, st6_after)
    finally:
        stop_daemon_cleanly(ws6)
        disp6.shutdown()
    log("  -> PASS: RC-06 verified.")


def _verify_rc06_quiesce_and_ordered_events(
    ws6: HostPath,
    ws6_path: Path,
    venv_py: Path,
    disp6: RuntimeDispatcher,
) -> None:
    q_ack = query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_QUIESCE, {"lease_sec": 5.0})
    check(q_ack and q_ack.get("state") == "quiesced")

    rel_during_q = query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_RELOAD, {"modules": ["kdb"]})
    check(rel_during_q and rel_during_q.get("deferred") is True)
    st_q = query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_STATUS)
    check(st_q and isinstance(st_q.get("status"), Mapping) and jlist(st_q["status"], "active_tier1_workers") == [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        queued_fut = pool.submit(disp6.invoke_typed, AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py"), caller_cwd=HostPath(ws6_path / "sub_dir"))
        time.sleep(0.10)
        check(not queued_fut.done())
        cold_fut = pool.submit(
            lambda: (time.sleep(0.04), run_cli_subproc(ws6, venv_py, str(ws6), "space.echo_tier0", {"tag": "record_cold_enter"}, ClientRoutingPolicy.FORCE_COLD))[1]
        )
        mut_out = disp6.invoke(
            InvokeRequest(
                task_id=TaskId("space.remove_and_install"),
                raw_input={"target_module": "vsc", "hold_ms": 200},
                workspace_root=ws6, caller_cwd=ws6,
                approval_scope=frozenset({TaskId("space.remove_and_install")}),
            )
        )
        check(mut_out.ok and cold_fut.result(timeout=10)["ok"] is True)

        sp_entry = ws6_path / ".modules" / "space" / "module_entry.py"
        atomic_write_bytes(HostPath(sp_entry), sp_entry.read_text(encoding="utf-8").replace('MODULE_VER = "v1"', 'MODULE_VER = "v2"').encode("utf-8"))
        check(query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_RESUME, {}) is not None)
        check(queued_fut.result(timeout=(10.0 if os.name == "nt" else 5.0)).executed_hot is True)
        vsc_starts_after_resume = jint(read_json_dict(ws6.join(".cache", "vsc_tier0_warm.json")), "starts", 0)
        time.sleep(0.35)
        check(jint(read_json_dict(ws6.join(".cache", "vsc_tier0_warm.json")), "starts", 0) == vsc_starts_after_resume)

    inst_exit = jfloat(read_json_dict(ws6.join(".cache", "installer_exit_ts.json")), "exit")
    cold_enter = jfloat(read_json_dict(ws6.join(".cache", "cold_reader_ts.json")), "enter")
    check(inst_exit > 0 and cold_enter >= inst_exit - 0.002, lambda: f"Cold reader entered before installer released lock: {inst_exit} vs {cold_enter}")
    imm_proof = read_json_dict(ws6.join(".cache", "imm_inline_proof.json")) or {}
    check(imm_proof.get("imm_seen_inline") == [1, 2] and imm_proof.get("deferred_flushed_early") is False)
    fifo_log = read_json_dict(ws6.join(".cache", "deferred_fifo.json")) or {}
    check(fifo_log.get("seqs") == [1, 2, 3] and fifo_log.get("batch_sizes") == [1, 1, 1])
    check(jint(read_json_dict(ws6.join(".cache", "diamond_merged.json")), "runs") == 1)
    strict_imm = disp6.invoke(InvokeRequest(task_id=TaskId("space.remove_and_install"), raw_input={"target_module": "fail_strict", "strict_imm_fail": True}, workspace_root=ws6, caller_cwd=ws6, approval_scope=frozenset({TaskId("space.remove_and_install")})))
    check(not strict_imm.ok)


def _verify_rc06_live_reload_and_core_handoff(
    ws6: HostPath,
    ws6_path: Path,
    disp6: RuntimeDispatcher,
    st6_before: JsonObject,
) -> JsonObject:
    v2_echo = disp6.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="hot"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    check(v2_echo.ok and v2_echo.value is not None and v2_echo.value.ok_msg == "tier0:v2:SPACE_H:hot")

    ast_entry = ws6_path / ".modules" / "ast" / "module_entry.py"
    ast_entry.write_text(ast_entry.read_text(encoding="utf-8").replace('AST_MOD_VER = "ast_v1"', 'AST_MOD_VER = "ast_v2"'), encoding="utf-8")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as rel_pool:
        sib_fut = rel_pool.submit(disp6.invoke_typed, KDB_SEARCH_META, SearchInDto(query="survive_reload", sleep_ms=260), routing_policy=ClientRoutingPolicy.STRICT_HOT)
        time.sleep(0.04)
        check(query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_RELOAD, {"modules": ["ast"]}) is not None)
        check(sib_fut.result(timeout=5.0).ok)
    deadline_rel = time.monotonic() + 4.0
    saw_v2 = False
    while time.monotonic() < deadline_rel:
        p_ast = disp6.invoke_typed(AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py"), caller_cwd=HostPath(ws6_path / "sub_dir"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
        if p_ast.ok and p_ast.value is not None and p_ast.value.module_ver == "ast_v2":
            saw_v2 = True
            break
        time.sleep(0.08)
    check(saw_v2)
    kdb_after_ast_reload = disp6.invoke_typed(KDB_SEARCH_META, SearchInDto(query="still_warm"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    check(kdb_after_ast_reload.ok and kdb_after_ast_reload.value is not None and kdb_after_ast_reload.value.warm_model_ready is True)

    query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_QUIESCE, {"lease_sec": 0.22})
    time.sleep(0.38)
    check(wait_for_daemon_online(ws6)["state"] == "ready")

    atomic_write_json(ws6.join("config", "gdrive.json"), {"auto_sync": False, "interval_sec": 0.25, "work_ms": 0})
    deadline_cfg = time.monotonic() + (6.0 if os.name == "nt" else 3.0)
    while time.monotonic() < deadline_cfg and not ws6.join(".cache", "config_reloaded_marker.json").path.exists():
        time.sleep(0.04)
    check(ws6.join(".cache", "config_reloaded_marker.json").path.is_file())

    bad_mod_hot = disp6.invoke(InvokeRequest(task_id=TaskId("space.bad_hot_mutate"), raw_input={}, workspace_root=ws6, caller_cwd=ws6, approval_scope=frozenset({TaskId("space.remove_and_install")})), output_type=SimpleOutDto)
    check(bad_mod_hot.ok and bad_mod_hot.value is not None and bad_mod_hot.value.ok_msg == ErrorCode.HOT_MUTATION_FORBIDDEN.value)
    bad_core_hot = disp6.invoke(InvokeRequest(task_id=TaskId("space.bad_hot_core_mutate"), raw_input={}, workspace_root=ws6, caller_cwd=ws6, approval_scope=frozenset({TaskId("space.upgrade_core")})), output_type=SimpleOutDto)
    check(bad_core_hot.ok and bad_core_hot.value is not None and bad_core_hot.value.ok_msg == ErrorCode.HOT_MUTATION_FORBIDDEN.value)
    cold_strict_err = disp6.invoke(InvokeRequest(task_id=TaskId("dev.run_sandbox"), raw_input={"child_workspace": str(ws6)}, workspace_root=ws6, caller_cwd=ws6, routing_policy=ClientRoutingPolicy.STRICT_HOT))
    check(not cold_strict_err.ok and cold_strict_err.error is not None and cold_strict_err.error.code == ErrorCode.COLD_DISPATCH_FORBIDDEN)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        draining_fg = pool.submit(disp6.invoke, InvokeRequest(task_id=TaskId("space.hold_lock_ms"), raw_input={"hold_ms": 180}, workspace_root=ws6, caller_cwd=ws6))
        time.sleep(0.04)
        upg_out = disp6.invoke(InvokeRequest(task_id=TaskId("space.upgrade_core"), raw_input={"version_tag": "2.1.0"}, workspace_root=ws6, caller_cwd=ws6, approval_scope=frozenset({TaskId("space.upgrade_core")})), output_type=SimpleOutDto)
        check(upg_out.ok and upg_out.value is not None and "handoff=True" in upg_out.value.ok_msg)
        check(draining_fg.result(timeout=5.0).ok)
    check(read_json_dict(ws6.join(".cache", "core_upgraded.json")) == {"version": "2.1.0"})

    deadline = time.monotonic() + (12.0 if os.name == "nt" else 6.0)
    st6_after: Optional[JsonObject] = None
    while time.monotonic() < deadline:
        cand = query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_STATUS)
        if cand and cand.get("ok") and isinstance(cand.get("status"), Mapping) and cand["status"].get("boot_id") != st6_before["boot_id"]:
            st6_after = cand["status"]
            break
        time.sleep(0.06)
    check(st6_after is not None and st6_after["pid"] != st6_before["pid"])
    return st6_after or {}


def _verify_rc06_empty_quiesce_fast_core_handoff(
    ws6: HostPath,
    ws6_path: Path,
    disp6: RuntimeDispatcher,
    st_prev: JsonObject,
) -> None:
    check(bool(st_prev.get("boot_id")))
    core_mod_dir = ws6_path / ".modules" / "core"
    core_mod_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(HostPath(core_mod_dir / "fast_patch.py"), b"PATCH_REV = 1\n")
    hot_imm = disp6.invoke_typed(AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py", call_tier0=True), caller_cwd=HostPath(ws6_path / "sub_dir"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    check(hot_imm.ok and (ws6_path / ".cache" / "tier1_imm_seen.json").is_file())
    hot_imm_err = disp6.invoke_typed(AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py", call_tier0=True, fail_imm_strict=True), caller_cwd=HostPath(ws6_path / "sub_dir"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    check(not hot_imm_err.ok)
    stop_daemon_cleanly(ws6)
    disp6.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="re_boot_same_size"))
    st_reboot = wait_for_daemon_online(ws6)
    q_ack = query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_QUIESCE, {})
    check(q_ack is not None and q_ack.get("ok") is True)
    atomic_write_bytes(HostPath(core_mod_dir / "fast_patch.py"), b"PATCH_REV = 2\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as h_pool:
        queued_strict = h_pool.submit(
            disp6.invoke,
            InvokeRequest(
                task_id=TaskId("space.daemon_metrics"),
                raw_input={},
                workspace_root=ws6,
                caller_cwd=ws6,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
            ),
            output_type=SimpleOutDto,
        )
        time.sleep(0.05)
        r_ack = query_daemon_control(ws6.join(".cache"), ws6, FrameKind.CONTROL_RESUME, {})
        check(r_ack is not None and r_ack.get("handoff") is True)
        q_res = queued_strict.result(timeout=10.0)
    check(q_res.ok and q_res.executed_hot is True)
    st_post = wait_for_daemon_online(ws6)
    check(st_post["boot_id"] != st_reboot["boot_id"])


def _verify_rc07_real_sigint_tree_and_lifo(ws7_host: Path, venv_py: Path) -> None:
    (ws7_host / ".cache").mkdir(parents=True, exist_ok=True)
    (ws7_host / ".cache" / "inject_teardown_error.flag").write_text("1", encoding="utf-8")
    gp_path = HostPath(ws7_host / ".cache" / "grandchild_pid.json")
    popen_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    popen_si: Optional[subprocess.STARTUPINFO] = None
    if sys.platform == "win32":
        popen_si = subprocess.STARTUPINFO()
        popen_si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        popen_si.wShowWindow = subprocess.SW_HIDE
    cli_proc = subprocess.Popen(
        [
            sys.executable, "-B", "-W", "error::ResourceWarning", str(live_host_boot_script_path()),
            "--cli-oneshot", str(ws7_host), str(venv_py), str(ws7_host),
            "dev.run_sandbox", json.dumps({"child_workspace": str(ws7_host), "spawn_sleep_child": True}),
            ClientRoutingPolicy.FORCE_COLD.value,
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=popen_flags,
        startupinfo=popen_si,
    )
    try:
        deadline = time.monotonic() + (12.0 if os.name == "nt" else 6.0)
        while time.monotonic() < deadline and read_json_dict(gp_path) is None:
            time.sleep(0.03)
        gp_info = read_json_dict(gp_path)
        check(gp_info is not None)
        sig_int = signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGINT
        cli_proc.send_signal(sig_int)
        out_str, _err_str = cli_proc.communicate(timeout=10.0)
    finally:
        reap_popen_quietly(cli_proc)
    check(cli_proc.returncode == 130)
    parsed = json.loads(out_str.strip())
    check(parsed["ok"] is False and parsed["error"] == ErrorCode.TASK_CANCELLED.value and parsed["teardown_count"] == 1)
    lifo_ord = read_json_dict(HostPath(ws7_host / ".cache" / "lifo_teardown_order.json")) or {}
    check(lifo_ord.get("order") == ["space_threw_first_in_lifo", "dev_closed_after_space_threw"])
    time.sleep(0.08)
    check(not is_process_alive(jint(gp_info, "child_pid")) and not is_process_alive(jint(gp_info, "grandchild_pid")))
    probe_l = FileLock(HostPath(ws7_host / ".cache" / "locks" / "installer.lock"))
    check(probe_l.acquire(shared=False, blocking=False))
    probe_l.release()
    (ws7_host / ".cache" / "inject_teardown_error.flag").unlink(missing_ok=True)


def verify_rc07_child_sandbox_and_lifo_teardown(tmp_root: Path, venv_py: Path) -> None:
    """Verify multi-child sandbox delegation, cross-workspace RPC cycle, SIGINT handling, and LIFO teardown."""
    log("[RC-07] Testing multi-child sandbox, cross-ws RPC cycle, real SIGINT (130) & 2-item LIFO order...")
    ws7_host = tmp_root / "ws_rc07_host"
    ws7_child_a = tmp_root / "ws_rc07_child_a"
    ws7_child_b = tmp_root / "ws_rc07_child_b"
    for w in (ws7_host, ws7_child_a, ws7_child_b):
        provision_live_workspace(w)

    rig = build_dispatcher_for_workspace(HostPath(ws7_host), HostPath(venv_py), sandbox_restricted=True)
    disp7_cold, cfg7 = rig.dispatcher, rig.config_view
    try:
        atomic_write_json(HostPath(ws7_host / "yscb.config.json"), {"workspace_version": 3})
        sb_chain = disp7_cold.invoke(
            InvokeRequest(
                task_id=TaskId("dev.run_sandbox"),
                raw_input={"child_workspace": str(ws7_child_a), "spawn_sleep_child": False, "sync_host_install": True},
                workspace_root=HostPath(ws7_host), caller_cwd=HostPath(ws7_host),
                approval_scope=frozenset({TaskId("space.remove_and_install")}),
            ),
            output_type=SandboxOutDto,
        )
        check(sb_chain.ok and sb_chain.value is not None and sb_chain.value.child_ok is True)
        check(cfg7.get_module_value(ModuleId("root"), "workspace_version") == 3)
        check(not (ws7_child_a / ".cache" / "daemon" / "daemon.json").exists())
        (ws7_host / ".cache" / "ast_lazy_inited.json").unlink(missing_ok=True)
        (ws7_host / ".cache" / "ast_lazy_closed.json").unlink(missing_ok=True)
        os_cancel = CancellationToken()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as c_pool:
            os_fut = c_pool.submit(
                disp7_cold.invoke_typed,
                AST_OUTLINE_META,
                OutlineInDto(rel_file="./sample.py", coop_sleep_ms=500),
                caller_cwd=HostPath(ws7_host / "sub_dir"),
                cancel_token=os_cancel,
            )
            dl_init = time.monotonic() + 4.0
            while time.monotonic() < dl_init and not (ws7_host / ".cache" / "ast_lazy_inited.json").is_file():
                time.sleep(0.02)
            check((ws7_host / ".cache" / "ast_lazy_inited.json").is_file())
            os_cancel.cancel()
            os_res = os_fut.result(timeout=5.0)
        check(not os_res.ok and os_res.error is not None and os_res.error.code == ErrorCode.TASK_CANCELLED)
        check((ws7_host / ".cache" / "ast_lazy_closed.json").is_file())
    finally:
        disp7_cold.shutdown()

    _verify_rc07_real_sigint_tree_and_lifo(ws7_host, venv_py)
    _verify_rc07_hot_multi_child_and_cross_ws_cycle(ws7_host, ws7_child_a, ws7_child_b, venv_py)
    log("  -> PASS: RC-07 verified.")


def _verify_rc07_hot_multi_child_and_cross_ws_cycle(
    ws7_host: Path,
    ws7_child_a: Path,
    ws7_child_b: Path,
    venv_py: Path,
) -> None:
    disp7_hot = build_dispatcher_for_workspace(HostPath(ws7_host), HostPath(venv_py), ttl_sec=10.0).dispatcher
    disp7_peer = build_dispatcher_for_workspace(HostPath(ws7_child_b), HostPath(venv_py), ttl_sec=10.0).dispatcher
    try:
        disp7_hot.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot_h"))
        wait_for_daemon_online(HostPath(ws7_host))
        hot_multi = disp7_hot.invoke(
            InvokeRequest(
                task_id=TaskId("space.orchestrate_child_ws"),
                raw_input={"child_ws": str(ws7_child_a), "second_child_ws": str(ws7_child_b)},
                workspace_root=HostPath(ws7_host), caller_cwd=HostPath(ws7_host), routing_policy=ClientRoutingPolicy.STRICT_HOT,
            ),
            output_type=SimpleOutDto,
        )
        check(hot_multi.ok and hot_multi.executed_hot and hot_multi.value is not None and hot_multi.value.ok_msg == "child_ok")
        check(not (ws7_child_b / ".cache" / "daemon" / "daemon.json").exists())

        disp7_peer.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot_p"))
        peer_st_before = wait_for_daemon_online(HostPath(ws7_child_b))
        cyc_cross = disp7_hot.invoke(
            InvokeRequest(
                task_id=TaskId("space.orchestrate_child_ws"),
                raw_input={"child_ws": str(ws7_child_b), "bounce_back_ws": str(ws7_host)},
                workspace_root=HostPath(ws7_host), caller_cwd=HostPath(ws7_host),
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
            )
        )
        peer_st_after = wait_for_daemon_online(HostPath(ws7_child_b))
        check(not cyc_cross.ok and cyc_cross.executed_hot is True)
        check(cyc_cross.error is not None and cyc_cross.error.code == ErrorCode.CALL_CYCLE_DETECTED)
        check(jint(peer_st_after, "tasks_handled") > jint(peer_st_before, "tasks_handled"))
        check(query_daemon_control(HostPath(ws7_child_b).join(".cache"), HostPath(ws7_child_b), FrameKind.CONTROL_STOP, {"force": True}) is not None)
    finally:
        stop_daemon_cleanly(HostPath(ws7_child_b))
        stop_daemon_cleanly(HostPath(ws7_host))
        disp7_peer.shutdown()
        disp7_hot.shutdown()


def verify_rc08_cross_proc_locks_and_guards(tmp_root: Path, venv_py: Path) -> None:
    """Verify cross-process file locks, security/topology gates, frame limits, poisoned pools, and daemon hygiene."""
    log("[RC-08] Testing cold-first & hot-first FileLock, security/exposure/frame/cycle gates & hot-daemon guards...")
    ws8_path = tmp_root / "ws_rc08"
    provision_live_workspace(ws8_path)
    ws8 = HostPath(ws8_path)
    disp8 = build_dispatcher_for_workspace(ws8, HostPath(venv_py), ttl_sec=90.0).dispatcher
    try:
        disp8.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot"))
        wait_for_daemon_online(ws8)
        _verify_rc08_both_lock_orders(ws8, venv_py, disp8)
        _verify_rc08_security_and_topology_gates(ws8, venv_py, disp8)
        _verify_rc08_frame_and_kernel_unit_regressions(ws8, disp8)
        _verify_fd_and_poisoned_pool_regressions(ws8, disp8)
        _verify_cold_isolation_and_queued_coalesce(ws8, disp8)
        _verify_retiring_reentrant_and_shutdown_edges(ws8, disp8)
        _verify_codec_partial_and_endpoint_probe(ws8, disp8)
        _verify_retiring_lock_yield_and_empty_reload(ws8, disp8)
        _verify_codec_nan_union_key_and_lease_bounds(ws8, disp8)
        _verify_daemon_hygiene_and_local_union(ws8)
    finally:
        stop_daemon_cleanly(ws8)
        disp8.shutdown()
    log("  -> PASS: RC-08 cross-process locks & security gates verified.")


def _verify_rc08_both_lock_orders(ws8: HostPath, venv_py: Path, disp8: RuntimeDispatcher) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fc = pool.submit(run_cli_subproc, ws8, venv_py, str(ws8), "dev.hold_shared_lock", {"hold_ms": 180, "actor": "cold_1"}, ClientRoutingPolicy.FORCE_COLD)
        time.sleep(0.05)
        fh = pool.submit(disp8.invoke, InvokeRequest(task_id=TaskId("dev.hold_shared_lock"), raw_input={"hold_ms": 80, "actor": "hot_1"}, workspace_root=ws8, caller_cwd=ws8))
        check(fc.result(timeout=10)["executed_hot"] is False and fh.result(timeout=10).ok)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fh2 = pool.submit(disp8.invoke, InvokeRequest(task_id=TaskId("dev.hold_shared_lock"), raw_input={"hold_ms": 180, "actor": "hot_2"}, workspace_root=ws8, caller_cwd=ws8))
        time.sleep(0.04)
        fc2 = pool.submit(run_cli_subproc, ws8, venv_py, str(ws8), "dev.hold_shared_lock", {"hold_ms": 80, "actor": "cold_2"}, ClientRoutingPolicy.FORCE_COLD)
        check(fh2.result(timeout=10).ok and fc2.result(timeout=10)["executed_hot"] is False)

    spans_raw = jlist(read_json_dict(ws8.join(".cache", "cross_lock_timeline.json")), "spans")
    check(len(spans_raw) == 4)
    spans = sorted((s for s in spans_raw if isinstance(s, Mapping)), key=lambda s: jfloat(s, "enter"))
    for idx in range(len(spans) - 1):
        check(jfloat(spans[idx], "exit") <= jfloat(spans[idx + 1], "enter") + 0.005)


def _verify_rc08_security_and_topology_gates(ws8: HostPath, venv_py: Path, disp8: RuntimeDispatcher) -> None:
    cli_sdk_only = run_cli_subproc(ws8, venv_py, str(ws8), "space.daemon_metrics", {}, ClientRoutingPolicy.STRICT_HOT)
    check(cli_sdk_only["ok"] is False and cli_sdk_only["error"] == ErrorCode.EXPOSURE_DENIED.value)

    cond_deny = disp8.invoke(InvokeRequest(task_id=TaskId("gdrive.put"), raw_input={"local_rel": "./sample.py"}, workspace_root=ws8, caller_cwd=ws8, allow_conditional=False))
    check(not cond_deny.ok and cond_deny.error is not None and cond_deny.error.code == ErrorCode.SECURITY_GATED)
    gated_ok = disp8.invoke(InvokeRequest(task_id=TaskId("vsc.gated_clean"), raw_input={}, workspace_root=ws8, caller_cwd=ws8, approval_scope=frozenset({TaskId("vsc.gated_clean")})))
    check(gated_ok.ok and gated_ok.executed_hot is True)
    esc = disp8.invoke(InvokeRequest(task_id=TaskId("space.bad_escalate"), raw_input={}, workspace_root=ws8, caller_cwd=ws8), output_type=SimpleOutDto)
    check(esc.ok and esc.value is not None and esc.value.ok_msg == "blocked:security_gated")
    ev_gated = disp8.invoke(InvokeRequest(task_id=TaskId("space.remove_and_install"), raw_input={"target_module": "vsc"}, workspace_root=ws8, caller_cwd=ws8, approval_scope=frozenset({TaskId("space.remove_and_install")}), propagation=CallPropagationContext(in_event_chain=True)))
    check(not ev_gated.ok and ev_gated.error is not None and ev_gated.error.code == ErrorCode.SECURITY_GATED)

    self_pre = disp8.invoke(InvokeRequest(task_id=TaskId("space.bad_self_preempt"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(not self_pre.ok and self_pre.error is not None and self_pre.error.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY)
    self_coa = disp8.invoke(InvokeRequest(task_id=TaskId("space.bad_self_coalesce"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(not self_coa.ok and self_coa.error is not None and self_coa.error.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY)

    call_cyc = disp8.invoke(InvokeRequest(task_id=TaskId("space.cycle_a"), raw_input={}, workspace_root=ws8, caller_cwd=ws8), output_type=SimpleOutDto)
    check(not call_cyc.ok and call_cyc.error is not None and call_cyc.error.code == ErrorCode.CALL_CYCLE_DETECTED)
    ev_cyc = disp8.invoke(InvokeRequest(task_id=TaskId("space.ev_cycle_start"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(not ev_cyc.ok and ev_cyc.error is not None and ev_cyc.error.code == ErrorCode.EVENT_CYCLE_DETECTED)
    mix_cyc = disp8.invoke(InvokeRequest(task_id=TaskId("space.mix_cycle_emit"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(not mix_cyc.ok and mix_cyc.error is not None and mix_cyc.error.code == ErrorCode.EVENT_CYCLE_DETECTED)

    t0_to1 = disp8.invoke(InvokeRequest(task_id=TaskId("space.tier0_timeout"), raw_input={"hold_ms": 350, "ignore_cancel": False}, workspace_root=ws8, caller_cwd=ws8))
    check(disp8.invoke(InvokeRequest(task_id=TaskId("space.hold_lock_ms"), raw_input={"hold_ms": 1, "ignore_cancel": False}, workspace_root=ws8, caller_cwd=ws8)).ok)
    t_start_uncoop = time.monotonic()
    t0_to2 = disp8.invoke(InvokeRequest(task_id=TaskId("space.tier0_timeout"), raw_input={"hold_ms": 500, "ignore_cancel": True}, workspace_root=ws8, caller_cwd=ws8))
    elapsed_uncoop = time.monotonic() - t_start_uncoop
    t0_after = disp8.invoke(InvokeRequest(task_id=TaskId("space.hold_lock_ms"), raw_input={"hold_ms": 5, "ignore_cancel": False}, workspace_root=ws8, caller_cwd=ws8))
    check(not t0_to1.ok and t0_to1.error is not None and t0_to1.error.code == ErrorCode.TASK_TIMEOUT)
    check(not t0_to2.ok and t0_to2.error is not None and t0_to2.error.code == ErrorCode.TASK_TIMEOUT and elapsed_uncoop < 0.40)
    check(t0_after.ok)
    ling_exit = jfloat(read_json_dict(ws8.join(".cache", "t0_lingering_exit.json")), "exit")
    next_enter = jfloat(read_json_dict(ws8.join(".cache", "t0_guard_probe_enter.json")), "enter")
    check(
        ling_exit > 0.0 and next_enter >= ling_exit - 0.005,
        lambda: f"ling_exit={ling_exit} next_enter={next_enter} hot={(t0_to1.executed_hot, t0_to2.executed_hot, t0_after.executed_hot)}",
    )
    nf_out = disp8.invoke(InvokeRequest(task_id=TaskId("space.nonexistent_xyz"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(not nf_out.ok and nf_out.error is not None and nf_out.error.code == ErrorCode.TASK_NOT_FOUND)

    runs_b = jint(read_json_dict(ws8.join(".cache", "diamond_merged.json")), "runs")
    p_fail = disp8.invoke(InvokeRequest(task_id=TaskId("space.partial_commit_parent"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(not p_fail.ok and jint(read_json_dict(ws8.join(".cache", "diamond_merged.json")), "runs") == runs_b + 1)
    check(not ws8.join(".cache", "deferred_fifo.json").path.exists())


def _verify_rc08_frame_and_kernel_unit_regressions(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    giant_str = "x" * (65 * 1024 * 1024)
    out_big = disp8.invoke(InvokeRequest(task_id=TaskId("space.echo_tier0"), raw_input={"tag": giant_str}, workspace_root=ws8, caller_cwd=ws8))
    srv_big = disp8.invoke(InvokeRequest(task_id=TaskId("space.giant_reply"), raw_input={}, workspace_root=ws8, caller_cwd=ws8, routing_policy=ClientRoutingPolicy.STRICT_HOT))
    check(not out_big.ok and out_big.error is not None and out_big.error.code == ErrorCode.PAYLOAD_TOO_LARGE)
    check(not srv_big.ok and srv_big.error is not None and srv_big.error.code == ErrorCode.PAYLOAD_TOO_LARGE)

    ep = read_daemon_endpoint_file(ws8.join(".cache"), ws8)
    check(ep is not None)
    with socket.create_connection((ep.host, ep.port), timeout=1.0) as raw_sock:
        raw_sock.sendall(struct.pack(">I", 80 * 1024 * 1024))
        check(raw_sock.recv(16) == b"")
    check(disp8.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="tiny")).ok)

    vsc_res = disp8.invoke(InvokeRequest(task_id=TaskId("vsc.sync"), raw_input={}, workspace_root=ws8, caller_cwd=ws8))
    check(vsc_res.ok and isinstance(vsc_res.value, Mapping) and vsc_res.value.get("helper_who") == "VSC_H")

    check(ws8.join(".cache", "vsc_tier0_warm.json").path.is_file())


def _verify_fd_and_poisoned_pool_regressions(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    lock_target = ws8.join(".cache", "locks", "fd_safety_probe.lock")
    holder = FileLock(lock_target)
    check(holder.acquire(shared=False, blocking=False))
    canary_a = ws8.path / ".cache" / "canary_a.txt"
    canary_b = ws8.path / ".cache" / "canary_b.txt"
    canary_a.write_text("ok_a", encoding="utf-8")
    canary_b.write_text("ok_b", encoding="utf-8")
    with canary_a.open("r", encoding="utf-8") as fa:
        contender = FileLock(lock_target)
        check(contender.acquire(shared=False, blocking=False) is False)
        expect_yscb_code(lambda: contender.acquire(shared=False, blocking=True, timeout_sec=0.04), ErrorCode.TASK_TIMEOUT)
        with canary_b.open("r", encoding="utf-8") as fb:
            contender.release()
            check(fa.read() == "ok_a" and fb.read() == "ok_b")
    holder.release()

    warm_kdb = disp8.invoke_typed(KDB_SEARCH_META, SearchInDto(query="pre_poison"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    check(warm_kdb.ok and warm_kdb.value is not None)
    poisoned_pid = warm_kdb.value.worker_pid
    (ws8.path / ".cache" / "ast_uncoop_in.json").unlink(missing_ok=True)
    (ws8.path / ".cache" / "kdb_search_in.json").unlink(missing_ok=True)
    uncoop_cancel = CancellationToken()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_sibling = pool.submit(
            disp8.invoke_typed,
            KDB_SEARCH_META,
            SearchInDto(query="healthy_sibling", sleep_ms=900),
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
        )
        wait_file_marker(ws8.path / ".cache" / "kdb_search_in.json")
        fut_uncoop = pool.submit(
            disp8.invoke_typed,
            AST_OUTLINE_META,
            OutlineInDto(rel_file="./sample.py", uncoop_hang_ms=5000),
            caller_cwd=ws8,
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
            cancel_token=uncoop_cancel,
        )
        wait_file_marker(ws8.path / ".cache" / "ast_uncoop_in.json")
        uncoop_cancel.cancel()
        res_uncoop = fut_uncoop.result(timeout=5.0)
        res_sibling = fut_sibling.result(timeout=5.0)
    check(not res_uncoop.ok and res_uncoop.error is not None and res_uncoop.error.code == ErrorCode.TASK_CANCELLED)
    check(res_sibling.ok and res_sibling.value is not None and res_sibling.value.worker_pid == poisoned_pid)
    kill_deadline = time.monotonic() + (3.0 if os.name == "nt" else 1.2)
    while time.monotonic() < kill_deadline and is_process_alive(poisoned_pid):
        time.sleep(0.03)
    check(not is_process_alive(poisoned_pid), "Poisoned shared worker was not terminated promptly after sibling drained!")
    healed_kdb = disp8.invoke_typed(KDB_SEARCH_META, SearchInDto(query="post_poison"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    check(healed_kdb.ok and healed_kdb.value is not None)
    check(healed_kdb.value.worker_pid != poisoned_pid and healed_kdb.value.warm_model_ready is True)


def _verify_cold_isolation_and_queued_coalesce(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    fc_sb = disp8.invoke(
        InvokeRequest(
            task_id=TaskId("dev.run_sandbox"),
            raw_input={"child_workspace": str(ws8), "spawn_sleep_child": False, "sync_host_install": True},
            workspace_root=ws8,
            caller_cwd=ws8,
            routing_policy=ClientRoutingPolicy.FORCE_COLD,
            approval_scope=frozenset({TaskId("space.remove_and_install")}),
        ),
        output_type=SandboxOutDto,
    )
    check(fc_sb.ok and fc_sb.value is not None and fc_sb.value.child_ok is True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as cpool:
        fca = cpool.submit(
            disp8.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": False, "sleep_ms": 60}, workspace_root=ws8, caller_cwd=ws8, routing_policy=ClientRoutingPolicy.FORCE_COLD),
            output_type=IndexOutDto,
        )
        time.sleep(0.02)
        fcb = cpool.submit(
            disp8.invoke,
            InvokeRequest(task_id=TaskId("kdb.index"), raw_input={"force": True, "sleep_ms": 20}, workspace_root=ws8, caller_cwd=ws8, routing_policy=ClientRoutingPolicy.FORCE_COLD),
            output_type=IndexOutDto,
        )
        rca, rcb = fca.result(timeout=15.0), fcb.result(timeout=15.0)
    check(rca.ok and rcb.ok and rca.value is not None and rcb.value is not None)
    check(rcb.coalesced is False and rcb.value.kdb_gen == rca.value.kdb_gen + 10)

    disp8.emit_background_event(EventId("core.config_changed"), {"changed_paths": []})
    check(disp8.active_turn_count == 0)


def _verify_retiring_reentrant_and_shutdown_edges(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    _ = disp8.invoke_typed(
        AST_OUTLINE_META,
        OutlineInDto(rel_file="./sample.py"),
        caller_cwd=HostPath(ws8.path / "sub_dir"),
        routing_policy=ClientRoutingPolicy.STRICT_HOT,
    )
    (ws8.path / ".cache" / "ast_uncoop_in.json").unlink(missing_ok=True)
    (ws8.path / ".cache" / "kdb_search_in.json").unlink(missing_ok=True)
    cancel_poison = CancellationToken()
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f_parent = pool.submit(
            disp8.invoke_typed,
            KDB_SEARCH_META,
            SearchInDto(query="reentrant_retiring", sleep_ms=650, post_sync=True),
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
        )
        wait_file_marker(ws8.path / ".cache" / "kdb_search_in.json")
        f_poison = pool.submit(
            disp8.invoke_typed,
            AST_OUTLINE_META,
            OutlineInDto(rel_file="./sample.py", uncoop_hang_ms=5500),
            caller_cwd=HostPath(ws8.path / "sub_dir"),
            routing_policy=ClientRoutingPolicy.STRICT_HOT,
            cancel_token=cancel_poison,
        )
        wait_file_marker(ws8.path / ".cache" / "ast_uncoop_in.json")
        cancel_poison.cancel()
        r_poison = f_poison.result(timeout=6.0)
        r_parent = f_parent.result(timeout=6.0)
    elapsed = time.monotonic() - t0
    check(not r_poison.ok and r_parent.ok and elapsed < 4.2)

    ws_ret = HostPath(ws8.path / "ws_ret_shutdown")
    provision_live_workspace(ws_ret.path)
    disp_ret = build_dispatcher_for_workspace(ws_ret, resolve_dedicated_venv_py(ws8), is_daemon_host=True).dispatcher
    try:
        disp_ret.warmup_daemon_container()
        w_snap = disp_ret.tier1_pool.active_worker_snapshots()
        check(len(w_snap) >= 1)
        ret_pid = w_snap[0].pid
        (ws_ret.path / ".cache" / "ast_uncoop_in.json").unlink(missing_ok=True)
        (ws_ret.path / ".cache" / "kdb_search_in.json").unlink(missing_ok=True)
        c_tok = CancellationToken()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as rpool:
            f_hold = rpool.submit(disp_ret.invoke_typed, KDB_SEARCH_META, SearchInDto(query="hold", sleep_ms=3000))
            wait_file_marker(ws_ret.path / ".cache" / "kdb_search_in.json")
            f_taint = rpool.submit(
                disp_ret.invoke_typed, AST_OUTLINE_META,
                OutlineInDto(rel_file="./sample.py", uncoop_hang_ms=5000),
                caller_cwd=HostPath(ws_ret.path / "sub_dir"), cancel_token=c_tok,
            )
            wait_file_marker(ws_ret.path / ".cache" / "ast_uncoop_in.json")
            c_tok.cancel()
            check(not f_taint.result(timeout=4.0).ok)
            time.sleep(0.45)
            disp_ret.shutdown(grace_ms=150)
            _ = f_hold.result(timeout=4.0)
        dl_ret = time.monotonic() + 2.0
        while time.monotonic() < dl_ret and is_process_alive(ret_pid):
            time.sleep(0.03)
        check(not is_process_alive(ret_pid))
    finally:
        disp_ret.shutdown(grace_ms=100)


def _verify_codec_partial_and_endpoint_probe(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    def _outer_factory() -> tuple[type, type]:
        @dataclass(frozen=True, slots=True)
        class OuterSibling:
            code: int

        def _inner_factory() -> type:
            @dataclass(frozen=True, slots=True)
            class InnerTarget:
                sib: OuterSibling

            return InnerTarget

        return (_inner_factory(), OuterSibling)

    inner_cls, outer_sib_cls = _outer_factory()
    check(DataclassCodec.encode_object(
        DataclassCodec.decode(inner_cls, {"sib": {"code": 55}}, localns={"OuterSibling": outer_sib_cls})
    ) == {"sib": {"code": 55}})

    gen_ev_sub = EventSubscriptionSpec(EventId("genmod.gen_ev"), _map_concrete_gen_payload)
    check(gen_ev_sub.decode_and_map([{"payload": 11}, {"payload": 22}]) == 33)
    expect_yscb_code(lambda: gen_ev_sub.decode_and_map([{"payload": "wrong_str"}]), ErrorCode.CODEC_VALIDATION_FAILED)
    nested_gen = DataclassCodec.decode(_GenEnvelopeBase[_MapperLeafDto], {"payload": {"val": 19}, "label": "g"})
    check(isinstance(nested_gen, _GenEnvelopeBase) and isinstance(nested_gen.payload, _MapperLeafDto) and nested_gen.payload.val == 19)

    seen_inos: list[int] = []

    def _rec_with_tag(tag: str, m_ns: int, sz: int, ino_v: int) -> None:
        if tag == "ok" and m_ns > 0 and sz > 0:
            seen_inos.append(ino_v)

    pf = ws8.join(".cache", "partial_echo_probe.json")
    atomic_write_json(pf, {"a": 1}, before_replace=functools.partial(_rec_with_tag, "ok"))
    check(len(seen_inos) == 1 and seen_inos[0] == pf.path.stat().st_ino)

    (ws8.path / ".cache" / "ast_uncoop_in.json").unlink(missing_ok=True)
    (ws8.path / ".cache" / "kdb_search_in.json").unlink(missing_ok=True)
    c_p = CancellationToken()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        ft1 = pool.submit(disp8.invoke_typed, KDB_SEARCH_META, SearchInDto(query="a2_parent", sleep_ms=700, post_sync=True), routing_policy=ClientRoutingPolicy.STRICT_HOT)
        wait_file_marker(ws8.path / ".cache" / "kdb_search_in.json")
        fp = pool.submit(disp8.invoke_typed, AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py", uncoop_hang_ms=4500), caller_cwd=HostPath(ws8.path / "sub_dir"), routing_policy=ClientRoutingPolicy.STRICT_HOT, cancel_token=c_p)
        wait_file_marker(ws8.path / ".cache" / "ast_uncoop_in.json")
        c_p.cancel()
        check(not fp.result(timeout=4.0).ok)
        time.sleep(0.05)
        ft3 = pool.submit(disp8.invoke, InvokeRequest(TaskId("kdb.index"), {"force": False, "sleep_ms": 20}, ws8, ws8, routing_policy=ClientRoutingPolicy.STRICT_HOT))
        check(ft1.result(timeout=6.0).ok and ft3.result(timeout=6.0).ok)


def _verify_retiring_lock_yield_and_empty_reload(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    _ = disp8.invoke_typed(AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py"), caller_cwd=HostPath(ws8.path / "sub_dir"), routing_policy=ClientRoutingPolicy.STRICT_HOT)
    (ws8.path / ".cache" / "ast_uncoop_in.json").unlink(missing_ok=True)
    (ws8.path / ".cache" / "kdb_search_in.json").unlink(missing_ok=True)
    cancel_p = CancellationToken()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        f_blk = pool.submit(disp8.invoke, InvokeRequest(TaskId("kdb.index"), {"force": False, "sleep_ms": 260}, ws8, ws8, routing_policy=ClientRoutingPolicy.STRICT_HOT))
        time.sleep(0.02)
        f_contend = pool.submit(disp8.invoke, InvokeRequest(TaskId("kdb.index"), {"force": True, "sleep_ms": 0}, ws8, ws8, routing_policy=ClientRoutingPolicy.STRICT_HOT))
        f_par = pool.submit(disp8.invoke_typed, KDB_SEARCH_META, SearchInDto(query="hshake_yield", sleep_ms=360, post_sync=True), routing_policy=ClientRoutingPolicy.STRICT_HOT)
        wait_file_marker(ws8.path / ".cache" / "kdb_search_in.json")
        f_taint = pool.submit(disp8.invoke_typed, AST_OUTLINE_META, OutlineInDto(rel_file="./sample.py", uncoop_hang_ms=4500), caller_cwd=HostPath(ws8.path / "sub_dir"), routing_policy=ClientRoutingPolicy.STRICT_HOT, cancel_token=cancel_p)
        wait_file_marker(ws8.path / ".cache" / "ast_uncoop_in.json")
        cancel_p.cancel()
        check(not f_taint.result(timeout=4.0).ok)
        check(f_blk.result(timeout=5.0).ok and f_par.result(timeout=5.0).ok and f_contend.result(timeout=5.0).ok)

    vsc_entry = ws8.path / ".modules" / "vsc" / "local_util.py"
    orig_vsc_util = vsc_entry.read_text(encoding="utf-8")
    try:
        vsc_entry.write_text(orig_vsc_util.replace('"VSC_H"', '"VSC_RELOADED_ALL"'), encoding="utf-8")
        rel_rep = query_daemon_control(ws8.join(".cache"), ws8, FrameKind.CONTROL_RELOAD, {})
        check(rel_rep is not None and rel_rep.get("ok") is True and rel_rep.get("reloaded") is True)
        v_after = disp8.invoke(InvokeRequest(TaskId("vsc.sync"), {}, ws8, ws8, routing_policy=ClientRoutingPolicy.STRICT_HOT))
        check(v_after.ok and isinstance(v_after.value, Mapping) and v_after.value.get("helper_who") == "VSC_RELOADED_ALL")
    finally:
        vsc_entry.write_text(orig_vsc_util, encoding="utf-8")
        _ = query_daemon_control(ws8.join(".cache"), ws8, FrameKind.CONTROL_RELOAD, {})


def _verify_codec_nan_union_key_and_lease_bounds(ws8: HostPath, disp8: RuntimeDispatcher) -> None:
    uk = _UnionKeyMapDto(entries={_SampleIntEnum.FAST: "fast_v", 42: "num_v"})
    check(DataclassCodec.decode(_UnionKeyMapDto, DataclassCodec.encode_object(uk)) == uk)

    nan_val = float("nan")
    for pol in (ClientRoutingPolicy.FORCE_COLD, ClientRoutingPolicy.AUTO_NO_SPAWN, ClientRoutingPolicy.STRICT_HOT):
        bad_nan = disp8.invoke(
            InvokeRequest(TaskId("space.echo_tier0"), {"tag": nan_val}, ws8, ws8, routing_policy=pol)
        )
        check(not bad_nan.ok and bad_nan.error is not None and bad_nan.error.code == ErrorCode.CODEC_VALIDATION_FAILED)

    bad_typed = disp8.invoke_typed(
        TaskMetadata(TaskId("space.echo_tier0"), JsonObject, SimpleOutDto),
        {"tag": nan_val},
    )
    check(not bad_typed.ok and bad_typed.error is not None and bad_typed.error.code == ErrorCode.CODEC_VALIDATION_FAILED)

    lease_cdir = ws8.join(".cache_reboot_probe")
    atomic_write_json(
        lease_cdir.join("daemon", "handoff_lease.json"),
        {"old_boot_id": "pre_reboot_boot", "expires_epoch": time.time() + 86400.0},
    )
    check(wait_for_handoff_daemon_endpoint(lease_cdir, ws8, max_wait_sec=0.2) is None)


def _verify_daemon_hygiene_and_local_union(ws8: HostPath) -> None:
    (h1, lns1), s1 = _make_repeated_local_codec_pair(2)
    (h2, lns2), s2 = _make_repeated_local_codec_pair(5)
    d1 = DataclassCodec.decode(h1, {"item": {"v": 7}}, localns=lns1)
    d2 = DataclassCodec.decode(h2, {"item": {"v": 9}}, localns=lns2)
    check(type(d1) is h1 and type(d2) is h2)
    check(isinstance(s1, EventSubscriptionSpec) and s1.decode_and_map([{"v": 3}]) == 6)
    check(isinstance(s2, EventSubscriptionSpec) and s2.decode_and_map([{"v": 4}]) == 20)

    if os.name != "nt":
        dj_mode = (ws8.path / ".cache" / "daemon" / "daemon.json").stat().st_mode & 0o777
        check(dj_mode == 0o600, lambda: f"Expected 0o600 on daemon.json, got {oct(dj_mode)}")

    ws_cold = HostPath(ws8.path / "ws_case_cold_hygiene")
    provision_live_workspace(ws_cold.path)
    before_keys = set(sys.modules)
    disp_c = build_dispatcher_for_workspace(ws_cold, resolve_dedicated_venv_py(ws8), is_daemon_host=False).dispatcher
    check(disp_c.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="cold_clean"), routing_policy=ClientRoutingPolicy.FORCE_COLD).ok)
    mid_keys = set(sys.modules) - before_keys
    check(mid_keys == set(), lambda: f"ColdTurn leaked dynamic modules: {mid_keys}")
    disp_c.shutdown(grace_ms=100)
    after_keys = set(sys.modules) - before_keys
    check(after_keys == set(), lambda: f"Dispatcher.shutdown leaked dynamic modules: {after_keys}")


def run_rc02_and_rc03_paired(tmp_root: Path, venv_py: Path) -> None:
    """Execute stage 02 and stage 03 against a shared live workspace and clean up."""
    ws2 = HostPath(tmp_root / "ws_rc02")
    disp2: Optional[RuntimeDispatcher] = None
    try:
        rc02 = verify_rc02_warmup_events_and_preempt(tmp_root, venv_py)
        ws2, disp2 = rc02.ws, rc02.dispatcher
        verify_rc03_coalesce_priority_and_nested_group(rc02.ws, rc02.ws_path, rc02.dispatcher)
    finally:
        stop_daemon_cleanly(ws2)
        if disp2 is not None:
            disp2.shutdown()


def _run_rc02_standalone(tmp_root: Path, venv_py: Path) -> None:
    rig: Optional[Rc02StageRig] = None
    try:
        rig = verify_rc02_warmup_events_and_preempt(tmp_root, venv_py)
    finally:
        stop_daemon_cleanly(rig.ws if rig is not None else HostPath(tmp_root / "ws_rc02"))
        if rig is not None:
            rig.dispatcher.shutdown()


def _run_rc03_standalone(tmp_root: Path, venv_py: Path) -> None:
    ws3_path = tmp_root / "ws_rc03"
    provision_live_workspace(ws3_path, include_broken_opt=False)
    ws3 = HostPath(ws3_path)
    disp3 = build_dispatcher_for_workspace(ws3, HostPath(venv_py), ttl_sec=20.0).dispatcher
    try:
        check(disp3.invoke_typed(ECHO_TIER0_META, EchoInDto(tag="boot")).ok)
        wait_for_daemon_online(ws3)
        verify_rc03_coalesce_priority_and_nested_group(ws3, ws3_path, disp3)
    finally:
        stop_daemon_cleanly(ws3)
        disp3.shutdown()


RC_SUITE_MAP: Final[dict[str, Callable[[Path, Path], None]]] = {
    "rc01": verify_rc01_cold_storm_and_sandbox,
    "rc02": _run_rc02_standalone,
    "rc03": _run_rc03_standalone,
    "rc04": verify_rc04_multiplex_cancel_and_ttl,
    "rc05": verify_rc05_tty_periodic_and_worker_crashes,
    "rc06": verify_rc06_quiesce_hot_reload_and_core_mutation,
    "rc07": verify_rc07_child_sandbox_and_lifo_teardown,
    "rc08": verify_rc08_cross_proc_locks_and_guards,
}


def run_all_rc_e2e(tmp_root: Path, venv_py: Path) -> None:
    """Run all end-to-end RC stages sequentially, enforcing zero stage orphans and final cleanup."""
    try:
        for stage_fn in (
            verify_rc01_cold_storm_and_sandbox,
            run_rc02_and_rc03_paired,
            verify_rc04_multiplex_cancel_and_ttl,
            verify_rc05_tty_periodic_and_worker_crashes,
            verify_rc06_quiesce_hot_reload_and_core_mutation,
            verify_rc07_child_sandbox_and_lifo_teardown,
            verify_rc08_cross_proc_locks_and_guards,
        ):
            stage_fn(tmp_root, venv_py)
            assert_zero_live_stage_orphans(tmp_root)
    finally:
        force_reap_tmp_root_orphans(tmp_root)


__all__ = (
    "RC_SUITE_MAP",
    "Rc02StageRig",
    "run_all_rc_e2e",
    "run_rc02_and_rc03_paired",
    "verify_rc01_cold_storm_and_sandbox",
    "verify_rc02_warmup_events_and_preempt",
    "verify_rc03_coalesce_priority_and_nested_group",
    "verify_rc04_multiplex_cancel_and_ttl",
    "verify_rc05_tty_periodic_and_worker_crashes",
    "verify_rc06_quiesce_hot_reload_and_core_mutation",
    "verify_rc07_child_sandbox_and_lifo_teardown",
    "verify_rc08_cross_proc_locks_and_guards",
)
