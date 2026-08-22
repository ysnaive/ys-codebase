#!/usr/bin/env python3
"""
yscb_cli.py — YS-Codebase 統一 CLI 轉接器 (Unified CLI Router)

語法：
  python yscb_cli.py <module_name> [command] [options...]

範例：
  python yscb_cli.py installer init
  python yscb_cli.py installer install agents-workflow
  python yscb_cli.py installer status
  python yscb_cli.py agents-workflow verify
  python yscb_cli.py agents-workflow scan --all
  python yscb_cli.py --help
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Windows 控制台編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CONFIG_FILENAME = "yscb_config.json"
INSTALLER_SCRIPT = "yscb_installer.py"


def get_root_dir() -> Path:
    cur = Path(__file__).resolve().parent
    return cur


def load_config(root_dir: Path) -> Dict[str, Any]:
    cfg_file = root_dir / CONFIG_FILENAME
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"installed_modules": {}}


def find_module_cli(root_dir: Path, module_name: str, config: Dict[str, Any]) -> Optional[Path]:
    """尋找指定模組的 scripts/cli.py 入口"""
    installed = config.get("installed_modules", {})
    mode = installed.get(module_name, {}).get("mode", "build")

    # 1. 依據已安裝模式查找 (source 模式查 source/，build 模式查 modules/)
    preferred_dirs = [
        root_dir / ("source" if mode == "source" else "modules") / module_name,
        root_dir / "ys_codebase" / ("source" if mode == "source" else "modules") / module_name,
    ]
    for p in preferred_dirs:
        cli_path = p / "scripts" / "cli.py"
        if cli_path.is_file():
            return cli_path

    # 2. 備用查找 (modules/ -> source/ -> build/ -> ys_codebase/*)
    search_subs = [
        "modules", "source", "build",
        "ys_codebase/modules", "ys_codebase/source", "ys_codebase/build"
    ]
    for sub in search_subs:
        alt_dir = root_dir / sub / module_name
        alt_cli = alt_dir / "scripts" / "cli.py"
        if alt_cli.is_file():
            return alt_cli

    return None


def get_all_available_clis(root_dir: Path, config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """掃描所有可供 CLI 調用的模組與其描述"""
    result: Dict[str, Dict[str, Any]] = {}

    # 1. 內建 installer
    installer_path = root_dir / INSTALLER_SCRIPT
    if not installer_path.exists():
        alt_inst = root_dir / "ys_codebase" / INSTALLER_SCRIPT
        if alt_inst.exists():
            installer_path = alt_inst

    result["installer"] = {
        "name": "installer",
        "description": "YS-Codebase 核心安裝管理工具 (init, install, pull, build, push, status, list, remove, diff)",
        "cli_path": installer_path if installer_path.exists() else None,
        "is_builtin": True
    }

    # 1.1 內建 uri 工具
    result["uri"] = {
        "name": "uri",
        "description": "Codebase 專用語意 URI 解析與反向轉換工具 (resolve, list, to-uri)",
        "cli_path": "builtin",
        "is_builtin": True
    }

    # 2. 掃描已安裝模組
    installed = config.get("installed_modules", {})
    for mod_name, info in installed.items():
        if mod_name == "core":
            continue
        cli_p = find_module_cli(root_dir, mod_name, config)
        desc = info.get("description", "")
        result[mod_name] = {
            "name": mod_name,
            "description": desc or f"已安裝模組 ({info.get('mode', 'build')})",
            "cli_path": cli_p,
            "is_builtin": False,
            "mode": info.get("mode", "build")
        }

    # 3. 掃描本地 modules/、source/ 與 build/ 中存在 cli.py 但未註冊的模組
    for sub in ["modules", "source", "build", "ys_codebase/source", "ys_codebase/build"]:
        sub_dir = root_dir / sub
        if sub_dir.is_dir():
            for item in sub_dir.iterdir():
                if item.is_dir() and not item.name.startswith(".") and item.name not in result and item.name != "core":
                    cli_candidate = item / "scripts" / "cli.py"
                    if cli_candidate.is_file():
                        manifest_p = item / "manifest.json"
                        desc = ""
                        if manifest_p.exists():
                            try:
                                with open(manifest_p, "r", encoding="utf-8") as mf:
                                    desc = json.load(mf).get("description", "")
                            except Exception:
                                pass
                        result[item.name] = {
                            "name": item.name,
                            "description": desc or f"本地可用模組 ({sub})",
                            "cli_path": cli_candidate,
                            "is_builtin": False,
                            "mode": sub
                        }

    return result


def print_global_help(root_dir: Path, config: Dict[str, Any]):
    clis = get_all_available_clis(root_dir, config)

    print("\n" + "=" * 80)
    print("  YS-Codebase 統一 CLI 轉接器 (yscb_cli.py)")
    print("=" * 80)
    print("  語法：python yscb_cli.py <module_name> [command] [options...]")
    print("-" * 80)
    print("  可用模組與指令入口列表：\n")
    print(f"  {'模組名稱 (Module)':<22} | {'CLI 狀態':<12} | {'功能說明'}")
    print("  " + "-" * 76)

    for mod_name, info in clis.items():
        status = "[可用]" if info.get("cli_path") else "[無 CLI 接口]"
        desc = info.get("description", "")
        print(f"  {mod_name:<22} | {status:<12} | {desc}")

    print("\n" + "=" * 80)
    print("  常用範例：")
    print("    • 調用 Installer 管理指令:  python yscb_cli.py installer status")
    print("    • 調用模組專屬指令:        python yscb_cli.py agents-workflow --help")
    print("    • 模組指令實例:            python yscb_cli.py agents-workflow verify")
    print("=" * 80 + "\n")


def handle_uri_command(root_dir: Path, config: Dict[str, Any], args: List[str]) -> int:
    """處理 uri 語意路徑相關指令 (resolve, list, to-uri)"""
    start_p = Path.cwd().resolve() if (Path.cwd() / CONFIG_FILENAME).exists() else root_dir.resolve()
    rel_proj = config.get("paths", {}).get("project_root", ".")
    proj_root = (start_p / rel_proj).resolve() if (start_p / CONFIG_FILENAME).exists() else (root_dir / rel_proj).resolve()

    core_candidates = [
        proj_root / "modules" / "core",
        proj_root / "source" / "core",
        root_dir / "modules" / "core",
        root_dir / "source" / "core",
        root_dir / "ys_codebase" / "source" / "core",
        root_dir / "ys_codebase" / "build" / "core",
        root_dir / "ys_codebase" / "modules" / "core"
    ]
    for cp in core_candidates:
        if (cp / "scripts").is_dir() and str(cp / "scripts") not in sys.path:
            sys.path.insert(0, str(cp / "scripts"))
            break
        elif cp.is_dir() and str(cp) not in sys.path:
            sys.path.insert(0, str(cp))
            break

    try:
        from yscb_core import ProjectURI
    except ImportError as e:
        print(f"[ERROR] 無法載入 yscb_core SDK：{e}", file=sys.stderr)
        return 1

    if not args or args[0] in ["--help", "-h", "help"]:
        print("\n" + "=" * 80)
        print("  🧭 YS-Codebase 專用語意 URI 工具 (Semantic URI Tool)")
        print("=" * 80)
        print("  指令語法：")
        print("    python yscb_cli.py uri resolve <uri_string>   解析語意 URI 為實體絕對路徑")
        print("    python yscb_cli.py uri list                   列出所有支援的 URI 協議與狀態")
        print("    python yscb_cli.py uri to-uri <file_path>     將實體路徑反向匹配為語意 URI")
        print("\n  標準支援協議 (Supported Schemes)：")
        print("    • project://<path>  - 專案根目錄 (Project Root)")
        print("    • yscb://<path>     - 工具庫根目錄 (YSCB Root)")
        print("    • plans://<path>    - 活躍開發計畫目錄 (paths.plans_dir)")
        print("    • archive://<path>  - 歷史歸檔目錄 (paths.archive_dir)")
        print("    • docs://<path>     - 專案知識庫目錄 (paths.docs_dir)")
        print("=" * 80 + "\n")
        return 0

    subcmd = args[0]

    if subcmd == "resolve":
        if len(args) < 2:
            print("用法: python yscb_cli.py uri resolve <uri_string>", file=sys.stderr)
            return 1
        target_uri = args[1]
        res = ProjectURI.resolve(target_uri, start_dir=start_p)
        if isinstance(res, str) and res == "!undefined":
            print("!undefined")
            return 1
        print(str(res))
        return 0

    elif subcmd == "list":
        schemes = ProjectURI.list_schemes(start_dir=start_p)
        print("\n" + "=" * 96)
        print("  Codebase 語意 URI 協議矩陣 (Semantic URI Protocol Matrix)")
        print("=" * 96)
        print(f"  {'協議 (Scheme)':<14} | {'所屬模組':<18} | {'設定鍵 (Setting)':<20} | {'狀態':<14} | {'解析基準路徑'}")
        print("  " + "-" * 92)
        for s in schemes:
            status_str = f"[{s['status']}]"
            print(f"  {s['scheme']:<14} | {s['module']:<18} | {s['setting']:<20} | {status_str:<14} | {s['resolved_path']}")
        print("=" * 96 + "\n")
        return 0

    elif subcmd == "to-uri":
        if len(args) < 2:
            print("用法: python yscb_cli.py uri to-uri <file_path>", file=sys.stderr)
            return 1
        target_path = args[1]
        uri_str = ProjectURI.to_uri(target_path, start_dir=start_p)
        print(uri_str)
        return 0

    else:
        print(f"[ERROR] 未知 uri 子指令 '{subcmd}'。請執行 'python yscb_cli.py uri --help'。", file=sys.stderr)
        return 1


def main() -> int:
    root_dir = get_root_dir()
    config = load_config(root_dir)

    args = sys.argv[1:]

    # 若無參數或為 --help / -h / help
    if not args or args[0] in ["--help", "-h", "help"]:
        print_global_help(root_dir, config)
        return 0

    target_module = args[0]
    sub_args = args[1:]

    # 1. 轉發至 installer
    if target_module in ["installer", "yscb", "core_installer"]:
        installer_script = root_dir / INSTALLER_SCRIPT
        if not installer_script.is_file():
            alt_inst = root_dir / "ys_codebase" / INSTALLER_SCRIPT
            if alt_inst.is_file():
                installer_script = alt_inst
            else:
                print(f"[ERROR] 找不到核心安裝器：{installer_script}", file=sys.stderr)
                return 1
        res = subprocess.run([sys.executable, str(installer_script)] + sub_args)
        return res.returncode

    # 1.1 轉發至 uri 工具
    if target_module == "uri":
        return handle_uri_command(root_dir, config, sub_args)

    # 2. 轉發至模組專屬 scripts/cli.py
    cli_path = find_module_cli(root_dir, target_module, config)
    if not cli_path:
        print(f"[ERROR] 模組 '{target_module}' 未安裝或未提供 scripts/cli.py 接口。", file=sys.stderr)
        print(f"提示：可執行 'python yscb_cli.py --help' 檢視可用模組清單。", file=sys.stderr)
        return 1

    # 構造執行環境並自動注入 yscb_core 至 PYTHONPATH
    env = os.environ.copy()
    rel_proj = config.get("paths", {}).get("project_root", ".")
    proj_root = (root_dir / rel_proj).resolve()

    env["YSCB_PROJECT_ROOT"] = str(proj_root)
    env["YSCB_ROOT"] = str(root_dir.resolve())
    env["YSCB_MODULE_DIR"] = str(cli_path.parent.parent.resolve())

    # 自動查找 Core SDK 路徑並掛載至 PYTHONPATH
    core_candidates = [
        proj_root / "modules" / "core",
        proj_root / "source" / "core",
        root_dir / "modules" / "core",
        root_dir / "source" / "core",
        root_dir / "ys_codebase" / "source" / "core",
        root_dir / "ys_codebase" / "build" / "core",
        root_dir / "ys_codebase" / "modules" / "core"
    ]
    for cp in core_candidates:
        if (cp / "scripts").is_dir():
            curr_pypath = env.get("PYTHONPATH", "")
            add_paths = str(cp / "scripts") + os.pathsep + str(cp)
            env["PYTHONPATH"] = add_paths + (os.pathsep + curr_pypath if curr_pypath else "")
            break
        elif cp.is_dir():
            curr_pypath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(cp) + (os.pathsep + curr_pypath if curr_pypath else "")
            break

    res = subprocess.run([sys.executable, str(cli_path)] + sub_args, cwd=str(proj_root), env=env)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
