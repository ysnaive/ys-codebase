#!/usr/bin/env python3
"""
scan_plan_status.py — 專案開發進度與狀態掃描工具

用途：掃描 `.agents/dev_plans/` 目錄，印出當前進行中與歷史 Dev Plan 的狀態矩陣。
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from pathlib import Path

def get_workspace_root() -> Path:
    cur = Path(__file__).resolve().parent
    while cur.parent != cur:
        if (cur / ".agents").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()

def get_plan_info(plan_dir: Path) -> tuple[str, str]:
    ft_plan = plan_dir / "FT_plan.md"
    p01_req = plan_dir / "P01_requirements_spec.md"
    umbrella = plan_dir / "umbrella_overview.md"

    track_type = "Unknown"
    status = "Unknown"

    if ft_plan.exists():
        track_type = "Fast Track"
        content = ft_plan.read_text(encoding="utf-8", errors="ignore")
        for st in ["Completed", "Reviewing", "Implementing", "Planning"]:
            if st in content:
                status = st
                break
    elif umbrella.exists():
        track_type = "Umbrella"
        content = umbrella.read_text(encoding="utf-8", errors="ignore")
        for st in ["Completed", "Implementing", "Planning"]:
            if st in content:
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

    return track_type, status

def scan_plans(include_history: bool = False):
    root = get_workspace_root()
    dev_plans_dir = root / ".agents" / "dev_plans"

    if not dev_plans_dir.exists():
        print("[INFO] 目前無 Dev Plans 目錄。")
        return

    print("=" * 85)
    print(f"{'計畫名稱':<50} | {'Track 模式':<14} | {'當前狀態':<14} | {'位置'}")
    print("=" * 85)

    # 1. 進行中計畫
    active_plans = [d for d in dev_plans_dir.iterdir() if d.is_dir() and d.name != "history" and not d.name.startswith(".")]
    for plan in sorted(active_plans, key=lambda x: x.name, reverse=True):
        t_type, status = get_plan_info(plan)
        disp_name = plan.name if len(plan.name) <= 48 else plan.name[:45] + "..."
        print(f"{disp_name:<50} | {t_type:<14} | {status:<14} | active/")

    # 2. 歷史計畫 (選填)
    if include_history:
        history_dir = dev_plans_dir / "history"
        if history_dir.exists():
            for y_dir in sorted(history_dir.iterdir(), reverse=True):
                if y_dir.is_dir():
                    for m_dir in sorted(y_dir.iterdir(), reverse=True):
                        if m_dir.is_dir():
                            for plan in sorted(m_dir.iterdir(), reverse=True):
                                if plan.is_dir():
                                    t_type, status = get_plan_info(plan)
                                    disp_name = plan.name if len(plan.name) <= 48 else plan.name[:45] + "..."
                                    print(f"{disp_name:<50} | {t_type:<14} | {status:<14} | history/{y_dir.name}/{m_dir.name}/")

    print("=" * 85)

if __name__ == "__main__":
    show_all = "--all" in sys.argv or "-a" in sys.argv
    scan_plans(include_history=show_all)
