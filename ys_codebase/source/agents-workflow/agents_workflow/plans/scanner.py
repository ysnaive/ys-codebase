"""
PlanScanner — 進行中開發計畫狀態掃描與矩陣渲染服務。
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple


def _resolve_uri_path(uri: str) -> Optional[Path]:
    """安全解析語意 URI，若無 core 上下文則回傳 None。"""
    try:
        from core.uri import resolve
        resolved = resolve(uri)
        return Path(resolved).resolve()
    except Exception:
        return None


class PlanScanner:
    """進行中開發計畫狀態掃描引擎。"""

    def __init__(self, plans_dir: Optional[Path] = None):
        """
        初始化 PlanScanner。
        
        Args:
            plans_dir: 進行中計畫目錄路徑。若為 None 則透過 workflow.plans:// 解析。
        """
        if plans_dir is not None:
            self.plans_dir = Path(plans_dir).resolve()
        else:
            resolved = _resolve_uri_path("workflow.plans://")
            self.plans_dir = resolved if resolved else Path.cwd() / "plans"

    def get_plan_info(self, plan_dir: Path) -> Tuple[str, str]:
        """
        解析單一計畫目錄的 Track 與當前狀態。
        
        Args:
            plan_dir: 計畫目錄路徑
            
        Returns:
            Tuple[str, str]: (track_type, status)
        """
        ft_plan = plan_dir / "fast_track_plan.md"
        legacy_ft_plan = plan_dir / "FT_plan.md"
        p00_req = plan_dir / "P00_semantic_requirements.md"
        p01_req = plan_dir / "P01_requirements_spec.md"
        umbrella = plan_dir / "umbrella_overview.md"
        master_roadmaps = list(plan_dir.glob("master_plan_*.md"))

        track_type = "Unknown"
        status = "Unknown"

        # 1. Umbrella 判定
        if umbrella.exists() or len(master_roadmaps) > 0:
            track_type = "Umbrella"
            target_doc = umbrella if umbrella.exists() else master_roadmaps[0]
            content = target_doc.read_text(encoding="utf-8", errors="ignore")
            for st in ["Completed", "In Progress", "Implementing", "Planning", "Discussing", "Draft", "Phase 0"]:
                if f"狀態：{st}" in content or f"狀態: {st}" in content or f"Status: {st}" in content or f"status: {st.lower()}" in content.lower():
                    status = st
                    break
            if status == "Unknown":
                sub_dirs = [d for d in plan_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")]
                if sub_dirs:
                    sub_statuses = [self.get_plan_info(sd)[1] for sd in sub_dirs]
                    if all("Completed" in s for s in sub_statuses):
                        status = "Completed"
                    else:
                        status = "In Progress"
                else:
                    status = "Planning"

        # 2. Fast Track 判定
        elif ft_plan.exists() or legacy_ft_plan.exists():
            track_type = "Fast Track"
            target_ft = ft_plan if ft_plan.exists() else legacy_ft_plan
            content = target_ft.read_text(encoding="utf-8", errors="ignore")
            for st in ["Completed", "Reviewing", "Implementing", "Planning", "Draft", "Confirmed"]:
                if f"狀態：{st}" in content or f"狀態: {st}" in content or f"Status: {st}" in content or f"status: {st.lower()}" in content.lower():
                    status = st
                    break
            if status == "Unknown":
                for st in ["Completed", "Reviewing", "Implementing", "Planning"]:
                    if st in content:
                        status = st
                        break

        # 3. Full Track 判定
        elif p01_req.exists():
            track_type = "Full Track"
            p07_file = plan_dir / "P07_walkthrough.md"
            if p07_file.exists():
                p07_content = p07_file.read_text(encoding="utf-8", errors="ignore")
                if "Completed" in p07_content or "狀態：Completed" in p07_content or "狀態: Completed" in p07_content:
                    status = "Completed"
                else:
                    status = "Reviewing/Phase 7"
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

        # 4. Phase 0 判定
        elif p00_req.exists():
            track_type = "Phase 0"
            content = p00_req.read_text(encoding="utf-8", errors="ignore")
            if "狀態：Confirmed" in content or "狀態: Confirmed" in content or "status: confirmed" in content.lower():
                status = "P00 Confirmed"
            else:
                status = "P00 Discussing"

        # 5. 檢查暫停快照
        if (plan_dir / "handoff.md").exists() and status != "Completed":
            status = f"{status} (Paused)"

        return track_type, status

    def scan_active_plans(self) -> List[Dict]:
        """
        掃描 workflow.plans:// 下的所有活躍進行中計畫。
        明確不掃描歷史目錄。
        
        Returns:
            List[Dict]: 結構化計畫清單
        """
        if not self.plans_dir.exists() or not self.plans_dir.is_dir():
            return []

        results = []
        # 篩選非隱藏目錄，並明確排除封存目錄 (archived 或 workflow.archived://)
        archived_dir = _resolve_uri_path("workflow.archived://")
        plan_dirs = [
            d for d in self.plans_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != "archived" and (not archived_dir or d.resolve() != archived_dir)
        ]

        for p_dir in sorted(plan_dirs, key=lambda x: x.name, reverse=True):
            track_type, status = self.get_plan_info(p_dir)
            sub_list = []

            # 遞迴掃描子計畫 sub_*
            sub_dirs = sorted([d for d in p_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")], key=lambda x: x.name)
            for s_dir in sub_dirs:
                s_track, s_status = self.get_plan_info(s_dir)
                sub_list.append({
                    "name": s_dir.name,
                    "path": s_dir,
                    "track": s_track,
                    "status": s_status,
                })

            results.append({
                "name": p_dir.name,
                "path": p_dir,
                "track": track_type,
                "status": status,
                "sub_plans": sub_list,
            })

        return results

    def render_matrix_ascii(self, plans: Optional[List[Dict]] = None) -> str:
        """
        將計畫清單渲染為 ASCII 表格字串。
        
        Args:
            plans: 計畫清單，若為 None 則調用 scan_active_plans()
            
        Returns:
            str: 格式化表格文字
        """
        if plans is None:
            plans = self.scan_active_plans()

        if not plans:
            return "[INFO] 目前無進行中的開發計畫。"

        lines = []
        lines.append("=" * 90)
        lines.append(f"{'計畫名稱 / 子計畫':<52} | {'Track 模式':<15} | {'當前狀態':<16} | {'位置'}")
        lines.append("=" * 90)

        for p in plans:
            disp_name = p["name"] if len(p["name"]) <= 50 else p["name"][:47] + "..."
            lines.append(f"{disp_name:<52} | {p['track']:<15} | {p['status']:<16} | plans/")
            for sub in p.get("sub_plans", []):
                sub_disp = f"  └─ {sub['name']}"
                sub_disp = sub_disp if len(sub_disp) <= 50 else sub_disp[:47] + "..."
                lines.append(f"{sub_disp:<52} | {sub['track']:<15} | {sub['status']:<16} | plans/")

        lines.append("=" * 90)
        return "\n".join(lines)
