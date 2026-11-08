"""
Core Telemetry - Lightweight CLI Execution Flight Recorder.
100% Python Standard Library. Zero Upper-Layer Coupling.

Delegates JSONL append, rolling line-retention truncation, and error hint extraction
to `core.log`.
"""
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.log import (
    _parse_jsonl_dict_line,
    _rotate_lines_file,
    extract_error_hint,
    log_file_jsonl,
    read_log_file_jsonl,
)

MAX_TELEMETRY_BYTES: int = 512 * 1024
KEEP_TELEMETRY_LINES: int = 1500


def _safe_getcwd() -> str:
    """安全取得當前工作目錄，若目錄已被刪除則回傳空字串。"""
    try:
        from core.context import get_virtual_cwd

        return get_virtual_cwd()
    except OSError:
        return ""


def _discover_yscb_root(yscb_abs: Optional[str] = None) -> Path:
    """探索 yscb 根目錄路徑，統一委派至 core.uri.resolve_yscb_root()。"""
    if yscb_abs:
        return Path(yscb_abs).resolve()
    from core import uri
    return Path(uri.resolve_yscb_root()).resolve()


def resolve_telemetry_path(yscb_abs: Optional[str] = None) -> Path:
    """
    解析 cache://core/telemetry.jsonl 絕對路徑。
    若設定環境變數 YSCB_TELEMETRY_PATH 則優先使用（供單元測試隔離驗證）。
    """
    env_override = os.environ.get("YSCB_TELEMETRY_PATH", "").strip()
    if env_override:
        return Path(env_override).resolve()

    if yscb_abs is None:
        try:
            from core import uri
            resolved = uri.resolve("cache://core/telemetry.jsonl", interactive=False)
            if resolved and not str(resolved).startswith("!"):
                return Path(resolved).resolve()
        except Exception:
            pass

    root = _discover_yscb_root(yscb_abs)
    return (root / ".cache" / "core" / "telemetry.jsonl").resolve()


def should_record_telemetry(
    module_name: str,
    cmd_path: List[str],
    raw_args: List[str],
) -> bool:
    """
    判定當前 CLI 呼叫是否應寫入 Telemetry：
    1. 若處於沙盒測試 (YSCB_TEST_SANDBOX == '1' 或 YSCB_TESTING == '1') 且未顯式設定 YSCB_TELEMETRY_PATH，預設略過。
    2. 略過 -h / --help / help 查詢。
    3. 略過 session-trace 自身呼叫，防止自檢動作污染觀測數據。
    """
    has_override = bool(os.environ.get("YSCB_TELEMETRY_PATH", "").strip())
    if not has_override:
        if os.environ.get("YSCB_TEST_SANDBOX") == "1" or os.environ.get("YSCB_TESTING") == "1":
            return False

    tokens = [str(t) for t in (cmd_path or [])] + [str(a) for a in (raw_args or [])]
    if any(t in ("-h", "--help", "help") for t in tokens):
        return False

    if cmd_path and cmd_path[0] in ("session-trace", "session_trace"):
        return False

    return True


def _parse_iso_to_epoch(iso_str: str) -> Optional[float]:
    """將 ISO-8601 時間字串解析為 UTC epoch 秒數。"""
    if not iso_str:
        return None
    s = iso_str.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def record_cli_event(
    module_name: str,
    cmd_path: List[str],
    args: List[str],
    exit_code: int,
    duration_ms: float,
    mode: str = "local",
    error_hint: str = "",
    yscb_abs: Optional[str] = None,
    cwd: Optional[str] = None,
    max_bytes: int = MAX_TELEMETRY_BYTES,
    keep_lines: int = KEEP_TELEMETRY_LINES,
) -> bool:
    """
    將單筆 CLI 執行紀錄追加寫入 cache://core/telemetry.jsonl。
    當檔案超過 max_bytes 時自動滾動截斷並保留最新 keep_lines 筆紀錄。
    全程靜默防護任何 I/O 例外，100% 不阻塞正常 CLI 執行。
    """
    try:
        if not should_record_telemetry(module_name, cmd_path, args):
            return False

        target_path = resolve_telemetry_path(yscb_abs)

        now_epoch = time.time()
        now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record: Dict[str, Any] = {
            "ts": now_iso,
            "epoch": round(now_epoch, 3),
            "module": str(module_name or ""),
            "cmd": " ".join(str(c) for c in cmd_path) if cmd_path else "",
            "args": [str(a) for a in (args or [])[:20]],
            "exit_code": int(exit_code),
            "duration_ms": round(float(duration_ms), 2),
            "mode": str(mode or "local"),
            "cwd": str(cwd or _safe_getcwd()),
            "error_hint": extract_error_hint(error_hint, max_len=200),
        }

        return log_file_jsonl(
            target_path,
            record,
            max_bytes=max_bytes,
            keep_lines=keep_lines,
        )
    except Exception:
        return False


def _rotate_telemetry_file(target_path: Path, keep_lines: int = KEEP_TELEMETRY_LINES) -> None:
    """滾動截斷 telemetry.jsonl，僅保留最後 keep_lines 筆有效 JSONL。"""
    _rotate_lines_file(target_path, keep_lines=keep_lines, jsonl_only=True)


def read_telemetry_records(
    since_iso: Optional[str] = None,
    since_minutes: Optional[float] = None,
    limit: Optional[int] = None,
    yscb_abs: Optional[str] = None,
    telemetry_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """
    讀取並過濾 cache://core/telemetry.jsonl 紀錄清單。
    單行損毀自動跳過；支援 since_iso、since_minutes 與尾端筆數 limit 過濾。
    """
    try:
        path = Path(telemetry_path).resolve() if telemetry_path else resolve_telemetry_path(yscb_abs)
        if not path.is_file():
            return []

        cutoff_epoch: Optional[float] = None
        if since_iso:
            cutoff_epoch = _parse_iso_to_epoch(since_iso)
        if since_minutes is not None and since_minutes >= 0:
            min_cutoff = time.time() - (float(since_minutes) * 60.0)
            cutoff_epoch = max(cutoff_epoch, min_cutoff) if cutoff_epoch is not None else min_cutoff

        if cutoff_epoch is None:
            return read_log_file_jsonl(path, limit=limit)

        def _time_filter(item: Dict[str, Any]) -> bool:
            rec_epoch = item.get("epoch")
            if not isinstance(rec_epoch, (int, float)):
                rec_epoch = _parse_iso_to_epoch(str(item.get("ts", "")))
            if rec_epoch is not None and float(rec_epoch) < cutoff_epoch:  # type: ignore[operator]
                return False
            return True

        return read_log_file_jsonl(path, limit=limit, filter_fn=_time_filter)
    except Exception:
        return []
