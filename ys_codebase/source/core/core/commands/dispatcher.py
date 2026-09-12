"""
Core Commands - CLI Pipeline Dispatcher & Dual-Track Router.
100% Python Standard Library. Zero Third-Party Dependencies.
"""
import difflib
import importlib.util
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from core.commands.bags import CmdBags
from core.commands.help import HelpRenderer
from core.commands.registry import CommandSpec, CommandsRegistry, ModuleSpec
from core.commands.resolver import (
    MissingValueError,
    MutualExclusionError,
    OptionResolutionError,
    OptionResolver,
)
from core.platform import is_process_alive, spawn_detached

# 快取已載入之 Contributes Registry
_GLOBAL_REGISTRY: Optional[CommandsRegistry] = None
_MODULE_CACHE: Dict[str, Any] = {}


def _get_yscb_root() -> Tuple[str, str]:
    """取得工作區根目錄與 yscb 根目錄。"""
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
    yscb_abs = os.path.normpath(os.path.join(host_dir, yscb_rel))
    return host_dir, yscb_abs


def _load_registry(yscb_abs: str) -> CommandsRegistry:
    """聚合工作區所有模組之 contributes/core.json 或 contributes/*.json。"""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is not None:
        return _GLOBAL_REGISTRY

    registry = CommandsRegistry()

    # =========================================================================
    # 🚨 剛性架構約束 (Rigid Architectural Guardrail) - 嚴禁擅自改動！
    # 本專案嚴格遵循：虛擬機測試 (dev test) -> install @build -> 實機測試 流程。
    # 僅允許 .modules 運行時空間載入 contributes，嚴禁直接運行或掃描開發環境 (source/) 程式碼。
    # 絕對禁止對此邏輯進行任何 fallback 或加入 source/ 空間之刪改！
    # =========================================================================
    modules_dir = os.path.join(yscb_abs, ".modules")
    if os.path.isdir(modules_dir):
        for mod_name in os.listdir(modules_dir):
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


def _try_hot_dispatch(module_name: str, cmd_name: str, args: List[str], yscb_abs: str) -> Optional[int]:
    """
    管道 B：透過 Localhost HTTP 將 server_compatible 指令熱派發至常駐 Server Worker。
    若連線超時或失敗則返回 None，自動降級為本地冷派發。
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
        payload = {
            "module": module_name,
            "args": [cmd_name] + args,
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
                        out = sys.stderr if pkt.get("stream") == "stderr" else sys.stdout
                        out.write(pkt.get("text", ""))
                        out.flush()
                    elif pkt.get("type") == "task_finish":
                        return pkt.get("exit_code", 0)
        return exit_code
    except Exception:
        # EC-04: 熱派發通訊異常時透明降級
        return None


def _maybe_auto_spawn_server(host_dir: str, yscb_abs: str) -> None:
    """
    在背景非同步按需拉起 Server 守護進程。
    僅在 server 模組存在、非 server/dev 指令、非測試環境、且 config/server/config.project.json enable != false 時觸發。
    """
    if os.environ.get("YSCB_TESTING") == "1" or os.environ.get("YSCB_TEST_SANDBOX") == "1":
        return

    state_file = os.path.join(yscb_abs, ".cache", "server", "daemon.json")
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                st = json.load(f)
            pid = st.get("pid")
            if pid:
                if is_process_alive(pid):
                    return  # 守護進程活躍，無須重複拉起
                else:
                    try:
                        os.remove(state_file)
                    except OSError:
                        pass
        except Exception:
            return

    # 🚨 剛性架構約束：僅允許 .modules 運行時空間，禁止任何 fallback
    if not os.path.isdir(os.path.join(yscb_abs, ".modules", "server")):
        return

    cfg_file = os.path.join(yscb_abs, "config", "server", "config.project.json")
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                if json.load(f).get("enable") is False:
                    return
        except Exception:
            pass

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
    🚨 剛性架構約束：僅允許 .modules 運行時空間，嚴禁直接運行開發環境 (source/) 程式碼，禁止任何 fallback。
    """
    target = os.path.join(yscb_abs, ".modules", module_name, "scripts", "cli.py")
    if os.path.isfile(target):
        return os.path.normpath(target)
    return None


def _ensure_hooks(hook_name: str) -> None:
    """觸發對稱生命週期 Hook。"""
    try:
        from core import events
        events.broadcast(hook_name, emit_module="core")
    except Exception:
        pass


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
    _ensure_hooks("pre_cli_dispatch")

    if isinstance(cmd_name, list):
        cmd_path = [str(c) for c in cmd_name]
    elif isinstance(cmd_name, str):
        cmd_path = cmd_name.split() if " " in cmd_name else [cmd_name]
    else:
        cmd_path = []

    func_name = "_".join(cmd_path).replace("-", "_") if cmd_path else "default"
    primary_cmd = cmd_path[0] if cmd_path else ""

    # 參數解析
    try:
        positional_args, resolved_options = OptionResolver.resolve(cmd_spec, raw_args)
    except OptionResolutionError as err:
        print(f"[yscb] Error: {err}")
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
        print(f"[yscb] Error: Cannot find CLI entrypoint for module '{module_name}'.")
        return 1

    # =========================================================================
    # 🚨 剛性架構約束 (Rigid Architectural Guardrail) - 嚴禁擅自改動！
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
            print(
                f"[yscb] Error (EC-05): Module '{module_name}' CLI script does not define "
                f"command function '{func_name}(cmd_bags)'."
            )
            return 127
    except SystemExit as se:
        exit_code = se.code if isinstance(se.code, int) else (0 if se.code is None else 1)
    except Exception as e:
        disp_cmd = " ".join(cmd_path)
        print(f"[yscb] Error executing '{module_name} {disp_cmd}': {e}")
        exit_code = 1
    finally:
        sys.argv = orig_argv
        # FR-10: 對稱觸發 post_cli_dispatch Hook
        _ensure_hooks("post_cli_dispatch")

    return exit_code


def dispatch(argv: Optional[List[str]] = None) -> int:
    """
    核心命令引擎入口函式。
    統一攔截 argv，完成路由分流、--help 渲染、雙管道派發與精確調用。
    """
    if argv is None:
        argv = sys.argv[1:]

    host_dir, yscb_abs = _get_yscb_root()
    if "YSCB_HOST_DIR" not in os.environ:
        os.environ["YSCB_HOST_DIR"] = host_dir
    if "YSCB_HOST_DISPATCH_TOKEN" not in os.environ:
        os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"

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
                print(f"[yscb] Error: Unknown command or module '{first_token}'.")
                if sugg:
                    print(f"       Did you mean '{sugg}'?")
                print("       Run 'python yscb.py --help' for available commands.")
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
        print(f"[yscb] Error: Unknown command '{unknown_token}' for module '{module_name}'.")
        if sugg:
            print(f"       Did you mean '{sugg}'?")
        print(f"       Run 'python yscb.py {module_name} --help' for available commands.")
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
                    if f"def {func_name}(" in content or f"def cmd_{func_name}(" in content:
                        has_fn = True
            except Exception:
                pass
        if not has_fn:
            print(HelpRenderer.render_cmd_help(module_name, cmd_disp_name, cmd_spec))
            return 0

    # 8. 檢查未知子指令
    if cmd_spec and cmd_spec.cmd and sub_args and not sub_args[0].startswith("-"):
        target_cli = _find_module_cli(module_name, yscb_abs)
        has_fn = False
        if target_cli:
            func_name = "_".join(cmd_path).replace("-", "_")
            try:
                with open(target_cli, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if f"def {func_name}(" in content or f"def cmd_{func_name}(" in content:
                        has_fn = True
            except Exception:
                pass
        if not has_fn:
            bad_sub = sub_args[0]
            sugg = _suggest_command(bad_sub, list(cmd_spec.cmd.keys()))
            print(f"[yscb] Error: Unknown subcommand '{bad_sub}' for command '{cmd_disp_name}'.")
            if sugg:
                print(f"       Did you mean '{sugg}'?")
            print(f"       Run 'python yscb.py {module_name} {cmd_disp_name} --help' for available subcommands.")
            return 1

    # 9. FR-06: 指令級 server_compatible 雙管道分流
    if cmd_spec is not None and cmd_spec.server_compatible:
        hot_res = _try_hot_dispatch(module_name, cmd_disp_name, sub_args, yscb_abs)
        if hot_res is not None:
            return hot_res
        # EC-04: 熱派發通訊失敗或常駐離線，透明降級至本地冷派發

    # 非 server / dev 指令在背景按需喚醒 Server 常駐進程
    if module_name not in ("server", "dev"):
        _maybe_auto_spawn_server(host_dir, yscb_abs)

    # 10. 本地冷派發執行
    return dispatch_local(
        module_name=module_name,
        cmd_name=cmd_path,
        raw_args=sub_args,
        cmd_spec=cmd_spec,
        yscb_abs=yscb_abs,
    )

