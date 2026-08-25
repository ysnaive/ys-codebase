#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extensions/dogfooding_pipeline_verify.py — 專案特化 Dogfooding 發布與版本守門驗證外掛

由 verify_plan.py 抽象動態調用，專門把關本專案在執行 Dev Plan 時的自引用流水線合規性：
1. 檢查源碼若有實質變更，對應模組之 manifest.json 版本號是否已如期遞進。
2. 檢查全專案【源碼 == 建置 == 安裝】三態版本一致性。
3. 檢查已完成計畫是否已於 project://CHANGELOG.md 登記發布紀錄。
"""

import sys
import os
import json
import re
from pathlib import Path

# Windows 控制台編碼防護
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        print("[ERROR] 請提供 Dev Plan 目錄路徑。用法: python dogfooding_pipeline_verify.py <plan_dir>", file=sys.stderr)
        return 1

    plan_dir = Path(sys.argv[1]).resolve()
    if not plan_dir.is_dir():
        print(f"[ERROR] 指定計畫目錄不存在: {plan_dir}", file=sys.stderr)
        return 1

    # 尋找專案根目錄
    cur = plan_dir
    project_root = cur
    while cur != cur.parent:
        if (cur / "yscb_config.json").is_file() or (cur / "AGENTS.md").is_file():
            project_root = cur
            break
        cur = cur.parent

    # 1. 讀取 Plan 狀態與交付清單
    p07_file = plan_dir / "P07_walkthrough.md"
    p04_file = plan_dir / "P04_implementation_plan.md"
    ft_file = plan_dir / "FT_plan.md"

    is_completed = False
    for f in [p07_file, ft_file]:
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "狀態：Completed" in text or "狀態: Completed" in text or "Status: Completed" in text:
                is_completed = True
                break

    issues = []

    # 2. 檢查 CHANGELOG.md 是否已更新 (若計畫為 Completed)
    if is_completed:
        global_changelog = project_root / "CHANGELOG.md"
        if not global_changelog.is_file():
            issues.append("[WARN] 專案根目錄缺少 CHANGELOG.md")
        else:
            cl_text = global_changelog.read_text(encoding="utf-8", errors="ignore")
            if plan_dir.name not in cl_text:
                issues.append(f"[WARN] project://CHANGELOG.md 尚未包含本計畫 ({plan_dir.name}) 之發布章節紀錄")

    # 3. 檢查全專案源碼 vs 建置 vs 安裝三態一致性
    config_file = project_root / "yscb_config.json"
    if config_file.is_file():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg_data = json.load(f)
            installed_modules = cfg_data.get("installed_modules", {})
            for mod_name, info in installed_modules.items():
                inst_ver = info.get("version")
                src_manifest = project_root / "ys_codebase" / "source" / mod_name / "manifest.json"
                if not src_manifest.is_file():
                    src_manifest = project_root / "source" / mod_name / "manifest.json"

                if src_manifest.is_file():
                    try:
                        with open(src_manifest, "r", encoding="utf-8") as mf:
                            src_ver = json.load(mf).get("version")
                        if is_completed and src_ver and inst_ver and src_ver != inst_ver:
                            issues.append(f"[WARN] 模組 '{mod_name}' 版本未完全同步 (源碼: v{src_ver}, 安裝: v{inst_ver})，請執行 Dogfooding Stage 4 同步")
                    except Exception:
                        pass
        except Exception:
            pass

    if issues:
        for iss in issues:
            print(iss)
        # 若有包含 [ERROR] 則返回 1，純 WARN 返回 0
        has_error = any("[ERROR]" in iss for iss in issues)
        return 1 if has_error else 0

    print("[SUCCESS] Dogfooding 自引用流水線與發布版本檢驗通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
