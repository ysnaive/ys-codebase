"""
Core Telemetry - Lightweight CLI Execution Flight Recorder.
100% Python Standard Library. Zero Upper-Layer Coupling.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

MAX_TELEMETRY_BYTES: int = 512 * 1024
KEEP_TELEMETRY_LINES: int = 1500


def _discover_yscb_root(yscb_abs: Optional[str] = None) -> Path:
    """探索 yscb 根目錄路徑。"""
    if yscb_abs:
        return Path(yscb_abs).resolve()
    try:
        from core import uri
        root_str = uri._get_yscb_root()
        if root_str:
            return Path(root_str).resolve()
    except Exception:
        pass

    host_dir = os.environ.get("YSCB_HOST_DIR", os.getcwd())
    cfg_path = os.path.join(host_dir, "yscb.config.json")
    yscb_rel = "."
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                yscb_rel = data.get("yscb_root", ".")
        except Exception:
            pass
    return Path(os.path.normpath(os.path.join(host_dir, yscb_rel))).resolve()


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


def extract_error_hint(text: str, max_len: int = 200) -> str:
    """自終端輸出或錯誤訊息中擷取最具代表性之單行報錯摘要。"""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    priority_keywords = ("[error]", "error:", "[fail]", "[blocker]", "exception", "traceback")
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in priority_keywords):
            return ln[:max_len]
    return lines[0][:max_len]


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
        target_path.parent.mkdir(parents=True, exist_ok=True)

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
            "cwd": str(cwd or os.getcwd()),
            "error_hint": extract_error_hint(error_hint, max_len=200),
        }

        line_str = json.dumps(record, ensure_ascii=False) + "\n"
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(line_str)

        if max_bytes > 0 and target_path.exists() and target_path.stat().st_size > max_bytes:
            _rotate_telemetry_file(target_path, keep_lines=keep_lines)

        return True
    except Exception:
        return False


def _rotate_telemetry_file(target_path: Path, keep_lines: int = KEEP_TELEMETRY_LINES) -> None:
    """滾動截斷 telemetry.jsonl，僅保留最後 keep_lines 筆有效 JSONL。"""
    try:
        raw_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
        valid_lines: List[str] = []
        for ln in raw_lines:
            s = ln.strip()
            if not s:
                continue
            try:
                json.loads(s)
                valid_lines.append(s)
            except Exception:
                continue

        kept = valid_lines[-max(1, keep_lines):]
        tmp_path = target_path.with_suffix(f".tmp.{os.getpid()}")
        tmp_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        os.replace(str(tmp_path), str(target_path))
    except Exception:
        pass


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

        records: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    item = json.loads(s)
                    if not isinstance(item, dict):
                        continue
                except Exception:
                    continue

                if cutoff_epoch is not None:
                    rec_epoch = item.get("epoch")
                    if not isinstance(rec_epoch, (int, float)):
                        rec_epoch = _parse_iso_to_epoch(str(item.get("ts", "")))
                    if rec_epoch is not None and float(rec_epoch) < cutoff_epoch:
                        continue

                records.append(item)

        if limit is not None and limit > 0 and len(records) > limit:
            records = records[-limit:]
        return records
    except Exception:
        return []

