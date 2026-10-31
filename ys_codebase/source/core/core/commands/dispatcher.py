"""
Core Commands - CLI Pipeline Dispatcher & Dual-Track Router.
100% Python Standard Library. Zero Third-Party Dependencies.
"""
import difflib
import importlib.util
import json
import os
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from core.commands.bags import CmdBags
from core.commands.help import HelpRenderer
from core.commands.registry import CommandSpec, CommandsRegistry
from core.commands.resolver import (
    OptionResolutionError,
    OptionResolver,
)
from core.platform import InterProcessLock, can_spawn_background_daemon, is_process_alive, spawn_detached
from core.telemetry import extract_error_hint, record_cli_event

# 快取已載入之 Contributes Registry
_GLOBAL_REGISTRY: Optional[CommandsRegistry] = None
_MODULE_CACHE: Dict[str, Any] = {}
_AUTO_SPAWN_WARNED: bool = False
_LAST_DISPATCH_ERROR_HINT: str = ""

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
        host_dir = uri.get_host_dir() or os.getcwd()
        return host_dir, uri.resolve_yscb_root()


def _load_registry(yscb_abs: str) -> CommandsRegistry:
    """聚合工作區所有模組之 contributes/core.json 或 contributes/*.json。"""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is not None:
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
        for mod_name in os.listdir(modules_dir):
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
                    except Exception:
                        pass

    _GLOBAL_REGISTRY = registry
    return registry


def _suggest_command(unknown_cmd: str, candidate_pool: List[str]) -> Optional[str]:
    """模糊拼寫比對演算法。"""
    matches = difflib.get_close_matches(unknown_cmd, candidate_pool, n=1, cutoff=0.5)
    return matches[0] if matches else None


def _try_hot_dispatch(module_name: str, cmd_path_or_name: Any, args: List[str], yscb_abs: str) -> Optional[int]:
    """
    管道 B：透過 Localhost HTTP 將 server_compatible 指令熱派發至常駐 Server Worker。
    若連線超時或失敗則返回 None，自動降級為本地冷派發。
    支援 cmd_path_or_name 為 List[str] 或單一 str。
    """
    state_file = os.path.join(yscb_abs, ".cache", "server", "daemon.json")
    if not os.path.isfile(state_file):
        return None

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        pid = state.get("pid")
        if not pid or not is_process_alive(pid):
            try:
                os.remove(state_file)
            except OSError:
                pass
            return None

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
            "cwd": os.getcwd(),
            "yscb_root": state.get("root", yscb_abs),
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        exit_code = 0
        captured_err: List[str] = []
        timeout_sec = float(os.environ.get("YSCB_DISPATCH_TIMEOUT", "120.0"))
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
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
                        global _LAST_DISPATCH_ERROR_HINT
                        _LAST_DISPATCH_ERROR_HINT = extract_error_hint("".join(captured_err)) if rc != 0 else ""
                        return rc
        return exit_code
    except Exception:
        # EC-04: 熱派發通訊異常時透明降級
        return None


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


def _read_server_spawn_config(yscb_abs: str) -> Tuple[bool, bool]:
    """依序讀取 project 與 local 雙層組態之 (enabled, auto_spawn)。"""
    auto_spawn = True
    enabled = True
    proj_cfg_file = os.path.join(yscb_abs, "config", "server", "config.project.json")
    local_cfg_file = os.path.join(yscb_abs, "config", "server", "config.local.json")

    for cfg_file in (proj_cfg_file, local_cfg_file):
        if os.path.isfile(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    if not isinstance(cfg_data, dict):
                        continue
                    if "enable" in cfg_data:
                        enabled = bool(cfg_data["enable"])
                    if "auto_spawn" in cfg_data:
                        auto_spawn = bool(cfg_data["auto_spawn"])
            except Exception:
                pass
    return enabled, auto_spawn


def _print_agent_daemon_blocker() -> None:
    """輸出沙盒受限環境下之 Agent 常駐啟動強制指引。"""
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
        "        - 方案 B: 維持純冷派發，由開發者評估關閉 auto_spawn\n"
        "        - 方案 C: (不推薦) 授權 Agent 暫時忽略常駐警示，以冷派發繼續作業\n\n"
        "[*] 狀態備註: 沙盒環境背景脫鉤受限，當前以本地冷派發臨時兜底，嚴禁擅改專案組態！\n"
        "================================================================================\n\n"
    )
    try:
        sys.stderr.write(msg)
        sys.stderr.flush()
    except Exception:
        pass


def _maybe_auto_spawn_server(host_dir: str, yscb_abs: str) -> None:
    """
    在背景非同步按需拉起 Server 守護進程。
    僅在 server 模組存在、非 server/dev 指令、非測試環境、且 config/server/config.project.json enable != false 時觸發。
    當偵測到環境無開立背景守護進程權限時，自動降級並輸出提示。
    """
    global _AUTO_SPAWN_WARNED

    if os.environ.get("YSCB_TESTING") == "1" or os.environ.get("YSCB_TEST_SANDBOX") == "1":
        return

    if _is_server_daemon_active_or_locked(yscb_abs):
        return

    # [!] 剛性架構約束：僅允許 .modules 運行時空間，禁止任何 fallback
    if not os.path.isdir(os.path.join(yscb_abs, ".modules", "server")):
        return

    enabled, auto_spawn = _read_server_spawn_config(yscb_abs)
    if not enabled or not auto_spawn:
        return

    if not can_spawn_background_daemon():
        if not _AUTO_SPAWN_WARNED:
            _AUTO_SPAWN_WARNED = True
            _print_agent_daemon_blocker()
        return

    try:
        yscb_py = os.path.join(host_dir, "yscb.py")
        if not os.path.isfile(yscb_py):
            yscb_py = sys.argv[0]
        spawn_detached(
            [sys.executable, yscb_py, "server", "start", "--daemon"],
            cwd=host_dir,
        )
    except Exception:
        pass


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
    5. 觸發 post_cli_dispatch Hook
    """
    # FR-10: 對稱觸發 pre_cli_dispatch Hook
    is_verbose = (
        os.environ.get("YSCB_VERBOSE") == "1"
        or os.environ.get("YSCB_DEBUG") == "1"
        or any(arg in ("--verbose", "--debug") for arg in raw_args)
    )
    _ensure_hooks("pre_cli_dispatch", verbose=is_verbose)

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
    # 僅注入 .modules/<module> 與 .modules/core 運行時空間至 sys.path。
    # 嚴禁直接運行開發環境 (source/) 程式碼，禁止在此向 sys.path 插入 source/ 空間！
    # =========================================================================
    mod_root = os.path.dirname(os.path.dirname(target_cli))
    core_dir = os.path.join(yscb_abs, ".modules", "core")

    for p in [core_dir, mod_root]:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

    # 載入模組
    if target_cli in _MODULE_CACHE:
        mod = _MODULE_CACHE[target_cli]
    else:
        spec = importlib.util.spec_from_file_location(
            f"yscb_mod_{module_name.replace('-', '_')}_cli",
            target_cli,
        )
        if spec is None or spec.loader is None:
            print(f"[yscb] Error: Cannot load spec for '{target_cli}'.")
            return 1
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
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
            # EC-05: 既無精確函式亦非純分支 (Hard Sunset: 徹底移除 process fallback)
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
        # FR-10: 對稱觸發 post_cli_dispatch Hook
        _ensure_hooks("post_cli_dispatch", verbose=is_verbose)

    return exit_code


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
    }

    # 2. 判斷是否為 core 的快捷指令 (例如 yscb status, yscb list)
    if first_token in core_commands:
        module_name = "core"
        target_tokens = argv
    elif first_token == "core":
        module_name = "core"
        target_tokens = rest_tokens
    else:
        # 3. 模組名稱或模組別名
        resolved_mod = registry.resolve_module_name(first_token)
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
                # EC-01: 未知模組或未知指令，模糊拼寫比對
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

    # 5. 沿 target_tokens 走訪指令樹 (FR-12)
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

    # 9. FR-06: 指令級 server_compatible 雙管道分流
    if cmd_spec is not None and cmd_spec.server_compatible:
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
        # EC-04: 熱派發通訊失敗或常駐離線，透明降級至本地冷派發

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

