"""
knowledge-db SPICE (.cir, .sp, .spice, .net, .cdl) 網表語意解析器 (SpiceParser)
"""

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple, Union

from ..schema import LanguageType, MemberInfo, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.spice")


@dataclass
class LogicalLine:
    """SPICE 預處理後之邏輯行模型 (含多行接續合併與原始行號追蹤)"""
    raw_text: str
    clean_text: str
    start_line: int
    end_line: int
    docstring: str = ""


@dataclass
class _SubcircuitScope:
    """子電路內部作用域暫存容器"""
    name: str
    start_line: int
    signature: str
    docstring: str = ""
    members: List[MemberInfo] = field(default_factory=list)


class SpiceParser(BaseParser):
    """
    SPICE 網表高精度語意解析器
    支援標準 Berkeley SPICE3、HSPICE、ngspice、LTspice 及 CDL/LVS 網表方言。
    """

    SUPPORTED_EXTENSIONS: Set[str] = {".cir", ".sp", ".spice", ".net", ".cdl"}

    # 常用元件前綴字母集合 (大小寫不敏感)
    ELEMENT_PREFIXES: Set[str] = {
        "X", "M", "Q", "D", "J", "Z", "R", "C", "L", "K",
        "V", "I", "E", "F", "G", "H", "B", "S", "W", "T", "U", "O", "A"
    }

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """
        判斷檔案副檔名是否為支援之 SPICE 網表類型 (大小寫不敏感)。
        """
        if not file_path:
            return False
        p = Path(file_path) if isinstance(file_path, str) else file_path
        return p.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """
        執行雙階段 SPICE 語意解析：
        Stage 1: 邏輯行聚合與前置處理 (處理 '+' 接續、註解剝離與 Docstring 萃取)
        Stage 2: 階層狀態機解析 (.subckt 作用域、.model、.param、.include 與元件實例)
        :param file_path: 相對於來源根目錄之正規化路徑 (forward slash)
        :param content: 檔案文字內容
        :param space: 所屬空間識別名稱
        :return: 提取之 UnifiedSymbol 清單
        """
        if not content or not content.strip():
            return []

        try:
            logical_lines = self._aggregate_logical_lines(content)
            return self._parse_state_machine(logical_lines, file_path=file_path, space=space, total_lines=len(content.splitlines()))
        except Exception as e:
            logger.warning(f"Unexpected error during SpiceParser.parse '{file_path}': {e}", exc_info=True)
            return []

    # =========================================================================
    # Stage 1: 行聚合與預處理狀態機
    # =========================================================================

    def _strip_inline_comment(self, text: str) -> str:
        """
        安全剝離行尾註解 (以 ';' 或 '$' 開始)，但保留引號或大括號內部之字元。
        """
        in_single_quote = False
        in_double_quote = False
        in_brace = False
        in_paren = False

        for idx, ch in enumerate(text):
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif ch == '{' and not (in_single_quote or in_double_quote):
                in_brace = True
            elif ch == '}' and in_brace:
                in_brace = False
            elif ch == '(' and not (in_single_quote or in_double_quote):
                in_paren = True
            elif ch == ')' and in_paren:
                in_paren = False
            elif (ch == ';' or ch == '$') and not (in_single_quote or in_double_quote or in_brace or in_paren):
                # 命中行尾註解
                return text[:idx].rstrip()

        return text.rstrip()

    def _aggregate_logical_lines(self, content: str) -> List[LogicalLine]:
        """
        Stage 1:
        1. 識別整行註解 ('*') 並累積為 Docstring 候選。
        2. 合併行首為 '+' 之接續行，精準追蹤起始與結束行號。
        3. 剝離行尾 ';' 與 '$' 註解。
        4. 產出純淨之 LogicalLine 清單。
        """
        lines = content.splitlines()
        logical_lines: List[LogicalLine] = []

        current_raw_parts: List[str] = []
        current_clean_parts: List[str] = []
        start_line: int = 0
        end_line: int = 0
        current_docstring_lines: List[str] = []

        def flush_active():
            nonlocal current_raw_parts, current_clean_parts, start_line, end_line, current_docstring_lines
            if current_clean_parts:
                full_clean = " ".join(current_clean_parts).strip()
                if full_clean:
                    full_raw = "\n".join(current_raw_parts)
                    doc = "\n".join(current_docstring_lines).strip()
                    logical_lines.append(
                        LogicalLine(
                            raw_text=full_raw,
                            clean_text=full_clean,
                            start_line=start_line,
                            end_line=end_line,
                            docstring=doc,
                        )
                    )
                    current_docstring_lines = []
            current_raw_parts = []
            current_clean_parts = []
            start_line = 0
            end_line = 0

        for line_idx, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()

            # 空白行
            if not stripped:
                # 若已有 active line，不立即清空 docstring，但可能結束接續
                continue

            # 整行註解行 (行首第 1 個非空白字元為 '*')
            if stripped.startswith("*"):
                # 若不是接續行，先 flush 之前 active 的指令
                flush_active()
                comment_body = stripped.lstrip("*").strip()
                # 萃取為 Docstring 候選
                if comment_body:
                    current_docstring_lines.append(comment_body)
                continue

            # 接續行 (行首第 1 個非空白字元為 '+')
            if stripped.startswith("+"):
                if current_clean_parts:
                    # 屬於前一個指令的延續
                    cont_body = stripped[1:].strip()
                    clean_cont = self._strip_inline_comment(cont_body)
                    if clean_cont:
                        current_clean_parts.append(clean_cont)
                    current_raw_parts.append(raw_line)
                    end_line = line_idx
                    continue
                else:
                    # 孤立的 '+' 行，視為獨立指令起點
                    stripped = stripped[1:].strip()

            # 遇到新的非註解、非接續指令行
            flush_active()

            clean_text = self._strip_inline_comment(stripped)
            if clean_text:
                start_line = line_idx
                end_line = line_idx
                current_raw_parts.append(raw_line)
                current_clean_parts.append(clean_text)

        flush_active()
        return logical_lines

    # =========================================================================
    # Stage 2: 階層語意狀態機
    # =========================================================================

    def _split_tokens(self, text: str) -> List[str]:
        """
        按空白切割 Token，但保護引號、括號與運算式。
        """
        tokens: List[str] = []
        current: List[str] = []
        in_single = False
        in_double = False
        in_paren = 0
        in_brace = 0

        for ch in text:
            if ch == "'" and not in_double:
                in_single = not in_single
                current.append(ch)
            elif ch == '"' and not in_single:
                in_double = not in_double
                current.append(ch)
            elif ch == '(' and not (in_single or in_double):
                in_paren += 1
                current.append(ch)
            elif ch == ')' and not (in_single or in_double):
                if in_paren > 0:
                    in_paren -= 1
                current.append(ch)
            elif ch == '{' and not (in_single or in_double):
                in_brace += 1
                current.append(ch)
            elif ch == '}' and not (in_single or in_double):
                if in_brace > 0:
                    in_brace -= 1
                current.append(ch)
            elif ch.isspace() and not (in_single or in_double or in_paren > 0 or in_brace > 0):
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(ch)

        if current:
            tokens.append("".join(current))

        return tokens

    def _parse_params_from_line(self, tokens: List[str]) -> List[Tuple[str, str]]:
        """
        從 .param 指令行中解析出所有 (param_name, param_expr) 鍵值對。
        範例: .param VDD=1.8V VSS=0V GAIN='10k*2'
        """
        params: List[Tuple[str, str]] = []
        full_line = " ".join(tokens[1:])  # 去除 .param

        # 匹配 key = value 模式
        # 支援 W=1u, L='0.18u', TEMP={25+2}
        pattern = r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*('[^']*'|\{[^}]*\}|\([^)]*\)|[^\s=]+)"
        matches = re.findall(pattern, full_line)
        for name, val in matches:
            params.append((name, val.strip()))

        # 若正則未匹配出（如純賦值形式），嘗試簡單分割
        if not params:
            for tok in tokens[1:]:
                if "=" in tok:
                    parts = tok.split("=", 1)
                    if parts[0].strip():
                        params.append((parts[0].strip(), parts[1].strip()))

        return params

    def _parse_state_machine(
        self,
        logical_lines: List[LogicalLine],
        file_path: str,
        space: str,
        total_lines: int
    ) -> List[UnifiedSymbol]:
        """
        Stage 2: 遍歷邏輯行，維護 Subcircuit 作用域並萃取所有 UnifiedSymbol。
        """
        symbols: List[UnifiedSymbol] = []
        current_subckt: Optional[_SubcircuitScope] = None

        for idx, log_line in enumerate(logical_lines):
            clean = log_line.clean_text
            tokens = self._split_tokens(clean)
            if not tokens:
                continue

            first_tok = tokens[0]
            first_tok_upper = first_tok.upper()

            # 首行標題 (Title Line) 容錯判定
            if idx == 0 and not first_tok.startswith(".") and not any(first_tok_upper.startswith(p) for p in self.ELEMENT_PREFIXES):
                logger.debug(f"Skipping probable SPICE title line: '{clean}'")
                continue

            # -----------------------------------------------------------------
            # 1. 子電路定義 (.SUBCKT ... .ENDS / .MACRO ... .EOM)
            # -----------------------------------------------------------------
            if first_tok_upper in {".SUBCKT", ".MACRO"}:
                if len(tokens) >= 2:
                    subckt_name = tokens[1]
                    # 若前已有未閉合 subcircuit (EC-02)，先閉合前一個
                    if current_subckt is not None:
                        sym = UnifiedSymbol(
                            id=UnifiedSymbol.compute_id(space, file_path, current_subckt.name, SymbolKind.CLASS.value, current_subckt.start_line),
                            name=current_subckt.name,
                            kind=SymbolKind.CLASS.value,
                            file_path=file_path,
                            line_number=current_subckt.start_line,
                            end_line=log_line.start_line - 1,
                            language=LanguageType.SPICE.value,
                            docstring=current_subckt.docstring,
                            signature=current_subckt.signature,
                            members=current_subckt.members,
                            metadata={"space": space, "type": "subcircuit"},
                        )
                        symbols.append(sym)

                    current_subckt = _SubcircuitScope(
                        name=subckt_name,
                        start_line=log_line.start_line,
                        signature=clean,
                        docstring=log_line.docstring,
                        members=[],
                    )
                continue

            if first_tok_upper in {".ENDS", ".EOM"}:
                if current_subckt is not None:
                    sym = UnifiedSymbol(
                        id=UnifiedSymbol.compute_id(space, file_path, current_subckt.name, SymbolKind.CLASS.value, current_subckt.start_line),
                        name=current_subckt.name,
                        kind=SymbolKind.CLASS.value,
                        file_path=file_path,
                        line_number=current_subckt.start_line,
                        end_line=log_line.end_line,
                        language=LanguageType.SPICE.value,
                        docstring=current_subckt.docstring,
                        signature=current_subckt.signature,
                        members=current_subckt.members,
                        metadata={"space": space, "type": "subcircuit"},
                    )
                    symbols.append(sym)
                    current_subckt = None
                continue

            # -----------------------------------------------------------------
            # 2. 元件模型定義 (.MODEL)
            # -----------------------------------------------------------------
            if first_tok_upper == ".MODEL":
                if len(tokens) >= 2:
                    model_name = tokens[1]
                    model_type = tokens[2] if len(tokens) >= 3 else ""
                    if current_subckt is not None:
                        # 記錄於 Subcircuit members
                        current_subckt.members.append(
                            MemberInfo(
                                name=model_name,
                                kind=SymbolKind.STRUCT.value,
                                signature=clean,
                                docstring=log_line.docstring,
                                line_number=log_line.start_line,
                            )
                        )
                    else:
                        # 頂層 Model 符號
                        symbols.append(
                            UnifiedSymbol(
                                id=UnifiedSymbol.compute_id(space, file_path, model_name, SymbolKind.STRUCT.value, log_line.start_line),
                                name=model_name,
                                kind=SymbolKind.STRUCT.value,
                                file_path=file_path,
                                line_number=log_line.start_line,
                                end_line=log_line.end_line,
                                language=LanguageType.SPICE.value,
                                docstring=log_line.docstring,
                                signature=clean,
                                metadata={"space": space, "model_type": model_type},
                            )
                        )
                continue

            # -----------------------------------------------------------------
            # 3. 參數定義 (.PARAM)
            # -----------------------------------------------------------------
            if first_tok_upper == ".PARAM":
                params = self._parse_params_from_line(tokens)
                for p_name, p_val in params:
                    sig = f".param {p_name}={p_val}"
                    if current_subckt is not None:
                        current_subckt.members.append(
                            MemberInfo(
                                name=p_name,
                                kind=SymbolKind.VARIABLE.value,
                                signature=sig,
                                docstring=log_line.docstring,
                                line_number=log_line.start_line,
                            )
                        )
                    else:
                        symbols.append(
                            UnifiedSymbol(
                                id=UnifiedSymbol.compute_id(space, file_path, p_name, SymbolKind.VARIABLE.value, log_line.start_line),
                                name=p_name,
                                kind=SymbolKind.VARIABLE.value,
                                file_path=file_path,
                                line_number=log_line.start_line,
                                end_line=log_line.end_line,
                                language=LanguageType.SPICE.value,
                                docstring=log_line.docstring,
                                signature=sig,
                                metadata={"space": space, "value": p_val},
                            )
                        )
                continue

            # -----------------------------------------------------------------
            # 4. 引用與包含指令 (.INCLUDE / .INC / .LIB / .HDL)
            # -----------------------------------------------------------------
            if first_tok_upper in {".INCLUDE", ".INC", ".LIB", ".HDL"}:
                if len(tokens) >= 2:
                    raw_target = tokens[1].strip("'\"")
                    symbols.append(
                        UnifiedSymbol(
                            id=UnifiedSymbol.compute_id(space, file_path, raw_target, SymbolKind.MACRO.value, log_line.start_line),
                            name=raw_target,
                            kind=SymbolKind.MACRO.value,
                            file_path=file_path,
                            line_number=log_line.start_line,
                            end_line=log_line.end_line,
                            language=LanguageType.SPICE.value,
                            docstring=log_line.docstring,
                            signature=clean,
                            metadata={"space": space, "directive": first_tok_upper},
                        )
                    )
                continue

            # -----------------------------------------------------------------
            # 5. 全域節點宣告 (.GLOBAL)
            # -----------------------------------------------------------------
            if first_tok_upper == ".GLOBAL":
                for node_name in tokens[1:]:
                    symbols.append(
                        UnifiedSymbol(
                            id=UnifiedSymbol.compute_id(space, file_path, node_name, SymbolKind.MACRO.value, log_line.start_line),
                            name=node_name,
                            kind=SymbolKind.MACRO.value,
                            file_path=file_path,
                            line_number=log_line.start_line,
                            end_line=log_line.end_line,
                            language=LanguageType.SPICE.value,
                            docstring=log_line.docstring,
                            signature=clean,
                            metadata={"space": space, "type": "global_node"},
                        )
                    )
                continue

            # -----------------------------------------------------------------
            # 6. 元件網表實例 (Element Instantiations)
            # -----------------------------------------------------------------
            prefix_char = first_tok_upper[0] if first_tok_upper else ""

            # 6.1 子電路呼叫實例 (X...)
            if prefix_char == "X":
                inst_name = first_tok
                if current_subckt is not None:
                    current_subckt.members.append(
                        MemberInfo(
                            name=inst_name,
                            kind=SymbolKind.FUNCTION.value,
                            signature=clean,
                            docstring=log_line.docstring,
                            line_number=log_line.start_line,
                        )
                    )
                else:
                    # 頂層子電路實例提升為頂層符號
                    symbols.append(
                        UnifiedSymbol(
                            id=UnifiedSymbol.compute_id(space, file_path, inst_name, SymbolKind.FUNCTION.value, log_line.start_line),
                            name=inst_name,
                            kind=SymbolKind.FUNCTION.value,
                            file_path=file_path,
                            line_number=log_line.start_line,
                            end_line=log_line.end_line,
                            language=LanguageType.SPICE.value,
                            docstring=log_line.docstring,
                            signature=clean,
                            metadata={"space": space, "type": "subcircuit_instance"},
                        )
                    )
                continue

            # 6.2 晶體管、二極體、被動元件與電源實例 (M, Q, D, J, Z, R, C, L, V, I, E, G, B...)
            if prefix_char in self.ELEMENT_PREFIXES:
                inst_name = first_tok
                if current_subckt is not None:
                    current_subckt.members.append(
                        MemberInfo(
                            name=inst_name,
                            kind=SymbolKind.VARIABLE.value,
                            signature=clean,
                            docstring=log_line.docstring,
                            line_number=log_line.start_line,
                        )
                    )
                else:
                    # 頂層獨立電源源 (V/I) 或關鍵行為模組，可依需求提升
                    if prefix_char in {"V", "I", "B"}:
                        symbols.append(
                            UnifiedSymbol(
                                id=UnifiedSymbol.compute_id(space, file_path, inst_name, SymbolKind.VARIABLE.value, log_line.start_line),
                                name=inst_name,
                                kind=SymbolKind.VARIABLE.value,
                                file_path=file_path,
                                line_number=log_line.start_line,
                                end_line=log_line.end_line,
                                language=LanguageType.SPICE.value,
                                docstring=log_line.docstring,
                                signature=clean,
                                metadata={"space": space, "type": f"element_{prefix_char}"},
                            )
                        )
                continue

        # 未閉合 Subcircuit 容錯處理 (EC-02)
        if current_subckt is not None:
            sym = UnifiedSymbol(
                id=UnifiedSymbol.compute_id(space, file_path, current_subckt.name, SymbolKind.CLASS.value, current_subckt.start_line),
                name=current_subckt.name,
                kind=SymbolKind.CLASS.value,
                file_path=file_path,
                line_number=current_subckt.start_line,
                end_line=total_lines,
                language=LanguageType.SPICE.value,
                docstring=current_subckt.docstring,
                signature=current_subckt.signature,
                members=current_subckt.members,
                metadata={"space": space, "type": "subcircuit", "unclosed": True},
            )
            symbols.append(sym)

        return symbols
