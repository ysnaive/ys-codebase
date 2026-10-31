"""
agents_workflow.plans._verifier_specs — PlanVerifier 模板佔位符規則、章節標題正規化與需求 ID 提取器。
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

VALID_STATUSES: Set[str] = {
    "draft", "confirmed", "in progress", "in_progress",
    "passed", "completed", "active", "archived", "pending", "review",
    "discussing", "planning", "executing", "concluded", "aborted", "cancelled",
    "backlog", "proposed", "ready", "deferred", "seeded",
}

ORIGIN_SEED_FILES: Set[str] = {"roadmap.md", "todo.md"}

PLACEHOLDER_PATTERNS: List[str] = [
    r"\[YYYY-MM-DD(?:\s+HH:MM)?\]",
    r"\[功能名稱\]",
    r"\[計畫名稱\]",
    r"\[所屬主計畫\]",
    r"\[待填寫\]",
    r"\[專案名稱\]",
    r"\[模型名稱\]",
    r"\[Model Name\]",
    r"\[主題名稱\]",
    r"\[修訂主題簡述\]",
    r"\[UI/UX/DX\s*\|\s*Parameter\s*\|\s*Docs\]",
    r"\[檔案路徑\]",
    r"\[Draft \|(?:\s*Discussing \|)?\s*Confirmed \| In Progress \| Passed \| Completed\]",
    r"\[Feature \| Refactor \| Bug Fix \| Performance \| Docs(?: \| Revision \| Research)?\]",
    r"\{\{\s*\.\.\.\s*\}\}",
]

PHASE_PREFIX_MAP: Dict[str, str] = {
    "P00": "P00_",
    "P01": "P01_",
    "P02": "P02_",
    "P03": "P03_",
    "P04": "P04_",
    "P05": "P05_",
    "P06": "P06_",
    "P07": "P07_",
}

PHASE_CANONICAL_FILES: Dict[str, str] = {
    "P00": "P00_discuss.md",
    "P01": "P01_requirements_spec.md",
    "P02": "P02_architecture_plan.md",
    "P03": "P03_api_spec.md",
    "P04": "P04_implementation_plan.md",
    "P05": "P05_task.md",
    "P06": "P06_test_plan.md",
    "P07": "P07_walkthrough.md",
}


def extract_dynamic_placeholders(templates_dir: Optional[Path]) -> List[str]:
    """動態自模板目錄提取標頭佔位符正則模式清單。"""
    patterns: List[str] = []
    tmpl_dir = templates_dir
    if not tmpl_dir or not tmpl_dir.exists():
        tmpl_dir = Path(__file__).resolve().parent.parent / "assets" / "templates"

    if tmpl_dir and tmpl_dir.exists():
        try:
            for tmpl_file in tmpl_dir.glob("*.md"):
                content = tmpl_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines()[:35]:
                    line_s = line.strip()
                    if line_s.startswith(">"):
                        matches = re.findall(r"\[([^\]\r\n]+)\]", line_s)
                        for m in matches:
                            m_clean = m.strip()
                            if ("|" in m_clean or re.search(r"[\u4e00-\u9fa5]", m_clean)) and not re.match(r"^REV-\d+", m_clean):
                                if "|" in m_clean:
                                    parts = [re.escape(p.strip()) for p in m_clean.split("|")]
                                    pat = r"\[\s*" + r"\s*\|\s*".join(parts) + r"\s*\]"
                                else:
                                    pat = r"\[" + re.escape(m_clean) + r"\]"
                                try:
                                    re.compile(pat)
                                    patterns.append(pat)
                                except re.error:
                                    pass
        except Exception:
            pass

    seen: Set[str] = set()
    unique_patterns: List[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique_patterns.append(p)
    return unique_patterns


def normalize_header_title(header_line: str) -> str:
    """
    正規化 Markdown 標題文字，去除前綴 '#'、數字編號與中英空白以利語意比對。
    例: '## 1. 使用者原始需求與意圖 (User Intent)' -> '使用者原始需求與意圖'
    """
    raw = header_line.lstrip("#").strip()
    raw = re.sub(r"^\d+(\.\d+)*\s*[\.、]?\s*", "", raw)
    core = re.sub(r"\(.*?\)|（.*?）", "", raw).strip()
    core = re.sub(r"(清冊|清單|列表|說明書|說明|紀錄表|紀錄|記錄|查閱)$", "", core)
    return core.lower().replace(" ", "").replace("_", "").replace("-", "")


def is_header_match(exp_norm: str, doc_norm: str) -> bool:
    """
    判斷模板預期章節與文件實際章節是否匹配。
    防範否定詞前綴（如「非功能需求」vs「功能需求」）因模糊子字串包含而產生誤匹配。
    """
    if not exp_norm or not doc_norm:
        return False
    if exp_norm == doc_norm:
        return True
    shorter, longer = (exp_norm, doc_norm) if len(exp_norm) < len(doc_norm) else (doc_norm, exp_norm)
    pos = longer.find(shorter)
    if pos == -1:
        return False
    if pos > 0 and longer[pos - 1] in ("非", "不", "無", "未"):
        return False
    return True


def load_template_header_specs(
    template_name: str,
    templates_dir: Optional[Path],
) -> List[Tuple[str, str]]:
    """讀取已解析之標準模板並提取其定義之 Markdown 二/三級章節標題，回傳 [(norm_title, raw_heading_line), ...] 清單。"""
    specs: List[Tuple[str, str]] = []
    tmpl_path = None
    if templates_dir and templates_dir.exists():
        cand = templates_dir / template_name
        if cand.exists():
            tmpl_path = cand

    if not tmpl_path:
        cand = Path(__file__).resolve().parent.parent / "assets" / "templates" / template_name
        if cand.exists():
            tmpl_path = cand

    if tmpl_path and tmpl_path.exists():
        try:
            content = tmpl_path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line_s = line.strip()
                if line_s.startswith("##") or line_s.startswith("###"):
                    if re.search(r"\[REV-\d+\]", line_s, re.IGNORECASE):
                        continue
                    norm = normalize_header_title(line_s)
                    if norm and len(norm) >= 2:
                        specs.append((norm, line_s))
        except Exception:
            pass
    return specs


def map_file_to_template(file_name: str, templates_dir: Optional[Path] = None) -> Optional[str]:
    """將計畫檔案對齊至標準模板名稱。"""
    base = os.path.basename(file_name)
    if base.startswith("P00_"):
        if templates_dir and (templates_dir / base).exists():
            return base
        return "P00_discuss.md"
    if base.startswith("P01_"):
        return "P01_requirements_spec.md"
    if base.startswith("P02_"):
        return "P02_architecture_plan.md"
    if base.startswith("P03_"):
        return "P03_api_spec.md"
    if base.startswith("P04_"):
        return "P04_implementation_plan.md"
    if base.startswith("P05_"):
        return "P05_task.md"
    if base.startswith("P06_"):
        return "P06_test_plan.md"
    if base.startswith("P07_"):
        return "P07_walkthrough.md"
    if re.match(r"^R\d{2}_.+\.md$", base, re.IGNORECASE):
        return "RXX_research_report.md"
    if base in ("fast_track_plan.md", "umbrella_overview.md", "revision_log.md", "handoff.md", "changelog.md"):
        return base
    return None


def extract_requirement_ids(markdown_text: str) -> Set[str]:
    """
    從 P01_requirements_spec.md 文本提取有效需求 ID 集合 (FR-XX, EC-XX, NFR-XX)。
    提取前依序預先剝除：
      1. Fenced Code Blocks (```...```)
      2. HTML 註解區塊 (<!--...-->)
      3. Markdown 刪除線語法 (~~...~~)
    """
    if not markdown_text:
        return set()

    cleaned = re.sub(r"```[\s\S]*?```", "", markdown_text)
    cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
    cleaned = re.sub(r"~~[\s\S]*?~~", "", cleaned)

    matches = re.findall(r"\b(?:FR|EC|NFR)-\d+\b", cleaned, flags=re.IGNORECASE)
    return {m.upper() for m in matches}
