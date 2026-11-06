"""
PlanScanner — 進行中開發計畫狀態掃描與矩陣渲染服務。
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ._common import resolve_plan_uri

_RESEARCH_DOC_RE = re.compile(r"^R\d{2}_.+\.md$", re.IGNORECASE)
_PLAN_DATE_PREFIX_RE = re.compile(r"^\d{4}_\d{2}_\d{2}")
_CHECKLIST_ITEM_RE = re.compile(r"^\s*-\s*\[([xX ])\]\s+(.+)")


class PlanScanner:
    """進行中開發計畫狀態掃描引擎。"""

    def __init__(self, plans_dir: Optional[Path] = None):
        """
        初始化 PlanScanner。

        Args:
            plans_dir: 進行中計畫目錄路徑。若為 None 則透過 workflow.plans:// 解析。
        """
        self.plans_dir = (
            Path(plans_dir).resolve()
            if plans_dir is not None
            else resolve_plan_uri("workflow.plans://", "plans")
        )

    def _resolve_umbrella_status(self, plan_dir: Path, umbrella: Path) -> str:
        """判定 Umbrella 主計畫狀態。"""
        from .status import PlanStatusResolver

        raw_status = PlanStatusResolver.get_doc_header_status(umbrella)
        if raw_status in ("completed", "concluded"):
            return "Completed"
        if raw_status in ("in progress", "executing", "implementing"):
            return "In Progress"
        if raw_status in ("planning", "discussing", "draft", "phase 0"):
            return "Planning" if raw_status == "planning" else raw_status.title()

        sub_dirs = [d for d in plan_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")]
        if not sub_dirs:
            return "Planning"
        sub_statuses = [self.get_plan_info(sd)[1] for sd in sub_dirs]
        return "Completed" if all("Completed" in s for s in sub_statuses) else "In Progress"

    @staticmethod
    def _resolve_fast_track_status(ft_plan: Path) -> str:
        """判定 Fast Track 計畫狀態。"""
        from .status import PlanStatusResolver

        raw_status = PlanStatusResolver.get_doc_header_status(ft_plan)
        if raw_status in ("completed", "concluded"):
            return "Completed"
        if raw_status == "passed":
            return "Passed"
        if raw_status in ("in progress", "implementing"):
            return "In Progress"
        if raw_status == "unknown":
            return "Planning"
        return raw_status.title()

    @staticmethod
    def _resolve_full_track_status(plan_dir: Path) -> str:
        """判定 Full Track 計畫狀態（支援標準檔名與 _auto.md 後綴雙軌相容）。"""
        from .status import PlanStatusResolver

        p07_file = PlanStatusResolver.resolve_phase_file(plan_dir, "P07")
        if p07_file.exists():
            return "Completed" if PlanStatusResolver.is_doc_completed(p07_file) else "Reviewing/Phase 7"

        p06_file = PlanStatusResolver.resolve_phase_file(plan_dir, "P06")
        p05_file = PlanStatusResolver.resolve_phase_file(plan_dir, "P05")
        if (
            p06_file.exists()
            and p05_file.exists()
            and PlanStatusResolver.get_doc_header_status(p06_file) in ("in progress", "passed", "completed")
        ):
            return "Testing/Phase 6"
        if p05_file.exists():
            return "Implementing/Phase 5"
        if PlanStatusResolver.resolve_phase_file(plan_dir, "P04").exists():
            return "Reviewing/Phase 4"
        if PlanStatusResolver.resolve_phase_file(plan_dir, "P03").exists():
            return "Designing/Phase 3"
        if PlanStatusResolver.resolve_phase_file(plan_dir, "P02").exists():
            return "Designing/Phase 2"
        return "Planning/Phase 1"

    @staticmethod
    def _resolve_revision_status(rev_log: Path) -> str:
        """判定獨立修訂計畫 (Revision) 狀態。"""
        from .status import PlanStatusResolver

        raw_status = PlanStatusResolver.get_doc_header_status(rev_log)
        if raw_status in ("completed", "concluded"):
            return "Completed"
        if raw_status == "passed":
            return "Passed"
        if raw_status in ("in progress", "implementing"):
            return "In Progress"
        if raw_status in ("confirmed", "draft", "pending"):
            return raw_status.title()
        return "In Progress"

    def get_plan_info(self, plan_dir: Path) -> Tuple[str, str]:
        """
        解析單一計畫目錄的 Track 與當前狀態。

        Args:
            plan_dir: 計畫目錄路徑

        Returns:
            Tuple[str, str]: (track_type, status)
        """
        from .status import PlanStatusResolver

        ft_plan = plan_dir / "fast_track_plan.md"
        p00_req = PlanStatusResolver.resolve_phase_file(plan_dir, "P00")
        p01_req = PlanStatusResolver.resolve_phase_file(plan_dir, "P01")
        umbrella = plan_dir / "umbrella_overview.md"
        rev_log = plan_dir / "revision_log.md"

        track_type = "Unknown"
        status = "Unknown"

        if umbrella.exists():
            track_type = "Umbrella"
            status = self._resolve_umbrella_status(plan_dir, umbrella)
        elif ft_plan.exists():
            track_type = "Fast Track"
            status = self._resolve_fast_track_status(ft_plan)
        elif p01_req.exists():
            track_type = "Full Track"
            status = self._resolve_full_track_status(plan_dir)
        elif rev_log.exists():
            track_type = "Revision"
            status = self._resolve_revision_status(rev_log)
        elif any(f.is_file() and _RESEARCH_DOC_RE.match(f.name) for f in plan_dir.iterdir() if f.is_file()):
            track_type = "Research"
            status = "Concluded" if PlanStatusResolver.is_research_completed(plan_dir) else "Draft"
        elif p00_req.exists():
            track_type = "Phase 0"
            raw_status = PlanStatusResolver.get_doc_header_status(p00_req)
            status = "P00 Confirmed" if raw_status in ("confirmed", "passed", "completed") else "P00 Discussing"
        elif (plan_dir / "roadmap.md").is_file() or (plan_dir / "todo.md").is_file():
            track_type = "Seeded"
            status = "Seeded (Pending Plan)"

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
        plan_dirs = [
            d for d in self.plans_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".") and _PLAN_DATE_PREFIX_RE.match(d.name)
        ]

        for p_dir in sorted(plan_dirs, key=lambda x: x.name, reverse=True):
            track_type, status = self.get_plan_info(p_dir)
            sub_list = []

            sub_dirs = sorted(
                [d for d in p_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")],
                key=lambda x: x.name,
            )
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
        completed_top = [p["name"] for p in plans if p.get("status") in ("Completed", "Concluded")]
        if completed_top:
            sample_cmd = f"python yscb.py agents-workflow plan archive {completed_top[0]}"
            lines.append(
                f"[HINT] 偵測到 {len(completed_top)} 個已結案計畫 ({', '.join(completed_top)})，可依開發者指示執行 `{sample_cmd}` 歸檔。"
            )
        return "\n".join(lines)

    def resolve_target_plan_dir(
        self, plan_name_or_subpath: Optional[Union[str, Path]] = None
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        解析目標計畫或子計畫目錄路徑。
        - 若指定 plan_name_or_subpath：支援完整路徑、`<plan_name>`、`<plan_name>/sub_XX` 或唯一 `sub_XX` 名稱。
        - 若未指定：自動篩選尚未 Completed / Concluded 之活躍計畫；若僅有 1 個則自動定位，若超過 1 個則拒絕盲猜並回傳提示訊息。
        """
        if plan_name_or_subpath:
            raw_str = str(plan_name_or_subpath).strip()
            cand = Path(raw_str)
            if cand.is_absolute() and cand.is_dir():
                return cand.resolve(), None

            rel_cand = (self.plans_dir / raw_str).resolve()
            if rel_cand.is_dir():
                return rel_cand, None

            if raw_str.startswith("sub_") and self.plans_dir.exists():
                matched_subs: List[Path] = []
                for p_dir in sorted(self.plans_dir.iterdir(), key=lambda x: x.name, reverse=True):
                    if p_dir.is_dir() and _PLAN_DATE_PREFIX_RE.match(p_dir.name):
                        sub_cand = p_dir / raw_str
                        if sub_cand.is_dir():
                            matched_subs.append(sub_cand.resolve())
                if len(matched_subs) == 1:
                    return matched_subs[0], None
                elif len(matched_subs) > 1:
                    names = ", ".join(f"{m.parent.name}/{m.name}" for m in matched_subs)
                    return None, f"找到多個同名子計畫 '{raw_str}' ({names})，請以 '<plan_name>/{raw_str}' 明確指定。"

            return None, f"找不到指定的計畫目錄：'{raw_str}'。"

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

    @staticmethod
    def _extract_capsule_drs(plan_dir: Path) -> List[str]:
        """提取恢復上下文膠囊之關鍵決策紀錄 (DRs，最多 5 筆)。"""
        from .searcher import PlanSearcher
        from .status import PlanStatusResolver

        drs: List[str] = []
        dr_sources: List[Path] = []
        for code in ("P00", "P02", "P03", "P04"):
            f = PlanStatusResolver.resolve_phase_file(plan_dir, code)
            if f.is_file() and f not in dr_sources:
                dr_sources.append(f)
        for extra_name in ("fast_track_plan.md", "revision_log.md", "umbrella_overview.md"):
            ef = plan_dir / extra_name
            if ef.is_file() and ef not in dr_sources:
                dr_sources.append(ef)

        seen_dr_ids = set()
        for src_f in dr_sources:
            try:
                extracted = PlanSearcher.extract_drs_from_content(
                    src_f.read_text(encoding="utf-8", errors="ignore")
                )
                for did, summ in extracted:
                    if did not in seen_dr_ids:
                        seen_dr_ids.add(did)
                        short_s = summ if len(summ) <= 70 else summ[:67] + "..."
                        drs.append(f"{did}: {short_s}")
                        if len(drs) >= 5:
                            break
            except Exception:
                continue
            if len(drs) >= 5:
                break
        return drs

    @staticmethod
    def _extract_capsule_impacted_files(plan_dir: Path) -> List[str]:
        """提取恢復上下文膠囊之受影響檔案清單 (最多 8 筆)。"""
        from .status import PlanStatusResolver

        impacted_files: List[str] = []
        file_sources: List[Path] = []
        p02_f = PlanStatusResolver.resolve_phase_file(plan_dir, "P02")
        if p02_f.is_file():
            file_sources.append(p02_f)
        for extra_name in ("fast_track_plan.md", "revision_log.md"):
            ef = plan_dir / extra_name
            if ef.is_file() and ef not in file_sources:
                file_sources.append(ef)

        for src_f in file_sources:
            try:
                is_spec_file = src_f.name not in ("fast_track_plan.md", "revision_log.md")
                for line in src_f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if is_spec_file and s.startswith(("## 3.", "## 4.")):
                        break
                    if s.startswith("|") and ("Modify" in s or "New" in s or "Delete" in s):
                        cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
                        if not cells or not cells[0]:
                            continue
                        cand = cells[0].strip("*").strip()
                        if cand in ("檔案路徑", "文件路徑", "衝擊維度", "維度", "---", ":---"):
                            continue
                        if "/" not in cand and "." not in cand:
                            continue
                        if cand not in impacted_files:
                            impacted_files.append(cand)
                            if len(impacted_files) >= 8:
                                break
            except Exception:
                continue
            if len(impacted_files) >= 8:
                break
        return impacted_files

    @staticmethod
    def _extract_capsule_task_progress(plan_dir: Path) -> Tuple[int, List[str]]:
        """提取恢復上下文膠囊之任務進度與待辦清單 (checked_cnt, unchecked_items)。"""
        from .status import PlanStatusResolver

        checked_cnt = 0
        unchecked_items: List[str] = []
        task_sources: List[Path] = []
        for code in ("P05", "P04"):
            tf = PlanStatusResolver.resolve_phase_file(plan_dir, code)
            if tf.is_file() and tf not in task_sources:
                task_sources.append(tf)
        for extra_name in ("fast_track_plan.md", "revision_log.md"):
            ef = plan_dir / extra_name
            if ef.is_file() and ef not in task_sources:
                task_sources.append(ef)

        for src_f in task_sources:
            try:
                for line in src_f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    m_chk = _CHECKLIST_ITEM_RE.match(line)
                    if m_chk:
                        mark, item_txt = m_chk.group(1), m_chk.group(2).strip()
                        if mark.lower() == "x":
                            checked_cnt += 1
                        else:
                            short_it = item_txt if len(item_txt) <= 75 else item_txt[:72] + "..."
                            unchecked_items.append(short_it)
            except Exception:
                continue
        return checked_cnt, unchecked_items

    def build_recovery_capsule(self, plan_dir: Path) -> str:
        """
        當目標計畫未建立 handoff.md 時，從現有計畫檔案確定性提取恢復上下文膠囊：
        1. 關鍵決策紀錄 (DRs)
        2. 受影響檔案清單 (Impacted Files)
        3. 任務進度與待完成項目 (Task Progress & Next Unchecked Items)
        """
        drs = self._extract_capsule_drs(plan_dir)
        impacted_files = self._extract_capsule_impacted_files(plan_dir)
        checked_cnt, unchecked_items = self._extract_capsule_task_progress(plan_dir)

        cap_lines: List[str] = []
        if drs:
            cap_lines.append("  * Key Decisions (DRs):")
            for d_str in drs:
                cap_lines.append(f"    - {d_str}")
        if impacted_files:
            cap_lines.append(f"  * Impacted Files     : {', '.join(impacted_files)}")
        total_tasks = checked_cnt + len(unchecked_items)
        if total_tasks > 0:
            cap_lines.append(
                f"  * Checklist Progress : {checked_cnt}/{total_tasks} completed ({len(unchecked_items)} remaining)"
            )
            for u_it in unchecked_items[:3]:
                cap_lines.append(f"    - [ ] {u_it}")
        return "\n".join(cap_lines)

    def execute_resume(
        self,
        plan_name_or_subpath: Optional[Union[str, Path]] = None,
        consume_handoff: bool = False,
    ) -> Dict[str, Any]:
        """
        執行確定性狀態領航與選配之 `--resume` `handoff.md` 原子閱後即焚 (`Consume & Delete`)。
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

        recovery_capsule = ""
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
            out_lines.append("  * Handoff Snapshot   : None (依產出物檔案結構與標頭狀態判定)")
            recovery_capsule = self.build_recovery_capsule(actual_dir)
            if recovery_capsule:
                out_lines.append("-" * 90)
                out_lines.append("[Deterministic Context Recovery Capsule]")
                out_lines.append(recovery_capsule)

        out_lines.append("=" * 90)

        return {
            "success": True,
            "error": None,
            "handoff_consumed": handoff_consumed,
            "handoff_path": handoff_path_str,
            "handoff_content": handoff_content,
            "recovery_capsule": recovery_capsule,
            "nav_info": nav_info,
            "formatted_output": "\n".join(out_lines),
        }
