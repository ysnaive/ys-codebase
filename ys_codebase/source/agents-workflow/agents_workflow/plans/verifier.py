"""
PlanVerifier — 開發計畫規範、動態模板鏡像與合規性稽核引擎。
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ._common import parse_markdown_blockquote_headers, resolve_plan_uri
from ._verifier_healer import (
    append_changelog_entry as _append_changelog_entry,
    auto_heal_companions as _auto_heal_companions,
    auto_heal_deterministic_headers as _auto_heal_deterministic_headers,
    infer_deterministic_header_values as _infer_deterministic_header_values,
    resolve_companion_model as _resolve_companion_model,
)
from ._verifier_specs import (
    ORIGIN_SEED_FILES as _ORIGIN_SEED_FILES,
    PHASE_CANONICAL_FILES,
    PHASE_PREFIX_MAP,
    PLACEHOLDER_PATTERNS as _PLACEHOLDER_PATTERNS,
    VALID_STATUSES as _VALID_STATUSES,
    extract_dynamic_placeholders,
    extract_requirement_ids as _extract_requirement_ids,
    is_header_match,
    load_template_header_specs,
    map_file_to_template,
    normalize_header_title as _normalize_header_title,
)


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
    """計畫檢核報告實體。"""
    plan_name: str
    plan_path: str
    status: PlanSeverity = PlanSeverity.PASS
    issues: List[PlanIssue] = field(default_factory=list)
    companion_created: List[str] = field(default_factory=list)
    header_healed: List[str] = field(default_factory=list)
    log_status: Optional[str] = None
    next_phase_hint: Optional[str] = None

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
            "header_healed": list(self.header_healed),
            "log_status": self.log_status,
            "next_phase_hint": self.next_phase_hint,
        }


class PlanVerifier:
    """開發計畫文件合規性稽核引擎 (4-Stage Verification Pipeline)。"""

    VALID_STATUSES = _VALID_STATUSES
    ORIGIN_SEED_FILES = _ORIGIN_SEED_FILES
    PLACEHOLDER_PATTERNS = _PLACEHOLDER_PATTERNS

    def __init__(
        self,
        plans_dir: Optional[Union[str, Path]] = None,
        archive_dir: Optional[Union[str, Path]] = None,
        templates_dir: Optional[Union[str, Path]] = None,
    ):
        """初始化 PlanVerifier。"""
        if plans_dir is not None:
            self.plans_dir = Path(plans_dir).resolve()
        else:
            self.plans_dir = resolve_plan_uri("workflow.plans://", default_fallback="plans")

        if archive_dir is not None:
            self.archive_dir = Path(archive_dir).resolve()
        else:
            self.archive_dir = resolve_plan_uri("workflow.archived://", default_fallback="plans/archived")

        if templates_dir is not None:
            self.templates_dir = Path(templates_dir).resolve()
        else:
            res_tmpl = resolve_plan_uri("cache://agents-workflow/resolved_contents/templates")
            if not res_tmpl or not res_tmpl.exists():
                res_tmpl = resolve_plan_uri("project://.agents/.yscb/templates")
            if not res_tmpl or not res_tmpl.exists():
                cand = Path.cwd() / ".cache" / "agents-workflow" / "resolved_contents" / "templates"
                res_tmpl = cand if cand.exists() else None
            self.templates_dir = res_tmpl

        self._template_headers_cache: Dict[str, List[str]] = {}
        self._template_header_specs_cache: Dict[str, List[Tuple[str, str]]] = {}
        self._dynamic_placeholders_cache: Optional[List[str]] = None

    def get_dynamic_placeholders(self) -> List[str]:
        """動態自模板目錄提取標頭佔位符正則模式清單。"""
        if self._dynamic_placeholders_cache is None:
            self._dynamic_placeholders_cache = extract_dynamic_placeholders(self.templates_dir)
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

    def get_resolved_template_header_specs(self, template_name: str) -> List[Tuple[str, str]]:
        """讀取已解析之標準模板並提取其定義之 Markdown 二/三級章節標題。"""
        if template_name in self._template_header_specs_cache:
            return self._template_header_specs_cache[template_name]

        specs = load_template_header_specs(template_name, self.templates_dir)
        self._template_header_specs_cache[template_name] = specs
        self._template_headers_cache[template_name] = [n for n, _ in specs]
        return specs

    def _check_nested_depth_and_structure(
        self, plan_dir: Path, rel_path: str, report: PlanReport
    ) -> None:
        """Stage 1: 檢查目錄巢狀層級 (<= 2) 與 Umbrella / Changelog 存在性。"""
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

            for pat in self.get_all_placeholder_patterns():
                for idx, line in enumerate(lines, 1):
                    line_clean = re.sub(r"`.*?`", "", line)
                    m = re.search(pat, line_clean)
                    if m:
                        matched_ph = m.group(0)
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
        self,
        file_path: Path,
        rel_file_name: str,
        is_sub_plan: bool,
        report: PlanReport,
        enable_auto_heal: bool = False,
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
                m = re.search(pat, line)
                if m:
                    matched_ph = m.group(0)
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

        tmpl_name = map_file_to_template(rel_file_name, self.templates_dir)
        expected_specs: List[Tuple[str, str]] = []
        missing_specs: List[Tuple[str, str]] = []
        if tmpl_name:
            expected_specs = self.get_resolved_template_header_specs(tmpl_name)
            if expected_specs:
                doc_headers = []
                for line in lines:
                    line_s = line.strip()
                    if line_s.startswith("##") or line_s.startswith("###"):
                        norm = _normalize_header_title(line_s)
                        if norm:
                            doc_headers.append(norm)

                for exp_norm, exp_raw in expected_specs:
                    matched = any(is_header_match(exp_norm, dh) for dh in doc_headers)
                    if not matched:
                        missing_specs.append((exp_norm, exp_raw))

        base_fname = os.path.basename(rel_file_name)
        is_handoff = base_fname == "handoff.md"
        is_seed_asset = base_fname.lower() in self.ORIGIN_SEED_FILES
        headers = parse_markdown_blockquote_headers(lines, max_lines=35)
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

        has_prior_file_issues = any(i.file_name == rel_file_name for i in report.issues)
        if (
            enable_auto_heal
            and not is_handoff
            and not is_seed_asset
            and has_status
            and has_model
            and len(missing_specs) == 0
            and not has_prior_file_issues
            and (not has_name or not has_date or (is_sub_plan and not has_parent))
        ):
            lines, headers, healed_keys = _auto_heal_deterministic_headers(
                file_path, lines, headers, is_sub_plan
            )
            if healed_keys:
                report.header_healed.append(f"{rel_file_name} ({', '.join(healed_keys)})")
                has_name = any(k in headers for k in [
                    "功能名稱", "計畫名稱", "所屬計畫", "name", "title", "調研主題", "topic", "subject", "主題"
                ])
                has_date = any(k in headers for k in [
                    "建立日期", "完成日期", "暫停時間", "歸檔日期", "更新日期",
                    "date", "created_at", "updated_at", "archived_at", "日期", "time", "timestamp"
                ])
                has_parent = any(k in headers for k in ["所屬主計畫", "所屬計畫", "parent_plan", "主計畫", "parent"])

        inferred_hdr = _infer_deterministic_header_values(file_path, is_sub_plan)
        inferred_name = inferred_hdr["功能名稱"]
        inferred_date = inferred_hdr["建立日期"]
        inferred_parent = inferred_hdr["所屬主計畫"]

        if not has_name:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message=f"Header Blockquote 缺少 [功能名稱] (或 [調研主題] / [所屬計畫]) 欄位。 [Fix Hint: 請於檔案前 35 行補上 '> 功能名稱：{inferred_name}']",
                )
            )
        if not has_date:
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="HEADER",
                    message=f"Header Blockquote 缺少 [建立日期] (或 [暫停時間]) 欄位。 [Fix Hint: 請於檔案前 35 行補上 '> 建立日期：{inferred_date}']",
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
                    message=f"二級子計畫之 Header Blockquote 必須包含 [所屬主計畫] 欄位以維持追溯鏈。 [Fix Hint: 請於檔案前 35 行補上 '> 所屬主計畫：{inferred_parent}']",
                )
            )

        if tmpl_name and expected_specs and missing_specs:
            m_cnt = len(missing_specs)
            n_cnt = len(expected_specs)
            r_sec = m_cnt / n_cnt
            pct = int(round(r_sec * 100))
            missing_norm_str = "、".join(f"'{norm}'" for norm, _ in missing_specs)
            missing_raw_str = " | ".join(raw for _, raw in missing_specs)
            all_raw_str = " | ".join(raw for _, raw in expected_specs)
            if r_sec < 0.5:
                msg = (
                    f"[TRIAGE: QUICK_PATCH (章節缺失 {m_cnt}/{n_cnt}, {pct}%)] "
                    f"缺少標準模板所要求之章節標題：{missing_norm_str}。 "
                    f"[Fix Hint: 檔案結構大致完整，請勿重寫全檔；請直接以 edit_file 補齊以下原始 Markdown 標題：{missing_raw_str}]"
                )
            else:
                msg = (
                    f"[TRIAGE: FULL_REWRITE (章節缺失 {m_cnt}/{n_cnt}, {pct}%, 屬盲寫結構偏離)] "
                    f"缺少標準模板所要求之章節標題：{missing_norm_str}。 "
                    f"[Fix Hint: 嚴禁翻找其他歷史計畫目錄抄襲！請直接讀取標準模板 '.agents/.yscb/templates/{tmpl_name}' 並依完整原始標題骨架 ({all_raw_str}) 以 write_file 重寫 '{rel_file_name}']"
                )
            report.issues.append(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="TEMPLATE",
                    message=msg,
                )
            )

        if os.path.basename(rel_file_name).startswith("P06_"):
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

    def _check_cross_file_and_traceability(
        self,
        target_dir: Path,
        rel_dir: str,
        phase_norm: str,
        report: PlanReport,
    ) -> None:
        """Step 3: 雙檔協同狀態檢核 (P02/P04 <-> P06) 與 P01 <-> P06 追溯鏈集合差集比對。"""
        from .status import PlanStatusResolver

        prefix = f"{rel_dir}/" if rel_dir != "." else ""
        p01_path = PlanStatusResolver.resolve_phase_file(target_dir, "P01")
        p02_path = PlanStatusResolver.resolve_phase_file(target_dir, "P02")
        p04_path = PlanStatusResolver.resolve_phase_file(target_dir, "P04")
        p06_path = PlanStatusResolver.resolve_phase_file(target_dir, "P06")

        p_up = phase_norm.upper()

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

        should_check_traceability = False
        if p01_path.is_file() and p06_path.is_file():
            if p_up in ("P04", "P06", "P07"):
                should_check_traceability = True
            elif p_up in ("ALL", "CURRENT") and (
                p04_path.is_file()
                or PlanStatusResolver.get_doc_header_status(p06_path) in ("confirmed", "in progress", "passed", "completed")
            ):
                should_check_traceability = True

        if should_check_traceability:
            try:
                p01_text = p01_path.read_text(encoding="utf-8", errors="ignore")
                p06_text = p06_path.read_text(encoding="utf-8", errors="ignore")
                p01_ids = _extract_requirement_ids(p01_text)
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

    def _build_next_phase_hint(self, target_dir: Path) -> Optional[str]:
        """當檢核全數通過且計畫尚未結案時，解析下一階段模板路徑與必備章節預告。"""
        from .status import PlanStatusResolver

        nav = PlanStatusResolver.resolve_next_action(target_dir)
        next_phase_raw = str(nav.get("next_phase") or "")
        if not next_phase_raw or any(
            done_kw in next_phase_raw for done_kw in ("Completed", "Archived", "Transition")
        ):
            return None

        phase_match = re.match(r"^(P0[0-7])\b", next_phase_raw)
        if phase_match:
            p_code = phase_match.group(1)
            stem = PlanStatusResolver.PHASE_CANONICAL_STEMS.get(p_code, f"{p_code}_spec")
            tmpl_name = f"{stem}.md"
        elif next_phase_raw in ("FP-01", "FP-02", "FP-03"):
            p_code = next_phase_raw
            tmpl_name = "fast_track_plan.md"
        elif next_phase_raw == "Revision":
            p_code = "Revision"
            tmpl_name = "revision_log.md"
        else:
            return None

        specs = self.get_resolved_template_header_specs(tmpl_name)
        if not specs:
            return None

        raw_titles_str = " | ".join(raw_h for _, raw_h in specs)
        return (
            f"下一階段 {p_code} ({tmpl_name}) -> "
            f"請先讀取 `.agents/.yscb/templates/{tmpl_name}` | "
            f"必備章節: {raw_titles_str}"
        )

    def _filter_files_by_phase(
        self, target_dir: Path, phase_norm: str
    ) -> List[Path]:
        """根據指定之 --phase 過濾應檢核之主體 Markdown 檔案清單（不含 changelog.md）。"""
        all_mds = [md for md in sorted(target_dir.glob("*.md")) if md.name != "changelog.md"]
        p_up = phase_norm.upper()
        if p_up in ("ALL", "CURRENT", ""):
            return all_mds

        prefix = PHASE_PREFIX_MAP.get(p_up)
        if not prefix:
            return all_mds

        matched = [md for md in all_mds if md.name.startswith(prefix)]
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
        """對指定計畫目錄執行四步檢核與伴隨檔自癒流水線，回傳結構化 PlanReport。"""
        if isinstance(plan_path_or_name, str):
            raw_str = plan_path_or_name.strip()
            p = Path(raw_str)
            if not p.is_absolute():
                if (self.plans_dir / raw_str).is_dir():
                    p = self.plans_dir / raw_str
                elif (self.archive_dir / raw_str).is_dir():
                    p = self.archive_dir / raw_str
                elif raw_str.startswith("sub_") and self.plans_dir.exists():
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

        if phase_norm in PHASE_CANONICAL_FILES:
            exp_fname = PHASE_CANONICAL_FILES[phase_norm]
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
            self._verify_markdown_file(
                md, md.name, is_sub, report, enable_auto_heal=enable_auto_heal
            )

        # Step 2: 若 Step 1 主體檔合規 (0 FAIL) 且提供 --log，自動補齊伴隨檔
        if not report.has_fails and enable_auto_heal:
            _auto_heal_companions(p, phase_norm, model, report)
            if "P06_test_plan.md" in report.companion_created:
                p06_new = p / "P06_test_plan.md"
                if p06_new.is_file() and p06_new not in target_mds:
                    self._verify_markdown_file(
                        p06_new, p06_new.name, is_sub, report, enable_auto_heal=enable_auto_heal
                    )

        # Step 3: 結構、changelog、雙檔協同 (P02/P04 <-> P06) 與 P01<->P06 追溯差集檢核
        self._check_nested_depth_and_structure(p, ".", report)
        changelog_path = p / "changelog.md"
        self._check_changelog_content(changelog_path, "changelog.md", report)
        self._check_cross_file_and_traceability(p, ".", phase_norm, report)

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
                            sub_md,
                            f"{sub.name}/{sub_md.name}",
                            True,
                            report,
                            enable_auto_heal=enable_auto_heal,
                        )
                    self._check_cross_file_and_traceability(sub, sub.name, phase_norm, report)

        # Step 4: 彙總狀態
        if report.has_fails:
            report.status = PlanSeverity.FAIL
            if enable_auto_heal:
                report.log_status = "skipped_on_fail"
        else:
            if report.has_warns:
                report.status = PlanSeverity.WARN
            else:
                report.status = PlanSeverity.PASS

            report.next_phase_hint = self._build_next_phase_hint(p)

            if enable_auto_heal and log_msg:
                resolved_model = _resolve_companion_model(p, phase_norm, model)
                _, l_status = _append_changelog_entry(
                    p, summary=log_msg, log_type=log_type, model=resolved_model
                )
                report.log_status = l_status

        return report

    def verify_all_plans(self) -> Dict[str, PlanReport]:
        """全量檢核所有活躍計畫（已封存計畫視為歷史存檔，不進行檢查）。"""
        results: Dict[str, PlanReport] = {}
        if self.plans_dir.exists():
            for item in sorted(self.plans_dir.iterdir(), key=lambda x: x.name):
                if item.is_dir() and not item.name.startswith(".") and re.match(r"^\d{4}_\d{2}_\d{2}", item.name):
                    results[item.name] = self.verify_plan(item)

        return results
