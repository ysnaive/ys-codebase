"""
PlanVerifier — 開發計畫規範、動態模板鏡像與合規性稽核引擎。
"""

import os
import re
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple


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
        "discussing", "planning", "executing", "concluded", "aborted", "cancelled"
    }

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
                    message=f"目錄層級超過專案最大限制 2 層 (主計畫 -> 子計畫)：'{rel_path}'。",
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
                    message="缺少雙星伴隨初始化之 'changelog.md' 檔案。",
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
                        message="分類型主計畫目錄包含子計畫，但缺少 'umbrella_overview.md' 總覽說明書。",
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
                                    message=f"實體子計畫目錄 '{sub.name}' 尚未登記於 'umbrella_overview.md' 清冊中。",
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
                        message="'changelog.md' 缺少標準 Markdown 表格結構或無任何紀錄行。",
                    )
                )
                return

            # 檢查是否有至少一筆資料行 (排除 header 和 separator)
            data_rows = [
                l for l in table_lines 
                if not re.match(r"^\|?\s*[-:]+\s*\|", l.strip()) 
                and not any(h in l for h in ["日期時間", "Timestamp", "類型", "Type"])
            ]
            if not data_rows:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="CHANGELOG",
                        message="'changelog.md' 尚無任何已記錄之變更或 Phase 推進條目。",
                    )
                )

            # 檢查佔位符 (排除行內代碼反引號)
            for pat in self.get_all_placeholder_patterns():
                for idx, line in enumerate(lines, 1):
                    line_clean = re.sub(r"`.*?`", "", line)
                    if re.search(pat, line_clean):
                        report.issues.append(
                            PlanIssue(
                                severity=PlanSeverity.FAIL,
                                file_name=rel_file_name,
                                line_number=idx,
                                category="PLACEHOLDER",
                                message=f"檢測到未替換之模板佔位符：'{re.search(pat, line_clean).group(0)}'。",
                            )
                        )
                        break
        except Exception as e:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="CHANGELOG",
                    message=f"讀取 'changelog.md' 失敗：{e}",
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
                    message=f"無法讀取 Markdown 檔案：{e}",
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
                    message="文件中檢測到殘留的 HTML 註解 (<!-- ... -->)，依規範產出與歸檔文件嚴禁包含任何 HTML 註解。",
                )
            )

        for pat in self.get_all_placeholder_patterns():
            for idx, line in enumerate(non_code_lines, 1):
                if re.search(pat, line):
                    report.issues.append(
                        PlanIssue(
                            severity=PlanSeverity.FAIL,
                            file_name=rel_file_name,
                            line_number=idx,
                            category="PLACEHOLDER",
                            message=f"檢測到未替換之模板佔位符：'{re.search(pat, line).group(0)}'。",
                        )
                    )
                    break


        # 2. Header 元數據檢查 (FR-03)
        is_handoff = os.path.basename(rel_file_name) == "handoff.md"
        headers = self.parse_plan_header(lines)
        has_name = any(k in headers for k in [
            "功能名稱", "計畫名稱", "所屬計畫", "name", "title", "調研主題", "topic", "subject", "主題"
        ])
        has_date = any(k in headers for k in [
            "建立日期", "完成日期", "暫停時間", "date", "created_at", "日期", "time", "timestamp"
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
                    message="Header Blockquote 缺少 [功能名稱] (或 [調研主題] / [所屬計畫]) 欄位。",
                )
            )
        if not has_date:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [建立日期] (或 [暫停時間]) 欄位。",
                )
            )
        if not has_model:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [模型] (或 model) 欄位，必須記錄撰寫/執行該檔案之後台模型名稱。",
                )
            )
        if not has_status:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="Header Blockquote 缺少 [狀態] (或 [當前所在階段]) 欄位。",
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
                        message=f"狀態值 '{status_val}' 非合法狀態（合法值：Draft, Discussing, Confirmed, In Progress, Passed, Completed 等）。",
                    )
                )
            elif status_val in ("completed", "concluded"):
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
                            message=f"計畫狀態為 '{status_val}'，但檔案中仍包含 {len(unchecked_lines)} 處未勾選之待辦 Checkbox (- [ ])。結案前必須全數完成或妥善處置。",
                        )
                    )

        if is_sub_plan and not has_parent:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message="二級子計畫之 Header Blockquote 必須包含 [所屬主計畫] 欄位以維持追溯鏈。",
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
                                message=f"缺少標準模板所要求之章節標題：'{exp_h}'。",
                            )
                        )

        # 4. 標準 ID 矩陣與測試規劃合規 (FR-02)
        if rel_file_name.endswith("P06_test_plan.md"):
            # 檢查是否具備 FT-XX 或 ET-XX 或 RT-XX 測試案例
            has_ft = any(re.search(r"\b(FT|ET|RT)-\d{2}\b", l) for l in lines)
            if not has_ft:
                report.issues.append(
                    PlanIssue(
                        severity=PlanSeverity.FAIL,
                        file_name=rel_file_name,
                        category="ID_MATRIX",
                        message="'P06_test_plan.md' 測試案例清冊缺少具備 'FT-XX'、'ET-XX' 或 'RT-XX' 前綴之測試項目。",
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
                        message="'revision_log.md' 修訂紀錄清單缺少具備 '[REV-XX]' 前綴之修訂條目。",
                    )
                )

    def verify_plan(self, plan_path_or_name: Union[str, Path]) -> PlanReport:
        """
        對指定計畫目錄執行 5 步檢核流水線，回傳結構化 PlanReport。
        """
        if isinstance(plan_path_or_name, str):
            p = Path(plan_path_or_name)
            if not p.is_absolute():
                if (self.plans_dir / plan_path_or_name).is_dir():
                    p = self.plans_dir / plan_path_or_name
                elif (self.archive_dir / plan_path_or_name).is_dir():
                    p = self.archive_dir / plan_path_or_name
                else:
                    p = self.plans_dir / plan_path_or_name
        else:
            p = plan_path_or_name

        report = PlanReport(
            plan_name=p.name,
            plan_path=str(p.resolve()),
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
                    message=f"找不到指定的計畫目錄：'{p}'。",
                )
            )
            return report

        # Stage 1: Structure & Depth Guard
        self._check_nested_depth_and_structure(p, ".", report)

        # Stage 2: Changelog Guard
        changelog_path = p / "changelog.md"
        self._check_changelog_content(changelog_path, "changelog.md", report)

        # Stage 4: Verify Markdown Files in Root
        is_sub = p.name.startswith("sub_")
        for md in sorted(p.glob("*.md")):
            if md.name == "changelog.md":
                continue
            self._verify_markdown_file(md, md.name, is_sub, report)

        # 遞迴檢查 sub_* 目錄
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

        # Stage 5: Aggregate Overall Status
        if report.has_fails:
            report.status = PlanSeverity.FAIL
        elif report.has_warns:
            report.status = PlanSeverity.WARN
        else:
            report.status = PlanSeverity.PASS

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
