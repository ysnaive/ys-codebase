"""
knowledge-db 呈現層格式化中樞 (formatter.py)
職責：
1. 全域重複資訊剔除 (UniversalRedundancyFilter)：剔除 Docstring 註解、Markdown Header 重複、版權樣板與空行
2. 8,000 字元自適應動態預算與線性衰減計算器
3. 檔案路徑正規化與 IDE 相容 Markdown 超連結生成
4. search 檢索命令格式化輸出 (format_search_output)
"""

from pathlib import Path
import re
from typing import Any, List, Optional, Tuple, Union

from core.context import get_env
from .schema import AggregatedFileResult

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
    if current_chars >= budget_limit or current_chars >= no_snippet_threshold:
        return 0
    if current_chars < start_decay:
        return max_lines
    if current_chars < min_decay:
        span = max(1, min_decay - start_decay)
        ratio = (current_chars - start_decay) / span
        return max(min_lines, int(round(max_lines - ratio * (max_lines - min_lines))))
    return min_lines


class UniversalRedundancyFilter:
    """
    通用切片去重與資訊純化器 (Universal Redundancy Filter)
    徹底過濾切片中任何與已呈現元資料重複之內容，最大化 8,000 字元內的真實邏輯密度。
    """

    LICENSE_PATTERNS = (
        re.compile(r"spdx-license-identifier", re.IGNORECASE),
        re.compile(r"copyright\s+(\(c\)|©|\d{4})", re.IGNORECASE),
        re.compile(r"all\s+rights\s+reserved", re.IGNORECASE),
        re.compile(r"licensed\s+under\s+the\s+(apache|mit|bsd|gpl)", re.IGNORECASE),
        re.compile(r"^/\*+\s*=+\s*\*+/$"),
    )

    @staticmethod
    def _find_unquoted_block_comment_start(line: str) -> int:
        """
        Scan a single line outside string literals ('...' / \"...\") and single-line comments (# / //)
        to find the starting index of a true `/*` block comment, or -1 if none.
        """
        in_quote: Optional[str] = None
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if in_quote is not None:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_quote:
                    in_quote = None
                i += 1
                continue
            if ch in ('"', "'"):
                in_quote = ch
                i += 1
                continue
            if ch == "#":
                return -1
            if ch == "/" and i + 1 < n:
                nxt = line[i + 1]
                if nxt == "/":
                    return -1
                if nxt == "*":
                    return i
            i += 1
        return -1

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
        5. 安全保底：保證至少保留目標定義行 target_line
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
                if (norm_name and (heading_content in norm_name or norm_name in heading_content)) or (
                    signature and heading_content in signature.lower()
                ):
                    continue

            # 3. 程式碼 Docstring 區塊剔除 (Python: """ 或 '''，C/JS/C#: /* ... */)
            if not is_md:
                if not in_docstring_block:
                    skip_whole_line = False
                    for q in ('"""', "'''"):
                        if stripped.startswith(q):
                            second_idx = stripped.find(q, len(q))
                            if second_idx != -1:
                                if ln != target_line:
                                    skip_whole_line = True
                                break
                            in_docstring_block = True
                            docstring_quote = q
                            break

                    if not skip_whole_line and not in_docstring_block:
                        c_idx = self._find_unquoted_block_comment_start(stripped)
                        if c_idx != -1:
                            close_idx = stripped.find("*/", c_idx + 2)
                            if close_idx != -1:
                                before_c = stripped[:c_idx].strip()
                                after_c = stripped[close_idx + 2 :].strip()
                                if not before_c and not after_c and ln != target_line:
                                    skip_whole_line = True
                            else:
                                in_docstring_block = True
                                docstring_quote = "*/"

                    if skip_whole_line:
                        continue

                    if in_docstring_block:
                        if stripped in ('"""', "'''", "/*", "/**"):
                            continue
                        if ln == target_line:
                            cleaned.append((ln, txt))
                            continue
                        continue
                else:
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

        # 6. 安全保底：若純化後為空，保底保留 target_line
        if not cleaned:
            target_candidates = [l for l in lines if l[0] == target_line]
            return target_candidates if target_candidates else [lines[0]]

        return cleaned


class TerminalStyler:
    """終端 ANSI 色彩樣式器，支援 TTY 偵測與 NO_COLOR 去色守門。"""

    def __init__(self, stream: Any = None):
        if stream is None:
            import sys
            stream = sys.stdout
        self.stream = stream
        is_atty = getattr(stream, "isatty", lambda: False)()
        no_color = bool(get_env("NO_COLOR", ""))
        self.enabled = is_atty and not no_color

    def path(self, text: str) -> str:
        return f"\033[94m{text}\033[0m" if self.enabled else text

    def symbol(self, text: str) -> str:
        return f"\033[92m{text}\033[0m" if self.enabled else text

    def kind(self, text: str) -> str:
        return f"\033[93m{text}\033[0m" if self.enabled else text

    def line(self, text: str) -> str:
        return f"\033[96m{text}\033[0m" if self.enabled else text

    def warn(self, text: str) -> str:
        return f"\033[1;93m{text}\033[0m" if self.enabled else text

    def err(self, text: str) -> str:
        return f"\033[1;91m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m" if self.enabled else text


class ResultFormatter:
    """
    knowledge-db 呈現層格式化器
    管理輸出路徑、Markdown 超連結與 4 大查詢命令渲染
    """

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        redundancy_filter: Optional[UniversalRedundancyFilter] = None,
        styler: Optional[TerminalStyler] = None,
        file_uri: bool = False,
    ):
        self.workspace_root: Optional[Path] = (
            Path(workspace_root).resolve() if workspace_root is not None else None
        )
        self.redundancy_filter = redundancy_filter or UniversalRedundancyFilter()
        self.styler = styler or TerminalStyler()
        self.file_uri = bool(file_uri)

    def get_workspace_root(self) -> Path:
        if self.workspace_root is not None:
            return Path(self.workspace_root).resolve()
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
        from core.context import get_virtual_cwd
        return Path(get_virtual_cwd()).resolve()

    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str:
        """將路徑正規化為相對於 Workspace/Project 根目錄之標準相對路徑 (forward slash)"""
        p = Path(file_path)
        ws = self.get_workspace_root()
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
                ws = self.get_workspace_root()
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
        file_uri: Optional[bool] = None,
    ) -> str:
        """格式化為相對路徑行號標籤 rel/path.py:Lxx-yy，或於 file_uri=True 時輸出 [filename:Lxx-yy](file:///abs_path#Lxx)"""
        use_uri = self.file_uri if file_uri is None else bool(file_uri)
        base_label = (
            Path(file_path).name
            if (use_uri and use_basename)
            else self.normalize_workspace_path(file_path)
        )
        if line is not None:
            label = f"{base_label}:L{line}-{end_line}" if (end_line is not None and end_line > line) else f"{base_label}:L{line}"
        else:
            label = base_label

        if not use_uri:
            return label

        uri_str = self.to_file_uri(file_path, line=line)
        return f"[{label}]({uri_str})"

    @staticmethod
    def _format_line_range(sym: Any) -> str:
        if sym.end_line and sym.end_line > sym.line_number:
            return f"Lines {sym.line_number}~{sym.end_line}"
        return f"Line {sym.line_number}"

    @staticmethod
    def _extract_item_summary(itm: Any) -> str:
        if itm.code_snippet and itm.code_snippet.docstring_summary:
            return itm.code_snippet.docstring_summary
        return itm.snippet or ""

    def _extract_purified_snippet_lines(
        self, itm: Any, language: str, max_snip_lines: Optional[int]
    ) -> List[Tuple[int, str]]:
        if not (itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0)):
            return []
        sym = itm.symbol
        pure_lines = self.redundancy_filter.purify_lines(
            itm.code_snippet.lines,
            target_line=itm.code_snippet.target_line,
            symbol_name=sym.name,
            signature=sym.signature,
            docstring_summary=itm.code_snippet.docstring_summary,
            language=language or "",
        )
        return pure_lines[:max_snip_lines] if max_snip_lines else pure_lines

    def _append_md_snippet_block(
        self,
        node_lines: List[str],
        itm: Any,
        language: str,
        max_snip_lines: Optional[int],
        header_line: Optional[str] = None,
    ) -> None:
        snip_lines = self._extract_purified_snippet_lines(itm, language, max_snip_lines)
        if not snip_lines:
            return
        if header_line:
            node_lines.append(header_line)
        node_lines.append(f"    ```{language or ''}")
        target_ln = itm.code_snippet.target_line
        for ln, code in snip_lines:
            mark = ">" if ln == target_ln else " "
            node_lines.append(f"    {mark} {ln:5d} | {code}")
        node_lines.append("    ```")

    def _append_text_snippet_block(
        self,
        node_lines: List[str],
        itm: Any,
        language: str,
        max_snip_lines: Optional[int],
        pipe: str,
        line_range: str,
        include_header: bool = False,
    ) -> None:
        effective = self._extract_purified_snippet_lines(itm, language, max_snip_lines)
        if not effective:
            return
        if include_header:
            node_lines.append(f"  {pipe}   代碼切片 ({line_range}):")
            code_indent = f"  {pipe}     "
        else:
            code_indent = f"  {pipe}   "
        max_ln = max(ln for ln, _ in effective)
        width = max(len(str(max_ln)), 3)
        target_ln = itm.code_snippet.target_line
        for ln, code in effective:
            mark = ">" if ln == target_ln else " "
            node_lines.append(f"{code_indent}{mark} {ln:{width}d} | {code}")

    def format_search_output(
        self,
        results: List[AggregatedFileResult],
        query: str = "",
        detail_mode: str = "auto",
        snippet: bool = False,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
        file_uri: Optional[bool] = None,
    ) -> str:
        """
        格式化 search 檢索結果為結構化終端或 Markdown 報告。
        硬上限限制為 8,000 字元，並自動剔除與既有資訊重複之切片內文。
        """
        if not results:
            if format_type == "md":
                return f"###  知識庫檢索: `{query}` (未找到符合的結果)"
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
        eff_file_uri = True if is_md else (self.file_uri if file_uri is None else bool(file_uri))
        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        # 2. Header
        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else ("預覽模式" if snippet else ""))
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"###  知識庫檢索: `{query}` (共找到 {total_nodes} 個檔案節點{desc_tag}):\n"
        else:
            header = f"[knowledge-db] 檢索查詢: '{query}' (共找到 {total_nodes} 個檔案節點{desc_tag}):"

        lines = [header]
        if not is_md and mode in ("detail", "auto") and snippet:
            lines.append("=" * 85)

        current_chars = sum(len(l) + 1 for l in lines)
        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for rank, res in enumerate(filtered_results, start=1):
            node_lines: List[str] = []
            first_sym = res.items[0].symbol if res.items else None
            first_line = first_sym.line_number if first_sym else None
            first_end = first_sym.end_line if first_sym else None
            if not is_md and mode == "auto" and not snippet and len(res.items) > 1:
                file_link = self.format_file_link(res.file_path, use_basename=False, file_uri=eff_file_uri)
            else:
                file_link = self.format_file_link(
                    res.file_path,
                    line=first_line,
                    end_line=first_end,
                    file_uri=eff_file_uri,
                )

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_results) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            lang_str = res.language or ""
            if is_md:
                if mode == "simple":
                    node_lines.append(f"- **#{rank:02d}** 檔案: {file_link}")
                    for itm in res.items:
                        sym = itm.symbol
                        line_range = self._format_line_range(sym)
                        node_lines.append(f"  - `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if snippet:
                            self._append_md_snippet_block(node_lines, itm, lang_str, max_snip_lines)
                elif mode == "detail":
                    node_lines.append(f"#### #{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} *({res.language}, {len(res.items)} 個命中項目)*")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = self._format_line_range(sym)
                        node_lines.append(f"- **#{rank:02d}.{itm_idx}** [{itm.score:05.2f}] `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if sym.signature:
                            node_lines.append(f"  - **簽名**: `{sym.signature}`")
                        summary_txt = self._extract_item_summary(itm)
                        if summary_txt:
                            node_lines.append(f"  - **摘要**: {summary_txt}")
                        if itm.matched_terms:
                            node_lines.append(f"  - **命中詞**: {', '.join(itm.matched_terms)}")
                        if snippet:
                            self._append_md_snippet_block(
                                node_lines,
                                itm,
                                lang_str,
                                max_snip_lines,
                                header_line=f"  - **代碼切片** ({line_range}):",
                            )
                else:  # auto
                    node_lines.append(f"- **#{rank:02d}** [{res.total_score:05.2f}] 檔案: {file_link} *({res.language})*")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = self._format_line_range(sym)
                        node_lines.append(f"  - **#{rank:02d}.{itm_idx}** [{itm.score:05.2f}] `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if sym.signature:
                            node_lines.append(f"    - **簽名**: `{sym.signature}`")
                        summary_txt = self._extract_item_summary(itm)
                        if summary_txt:
                            node_lines.append(f"    - **摘要**: {summary_txt}")
                        if snippet:
                            self._append_md_snippet_block(node_lines, itm, lang_str, max_snip_lines)
            else:
                if mode == "simple":
                    node_lines.append(f"#{rank:02d} 檔案: {self.styler.path(file_link)}")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = self._format_line_range(sym)
                        node_lines.append(f"  {branch} {self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)} {self.styler.line(f'({line_range})')}")
                        if snippet:
                            self._append_text_snippet_block(
                                node_lines, itm, lang_str, max_snip_lines, pipe, line_range, include_header=False
                            )
                elif mode == "detail" or (mode == "auto" and snippet):
                    node_lines.append(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {self.styler.path(file_link)} ({len(res.items)} 個命中項目, {res.language})")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = self._format_line_range(sym)
                        node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)} {self.styler.line(f'({line_range})')}")
                        if sym.signature:
                            node_lines.append(f"  {pipe}   簽名: {sym.signature}")
                        summary_txt = self._extract_item_summary(itm)
                        if summary_txt:
                            node_lines.append(f"  {pipe}   摘要: {summary_txt}")
                        if mode == "detail" and itm.matched_terms:
                            node_lines.append(f"  {pipe}   命中詞: {', '.join(itm.matched_terms)}")
                        if snippet:
                            self._append_text_snippet_block(
                                node_lines, itm, lang_str, max_snip_lines, pipe, line_range, include_header=True
                            )
                    node_lines.append("-" * 85)
                else:  # auto without snippet
                    if len(res.items) == 1:
                        sym = res.items[0].symbol
                        sym_link = self.format_file_link(
                            sym.file_path,
                            line=sym.line_number,
                            end_line=sym.end_line,
                            file_uri=eff_file_uri,
                        )
                        node_lines.append(
                            f"#{rank:02d} 檔案: {self.styler.path(sym_link)} "
                            f"({self.styler.kind(sym.kind.upper())}:{self.styler.symbol(sym.name)}) [{res.total_score:05.2f}]"
                        )
                    else:
                        node_lines.append(
                            f"#{rank:02d} 檔案: {self.styler.path(file_link)} "
                            f"(總分: {res.total_score:05.2f}, {len(res.items)} 項命中):"
                        )
                        for itm_idx, itm in enumerate(res.items, start=1):
                            is_last = (itm_idx == len(res.items))
                            branch = "└──" if is_last else "├──"
                            sym = itm.symbol
                            line_range = self._format_line_range(sym)
                            node_lines.append(
                                f"  {branch} #{rank:02d}.{itm_idx} "
                                f"{self.styler.kind(sym.kind.upper())}: {self.styler.symbol(sym.name)} "
                                f"{self.styler.line(f'({line_range})')} [{itm.score:05.2f}]"
                            )

            lines.extend(node_lines)
            current_chars += sum(len(l) + 1 for l in node_lines)
            rendered_nodes += 1

            # 嚴格 8,000 字元預算上限檢查 (保底 5 個項目)
            if limit_mode == "auto":
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_results) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> [*] *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個檔案結果；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個檔案結果；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)
