#!/usr/bin/env python3
"""
scan_plan_status.py — 專案開發進度與狀態掃描工具

用途：掃描 `.agents/dev_plans/` 目錄，印出當前進行中與歷史 Dev Plan 的狀態矩陣（支援 Umbrella 主/子計畫階層）。
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
    p00_req = plan_dir / "P00_semantic_requirements.md"
    p01_req = plan_dir / "P01_requirements_spec.md"
    umbrella = plan_dir / "umbrella_overview.md"
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
        for st in ["Completed", "Reviewing", "Implementing", "Planning"]:
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
    elif p00_req.exists():
        track_type = "Phase 0 (P00)"
        content = p00_req.read_text(encoding="utf-8", errors="ignore")
        if "狀態：Confirmed" in content or "狀態: Confirmed" in content:
            status = "P00 Confirmed"
        else:
            status = "P00 Discussing"

    return track_type, status

def scan_plans(include_history: bool = False):
    root = get_workspace_root()
    dev_plans_dir = root / ".agents" / "dev_plans"

    if not dev_plans_dir.exists():
        print("[INFO] 目前無 Dev Plans 目錄。")
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
    active_plans = [d for d in dev_plans_dir.iterdir() if d.is_dir() and d.name != "history" and not d.name.startswith(".")]
    for plan in sorted(active_plans, key=lambda x: x.name, reverse=True):
        print_plan_tree(plan, "active/")

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
                                    print_plan_tree(plan, f"history/{y_dir.name}/{m_dir.name}/")

    print("=" * 90)

if __name__ == "__main__":
    show_all = "--all" in sys.argv or "-a" in sys.argv
    scan_plans(include_history=show_all)
