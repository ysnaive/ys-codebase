"""Modular real-machine verification runner for Core 2.0 domains, SDK facade, and live E2E scenarios."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Final, Optional, Sequence
import warnings

warnings.simplefilter("error", ResourceWarning)

_CORE_V2_ROOT: Final[Path] = Path(__file__).resolve().parent
_CORE_SRC_ROOT: Final[Path] = _CORE_V2_ROOT / "source" / "core"
for _entry in (str(_CORE_V2_ROOT), str(_CORE_SRC_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from tests._boot import cli_oneshot_main, daemon_process_main
from tests._harness import (
    assert_zero_live_stage_orphans,
    check,
    force_reap_tmp_root_orphans,
    log,
)
from tests.test_foundation_fs import run_foundation_fs_suite
from tests.test_gate0 import verify_gate0_ast_architecture
from tests.test_rc_e2e import RC_SUITE_MAP, run_all_rc_e2e
from tests.test_runtime_daemon import run_runtime_daemon_suite
from tests.test_surface_sdk import run_surface_sdk_suite

_ALL_ORDER: Final[tuple[str, ...]] = (
    "gate0",
    "foundation_fs",
    "surface_sdk",
    "runtime_daemon",
    "rc_e2e",
)
_VENV_REQUIRED: Final[frozenset[str]] = frozenset({"runtime_daemon", "rc_e2e", *RC_SUITE_MAP.keys()})
_VALID_SUITES: Final[frozenset[str]] = frozenset({"all", *_ALL_ORDER, *RC_SUITE_MAP.keys()})


def _parse_suite_selection(raw_suites: Sequence[str]) -> tuple[str, ...]:
    tokens: list[str] = []
    for item in raw_suites:
        for part in item.split(","):
            tok = part.strip().lower()
            if tok:
                tokens.append(tok)
    if not tokens or "all" in tokens:
        return _ALL_ORDER
    ordered: list[str] = []
    for tok in tokens:
        if tok not in _VALID_SUITES:
            raise ValueError(f"Unknown verification suite {tok!r}; expected one of {sorted(_VALID_SUITES)}")
        if tok not in ordered:
            ordered.append(tok)
    return tuple(ordered)


def _create_isolated_venvs(tmp_root: Path) -> Path:
    venv_dir = tmp_root / "shared_venv"
    ded_venv_dir = tmp_root / "dedicated_gdrive_venv"
    win_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    for target_dir in (venv_dir, ded_venv_dir):
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(target_dir)],
            check=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=win_flags,
        )
    rel_bin = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    venv_py = venv_dir / rel_bin
    ded_venv_py = ded_venv_dir / rel_bin
    check(venv_py.is_file() and ded_venv_py.is_file())
    return venv_py


def _run_selected_suites(selected: Sequence[str]) -> None:
    started = time.monotonic()
    if "gate0" in selected:
        t0 = time.monotonic()
        log("[Gate 0] Verifying explicit allowlist DAG, Living-Spec 1:1 parity, zero Any/print/getattr & multi-file self-audit...")
        verify_gate0_ast_architecture(include_runner=True)
        log(f"  -> PASS: Gate 0 verified ({time.monotonic() - t0:.2f}s).")
    live_suites = tuple(s for s in selected if s != "gate0")
    if not live_suites:
        log(f"\nSELECTED VERIFICATIONS PASSED ({', '.join(selected)}, {time.monotonic() - started:.2f}s, 0 ResourceWarning)!")
        return
    needs_venv = any(s in _VENV_REQUIRED for s in live_suites)
    with tempfile.TemporaryDirectory(prefix="yscb_v2_live_") as tmp_dir_str:
        tmp_root = Path(tmp_dir_str)
        venv_py = _create_isolated_venvs(tmp_root) if needs_venv else Path(sys.executable)
        try:
            for suite_name in live_suites:
                t_s = time.monotonic()
                if suite_name == "foundation_fs":
                    run_foundation_fs_suite(tmp_root)
                elif suite_name == "surface_sdk":
                    run_surface_sdk_suite(tmp_root)
                elif suite_name == "runtime_daemon":
                    run_runtime_daemon_suite(tmp_root, venv_py)
                elif suite_name == "rc_e2e":
                    run_all_rc_e2e(tmp_root, venv_py)
                else:
                    RC_SUITE_MAP[suite_name](tmp_root, venv_py)
                assert_zero_live_stage_orphans(tmp_root)
                log(f"  -> PASS: suite '{suite_name}' completed ({time.monotonic() - t_s:.2f}s).")
        finally:
            force_reap_tmp_root_orphans(tmp_root)
    log(f"\nALL SELECTED LIVE VERIFICATIONS PASSED ({', '.join(selected)}, {time.monotonic() - started:.2f}s, 0 ResourceWarning)!")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Core 2.0 modular live verification runner")
    parser.add_argument(
        "--suite",
        action="append",
        default=[],
        help="Suite(s) to execute: all, gate0, foundation_fs, surface_sdk, runtime_daemon, rc_e2e, rc01..rc08",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "--daemon-entry":
        return daemon_process_main(args[1], args[2], args[3])
    if args and args[0] == "--cli-oneshot":
        return cli_oneshot_main(args[1], args[2], args[3], args[4], args[5], args[6])
    parsed = _build_arg_parser().parse_args(args)
    selected = _parse_suite_selection(parsed.suite)
    _run_selected_suites(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
