"""Roadmap 策略資產掃描與摘要管理器 (RoadmapManager)

負責 `workflow.plans://roadmap/` 空間掃描、Markdown AST/Regex Header 元資料提取與問題背景摘要格式化。
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class RoadmapItem:
    """Roadmap 條目結構化模型"""
    topic: str                     # 主題名稱
    filename: str                  # 實體檔案名稱
    path: Path                     # 絕對路徑
    title: str                     # 頂部 H1 標題
    status: str                    # 狀態 (Backlog | Proposed | Deferred | In Progress)
    date: str                      # 歸檔/更新日期 (YYYY-MM-DD)
    problem_summary: str           # 問題背景摘要
    has_valid_header: bool         # 是否具備合規之標準元資料 Header


class RoadmapManager:
    """Roadmap 策略資產掃描與摘要管理器 (零外部依賴)"""

    def __init__(self, roadmap_dir: Optional[Path] = None, host_dir: Optional[str] = None):
        if roadmap_dir is not None:
            self.roadmap_dir = Path(roadmap_dir)
        else:
            resolved = None
            try:
                from core import uri  # type: ignore
                resolved_uri = uri.resolve("workflow.roadmap://")
                if resolved_uri and not resolved_uri.startswith("!"):
                    resolved = Path(resolved_uri)
            except Exception:
                pass

            if resolved is None:
                base = Path(host_dir) if host_dir else Path.cwd()
                # 優先檢查 plans/roadmap，次檢查根目錄 roadmap
                if (base / "plans" / "roadmap").exists():
                    self.roadmap_dir = base / "plans" / "roadmap"
                elif (base / "roadmap").exists():
                    self.roadmap_dir = base / "roadmap"
                else:
                    self.roadmap_dir = base / "plans" / "roadmap"
            else:
                self.roadmap_dir = resolved

    def scan_roadmaps(self) -> List[RoadmapItem]:
        """
        掃描 roadmap_dir 下的所有 *.md 檔案。
        強韌容錯 (EC-04)：逐檔提取 Header 與問題背景區塊，若格式非標準則自動 fallback，絕不拋出例外。
        返回依日期倒序排列的 RoadmapItem 清單。
        """
        if not self.roadmap_dir.exists() or not self.roadmap_dir.is_dir():
            return []

        items: List[RoadmapItem] = []
        for file_path in self.roadmap_dir.glob("*.md"):
            if not file_path.is_file():
                continue
            item = self._parse_roadmap_file(file_path)
            if item:
                items.append(item)

        # 依日期倒序排序
        items.sort(key=lambda x: x.date if x.date else "", reverse=True)
        return items

    def _parse_roadmap_file(self, file_path: Path) -> Optional[RoadmapItem]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return None

        filename = file_path.name
        stem = file_path.stem
        lines = content.splitlines()

        title = stem
        topic = stem
        status = "Backlog"
        date = ""
        has_valid_header = False

        # 提取 H1 標題
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # 提取 Header 區塊引用 (> 主題：..., > 狀態：..., > 歸檔日期：...)
        for line in lines[:30]:
            trimmed = line.strip()
            if trimmed.startswith(">"):
                val = trimmed.lstrip(">").strip()
                if "主題" in val or "Topic" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        topic = m.group(1).strip()
                        has_valid_header = True
                elif "狀態" in val or "Status" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        status = m.group(1).strip()
                        has_valid_header = True
                elif "日期" in val or "Date" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        date = m.group(1).strip()
                        has_valid_header = True

        # 提取 "## 1. 問題陳述" 或 "## 1. 問題背景" 摘要
        summary_lines = []
        in_problem_section = False
        for line in lines:
            if re.match(r"^##\s+1\.\s+.*(問題|背景|陳述|Problem|Background)", line):
                in_problem_section = True
                continue
            if in_problem_section:
                if line.startswith("## "):
                    break
                stripped = line.strip()
                # 過濾子標題與空行
                if stripped and not stripped.startswith("###") and not stripped.startswith("```"):
                    summary_lines.append(stripped)
                    if len(summary_lines) >= 3:
                        break

        if summary_lines:
            problem_summary = " ".join(summary_lines)
            if len(problem_summary) > 200:
                problem_summary = problem_summary[:197] + "..."
        else:
            # Fallback (EC-04): 取前 3 行非空非標題文字
            fallback_lines = []
            for line in lines:
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith(">") and not s.startswith("---"):
                    fallback_lines.append(s)
                    if len(fallback_lines) >= 2:
                        break
            problem_summary = " ".join(fallback_lines) if fallback_lines else "無背景說明摘要"
            if len(problem_summary) > 200:
                problem_summary = problem_summary[:197] + "..."

        return RoadmapItem(
            topic=topic,
            filename=filename,
            path=file_path,
            title=title,
            status=status,
            date=date,
            problem_summary=problem_summary,
            has_valid_header=has_valid_header
        )

    def format_summary_table(self, items: Optional[List[RoadmapItem]] = None) -> str:
        """格式化輸出極簡 ASCII / Markdown 摘要對照表。"""
        if items is None:
            items = self.scan_roadmaps()

        if not items:
            return (
                f"[agents-workflow:roadmap] 目前無任何待啟動之 Roadmap 技術儲備。\n"
                f"掃描目錄: {self.roadmap_dir}\n"
                f"可透過 /Research 調研結案或暫緩計畫沉澱新增技術路線圖。"
            )

        col_w = 90
        divider = "=" * col_w
        header = f"{'Roadmap 主題 / 檔案名稱':<36} | {'狀態':<12} | {'更新日期':<10} | {'核心背景摘要'}"
        sub_divider = "-" * col_w

        rows = [divider, header, sub_divider]
        for item in items:
            topic_disp = item.topic if len(item.topic) <= 34 else item.topic[:31] + "..."
            status_disp = item.status[:12]
            date_disp = item.date[:10] if item.date else "未標註"
            summary_disp = item.problem_summary if len(item.problem_summary) <= 50 else item.problem_summary[:47] + "..."
            rows.append(f"{topic_disp:<36} | {status_disp:<12} | {date_disp:<10} | {summary_disp}")

        rows.append(divider)
        return "\n".join(rows)

    def get_roadmap(self, topic_or_file: str) -> Optional[RoadmapItem]:
        """依主題名稱或檔名精準查找單一 Roadmap 條目。"""
        items = self.scan_roadmaps()
        for item in items:
            if item.topic == topic_or_file or item.filename == topic_or_file or item.filename == f"{topic_or_file}.md":
                return item
        # 模糊包含比對
        for item in items:
            if topic_or_file.lower() in item.topic.lower() or topic_or_file.lower() in item.filename.lower():
                return item
        return None
