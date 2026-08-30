"""
PlanSearcher — 歷史開發計畫與決策記錄 (DR) 檢索服務。
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set


def _resolve_uri_path(uri: str) -> Optional[Path]:
    """安全解析語意 URI，若無 core 上下文則回傳 None。"""
    try:
        from core.uri import resolve
        resolved = resolve(uri)
        return Path(resolved).resolve()
    except Exception:
        return None


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
        if plans_dir is not None:
            self.plans_dir = Path(plans_dir).resolve()
        else:
            res_plans = _resolve_uri_path("workflow.plans://")
            self.plans_dir = res_plans if res_plans else Path.cwd() / "plans"

        if archive_dir is not None:
            self.archive_dir = Path(archive_dir).resolve()
        else:
            res_arch = _resolve_uri_path("workflow.archived://")
            self.archive_dir = res_arch if res_arch else Path.cwd() / "plans" / "archived"

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

        # 1. 進行中計畫
        if self.plans_dir.is_dir():
            for item in self.plans_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    if year or month:
                        match = re.match(r"^(\d{4})_(\d{2})_", item.name)
                        if match:
                            y, m = match.group(1), match.group(2)
                            if (year is None or y == year) and (month is None or m == month):
                                plans.append(item)
                    else:
                        plans.append(item)

        # 2. 歷史歸檔計畫 archive_dir/YYYY/MM/
        if self.archive_dir.is_dir():
            for y_dir in sorted(self.archive_dir.iterdir(), reverse=True):
                if y_dir.is_dir() and (year is None or y_dir.name == year):
                    for m_dir in sorted(y_dir.iterdir(), reverse=True):
                        if m_dir.is_dir() and (month is None or m_dir.name == month):
                            for p_dir in sorted(m_dir.iterdir(), reverse=True):
                                if p_dir.is_dir() and not p_dir.name.startswith("."):
                                    plans.append(p_dir)

        return plans

    @staticmethod
    def extract_drs_from_content(content: str) -> List[Tuple[str, str]]:
        """
        從 Markdown 文本中提取決策記錄 (DR)。
        支援:
        - ### [P01:DR-01] 標題 或 ### DR-01: 標題
        - - **[P01:DR-01] 標題**：內容
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

        # 模式 2: - **...DR...**：內容 (相容中英文與任意符號)
        list_matches = re.findall(
            r"-\s*\*\*(.*?DR.*?)\*\*\s*[:：]\s*(.*)",
            content
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
        results: List[Dict] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for plan in plans:
            for md_file in sorted(plan.rglob("*.md")):
                try:
                    content = md_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                drs = self.extract_drs_from_content(content)
                for dr_id, summary in drs:
                    dedup_key = (plan.name, dr_id)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    if query:
                        q_lower = query.lower()
                        if (
                            q_lower not in dr_id.lower()
                            and q_lower not in summary.lower()
                            and q_lower not in md_file.name.lower()
                        ):
                            continue

                    try:
                        rel_src = md_file.relative_to(plan)
                        disp_source = f"{plan.name}/{rel_src}" if str(rel_src) != "." else plan.name
                    except Exception:
                        disp_source = plan.name

                    results.append({
                        "plan_name": plan.name,
                        "source_file": disp_source,
                        "dr_id": dr_id,
                        "summary": summary,
                    })

                    if len(results) >= limit:
                        return results

        return results

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
        results: List[Dict] = []
        q_lower = query.lower()

        for plan in plans:
            for md_file in sorted(plan.rglob("*.md")):
                try:
                    lines = md_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue

                for idx, line in enumerate(lines):
                    if q_lower in line.lower():
                        start_i = max(0, idx - 1)
                        end_i = min(len(lines), idx + 2)
                        context = [(l_num + 1, lines[l_num]) for l_num in range(start_i, end_i)]

                        results.append({
                            "plan_name": plan.name,
                            "file_path": md_file,
                            "rel_path": str(md_file.name),
                            "line_no": idx + 1,
                            "matched_line": line,
                            "context": context,
                        })

                        if len(results) >= limit:
                            return results

        return results
