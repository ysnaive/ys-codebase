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
import re
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
        "description": "YS-Codebase 核心安裝管理工具 (init, install, pull/update, build, push, status, list, remove/uninstall, diff, rollback, self-update)",
        "cli_path": installer_path if installer_path.exists() else None,
        "is_builtin": True
    }

    # 1.1 內建 uri 工具
    result["uri"] = {
        "name": "uri",
        "description": "Codebase 專用語意 URI 解析、反向轉換與健康檢查工具 (resolve, list, to-uri, check)",
        "cli_path": "builtin",
        "is_builtin": True
    }

    # 1.2 內建 cache 工具
    result["cache"] = {
        "name": "cache",
        "description": "模組專屬快取管理與清理工具 (status, clean)",
        "cli_path": "builtin",
        "is_builtin": True
    }

    # 1.3 內建 version 工具
    result["version"] = {
        "name": "version",
        "description": "語意化版本管理與相依檢查工具 (status, check, check-update, bump)",
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

    elif subcmd == "check":
        checks = ProjectURI.check_schemes(start_dir=start_p)
        print("\n" + "=" * 96)
        print("  🩺 Codebase 語意 URI 協議健康度與沙盒診斷報告 (URI Protocol Health Check)")
        print("=" * 96)
        print(f"  {'協議 (Scheme)':<16} | {'健康狀態':<10} | {'診斷細節':<30} | {'解析基準路徑'}")
        print("  " + "-" * 92)
        has_fail = False
        for c in checks:
            h_tag = f"[{c['health']}]"
            if c['health'] == 'FAIL':
                has_fail = True
            print(f"  {c['scheme']:<16} | {h_tag:<10} | {c['details']:<30} | {c['resolved_path']}")
        print("=" * 96 + "\n")
        return 1 if has_fail else 0

    else:
        print(f"[ERROR] 未知 uri 子指令 '{subcmd}'。請執行 'python yscb_cli.py uri --help'。", file=sys.stderr)
        return 1


def handle_cache_command(root_dir: Path, config: Dict[str, Any], args: List[str]) -> int:
    """處理 cache 快取管理相關指令 (clean, status)"""
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
        from yscb_core import ProjectContext
    except ImportError as e:
        print(f"[ERROR] 無法載入 yscb_core SDK：{e}", file=sys.stderr)
        return 1

    cache_root = ProjectContext.get_cache_root(start_p)
    modules_cache_root = cache_root / "modules"

    if not args or args[0] in ["--help", "-h", "help"]:
        print("\n" + "=" * 80)
        print("  💾 YS-Codebase 模組快取管理工具 (Module Cache Tool)")
        print("=" * 80)
        print("  指令語法：")
        print("    python yscb_cli.py cache status               檢視各模組專屬快取佔用狀態")
        print("    python yscb_cli.py cache clean <module_name>  清理指定模組的命名空間快取")
        print("    python yscb_cli.py cache clean --all          清理所有工具庫快取")
        print(f"\n  快取根目錄: {cache_root}")
        print("=" * 80 + "\n")
        return 0

    subcmd = args[0]

    if subcmd == "status":
        print("\n" + "=" * 80)
        print(f"  📦 模組專屬快取佔用統計 ({modules_cache_root})")
        print("=" * 80)
        if not modules_cache_root.is_dir():
            print("  [INFO] 目前無任何模組快取。")
        else:
            mod_dirs = [d for d in modules_cache_root.iterdir() if d.is_dir()]
            if not mod_dirs:
                print("  [INFO] 目前無任何模組快取。")
            else:
                print(f"  {'模組名稱 (Module)':<22} | {'檔案數量':<10} | {'磁碟佔用':<14} | {'實體快取路徑'}")
                print("  " + "-" * 76)
                for md in sorted(mod_dirs, key=lambda p: p.name):
                    files = [f for f in md.rglob("*") if f.is_file()]
                    total_size = sum(f.stat().st_size for f in files)
                    kb = total_size / 1024
                    print(f"  {md.name:<22} | {len(files):<10} | {kb:10.2f} KB | {md}")
        print("=" * 80 + "\n")
        return 0

    elif subcmd == "clean":
        clean_all = "--all" in args
        target_mod = None
        for a in args[1:]:
            if not a.startswith("-"):
                target_mod = a
                break

        import shutil
        if clean_all:
            if cache_root.is_dir():
                shutil.rmtree(cache_root, ignore_errors=True)
                print(f"[SUCCESS] 已徹底清理所有工具庫快取目錄：{cache_root}")
            else:
                print(f"[INFO] 快取目錄不存在，無需清理。")
            return 0
        elif target_mod:
            mod_cache = modules_cache_root / target_mod
            if mod_cache.is_dir():
                shutil.rmtree(mod_cache, ignore_errors=True)
                print(f"[SUCCESS] 已清理模組 '{target_mod}' 專屬快取目錄：{mod_cache}")
            else:
                print(f"[INFO] 模組 '{target_mod}' 無快取目錄或已被清理。")
            return 0
        else:
            print("用法: python yscb_cli.py cache clean <module_name> 或 python yscb_cli.py cache clean --all", file=sys.stderr)
            return 1

    else:
        print(f"[ERROR] 未知的 cache 子指令: '{subcmd}'", file=sys.stderr)
        return 1


def handle_version_command(root_dir: Path, config: Dict[str, Any], args: List[str]) -> int:
    """處理 version 子指令 (status, check, check-update, bump)"""
    rel_proj = config.get("paths", {}).get("project_root", ".")
    proj_root = (root_dir / rel_proj).resolve()

    # 掛載 yscb_core
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
        from yscb_core import SemVer, VersionConstraint, ProjectContext
    except ImportError:
        try:
            from semver import SemVer, VersionConstraint
        except ImportError:
            print("[ERROR] 無法載入 SemVer 模組，請確認 core 模組已就緒。", file=sys.stderr)
            return 1

    if not args or args[0] in ["--help", "-h", "help"]:
        print("\n" + "=" * 80)
        print("  🏷️  YS-Codebase 語意化版本管理工具 (Version Management Tool)")
        print("=" * 80)
        print("  指令語法：")
        print("    python yscb_cli.py version status                      檢視全專案模組版本狀態矩陣")
        print("    python yscb_cli.py version check                       校驗全專案相依性約束相容性")
        print("    python yscb_cli.py version check-update                檢查是否有可用更新與 Migration 提示")
        print("    python yscb_cli.py version bump <module> <level>       遞進模組版本號 (major|minor|patch)")
        print("=" * 80 + "\n")
        return 0

    subcmd = args[0].lower()

    def get_manifest_version(p: Path) -> Optional[str]:
        mf = p / "manifest.json"
        if mf.is_file():
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    return json.load(f).get("version")
            except Exception:
                pass
        return None

    def get_installer_file_version(p: Path) -> Optional[str]:
        if not p.is_file():
            return None
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'INSTALLER_VERSION\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    # 收集全模組名稱
    all_modules = set()
    scan_subs = [
        root_dir / "source",
        root_dir / "build",
        root_dir / "modules",
        root_dir / "ys_codebase" / "source",
        root_dir / "ys_codebase" / "build",
        root_dir / "ys_codebase" / "modules"
    ]
    for s_dir in scan_subs:
        if s_dir.is_dir():
            for item in s_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    all_modules.add(item.name)

    installed_dict = config.get("installed_modules", {})
    for m in installed_dict:
        all_modules.add(m)

    sorted_modules = sorted(list(all_modules))

    if subcmd == "status":
        print("\n" + "=" * 96)
        print("  🏷️  全專案模組與工具庫版本狀態矩陣 (Module & Tooling Version Status Matrix)")
        print("=" * 96)
        print(f"  {'模組/工具 (Name)':<22} | {'源碼版本 (Source)':<18} | {'建置版本 (Build)':<18} | {'安裝版本 (Install)':<18} | {'同步狀態 (Status)'}")
        print("  " + "-" * 92)

        # 1. 核心起手腳本 (Installer Bootstrapper)
        inst_boot_v = get_installer_file_version(root_dir / "yscb_installer.py")
        src_boot_v = get_installer_file_version(root_dir / "ys_codebase" / "yscb_installer.py") or inst_boot_v
        cache_boot_v = get_installer_file_version(root_dir / ".yscb_cache" / "mirror" / "yscb_installer.py") or get_installer_file_version(root_dir / ".yscb_cache" / "yscb_installer.py") or src_boot_v

        boot_status = "[SYNCED]"
        if not inst_boot_v:
            boot_status = "[NOT_FOUND]"
        elif src_boot_v and SemVer(src_boot_v) > SemVer(inst_boot_v):
            boot_status = "[OUTDATED]"

        print(f"  {'installer (CLI)':<22} | {('v'+src_boot_v if src_boot_v else '-'):<18} | {('v'+cache_boot_v if cache_boot_v else '-'):<18} | {('v'+inst_boot_v if inst_boot_v else '-'):<18} | {boot_status}")

        for mod in sorted_modules:
            # 尋找 source version
            src_v = None
            for p in [root_dir / "source" / mod, root_dir / "ys_codebase" / "source" / mod]:
                src_v = get_manifest_version(p)
                if src_v:
                    break

            # 尋找 build version
            build_v = None
            for p in [root_dir / "build" / mod, root_dir / "ys_codebase" / "build" / mod]:
                build_v = get_manifest_version(p)
                if build_v:
                    break

            # 尋找 installed version
            inst_v = installed_dict.get(mod, {}).get("version")
            if not inst_v:
                for p in [root_dir / "modules" / mod, root_dir / "ys_codebase" / "modules" / mod]:
                    inst_v = get_manifest_version(p)
                    if inst_v:
                        break

            # 計算同步狀態
            status_tag = "[SYNCED]"
            if not inst_v:
                status_tag = "[NOT_INSTALLED]"
            elif src_v and build_v and inst_v:
                if src_v == build_v == inst_v:
                    status_tag = "[SYNCED]"
                elif SemVer(src_v) > SemVer(inst_v) or SemVer(src_v) > SemVer(build_v):
                    status_tag = "[OUTDATED]"
                else:
                    status_tag = "[DIVERGED]"
            elif src_v and not build_v:
                status_tag = "[UNBUILT]"

            src_display = f"v{src_v}" if src_v else "-"
            build_display = f"v{build_v}" if build_v else "-"
            inst_display = f"v{inst_v}" if inst_v else "-"

            print(f"  {mod:<22} | {src_display:<18} | {build_display:<18} | {inst_display:<18} | {status_tag}")

        print("=" * 96 + "\n")
        return 0

    elif subcmd == "check":
        print("\n" + "=" * 80)
        print("  🔍 全專案模組相依性相容約束校驗 (Dependency Compatibility Check)")
        print("=" * 80)
        has_error = False

        for mod in sorted_modules:
            manifest_p = None
            for p in [root_dir / "source" / mod, root_dir / "modules" / mod, root_dir / "ys_codebase" / "source" / mod]:
                if (p / "manifest.json").is_file():
                    manifest_p = p / "manifest.json"
                    break

            if not manifest_p:
                continue

            try:
                with open(manifest_p, "r", encoding="utf-8") as f:
                    mf_data = json.load(f)
            except Exception:
                continue

            deps = mf_data.get("dependencies", [])
            for dep_spec in deps:
                try:
                    dep_name, constraint = VersionConstraint.parse_dependency_spec(dep_spec)
                except Exception as e:
                    print(f"  ❌ [{mod}] 相依語法錯誤: '{dep_spec}' ({e})")
                    has_error = True
                    continue

                # 取得相依模組版本
                dep_ver = installed_dict.get(dep_name, {}).get("version")
                if not dep_ver:
                    for p in [root_dir / "source" / dep_name, root_dir / "modules" / dep_name, root_dir / "ys_codebase" / "source" / dep_name]:
                        dep_ver = get_manifest_version(p)
                        if dep_ver:
                            break

                if not dep_ver:
                    print(f"  ❌ [{mod}] 缺少相依模組 '{dep_name}' (要求約束: {constraint.raw_expr})")
                    has_error = True
                elif not constraint.matches(dep_ver):
                    print(f"  ❌ [{mod}] 相依衝突 '{dep_name}' (當前: v{dep_ver}, 要求約束: {constraint.raw_expr})")
                    has_error = True
                else:
                    print(f"  ✅ [{mod}] 相依滿足: '{dep_name}' (v{dep_ver} 滿足 {constraint.raw_expr})")

        print("=" * 80)
        if has_error:
            print("  🚨 檢測到相依性衝突或遺漏，請檢查上述錯誤。\n")
            return 1
        else:
            print("  🎉 [PASS] 全專案所有模組相依性約束 100% 滿足相容性要求！\n")
            return 0

    elif subcmd == "check-update":
        print("\n" + "=" * 90)
        print("  🚀 模組與起手腳本更新檢查 (Check Updates & Migration Advisory)")
        print("=" * 90)
        print(f"  {'項目名稱 (Component)':<22} | {'當前安裝':<10} | {'最新可用':<10} | {'變更等級':<10} | {'升級指引 / Migration'}")
        print("  " + "-" * 86)
        installer_update_available = False
        update_count = 0

        # 0. 檢查 Installer 起手腳本更新
        inst_boot_v_str = get_installer_file_version(root_dir / "yscb_installer.py")
        src_boot_v_str = get_installer_file_version(root_dir / "ys_codebase" / "yscb_installer.py") or get_installer_file_version(root_dir / ".yscb_cache" / "mirror" / "yscb_installer.py") or get_installer_file_version(root_dir / ".yscb_cache" / "yscb_installer.py")
        if inst_boot_v_str and src_boot_v_str:
            i_ver = SemVer(inst_boot_v_str)
            s_ver = SemVer(src_boot_v_str)
            if s_ver > i_ver:
                installer_update_available = True
                b_level = "PATCH" if s_ver.major == i_ver.major and s_ver.minor == i_ver.minor else ("MINOR" if s_ver.major == i_ver.major else "MAJOR")
                print(f"  {'installer (CLI)':<22} | v{inst_boot_v_str:<9} | v{src_boot_v_str:<9} | {b_level:<10} | 💡 執行 'python yscb_cli.py installer self-update' 即可更新")

        print("  " + "-" * 86)

        for mod in sorted_modules:
            inst_v_str = installed_dict.get(mod, {}).get("version")
            if not inst_v_str:
                for p in [root_dir / "modules" / mod, root_dir / "ys_codebase" / "modules" / mod]:
                    inst_v_str = get_manifest_version(p)
                    if inst_v_str:
                        break

            if not inst_v_str:
                continue

            # 最新可用版本 (源碼優先)
            latest_v_str = None
            for p in [root_dir / "source" / mod, root_dir / "build" / mod, root_dir / "ys_codebase" / "source" / mod]:
                latest_v_str = get_manifest_version(p)
                if latest_v_str:
                    break

            if not latest_v_str:
                continue

            inst_v = SemVer(inst_v_str)
            latest_v = SemVer(latest_v_str)

            if latest_v > inst_v:
                update_count += 1
                if latest_v.major > inst_v.major:
                    level = "MAJOR"
                    mig_needed = "🚨 需要專案升級指南"
                elif latest_v.minor > inst_v.minor:
                    level = "MINOR"
                    mig_needed = f"⚠️ 需要執行 _migration.py ({latest_v.major}.{latest_v.minor}.x)"
                else:
                    level = "PATCH"
                    mig_needed = "✅ 無 (安全直接覆蓋)"

                print(f"  {mod:<20} | v{inst_v_str:<11} | v{latest_v_str:<11} | {level:<10} | {mig_needed}")

        print("=" * 90)
        if update_count == 0 and not installer_update_available:
            print("  ✨ 所有已安裝模組與起手腳本皆為最新版本，無待更新項目。\n")
        else:
            if update_count > 0:
                print(f"  💡 發現 {update_count} 個模組可升級。執行 'python yscb_cli.py installer install <module> --force' 即可安全升級。")
            if installer_update_available:
                print("  💡 起手腳本 (installer) 有新版本。執行 'python yscb_cli.py installer self-update' 即可更新。")
            print()
        return 0

    elif subcmd == "bump":
        if len(args) < 3:
            print("用法: python yscb_cli.py version bump <module_name> <major|minor|patch>", file=sys.stderr)
            return 1

        mod_name = args[1]
        bump_level = args[2].lower()

        if bump_level not in ["major", "minor", "patch"]:
            print(f"[ERROR] 未知的遞進等級 '{bump_level}'，僅支援 'major', 'minor', 'patch'。", file=sys.stderr)
            return 1

        # 尋找源碼 manifest.json (SSOT)
        src_manifest_candidates = [
            root_dir / "source" / mod_name / "manifest.json",
            root_dir / "ys_codebase" / "source" / mod_name / "manifest.json"
        ]
        target_mf: Optional[Path] = None
        for p in src_manifest_candidates:
            if p.is_file():
                target_mf = p
                break

        if not target_mf:
            print(f"[ERROR] 找不到模組 '{mod_name}' 的源碼 manifest.json。請確認模組名稱。", file=sys.stderr)
            return 1

        try:
            with open(target_mf, "r", encoding="utf-8") as f:
                mf_content = json.load(f)
        except Exception as e:
            print(f"[ERROR] 讀取 {target_mf} 失敗: {e}", file=sys.stderr)
            return 1

        curr_ver_str = mf_content.get("version", "1.0.0")
        curr_ver = SemVer(curr_ver_str)
        new_ver = curr_ver.bump(bump_level)

        mf_content["version"] = str(new_ver)
        try:
            with open(target_mf, "w", encoding="utf-8") as f:
                json.dump(mf_content, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            print(f"[ERROR] 寫入 {target_mf} 失敗: {e}", file=sys.stderr)
            return 1

        print(f"\n[SUCCESS] 模組 '{mod_name}' 版本號已成功遞進：")
        print(f"  • 原版本 : v{curr_ver_str}")
        print(f"  • 新版本 : v{new_ver} (級別: {bump_level.upper()})")
        print(f"  • 更新檔 : {target_mf}\n")
        return 0

    else:
        print(f"[ERROR] 未知 version 子指令 '{subcmd}'。請執行 'python yscb_cli.py version --help'。", file=sys.stderr)
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

    # 1.2 轉發至 cache 工具
    if target_module == "cache":
        return handle_cache_command(root_dir, config, sub_args)

    # 1.3 轉發至 version 工具
    if target_module == "version":
        return handle_version_command(root_dir, config, sub_args)

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
