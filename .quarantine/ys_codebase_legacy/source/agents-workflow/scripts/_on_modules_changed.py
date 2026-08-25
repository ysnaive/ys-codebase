#!/usr/bin/env python3
"""
_on_modules_changed.py — agents-workflow 生命週期連動 Hook 與動態合成觸發器
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple

# Windows 控制台編碼防呆
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPTS_DIR.parent
COMMANDS_DIR = MODULE_DIR / "workflows" / "commands"
WORKFLOWS_DIR = MODULE_DIR / "workflows"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# 嘗試載入 Core SDK
try:
    from yscb_core import ProjectContext
except ImportError:
    # 若在源碼模式或未安裝時，動態定位 core
    core_scripts = MODULE_DIR.parent / "core" / "scripts"
    if core_scripts.is_dir() and str(core_scripts) not in sys.path:
        sys.path.insert(0, str(core_scripts))
    from context import ProjectContext

from sop_synthesizer import SOPSynthesizer


def parse_changes(args: List[str]) -> List[Tuple[str, str]]:
    """解析 CLI 傳入之 action:module 清單"""
    changes: List[Tuple[str, str]] = []
    for arg in args:
        if ":" in arg:
            action, mod_name = arg.split(":", 1)
            changes.append((action.strip(), mod_name.strip()))
    return changes


def synthesize_all_workflows() -> int:
    """從 workflows/commands/ 讀取基準指令，動態聚合所有外掛 Patch 並輸出至 workflows/*.md"""
    if not COMMANDS_DIR.is_dir():
        print(f"[WARN] 找不到基準指令目錄：{COMMANDS_DIR}")
        return 0

    # 若當前處於 source 源碼開發空間，不輸出生成物至 source/workflows/ 避免污染源碼庫
    if MODULE_DIR.parent.name == "source":
        return 0

    # 1. 取得所有模組對 agents-workflow 的貢獻
    contributions = ProjectContext.get_contributions("agents-workflow", start_dir=MODULE_DIR)

    # 收集全部 sop_patches
    # 格式: { target_sop: [ (patch_dict, mod_root, mod_name), ... ] }
    all_patches_by_sop = {}
    for mod_name, mod_dir, payload in contributions:
        if not isinstance(payload, dict):
            continue
        patches = payload.get("sop_patches", [])
        if not isinstance(patches, list):
            continue
        for patch in patches:
            if isinstance(patch, dict):
                target_sop = patch.get("target_sop")
                if target_sop:
                    if target_sop not in all_patches_by_sop:
                        all_patches_by_sop[target_sop] = []
                    all_patches_by_sop[target_sop].append((patch, mod_dir, mod_name))

    # 疊加順序決定性保證：依 (priority, 模組名稱) 穩定排序，priority 預設 100，數值越小越先注入
    def _patch_sort_key(entry):
        patch_dict, _mod_root, mod_name = entry
        priority = patch_dict.get("priority", 100)
        if not isinstance(priority, (int, float)):
            priority = 100
        return (priority, mod_name)

    for _ts in all_patches_by_sop:
        all_patches_by_sop[_ts].sort(key=_patch_sort_key)

    synthesized_count = 0
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

    for cmd_file in COMMANDS_DIR.glob("*.md"):
        template_text = cmd_file.read_text(encoding="utf-8")
        patches_for_file = all_patches_by_sop.get(cmd_file.name, [])

        result_text = template_text
        for patch_dict, mod_root, _mod_name in patches_for_file:
            result_text = SOPSynthesizer.synthesize_sop(
                template_content=result_text,
                patches=[patch_dict],
                contributing_module_root=mod_root
            )

        # 正則剝除所有未命中/殘留的 YSCB_SLOT 標記
        clean_text = SOPSynthesizer.strip_slot_markers(result_text)

        # 輸出至 workflows/<name>.md
        out_file = WORKFLOWS_DIR / cmd_file.name
        out_file.write_text(clean_text, encoding="utf-8")
        synthesized_count += 1

    return synthesized_count


def main() -> int:
    changes = parse_changes(sys.argv[1:])
    change_desc = ", ".join([f"{a}:{m}" for a, m in changes]) if changes else "無特定異動"
    print(f"[HOOK:agents-workflow] 收到模組生命週期廣播事件 ({change_desc})，啟動連動合成...")

    # 1. 執行 workflows/ 具體化動態合成
    count = synthesize_all_workflows()
    print(f"[HOOK:agents-workflow] 已從 commands/ 完成 {count} 份 SOP 工作流連動合成 ➔ {WORKFLOWS_DIR}")

    # 2. 環境感知：檢查專案是否已啟用 IDE (如 .agents/workflows/ 存在)
    proj_root = ProjectContext.get_project_root(start_dir=MODULE_DIR)
    ide_target = proj_root / ".agents" / "workflows"

    if ide_target.is_dir() or (proj_root / ".agents").is_dir():
        print(f"[HOOK:agents-workflow] 偵測到專案已啟用 IDE 工作流目錄 ({ide_target})，自動執行同步更新...")
        try:
            import importlib.util
            cli_path = SCRIPTS_DIR / "cli.py"
            spec = importlib.util.spec_from_file_location("agents_workflow_cli", str(cli_path))
            if spec and spec.loader:
                wf_cli = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(wf_cli)
                wf_cli.generate_antigravity_ide_commands()
                print("[HOOK:agents-workflow] IDE 指令無感自動同步完成！")
        except Exception as e:
            print(f"[WARN] 自動同步 IDE 指令失敗: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
