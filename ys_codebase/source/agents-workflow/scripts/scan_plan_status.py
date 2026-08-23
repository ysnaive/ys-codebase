#!/usr/bin/env python3
"""
scan_plan_status.py — 開發計畫狀態矩陣掃描工具

用途：掃描 plans_dir (與 archive_dir) 目錄，印出當前進行中與歷史 Dev Plan 的狀態矩陣（支援 Umbrella 主/子計畫階層）。
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_utils import get_plans_dir, get_archive_dir, get_module_dir, get_workspace_root

def get_plan_info(plan_dir: Path) -> tuple[str, str]:
    ft_plan = plan_dir / "FT_plan.md"
    p00_req = plan_dir / "P00_semantic_requirements.md"
    p01_req = plan_dir / "P01_requirements_spec.md"
    umbrella = plan_dir / "umbrella_overview.md"
    # master_plan_*.md 為舊版/人工遷移專案之相容命名偵測，標準 SOP 一律使用 umbrella_overview.md，
    # Agent 不應主動建立此檔名（僅供偵測既有專案殘留檔案）。
    master_roadmaps = list(plan_dir.glob("master_plan_*.md"))

    track_type = "Unknown"
    status = "Unknown"

    if umbrella.exists() or len(master_roadmaps) > 0:
        track_type = "Umbrella"
        target_doc = umbrella if umbrella.exists() else master_roadmaps[0]
        content = target_doc.read_text(encoding="utf-8", errors="ignore")
        for st in ["Completed", "In Progress", "Implementing", "Planning", "Discussing", "Draft"]:
            if f"狀態：{st}" in content or f"狀態: {st}" in content or f"Status: {st}" in content:
                status = st
                break
        if status == "Unknown":
            # 檢查子目錄完成度
            sub_dirs = [d for d in plan_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")]
            if sub_dirs:
                sub_statuses = [get_plan_info(sd)[1] for sd in sub_dirs]
                if all(s == "Completed" for s in sub_statuses):
                    status = "Completed"
                else:
                    status = "In Progress"
            else:
                status = "Planning"
    elif ft_plan.exists():
        track_type = "Fast Track"
        content = ft_plan.read_text(encoding="utf-8", errors="ignore")
        # 精確比對 Header「狀態：」欄位，避免正文其他段落偶然出現同名字詞（如 "Reviewing"）造成誤判
        for st in ["Completed", "Reviewing", "Implementing", "Planning"]:
            if f"狀態：{st}" in content or f"狀態: {st}" in content or f"Status: {st}" in content:
                status = st
                break
    elif p01_req.exists():
        track_type = "Full Track"
        if (plan_dir / "P07_walkthrough.md").exists():
            status = "Completed"
        elif (plan_dir / "P06_test_plan.md").exists() and (plan_dir / "P05_task.md").exists():
            status = "Testing/Phase 6"
        elif (plan_dir / "P05_task.md").exists():
            status = "Implementing/Phase 5"
        elif (plan_dir / "P04_implementation_plan.md").exists():
            status = "Reviewing/Phase 4"
        elif (plan_dir / "P03_api_spec.md").exists():
            status = "Designing/Phase 3"
        elif (plan_dir / "P02_architecture_plan.md").exists():
            status = "Designing/Phase 2"
        else:
            status = "Planning/Phase 1"
    elif p00_req.exists():
        track_type = "Phase 0 (P00)"
        content = p00_req.read_text(encoding="utf-8", errors="ignore")
        if "狀態：Confirmed" in content or "狀態: Confirmed" in content:
            status = "P00 Confirmed"
        else:
            status = "P00 Discussing"

    # 若存在暫停交接快照
    if (plan_dir / "handoff.md").exists() and status != "Completed":
        status = f"{status} (Paused)"

    return track_type, status

def scan_plans(include_history: bool = False):
    module_dir = get_module_dir()
    plans_dir = get_plans_dir(module_dir)
    archive_dir = get_archive_dir(module_dir)

    if not plans_dir.exists() and not (include_history and archive_dir.exists()):
        print(f"[INFO] 目前無計畫目錄 ({plans_dir})。")
        return

    print("=" * 90)
    print(f"{'計畫名稱 / 子計畫':<52} | {'Track 模式':<15} | {'當前狀態':<16} | {'位置'}")
    print("=" * 90)

    def print_plan_tree(plan_dir: Path, loc_str: str):
        t_type, status = get_plan_info(plan_dir)
        disp_name = plan_dir.name if len(plan_dir.name) <= 50 else plan_dir.name[:47] + "..."
        print(f"{disp_name:<52} | {t_type:<15} | {status:<16} | {loc_str}")
        
        # 掃描子計畫 sub_*
        sub_dirs = sorted([d for d in plan_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")], key=lambda x: x.name)
        for sd in sub_dirs:
            st_type, s_status = get_plan_info(sd)
            sub_disp = f"  └─ {sd.name}"
            sub_disp = sub_disp if len(sub_disp) <= 50 else sub_disp[:47] + "..."
            print(f"{sub_disp:<52} | {st_type:<15} | {s_status:<16} | {loc_str}")

    # 1. 進行中計畫
    if plans_dir.exists():
        active_plans = [d for d in plans_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        for plan in sorted(active_plans, key=lambda x: x.name, reverse=True):
            print_plan_tree(plan, "plans/")

    # 2. 歷史歸檔計畫 (選填)
    if include_history and archive_dir.exists():
        for y_dir in sorted(archive_dir.iterdir(), reverse=True):
            if y_dir.is_dir():
                for m_dir in sorted(y_dir.iterdir(), reverse=True):
                    if m_dir.is_dir():
                        for plan in sorted(m_dir.iterdir(), reverse=True):
                            if plan.is_dir():
                                print_plan_tree(plan, f"archive/{y_dir.name}/{m_dir.name}/")

    print("=" * 90)

if __name__ == "__main__":
    show_all = "--all" in sys.argv or "-a" in sys.argv
    scan_plans(include_history=show_all)
