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

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_utils import (
    load_project_config,
    save_project_config,
    load_local_config,
    save_local_config,
    get_plans_dir,
    get_archive_dir,
    get_docs_dir,
    get_extensions_dir,
    get_workspace_root,
    is_undefined_value,
    sync_agents_md,
    DEFAULT_AGENTS_MD_PATH,
)

from ext_registry import ExtensionRegistry
from ide_sync import IDECacheTracker
from sop_synthesizer import SOPSynthesizer

try:
    from yscb_core import ProjectContext
except ImportError:
    core_scripts = MODULE_DIR.parent / "core" / "scripts"
    if core_scripts.is_dir() and str(core_scripts) not in sys.path:
        sys.path.insert(0, str(core_scripts))
    from context import ProjectContext


def load_module_config() -> Dict[str, Any]:
    """載入本地運行期個人模組設定 (config.local.json)"""
    return load_local_config(MODULE_DIR)


def save_module_config(config: Dict[str, Any]):
    """持久化儲存本地模組個人設定至 config.local.json (被 .gitignore 忽略)"""
    save_local_config(config, MODULE_DIR)


CORE_WORKFLOW_FILES = [
    "ContextInit.md",
    "NewPlan.md",
    "Continue.md",
    "Discuss.md",
    "Idea.md",
    "Pause.md",
    "Research.md",
    "Review.md",
    "DocumentationStandards.md"
]

def get_core_workflow_files() -> List[str]:
    """獲取核心工作流清單"""
    return CORE_WORKFLOW_FILES


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


# ── IDE Adapter 註冊表 (開放式擴充點) ────────────────────────────────────
# 新增 IDE 支援時，僅需在此表新增一筆 adapter 定義 (target_subdir 為相對專案根目錄之路徑段)，
# 生成、快取追蹤 (per-adapter manifest)、孤兒清理與 config.local.json 紀錄均自動套用。
IDE_ADAPTERS: Dict[str, Dict[str, Any]] = {
    "antigravity": {
        "aliases": ["gemini"],
        "target_subdir": (".agents", "workflows"),
        "display_name": "Google Antigravity / Gemini",
    },
}


def locate_ide_target_dir(adapter: str = "antigravity") -> Path:
    """定位指定 IDE Adapter 的工作流指令目標目錄"""
    proj_root = get_workspace_root(MODULE_DIR)
    subdir = IDE_ADAPTERS.get(adapter, IDE_ADAPTERS["antigravity"])["target_subdir"]

    # 若專案根目錄本身即為目標子目錄首段 (例如根目錄名為 .agents)，避免重複疊加
    if proj_root.name == subdir[0]:
        target = proj_root.joinpath(*subdir[1:]) if len(subdir) > 1 else proj_root
    else:
        target = proj_root.joinpath(*subdir)

    target.mkdir(parents=True, exist_ok=True)
    return target


def locate_antigravity_target_dir() -> Path:
    """[相容別名] 定位專案的 Antigravity / Gemini 工作流目錄 (.agents/workflows/)"""
    return locate_ide_target_dir("antigravity")


def clear_ide_commands(ide_name: Optional[str] = None) -> int:
    """清理已生成的 IDE 引用式指令檔案，並同步更新 config.local.json 與各 Adapter 之 IDECacheTracker"""
    proj_root = get_workspace_root(MODULE_DIR)

    mod_config = load_module_config()
    integrations = mod_config.get("ide_integrations", {})

    target_ides = [ide_name] if (ide_name and ide_name in integrations) else list(integrations.keys())
    if not target_ides:
        # 未有任何紀錄時，仍嘗試清理預設 adapter 與舊版全域 manifest 的殘留追蹤
        target_ides = list(IDE_ADAPTERS.keys())

    total_cleaned = 0
    for current_ide in list(target_ides):
        tracker = IDECacheTracker(proj_root, adapter=current_ide)
        cleaned_files = tracker.clean_orphans([])
        total_cleaned += len(cleaned_files)
        tracker.save_manifest([])
        if current_ide in integrations:
            del integrations[current_ide]

    mod_config["ide_integrations"] = integrations
    save_module_config(mod_config)
    print(f"[SUCCESS] IDE 指令清理作業完成，共移除 {total_cleaned} 個檔案。")
    return 0


def build_jit_uri_header(target_dir: Path, core_file: Path) -> str:
    """生成動態 JIT 語意 URI 解析對照表 Markdown 區塊"""
    proj_root = get_workspace_root(MODULE_DIR)
    rel_core_link = get_relative_link(target_dir, core_file)

    def _fmt_rel(raw_p: Any) -> str:
        if is_undefined_value(raw_p) or str(raw_p) == "!undefined":
            return "`!undefined` (未初始化)"
        try:
            p = Path(raw_p)
            if p.is_absolute():
                rel = os.path.relpath(p, proj_root).replace("\\", "/")
                return f"`./{rel}`" if rel != "." else "`./`"
            return f"`{raw_p}`"
        except Exception:
            return f"`{raw_p}`"

    try:
        from yscb_core import ProjectURI
        plans_res = _fmt_rel(ProjectURI.resolve("plans://", start_dir=MODULE_DIR))
        arch_res = _fmt_rel(ProjectURI.resolve("archive://", start_dir=MODULE_DIR))
        docs_res = _fmt_rel(ProjectURI.resolve("docs://", start_dir=MODULE_DIR))
        ext_res = _fmt_rel(ProjectURI.resolve("sop_ext://", start_dir=MODULE_DIR))
        yscb_res = _fmt_rel(ProjectURI.resolve("yscb://", start_dir=MODULE_DIR))
    except Exception:
        plans_res = "`./plans`"
        arch_res = "`./archive_plans`"
        docs_res = "`./docs`"
        ext_res = "`./extensions`"
        yscb_res = "`./`"

    return f"""> [!NOTE]
> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)
> 本專案已註冊之語意 URI 實體路徑如下（核心來源規範：[{core_file.name}]({rel_core_link})）：
> 
> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |
> | :--- | :--- | :--- |
> | **`project://`** | `./` | `[ACTIVE]` |
> | **`yscb://`** | {yscb_res} | `[ACTIVE]` |
> | **`plans://`** | {plans_res} | `[ACTIVE]` |
> | **`archive://`** | {arch_res} | `[ACTIVE]` |
> | **`docs://`** | {docs_res} | `[ACTIVE]` |
> | **`sop_ext://`** | {ext_res} | `[ACTIVE]` |
> 
> 🛠️ **CLI 動態解析指令**：`python yscb_cli.py uri resolve <uri>`（例：`python yscb_cli.py uri resolve project://AGENTS.md`）
"""


def _collect_sop_patches() -> Dict[str, list]:
    """
    收集所有模組貢獻之 sop_patches，依 target_sop 分組。

    疊加順序具決定性：先依 (priority, 模組名稱) 穩定排序，priority 未宣告時預設 100，數值越小越先注入。
    """
    contributions = ProjectContext.get_contributions("agents-workflow", start_dir=MODULE_DIR)
    all_patches_by_sop: Dict[str, list] = {}
    for mod_name, mod_dir, payload in contributions:
        if isinstance(payload, dict):
            for patch in payload.get("sop_patches", []):
                if isinstance(patch, dict) and patch.get("target_sop"):
                    ts = patch["target_sop"]
                    if ts not in all_patches_by_sop:
                        all_patches_by_sop[ts] = []
                    all_patches_by_sop[ts].append((patch, mod_dir, mod_name))

    def _patch_sort_key(entry):
        patch_dict, _mod_root, mod_name = entry
        priority = patch_dict.get("priority", 100)
        if not isinstance(priority, (int, float)):
            priority = 100
        return (priority, mod_name)

    for ts in all_patches_by_sop:
        all_patches_by_sop[ts].sort(key=_patch_sort_key)
    return all_patches_by_sop


def generate_ide_commands(adapter: str = "antigravity", prefix: str = "", postfix: str = "") -> int:
    """為指定 IDE Adapter 生成指令文件，整合連動合成與 per-adapter IDECacheTracker 孤兒檔案清理"""
    # 0. 先執行 workflows/ 連動動態合成
    try:
        from _on_modules_changed import synthesize_all_workflows
        synthesize_all_workflows()
    except Exception as e:
        print(f"[WARN] 動態連動合成失敗: {e}")

    adapter_info = IDE_ADAPTERS.get(adapter, IDE_ADAPTERS["antigravity"])
    proj_root = get_workspace_root(MODULE_DIR)
    tracker = IDECacheTracker(proj_root, adapter=adapter)
    target_dir = locate_ide_target_dir(adapter)

    print(f"\n[IDE:{adapter}] 正在生成 {adapter_info.get('display_name', adapter)} 工作流指令 (全量鏡像 + JIT 語意解析注入)...")
    print(f"  • 目標目錄: {target_dir}")
    print(f"  • 前綴 (Prefix): '{prefix}'")
    print(f"  • 後綴 (Postfix): '{postfix}'")
    print("-" * 75)

    # 收集跨模組 patches (含 priority 決定性排序)
    all_patches_by_sop = _collect_sop_patches()

    generated_files: List[Path] = []
    core_wf_files = get_core_workflow_files()

    for wf_name in core_wf_files:
        cmd_file = MODULE_DIR / "workflows" / "commands" / wf_name
        if cmd_file.is_file():
            core_file = cmd_file
        elif (WORKFLOWS_DIR / wf_name).is_file():
            core_file = WORKFLOWS_DIR / wf_name
        else:
            print(f"[WARN] 找不到工作流檔案：{wf_name}，略過。")
            continue

        stem = core_file.stem
        cmd_name = f"{prefix}{stem}{postfix}"
        target_filename = f"{cmd_name}.md"
        target_file = target_dir / target_filename

        raw_content = core_file.read_text(encoding="utf-8")
        desc = extract_description(core_file)

        body = raw_content
        if body.startswith("---"):
            parts = body.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].lstrip("\r\n")

        # 執行 Slot 補丁動態注入 (依 priority 決定性順序)
        for patch_dict, mod_root, _mod_name in all_patches_by_sop.get(wf_name, []):
            body = SOPSynthesizer.synthesize_sop(body, [patch_dict], mod_root)

        for other_wf in core_wf_files:
            o_stem = Path(other_wf).stem
            other_cmd = f"{prefix}{o_stem}{postfix}"
            body = body.replace(f"./{other_wf}", f"./{other_cmd}.md")
            body = body.replace(f"./{o_stem}.md", f"./{other_cmd}.md")

        clean_body = SOPSynthesizer.strip_slot_markers(body)
        jit_header = build_jit_uri_header(target_dir, core_file)

        final_content = f"""---
description: {desc}
---

{jit_header}
{clean_body}"""

        target_file.write_text(final_content, encoding="utf-8")
        generated_files.append(target_file)
        print(f"  [+] 已生成: {target_file.name}")

    # 自動清理不再產出的孤兒指令檔案
    deleted_orphans = tracker.clean_orphans(generated_files)
    if deleted_orphans:
        for orphan in deleted_orphans:
            print(f"  [-] 已清理孤兒指令: {orphan.name}")

    # 儲存快取紀錄
    tracker.save_manifest(generated_files)

    # 同步更新 config.local.json
    mod_config = load_module_config()
    if "ide_integrations" not in mod_config:
        mod_config["ide_integrations"] = {}
    mod_config["ide_integrations"][adapter] = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "target_dir": str(target_dir.relative_to(proj_root)).replace("\\", "/"),
        "absolute_target_dir": str(target_dir).replace("\\", "/"),
        "generated_files": [f.name for f in generated_files]
    }
    save_module_config(mod_config)

    print("-" * 75)
    print(f"[SUCCESS] {adapter_info.get('display_name', adapter)} 工作流指令生成完成！共寫入 {len(generated_files)} 個指令，清理 {len(deleted_orphans)} 個孤兒檔案。")
    return 0


def generate_antigravity_ide_commands(prefix: str = "", postfix: str = "") -> int:
    """[相容別名] 為 Antigravity / Gemini IDE 生成指令文件"""
    return generate_ide_commands("antigravity", prefix=prefix, postfix=postfix)


# 相容別名
generate_gemini_ide_commands = generate_antigravity_ide_commands


def discover_all_extensions() -> List[Dict[str, Any]]:
    """透過 ExtensionRegistry 掃描所有可用 SOP 擴充"""
    registry = ExtensionRegistry.discover_all(ProjectContext)
    results = []
    for name, info in sorted(registry.items()):
        source_type = info.get("source_type", "module")
        mod_name = info.get("module_name")
        if source_type == "sop_ext":
            source_tag = "[sop_ext]"
        else:
            source_tag = f"[module: {mod_name}]" if mod_name else "[module]"

        doc_path = info.get("doc_path")
        desc = ""
        if doc_path and doc_path.is_file():
            try:
                content = doc_path.read_text(encoding="utf-8", errors="ignore")
                for l in content.splitlines():
                    if l.startswith("#"):
                        desc = l.lstrip("#").strip()
                        break
            except Exception:
                pass

        results.append({
            "name": name,
            "file": doc_path.name if doc_path else f"{name}.md",
            "path": doc_path,
            "script_path": info.get("script_path"),
            "phase": "All / On-Demand",
            "trigger": info.get("trigger", "on_demand"),
            "description": desc or name,
            "source_tag": source_tag
        })
    return results


def handle_ext_command(args) -> int:
    """處理 ext 子指令族 (list, show)"""
    exts = discover_all_extensions()
    if not hasattr(args, "ext_command") or args.ext_command == "list" or not args.ext_command:
        print("\n" + "=" * 96)
        print("  🧩 專案可用 SOP 擴充清單 (Available SOP Extensions)")
        print("=" * 96)
        if not exts:
            print("  [INFO] 目前無已註冊之 SOP Extension。可於 sop_ext:// 目錄建立擴充 Markdown 文件。")
            print("=" * 96 + "\n")
            return 0

        print(f"  {'擴充名稱 (Name)':<28} | {'觸發模式 (Trigger)':<16} | {'來源 (Source)':<20} | {'說明'}")
        print("  " + "-" * 92)
        for e in exts:
            trig_str = f"[{e['trigger']}]"
            desc = e['description'][:30]
            print(f"  {e['name']:<28} | {trig_str:<16} | {e['source_tag']:<20} | {desc}")
        print("=" * 96 + "\n")
        return 0

    elif args.ext_command == "show":
        target = args.name
        matched = [e for e in exts if e["name"].lower() == target.lower() or e["file"].lower() == target.lower()]
        if not matched:
            print(f"[ERROR] 找不到名為 '{target}' 的 Extension。請執行 'python yscb_cli.py agents-workflow ext list' 檢視可用清單。", file=sys.stderr)
            return 1
        target_ext = matched[0]
        if target_ext.get("path") and target_ext["path"].is_file():
            print(f"\n# 🧩 Extension: {target_ext['name']} ({target_ext['source_tag']} 檔案: {target_ext['path'].name})\n")
            print(target_ext["path"].read_text(encoding="utf-8", errors="replace"))
        else:
            print(f"\n# 🧩 Extension: {target_ext['name']} ({target_ext['source_tag']})\n無附帶 Markdown 說明文件。")
        return 0

    return 0


def init_project_paths(
    plans_dir: Optional[str] = None,
    archive_dir: Optional[str] = None,
    docs_dir: Optional[str] = None,
    extensions_dir: Optional[str] = None,
    agents_md_path: Optional[str] = None,
    is_default: bool = False
) -> int:
    """初始化 agents-workflow 之專案路徑設定 (config.project.json)"""
    proj_cfg = load_project_config(MODULE_DIR)
    if "paths" not in proj_cfg:
        proj_cfg["paths"] = {}

    if is_default:
        proj_cfg["paths"]["plans_dir"] = plans_dir or "plans"
        proj_cfg["paths"]["archive_dir"] = archive_dir or "archive_plans"
        proj_cfg["paths"]["docs_dir"] = docs_dir or "docs"
        proj_cfg["paths"]["extensions_dir"] = extensions_dir or "extensions"
        proj_cfg["paths"]["agents_md_path"] = agents_md_path or DEFAULT_AGENTS_MD_PATH
    else:
        if plans_dir: proj_cfg["paths"]["plans_dir"] = plans_dir
        if archive_dir: proj_cfg["paths"]["archive_dir"] = archive_dir
        if docs_dir: proj_cfg["paths"]["docs_dir"] = docs_dir
        if extensions_dir: proj_cfg["paths"]["extensions_dir"] = extensions_dir
        if agents_md_path: proj_cfg["paths"]["agents_md_path"] = agents_md_path

    # 檢查是否仍有 !undefined
    p_val = proj_cfg["paths"].get("plans_dir", "!undefined")
    a_val = proj_cfg["paths"].get("archive_dir", "!undefined")
    d_val = proj_cfg["paths"].get("docs_dir", "!undefined")
    e_val = proj_cfg["paths"].get("extensions_dir", "!undefined")
    ag_val = proj_cfg["paths"].get("agents_md_path", "!undefined")

    if not is_default and (p_val == "!undefined" and a_val == "!undefined" and d_val == "!undefined" and e_val == "!undefined" and ag_val == "!undefined"):
        print("[ERROR] 未指定任何有效路徑參數。請使用 --default 或指定 --plans-dir, --archive-dir, --docs-dir, --extensions-dir, --agents-md。")
        return 1

    save_project_config(proj_cfg, MODULE_DIR)
    print(f"[SUCCESS] agents-workflow 專案路徑設定已成功更新！")
    print(f"  • 設定檔路徑    : {MODULE_DIR / 'config.project.json'}")
    print(f"  • plans_dir       : {proj_cfg['paths'].get('plans_dir')}")
    print(f"  • archive_dir     : {proj_cfg['paths'].get('archive_dir')}")
    print(f"  • docs_dir        : {proj_cfg['paths'].get('docs_dir')}")
    print(f"  • extensions_dir  : {proj_cfg['paths'].get('extensions_dir')}")
    print(f"  • agents_md_path  : {proj_cfg['paths'].get('agents_md_path')}")

    # 觸發 AGENTS.md 軟合併有效加載
    target_agents_md = proj_cfg["paths"].get("agents_md_path")
    if target_agents_md and not is_undefined_value(target_agents_md):
        sync_agents_md(MODULE_DIR, target_agents_md)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python yscb_cli.py agents-workflow",
        description="Agents-Workflow AI 研發工作流與定式工具庫 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用範例:
  # 初始化專案路徑規範 (config.project.json):
  python yscb_cli.py agents-workflow init --plans-dir plans --archive-dir archive_plans --docs-dir docs --extensions-dir extensions
  python yscb_cli.py agents-workflow init --default

  # 查詢專案可用 Extension 擴充清單:
  python yscb_cli.py agents-workflow ext list
  python yscb_cli.py agents-workflow ext show ext_template

  # IDE 整合指令生成與清理:
  python yscb_cli.py agents-workflow --ide-antigravity
  python yscb_cli.py agents-workflow --ide-antigravity -prefix "sop_"
  python yscb_cli.py agents-workflow --ide-clear

  # 工作流定式工具:
  python yscb_cli.py agents-workflow verify
  python yscb_cli.py agents-workflow scan --all
  python yscb_cli.py agents-workflow search --query "Architecture"
  python yscb_cli.py agents-workflow archive 2026_08_22_1200_my_plan
"""
    )

    # IDE 整合參數
    parser.add_argument("--ide-antigravity", action="store_true", help="為 Antigravity / Gemini IDE 自動生成引用式指令檔案（生成前自動清理舊指令）")
    parser.add_argument("--ide-gemini", action="store_true", help="[別名] 同 --ide-antigravity")
    parser.add_argument("--ide-clear", action="store_true", help="清理已生成的 IDE 引用式指令檔案並重置設定檔紀錄")
    parser.add_argument("-prefix", "--prefix", default="", help="生成的 IDE 指令前綴 (例: sop_, custom_)")
    parser.add_argument("-postfix", "--postfix", default="", help="生成的 IDE 指令後綴 (例: _v2)")

    subparsers = parser.add_subparsers(dest="subcommand", title="工作流工具指令", description="支援的定式工具列表")

    # 0. init
    init_p = subparsers.add_parser("init", help="初始化模組之專案路徑規範 (寫入 config.project.json)")
    init_p.add_argument("--plans-dir", help="指定活躍開發計畫目錄路徑 (相對於專案根目錄)")
    init_p.add_argument("--archive-dir", help="指定歷史計畫歸檔目錄路徑 (相對於專案根目錄)")
    init_p.add_argument("--docs-dir", help="指定專案知識庫目錄路徑 (相對於專案根目錄)")
    init_p.add_argument("--extensions-dir", "--ext-dir", help="指定專案特化擴充清單目錄路徑 (相對於專案根目錄)")
    init_p.add_argument("--agents-md", "--agents-md-path", help="指定 AGENTS.md 行為準則檔案路徑 (相對於專案根目錄)")
    init_p.add_argument("--default", action="store_true", help="使用推薦預設值快速初始化 (plans, archive_plans, docs, extensions, AGENTS.md)")

    # 0.1 ext
    ext_p = subparsers.add_parser("ext", help="查詢與檢視專案可用之 SOP Extension 擴充清單")
    ext_sub = ext_p.add_subparsers(dest="ext_command", help="Extension 操作")
    ext_list_p = ext_sub.add_parser("list", help="列出所有可用 Extension 與觸發模式")
    ext_show_p = ext_sub.add_parser("show", help="檢視指定 Extension 完整內容與 Checklist")
    ext_show_p.add_argument("name", help="Extension 名稱或檔案名")

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

    # 5. docs
    docs_p = subparsers.add_parser("docs", help="專案知識庫 (docs/) 健康守護與按需輔助工具")
    docs_sub = docs_p.add_subparsers(dest="docs_action", help="Docs 操作指令")
    
    docs_init_p = docs_sub.add_parser("init", help="初始化知識庫根目錄與全域地圖骨架")
    docs_init_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    docs_audit_p = docs_sub.add_parser("audit", help="檢查 docs/ 內部相對路徑死鏈與 Frontmatter 語法")
    docs_audit_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    docs_check_p = docs_sub.add_parser("check-links", help="[別名] 同 audit")
    docs_check_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    docs_topic_p = docs_sub.add_parser("new-topic", help="快速生成專題技術手冊範本")
    docs_topic_p.add_argument("module", help="目標模組目錄名稱 (例: Core 或 Network)")
    docs_topic_p.add_argument("topic", help="專題名稱 (例: lifecycle 或 protocol_spec)")
    docs_topic_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    args, unknown = parser.parse_known_args()

    # 處理 --ide-clear
    if args.ide_clear:
        return clear_ide_commands()

    # 處理 --ide-antigravity / --ide-gemini
    if args.ide_antigravity or args.ide_gemini:
        return generate_antigravity_ide_commands(prefix=args.prefix, postfix=args.postfix)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "init":
        return init_project_paths(args.plans_dir, args.archive_dir, args.docs_dir, args.extensions_dir, args.agents_md, args.default)

    elif args.subcommand == "ext":
        return handle_ext_command(args)

    elif args.subcommand == "verify":
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

    elif args.subcommand == "docs":
        script = SCRIPTS_DIR / "docs_tool.py"
        if not args.docs_action:
            subprocess.run([sys.executable, str(script), "--help"])
            return 0
        call_args = [sys.executable, str(script), args.docs_action]
        if getattr(args, "module", None): call_args.append(args.module)
        if getattr(args, "topic", None): call_args.append(args.topic)
        if getattr(args, "docs_dir", None): call_args.extend(["--docs-dir", args.docs_dir])
        return subprocess.run(call_args).returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())

