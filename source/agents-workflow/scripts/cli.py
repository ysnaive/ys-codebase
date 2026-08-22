#!/usr/bin/env python3
"""
agents-workflow CLI 專屬接口 (source/agents-workflow/scripts/cli.py)
"""

import sys
import os
import json
import argparse
import datetime
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

# Windows 控制台編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPTS_DIR.parent
WORKFLOWS_DIR = MODULE_DIR / "workflows"

CORE_WORKFLOW_FILES = [
    "ContextInit.md",
    "NewPlan.md",
    "Continue.md",
    "Discuss.md",
    "Idea.md",
    "Pause.md",
    "Research.md",
    "Review.md"
]


def load_module_config() -> Dict[str, Any]:
    """載入模組設定檔，若不存在則降級讀取 config.template.json"""
    module_config_path = MODULE_DIR / "config.json"
    template_config_path = MODULE_DIR / "config.template.json"
    if module_config_path.is_file():
        try:
            with open(module_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    if template_config_path.is_file():
        try:
            with open(template_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ide_integrations": {}, "custom_module_settings": {}}


def save_module_config(config: Dict[str, Any]):
    """持久化儲存模組設定檔至 module/config.json"""
    module_config_path = MODULE_DIR / "config.json"
    with open(module_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def extract_description(md_path: Path) -> str:
    """自 Markdown 的 YAML Frontmatter 提取 description 欄位"""
    try:
        content = md_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.splitlines():
                    line_s = line.strip()
                    if line_s.startswith("description:"):
                        desc = line_s.split("description:", 1)[1].strip()
                        return desc.strip("\"'")
    except Exception:
        pass
    return f"{md_path.stem} 工作流指令"


def get_relative_link(from_dir: Path, to_file: Path) -> str:
    """計算從目標目錄至核心文件的相對路徑 URL"""
    try:
        rel = os.path.relpath(to_file, from_dir)
        return rel.replace("\\", "/")
    except ValueError:
        return str(to_file).replace("\\", "/")


def locate_gemini_target_dir() -> Path:
    """定位專案的 Gemini / Antigravity 工作流目錄"""
    proj_root_str = os.environ.get("YSCB_PROJECT_ROOT")
    proj_root = Path(proj_root_str).resolve() if proj_root_str else Path.cwd().resolve()
    
    if proj_root.name == ".agents":
        target = proj_root / "workflows"
    else:
        target = proj_root / ".agents" / "workflows"

    target.mkdir(parents=True, exist_ok=True)
    return target


def clear_ide_commands(ide_name: Optional[str] = None) -> int:
    """清理已生成的 IDE 引用式指令檔案，並同步更新 config.json"""
    mod_config = load_module_config()
    integrations = mod_config.get("ide_integrations", {})

    if not integrations:
        print("[IDE:Clear] 目前無任何由 IDE 生成器產生的檔案需要清理。")
        return 0

    target_ides = [ide_name] if (ide_name and ide_name in integrations) else list(integrations.keys())
    if not target_ides or (ide_name and ide_name not in integrations):
        print(f"[IDE:Clear] 查無 IDE '{ide_name}' 的歷史生成紀錄。")
        return 0

    total_cleaned = 0
    for current_ide in list(target_ides):
        ide_info = integrations.get(current_ide, {})
        gen_files = ide_info.get("generated_files", [])
        raw_target_dir = ide_info.get("absolute_target_dir") or ide_info.get("target_dir")
        if not raw_target_dir:
            continue

        target_dir = Path(raw_target_dir)
        if not target_dir.is_absolute():
            target_dir = (MODULE_DIR / target_dir).resolve()

        removed_count = 0
        for fname in gen_files:
            file_to_del = target_dir / fname
            if file_to_del.is_file():
                try:
                    file_to_del.unlink()
                    removed_count += 1
                except Exception as e:
                    print(f"[WARN] 無法刪除檔案 {file_to_del}: {e}")

        print(f"[IDE:Clear] 已清理 {current_ide.capitalize()} 歷史生成的 {removed_count} 個指令檔案 (目錄: {target_dir})。")
        total_cleaned += removed_count
        del integrations[current_ide]

    mod_config["ide_integrations"] = integrations
    save_module_config(mod_config)
    print(f"[SUCCESS] IDE 指令清理作業完成，共移除 {total_cleaned} 個檔案。")
    return 0


def generate_gemini_ide_commands(prefix: str = "", postfix: str = "") -> int:
    """為 Gemini / Antigravity IDE 生成引用式指令文件，生成前自動清理舊有指令並更新 config.json"""
    # 1. 檢查並自動清理先前 gemini 生成的指令
    mod_config = load_module_config()
    if "gemini" in mod_config.get("ide_integrations", {}):
        print(f"[IDE:Gemini] 偵測到先前已存在 Gemini 生成紀錄，先執行舊檔案自動清理...")
        clear_ide_commands("gemini")
        mod_config = load_module_config()

    target_dir = locate_gemini_target_dir()
    print(f"\n[IDE:Gemini] 正在生成 Gemini / Antigravity 引用式工作流指令...")
    print(f"  • 目標目錄: {target_dir}")
    print(f"  • 前綴 (Prefix): '{prefix}'")
    print(f"  • 後綴 (Postfix): '{postfix}'")
    print("-" * 75)

    generated_files = []

    for wf_name in CORE_WORKFLOW_FILES:
        core_file = WORKFLOWS_DIR / wf_name
        if not core_file.is_file():
            print(f"[WARN] 找不到核心工作流檔案：{core_file}，略過。")
            continue

        stem = core_file.stem
        target_filename = f"{prefix}{stem}{postfix}.md"
        target_file = target_dir / target_filename

        desc = extract_description(core_file)
        rel_link = get_relative_link(target_dir, core_file)

        # 產生引用式指令 Markdown 內容
        content = f"""---
description: {desc}
---

# /{prefix}{stem}{postfix} 指令

本指令引用 YS-Codebase 核心工作流規範：[{wf_name}]({rel_link})

請 Agent 嚴格遵循上述核心工作流進行操作與階段推進。
"""
        target_file.write_text(content, encoding="utf-8")
        generated_files.append(target_filename)
        print(f"  [+] 已生成指令: {target_filename} ➔ 引用 {wf_name}")

    try:
        rel_target_dir = os.path.relpath(target_dir, MODULE_DIR).replace("\\", "/")
    except ValueError:
        rel_target_dir = str(target_dir).replace("\\", "/")

    if "ide_integrations" not in mod_config:
        mod_config["ide_integrations"] = {}

    mod_config["ide_integrations"]["gemini"] = {
        "target_dir": rel_target_dir,
        "absolute_target_dir": str(target_dir),
        "prefix": prefix,
        "postfix": postfix,
        "generated_files": generated_files,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds")
    }
    save_module_config(mod_config)

    print("-" * 75)
    print(f"[SUCCESS] Gemini 工作流指令生成完成！共 {len(generated_files)} 個指令。")
    print(f"  • 設定檔已記錄至: {MODULE_DIR / 'config.json'}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python yscb_cli.py agents-workflow",
        description="Agents-Workflow AI 研發工作流與定式工具庫 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用範例:
  # IDE 整合指令生成與清理:
  python yscb_cli.py agents-workflow --ide-gemini
  python yscb_cli.py agents-workflow --ide-gemini -prefix "sop_"
  python yscb_cli.py agents-workflow --ide-gemini -prefix "sop-" -postfix "_v2"
  python yscb_cli.py agents-workflow --ide-clear

  # 工作流定式工具:
  python yscb_cli.py agents-workflow verify
  python yscb_cli.py agents-workflow verify 2026_08_22_1200_my_plan
  python yscb_cli.py agents-workflow scan --all
  python yscb_cli.py agents-workflow search --query "Architecture"
  python yscb_cli.py agents-workflow search --dr --query "camelCase"
  python yscb_cli.py agents-workflow archive 2026_08_22_1200_my_plan
"""
    )

    # IDE 整合參數
    parser.add_argument("--ide-gemini", action="store_true", help="為 Gemini / Antigravity IDE 自動生成引用式指令檔案（生成前自動清理舊指令）")
    parser.add_argument("--ide-clear", action="store_true", help="清理已生成的 IDE 引用式指令檔案並重置設定檔紀錄")
    parser.add_argument("-prefix", "--prefix", default="", help="生成的 IDE 指令前綴 (例: sop_, custom_)")
    parser.add_argument("-postfix", "--postfix", default="", help="生成的 IDE 指令後綴 (例: _v2)")

    subparsers = parser.add_subparsers(dest="subcommand", title="工作流工具指令", description="支援的定式工具列表")

    # 1. verify
    verify_p = subparsers.add_parser("verify", help="稽核 Dev Plan 合規性與 Extension 落實情況")
    verify_p.add_argument("plan", nargs="?", help="指定欲驗證的計畫目錄名稱（可選，預設掃描所有進行中計畫）")

    # 2. scan
    scan_p = subparsers.add_parser("scan", help="掃描專案開發計畫進度矩陣")
    scan_p.add_argument("--all", action="store_true", help="包含已歸檔之歷史計畫全量掃描")

    # 3. search
    search_p = subparsers.add_parser("search", help="檢索歷史計畫與 DR 決策記錄")
    search_p.add_argument("-q", "--query", required=True, help="檢索關鍵字")
    search_p.add_argument("--dr", action="store_true", help="僅檢索 Decision Records (DR)")
    search_p.add_argument("--year", type=int, help="篩選年份 (例: 2026)")
    search_p.add_argument("--month", type=int, help="篩選月份 (例: 8)")

    # 4. archive
    archive_p = subparsers.add_parser("archive", help="安全歸檔已完成之計畫目錄")
    archive_p.add_argument("plan", help="欲歸檔的計畫目錄名稱")
    archive_p.add_argument("--force", action="store_true", help="強制覆寫同名歸檔目錄")

    args, unknown = parser.parse_known_args()

    # 處理 --ide-clear
    if args.ide_clear:
        return clear_ide_commands()

    # 處理 --ide-gemini
    if args.ide_gemini:
        return generate_gemini_ide_commands(prefix=args.prefix, postfix=args.postfix)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "verify":
        script = SCRIPTS_DIR / "verify_plan.py"
        call_args = [sys.executable, str(script)]
        if args.plan: call_args.append(args.plan)
        return subprocess.run(call_args).returncode

    elif args.subcommand == "scan":
        script = SCRIPTS_DIR / "scan_plan_status.py"
        call_args = [sys.executable, str(script)]
        if args.all: call_args.append("--all")
        return subprocess.run(call_args).returncode

    elif args.subcommand == "search":
        script = SCRIPTS_DIR / "search_dev_plans.py"
        call_args = [sys.executable, str(script), "--query", args.query]
        if args.dr: call_args.append("--dr")
        if args.year: call_args.extend(["--year", str(args.year)])
        if args.month: call_args.extend(["--month", str(args.month)])
        return subprocess.run(call_args).returncode

    elif args.subcommand == "archive":
        script = SCRIPTS_DIR / "archive_plan.py"
        call_args = [sys.executable, str(script), args.plan]
        if args.force: call_args.append("--force")
        return subprocess.run(call_args).returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
