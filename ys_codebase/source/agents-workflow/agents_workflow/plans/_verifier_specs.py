"""
agents_workflow.plans._verifier_specs — PlanVerifier 模板佔位符規則、章節標題正規化與需求 ID 提取器。
"""

import os
import re
from pathlib import Path
from types import MappingProxyType
from typing import Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

VALID_STATUSES: FrozenSet[str] = frozenset({
    "draft", "confirmed", "in progress", "in_progress", "implementing",
    "passed", "completed", "active", "archived", "pending", "review",
    "discussing", "planning", "executing", "concluded", "aborted", "cancelled",
    "backlog", "proposed", "ready", "deferred", "seeded", "phase 0",
})

ORIGIN_SEED_FILES: FrozenSet[str] = frozenset({"roadmap.md", "todo.md"})

HEADER_NAME_KEYS: Tuple[str, ...] = (
    "功能名稱", "計畫名稱", "所屬計畫", "name", "title", "調研主題", "topic", "subject", "主題",
)
HEADER_DATE_KEYS: Tuple[str, ...] = (
    "建立日期", "完成日期", "暫停時間", "歸檔日期", "更新日期",
    "date", "created_at", "updated_at", "archived_at", "日期", "time", "timestamp",
)
HEADER_STATUS_KEYS: Tuple[str, ...] = (
    "狀態", "status", "調研狀態", "research_status", "plan_status", "計畫狀態", "進度", "當前所在階段",
)
HEADER_PARENT_KEYS: Tuple[str, ...] = (
    "所屬主計畫", "所屬計畫", "parent_plan", "主計畫", "parent",
)
HEADER_MODEL_KEYS: Tuple[str, ...] = (
    "模型", "model", "ai_model", "ai-model", "模型名稱", "model_name",
)

PLACEHOLDER_PATTERNS: Tuple[str, ...] = (
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
)

PHASE_PREFIX_MAP: Mapping[str, str] = MappingProxyType({
    "P00": "P00_",
    "P01": "P01_",
    "P02": "P02_",
    "P03": "P03_",
    "P04": "P04_",
    "P05": "P05_",
    "P06": "P06_",
    "P07": "P07_",
})

PHASE_CANONICAL_FILES: Mapping[str, str] = MappingProxyType({
    "P00": "P00_discuss.md",
    "P01": "P01_requirements_spec.md",
    "P02": "P02_architecture_plan.md",
    "P03": "P03_api_spec.md",
    "P04": "P04_implementation_plan.md",
    "P05": "P05_task.md",
    "P06": "P06_test_plan.md",
    "P07": "P07_walkthrough.md",
})

_BRACKET_TOKEN_RE = re.compile(r"\[([^\]\r\n]+)\]")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fa5]")
_REV_PREFIX_RE = re.compile(r"^REV-\d+")
_HEADER_NUM_PREFIX_RE = re.compile(r"^\d+(\.\d+)*\s*[\.、]?\s*")
_HEADER_PARENS_RE = re.compile(r"\(.*?\)|（.*?）")
_HEADER_SUFFIX_RE = re.compile(r"(清冊|清單|列表|說明書|說明|紀錄表|紀錄|記錄|查閱)$")
_H2_SECTION_NUM_RE = re.compile(r"^##\s*(\d+)\.")
_REV_TAG_RE = re.compile(r"\[REV-\d+\]", re.IGNORECASE)
_AUTO_RANGE_FILE_RE = re.compile(r"^P0[1-5]-05_auto\.md$", re.IGNORECASE)
_RESEARCH_REPORT_FILE_RE = re.compile(r"^R\d{2}_.+\.md$", re.IGNORECASE)
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_STRIKETHROUGH_RE = re.compile(r"~~[\s\S]*?~~")
_REQ_ID_RE = re.compile(r"\b(?:FR|EC|NFR)-\d+\b", re.IGNORECASE)


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
                        matches = _BRACKET_TOKEN_RE.findall(line_s)
                        for m in matches:
                            m_clean = m.strip()
                            if ("|" in m_clean or _CJK_CHAR_RE.search(m_clean)) and not _REV_PREFIX_RE.match(m_clean):
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
    raw = _HEADER_NUM_PREFIX_RE.sub("", raw)
    core = _HEADER_PARENS_RE.sub("", raw).strip()
    core = _HEADER_SUFFIX_RE.sub("", core)
    return core.lower().replace(" ", "").replace("_", "").replace("-", "")


def extract_markdown_headers(lines: List[str]) -> List[str]:
    """自 Markdown 行清單提取非程式碼區塊之二/三級章節正規化標題清單。"""
    doc_headers: List[str] = []
    in_code_block = False
    for line in lines:
        line_s = line.strip()
        if line_s.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if line_s.startswith("##") or line_s.startswith("###"):
            norm = normalize_header_title(line_s)
            if norm:
                doc_headers.append(norm)
    return doc_headers


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
    min_phase: int = 1,
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
            current_h2_phase = 0
            in_code_block = False
            for line in content.splitlines():
                line_s = line.strip()
                if line_s.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue
                if line_s.startswith("##") and not line_s.startswith("###"):
                    m_sec = _H2_SECTION_NUM_RE.match(line_s)
                    current_h2_phase = int(m_sec.group(1)) if m_sec else 0
                if line_s.startswith("##") or line_s.startswith("###"):
                    if template_name == "PXX-05_auto.md" and min_phase > 1 and 0 < current_h2_phase < min_phase:
                        continue
                    if _REV_TAG_RE.search(line_s):
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
    if _AUTO_RANGE_FILE_RE.match(base) or base == "PXX-05_auto.md":
        return "PXX-05_auto.md"
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
    if _RESEARCH_REPORT_FILE_RE.match(base):
        return "RXX_research_report.md"
    if base in ("fast_track_plan.md", "umbrella_overview.md", "revision_log.md", "handoff.md", "changelog.md"):
        return base
    return None


def extract_requirement_ids(markdown_text: str) -> Set[str]:
    """
    從 P01_requirements_spec.md 或 P06_test_plan.md 文本提取有效需求 ID 集合 (FR-XX, EC-XX, NFR-XX)。
    提取前依序預先剝除：
      1. Fenced Code Blocks (```...```)
      2. HTML 註解區塊 (<!--...-->)
      3. Markdown 刪除線語法 (~~...~~)
    """
    if not markdown_text:
        return set()

    cleaned = _FENCED_CODE_RE.sub("", markdown_text)
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)
    cleaned = _STRIKETHROUGH_RE.sub("", cleaned)

    matches = _REQ_ID_RE.findall(cleaned)
    return {m.upper() for m in matches}
