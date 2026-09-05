"""
knowledge-db 呈現層格式化中樞 (formatter.py)
職責：
1. 全域重複資訊剔除 (UniversalRedundancyFilter)：剔除 Docstring 註解、Markdown Header 重複、版權樣板與空行
2. 8,000 字元自適應動態預算與線性衰減計算器
3. 檔案路徑正規化與 IDE 相容 Markdown 超連結生成
4. 4 大查詢命令格式化輸出 (format_search_output, format_callers_output, format_callees_output, format_impact_output)
"""

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .schema import AggregatedFileResult, AggregatedItem, SymbolCallSite, UnifiedSymbol

AUTO_BUDGET_CHARS: int = 8000
AUTO_DECAY_START_CHARS: int = 3500
AUTO_DECAY_MIN_CHARS: int = 6000
AUTO_NO_SNIPPET_CHARS: int = 7000
AUTO_MAX_SNIPPET_LINES: int = 30
AUTO_MIN_SNIPPET_LINES: int = 10
AUTO_MIN_RENDERED_ITEMS: int = 5


def compute_dynamic_snippet_lines(
    current_chars: int,
    budget_limit: int = AUTO_BUDGET_CHARS,
    start_decay: int = AUTO_DECAY_START_CHARS,
    min_decay: int = AUTO_DECAY_MIN_CHARS,
    no_snippet_threshold: int = AUTO_NO_SNIPPET_CHARS,
    max_lines: int = AUTO_MAX_SNIPPET_LINES,
    min_lines: int = AUTO_MIN_SNIPPET_LINES,
) -> int:
    """
    計算 auto 模式下的動態切片行數預算 (8,000 字元上限優化):
    - < 3500 字元: 30 行
    - 3500 ~ 6000 字元: 30 -> 10 行線性平滑遞減
    - 6000 ~ 7000 字元: 10 行
    - 7000 ~ 8000 字元: 0 行 (強制無切片，保留元資料與保底 5 項目)
    - >= 8000 字元: 0 行
    """
    if current_chars < start_decay:
        return max_lines
    elif current_chars < min_decay:
        ratio = (current_chars - start_decay) / (min_decay - start_decay)
        return max(min_lines, int(round(max_lines - ratio * (max_lines - min_lines))))
    elif current_chars < no_snippet_threshold:
        return min_lines
    else:
        return 0


class UniversalRedundancyFilter:
    """
    通用切片去重與資訊純化器 (Universal Redundancy Filter)
    徹底過濾切片中任何與已呈現元資料重複之內容，最大化 8,000 字元內的真實邏輯密度。
    """

    LICENSE_PATTERNS = [
        re.compile(r"spdx-license-identifier", re.IGNORECASE),
        re.compile(r"copyright\s+(\(c\)|©|\d{4})", re.IGNORECASE),
        re.compile(r"all\s+rights\s+reserved", re.IGNORECASE),
        re.compile(r"licensed\s+under\s+the\s+(apache|mit|bsd|gpl)", re.IGNORECASE),
        re.compile(r"^/\*+\s*=+\s*\*+/$"),
    ]

    def purify_lines(
        self,
        lines: List[Tuple[int, str]],
        target_line: int = 1,
        symbol_name: str = "",
        signature: str = "",
        docstring_summary: str = "",
        language: str = "",
    ) -> List[Tuple[int, str]]:
        """
        純化代碼切片行清單 [(line_num, text), ...]:
        1. 剔除重複之 Markdown # Heading (與 symbol_name 或 signature 重疊)
        2. 剔除重複之 Docstring 區塊 (Python \"\"\"/''' 或 C/JS /* ... */ 註解)
        3. 剔除版權宣告、SPDX 與 License 樣板
        4. 收斂 2 行以上連續空白行
        5. EC-05 保底：保證至少保留目標定義行 target_line
        """
        if not lines:
            return []

        cleaned: List[Tuple[int, str]] = []
        is_md = (language.lower() in ("markdown", "md") or any(txt.lstrip().startswith("#") for _, txt in lines[:2]))
        in_docstring_block = False
        docstring_quote: Optional[str] = None
        consecutive_empty = 0

        norm_name = symbol_name.strip().lower()
        norm_summary = docstring_summary.strip().lower()

        for ln, txt in lines:
            stripped = txt.strip()

            # 1. 樣板與版權註解剔除
            if any(p.search(stripped) for p in self.LICENSE_PATTERNS):
                continue

            # 2. Markdown Header 重疊剔除
            if is_md and stripped.startswith("#"):
                heading_content = re.sub(r"^#+\s*", "", stripped).strip().lower()
                if (norm_name and (heading_content in norm_name or norm_name in heading_content)) or \
                   (signature and heading_content in signature.lower()):
                    continue

            # 3. 程式碼 Docstring 區塊剔除 (Python: """ 或 ''')
            if not is_md:
                if not in_docstring_block:
                    # 檢測是否進入多行 docstring
                    for q in ('"""', "'''", "/*"):
                        if q in stripped:
                            if q == "/*":
                                end_q = "*/"
                            else:
                                end_q = q

                            # 單行完整 docstring
                            first_idx = stripped.find(q)
                            second_idx = stripped.find(end_q, first_idx + len(q))
                            if second_idx != -1:
                                # 單行註解塊包含 docstring summary 或僅為純註解
                                if ln != target_line:
                                    stripped = ""
                                    break
                            else:
                                # 多行註解起點
                                in_docstring_block = True
                                docstring_quote = end_q
                                break

                    if in_docstring_block:
                        # 若起點非 target_line，或起點僅有引號，直接略過
                        if stripped in ('"""', "'''", "/*", "/**"):
                            continue
                        # 若與 target_line 同行 (例如 def foo(): \"\"\"doc)
                        if ln == target_line:
                            cleaned.append((ln, txt))
                            continue
                        continue

                else:
                    # 處於 docstring 內部
                    if docstring_quote and docstring_quote in stripped:
                        in_docstring_block = False
                        docstring_quote = None
                    continue

                # 4. 單行註解與 docstring_summary 重合剔除
                if norm_summary and (stripped.startswith("#") or stripped.startswith("//")):
                    comment_body = stripped.lstrip("#/").strip().lower()
                    if comment_body and (comment_body in norm_summary or norm_summary in comment_body):
                        continue

            # 5. 連續空白行收斂
            if not stripped:
                consecutive_empty += 1
                if consecutive_empty > 1:
                    continue
            else:
                consecutive_empty = 0

            cleaned.append((ln, txt))

        # 6. EC-05 安全保底：若純化後為空，保底保留 target_line
        if not cleaned:
            target_candidates = [l for l in lines if l[0] == target_line]
            if target_candidates:
                return target_candidates
            return [lines[0]]

        return cleaned


class TerminalStyler:
    """終端 ANSI 色彩樣式器，支援 TTY 偵測與 NO_COLOR 去色守門。"""

    def __init__(self, stream: Any = None):
        if stream is None:
            import sys
            stream = sys.stdout
        self.stream = stream
        is_atty = getattr(stream, "isatty", lambda: False)()
        no_color = bool(os.getenv("NO_COLOR", ""))
        self.enabled = is_atty and not no_color

    def path(self, text: str) -> str:
        """亮藍色"""
        return f"\033[94m{text}\033[0m" if self.enabled else text

    def symbol(self, text: str) -> str:
        """亮綠色"""
        return f"\033[92m{text}\033[0m" if self.enabled else text

    def kind(self, text: str) -> str:
        """亮黃色"""
        return f"\033[93m{text}\033[0m" if self.enabled else text

    def line(self, text: str) -> str:
        """亮青色"""
        return f"\033[96m{text}\033[0m" if self.enabled else text

    def warn(self, text: str) -> str:
        """亮黃色加粗"""
        return f"\033[1;93m{text}\033[0m" if self.enabled else text

    def err(self, text: str) -> str:
        """亮紅色加粗"""
        return f"\033[1;91m{text}\033[0m" if self.enabled else text


class ResultFormatter:
    """
    knowledge-db 呈現層格式化器
    管理輸出路徑、Markdown 超連結與 4 大查詢命令渲染
    """

    def __init__(
        self,
        space_manager: Optional[Any] = None,
        workspace_root: Optional[Path] = None,
        redundancy_filter: Optional[UniversalRedundancyFilter] = None,
        styler: Optional[TerminalStyler] = None,
    ):
        self.space_manager = space_manager
        self.workspace_root = workspace_root
        self.redundancy_filter = redundancy_filter or UniversalRedundancyFilter()
        self.styler = styler or TerminalStyler()

    def _get_workspace_root(self) -> Path:
        if self.workspace_root:
            return self.workspace_root
        try:
            from core import uri
            p_res = uri.resolve("project://", interactive=False)
            if p_res:
                return Path(p_res).resolve()
        except Exception:
            pass
        try:
            from core import uri
            host_dir = uri.get_host_dir()
            if host_dir:
                return Path(host_dir).resolve()
        except Exception:
            pass
        return Path.cwd().resolve()

    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str:
        """將路徑正規化為相對於 Workspace/Project 根目錄之標準相對路徑 (forward slash)"""
        p = Path(file_path)
        ws = self._get_workspace_root()
        try:
            if p.is_absolute():
                rel = p.resolve().relative_to(ws)
                return str(rel).replace("\\", "/")
        except (ValueError, Exception):
            pass
        return str(file_path).replace("\\", "/")

    def to_file_uri(self, file_path: Union[str, Path], line: Optional[int] = None) -> str:
        """將指定檔案路徑轉譯為標準 RFC 8089 file:/// 協議 URI"""
        p = Path(file_path)
        if not p.is_absolute():
            resolved = None
            try:
                from core import uri
                resolved = uri.resolve(f"project://{file_path}", interactive=False)
            except Exception:
                pass
            if resolved:
                p = Path(resolved).resolve()
            else:
                ws = self._get_workspace_root()
                p = (ws / p).resolve()
        else:
            p = p.resolve()

        posix_path = p.as_posix()
        if not posix_path.startswith("/"):
            posix_path = "/" + posix_path

        uri_str = f"file://{posix_path}"
        if line is not None:
            uri_str += f"#L{line}"
        return uri_str

    def format_file_link(
        self,
        file_path: Union[str, Path],
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        use_basename: bool = True,
    ) -> str:
        """格式化為 IDE 相容之 Markdown 檔案超連結標籤: [filename:Lxx~Lyy](file:///abs_path#Lxx)"""
        base_label = Path(file_path).name if use_basename else self.normalize_workspace_path(file_path)
        if line is not None:
            if end_line is not None and end_line > line:
                label = f"{base_label}:L{line}-{end_line}"
            else:
                label = f"{base_label}:L{line}"
        else:
            label = base_label

        uri_str = self.to_file_uri(file_path, line=line)
        return f"[{label}]({uri_str})"

    def format_search_output(
        self,
        results: List[AggregatedFileResult],
        query: str = "",
        detail_mode: str = "auto",
        snippet: bool = False,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """
        格式化 search 檢索結果為結構化終端或 Markdown 報告。
        硬上限限制為 8,000 字元，並自動剔除與既有資訊重複之切片內文。
        """
        if not results:
            if format_type == "md":
                return f"### 🔍 知識庫檢索: `{query}` (未找到符合的結果)"
            return f"[knowledge-db] 檢索查詢: '{query}' (未找到符合的結果)"

        # 1. 自適應分數斷層過濾
        filtered_results: List[AggregatedFileResult] = list(results)
        if limit_mode == "auto":
            top_score = results[0].total_score
            min_thresh = top_score * 0.20 if top_score < 0.5 else max(0.5, top_score * 0.20)
            adapted = []
            for i, r in enumerate(results):
                if r.total_score < min_thresh:
                    break
                if i >= 3:
                    prev_score = results[i - 1].total_score
                    if r.total_score < prev_score * 0.40 or r.total_score < top_score * 0.15:
                        break
                adapted.append(r)
                if len(adapted) >= 15:
                    break
            filtered_results = adapted if adapted else [results[0]]
        elif isinstance(limit_mode, int) and limit_mode > 0:
            filtered_results = results[:limit_mode]

        total_nodes = len(filtered_results)
        is_md = (format_type == "md")
        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        # 2. Header
        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else ("預覽模式" if snippet else ""))
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 🔍 知識庫檢索: `{query}` (共找到 {total_nodes} 個檔案節點{desc_tag}):\n"
        else:
            header = f"[knowledge-db] 檢索查詢: '{query}' (共找到 {total_nodes} 個檔案節點{desc_tag}):"

        lines = [header]
        if not is_md and mode in ("detail", "auto") and snippet:
            lines.append("=" * 85)

        # 3. 逐檔案節點渲染 (受 8,000 字元預算與全域切片去重保護)
        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for rank, res in enumerate(filtered_results, start=1):
            node_lines = []
            first_sym = res.items[0].symbol if res.items else None
            first_line = first_sym.line_number if first_sym else None
            first_end = first_sym.end_line if first_sym else None
            file_link = self.format_file_link(res.file_path, line=first_line, end_line=first_end)

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_results) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            if is_md:
                # Markdown 格式
                if mode == "simple":
                    node_lines.append(f"- **#{rank:02d}** 檔案: {file_link}")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  - `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            pure_lines = self.redundancy_filter.purify_lines(
                                itm.code_snippet.lines,
                                target_line=itm.code_snippet.target_line,
                                symbol_name=sym.name,
                                signature=sym.signature,
                                docstring_summary=itm.code_snippet.docstring_summary,
                                language=res.language or "",
                            )
                            snip_lines = pure_lines[:max_snip_lines] if max_snip_lines else pure_lines
                            if snip_lines:
                                lang = res.language or ""
                                node_lines.append(f"    ```{lang}")
                                for ln, code in snip_lines:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"    {mark} {ln:5d} | {code}")
                                node_lines.append("    ```")
                elif mode == "detail":
                    node_lines.append(f"#### #{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} *({res.language}, {len(res.items)} 個命中項目)*")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"- **#{rank:02d}.{itm_idx}** [{itm.score:05.2f}] `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if sym.signature:
                            node_lines.append(f"  - **簽名**: `{sym.signature}`")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            node_lines.append(f"  - **摘要**: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            node_lines.append(f"  - **摘要**: {itm.snippet}")
                        if itm.matched_terms:
                            node_lines.append(f"  - **命中詞**: {', '.join(itm.matched_terms)}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            pure_lines = self.redundancy_filter.purify_lines(
                                itm.code_snippet.lines,
                                target_line=itm.code_snippet.target_line,
                                symbol_name=sym.name,
                                signature=sym.signature,
                                docstring_summary=itm.code_snippet.docstring_summary,
                                language=res.language or "",
                            )
                            snip_lines = pure_lines[:max_snip_lines] if max_snip_lines else pure_lines
                            if snip_lines:
                                lang = res.language or ""
                                node_lines.append(f"  - **代碼切片** ({line_range}):")
                                node_lines.append(f"    ```{lang}")
                                for ln, code in snip_lines:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"    {mark} {ln:5d} | {code}")
                                node_lines.append("    ```")
                else:  # auto
                    node_lines.append(f"- **#{rank:02d}** [{res.total_score:05.2f}] 檔案: {file_link} *({res.language})*")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  - **#{rank:02d}.{itm_idx}** [{itm.score:05.2f}] `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if sym.signature:
                            node_lines.append(f"    - **簽名**: `{sym.signature}`")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            node_lines.append(f"    - **摘要**: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            node_lines.append(f"    - **摘要**: {itm.snippet}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            pure_lines = self.redundancy_filter.purify_lines(
                                itm.code_snippet.lines,
                                target_line=itm.code_snippet.target_line,
                                symbol_name=sym.name,
                                signature=sym.signature,
                                docstring_summary=itm.code_snippet.docstring_summary,
                                language=res.language or "",
                            )
                            snip_lines = pure_lines[:max_snip_lines] if max_snip_lines else pure_lines
                            if snip_lines:
                                lang = res.language or ""
                                node_lines.append(f"    ```{lang}")
                                for ln, code in snip_lines:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"    {mark} {ln:5d} | {code}")
                                node_lines.append("    ```")
            else:
                # Text / ANSI 終端格式
                if mode == "simple":
                    node_lines.append(f"#{rank:02d} 檔案: {self.styler.path(file_link)}")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  {branch} {self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)} {self.styler.line(f'({line_range})')}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            pure_lines = self.redundancy_filter.purify_lines(
                                itm.code_snippet.lines,
                                target_line=itm.code_snippet.target_line,
                                symbol_name=sym.name,
                                signature=sym.signature,
                                docstring_summary=itm.code_snippet.docstring_summary,
                                language=res.language or "",
                            )
                            effective = pure_lines[:max_snip_lines] if max_snip_lines else pure_lines
                            if effective:
                                max_ln = max(ln for ln, _ in effective)
                                width = max(len(str(max_ln)), 3)
                                for ln, code in effective:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"  {pipe}   {mark} {ln:{width}d} | {code}")
                elif mode == "detail":
                    node_lines.append(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {self.styler.path(file_link)} ({len(res.items)} 個命中項目, {res.language})")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)} {self.styler.line(f'({line_range})')}")
                        if sym.signature:
                            node_lines.append(f"  {pipe}   簽名: {sym.signature}")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            node_lines.append(f"  {pipe}   摘要: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            node_lines.append(f"  {pipe}   摘要: {itm.snippet}")
                        if itm.matched_terms:
                            node_lines.append(f"  {pipe}   命中詞: {', '.join(itm.matched_terms)}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            pure_lines = self.redundancy_filter.purify_lines(
                                itm.code_snippet.lines,
                                target_line=itm.code_snippet.target_line,
                                symbol_name=sym.name,
                                signature=sym.signature,
                                docstring_summary=itm.code_snippet.docstring_summary,
                                language=res.language or "",
                            )
                            effective = pure_lines[:max_snip_lines] if max_snip_lines else pure_lines
                            if effective:
                                node_lines.append(f"  {pipe}   代碼切片 ({line_range}):")
                                max_ln = max(ln for ln, _ in effective)
                                width = max(len(str(max_ln)), 3)
                                for ln, code in effective:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"  {pipe}     {mark} {ln:{width}d} | {code}")
                    node_lines.append("-" * 85)
                else:  # auto
                    if snippet:
                        node_lines.append(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {self.styler.path(file_link)} ({len(res.items)} 個命中項目, {res.language})")
                        for itm_idx, itm in enumerate(res.items, start=1):
                            is_last = (itm_idx == len(res.items))
                            branch = "└──" if is_last else "├──"
                            pipe = "   " if is_last else "│  "
                            sym = itm.symbol
                            line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                            node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)} {self.styler.line(f'({line_range})')}")
                            if sym.signature:
                                node_lines.append(f"  {pipe}   簽名: {sym.signature}")
                            if itm.code_snippet and itm.code_snippet.docstring_summary:
                                node_lines.append(f"  {pipe}   摘要: {itm.code_snippet.docstring_summary}")
                            elif itm.snippet:
                                node_lines.append(f"  {pipe}   摘要: {itm.snippet}")
                            if itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                                pure_lines = self.redundancy_filter.purify_lines(
                                    itm.code_snippet.lines,
                                    target_line=itm.code_snippet.target_line,
                                    symbol_name=sym.name,
                                    signature=sym.signature,
                                    docstring_summary=itm.code_snippet.docstring_summary,
                                    language=res.language or "",
                                )
                                effective = pure_lines[:max_snip_lines] if max_snip_lines else pure_lines
                                if effective:
                                    node_lines.append(f"  {pipe}   代碼切片 ({line_range}):")
                                    max_ln = max(ln for ln, _ in effective)
                                    width = max(len(str(max_ln)), 3)
                                    for ln, code in effective:
                                        mark = ">" if ln == itm.code_snippet.target_line else " "
                                        node_lines.append(f"  {pipe}     {mark} {ln:{width}d} | {code}")
                        node_lines.append("-" * 85)
                    else:
                        if len(res.items) == 1:
                            sym = res.items[0].symbol
                            sym_link = self.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
                            node_lines.append(f"#{rank:02d} 檔案: {self.styler.path(sym_link)} ({self.styler.kind(sym.kind)}:{self.styler.symbol(sym.name)}) [{res.total_score:05.2f}]")
                        else:
                            node_lines.append(f"#{rank:02d} 檔案: {self.styler.path(file_link)} (總分: {res.total_score:05.2f}, {len(res.items)} 項命中):")
                            for itm_idx, itm in enumerate(res.items, start=1):
                                is_last = (itm_idx == len(res.items))
                                branch = "└──" if is_last else "├──"
                                sym = itm.symbol
                                sym_link = self.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
                                node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} {self.styler.path(sym_link)} ({self.styler.kind(sym.kind)}:{self.styler.symbol(sym.name)}) [{itm.score:05.2f}]")

            lines.extend(node_lines)
            rendered_nodes += 1

            # 嚴格 8,000 字元預算上限檢查 (保底 5 個項目)
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_results) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個檔案結果；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個檔案結果；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)

    def format_callers_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """格式化 callers (調用源) 輸出為 ANSI 樹狀圖或 Markdown 格式"""
        target = result.get("target_symbol")
        is_md = (format_type == "md")
        if not target:
            if is_md:
                return f"### 📞 調用源查詢: `{result.get('target_query')}` (未找到相符符號)"
            return f"[knowledge-db] 查無相符目標符號: '{result.get('target_query')}'"

        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        callers = result.get("callers", [])
        total_callers = len(callers)
        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)

        filtered_callers = callers
        if isinstance(limit_mode, int) and limit_mode > 0:
            filtered_callers = callers[:limit_mode]

        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else ("預覽模式" if snippet else ""))
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 📞 調用源追蹤 (Callers): `{target.name}` (共找到 {total_callers} 個調用來源{desc_tag}):\n\n"
            header += f"- **📍 目標符號**: `{target.name}` ({target.kind}) 檔案: {target_link}"
            if target.signature:
                header += f"\n  - **簽名**: `{target.signature}`"
            lines = [header, ""]
        else:
            header = f"[knowledge-db] 符號 '{target.name}' 之上游調用者清單 (Callers - 共 {total_callers} 個來源{desc_tag}):"
            lines = [
                header,
                "-" * 85,
                f"📍 目標符號: `{target.name}` ({target.kind}) 檔案: {target_link}",
            ]
            if mode == "detail" and target.signature:
                lines.append(f"   簽名: {target.signature}")
            lines.append("")

        if not filtered_callers:
            empty_msg = "  (目前尚無靜態調用者依賴)" if not is_md else "> *(目前尚無靜態調用者依賴)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for idx, item in enumerate(filtered_callers, start=1):
            node_lines = []
            sym = item["symbol"]
            sites = item.get("call_sites", [])
            primary_line = sites[0]["line_number"] if sites else sym.line_number
            link_str = self.format_file_link(sym.file_path, line=primary_line)
            is_last = (idx == len(filtered_callers))
            branch = "└──" if is_last else "├──"
            pipe = "   " if is_last else "│  "
            code_snip = item.get("code_snippet")

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_callers) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            if is_md:
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" *(調用點: {', '.join(site_strs)})*" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
                elif mode == "detail":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**)")
                    if sym.signature:
                        node_lines.append(f"  - **簽名**: `{sym.signature}`")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: `{s['scope']}`)" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"  - **調用點**: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"  - **摘要**: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  - **調用代碼切片**:")
                            node_lines.append(f"    ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"    {mark} {ln:5d} | {code}")
                            node_lines.append("    ```")
                else:  # auto
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
            else:
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" [調用點: {', '.join(site_strs)}]" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(sym.kind)}:{self.styler.symbol(sym.name)}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)
                elif mode == "detail":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)})")
                    if sym.signature:
                        node_lines.append(f"{pipe}   簽名: {sym.signature}")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: {s['scope']})" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"{pipe}   調用位置: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"{pipe}   摘要: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(f"{pipe}   調用代碼切片:")
                            node_lines.append(formatted_snip)
                else:  # auto
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(sym.kind)}:{self.styler.symbol(sym.name)}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)

            lines.extend(node_lines)
            rendered_nodes += 1

            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_callers) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個調用來源；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個調用來源；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)

    def format_callees_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """格式化 callees (下游被調用者) 輸出為 ANSI 樹狀圖或 Markdown 格式"""
        target = result.get("target_symbol")
        is_md = (format_type == "md")
        if not target:
            if is_md:
                return f"### 🎯 下游被調用者查詢: `{result.get('target_query')}` (未找到相符符號)"
            return f"[knowledge-db] 查無相符目標符號: '{result.get('target_query')}'"

        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        callees = result.get("callees", [])
        total_callees = len(callees)
        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)

        filtered_callees = callees
        if isinstance(limit_mode, int) and limit_mode > 0:
            filtered_callees = callees[:limit_mode]

        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else ("預覽模式" if snippet else ""))
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 🎯 下游被調用者追蹤 (Callees): `{target.name}` (共調用 {total_callees} 個內部組件{desc_tag}):\n\n"
            header += f"- **📍 目標符號**: `{target.name}` ({target.kind}) 檔案: {target_link}"
            if target.signature:
                header += f"\n  - **簽名**: `{target.signature}`"
            lines = [header, ""]
        else:
            header = f"[knowledge-db] 符號 '{target.name}' 之內部下游依賴清單 (Callees - 共 {total_callees} 個被調用項{desc_tag}):"
            lines = [
                header,
                "-" * 85,
                f"📍 目標符號: `{target.name}` ({target.kind}) 檔案: {target_link}",
            ]
            if mode == "detail" and target.signature:
                lines.append(f"   簽名: {target.signature}")
            lines.append("")

        if not filtered_callees:
            empty_msg = "  (未檢測到內部符號調用，可能為純邏輯函式或葉節點)" if not is_md else "> *(未檢測到內部符號調用，可能為純邏輯函式或葉節點)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for idx, item in enumerate(filtered_callees, start=1):
            node_lines = []
            sym = item["symbol"]
            sites = item.get("call_sites", [])
            primary_line = sites[0]["line_number"] if sites else sym.line_number
            link_str = self.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
            is_last = (idx == len(filtered_callees))
            branch = "└──" if is_last else "├──"
            pipe = "   " if is_last else "│  "
            code_snip = item.get("code_snippet")

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_callees) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            if is_md:
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" *(調用點: {', '.join(site_strs)})*" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
                elif mode == "detail":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**)")
                    if sym.signature:
                        node_lines.append(f"  - **簽名**: `{sym.signature}`")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: `{s['scope']}`)" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"  - **調用點**: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"  - **摘要**: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  - **被調用組件切片**:")
                            node_lines.append(f"    ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"    {mark} {ln:5d} | {code}")
                            node_lines.append("    ```")
                else:  # auto
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
            else:
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" [調用點: {', '.join(site_strs)}]" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(sym.kind)}:{self.styler.symbol(sym.name)}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)
                elif mode == "detail":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)})")
                    if sym.signature:
                        node_lines.append(f"{pipe}   簽名: {sym.signature}")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: {s['scope']})" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"{pipe}   調用位置: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"{pipe}   摘要: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)
                            node_lines.append(f"{pipe}   被調用代碼切片:")
                            node_lines.append(formatted_snip)
                else:  # auto
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(sym.kind)}:{self.styler.symbol(sym.name)}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)

            lines.extend(node_lines)
            rendered_nodes += 1

            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_callees) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個被調用項目；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個被調用項目；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)

    def format_impact_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """格式化 impact (重構影響面拓撲) 輸出為 ANSI 階層樹或 Markdown 格式"""
        target = result.get("target_symbol")
        is_md = (format_type == "md")
        if not target:
            if is_md:
                return f"### 💥 影響面拓撲查詢: `{result.get('target_query')}` (未找到相符符號)"
            return f"[knowledge-db] 查無相符目標符號: '{result.get('target_query')}'"

        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)
        depth = result.get("max_depth", 2)
        total_syms = result.get("total_impacted_symbols", 0)
        total_files = result.get("total_impacted_files", 0)

        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else "")
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 💥 重構影響面擴散拓撲 (Impact Analysis): `{target.name}`{desc_tag}\n\n"
            header += f"- **📍 目標核心符號**: `{target.name}` ({target.kind}) 檔案: {target_link}\n"
            header += f"- **📊 影響半徑**: 擴散深度 `{depth}` 階，波及 `{total_syms}` 個符號 / `{total_files}` 個實體檔案"
            lines = [header, ""]
        else:
            header = f"[knowledge-db] 符號 '{target.name}' 重構影響面擴散拓撲 (Blast Radius: {depth} 階深度, 影響 {total_syms} 個符號 / {total_files} 個檔案{desc_tag}):"
            lines = [
                header,
                "-" * 85,
                f"📍 目標核心符號: `{target.name}` ({target.kind}) 檔案: {target_link}",
            ]
            if mode == "detail" and target.signature:
                lines.append(f"   簽名: {target.signature}")
            lines.append("")

        layers = result.get("layers", {})
        if not layers:
            empty_msg = "  (未發現上游依賴影響點，修改安全)" if not is_md else "> *(未發現上游依賴影響點，修改安全)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0
        max_items = limit_mode if (isinstance(limit_mode, int) and limit_mode > 0) else None

        sorted_depths = sorted(layers.keys())
        for d_idx, d in enumerate(sorted_depths):
            syms = layers[d]
            is_last_depth = (d_idx == len(sorted_depths) - 1)
            depth_branch = "└──" if is_last_depth else "├──"
            tag_name = f"{d} 階直接影響 (Direct Callers)" if d == 1 else f"{d} 階間接影響 (Transitive Callers Level {d})"

            if is_md:
                lines.append(f"#### 階層 {d}：{tag_name} ({len(syms)} 個符號)")
            else:
                icon = "🟢" if d == 1 else "🟡"
                lines.append(f"{depth_branch} {icon} {tag_name} - {len(syms)} 個符號:")

            sub_prefix = "    " if is_last_depth else "│   "
            for s_idx, s in enumerate(syms):
                if max_items is not None and rendered_nodes >= max_items:
                    break

                is_last_sym = (s_idx == len(syms) - 1)
                sub_branch = "└──" if is_last_sym else "├──"
                sub_pipe = "   " if is_last_sym else "│  "
                link_str = self.format_file_link(s.file_path, line=s.line_number, end_line=s.end_line)

                if is_md:
                    if mode == "detail":
                        lines.append(f"- **#{rendered_nodes+1:02d}** 檔案: {link_str} (`{s.kind}`: **{s.name}**)")
                        if s.signature:
                            lines.append(f"  - **簽名**: `{s.signature}`")
                        if s.docstring:
                            doc_sum = s.docstring.strip().split("\n")[0]
                            lines.append(f"  - **摘要**: {doc_sum}")
                    else:
                        lines.append(f"- **#{rendered_nodes+1:02d}** 檔案: {link_str} (`{s.kind}`: **{s.name}**)")
                else:
                    if mode == "detail":
                        lines.append(f"{sub_prefix}{sub_branch} #{rendered_nodes+1:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(s.kind.upper())}: {self.styler.symbol(s.name)})")
                        if s.signature:
                            lines.append(f"{sub_prefix}{sub_pipe}   簽名: {s.signature}")
                        if s.docstring:
                            doc_sum = s.docstring.strip().split("\n")[0]
                            lines.append(f"{sub_prefix}{sub_pipe}   摘要: {doc_sum}")
                    else:
                        lines.append(f"{sub_prefix}{sub_branch} #{rendered_nodes+1:02d} 檔案: {self.styler.path(link_str)} ({self.styler.kind(s.kind)}:{self.styler.symbol(s.name)})")

                rendered_nodes += 1

                if limit_mode == "auto":
                    current_chars = sum(len(l) + 1 for l in lines)
                    if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                        budget_reached = True
                        remaining_count = total_syms - rendered_nodes
                        break

            if budget_reached or (max_items is not None and rendered_nodes >= max_items):
                break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個受影響符號；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個受影響符號；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)
