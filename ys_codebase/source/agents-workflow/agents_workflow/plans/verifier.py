"""
PlanVerifier — 開發計畫規範、動態模板鏡像與合規性稽核引擎。
"""

import os
import re
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple, Set


class PlanSeverity(str, Enum):
    """計畫檢核嚴重度枚舉。"""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class PlanIssue:
    """單一診斷問題項目。"""
    severity: PlanSeverity
    file_name: str
    category: str
    message: str
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "file": self.file_name,
            "line": self.line_number,
            "category": self.category,
            "message": self.message,
        }


@dataclass
class PlanReport:
    """計畫檢核報告實體（支援向下相容 Tuple 解構）。"""
    plan_name: str
    plan_path: str
    status: PlanSeverity = PlanSeverity.PASS
    issues: List[PlanIssue] = field(default_factory=list)
    companion_created: List[str] = field(default_factory=list)
    log_status: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status != PlanSeverity.FAIL

    @property
    def has_fails(self) -> bool:
        return any(i.severity == PlanSeverity.FAIL for i in self.issues)

    @property
    def has_warns(self) -> bool:
        return any(i.severity == PlanSeverity.WARN for i in self.issues)

    @property
    def errors(self) -> List[str]:
        return [
            f"({i.file_name}:{i.line_number or 0}) [{i.category}] {i.message}"
            for i in self.issues
            if i.severity == PlanSeverity.FAIL
        ]

    @property
    def warnings(self) -> List[str]:
        return [
            f"({i.file_name}:{i.line_number or 0}) [{i.category}] {i.message}"
            for i in self.issues
            if i.severity == PlanSeverity.WARN
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "plan_path": self.plan_path,
            "status": self.status.value,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "total_errors": len(self.errors),
            "total_warns": len(self.warnings),
            "companion_created": list(self.companion_created),
            "log_status": self.log_status,
        }

    def __iter__(self):
        # 支援 Tuple 解包: passed, errors = verifier.verify_plan(name)
        yield self.passed
        yield self.errors

    def __getitem__(self, index: int):
        if index == 0:
            return self.passed
        elif index == 1:
            return self.errors
        raise IndexError("PlanReport index out of range (0=passed, 1=errors)")


from . import _resolve_uri_path


class PlanVerifier:
    """開發計畫文件合規性稽核引擎 (4-Stage Verification Pipeline)。"""

    VALID_STATUSES = {
        "draft", "confirmed", "in progress", "in_progress",
        "passed", "completed", "active", "archived", "pending", "review",
        "discussing", "planning", "executing", "concluded", "aborted", "cancelled",
        "backlog", "proposed", "ready", "deferred", "seeded"
    }

    ORIGIN_SEED_FILES = {"roadmap.md", "todo.md"}

    # 模板佔位符正則（未替換即違規）
    PLACEHOLDER_PATTERNS = [
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

    def __init__(
        self,
        plans_dir: Optional[Union[str, Path]] = None,
        archive_dir: Optional[Union[str, Path]] = None,
        templates_dir: Optional[Union[str, Path]] = None,
    ):
        """
        初始化 PlanVerifier。
        """
        if plans_dir is not None:
            self.plans_dir = Path(plans_dir).resolve()
        else:
            self.plans_dir = _resolve_uri_path("workflow.plans://", default_fallback="plans")

        if archive_dir is not None:
            self.archive_dir = Path(archive_dir).resolve()
        else:
            self.archive_dir = _resolve_uri_path("workflow.archived://", default_fallback="plans/archived")

        if templates_dir is not None:
            self.templates_dir = Path(templates_dir).resolve()
        else:
            # 優先搜尋編譯展開之快取模板
            res_tmpl = _resolve_uri_path("cache://agents-workflow/resolved_contents/templates")
            if not res_tmpl or not res_tmpl.exists():
                res_tmpl = _resolve_uri_path("project://.agents/.yscb/templates")
            if not res_tmpl or not res_tmpl.exists():
                # 宿主回退定位
                cand = Path.cwd() / ".cache" / "agents-workflow" / "resolved_contents" / "templates"
                res_tmpl = cand if cand.exists() else None
            self.templates_dir = res_tmpl

        self._template_headers_cache: Dict[str, List[str]] = {}
        self._dynamic_placeholders_cache: Optional[List[str]] = None

    def get_dynamic_placeholders(self) -> List[str]:
        """動態自模板目錄提取標頭佔位符正則模式清單。"""
        if self._dynamic_placeholders_cache is not None:
            return self._dynamic_placeholders_cache

        patterns: List[str] = []
        tmpl_dir = self.templates_dir
        if not tmpl_dir or not tmpl_dir.exists():
            tmpl_dir = Path(__file__).resolve().parent.parent / "assets" / "templates"

        if tmpl_dir and tmpl_dir.exists():
            try:
                for tmpl_file in tmpl_dir.glob("*.md"):
                    content = tmpl_file.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()[:35]
                    for line in lines:
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

        seen = set()
        unique_patterns = []
        for p in patterns:
            if p not in seen:
                seen.add(p)
                unique_patterns.append(p)

        self._dynamic_placeholders_cache = unique_patterns
        return self._dynamic_placeholders_cache

    def get_all_placeholder_patterns(self) -> List[str]:
        """獲取靜態與動態合併之全量佔位符正則清單。"""
        dyn = self.get_dynamic_placeholders()
        seen = set(self.PLACEHOLDER_PATTERNS)
        res = list(self.PLACEHOLDER_PATTERNS)
        for p in dyn:
            if p not in seen:
                seen.add(p)
                res.append(p)
        return res

    @staticmethod
    def parse_plan_header(lines: List[str]) -> Dict[str, str]:
        """結構化解析 Markdown 開頭 Blockquote (> 欄位：值) 中的 Header 元數據。"""
        headers = {}
        for line in lines[:35]:
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

    @staticmethod
    def normalize_header_title(header_line: str) -> str:
        """
        正規化 Markdown 標題文字，去除前綴 '#'、數字編號與中英空白以利語意比對。
        例: '## 1. 使用者原始需求與意圖 (User Intent)' -> '使用者原始需求與意圖'
        """
        raw = header_line.lstrip("#").strip()
        # 移除前綴編號如 '1. ', '1.1 ', '一、'
        raw = re.sub(r"^\d+(\.\d+)*\s*[\.、]?\s*", "", raw)
        # 移除英文/中文括號內容以提取核心詞
        core = re.sub(r"\(.*?\)|（.*?）", "", raw).strip()
        # 移除常見後綴以提高容錯對齊度
        core = re.sub(r"(清冊|清單|列表|說明書|說明|紀錄表|紀錄|記錄|查閱)$", "", core)
        return core.lower().replace(" ", "").replace("_", "").replace("-", "")


    def get_resolved_template_headers(self, template_name: str) -> List[str]:
        """
        讀取已解析之標準模板並提取其定義之 Markdown 章節標題 (# Headers)。
        """
        if template_name in self._template_headers_cache:
            return self._template_headers_cache[template_name]

        headers: List[str] = []
        tmpl_path = None
        if self.templates_dir and self.templates_dir.exists():
            cand = self.templates_dir / template_name
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
                    if line_s.startswith("#"):
                        # 僅擷取二級與三級核心章節標題（排除 [REV-XX] 動態修訂條目標題）
                        if line_s.startswith("##") or line_s.startswith("###"):
                            if re.search(r"\[REV-\d+\]", line_s, re.IGNORECASE):
                                continue
                            norm = self.normalize_header_title(line_s)
                            if norm and len(norm) >= 2:
                                headers.append(norm)
            except Exception:
                pass

        self._template_headers_cache[template_name] = headers
        return headers

    def _map_file_to_template(self, file_name: str) -> Optional[str]:
        """將計畫檔案對齊至標準模板名稱。"""
        base = os.path.basename(file_name)
        if base.startswith("P00_"):
            if self.templates_dir and (self.templates_dir / base).exists():
                return base
            if self.templates_dir and (self.templates_dir / "P00_discuss.md").exists():
                return "P00_discuss.md"
            if self.templates_dir and (self.templates_dir / "P00_semantic_requirements.md").exists():
                return "P00_semantic_requirements.md"
            return "P00_semantic_requirements.md" if "semantic" in base else "P00_discuss.md"
        elif base.startswith("P01_"):
            return "P01_requirements_spec.md"
        elif base.startswith("P02_"):
            return "P02_architecture_plan.md"
        elif base.startswith("P03_"):
            return "P03_api_spec.md"
        elif base.startswith("P04_"):
            return "P04_implementation_plan.md"
        elif base.startswith("P05_"):
            return "P05_task.md"
        elif base.startswith("P06_"):
            return "P06_test_plan.md"
        elif base.startswith("P07_"):
            return "P07_walkthrough.md"
        elif re.match(r"^R\d{2}_.+\.md$", base, re.IGNORECASE):
            return "RXX_research_report.md"
        elif base in ("fast_track_plan.md", "FT_plan.md"):
            return "fast_track_plan.md"
        elif base == "umbrella_overview.md":
            return "umbrella_overview.md"
        elif base == "revision_log.md":
            return "revision_log.md"
        elif base == "handoff.md":
            return "handoff.md"
        elif base == "changelog.md":
            return "changelog.md"
        return None

    def _check_nested_depth_and_structure(
        self, plan_dir: Path, rel_path: str, report: PlanReport
    ) -> None:
        """Stage 1: 檢查目錄巢狀層級 (<= 2) 與 Umbrella / Changelog 存在性。"""
        # 檢查深度
        parts = Path(rel_path).parts
        if len(parts) > 2:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_path,
                    category="STRUCTURE",
                    message=f"目錄層級超過專案最大限制 2 層 (主計畫 -> 子計畫)：'{rel_path}'。 [Fix Hint: 請將 '{rel_path}' 上移至主計畫直接子目錄 (sub_XX) 層級]",
                )
            )

        # 檢查雙星伴隨 changelog.md
        changelog_path = plan_dir / "changelog.md"
        if not changelog_path.exists():
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=f"{rel_path}/changelog.md" if rel_path != "." else "changelog.md",
                    category="STRUCTURE",
                    message="缺少雙星伴隨初始化之 'changelog.md' 檔案。 [Fix Hint: 請建立 changelog.md 或執行 plan verify <plan> --log '<摘要>' 自動初始化並寫入日誌]",
                )
            )

        # 檢查 Umbrella 主計畫結構
        sub_dirs = [d for d in plan_dir.iterdir() if d.is_dir() and d.name.startswith("sub_")]
        if sub_dirs:
            umbrella_md = plan_dir / "umbrella_overview.md"
            if not umbrella_md.exists():
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=f"{rel_path}/umbrella_overview.md" if rel_path != "." else "umbrella_overview.md",
                        category="STRUCTURE",
                        message="分類型主計畫目錄包含子計畫，但缺少 'umbrella_overview.md' 總覽說明書。 [Fix Hint: 請讀取 umbrella_overview.md 模板於主計畫根目錄建立總覽檔]",
                    )
                )
            else:
                try:
                    u_content = umbrella_md.read_text(encoding="utf-8", errors="ignore")
                    for sub in sub_dirs:
                        if sub.name not in u_content:
                            report.issues.append(
                                PlanIssue(
                                    severity=PlanSeverity.WARN,
                                    file_name="umbrella_overview.md",
                                    category="STRUCTURE",
                                    message=f"實體子計畫目錄 '{sub.name}' 尚未登記於 'umbrella_overview.md' 清冊中。 [Fix Hint: 請於 umbrella_overview.md §2 子計畫矩陣補登 '{sub.name}']",
                                )
                            )
                except Exception:
                    pass

    def _check_changelog_content(
        self, changelog_path: Path, rel_file_name: str, report: PlanReport
    ) -> None:
        """Stage 2: 檢查 changelog.md 表格格式與記錄完備性。"""
        if not changelog_path.exists():
            return
        try:
            content = changelog_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            
            # 檢查是否有表格
            table_lines = [l for l in lines if "|" in l and not l.strip().startswith("<!--")]
            if len(table_lines) < 2:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="CHANGELOG",
                        message="'changelog.md' 缺少標準 Markdown 表格結構或無任何紀錄行。 [Fix Hint: 請參考 changelog.md 模板補齊 '| 日期時間 | 類型 | 模型 | 摘要 |' 表格]",
                    )
                )
                return

            # 檢查是否有至少一筆資料行 (排除 header 和 separator)
            data_rows = [
                l for l in table_lines
                if not re.match(r"^\|?\s*[-:]+\s*\|", l.strip())
                and not (
                    [c.strip() for c in l.strip().strip("|").split("|")][:1]
                    in (["日期時間"], ["Timestamp"])
                )
            ]
            if not data_rows:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="CHANGELOG",
                        message="'changelog.md' 尚無任何已記錄之變更或 Phase 推進條目。 [Fix Hint: 請執行 plan verify <plan> --log '<摘要>' 追加至少一筆變更紀錄]",
                    )
                )

            # 檢查佔位符 (排除行內代碼反引號)
            for pat in self.get_all_placeholder_patterns():
                for idx, line in enumerate(lines, 1):
                    line_clean = re.sub(r"`.*?`", "", line)
                    if re.search(pat, line_clean):
                        matched_ph = re.search(pat, line_clean).group(0)
                        report.issues.append(
                            PlanIssue(
                                severity=PlanSeverity.FAIL,
                                file_name=rel_file_name,
                                line_number=idx,
                                category="PLACEHOLDER",
                                message=f"檢測到未替換之模板佔位符：'{matched_ph}'。 [Fix Hint: 請將第 {idx} 行之 '{matched_ph}' 替換為實際值]",
                            )
                        )
                        break
        except Exception as e:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="CHANGELOG",
                    message=f"讀取 'changelog.md' 失敗：{e} [Fix Hint: 請確認 'changelog.md' 檔案權限與 UTF-8 編碼是否正常]",
                )
            )

    def _verify_markdown_file(
        self, file_path: Path, rel_file_name: str, is_sub_plan: bool, report: PlanReport
    ) -> None:
        """Stage 4: 稽核單一 Markdown 文件的 Header、佔位符、動態模板鏡像與 ID 格式。"""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="IO",
                    message=f"無法讀取 Markdown 檔案：{e} [Fix Hint: 請確認 '{rel_file_name}' 存在且具備 UTF-8 讀取權限]",
                )
            )
            return

        lines = content.splitlines()

        # 過濾代碼塊與行內代碼，避免文檔說明程式碼時引起誤判
        non_code_lines = []
        in_code_block = False
        for l in lines:
            if l.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block:
                cleaned_l = re.sub(r"`.*?`", "", l)
                non_code_lines.append(cleaned_l)

        non_code_text = "\n".join(non_code_lines)

        # 1. 佔位符與 HTML 註解檢查 (FR-06)
        if "<!--" in non_code_text or "-->" in non_code_text or re.search(r"<!--[\s\S]*?-->", non_code_text):
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HTML_COMMENT",
                    message="文件中檢測到殘留的 HTML 註解 (<!-- ... -->)，依規範產出與歸檔文件嚴禁包含任何 HTML 註解。 [Fix Hint: 請移除檔案中所有 <!-- ... --> 註解區塊]",
                )
            )

        for pat in self.get_all_placeholder_patterns():
            for idx, line in enumerate(non_code_lines, 1):
                if re.search(pat, line):
                    matched_ph = re.search(pat, line).group(0)
                    report.issues.append(
                        PlanIssue(
                            severity=PlanSeverity.FAIL,
                            file_name=rel_file_name,
                            line_number=idx,
                            category="PLACEHOLDER",
                            message=f"檢測到未替換之模板佔位符：'{matched_ph}'。 [Fix Hint: 請將 '{rel_file_name}' 中的 '{matched_ph}' 替換為實際值]",
                        )
                    )
                    break


        # 2. Header 元數據檢查 (FR-03)
        base_fname = os.path.basename(rel_file_name)
        is_handoff = base_fname == "handoff.md"
        is_seed_asset = base_fname.lower() in self.ORIGIN_SEED_FILES
        headers = self.parse_plan_header(lines)
        has_name = any(k in headers for k in [
            "功能名稱", "計畫名稱", "所屬計畫", "name", "title", "調研主題", "topic", "subject", "主題"
        ])
        has_date = any(k in headers for k in [
            "建立日期", "完成日期", "暫停時間", "歸檔日期", "更新日期",
            "date", "created_at", "updated_at", "archived_at", "日期", "time", "timestamp"
        ])
        has_status = any(k in headers for k in [
            "狀態", "status", "調研狀態", "research_status", "plan_status", "計畫狀態", "進度", "當前所在階段"
        ])
        has_parent = any(k in headers for k in ["所屬主計畫", "所屬計畫", "parent_plan", "主計畫", "parent"])
        has_model = any(k in headers for k in [
            "模型", "model", "ai_model", "ai-model", "模型名稱", "model_name"
        ])

        if not has_name:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [功能名稱] (或 [調研主題] / [所屬計畫]) 欄位。 [Fix Hint: 請於檔案前 35 行補上 '> 功能名稱：<名稱>']",
                )
            )
        if not has_date:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [建立日期] (或 [暫停時間]) 欄位。 [Fix Hint: 請於檔案前 35 行補上 '> 建立日期：YYYY-MM-DD']",
                )
            )
        if not has_model:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [模型] (或 model) 欄位，必須記錄撰寫/執行該檔案之後台模型名稱。 [Fix Hint: 請於檔案前 35 行補上 '> 模型：<當輪平台宣告模型或 Unknown>']",
                )
            )
        if not has_status:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [狀態] (或 [當前所在階段]) 欄位。 [Fix Hint: 請於檔案前 35 行補上 '> 狀態：Confirmed' (或對應合法狀態)]",
                )
            )
        elif not is_handoff:
            # 校驗狀態合法性
            status_val = (
                headers.get("狀態")
                or headers.get("status")
                or headers.get("計畫狀態")
                or headers.get("調研狀態")
                or headers.get("research_status")
                or headers.get("plan_status")
                or ""
            ).lower()
            if status_val and status_val not in self.VALID_STATUSES:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="HEADER",
                        message=f"狀態值 '{status_val}' 非合法狀態（合法值：Draft, Discussing, Confirmed, In Progress, Passed, Completed 等）。 [Fix Hint: 請將 '> 狀態：' 更新為合法狀態枚舉值]",
                    )
                )
            elif not is_seed_asset and status_val in ("completed", "concluded"):
                unchecked_lines = [
                    idx for idx, line in enumerate(non_code_lines, 1)
                    if re.search(r"^\s*-\s*\[\s*\]\s+", line)
                ]
                if unchecked_lines:
                    report.issues.append(
                        PlanIssue(
                            severity=PlanSeverity.FAIL,
                            file_name=rel_file_name,
                            line_number=unchecked_lines[0],
                            category="CHECKLIST",
                            message=f"計畫狀態為 '{status_val}'，但檔案中仍包含 {len(unchecked_lines)} 處未勾選之待辦 Checkbox (- [ ])。結案前必須全數完成或妥善處置。 [Fix Hint: 請將 '{rel_file_name}' 中未勾選之 '- [ ]' 更新為 '- [x]']",
                        )
                    )

        if is_sub_plan and not is_seed_asset and not has_parent:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="二級子計畫之 Header Blockquote 必須包含 [所屬主計畫] 欄位以維持追溯鏈。 [Fix Hint: 請於檔案前 35 行補上 '> 所屬主計畫：<父目錄計畫名稱>']",
                )
            )

        # 3. 動態模板章節標題鏡像對齊 (FR-01)
        tmpl_name = self._map_file_to_template(rel_file_name)
        if tmpl_name:
            expected_headers = self.get_resolved_template_headers(tmpl_name)
            if expected_headers:
                doc_headers = []
                for line in lines:
                    line_s = line.strip()
                    if line_s.startswith("##") or line_s.startswith("###"):
                        norm = self.normalize_header_title(line_s)
                        if norm:
                            doc_headers.append(norm)

                for exp_h in expected_headers:
                    # 檢查是否有模糊或包含匹配
                    matched = any(exp_h in dh or dh in exp_h for dh in doc_headers)
                    if not matched:
                        report.issues.append(
                            PlanIssue(
                                severity=PlanSeverity.FAIL,
                                file_name=rel_file_name,
                                category="TEMPLATE",
                                message=f"缺少標準模板所要求之章節標題：'{exp_h}'。 [Fix Hint: 請對照標準模板 '{tmpl_name}' 補齊包含 '{exp_h}' 之二級/三級標題]",
                            )
                        )

        # 4. 標準 ID 矩陣與測試規劃合規 (FR-02)
        if os.path.basename(rel_file_name).startswith("P06_"):
            # 檢查是否具備 FT-XX 或 ET-XX 或 RT-XX 測試案例
            has_ft = any(re.search(r"\b(FT|ET|RT)-\d{2}\b", l) for l in lines)
            if not has_ft:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="ID_MATRIX",
                        message="'P06_test_plan.md' 測試案例清冊缺少具備 'FT-XX'、'ET-XX' 或 'RT-XX' 前綴之測試項目。 [Fix Hint: 請於 P06_test_plan.md §1 表格補入至少一項如 'FT-01' 之測試案例]",
                    )
                )
        elif rel_file_name.endswith("revision_log.md"):
            # 檢查是否具備 [REV-XX] 修訂條目
            has_rev = any(re.search(r"\[REV-\d+\]", l) for l in lines)
            if not has_rev:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="ID_MATRIX",
                        message="'revision_log.md' 修訂紀錄清單缺少具備 '[REV-XX]' 前綴之修訂條目。 [Fix Hint: 請於 revision_log.md §1 補入至少一項 '### [REV-01] <修訂主題>' 條目]",
                    )
                )

    @staticmethod
    def extract_requirement_ids(markdown_text: str) -> Set[str]:
        """
        從 P01_requirements_spec.md 文本提取有效需求 ID 集合 (FR-XX, EC-XX, NFR-XX)。
        提取前依序預先剝除：
          1. Fenced Code Blocks (```...```)
          2. HTML 註解區塊 (<!--...-->)
          3. Markdown 刪除線語法 (~~...~~) 與整行被刪除線包裹之廢止需求列

        Args:
            markdown_text: P01 原始 Markdown 內容

        Returns:
            Set[str]: 大寫標準化需求 ID 集合 (如 {'FR-01', 'EC-01', 'NFR-01'})
        """
        if not markdown_text:
            return set()

        # Step 1: 剝除 Fenced Code Blocks
        cleaned = re.sub(r"```[\s\S]*?```", "", markdown_text)
        # Step 2: 剝除 HTML 註解
        cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
        # Step 3: 剝除 Markdown 刪除線片段 (~~...~~)
        cleaned = re.sub(r"~~[\s\S]*?~~", "", cleaned)

        matches = re.findall(r"\b(?:FR|EC|NFR)-\d+\b", cleaned, flags=re.IGNORECASE)
        return {m.upper() for m in matches}

    @staticmethod
    def _resolve_effective_phase(target_dir: Path, phase_norm: str) -> str:
        """
        當 phase_norm 為 'CURRENT' 時，依據目錄現有產物與狀態動態推導當前階段代號 (如 'P02', 'P04' 等)。
        """
        p_up = (phase_norm or "ALL").strip().upper()
        if p_up != "CURRENT":
            return p_up
        from .status import PlanStatusResolver

        nav = PlanStatusResolver.resolve_next_action(target_dir)
        cur = str(nav.get("current_phase", "")).strip().upper()
        if cur in ("P00", "P01", "P02", "P03", "P04", "P05", "P06", "P07"):
            return cur
        return "ALL"

    def _resolve_companion_model(
        self,
        target_dir: Path,
        phase_norm: str,
        explicit_model: Optional[str] = None,
    ) -> str:
        """
        解析伴隨檔初始化時應填入之模型名稱（防呆 2：嚴禁跨階段回溯舊檔）。
        優先取用 CLI 顯式傳入之 --model；若未傳入，僅允許讀取當下同階段主體檔之標頭模型，否則回傳 'Unknown'。
        """
        if explicit_model and isinstance(explicit_model, str) and explicit_model.strip():
            val = explicit_model.strip()
            if not (val.startswith("[") and val.endswith("]")):
                return val

        from .status import PlanStatusResolver

        eff_phase = self._resolve_effective_phase(target_dir, phase_norm)
        if eff_phase in PlanStatusResolver.PHASE_CANONICAL_STEMS:
            primary_f = PlanStatusResolver.resolve_phase_file(target_dir, eff_phase)
            if primary_f.is_file():
                return PlanStatusResolver.get_doc_header_model(primary_f)

        # 若未指定特定 P0X，僅當目錄下僅有單一主體入口檔（如 umbrella_overview.md 或 fast_track_plan.md 或 revision_log.md）時讀取該檔
        for entry_name in ("umbrella_overview.md", "fast_track_plan.md", "revision_log.md"):
            if (target_dir / entry_name).is_file():
                return PlanStatusResolver.get_doc_header_model(target_dir / entry_name)

        return "Unknown"

    def _auto_heal_companions(
        self,
        target_dir: Path,
        phase_norm: str,
        explicit_model: Optional[str],
        report: PlanReport,
    ) -> None:
        """
        Step 2: 自動初始化缺失之伴隨檔 (changelog.md 與 P02 階段伴隨之 P06_test_plan.md Draft)。
        僅於 Step 1 目標階段主體檔合規 (0 FAIL) 且啟用自癒時呼叫。
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        is_sub = target_dir.name.startswith("sub_")
        parent_name = target_dir.parent.name if is_sub else "N/A (Root Plan)"
        model_val = self._resolve_companion_model(target_dir, phase_norm, explicit_model)
        rel_prefix = f"{target_dir.name}/" if is_sub and target_dir.resolve() != Path(report.plan_path).resolve() else ""

        # 1. 若缺少 changelog.md，自動初始化
        changelog_path = target_dir / "changelog.md"
        if not changelog_path.exists():
            now_min = datetime.now().strftime("%Y-%m-%d %H:%M")
            cl_content = (
                f"# 計畫變更紀錄 (Changelog)\n\n"
                f"> 功能名稱：{target_dir.name}  \n"
                f"> 建立日期：{today_str}  \n"
                f"> 所屬主計畫：{parent_name}  \n"
                f"> 狀態：In Progress  \n"
                f"> 模型：{model_val}  \n\n"
                f"> 模板版本：v1.1  \n\n"
                f"---\n\n"
                f"## 變更紀錄\n\n"
                f"| 日期時間 | 類型 | 模型 | 摘要 |\n"
                f"| :--- | :---: | :--- | :--- |\n"
                f"| {now_min} | `PHASE` | {model_val} | 自動初始化變更日誌 (changelog.md) |\n"
            )
            changelog_path.write_text(cl_content, encoding="utf-8")
            created_rel = f"{rel_prefix}changelog.md"
            if created_rel not in report.companion_created:
                report.companion_created.append(created_rel)

        # 2. 若目標階段為 P02（或 current 為 P02）且存在 P02_architecture_plan*.md 但缺少 P06_test_plan*.md，自動初始化 Draft
        from .status import PlanStatusResolver

        p02_path = PlanStatusResolver.resolve_phase_file(target_dir, "P02")
        p06_path = PlanStatusResolver.resolve_phase_file(target_dir, "P06")
        if phase_norm.upper() in ("P02", "ALL", "CURRENT") and p02_path.is_file() and not p06_path.exists():
            p02_model = self._resolve_companion_model(target_dir, "P02", explicit_model)
            # 若 P01 存在，自動預先將 P01 所有需求 ID 填入 P06 Draft 表格骨架
            p01_path = PlanStatusResolver.resolve_phase_file(target_dir, "P01")
            req_ids = sorted(self.extract_requirement_ids(p01_path.read_text(encoding="utf-8", errors="ignore"))) if p01_path.is_file() else ["FR-01"]
            if not req_ids:
                req_ids = ["FR-01"]

            case_rows = []
            exec_rows = []
            for idx, rid in enumerate(req_ids, 1):
                prefix = "ET" if rid.startswith("EC-") else ("RT" if rid.startswith("NFR-") else "FT")
                tid = f"{prefix}-{idx:02d}"
                t_kind = "邊界測試" if prefix == "ET" else ("回歸測試" if prefix == "RT" else "單元測試")
                case_rows.append(
                    f"| **{tid}** | {t_kind} | 待於 Phase 4 定稿補齊 ({rid}) | {rid} | 待定稿 |"
                )
                exec_rows.append(f"| **{tid}** | `Pending` | 待執行 | - |")

            p06_content = (
                f"# 測試計畫與驗證報告 (Test Plan & Verification)\n\n"
                f"> 功能名稱：{target_dir.name}  \n"
                f"> 建立日期：{today_str}  \n"
                f"> 所屬主計畫：{parent_name}  \n"
                f"> 狀態：Draft  \n"
                f"> 模型：{p02_model}  \n\n"
                f"> 模板版本：v1.4  \n\n"
                f"---\n\n"
                f"## 1. 自動化測試案例清單 (Automated Test Cases)\n\n"
                f"| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |\n"
                f"| :--- | :--- | :--- | :--- | :--- |\n"
                + "\n".join(case_rows)
                + "\n\n---\n\n"
                f"## 2. 測試執行紀錄表 (Test Execution Log)\n\n"
                f"| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |\n"
                f"| :--- | :---: | :--- | :---: |\n"
                + "\n".join(exec_rows)
                + "\n\n---\n\n"
                f"## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n\n"
                f"| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |\n"
                f"| :--- | :--- | :---: | :--- |\n"
                f"| **UX-01** | 待於 Phase 4 定稿確認 | `Pending` | 待驗收 |\n"
            )
            p06_path.write_text(p06_content, encoding="utf-8")
            created_rel = f"{rel_prefix}P06_test_plan.md"
            if created_rel not in report.companion_created:
                report.companion_created.append(created_rel)

    def _check_cross_file_and_traceability(
        self,
        target_dir: Path,
        rel_dir: str,
        phase_norm: str,
        report: PlanReport,
    ) -> None:
        """
        Step 3: 雙檔協同狀態檢核 (P02/P04 <-> P06) 與 P01 <-> P06 追溯鏈集合差集比對 (FR-04, FR-05)。
        """
        from .status import PlanStatusResolver

        prefix = f"{rel_dir}/" if rel_dir != "." else ""
        p01_path = PlanStatusResolver.resolve_phase_file(target_dir, "P01")
        p02_path = PlanStatusResolver.resolve_phase_file(target_dir, "P02")
        p04_path = PlanStatusResolver.resolve_phase_file(target_dir, "P04")
        p06_path = PlanStatusResolver.resolve_phase_file(target_dir, "P06")

        p_up = phase_norm.upper()

        # 1. P02 雙檔協同檢核：當檢核 P02 (或 P02 已存在且檢核 ALL/CURRENT) 時，必須存在 P06_test_plan.md
        if p_up in ("P02", "ALL", "CURRENT") and p02_path.is_file():
            if not p06_path.is_file():
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=f"{prefix}P06_test_plan.md",
                        category="COMPANION",
                        message=(
                            "Phase 2 ('P02_architecture_plan.md') 已建立，但缺少同步初始化之測試計畫草案 'P06_test_plan.md'。 "
                            "[Fix Hint: 請讀取 P06_test_plan.md 模板建立 Draft 測試計畫，或執行 plan verify <plan> --phase P02 --log '<摘要>' 自動補齊]"
                        ),
                    )
                )

        # 2. P04 雙檔協同檢核：當檢核 P04 (或 P04 已存在且檢核 ALL/CURRENT/P05/P06/P07) 時，P06 狀態必須已達 Confirmed 以上
        if p_up in ("P04", "P05", "P06", "P07", "ALL", "CURRENT") and p04_path.is_file():
            if not p06_path.is_file():
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=f"{prefix}P06_test_plan.md",
                        category="COMPANION",
                        message=(
                            "Phase 4 ('P04_implementation_plan.md') 已建立，但缺少 'P06_test_plan.md'。 "
                            "[Fix Hint: 請建立 P06_test_plan.md 並將狀態設為 Confirmed]"
                        ),
                    )
                )
            else:
                p06_st = PlanStatusResolver.get_doc_header_status(p06_path)
                if p06_st not in ("confirmed", "in progress", "passed", "completed"):
                    report.issues.append(
                        PlanIssue(
                            severity=PlanSeverity.FAIL,
                            file_name=f"{prefix}P06_test_plan.md",
                            category="COMPANION",
                            message=(
                                f"Phase 4 ('P04_implementation_plan.md') 已建立，但 'P06_test_plan.md' 標頭狀態仍為 '{p06_st.title()}'（未達 Confirmed）。 "
                                "[Fix Hint: 請補齊 P06_test_plan.md 測試細節並將頂部 '> 狀態：' 更新為 Confirmed]"
                            ),
                        )
                    )

        # 3. P01 <-> P06 追溯鏈集合差集比對 (當 P01 與 P06 皆存在，且處於 P04+ 或指定檢核 P04/P06/ALL/CURRENT 時)
        should_check_traceability = False
        if p01_path.is_file() and p06_path.is_file():
            if p_up in ("P04", "P06", "P07"):
                should_check_traceability = True
            elif p_up in ("ALL", "CURRENT") and (p04_path.is_file() or PlanStatusResolver.get_doc_header_status(p06_path) in ("confirmed", "in progress", "passed", "completed")):
                should_check_traceability = True

        if should_check_traceability:
            try:
                p01_text = p01_path.read_text(encoding="utf-8", errors="ignore")
                p06_text = p06_path.read_text(encoding="utf-8", errors="ignore")
                p01_ids = self.extract_requirement_ids(p01_text)
                if p01_ids:
                    p06_upper = p06_text.upper()
                    missing_ids = sorted(
                        [rid for rid in p01_ids if not re.search(r"\b" + re.escape(rid) + r"\b", p06_upper)]
                    )
                    if missing_ids:
                        missing_str = ", ".join(missing_ids)
                        report.issues.append(
                            PlanIssue(
                                severity=PlanSeverity.FAIL,
                                file_name=f"{prefix}P06_test_plan.md",
                                category="TRACEABILITY",
                                message=(
                                    f"P01 需求規格書中之需求 ID 未於 'P06_test_plan.md' 完整映射（孤兒需求 ID 共 {len(missing_ids)} 項：{missing_str}）。 "
                                    f"[Fix Hint: 請於 '{prefix}P06_test_plan.md' §1 自動化測試案例清單中補齊對應 {missing_str} 之 FT/ET/RT 測試案例]"
                                ),
                            )
                        )
            except Exception:
                pass

    def append_changelog_entry(
        self,
        target_dir: Path,
        summary: str,
        log_type: str = "PHASE",
        model: str = "Unknown",
    ) -> Tuple[bool, str]:
        """
        於 target_dir/changelog.md 表格頂部免讀盲寫插入新紀錄列 (含首筆 (類型, 摘要) 冪等防重入保護)。

        Args:
            target_dir: 目標計畫或子計畫目錄
            summary: 變更摘要文字
            log_type: 日誌類型標籤 (預設 PHASE)
            model: 模型名稱 (預設 Unknown)

        Returns:
            Tuple[bool, str]: (是否實際寫入新列, 狀態碼 'appended' | 'idempotent_skipped')
        """
        changelog_path = target_dir / "changelog.md"
        clean_type = log_type.strip().upper().strip("`") or "PHASE"
        clean_summary = summary.strip().replace("\r", " ").replace("\n", " ")
        clean_model = model.strip() if model and model.strip() else "Unknown"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        if not changelog_path.exists():
            today_str = datetime.now().strftime("%Y-%m-%d")
            is_sub = target_dir.name.startswith("sub_")
            parent_name = target_dir.parent.name if is_sub else "N/A (Root Plan)"
            cl_content = (
                f"# 計畫變更紀錄 (Changelog)\n\n"
                f"> 功能名稱：{target_dir.name}  \n"
                f"> 建立日期：{today_str}  \n"
                f"> 所屬主計畫：{parent_name}  \n"
                f"> 狀態：In Progress  \n"
                f"> 模型：{clean_model}  \n\n"
                f"> 模板版本：v1.1  \n\n"
                f"---\n\n"
                f"## 變更紀錄\n\n"
                f"| 日期時間 | 類型 | 模型 | 摘要 |\n"
                f"| :--- | :---: | :--- | :--- |\n"
                f"| {now_str} | `{clean_type}` | {clean_model} | {clean_summary} |\n"
            )
            changelog_path.write_text(cl_content, encoding="utf-8")
            return True, "appended"

        content = changelog_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        # 尋找表格分隔線 (如 | :--- | :---: | ...) 的位置
        sep_idx = -1
        for idx, line in enumerate(lines):
            if "|" in line and re.match(r"^\|?\s*[-:]+\s*\|", line.strip()):
                sep_idx = idx
                break

        if sep_idx == -1:
            # 若無標準表格，於檔尾補建標準表格
            new_row = f"| {now_str} | `{clean_type}` | {clean_model} | {clean_summary} |"
            lines.extend([
                "",
                "## 變更紀錄",
                "",
                "| 日期時間 | 類型 | 模型 | 摘要 |",
                "| :--- | :---: | :--- | :--- |",
                new_row,
            ])
            changelog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True, "appended"

        # 防呆 1-B：檢查第一筆資料列是否與 (clean_type, clean_summary) 完全相同（冪等防重入）
        first_data_idx = sep_idx + 1
        while first_data_idx < len(lines) and not lines[first_data_idx].strip():
            first_data_idx += 1

        if first_data_idx < len(lines) and "|" in lines[first_data_idx]:
            cells = [c.strip() for c in lines[first_data_idx].strip().strip("|").split("|")]
            if len(cells) >= 3:
                existing_type = cells[1].strip().strip("`").upper()
                existing_summary = cells[-1].strip()
                if existing_type == clean_type and existing_summary == clean_summary:
                    return False, "idempotent_skipped"

        new_row = f"| {now_str} | `{clean_type}` | {clean_model} | {clean_summary} |"
        lines.insert(sep_idx + 1, new_row)
        changelog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True, "appended"


    def _filter_files_by_phase(
        self, target_dir: Path, phase_norm: str
    ) -> List[Path]:
        """根據指定之 --phase 過濾應檢核之主體 Markdown 檔案清單（不含 changelog.md）。"""
        all_mds = [md for md in sorted(target_dir.glob("*.md")) if md.name != "changelog.md"]
        p_up = phase_norm.upper()
        if p_up in ("ALL", "CURRENT", ""):
            return all_mds

        phase_prefix_map = {
            "P00": "P00_",
            "P01": "P01_",
            "P02": "P02_",
            "P03": "P03_",
            "P04": "P04_",
            "P05": "P05_",
            "P06": "P06_",
            "P07": "P07_",
        }
        prefix = phase_prefix_map.get(p_up)
        if not prefix:
            return all_mds

        matched = [md for md in all_mds if md.name.startswith(prefix)]
        # P04 雙定稿時亦需一併檢核 P06_test_plan*.md
        if p_up == "P04":
            from .status import PlanStatusResolver

            p06_f = PlanStatusResolver.resolve_phase_file(target_dir, "P06")
            if p06_f.is_file() and p06_f not in matched:
                matched.append(p06_f)
        return matched

    def verify_plan(
        self,
        plan_path_or_name: Union[str, Path],
        phase: str = "all",
        log_msg: Optional[str] = None,
        log_type: str = "PHASE",
        model: Optional[str] = None,
    ) -> PlanReport:
        """
        對指定計畫目錄執行四步檢核與伴隨檔自癒流水線，回傳結構化 PlanReport。
        1. Step 1: 檢核目標階段主體檔合規性
        2. Step 2: 若 Step 1 無 FAIL 且提供 log_msg (或為 P02)，自動初始化缺失之伴隨檔 (changelog.md, P06 Draft)
        3. Step 3: 執行目錄結構、changelog、雙檔協同 (P02/P04 <-> P06) 與 P01<->P06 追溯差集比對
        4. Step 4: 僅當 100% PASS (0 FAIL) 且提供 log_msg 時，自動以系統時間戳免讀盲寫追加 changelog.md
        """
        if isinstance(plan_path_or_name, str):
            raw_str = plan_path_or_name.strip()
            p = Path(raw_str)
            if not p.is_absolute():
                if (self.plans_dir / raw_str).is_dir():
                    p = self.plans_dir / raw_str
                elif (self.archive_dir / raw_str).is_dir():
                    p = self.archive_dir / raw_str
                elif raw_str.startswith("sub_") and self.plans_dir.exists():
                    # 支援直接傳入唯一 sub_XX 子計畫名稱 (EC-06)
                    matched_subs = [
                        d / raw_str
                        for d in sorted(self.plans_dir.iterdir(), key=lambda x: x.name, reverse=True)
                        if d.is_dir() and re.match(r"^\d{4}_\d{2}_\d{2}", d.name) and (d / raw_str).is_dir()
                    ]
                    if len(matched_subs) == 1:
                        p = matched_subs[0]
                    else:
                        p = self.plans_dir / raw_str
                else:
                    p = self.plans_dir / raw_str
        else:
            p = plan_path_or_name

        disp_name = (
            f"{p.parent.name}/{p.name}"
            if p.name.startswith("sub_") and p.parent != self.plans_dir
            else p.name
        )

        report = PlanReport(
            plan_name=disp_name,
            plan_path=str(p.resolve()) if p.exists() else str(p),
            status=PlanSeverity.PASS,
            issues=[],
        )

        if not p.exists() or not p.is_dir():
            report.status = PlanSeverity.FAIL
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=".",
                    category="STRUCTURE",
                    message=f"找不到指定的計畫目錄：'{p}'。 [Fix Hint: 請確認計畫目錄名稱或路徑是否正確]",
                )
            )
            return report

        phase_norm = (phase or "all").strip().upper()
        is_sub = p.name.startswith("sub_")
        enable_auto_heal = bool(log_msg and log_msg.strip())

        # 若 phase 指定具體 P00~P07，確認該階段主體檔案必須已存在
        phase_prefix_map = {
            "P00": "P00_discuss.md",
            "P01": "P01_requirements_spec.md",
            "P02": "P02_architecture_plan.md",
            "P03": "P03_api_spec.md",
            "P04": "P04_implementation_plan.md",
            "P05": "P05_task.md",
            "P06": "P06_test_plan.md",
            "P07": "P07_walkthrough.md",
        }
        if phase_norm in phase_prefix_map:
            exp_fname = phase_prefix_map[phase_norm]
            if not any(f.name.startswith(phase_norm + "_") for f in p.glob("*.md")):
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=exp_fname,
                        category="STRUCTURE",
                        message=f"指定檢核階段 '{phase_norm}'，但目錄中找不到對應主體檔案 '{exp_fname}'。 [Fix Hint: 請先建立 '{exp_fname}' 後再執行檢核]",
                    )
                )

        # Step 1: 檢核目標階段主體 Markdown 檔案本體合規性
        target_mds = self._filter_files_by_phase(p, phase_norm)
        for md in target_mds:
            self._verify_markdown_file(md, md.name, is_sub, report)

        # Step 2: 若 Step 1 主體檔合規 (0 FAIL) 且提供 --log，自動補齊伴隨檔 (changelog.md 與 P02 伴隨之 P06 Draft)
        if not report.has_fails and enable_auto_heal:
            self._auto_heal_companions(p, phase_norm, model, report)
            # 若伴隨生成了 P06_test_plan.md，對新生成之伴隨檔執行本體合規檢核
            if "P06_test_plan.md" in report.companion_created:
                p06_new = p / "P06_test_plan.md"
                if p06_new.is_file() and p06_new not in target_mds:
                    self._verify_markdown_file(p06_new, p06_new.name, is_sub, report)

        # Step 3: 結構、changelog、雙檔協同 (P02/P04 <-> P06) 與 P01<->P06 追溯差集檢核
        self._check_nested_depth_and_structure(p, ".", report)
        changelog_path = p / "changelog.md"
        self._check_changelog_content(changelog_path, "changelog.md", report)
        self._check_cross_file_and_traceability(p, ".", phase_norm, report)

        # 若為 Umbrella 主目錄且未指定特定單一 P0X 階段，遞迴檢查 sub_* 目錄
        if phase_norm in ("ALL", "CURRENT"):
            for sub in sorted(p.iterdir(), key=lambda x: x.name):
                if sub.is_dir() and sub.name.startswith("sub_"):
                    self._check_nested_depth_and_structure(sub, sub.name, report)
                    sub_changelog = sub / "changelog.md"
                    self._check_changelog_content(sub_changelog, f"{sub.name}/changelog.md", report)
                    for sub_md in sorted(sub.glob("*.md")):
                        if sub_md.name == "changelog.md":
                            continue
                        self._verify_markdown_file(
                            sub_md, f"{sub.name}/{sub_md.name}", True, report
                        )
                    self._check_cross_file_and_traceability(sub, sub.name, phase_norm, report)

        # Step 4: 彙總狀態，僅當 100% PASS (0 FAIL) 且提供 log_msg 時寫入 changelog.md (EC-03, EC-04)
        if report.has_fails:
            report.status = PlanSeverity.FAIL
            if enable_auto_heal:
                report.log_status = "skipped_on_fail"
        else:
            if report.has_warns:
                report.status = PlanSeverity.WARN
            else:
                report.status = PlanSeverity.PASS

            if enable_auto_heal and log_msg:
                resolved_model = self._resolve_companion_model(p, phase_norm, model)
                _, l_status = self.append_changelog_entry(
                    p, summary=log_msg, log_type=log_type, model=resolved_model
                )
                report.log_status = l_status

        return report


    def verify_all_plans(self, include_archived: bool = False) -> Dict[str, PlanReport]:
        """
        全量檢核所有活躍計畫（已封存計畫視為歷史存檔，不進行檢查）。
        """
        results: Dict[str, PlanReport] = {}
        if self.plans_dir.exists():
            for item in sorted(self.plans_dir.iterdir(), key=lambda x: x.name):
                if item.is_dir() and not item.name.startswith(".") and re.match(r"^\d{4}_\d{2}_\d{2}", item.name):
                    results[item.name] = self.verify_plan(item)

        return results

    def verify(
        self,
        plan_name: Optional[str] = None,
        include_all: bool = False
    ) -> Dict[str, Any]:
        """
        向後相容通用檢核入口。
        """
        if plan_name:
            rep = self.verify_plan(plan_name)
            return {
                "success": rep.passed,
                "error": rep.errors[0] if rep.errors else None,
                "plans_audited": 1,
                "total_errors": len(rep.errors),
                "total_warns": len(rep.warnings),
                "details": {rep.plan_name: [i.to_dict() for i in rep.issues]},
                "reports": {rep.plan_name: rep},
            }
        else:
            all_reps = self.verify_all_plans(include_archived=include_all)
            total_err = sum(len(r.errors) for r in all_reps.values())
            total_warn = sum(len(r.warnings) for r in all_reps.values())
            return {
                "success": total_err == 0,
                "error": None,
                "plans_audited": len(all_reps),
                "total_errors": total_err,
                "total_warns": total_warn,
                "details": {k: [i.to_dict() for i in v.issues] for k, v in all_reps.items()},
                "reports": all_reps,
            }
