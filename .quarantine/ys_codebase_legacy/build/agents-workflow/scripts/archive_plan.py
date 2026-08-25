#!/usr/bin/env python3
"""
archive_plan.py — 開發計畫安全歸檔工具

用途：將已完成的開發計畫從 plans_dir/<plan_name> 安全搬移至 archive_dir/YYYY/MM/<plan_name>。
守則：Agent 嚴禁主動執行，僅在開發者明確下達歸檔指令後方可呼叫。
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import shutil
import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_utils import get_plans_dir, get_archive_dir, get_module_dir, get_workspace_root

def archive_plan(plan_name: str, force: bool = False) -> bool:
    module_dir = get_module_dir()
    plans_dir = get_plans_dir(module_dir)
    archive_dir = get_archive_dir(module_dir)
    root = get_workspace_root(module_dir)

    src_dir = plans_dir / plan_name
    if not src_dir.exists() or not src_dir.is_dir():
        print(f"[ERROR] 找不到指定的計畫目錄：{src_dir}")
        return False

    # 解析日期前綴 YYYY_MM
    match = re.match(r"^(\d{4})_(\d{2})_", plan_name)
    if not match:
        print(f"[ERROR] 計畫名稱格式不符合規範（需以 YYYY_MM 開頭）：{plan_name}")
        return False

    year, month = match.group(1), match.group(2)
    dest_dir = archive_dir / year / month / plan_name

    # 檢查 Umbrella 子計畫是否皆已完成
    sub_dirs = [d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")]
    if sub_dirs and not force:
        uncompleted_subs = []
        for sd in sub_dirs:
            sd_completed = False
            for tf in [sd / "FT_plan.md", sd / "P07_walkthrough.md"]:
                if tf.exists():
                    c = tf.read_text(encoding="utf-8", errors="ignore")
                    if "Completed" in c or "狀態：Completed" in c or "狀態: Completed" in c:
                        sd_completed = True
                        break
            if not sd_completed:
                uncompleted_subs.append(sd.name)
        if uncompleted_subs:
            print(f"[WARNING] 主計畫 {plan_name} 底下尚有未完成的子計畫：{', '.join(uncompleted_subs)}")
            print("若確定要強制連同未完成子計畫一併歸檔，請加上 --force 參數。")
            return False

    # 檢查主計畫是否已完成
    ft_plan = src_dir / "FT_plan.md"
    p07_walkthrough = src_dir / "P07_walkthrough.md"
    umbrella_overview = src_dir / "umbrella_overview.md"

    is_completed = False
    for target_file in [ft_plan, p07_walkthrough, umbrella_overview]:
        if target_file.exists():
            content = target_file.read_text(encoding="utf-8", errors="ignore")
            if "Completed" in content or "status: active" in content or "狀態：Completed" in content or "狀態: Completed" in content:
                is_completed = True
                break

    if not is_completed and not force:
        print(f"[WARNING] 計畫 {plan_name} 似乎尚未完成（未找到 Completed 標記）。")
        print("若確定要強制歸檔，請加上 --force 參數。")
        return False

    # 檢查全域 CHANGELOG.md 是否有記載
    changelog_file = root / "CHANGELOG.md"
    if changelog_file.exists() and not force:
        cl_content = changelog_file.read_text(encoding="utf-8", errors="ignore")
        if plan_name not in cl_content:
            print(f"[WARNING] 根目錄 CHANGELOG.md 尚未包含此計畫 ({plan_name}) 的紀錄。")
            print("若確定要跳過 CHANGELOG 檢查，請加上 --force 參數。")
            return False

    # 清理暫時性交接檔案 (handoff.md)
    temp_handoff = src_dir / "handoff.md"
    if temp_handoff.exists():
        temp_handoff.unlink()
        print(f"  - [CLEANUP] 已清理暫時性交接檔案：{temp_handoff.name}")

    # 執行安全搬移
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        print(f"[ERROR] 目標歷史目錄已存在相同名稱的計畫：{dest_dir}")
        return False

    shutil.move(str(src_dir), str(dest_dir))
    print(f"[SUCCESS] 已成功將計畫歸檔至：{dest_dir}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python archive_plan.py <plan_name> [--force]")
        print("範例: python archive_plan.py 2026_08_01_1000_feature_name")
        sys.exit(1)

    p_name = sys.argv[1]
    is_force = "--force" in sys.argv
    success = archive_plan(p_name, force=is_force)
    sys.exit(0 if success else 1)
