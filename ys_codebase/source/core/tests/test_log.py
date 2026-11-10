"""
Unit & Edge-Case Tests for `core.log` Unified Logging Pipeline, `DebouncedIOStreamer`,
and `RollingFileLogger` (`FT-01` ~ `FT-05`, `ET-01` ~ `ET-05`).
"""

import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import shutil
import sys
from unittest.mock import patch

from dev.testing import Requirement, YSCBTestCase, require

from core import log as core_log
from core.log import (
    DebouncedIOStreamer,
    RollingFileLogger,
    _extract_log_file_timestamp,
    _safe_replace_file,
    bind_log_context,
    clear_error_hint,
    extract_error_hint,
    get_current_log_scope,
    get_last_error_hint,
    log,
    log_debug,
    log_error,
    log_file,
    log_file_jsonl,
    log_info,
    log_stream,
    log_warn,
    read_log_file_jsonl,
    read_log_file_tail,
    record_error_hint,
)
from core.telemetry import record_cli_event, read_telemetry_records


@require(Requirement.LOGIC)
class TestCoreLogPipeline(YSCBTestCase):
    """Comprehensive verification for `core.log` stream family, file family, and edge cases."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = tempfile.mkdtemp(prefix="yscb_test_log_")
        clear_error_hint()

    def tearDown(self) -> None:
        clear_error_hint()
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    def test_ft01_terminal_stream_family_and_contextvar_routing(self) -> None:
        """
        FT-01: Verify `log*` caller stream family (`log`, `log_stream`, `log_info`,
        `log_warn`, `log_error`, `log_debug`) in foreground vs background `RollingFileLogger` scope.
        """
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            log("hello", "world", sep="-")
            log_info("info message")
            log_warn("warn on stdout")
            log_warn("warn on stderr", stream="stderr")
            log_error("error on stdout")
            log_error("error on stderr", stream="stderr")
            log_stream("raw-chunk", stream="stdout")
            # Debug disabled by default
            log_debug("hidden debug")

        self.assertEqual(
            out_buf.getvalue(),
            "hello-world\ninfo message\nwarn on stdout\nerror on stdout\nraw-chunk",
        )
        self.assertEqual(err_buf.getvalue(), "warn on stderr\nerror on stderr\n")

        # Verify debug enabled via bind_log_context
        dbg_buf = io.StringIO()
        with redirect_stderr(dbg_buf):
            with bind_log_context(debug_enabled=True):
                log_debug("visible debug")
        self.assertEqual(dbg_buf.getvalue(), "visible debug\n")

        # Verify Plane P4 background_sink routing writes structured lines to RollingFileLogger
        bg_dir = os.path.join(self.tmp_dir, "bg_logs")
        bg_logger = RollingFileLogger(yscb_root=self.tmp_dir, log_dir=bg_dir)
        bg_logger.recover_and_open()
        try:
            fg_buf = io.StringIO()
            with redirect_stdout(fg_buf), bind_log_context(
                background_sink=bg_logger, component="svc_worker"
            ):
                log_info("background task started")
                log_warn("background warning")
                log_error("background failure")
                self.assertIsNotNone(get_current_log_scope())
            # Nothing should leak to foreground stdout when background_sink is bound
            self.assertEqual(fg_buf.getvalue(), "")
            chunk, _, _ = bg_logger.read_tail_chunks(0)
            self.assertIn("[INFO] [svc_worker] background task started", chunk)
            self.assertIn("[WARNING] [svc_worker] background warning", chunk)
            self.assertIn("[ERROR] [svc_worker] background failure", chunk)
        finally:
            bg_logger.close()

        self.mark_passed()

    def test_ft02_debounced_io_streamer_and_server_facade(self) -> None:
        """
        FT-02: Verify `DebouncedIOStreamer` capture, consolidation, 4KB auto-flush,
        `send_task_finish`, and `_StreamProxy` contract.
        """
        emitted = []
        streamer = DebouncedIOStreamer(
            emit_chunk=lambda pkt: emitted.append(pkt),
            debounce_ms=500,
            max_buffer_bytes=64,
        )
        with streamer:
            log("line 1")
            log_info("line 2")
            log_error("err 1", stream="stderr")
            # Trigger immediate flush by exceeding 64 bytes
            log("x" * 80)

        streamer.send_task_finish(exit_code=0, duration_ms=12.5, error=None)

        stream_pkts = [p for p in emitted if p.get("type") == "terminal_stream"]
        finish_pkts = [p for p in emitted if p.get("type") == "task_finish"]
        self.assertTrue(len(stream_pkts) >= 2)
        self.assertEqual(len(finish_pkts), 1)
        self.assertEqual(finish_pkts[0]["exit_code"], 0)

        stdout_combined = "".join(p["text"] for p in stream_pkts if p["stream"] == "stdout")
        stderr_combined = "".join(p["text"] for p in stream_pkts if p["stream"] == "stderr")
        self.assertIn("line 1\nline 2\n", stdout_combined)
        self.assertIn("x" * 80, stdout_combined)
        self.assertEqual(stderr_combined, "err 1\n")

        self.mark_passed()

    def test_ft03_rolling_file_logger_and_log_file_family(self) -> None:
        """
        FT-03: Verify `RollingFileLogger`, `log_file`,
        `log_file_jsonl`, `read_log_file_jsonl`, and `read_log_file_tail`.
        """
        log_dir = os.path.join(self.tmp_dir, "rolling")
        r_logger = RollingFileLogger(yscb_root=self.tmp_dir, log_dir=log_dir, echo_console=True)
        echo_buf = io.StringIO()
        with redirect_stdout(echo_buf):
            start_ts = r_logger.recover_and_open()
            self.assertTrue(r_logger.is_opened)
            r_logger.info("master booted")
            r_logger.warn("minor issue")
            try:
                raise ValueError("boom error")
            except ValueError as exc:
                r_logger.error("caught exception", exc_info=exc)

        self.assertIn("master booted", echo_buf.getvalue())
        text, offset, ino = r_logger.read_tail_chunks(0)
        self.assertIn(f'server start at time "{start_ts}"', text)
        self.assertIn("[INFO] [master] master booted", text)
        self.assertIn("[WARNING] [master] minor issue", text)
        self.assertIn("ValueError: boom error", text)
        self.assertGreater(offset, 0)

        arch_path = r_logger.archive_and_close()
        self.assertIsNotNone(arch_path)
        self.assertFalse(r_logger.is_opened)
        self.assertTrue(os.path.isfile(arch_path))

        # Test functional log_file with line rotation (9 bytes/line -> > 50 bytes at 6 lines -> keeps 3)
        plain_log = Path(self.tmp_dir) / "plain.log"
        for idx in range(6):
            ok = log_file(plain_log, f"entry-{idx:02d}", max_bytes=50, keep_lines=3)
            self.assertTrue(ok)
        lines = plain_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["entry-03", "entry-04", "entry-05"])

        # Test log_file_jsonl and read_log_file_jsonl
        jsonl_path = Path(self.tmp_dir) / "ledger.jsonl"
        for idx in range(8):
            self.assertTrue(
                log_file_jsonl(jsonl_path, {"seq": idx, "msg": "payload"}, max_bytes=80, keep_lines=4)
            )
        records = read_log_file_jsonl(jsonl_path)
        self.assertEqual([r["seq"] for r in records], [4, 5, 6, 7])
        tail_two = read_log_file_jsonl(jsonl_path, limit=2)
        self.assertEqual([r["seq"] for r in tail_two], [6, 7])

        # Negative test: non-dict record returns False
        self.assertFalse(log_file_jsonl(jsonl_path, "not-a-dict"))  # type: ignore[arg-type]

        self.mark_passed()

    def test_ft04_telemetry_delegation_and_error_hint_accumulation(self) -> None:
        """
        FT-04: Verify `telemetry.py` delegates to `core.log` and `error_hint` accumulation
        prioritizes `[ERROR]`/`[FAIL]` keywords across multiple `log_error` calls (`EC-05`).
        """
        clear_error_hint()
        log_error("Some preliminary context line")
        log_error("[FAIL] Critical validation failure in module 'core'")
        log_error("Follow-up remediation hint")

        hint = get_last_error_hint()
        self.assertEqual(hint, "[FAIL] Critical validation failure in module 'core'")

        telemetry_file = Path(self.tmp_dir) / "telemetry.jsonl"
        with patch.dict(os.environ, {"YSCB_TELEMETRY_PATH": str(telemetry_file)}):
            ok = record_cli_event(
                module_name="core",
                cmd_path=["contributes", "check"],
                args=["core"],
                exit_code=1,
                duration_ms=15.2,
                mode="local",
                error_hint=get_last_error_hint(),
            )
            self.assertTrue(ok)
            recs = read_telemetry_records(telemetry_path=telemetry_file)
            self.assertEqual(len(recs), 1)
            self.assertEqual(
                recs[0]["error_hint"],
                "[FAIL] Critical validation failure in module 'core'",
            )

        self.mark_passed()

    def test_ft05_core_module_zero_a1_violations_and_public_export(self) -> None:
        """
        FT-05: AST scan across all non-test `.py` files in `ys_codebase/source/core/`
        verifies 0 `print()`, 0 `sys.stdout.write`/`sys.stderr.write`, and 0 `import logging`
        outside `core/core/log.py`.
        """
        import core

        self.assertIs(core.log, core_log)

        core_src_root = Path(__file__).resolve().parents[1]
        violations = []
        for py_file in sorted(core_src_root.rglob("*.py")):
            rel = py_file.relative_to(core_src_root).as_posix()
            if rel.startswith("tests/") or rel == "core/log.py":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "print":
                        violations.append(f"{rel}:{node.lineno}: print()")
                    elif isinstance(node.func, ast.Attribute) and node.func.attr in ("write", "flush"):
                        val = node.func.value
                        if (
                            isinstance(val, ast.Attribute)
                            and isinstance(val.value, ast.Name)
                            and val.value.id == "sys"
                            and val.attr in ("stdout", "stderr")
                        ):
                            violations.append(f"{rel}:{node.lineno}: sys.{val.attr}.{node.func.attr}()")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "logging" or alias.name.startswith("logging."):
                            violations.append(f"{rel}:{node.lineno}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and (node.module == "logging" or node.module.startswith("logging.")):
                        violations.append(f"{rel}:{node.lineno}: from {node.module} import ...")

        self.assertEqual(violations, [], f"Found A1 violations in module:core: {violations}")
        self.mark_passed()

    def test_et01_no_circular_import_or_undefined_uri_reentry(self) -> None:
        """
        ET-01 (`EC-01`): `core/log.py` has 0 top-level `core.*` imports, and `log_file`
        calls `uri.resolve(..., interactive=False)` without triggering interactive prompts.
        """
        log_py = Path(core_log.__file__).read_text(encoding="utf-8")
        tree = ast.parse(log_py)
        top_level_core_imports = []
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name == "core" or alias.name.startswith("core."):
                        top_level_core_imports.append(alias.name)
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module and (stmt.module == "core" or stmt.module.startswith("core.")):
                    top_level_core_imports.append(stmt.module)
        self.assertEqual(top_level_core_imports, [])

        # Verify undefined URI in log_file returns False cleanly without calling input()
        with patch("builtins.input", side_effect=AssertionError("input() must not be called!")):
            res = log_file("nonexistent_scheme://foo/bar.log", "test line")
            self.assertFalse(res)

        self.mark_passed()

    def test_et02_inner_redirect_stdout_precedence_inside_streamer(self) -> None:
        """
        ET-02 (`EC-02`): When a unit test uses `redirect_stdout` or `patch('sys.stderr')`
        inside an active `DebouncedIOStreamer`, `core.log` writes to the inner redirected buffer.
        """
        emitted = []
        streamer = DebouncedIOStreamer(emit_chunk=lambda p: emitted.append(p))
        with streamer:
            log("outer before")
            inner_out = io.StringIO()
            inner_err = io.StringIO()
            with redirect_stdout(inner_out), redirect_stderr(inner_err):
                log("captured by inner stdout")
                log_error("captured by inner stderr", stream="stderr")
            log("outer after")

        self.assertEqual(inner_out.getvalue(), "captured by inner stdout\n")
        self.assertEqual(inner_err.getvalue(), "captured by inner stderr\n")

        outer_text = "".join(p["text"] for p in emitted if p.get("type") == "terminal_stream")
        self.assertIn("outer before\n", outer_text)
        self.assertIn("outer after\n", outer_text)
        self.assertNotIn("captured by inner stdout", outer_text)

        self.mark_passed()

    def test_et03_streamer_reentrant_flush_and_idempotent_stop(self) -> None:
        """
        ET-03 (`EC-03`): Re-entrant `streamer.flush()` inside `emit_chunk` callback does not
        duplicate packets or deadlock, and repeated `stop_capture()` is idempotent.
        """
        emitted = []
        streamer_ref = []

        def _reentrant_emit(pkt):
            emitted.append(pkt)
            if streamer_ref:
                # Re-entrant flush inside emit_chunk
                streamer_ref[0].flush()

        streamer = DebouncedIOStreamer(emit_chunk=_reentrant_emit)
        streamer_ref.append(streamer)
        streamer.start_capture()
        try:
            log("single message")
            streamer.flush()
        finally:
            streamer.stop_capture()
            # Idempotent second call
            streamer.stop_capture()

        stream_pkts = [p for p in emitted if p.get("type") == "terminal_stream"]
        self.assertEqual(len(stream_pkts), 1)
        self.assertEqual(stream_pkts[0]["text"], "single message\n")

        self.mark_passed()

    def test_et04_safe_replace_file_os_replace_and_fallback(self) -> None:
        """
        ET-04 (`EC-04`): `_safe_replace_file` uses `os.replace` and falls back to
        `shutil.copy2` + `os.remove` when `os.replace` raises `OSError`.
        """
        src = os.path.join(self.tmp_dir, "src.txt")
        dst = os.path.join(self.tmp_dir, "dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("atomic payload")
        with open(dst, "w", encoding="utf-8") as f:
            f.write("old destination")

        # 1. Normal os.replace overwrites existing dst
        _safe_replace_file(src, dst)
        self.assertFalse(os.path.exists(src))
        with open(dst, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "atomic payload")

        # 2. Fallback when os.replace raises OSError
        src2 = os.path.join(self.tmp_dir, "src2.txt")
        dst2 = os.path.join(self.tmp_dir, "dst2.txt")
        with open(src2, "w", encoding="utf-8") as f:
            f.write("fallback payload")

        import errno as _errno
        with patch("core.log.os.replace", side_effect=OSError(_errno.EXDEV, "Cross-device link")):
            _safe_replace_file(src2, dst2)

        self.assertFalse(os.path.exists(src2))
        with open(dst2, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "fallback payload")

        self.mark_passed()

    def test_et05_dispatcher_locks_error_hint_before_post_cli_dispatch(self) -> None:
        """
        ET-05 (`EC-05`): Verify `dispatcher.dispatch_local` locks the primary command's
        `error_hint` before `post_cli_dispatch` hooks run, preventing secondary post-hook
        error logs from overwriting the primary failure hint.
        """
        from core.commands import dispatcher

        def _fake_hooks(event_name: str, verbose: bool = False) -> None:
            if event_name == "post_cli_dispatch":
                log_error("[FAIL] Secondary post-hook noise that should not overwrite primary hint")

        err_buf = io.StringIO()
        with patch.object(dispatcher, "_ensure_hooks", side_effect=_fake_hooks), redirect_stdout(
            err_buf
        ):
            exit_code = dispatcher.dispatch_local(
                module_name="nonexistent_test_module",
                cmd_name=["run"],
                raw_args=[],
                cmd_spec=None,
                yscb_abs=self.tmp_dir,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            get_last_error_hint(),
            "[yscb] Error: Cannot find CLI entrypoint for module 'nonexistent_test_module'.",
        )
        self.mark_passed()

    def test_remediation_background_sink_echo_console_and_streamer_debounce(self) -> None:
        """
        Verify:
        1. `RollingFileLogger.write_raw` with `echo_console=True` inside `bind_log_context(background_sink=logger)`
           writes directly to `sys.stdout` without infinite recursion.
        2. `_write_to_active_target` writing to `scope.streamer` via `log_stream(..., flush=True)`
           buffers small chunks instead of immediately flushing on every call.
        3. `DebouncedIOStreamer.start_capture()` is idempotent on re-entry and isolates `background_sink=None`
           and `error_chunks=[]`.
        4. `_StreamProxy.write` redirects to `scope.background_sink` when a background scope is active.
        5. `isolated_error_scope=True` isolates error chunks from the global fallback buffer.
        6. `_rotate_lines_file` preserves JSONL lines containing `\\u2028`/`\\u2029` without splitting them.
        """
        log_dir = os.path.join(self.tmp_dir, "echo_bg_logs")
        logger = RollingFileLogger(log_dir, echo_console=True)
        out_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), bind_log_context(
                background_sink=logger, component="bg-svc"
            ):
                log_info("echo console safe message")
            self.assertIn("[INFO] [bg-svc] echo console safe message", out_buf.getvalue())
            with open(logger.log_file, "r", encoding="utf-8") as f:
                self.assertIn("[INFO] [bg-svc] echo console safe message", f.read())

            # Debounce preservation & start_capture idempotency + background_sink isolation
            emitted = []
            streamer = DebouncedIOStreamer(
                emit_chunk=lambda pkt: emitted.append(pkt),
                debounce_ms=60000,
                max_buffer_bytes=4096,
            )
            with bind_log_context(background_sink=logger, component="parent-bg"):
                streamer.start_capture()
                # Re-entrant start_capture must not overwrite _orig_stdout with _stdout_proxy
                streamer.start_capture()
                try:
                    log_stream("small chunk 1\n", flush=True)
                    log_stream("small chunk 2\n", flush=True)
                    # Should still be buffered before flush/stop_capture
                    self.assertEqual(emitted, [])

                    # Inner background_sink scope writing to sys.stdout (_StreamProxy) routes to logger
                    with bind_log_context(background_sink=logger, component="inner-bg"):
                        sys.stdout.write("proxy routed to bg sink\n")
                        sys.stderr.write("proxy err routed to bg sink\n")
                    self.assertEqual(emitted, [])
                finally:
                    streamer.stop_capture()

            self.assertIsNot(sys.stdout, streamer._stdout_proxy)
            stream_pkts = [p for p in emitted if p.get("type") == "terminal_stream"]
            self.assertEqual(len(stream_pkts), 1)
            self.assertEqual(stream_pkts[0]["text"], "small chunk 1\nsmall chunk 2\n")
            with open(logger.log_file, "r", encoding="utf-8") as f:
                bg_content = f.read()
            self.assertIn("[INFO] [inner-bg] proxy routed to bg sink", bg_content)
            self.assertIn("[WARNING] [inner-bg] proxy err routed to bg sink", bg_content)
        finally:
            logger.close()

        # Isolated error scope does not pollute or clear global error hint
        clear_error_hint()
        record_error_hint("[ERROR] Outer primary error")
        with bind_log_context(isolated_error_scope=True):
            self.assertEqual(get_last_error_hint(), "")
            record_error_hint("[FAIL] Isolated inner error")
            self.assertEqual(get_last_error_hint(), "[FAIL] Isolated inner error")
            clear_error_hint()
            self.assertEqual(get_last_error_hint(), "")
        self.assertEqual(get_last_error_hint(), "[ERROR] Outer primary error")

        # _rotate_lines_file preserves \u2028 and \u2029 inside JSONL lines
        jsonl_file = os.path.join(self.tmp_dir, "unicode_sep.jsonl")
        for idx in range(5):
            log_file_jsonl(
                jsonl_file,
                {"idx": idx, "msg": f"line\u2028sep\u2029val_{idx}"},
                max_bytes=50,
                keep_lines=3,
            )
        rows = read_log_file_jsonl(jsonl_file)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["idx"] for r in rows], [2, 3, 4])
        self.assertEqual(rows[-1]["msg"], "line\u2028sep\u2029val_4")

        self.mark_passed()

    def test_progress_reporter_and_stderr_immediate_streamer_flush(self) -> None:
        """
        Verify:
        1. `ProgressReporter` suppresses fast tasks (< initial_delay_ms) unless `YSCB_FORCE_PROGRESS=1`.
        2. With `YSCB_FORCE_PROGRESS=1`, `ProgressReporter` emits stage & percentage lines strictly to `stderr`
           without polluting `stdout` or `get_last_error_hint()`, and immediately flushes `DebouncedIOStreamer`.
        3. `ProgressReporter` stays silent inside `bind_log_context(background_sink=...)` and `YSCB_QUIET_PROGRESS=1`.
        4. `_stderr_proxy.write` with `\r` flushes `DebouncedIOStreamer` immediately, while `stdout` small chunks stay buffered.
        5. `ProgressReporter` cooperates with `request_task_cancel()` and raises `TaskCancelledError`.
        """
        from core.context import (
            TaskCancelledError,
            bind_runtime_context,
            request_task_cancel,
            reset_task_cancelled,
        )
        from core.log import ProgressReporter

        # (a) Ultra-fast operation under default 200ms threshold emits nothing
        out_fast, err_fast = io.StringIO(), io.StringIO()
        with redirect_stdout(out_fast), redirect_stderr(err_fast):
            pr_fast = ProgressReporter("ast", "建置索引", total_stages=2, initial_delay_ms=5000.0)
            pr_fast.stage(1, "解析檔案", 1, 4)
            pr_fast.advance(2, 4)
            pr_fast.finish("索引完成")
        self.assertEqual(out_fast.getvalue(), "")
        self.assertEqual(err_fast.getvalue(), "")

        # (b) Forced progress inside DebouncedIOStreamer flushes immediately to stderr, 0 stdout, 0 error_hint
        clear_error_hint()
        emitted = []
        streamer = DebouncedIOStreamer(
            emit_chunk=emitted.append,
            debounce_ms=60000,
            max_buffer_bytes=4096,
        )
        with bind_runtime_context(env={"YSCB_FORCE_PROGRESS": "1"}):
            with streamer:
                pr = ProgressReporter("ast", "建置工作區索引", total_stages=2, interval_ms=20.0)
                pr.stage(1, "解析檔案", 0, 4)
                # Must have flushed immediately without waiting for debounce timer or stop_capture
                self.assertGreaterEqual(len(emitted), 1)
                self.assertEqual(emitted[-1]["stream"], "stderr")
                self.assertIn("[ast] 建置工作區索引 (1/2: 解析檔案 0/4 [0%]...)", emitted[-1]["text"])

                pr.advance(4, 4, detail="done")
                pr.finish("工作區索引完成")
                self.assertEqual(get_last_error_hint(), "")
                # Also verify carriage-return on stderr proxy flushes immediately
                prev_cnt = len(emitted)
                sys.stderr.write("tick\r")
                self.assertEqual(len(emitted), prev_cnt + 1)
                self.assertEqual(emitted[-1]["text"], "tick\r")

        stdout_pkts = [p for p in emitted if p.get("stream") == "stdout"]
        self.assertEqual(stdout_pkts, [])

        # (c) Background sink & YSCB_QUIET_PROGRESS=1 auto-silence ProgressReporter
        bg_dir = os.path.join(self.tmp_dir, "pr_bg_logs")
        bg_logger = RollingFileLogger(bg_dir, echo_console=False)
        try:
            with bind_runtime_context(env={"YSCB_FORCE_PROGRESS": "1"}), bind_log_context(
                background_sink=bg_logger, component="bg-worker"
            ):
                pr_bg = ProgressReporter("knowledge-db", "背景同步", total_stages=1)
                pr_bg.stage(1, "向量嵌入", 1, 2)
                pr_bg.finish()
            if os.path.exists(bg_logger.log_file):
                with open(bg_logger.log_file, "r", encoding="utf-8") as f:
                    self.assertNotIn("背景同步", f.read())
        finally:
            bg_logger.close()

        err_quiet = io.StringIO()
        with bind_runtime_context(env={"YSCB_FORCE_PROGRESS": "1", "YSCB_QUIET_PROGRESS": "1"}), redirect_stderr(
            err_quiet
        ):
            pr_q = ProgressReporter("ast", "靜默測試", total_stages=1)
            pr_q.stage(1, "解析", 1, 1, force=True)
            pr_q.finish()
        self.assertEqual(err_quiet.getvalue(), "")

        # (d) Cooperative cancellation raises TaskCancelledError
        reset_task_cancelled()
        request_task_cancel()
        try:
            pr_cancel = ProgressReporter("ast", "取消測試", enabled=False)
            with self.assertRaises(TaskCancelledError):
                pr_cancel.stage(1, "解析")
        finally:
            reset_task_cancelled()

        self.mark_passed()


