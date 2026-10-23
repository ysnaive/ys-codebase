"""
PlanScanner — 進行中開發計畫狀態掃描與矩陣渲染服務。
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any, Union


from . import _resolve_uri_path


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
        p00_req = plan_dir / "P00_discuss.md"
        legacy_p00_req = plan_dir / "P00_semantic_requirements.md"
        p01_req = plan_dir / "P01_requirements_spec.md"
        umbrella = plan_dir / "umbrella_overview.md"
        rev_log = plan_dir / "revision_log.md"
        master_roadmaps = list(plan_dir.glob("master_plan_*.md"))

        track_type = "Unknown"
        status = "Unknown"

        from .status import PlanStatusResolver

        # 1. Umbrella 判定
        if umbrella.exists() or len(master_roadmaps) > 0:
            track_type = "Umbrella"
            target_doc = umbrella if umbrella.exists() else master_roadmaps[0]
            raw_status = PlanStatusResolver.get_doc_header_status(target_doc)
            if raw_status in ("completed", "concluded"):
                status = "Completed"
            elif raw_status in ("in progress", "executing", "implementing"):
                status = "In Progress"
            elif raw_status in ("planning", "discussing", "draft", "phase 0"):
                status = "Planning" if raw_status == "planning" else raw_status.title()
            else:
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
            raw_status = PlanStatusResolver.get_doc_header_status(target_ft)
            if raw_status in ("completed", "concluded"):
                status = "Completed"
            elif raw_status == "passed":
                status = "Passed"
            elif raw_status in ("in progress", "implementing"):
                status = "In Progress"
            elif raw_status in ("confirmed", "planning", "draft", "pending"):
                status = raw_status.title()
            elif raw_status == "unknown":
                status = "Planning"
            else:
                status = raw_status.title()

        # 3. Full Track 判定
        elif p01_req.exists():
            track_type = "Full Track"
            p07_file = plan_dir / "P07_walkthrough.md"
            p06_file = plan_dir / "P06_test_plan.md"
            p05_file = plan_dir / "P05_task.md"
            p04_file = plan_dir / "P04_implementation_plan.md"
            p03_file = plan_dir / "P03_api_spec.md"
            p02_file = plan_dir / "P02_architecture_plan.md"

            if p07_file.exists():
                if PlanStatusResolver.is_doc_completed(p07_file):
                    status = "Completed"
                else:
                    status = "Reviewing/Phase 7"
            elif p06_file.exists() and p05_file.exists() and PlanStatusResolver.get_doc_header_status(p06_file) in ("in progress", "passed", "completed"):
                status = "Testing/Phase 6"
            elif p05_file.exists():
                status = "Implementing/Phase 5"
            elif p04_file.exists():
                status = "Reviewing/Phase 4"
            elif p03_file.exists():
                status = "Designing/Phase 3"
            elif p02_file.exists():
                status = "Designing/Phase 2"
            else:
                status = "Planning/Phase 1"

        # 4. 獨立修訂計畫 (Revision) 判定 (若附掛於 1~3 主計畫則不會進入此分支，保持正交不影響原計畫狀態)
        elif rev_log.exists():
            track_type = "Revision"
            raw_status = PlanStatusResolver.get_doc_header_status(rev_log)
            if raw_status in ("completed", "concluded"):
                status = "Completed"
            elif raw_status == "passed":
                status = "Passed"
            elif raw_status in ("in progress", "implementing"):
                status = "In Progress"
            elif raw_status in ("confirmed", "draft", "pending"):
                status = raw_status.title()
            else:
                status = "In Progress"

        # 5. Research 調研 Track 判定
        elif any(f.is_file() and re.match(r"^R\d{2}_.+\.md$", f.name, re.IGNORECASE) for f in plan_dir.iterdir() if f.is_file()):
            track_type = "Research"
            if PlanStatusResolver.is_research_completed(plan_dir):
                status = "Concluded"
            else:
                status = "Draft"

        # 6. Phase 0 判定
        elif p00_req.exists() or legacy_p00_req.exists():
            track_type = "Phase 0"
            target_p00 = p00_req if p00_req.exists() else legacy_p00_req
            raw_status = PlanStatusResolver.get_doc_header_status(target_p00)
            if raw_status in ("confirmed", "passed", "completed"):
                status = "P00 Confirmed"
            else:
                status = "P00 Discussing"

        # 7. 檢查暫停快照
        if (plan_dir / "handoff.md").exists() and status not in ("Completed", "Concluded"):
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
        # 僅掃描符合時間戳命名規範之活躍計畫目錄 (r"^\d{4}_\d{2}_\d{2}")
        plan_dirs = [
            d for d in self.plans_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".") and re.match(r"^\d{4}_\d{2}_\d{2}", d.name)
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

    def resolve_target_plan_dir(
        self, plan_name_or_subpath: Optional[Union[str, Path]] = None
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        解析目標計畫或子計畫目錄路徑。
        - 若指定 plan_name_or_subpath：支援完整路徑、`<plan_name>`、`<plan_name>/sub_XX` 或唯一 `sub_XX` 名稱。
        - 若未指定：自動篩選尚未 Completed / Concluded 之活躍計畫；若僅有 1 個則自動定位，若超過 1 個則拒絕盲猜並回傳提示訊息（EC-01）。

        Args:
            plan_name_or_subpath: 計畫名稱、子計畫相對路徑或 None

        Returns:
            Tuple[Optional[Path], Optional[str]]: (定位之目標目錄 Path, 錯誤或提示訊息)
        """
        if plan_name_or_subpath:
            raw_str = str(plan_name_or_subpath).strip()
            cand = Path(raw_str)
            if cand.is_absolute() and cand.is_dir():
                return cand.resolve(), None

            rel_cand = (self.plans_dir / raw_str).resolve()
            if rel_cand.is_dir():
                return rel_cand, None

            # 支援直接傳入 sub_XX 名稱（於活躍計畫下搜尋唯一匹配之子計畫目錄）
            if raw_str.startswith("sub_") and self.plans_dir.exists():
                matched_subs: List[Path] = []
                for p_dir in sorted(self.plans_dir.iterdir(), key=lambda x: x.name, reverse=True):
                    if p_dir.is_dir() and re.match(r"^\d{4}_\d{2}_\d{2}", p_dir.name):
                        sub_cand = p_dir / raw_str
                        if sub_cand.is_dir():
                            matched_subs.append(sub_cand.resolve())
                if len(matched_subs) == 1:
                    return matched_subs[0], None
                elif len(matched_subs) > 1:
                    names = ", ".join(f"{m.parent.name}/{m.name}" for m in matched_subs)
                    return None, f"找到多個同名子計畫 '{raw_str}' ({names})，請以 '<plan_name>/{raw_str}' 明確指定。"

            return None, f"找不到指定的計畫目錄：'{raw_str}'。"

        # 未指定時：掃描所有活躍計畫，過濾掉已 Completed / Concluded 的計畫
        plans = self.scan_active_plans()
        if not plans:
            return None, "目前無進行中的開發計畫。"

        in_progress_plans = [
            p for p in plans if p.get("status") not in ("Completed", "Concluded")
        ]
        target_pool = in_progress_plans if in_progress_plans else plans

        if len(target_pool) > 1:
            plan_names = ", ".join(p["name"] for p in target_pool)
            return (
                None,
                f"偵測到多個進行中計畫 ({len(target_pool)} 個: {plan_names})。依零臆測原則，請使用 '--plan <plan_name>' 明確指定目標計畫。",
            )

        return Path(target_pool[0]["path"]).resolve(), None

    def execute_resume(
        self,
        plan_name_or_subpath: Optional[Union[str, Path]] = None,
        consume_handoff: bool = False,
    ) -> Dict[str, Any]:
        """
        執行確定性狀態領航與選配之 `--resume` `handoff.md` 原子閱後即焚 (`Consume & Delete`)。

        Args:
            plan_name_or_subpath: 目標計畫或子計畫路徑/名稱（選填）
            consume_handoff: 是否在讀取 handoff.md 後立即物理刪除 (os.unlink)

        Returns:
            Dict[str, Any]: 結構化領航與恢復結果
        """
        from .status import PlanStatusResolver

        target_dir, err_msg = self.resolve_target_plan_dir(plan_name_or_subpath)
        if err_msg or target_dir is None:
            return {
                "success": False,
                "error": err_msg or "無法定位目標計畫目錄。",
                "handoff_consumed": False,
                "handoff_path": None,
                "handoff_content": None,
                "nav_info": None,
                "formatted_output": f"[agents-workflow:plan] [WARN] {err_msg}",
            }

        nav_info = PlanStatusResolver.resolve_next_action(target_dir)
        actual_dir: Path = nav_info["target_plan_dir"]

        # 檢查目標目錄（如 sub_XX）或外層 Umbrella 目錄是否存在 handoff.md
        handoff_candidates: List[Path] = []
        if (actual_dir / "handoff.md").is_file():
            handoff_candidates.append(actual_dir / "handoff.md")
        if actual_dir != target_dir and (target_dir / "handoff.md").is_file():
            handoff_candidates.append(target_dir / "handoff.md")

        handoff_content: Optional[str] = None
        handoff_path_str: Optional[str] = None
        handoff_consumed = False

        if handoff_candidates:
            h_file = handoff_candidates[0]
            handoff_path_str = str(h_file)
            try:
                handoff_content = h_file.read_text(encoding="utf-8", errors="ignore")
                if consume_handoff:
                    os.unlink(h_file)
                    handoff_consumed = True
                    nav_info["has_handoff"] = False
            except Exception as ex:
                handoff_content = f"[讀取或清理 handoff.md 發生異常: {ex}]"

        out_lines = []
        out_lines.append("=" * 90)
        out_lines.append("[Plan Navigation & State Driver]")
        out_lines.append("-" * 90)
        out_lines.append(f"  * Target Plan        : {nav_info['target_plan_name']}")
        out_lines.append(f"  * Plan Mode          : {nav_info['mode']}")
        out_lines.append(
            f"  * Current Breakpoint : {nav_info['current_phase']} (Status: {nav_info['current_status']})"
        )
        out_lines.append(f"  * Next Phase         : {nav_info['next_phase']}")
        out_lines.append(f"  * Required Reference : {nav_info['required_reference_path']}")
        out_lines.append(f"  * Next Action Hint   : {nav_info['next_action_hint']}")

        if handoff_content is not None:
            out_lines.append("-" * 90)
            action_tag = (
                "CONSUMED & DELETED (閱後即焚已完成)"
                if handoff_consumed
                else "DETECTED (唯讀預覽，加 --resume 可消費刪除)"
            )
            out_lines.append(f"  * Handoff Snapshot   : {action_tag} [{handoff_path_str}]")
            out_lines.append("-" * 90)
            out_lines.append(handoff_content.rstrip())
        else:
            out_lines.append(f"  * Handoff Snapshot   : None (依產出物檔案結構與標頭狀態判定)")

        out_lines.append("=" * 90)

        return {
            "success": True,
            "error": None,
            "handoff_consumed": handoff_consumed,
            "handoff_path": handoff_path_str,
            "handoff_content": handoff_content,
            "nav_info": nav_info,
            "formatted_output": "\n".join(out_lines),
        }

