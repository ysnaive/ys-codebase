"""
PlanSearcher — 歷史開發計畫與決策記錄 (DR) 檢索服務。
"""

import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set

from ._common import resolve_plan_uri


class PlanSearcher:
    """開發計畫歷史與決策記錄檢索引擎。"""

    def __init__(
        self,
        plans_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
    ):
        """
        初始化 PlanSearcher。
        
        Args:
            plans_dir: 進行中計畫目錄。若為 None 則透過 workflow.plans:// 解析。
            archive_dir: 歷史歸檔目錄。若為 None 則透過 workflow.archived:// 解析。
        """
        self.plans_dir = (
            Path(plans_dir).resolve()
            if plans_dir is not None
            else resolve_plan_uri("workflow.plans://", "plans")
        )
        self.archive_dir = (
            Path(archive_dir).resolve()
            if archive_dir is not None
            else resolve_plan_uri("workflow.archived://", "plans/archived")
        )

    def find_all_plans(self, year: Optional[str] = None, month: Optional[str] = None) -> List[Path]:
        """
        收集進行中與歷史歸檔目錄下的所有計畫資料夾。
        
        Args:
            year: 限定年份 (例如 '2026')
            month: 限定月份 (例如 '08')
            
        Returns:
            List[Path]: 計畫目錄列表
        """
        plans: List[Path] = []

        # 1. 進行中計畫 (必須符合時間戳前綴 YYYY_MM_DD)
        if self.plans_dir.is_dir():
            for item in self.plans_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    match = re.match(r"^(\d{4})_(\d{2})_", item.name)
                    if match:
                        y, m = match.group(1), match.group(2)
                        if (year is None or y == year) and (month is None or m == month):
                            plans.append(item)

        # 2. 歷史歸檔計畫 archive_dir/YYYY/MM/
        if self.archive_dir.is_dir():
            for y_dir in sorted(self.archive_dir.iterdir(), reverse=True):
                if y_dir.is_dir() and re.match(r"^\d{4}$", y_dir.name) and (year is None or y_dir.name == year):
                    for m_dir in sorted(y_dir.iterdir(), reverse=True):
                        if m_dir.is_dir() and re.match(r"^\d{2}$", m_dir.name) and (month is None or m_dir.name == month):
                            for p_dir in sorted(m_dir.iterdir(), reverse=True):
                                if p_dir.is_dir() and not p_dir.name.startswith(".") and re.match(r"^\d{4}_\d{2}_\d{2}", p_dir.name):
                                    plans.append(p_dir)

        return plans

    @staticmethod
    def _score_plan_and_file(plan_dir: Path, md_file: Path, is_active: bool) -> Tuple[int, str, int, str]:
        """計算檢索結果之權重排序鍵：(檔案角色優先度, 計畫時間戳, 活躍目錄加權, 檔名)。"""
        fname = md_file.name
        if fname in ("P00_discuss.md", "P07_walkthrough.md", "fast_track_plan.md", "umbrella_overview.md", "revision_log.md") or re.match(
            r"^R\d{2}_.+\.md$", fname, re.IGNORECASE
        ):
            role_weight = 3
        elif fname == "P06_test_plan.md":
            role_weight = 2
        elif re.match(r"^P0[1-5]", fname, re.IGNORECASE):
            role_weight = 1
        else:
            role_weight = 0

        m_date = re.match(r"^(\d{4}_\d{2}_\d{2}(?:_\d{4})?)", plan_dir.name)
        date_key = m_date.group(1) if m_date else plan_dir.name
        active_bonus = 1 if is_active else 0
        return (active_bonus, date_key, role_weight, fname)

    @staticmethod
    def extract_drs_from_content(content: str) -> List[Tuple[str, str]]:
        """
        從 Markdown 文本中提取決策記錄 (DR)。
        支援:
        - ### [P01:DR-01] 標題 或 ### DR-01: 標題
        - - **[P01:DR-01] 標題**：內容
        - - **[P01:DR-01]** 內容
        - - **DR-01**：內容
        
        Returns:
            List[Tuple[str, str]]: [(dr_id, summary), ...]
        """
        results: List[Tuple[str, str]] = []

        # 模式 1: ### DR-01: [標題] 或 ### [P01:DR-01] 標題
        sections = re.split(r"(?=^###\s+.*DR-)", content, flags=re.MULTILINE)
        for sec in sections:
            header_match = re.match(r"^###\s+([^\n]+)", sec)
            if header_match:
                dr_header = header_match.group(1).strip()
                summary_match = re.search(r"-\s*\*\*結論\*\*\s*[:：]\s*(.*)", sec)
                if not summary_match:
                    summary_match = re.search(r"-\s*\*\*議題\*\*\s*[:：]\s*(.*)", sec)
                summary = summary_match.group(1).strip() if summary_match else dr_header
                results.append((dr_header, summary))

        # 模式 2: - **...DR...**：內容 或 - **...DR...** 內容 (相容中英文與冒號省略格式)
        list_matches = re.findall(
            r"-\s*\*\*([^*\r\n]*?DR[^*\r\n]*?)\*\*\s*(?:[:：]\s*|\s+)([^\r\n]+)",
            content,
        )
        for dr_id, summary in list_matches:
            results.append((dr_id.strip(), summary.strip()))

        return results

    def search_drs(
        self,
        query: str = "",
        year: Optional[str] = None,
        month: Optional[str] = None,
        limit: int = 25
    ) -> List[Dict]:
        """
        檢索決策記錄 (DR)。
        
        Returns:
            List[Dict]: DR 檢索結果清單
        """
        plans = self.find_all_plans(year=year, month=month)
        candidates: List[Tuple[Tuple[int, str, int, str], Dict]] = []
        seen_keys: Set[Tuple[str, str, str]] = set()

        for plan in plans:
            is_active = plan.parent == self.plans_dir
            for md_file in sorted(plan.rglob("*.md")):
                try:
                    content = md_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                try:
                    rel_src_str = str(md_file.relative_to(plan)).replace("\\", "/")
                    disp_source = f"{plan.name}/{rel_src_str}" if rel_src_str != "." else plan.name
                except Exception:
                    rel_src_str = md_file.name
                    disp_source = plan.name

                drs = self.extract_drs_from_content(content)
                for dr_id, summary in drs:
                    dedup_key = (plan.name, rel_src_str, dr_id)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    if query:
                        q_lower = query.lower()
                        if (
                            q_lower not in dr_id.lower()
                            and q_lower not in summary.lower()
                            and q_lower not in rel_src_str.lower()
                            and q_lower not in plan.name.lower()
                        ):
                            continue

                    score_key = self._score_plan_and_file(plan, md_file, is_active)
                    candidates.append((
                        score_key,
                        {
                            "plan_name": plan.name,
                            "source_file": disp_source,
                            "dr_id": dr_id,
                            "summary": summary,
                        },
                    ))

        candidates.sort(key=lambda x: (x[0][0], x[0][1], x[0][2]), reverse=True)
        return [item for _, item in candidates[:limit]] if limit > 0 else [item for _, item in candidates]

    def search_full_text(
        self,
        query: str,
        year: Optional[str] = None,
        month: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        跨計畫全文程式碼/文字檢索。
        
        Returns:
            List[Dict]: 匹配項目清單
        """
        if not query:
            return []

        plans = self.find_all_plans(year=year, month=month)
        candidates: List[Tuple[Tuple[int, str, int, str], Dict]] = []
        q_lower = query.lower()

        for plan in plans:
            is_active = plan.parent == self.plans_dir
            for md_file in sorted(plan.rglob("*.md")):
                try:
                    lines = md_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue

                try:
                    rel_path_str = str(md_file.relative_to(plan)).replace("\\", "/")
                except Exception:
                    rel_path_str = str(md_file.name)

                score_key = self._score_plan_and_file(plan, md_file, is_active)
                for idx, line in enumerate(lines):
                    if q_lower in line.lower():
                        start_i = max(0, idx - 1)
                        end_i = min(len(lines), idx + 2)
                        context = [(l_num + 1, lines[l_num]) for l_num in range(start_i, end_i)]

                        candidates.append((
                            score_key,
                            {
                                "plan_name": plan.name,
                                "file_path": md_file,
                                "rel_path": rel_path_str,
                                "line_no": idx + 1,
                                "matched_line": line,
                                "context": context,
                            },
                        ))

        candidates.sort(key=lambda x: (x[0][0], x[0][1], x[0][2]), reverse=True)
        return [item for _, item in candidates[:limit]] if limit > 0 else [item for _, item in candidates]
