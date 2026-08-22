#!/usr/bin/env python3
"""
core/scripts/cli.py — YS-Codebase 核心運行期 SDK (Core) 專屬 CLI 接口

指令清單：
  - python yscb_cli.py core info          檢視 Core SDK 運行環境與路徑狀態
  - python yscb_cli.py core uri resolve   解析語意 URI
  - python yscb_cli.py core uri list      列出所有已註冊協議矩陣
  - python yscb_cli.py core uri to-uri    實體路徑轉為語意 URI
"""

import sys
import os
import argparse
from pathlib import Path

# Windows 控制台編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 確保可引用 yscb_core
SCRIPTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

try:
    from yscb_core import ProjectContext, ConfigManager, Console, ProjectURI, __version__
except ImportError:
    # 備用查找
    cur = SCRIPTS_DIR
    while cur.parent != cur:
        if (cur / "scripts" / "yscb_core").is_dir():
            if str(cur / "scripts") not in sys.path:
                sys.path.insert(0, str(cur / "scripts"))
            break
        if (cur / "yscb_core").is_dir():
            if str(cur) not in sys.path:
                sys.path.insert(0, str(cur))
            break
        cur = cur.parent
    from yscb_core import ProjectContext, ConfigManager, Console, ProjectURI, __version__


def cmd_info(args):
    """顯示 Core SDK 與環境資訊"""
    try:
        proj_root = ProjectContext.get_project_root()
    except Exception:
        proj_root = Path.cwd()

    try:
        yscb_root = ProjectContext.get_yscb_root()
    except Exception:
        yscb_root = MODULE_DIR.parent.parent

    print("\n" + "=" * 80)
    print("  ⚙️  YS-Codebase Core Runtime SDK (yscb_core) 狀態資訊")
    print("=" * 80)
    print(f"  • SDK 版本 (Version)     : v{__version__}")
    print(f"  • 專案根目錄 (ProjectRoot) : {proj_root}")
    print(f"  • 工具庫目錄 (YSCBRoot)   : {yscb_root}")
    print(f"  • Core 模組路徑           : {MODULE_DIR}")
    print("=" * 80 + "\n")
    return 0


def cmd_uri(args):
    """URI 子指令轉發"""
    sub_action = args.action

    if sub_action == "resolve":
        if not args.target:
            Console.error("請提供欲解析的語意 URI，例: project://AGENTS.md")
            return 1
        res = ProjectURI.resolve(args.target)
        if isinstance(res, str) and res == "!undefined":
            print("!undefined")
            return 1
        print(str(res))
        return 0

    elif sub_action == "list":
        schemes = ProjectURI.list_schemes()
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

    elif sub_action == "to-uri":
        if not args.target:
            Console.error("請提供欲轉換的實體檔案路徑，例: docs/_project/STANDARDS.md")
            return 1
        uri_str = ProjectURI.to_uri(args.target)
        print(uri_str)
        return 0

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="python yscb_cli.py core",
        description="YS-Codebase Core SDK 核心模組管理工具"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用子指令")

    # 1. info
    p_info = subparsers.add_parser("info", help="顯示 Core SDK 運行環境與路徑狀態")
    p_info.set_defaults(func=cmd_info)

    # 2. uri
    p_uri = subparsers.add_parser("uri", help="語意 URI 解析與轉換工具")
    p_uri_sub = p_uri.add_subparsers(dest="action", help="URI 操作")

    p_res = p_uri_sub.add_parser("resolve", help="解析語意 URI 為實體絕對路徑")
    p_res.add_argument("target", help="語意 URI (如 project://AGENTS.md)")

    p_list = p_uri_sub.add_parser("list", help="列出所有已註冊協議矩陣")

    p_touri = p_uri_sub.add_parser("to-uri", help="實體路徑轉為語意 URI")
    p_touri.add_argument("target", help="本機實體路徑")

    p_uri.set_defaults(func=cmd_uri)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)
    
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
