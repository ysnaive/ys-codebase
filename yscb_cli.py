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
    preferred_dir = root_dir / ("source" if mode == "source" else "modules") / module_name
    cli_path = preferred_dir / "scripts" / "cli.py"
    if cli_path.is_file():
        return cli_path

    # 2. 備用查找 (modules/ -> source/ -> build/)
    for sub in ["modules", "source", "build"]:
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
    result["installer"] = {
        "name": "installer",
        "description": "YS-Codebase 核心安裝管理工具 (init, install, pull, build, push, status, list, remove)",
        "cli_path": installer_path if installer_path.exists() else None,
        "is_builtin": True
    }

    # 2. 掃描已安裝模組
    installed = config.get("installed_modules", {})
    for mod_name, info in installed.items():
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
    for sub in ["modules", "source", "build"]:
        sub_dir = root_dir / sub
        if sub_dir.is_dir():
            for item in sub_dir.iterdir():
                if item.is_dir() and not item.name.startswith(".") and item.name not in result:
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
            print(f"[ERROR] 找不到核心安裝器：{installer_script}", file=sys.stderr)
            return 1
        res = subprocess.run([sys.executable, str(installer_script)] + sub_args)
        return res.returncode

    # 2. 特殊基座模組 core 友善提示
    if target_module == "core":
        print("[INFO] 'core' 為 YS-Codebase 核心底層基座模組，純作為基礎相依，不提供獨立 CLI 指令接口。")
        print("提示：可執行 'python yscb_cli.py --help' 檢視其他可用模組與指令手冊。")
        return 0

    # 3. 轉發至模組專屬 scripts/cli.py
    cli_path = find_module_cli(root_dir, target_module, config)
    if not cli_path:
        print(f"[ERROR] 模組 '{target_module}' 未安裝或未提供 scripts/cli.py 接口。", file=sys.stderr)
        print(f"提示：可執行 'python yscb_cli.py --help' 檢視可用模組清單。", file=sys.stderr)
        return 1

    # 執行模組 CLI
    env = os.environ.copy()
    env["YSCB_PROJECT_ROOT"] = str(root_dir)
    res = subprocess.run([sys.executable, str(cli_path)] + sub_args, cwd=str(root_dir), env=env)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
