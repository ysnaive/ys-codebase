"""
PlanStatusResolver — 開發計畫標頭狀態解析與完成度檢測服務 (SSOT)。
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Union


class PlanStatusResolver:
    """計畫文件標頭狀態提取與完成度解析服務 (SSOT)。"""

    STATUS_KEYS = [
        "狀態",
        "status",
        "計畫狀態",
        "plan_status",
        "調研狀態",
        "research_status",
        "進度",
        "當前所在階段",
    ]

    COMPLETED_STATUS_SET = {"completed", "concluded", "passed"}

    @classmethod
    def parse_header_metadata(cls, lines: List[str], max_lines: int = 35) -> Dict[str, str]:
        """
        結構化解析 Markdown 開頭 Blockquote (> 欄位：值) 中的 Header 元數據。
        
        Args:
            lines: Markdown 行清單
            max_lines: 最大讀取行數 (預設 35)
            
        Returns:
            Dict[str, str]: 小寫欄位名與修剪後的字串字典
        """
        headers: Dict[str, str] = {}
        for line in lines[:max_lines]:
            line_clean = line.strip().replace("\u3000", " ")
            if line_clean.startswith(">"):
                inner = line_clean.lstrip(">").strip()
                if "：" in inner:
                    k, v = inner.split("：", 1)
                    headers[k.strip().lower()] = v.strip()
                elif ":" in inner:
                    k, v = inner.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
        return headers

    @classmethod
    def get_doc_header_status(cls, doc_target: Union[Path, str]) -> str:
        """
        讀取單一 Markdown 文件標頭狀態。
        
        Args:
            doc_target: 文件檔案路徑 (Path/str) 或 Markdown 文字內容 (str)
            
        Returns:
            str: 正規化後之小寫狀態字串 (如 'in progress', 'completed', 'concluded' 等)，若無法解析則回傳 'unknown'。
        """
        content = ""
        if isinstance(doc_target, Path) or (isinstance(doc_target, str) and "\n" not in doc_target and Path(doc_target).exists()):
            p = Path(doc_target)
            if not p.is_file():
                return "unknown"
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return "unknown"
        elif isinstance(doc_target, str):
            content = doc_target
        else:
            return "unknown"

        try:
            lines = content.splitlines()[:35]
            headers = cls.parse_header_metadata(lines)

            for key in cls.STATUS_KEYS:
                if key in headers:
                    val = headers[key].strip()
                    # 排除未替換之模板佔位符如 [Draft | Confirmed ...]
                    if val.startswith("[") and val.endswith("]") and "|" in val:
                        return "unknown"
                    # 正規化常見同義詞
                    norm_val = val.lower()
                    if norm_val in ("in_progress", "implementing", "executing", "active"):
                        return "in progress"
                    return norm_val

            return "unknown"
        except Exception:
            return "unknown"

    @classmethod
    def is_doc_completed(cls, doc_target: Union[Path, str]) -> bool:
        """
        檢驗單一文件是否已完成結案 (依據標頭狀態)。
        
        Args:
            doc_target: 文件檔案路徑或文字內容
            
        Returns:
            bool: 若標頭狀態為 completed, concluded 或 passed 則為 True
        """
        status = cls.get_doc_header_status(doc_target)
        return status in cls.COMPLETED_STATUS_SET

    @classmethod
    def is_research_completed(cls, plan_dir_or_target: Union[Path, str]) -> bool:
        """
        檢驗 Research 計畫是否完成結案 (所有 R{NN}_*.md 檔案標頭皆為 concluded 或 completed)。
        
        Args:
            plan_dir_or_target: 計畫目錄路徑、單一檔案路徑或 Markdown 內容
            
        Returns:
            bool: 若為目錄且所有 R 檔完成，或為單一調研文件且已完成則為 True
        """
        if isinstance(plan_dir_or_target, Path) or (isinstance(plan_dir_or_target, str) and "\n" not in plan_dir_or_target and Path(plan_dir_or_target).exists()):
            p = Path(plan_dir_or_target)
            if p.is_dir():
                r_files = [
                    f for f in p.iterdir()
                    if f.is_file() and re.match(r"^R\d{2}_.+\.md$", f.name, re.IGNORECASE)
                ]
                if not r_files:
                    return False
                return all(cls.is_doc_completed(rf) for rf in r_files)
            elif p.is_file():
                return cls.is_doc_completed(p)

        return cls.is_doc_completed(plan_dir_or_target)

