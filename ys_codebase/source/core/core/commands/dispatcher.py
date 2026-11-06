"""
Core Commands - CLI Pipeline Dispatcher & Dual-Track Router.
100% Python Standard Library. Zero Third-Party Dependencies.
"""
import difflib
import errno
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.commands.bags import CmdBags
from core.commands.help import HelpRenderer
from core.commands.registry import CommandSpec, CommandsRegistry
from core.commands.resolver import (
    OptionResolutionError,
    OptionResolver,
)
from core.platform import InterProcessLock, can_spawn_background_daemon, daemon_probe, is_process_alive, spawn_detached
from core.telemetry import extract_error_hint, record_cli_event

# 快取已載入之 Contributes Registry
_GLOBAL_REGISTRY: Optional[CommandsRegistry] = None
_GLOBAL_REGISTRY_ROOT: Optional[str] = None
_MODULE_CACHE: Dict[str, Any] = {}
_AUTO_SPAWN_WARNED: bool = False
_LAST_DISPATCH_ERROR_HINT: str = ""
# strict 模式 auto-spawn 後等待 daemon 活躍之上限秒數
_STRICT_SPAWN_WAIT_SEC: float = 10.0


def _safe_getcwd() -> str:
    """安全取得當前工作目錄，若目錄已被刪除則回傳空字串。"""
    try:
        return os.getcwd()
    except OSError:
        return ""


def clear_cache() -> None:
    """清空已快取之 CommandsRegistry 與 CLI 模組快取。"""
    global _GLOBAL_REGISTRY, _GLOBAL_REGISTRY_ROOT
    _GLOBAL_REGISTRY = None
    _GLOBAL_REGISTRY_ROOT = None
    _MODULE_CACHE.clear()

# 環境與模組生命週期變異指令（執行前禁止自動拉起背景 Server，防範解壓/重載中途引發重啟風暴）
_LIFECYCLE_MUTATION_COMMANDS = {
    "install",
    "update",
    "remove",
    "reload",
    "restore",
    "rollback",
    "bootstrap",
    "init",
    "self-update",
}


def _get_yscb_root() -> Tuple[str, str]:
    """取得工作區根目錄與 yscb 根目錄，統一委派至 core.uri 尋根入口。"""
    from core import uri
    try:
        return uri._get_host_config()
    except Exception:
        host_dir = uri.get_host_dir() or _safe_getcwd()
        return host_dir, uri.resolve_yscb_root()


def _load_registry(yscb_abs: str) -> CommandsRegistry:
    """聚合工作區所有模組之 contributes/core.json 或 contributes/*.json。"""
    global _GLOBAL_REGISTRY, _GLOBAL_REGISTRY_ROOT
    norm_root = os.path.normcase(os.path.abspath(yscb_abs)) if yscb_abs else ""
    if _GLOBAL_REGISTRY is not None and _GLOBAL_REGISTRY_ROOT == norm_root:
        return _GLOBAL_REGISTRY

    registry = CommandsRegistry()

    # =========================================================================
    # [!] 剛性架構約束 (Rigid Architectural Guardrail) - 嚴禁擅自改動！
    # 本專案嚴格遵循：虛擬機測試 (dev test) -> install @build -> 實機測試 流程。
    # 僅允許 .modules 運行時空間載入 contributes，嚴禁直接運行或掃描開發環境 (source/) 程式碼。
    # 絕對禁止對此邏輯進行任何 fallback 或加入 source/ 空間之刪改！
    # =========================================================================
    modules_dir = os.path.join(yscb_abs, ".modules")
    if os.path.isdir(modules_dir):
        for mod_name in sorted(os.listdir(modules_dir), key=lambda m: (0 if m == "core" else 1, m)):
            if mod_name.startswith("."):
                continue
            mod_path = os.path.join(modules_dir, mod_name)
            if not os.path.isdir(mod_path):
                continue

            contrib_dir = os.path.join(mod_path, "contributes")
            if not os.path.isdir(contrib_dir):
                continue

            # 搜尋 core.json 或 commands.json
            for cfile in ("core.json", "commands.json"):
                cpath = os.path.join(contrib_dir, cfile)
                if os.path.isfile(cpath):
                    try:
                        with open(cpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if "commands" in data and isinstance(data["commands"], dict):
                                registry.register_module(mod_name, data["commands"])
                                break
                    except ValueError as err:
                        print(f"[yscb:registry] Warning: {err}", file=sys.stderr)
                    except Exception:
                        pass

    _GLOBAL_REGISTRY = registry
    _GLOBAL_REGISTRY_ROOT = norm_root
    return registry


def _suggest_command(unknown_cmd: str, candidate_pool: List[str]) -> Optional[str]:
    """模糊拼寫比寫演算法。"""
    matches = difflib.get_close_matches(unknown_cmd, candidate_pool, n=1, cutoff=0.5)
    return matches[0] if matches else None


@dataclass(frozen=True)
class _HotDispatchResult:
    """
    熱派發嘗試結果。

    exit_code: 取得 task_finish 時之退出碼；未完成則為 None。
    accepted: 請求是否已送達並被 Server 接受（已開始串流）。為 True 而 exit_code 為 None 表示
              「送出後失敗」（讀取逾時、連線重置、被搶占等），此時重試可能導致重複執行。
    """
    exit_code: Optional[int]
    accepted: bool


_ORIGINAL_URLOPEN = urllib.request.urlopen


def _open_localhost_no_proxy(req: urllib.request.Request, timeout: float) -> Any:
    """透過無代理 Opener 發送 Localhost 請求；若測試已替換 urlopen 則委派予 urlopen。"""
    if urllib.request.urlopen is not _ORIGINAL_URLOPEN:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def _hot_dispatch_attempt(module_name: str, cmd_path_or_name: Any, args: List[str], yscb_abs: str) -> _HotDispatchResult:
    """
    管道 B 單次嘗試：透過 Localhost HTTP 將 server_compatible 指令熱派發至常駐 Server Worker。

    區分「請求未被接受」（無/過期 daemon.json、連線拒絕、送出前之 HTTP 錯誤）與「送出後失敗」，
    供 strict 模式判斷是否可安全重試。
    """
    state_file = os.path.join(yscb_abs, ".cache", "server", "daemon.json")
    if not os.path.isfile(state_file):
        return _HotDispatchResult(None, False)

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return _HotDispatchResult(None, False)
    pid = state.get("pid") if isinstance(state, dict) else None
    if not pid or not is_process_alive(pid):
        try:
            os.remove(state_file)
        except OSError:
            pass
        return _HotDispatchResult(None, False)

    port, token = state.get("port"), state.get("token")
    url = f"http://127.0.0.1:{port}/api/dispatch"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    dispatch_args = list(cmd_path_or_name) if isinstance(cmd_path_or_name, (list, tuple)) else [cmd_path_or_name]
    payload = {
        "module": module_name,
        "args": dispatch_args + list(args),
        "cwd": _safe_getcwd(),
        "yscb_root": state.get("root", yscb_abs),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    captured_err: List[str] = []
    try:
        timeout_sec = float(os.environ.get("YSCB_DISPATCH_TIMEOUT", "120.0"))
    except (TypeError, ValueError):
        timeout_sec = 120.0
    try:
        resp = _open_localhost_no_proxy(req, timeout=timeout_sec)
    except urllib.error.HTTPError:
        # Server 於串流前即拒絕（鑑權失敗、根目錄不符等），任務未執行
        return _HotDispatchResult(None, False)
    except urllib.error.URLError as err:
        # 連線階段失敗（拒絕連線、無法解析）任務未送達；若為逾時或連線重置/中斷則視為已送達
        accepted_err = isinstance(
            err.reason,
            (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError),
        )
        unreachable = isinstance(err.reason, OSError) and not accepted_err
        return _HotDispatchResult(None, not unreachable)
    except ConnectionRefusedError:
        return _HotDispatchResult(None, False)
    except OSError as err:
        if not isinstance(err, (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)) and (
            "refused" in str(err).lower() or getattr(err, "errno", None) == errno.ECONNREFUSED
        ):
            return _HotDispatchResult(None, False)
        return _HotDispatchResult(None, True)
    except Exception:
        # 請求可能已送出（逾時、重置），保守視為已接受
        return _HotDispatchResult(None, True)

    try:
        with resp:
            buf = ""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if not line.strip():
                        continue
                    pkt = json.loads(line)
                    if pkt.get("type") == "terminal_stream":
                        text_chunk = pkt.get("text", "")
                        out = sys.stderr if pkt.get("stream") == "stderr" else sys.stdout
                        out.write(text_chunk)
                        out.flush()
                        if len(captured_err) < 8 and (
                            pkt.get("stream") == "stderr"
                            or any(k in text_chunk for k in ("Error", "[FAIL]", "[BLOCKER]"))
                        ):
                            captured_err.append(text_chunk)
                    elif pkt.get("type") == "task_finish":
                        rc = pkt.get("exit_code", 0)
                        err_field = pkt.get("error")
                        if rc != 0 and err_field:
                            # Surface server-side failures (e.g. worker preempted) instead of failing silently
                            err_line = f"[yscb] Error: {err_field}\n"
                            sys.stderr.write(err_line)
                            sys.stderr.flush()
                            captured_err.append(err_line)
                        global _LAST_DISPATCH_ERROR_HINT
                        _LAST_DISPATCH_ERROR_HINT = extract_error_hint("".join(captured_err)) if rc != 0 else ""
                        return _HotDispatchResult(rc, True)
    except Exception:
        # 串流中途失敗：任務已送達，結果不明
        return _HotDispatchResult(None, True)
    # 串流結束卻無 task_finish：任務已送達，結果不明
    return _HotDispatchResult(None, True)


def _try_hot_dispatch(module_name: str, cmd_path_or_name: Any, args: List[str], yscb_abs: str) -> Optional[int]:
    """
    管道 B（非嚴格模式）：熱派發並回傳退出碼；僅當請求尚未被 Server 接受（not res.accepted）時返回 None 降級冷派發，
    若請求已被接受（res.accepted 為 True）但中途逾時或斷線未取得 task_finish，直接回傳 1 以防止重複執行。
    支援 cmd_path_or_name 為 List[str] 或單一 str。
    """
    res = _hot_dispatch_attempt(module_name, cmd_path_or_name, args, yscb_abs)
    if not res.accepted:
        return None
    if res.exit_code is not None:
        return res.exit_code
    err_msg = (
        "[yscb] Error: hot_dispatch: request was delivered to the server but failed before completion "
        "(timeout / connection reset / worker restarted). Not falling back to cold dispatch to avoid double execution."
    )
    global _LAST_DISPATCH_ERROR_HINT
    _LAST_DISPATCH_ERROR_HINT = err_msg
    return 1


def _is_server_daemon_active_or_locked(yscb_abs: str) -> bool:
    """檢查常駐 Server daemon.json 或啟動期 daemon.lock 是否已活躍。"""
    state_file = os.path.join(yscb_abs, ".cache", "server", "daemon.json")
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                st = json.load(f)
            pid = st.get("pid")
            if pid:
                if is_process_alive(pid):
                    return True
                try:
                    os.remove(state_file)
                except OSError:
                    pass
        except Exception:
            return True

    lock_file = os.path.join(yscb_abs, ".cache", "server", "daemon.lock")
    if os.path.isfile(lock_file):
        try:
            probe_lock = InterProcessLock(lock_file)
            if not probe_lock.acquire(blocking=False):
                return True
            probe_lock.release()
        except Exception:
            pass
    return False


@dataclass(frozen=True)
class _ServerSpawnConfig:
    """dispatcher 所需之 server 組態快照（core 不得 import server.config，故直讀 JSON）。"""
    enabled: bool
    auto_spawn: bool
    strict_hot_dispatch: bool


def _read_server_spawn_config(yscb_abs: str) -> _ServerSpawnConfig:
    """依序讀取 project (config/) 與 local (.config.local/) 雙層組態之 enable / auto_spawn / strict_hot_dispatch。"""
    values: Dict[str, bool] = {"enable": True, "auto_spawn": True, "strict_hot_dispatch": False}
    proj_cfg_file = os.path.join(yscb_abs, "config", "server", "config.project.json")
    local_cfg_file = os.path.join(yscb_abs, ".config.local", "server", "config.local.json")

    for cfg_file in (proj_cfg_file, local_cfg_file):
        if os.path.isfile(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    if not isinstance(cfg_data, dict):
                        continue
                    for key in values:
                        if key in cfg_data:
                            values[key] = bool(cfg_data[key])
            except Exception:
                pass
    return _ServerSpawnConfig(
        enabled=values["enable"],
        auto_spawn=values["auto_spawn"],
        strict_hot_dispatch=values["strict_hot_dispatch"],
    )


def _print_agent_daemon_blocker(strict: bool = False) -> None:
    """
    輸出 Server 常駐不可用時之 Agent 指引。

    Args:
        strict: False 為 advisory 文案（本次以冷派發兜底，exit code 不變）；
                True 為 strict 文案（strict_hot_dispatch 已阻斷本次執行，回傳 1）。
    """
    if strict:
        status_line = (
            "[*] 狀態備註: strict_hot_dispatch=true，本指令僅允許熱派發，已阻斷執行 (exit 1)，未進行冷派發！\n"
        )
    else:
        status_line = (
            "[*] 狀態備註: 常駐 Server 不可用（環境不支援背景常駐或已被回收），本次已以本地冷派發兜底完成，嚴禁擅改專案組態！\n"
        )
    msg = (
        "\n"
        "================================================================================\n"
        "[BLOCKER] YSCB SERVER DAEMON MANDATORY ACTION REQUIRED FOR AGENTS\n"
        "================================================================================\n"
        "[!] 嚴格阻斷約束 (STRICT AGENT BLOCKER):\n"
        "    你必須立即暫停推進手頭上的業務任務！\n"
        "    在完成以下【步驟 1】或【步驟 2】之前，【嚴禁】略過此提示繼續執行後續指令！\n\n"
        "[!] 強制執行程序 (MANDATORY DIRECTIVES):\n"
        "    [1] 步驟 1 (立即執行):\n"
        "        調用終端工具以【背景/常駐模式】(Background/Daemon task) 啟動 Server：\n"
        "        $ python yscb.py server start --console\n\n"
        "    [2] 步驟 2 (異常請示):\n"
        "        若當前環境不支援常駐進程導致啟動失敗，請立即向開發者回報並請示處置方案：\n"
        "        - 方案 A: 由開發者在外部獨立終端手動啟動 server\n"
        "        - 方案 B: 維持純冷派發，由開發者評估關閉 auto_spawn / strict_hot_dispatch\n"
        "        - 方案 C: (不推薦) 授權 Agent 暫時忽略常駐警示，以冷派發繼續作業\n"
        "        (誤判可常駐時，開發者可設定環境變數 YSCB_FORCE_DAEMON=1 強制允許背景常駐)\n\n"
        + status_line
        + "================================================================================\n\n"
    )
    try:
        sys.stderr.write(msg)
        sys.stderr.flush()
    except Exception:
        pass


def _spawn_server_daemon(host_dir: str, yscb_abs: str) -> Optional[int]:
    """以脫鉤背景進程拉起 Server 並記錄 spawn 探針；失敗回傳 None。"""
    yscb_py = os.path.join(host_dir, "yscb.py")
    if not os.path.isfile(yscb_py):
        yscb_py = sys.argv[0]
    try:
        pid = spawn_detached(
            [sys.executable, yscb_py, "server", "start", "--daemon"],
            cwd=host_dir,
        )
    except OSError as err:
        if os.environ.get("YSCB_VERBOSE") == "1" or os.environ.get("YSCB_DEBUG") == "1":
            print(f"[core:dispatcher] Warning: Failed to auto-spawn server daemon: {err}", file=sys.stderr)
        return None
    daemon_probe.record_spawn(yscb_abs, pid)
    return pid


def _warn_daemon_unavailable_once(strict: bool = False) -> None:
    """每進程僅輸出一次 [BLOCKER]（strict 文案則每次阻斷皆輸出）。"""
    global _AUTO_SPAWN_WARNED
    if strict:
        _AUTO_SPAWN_WARNED = True
        _print_agent_daemon_blocker(strict=True)
        return
    if not _AUTO_SPAWN_WARNED:
        _AUTO_SPAWN_WARNED = True
        _print_agent_daemon_blocker(strict=False)


def _maybe_auto_spawn_server(host_dir: str, yscb_abs: str) -> None:
    """
    在背景非同步按需拉起 Server 守護進程。
    僅在 server 模組存在、非 server/dev 指令、非測試環境、且 config/server/config.project.json enable != false 時觸發。
    當偵測到環境無開立背景守護進程權限（含實證回收偵測）時，輸出一次 advisory [BLOCKER] 並照常冷派發（exit code 不變）。
    """
    if os.environ.get("YSCB_TESTING") == "1" or os.environ.get("YSCB_TEST_SANDBOX") == "1":
        return

    if _is_server_daemon_active_or_locked(yscb_abs):
        return

    # [!] 剛性架構約束：僅允許 .modules 運行時空間，禁止任何 fallback
    if not os.path.isdir(os.path.join(yscb_abs, ".modules", "server")):
        return

    cfg = _read_server_spawn_config(yscb_abs)
    if not cfg.enabled or not cfg.auto_spawn:
        return

    if not can_spawn_background_daemon(yscb_root=yscb_abs):
        _warn_daemon_unavailable_once(strict=False)
        return

    _spawn_server_daemon(host_dir, yscb_abs)


def _strict_hot_dispatch_or_block(
    module_name: str,
    cmd_path: List[str],
    sub_args: List[str],
    host_dir: str,
    yscb_abs: str,
) -> int:
    """
    strict_hot_dispatch 模式之熱派發（含首次嘗試），絕不冷派發。

    1. 首次熱派發成功即回傳退出碼。
    2. 請求已送達但送出後失敗（逾時、重置、被搶占）→ 不重試（防重複執行），回傳 1。
    3. Server 不可達且可常駐、auto_spawn=true → auto-spawn 並等待 daemon 活躍（≤ _STRICT_SPAWN_WAIT_SEC）
       後重試一次；重試結果同上規則判定。
    4. 仍不可達 → 輸出 strict [BLOCKER] 並回傳 1。
    """
    global _LAST_DISPATCH_ERROR_HINT
    result = _hot_dispatch_attempt(module_name, cmd_path, sub_args, yscb_abs)
    if result.exit_code is None and not result.accepted:
        cfg = _read_server_spawn_config(yscb_abs)
        can_spawn = (
            cfg.auto_spawn
            and os.path.isdir(os.path.join(yscb_abs, ".modules", "server"))
            and can_spawn_background_daemon(yscb_root=yscb_abs)
        )
        if can_spawn:
            if not _is_server_daemon_active_or_locked(yscb_abs):
                _spawn_server_daemon(host_dir, yscb_abs)
            state_file = os.path.join(yscb_abs, ".cache", "server", "daemon.json")
            deadline = time.time() + _STRICT_SPAWN_WAIT_SEC
            while time.time() < deadline:
                if os.path.isfile(state_file):
                    result = _hot_dispatch_attempt(module_name, cmd_path, sub_args, yscb_abs)
                    if result.accepted or result.exit_code is not None:
                        break
                time.sleep(0.2)

    if result.exit_code is not None:
        return result.exit_code

    if result.accepted:
        err_msg = (
            "[yscb] Error: strict_hot_dispatch: request was delivered to the server but failed before completion "
            "(timeout / connection reset / worker restarted). Not retried to avoid double execution; "
            "check 'server status' and the server log, then re-run if appropriate."
        )
        _LAST_DISPATCH_ERROR_HINT = err_msg
        print(err_msg, file=sys.stderr)
        return 1

    _LAST_DISPATCH_ERROR_HINT = "[BLOCKER] strict_hot_dispatch: server daemon unavailable, cold dispatch blocked"
    _warn_daemon_unavailable_once(strict=True)
    return 1


def _find_module_cli(module_name: str, yscb_abs: str) -> Optional[str]:
    """
    定位目標模組之 scripts/cli.py。
    [!] 剛性架構約束：僅允許 .modules 運行時空間，嚴禁直接運行開發環境 (source/) 程式碼，禁止任何 fallback。
    """
    target = os.path.join(yscb_abs, ".modules", module_name, "scripts", "cli.py")
    if os.path.isfile(target):
        return os.path.normpath(target)
    return None


def _ensure_hooks(hook_name: str, verbose: Optional[bool] = None) -> Dict[str, Any]:
    """觸發對稱生命週期 Hook。"""
    is_verbose = (
        verbose
        if verbose is not None
        else (
            os.environ.get("YSCB_VERBOSE") == "1"
            or os.environ.get("YSCB_DEBUG") == "1"
            or "--verbose" in sys.argv
            or "--debug" in sys.argv
        )
    )
    try:
        from core import events
        res = events.broadcast(hook_name, emit_module="core", verbose=is_verbose)
        if is_verbose and res:
            print(f"[core:dispatcher] Hooks for '{hook_name}' completed: {res}", file=sys.stderr)
        return res
    except Exception as e:
        if is_verbose:
            import traceback
            print(f"[core:dispatcher] Warning: Failed to trigger hook '{hook_name}': {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        return {}


def dispatch_local(
    module_name: str,
    cmd_name: Any,
    raw_args: List[str],
    cmd_spec: Optional[CommandSpec],
    yscb_abs: str,
) -> int:
    """
    本地冷派發執行體。
    負責：
    1. 觸發 pre_cli_dispatch Hook
    2. OptionResolver 解析參數與互斥檢查
    3. 載入目標模組 scripts/cli.py
    4. 調用精確命令函式
    5. 觸發 post_cli_dispatch Hook（頂層 try...finally 對稱保證）
    """
    is_verbose = (
        os.environ.get("YSCB_VERBOSE") == "1"
        or os.environ.get("YSCB_DEBUG") == "1"
        or any(arg in ("--verbose", "--debug") for arg in raw_args)
    )
    _ensure_hooks("pre_cli_dispatch", verbose=is_verbose)
    try:
        if isinstance(cmd_name, list):
            cmd_path = [str(c) for c in cmd_name]
        elif isinstance(cmd_name, str):
            cmd_path = cmd_name.split() if " " in cmd_name else [cmd_name]
        else:
            cmd_path = []

        func_name = "_".join(cmd_path).replace("-", "_") if cmd_path else "default"
        primary_cmd = cmd_path[0] if cmd_path else ""

        # 參數解析
        global _LAST_DISPATCH_ERROR_HINT
        _LAST_DISPATCH_ERROR_HINT = ""
        try:
            positional_args, resolved_options = OptionResolver.resolve(cmd_spec, raw_args)
        except OptionResolutionError as err:
            err_msg = f"[yscb] Error: {err}"
            _LAST_DISPATCH_ERROR_HINT = err_msg
            print(err_msg)
            return 1

        raw_cmd_str = " ".join(cmd_path + raw_args) if (cmd_path or raw_args) else ""
        cmd_bags = CmdBags(
            raw_cmd=raw_cmd_str,
            command=func_name,
            args=positional_args,
            options=resolved_options,
        )

        target_cli = _find_module_cli(module_name, yscb_abs)
        if not target_cli:
            err_msg = f"[yscb] Error: Cannot find CLI entrypoint for module '{module_name}'."
            _LAST_DISPATCH_ERROR_HINT = err_msg
            print(err_msg)
            return 1

        # =========================================================================
        # [!] 剛性架構約束 (Rigid Architectural Guardrail) - 嚴禁擅自改動！
        # 統一透過 core.platform.ensure_installed_modules_path 將所有已安裝 .modules/<mod>
        # 注入 sys.path（並將當前目標模組與 core 置於最前）。
        # 嚴禁直接運行開發環境 (source/) 程式碼，禁止在此向 sys.path 插入 source/ 空間！
        # =========================================================================
        from core.platform import ensure_installed_modules_path

        mod_root = os.path.dirname(os.path.dirname(target_cli))
        ensure_installed_modules_path(
            yscb_root=yscb_abs,
            priority_module=module_name,
            extra_paths=[mod_root] if os.path.isdir(mod_root) else None,
        )

        # 載入模組
        if target_cli in _MODULE_CACHE:
            mod = _MODULE_CACHE[target_cli]
        else:
            mod_pkg = module_name.replace("-", "_")
            script_stem = os.path.splitext(os.path.basename(target_cli))[0].replace(".", "_")
            unique_mod_name = f"_yscb_mod_{mod_pkg}_{script_stem}"
            spec = importlib.util.spec_from_file_location(
                unique_mod_name,
                target_cli,
            )
            if spec is None or spec.loader is None:
                print(f"[yscb] Error: Cannot load spec for '{target_cli}'.")
                return 1
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception as load_err:
                # 載入期例外（含 SyntaxError）移除半初始化模組並回傳 1
                sys.modules.pop(spec.name, None)
                err_msg = f"[yscb] Error loading CLI for '{module_name}': {type(load_err).__name__}: {load_err}"
                _LAST_DISPATCH_ERROR_HINT = err_msg
                print(err_msg)
                return 1
            _MODULE_CACHE[target_cli] = mod

        exit_code = 0
        orig_argv = list(sys.argv)
        try:
            sys.argv = [target_cli] + raw_args

            # 優先尋找階層下劃線精確函式 (如 uri_list)
            fn = getattr(mod, func_name, None)
            if not callable(fn) and len(cmd_path) > 1:
                # 檢查頂層函式 (例如 cli.uri，若其能自行處理 sub_cmd)
                top_fn = getattr(mod, primary_cmd, None)
                if callable(top_fn):
                    combined_args = cmd_path[1:] + positional_args
                    sub_bags = CmdBags(raw_cmd=raw_cmd_str, command=primary_cmd, args=combined_args, options=resolved_options)
                    fn = lambda _: top_fn(sub_bags)

            if callable(fn):
                ret = fn(cmd_bags)
                exit_code = int(ret) if ret is not None else 0
            elif cmd_spec and cmd_spec.cmd:
                # 純分支且無自身函式，自動降級渲染子指令 Help
                disp_cmd = " ".join(cmd_path)
                print(HelpRenderer.render_cmd_help(module_name, disp_cmd, cmd_spec))
                exit_code = 0
            else:
                # 既無精確函式亦非純分支 (Hard Sunset: 徹底移除 process fallback)
                disp_cmd = " ".join(cmd_path)
                err_msg = (
                    f"[yscb] Error (EC-05): Module '{module_name}' CLI script does not define "
                    f"command function '{func_name}(cmd_bags)'."
                )
                _LAST_DISPATCH_ERROR_HINT = err_msg
                print(err_msg)
                return 127
        except SystemExit as se:
            exit_code = se.code if isinstance(se.code, int) else (0 if se.code is None else 1)
        except Exception as e:
            disp_cmd = " ".join(cmd_path)
            err_msg = f"[yscb] Error executing '{module_name} {disp_cmd}': {e}"
            _LAST_DISPATCH_ERROR_HINT = err_msg
            print(err_msg)
            exit_code = 1
        finally:
            sys.argv = orig_argv

        return exit_code
    finally:
        # 對稱觸發 post_cli_dispatch Hook
        _ensure_hooks("post_cli_dispatch", verbose=is_verbose)


def _maybe_check_and_print_updates() -> None:
    """於任意 CLI 指令執行完畢後觸發非阻塞 12 小時節流版本檢查與提示（含 yscb.py 入口檔自檢）。"""
    if os.environ.get("YSCB_TESTING") == "1" or os.environ.get("YSCB_TEST_SANDBOX") == "1":
        return
    try:
        from core.update_checker import UpdateChecker
        checker = UpdateChecker()
        checker.check_updates(force=False)
        checker.print_tips_if_available()
    except Exception:
        pass


def dispatch(argv: Optional[List[str]] = None) -> int:
    """
    核心命令引擎入口函式。
    統一攔截 argv，完成路由分流、--help 渲染、雙管道派發與精確調用。
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

    if argv is None:
        argv = sys.argv[1:]

    if "--verbose" in argv:
        os.environ["YSCB_VERBOSE"] = "1"
    if "--debug" in argv:
        os.environ["YSCB_DEBUG"] = "1"

    host_dir, yscb_abs = _get_yscb_root()
    if "YSCB_HOST_DIR" not in os.environ:
        os.environ["YSCB_HOST_DIR"] = host_dir
    if "YSCB_HOST_DISPATCH_TOKEN" not in os.environ:
        os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"

    t_start = time.perf_counter()
    registry = _load_registry(yscb_abs)

    # 1. 空參數或全域 --help
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(HelpRenderer.render_global_help(registry))
        return 0

    first_token = argv[0]
    rest_tokens = argv[1:]

    core_mod = registry.get_module("core")
    core_commands = set(core_mod.commands.keys()) if core_mod else {
        "install", "update", "remove", "list", "status",
        "rollback", "reload", "restore", "bootstrap", "uri", "config", "event",
        "contributes", "gitignore", "file-space", "fs",
    }

    # 2. 判斷是否為 core 的快捷指令 (例如 yscb status, yscb list, yscb fs)
    # 當頂層 first_token 未冠上 'core' 前綴，但同時與某個已安裝非 'core' 外部模組同名時（例如過渡期之 file-space），
    # 優先交由該外部模組處理，確保 yscb.py core file-space 與 yscb.py fs 直通 core 且舊模組零衝突。
    resolved_non_core_mod = registry.resolve_module_name(first_token)
    if resolved_non_core_mod is None and first_token != "core" and _find_module_cli(first_token, yscb_abs):
        resolved_non_core_mod = first_token

    if first_token in core_commands and resolved_non_core_mod in (None, "core"):
        module_name = "core"
        target_tokens = argv
    elif first_token == "core":
        module_name = "core"
        target_tokens = rest_tokens
    else:
        # 3. 模組名稱或模組別名
        resolved_mod = resolved_non_core_mod or registry.resolve_module_name(first_token)
        if resolved_mod is not None:
            module_name = resolved_mod
            target_tokens = rest_tokens
        else:
            # 檢查是否為未在 registry 宣告但存在於檔案系統的模組
            cli_candidate = _find_module_cli(first_token, yscb_abs)
            if cli_candidate:
                module_name = first_token
                target_tokens = rest_tokens
            else:
                # 未知模組或未知指令，模糊拼寫比對
                all_candidates = list(core_commands) + registry.list_modules()
                sugg = _suggest_command(first_token, all_candidates)
                err_msg = f"[yscb] Error: Unknown command or module '{first_token}'."
                print(err_msg)
                if sugg:
                    print(f"       Did you mean '{sugg}'?")
                print("       Run 'python yscb.py --help' for available commands.")
                record_cli_event(
                    module_name=first_token,
                    cmd_path=[],
                    args=rest_tokens,
                    exit_code=1,
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    mode="router_err",
                    error_hint=err_msg + (f" Did you mean '{sugg}'?" if sugg else ""),
                    yscb_abs=yscb_abs,
                )
                return 1

    # 4. 模組級 --help 攔截
    mod_spec = registry.get_module(module_name)
    if not target_tokens or target_tokens[0] in ("-h", "--help", "help"):
        if mod_spec:
            print(HelpRenderer.render_module_help(module_name, mod_spec))
        else:
            print(f"YS-Codebase Module: {module_name}\n(Run 'python yscb.py {module_name} --help' for options)")
        return 0

    # 5. 沿 target_tokens 走訪指令樹
    cmd_path, cmd_spec, sub_args = registry.resolve_command_path(module_name, target_tokens)

    if not cmd_path:
        unknown_token = target_tokens[0]
        cand_list = list(mod_spec.commands.keys()) if (mod_spec and mod_spec.commands) else []
        sugg = _suggest_command(unknown_token, cand_list)
        err_msg = f"[yscb] Error: Unknown command '{unknown_token}' for module '{module_name}'."
        print(err_msg)
        if sugg:
            print(f"       Did you mean '{sugg}'?")
        print(f"       Run 'python yscb.py {module_name} --help' for available commands.")
        record_cli_event(
            module_name=module_name,
            cmd_path=[unknown_token],
            args=target_tokens[1:],
            exit_code=1,
            duration_ms=(time.perf_counter() - t_start) * 1000.0,
            mode="router_err",
            error_hint=err_msg + (f" Did you mean '{sugg}'?" if sugg else ""),
            yscb_abs=yscb_abs,
        )
        return 1

    cmd_disp_name = " ".join(cmd_path)

    # 6. 指令級 --help 攔截
    if any(a in ("-h", "--help", "help") for a in sub_args):
        if cmd_spec:
            print(HelpRenderer.render_cmd_help(module_name, cmd_disp_name, cmd_spec))
            return 0
        elif mod_spec:
            print(HelpRenderer.render_module_help(module_name, mod_spec))
            return 0

    # 7. 純分支未接子指令檢查
    if cmd_spec and cmd_spec.cmd and not sub_args:
        target_cli = _find_module_cli(module_name, yscb_abs)
        has_fn = False
        if target_cli:
            func_name = "_".join(cmd_path).replace("-", "_")
            try:
                with open(target_cli, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if f"def {func_name}(" in content:
                        has_fn = True
            except Exception:
                pass
        if not has_fn:
            print(HelpRenderer.render_cmd_help(module_name, cmd_disp_name, cmd_spec))
            return 0

    # 8. 檢查未知子指令
    if cmd_spec and cmd_spec.cmd and not cmd_spec.args and sub_args and not sub_args[0].startswith("-"):
        bad_sub = sub_args[0]
        sugg = _suggest_command(bad_sub, list(cmd_spec.cmd.keys()))
        err_msg = f"[yscb] Error: Unknown subcommand '{bad_sub}' for command '{cmd_disp_name}'."
        print(err_msg)
        if sugg:
            print(f"       Did you mean '{sugg}'?")
        print(f"       Run 'python yscb.py {module_name} {cmd_disp_name} --help' for available subcommands.")
        record_cli_event(
            module_name=module_name,
            cmd_path=cmd_path + [bad_sub],
            args=sub_args[1:],
            exit_code=1,
            duration_ms=(time.perf_counter() - t_start) * 1000.0,
            mode="router_err",
            error_hint=err_msg + (f" Did you mean '{sugg}'?" if sugg else ""),
            yscb_abs=yscb_abs,
        )
        return 1

    # 9. 指令級 server_compatible 雙管道分流
    if cmd_spec is not None and cmd_spec.server_compatible:
        spawn_cfg = _read_server_spawn_config(yscb_abs)
        if spawn_cfg.enabled and spawn_cfg.strict_hot_dispatch:
            # strict_hot_dispatch 啟用（且 server enable=true）時僅允許熱派發，禁止冷派發兜底
            hot_res: Optional[int] = _strict_hot_dispatch_or_block(module_name, cmd_path, sub_args, host_dir, yscb_abs)
        else:
            hot_res = _try_hot_dispatch(module_name, cmd_path, sub_args, yscb_abs)
        if hot_res is not None:
            record_cli_event(
                module_name=module_name,
                cmd_path=cmd_path,
                args=sub_args,
                exit_code=hot_res,
                duration_ms=(time.perf_counter() - t_start) * 1000.0,
                mode="hot",
                error_hint=_LAST_DISPATCH_ERROR_HINT if hot_res != 0 else "",
                yscb_abs=yscb_abs,
            )
            _maybe_check_and_print_updates()
            return hot_res
        # 熱派發通訊失敗或常駐離線，透明降級至本地冷派發

    # 非 server / dev 指令且非 core 生命週期變異指令時，在背景按需喚醒 Server 常駐進程
    primary_cmd_token = cmd_path[0] if cmd_path else ""
    if module_name not in ("server", "dev") and not (
        module_name == "core" and primary_cmd_token in _LIFECYCLE_MUTATION_COMMANDS
    ):
        _maybe_auto_spawn_server(host_dir, yscb_abs)

    # 10. 本地冷派發執行
    ret = dispatch_local(
        module_name=module_name,
        cmd_name=cmd_path,
        raw_args=sub_args,
        cmd_spec=cmd_spec,
        yscb_abs=yscb_abs,
    )
    record_cli_event(
        module_name=module_name,
        cmd_path=cmd_path,
        args=sub_args,
        exit_code=ret,
        duration_ms=(time.perf_counter() - t_start) * 1000.0,
        mode="local",
        error_hint=_LAST_DISPATCH_ERROR_HINT if ret != 0 else "",
        yscb_abs=yscb_abs,
    )
    _maybe_check_and_print_updates()
    return ret
