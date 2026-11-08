"""
SPICE Circuit Netlist Semantic Parser (`.cir`, `.sp`, `.spice`, `.net`, `.cdl`).

Two-stage architecture:
- Stage 1: Line Continuation (`+`) Aggregator & Preceding Comment (`*`, `;`, `$`) Docstring Extractor.
- Stage 2: Hierarchical Subcircuit (`.subckt` ... `.ends`) & Directive State Machine.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import FrozenSet, List, Optional, Tuple, Union

from core.log import log_debug

from ..schema import LanguageType, MemberInfo, SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import BaseParser


@dataclass(frozen=True)
class LogicalLine:
    """Represents a logical SPICE line after merging '+' continuations."""

    start_line: int
    end_line: int
    clean_text: str
    raw_text: str
    docstring: str = ""


class _SubcircuitScope:
    """Active subcircuit scope accumulator during Stage 2 parsing."""

    def __init__(
        self,
        name: str,
        start_line: int,
        signature: str,
        docstring: str,
        members: Optional[List[MemberInfo]] = None,
    ) -> None:
        self.name = name
        self.start_line = start_line
        self.signature = signature
        self.docstring = docstring
        self.members: List[MemberInfo] = list(members) if members is not None else []


def _split_tokens(text: str) -> List[str]:
    """Split a SPICE logical line into tokens while preserving quoted strings, parentheses, and braces."""
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
        elif ch == "(" and not (in_single or in_double):
            in_paren += 1
            current.append(ch)
        elif ch == ")" and not (in_single or in_double):
            if in_paren > 0:
                in_paren -= 1
            current.append(ch)
        elif ch == "{" and not (in_single or in_double):
            in_brace += 1
            current.append(ch)
        elif ch == "}" and not (in_single or in_double):
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


def _parse_params_from_line(tokens: List[str]) -> List[Tuple[str, str]]:
    """Extract `(name, value)` pairs from a `.PARAM` directive token list."""
    params: List[Tuple[str, str]] = []
    full_line = " ".join(tokens[1:])

    pattern = r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*('[^']*'|\{[^}]*\}|\([^)]*\)|[^\s=]+)"
    matches = re.findall(pattern, full_line)
    for name, val in matches:
        params.append((name, val.strip()))

    if not params:
        for tok in tokens[1:]:
            if "=" in tok:
                parts = tok.split("=", 1)
                if parts[0].strip():
                    params.append((parts[0].strip(), parts[1].strip()))

    return params


class SpiceParser(BaseParser):
    """
    SPICE Netlist Parser supporting HSPICE, ngspice, LTspice, Spectre/CDL dialects.
    """

    SUPPORTED_EXTENSIONS: FrozenSet[str] = frozenset({".cir", ".sp", ".spice", ".net", ".cdl", ".netlist"})

    ELEMENT_PREFIXES: FrozenSet[str] = frozenset({
        "M", "Q", "D", "J", "Z", "R", "C", "L", "K",
        "V", "I", "E", "F", "G", "H", "B", "X", "T", "U", "W", "S",
    })

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        if not file_path:
            return False
        ext = Path(str(file_path)).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: Union[str, Path], content: str, space: str) -> List[UnifiedSymbol]:
        if not content or not content.strip():
            return []

        norm_path = str(file_path).replace("\\", "/")
        raw_lines = content.splitlines()
        total_lines = len(raw_lines)

        logical_lines = self._aggregate_logical_lines(raw_lines)
        if not logical_lines:
            return []

        return self._parse_state_machine(logical_lines, norm_path, space, total_lines)

    # =========================================================================
    # Stage 1: Line Continuation & Comment Aggregator
    # =========================================================================

    @staticmethod
    def _strip_inline_comment(line: str) -> str:
        in_single = False
        in_double = False
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                if ch == ";" or ch == "$":
                    return line[:i].strip()
        return line.strip()

    @staticmethod
    def _extract_comment_text(stripped_line: str) -> Optional[str]:
        if stripped_line.startswith("*"):
            return stripped_line.lstrip("*").strip()
        if stripped_line.startswith(";"):
            return stripped_line.lstrip(";").strip()
        if stripped_line.startswith("$"):
            return stripped_line.lstrip("$").strip()
        return None

    def _aggregate_logical_lines(self, raw_lines: List[str]) -> List[LogicalLine]:
        logical_lines: List[LogicalLine] = []
        pending_comments: List[str] = []

        current_clean_parts: List[str] = []
        current_raw_parts: List[str] = []
        current_doc: str = ""
        start_line: int = 1
        end_line: int = 1

        def flush_active() -> None:
            nonlocal current_clean_parts, current_raw_parts, current_doc
            if current_clean_parts:
                merged_clean = " ".join(p for p in current_clean_parts if p)
                merged_raw = "\n".join(current_raw_parts)
                if merged_clean:
                    logical_lines.append(
                        LogicalLine(
                            start_line=start_line,
                            end_line=end_line,
                            clean_text=merged_clean,
                            raw_text=merged_raw,
                            docstring=current_doc,
                        )
                    )
                current_clean_parts = []
                current_raw_parts = []
                current_doc = ""

        for idx, raw_line in enumerate(raw_lines):
            line_idx = idx + 1
            stripped = raw_line.strip()

            if not stripped:
                continue

            comment_body = self._extract_comment_text(stripped)
            if comment_body is not None:
                flush_active()
                if comment_body:
                    pending_comments.append(comment_body)
                continue

            if stripped.startswith("+"):
                if current_clean_parts:
                    cont_body = stripped[1:].strip()
                    clean_cont = self._strip_inline_comment(cont_body)
                    if clean_cont:
                        current_clean_parts.append(clean_cont)
                    current_raw_parts.append(raw_line)
                    end_line = line_idx
                    continue
                else:
                    stripped = stripped[1:].strip()

            flush_active()

            clean_text = self._strip_inline_comment(stripped)
            if clean_text:
                start_line = line_idx
                end_line = line_idx
                current_raw_parts.append(raw_line)
                current_clean_parts.append(clean_text)
                if pending_comments:
                    current_doc = "\n".join(pending_comments)
                    pending_comments.clear()

        flush_active()
        return logical_lines

    # =========================================================================
    # Stage 2: Hierarchical State Machine
    # =========================================================================

    @staticmethod
    def _build_subckt_symbol(
        subckt: _SubcircuitScope,
        file_path: str,
        space: str,
        end_line: int,
        unclosed: bool = False,
    ) -> UnifiedSymbol:
        meta = {"space": space, "spaces": [space], "type": "subcircuit"}
        if unclosed:
            meta["unclosed"] = True
        return UnifiedSymbol(
            id=UnifiedSymbol.compute_id(space, file_path, subckt.name, SymbolKind.CLASS.value, subckt.start_line),
            name=subckt.name,
            kind=SymbolKind.CLASS.value,
            file_path=file_path,
            line_number=subckt.start_line,
            end_line=end_line,
            language=LanguageType.SPICE.value,
            docstring=subckt.docstring,
            signature=subckt.signature,
            children=tuple(subckt.members),
            metadata=meta,
        )

    def _handle_dot_directive(
        self,
        first_tok_upper: str,
        tokens: List[str],
        log_line: LogicalLine,
        file_path: str,
        space: str,
        current_subckt: Optional[_SubcircuitScope],
        symbols: List[UnifiedSymbol],
    ) -> Tuple[bool, Optional[_SubcircuitScope]]:
        clean = log_line.clean_text

        if first_tok_upper in {".SUBCKT", ".MACRO"}:
            if len(tokens) >= 2:
                subckt_name = tokens[1]
                if current_subckt is not None:
                    symbols.append(
                        self._build_subckt_symbol(
                            current_subckt, file_path, space, log_line.start_line - 1
                        )
                    )
                current_subckt = _SubcircuitScope(
                    name=subckt_name,
                    start_line=log_line.start_line,
                    signature=clean,
                    docstring=log_line.docstring,
                    members=[],
                )
            return True, current_subckt

        if first_tok_upper in {".ENDS", ".EOM"}:
            if current_subckt is not None:
                symbols.append(
                    self._build_subckt_symbol(current_subckt, file_path, space, log_line.end_line)
                )
                current_subckt = None
            return True, current_subckt

        if first_tok_upper == ".MODEL":
            if len(tokens) >= 2:
                model_name = tokens[1]
                model_type = tokens[2] if len(tokens) >= 3 else ""
                if current_subckt is not None:
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
                    symbols.append(
                        UnifiedSymbol(
                            id=UnifiedSymbol.compute_id(
                                space, file_path, model_name, SymbolKind.STRUCT.value, log_line.start_line
                            ),
                            name=model_name,
                            kind=SymbolKind.STRUCT.value,
                            file_path=file_path,
                            line_number=log_line.start_line,
                            end_line=log_line.end_line,
                            language=LanguageType.SPICE.value,
                            docstring=log_line.docstring,
                            signature=clean,
                            metadata={"space": space, "spaces": [space], "model_type": model_type},
                        )
                    )
            return True, current_subckt

        if first_tok_upper == ".PARAM":
            params = _parse_params_from_line(tokens)
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
                            id=UnifiedSymbol.compute_id(
                                space, file_path, p_name, SymbolKind.VARIABLE.value, log_line.start_line
                            ),
                            name=p_name,
                            kind=SymbolKind.VARIABLE.value,
                            file_path=file_path,
                            line_number=log_line.start_line,
                            end_line=log_line.end_line,
                            language=LanguageType.SPICE.value,
                            docstring=log_line.docstring,
                            signature=sig,
                            metadata={"space": space, "spaces": [space], "value": p_val},
                        )
                    )
            return True, current_subckt

        if first_tok_upper in {".INCLUDE", ".INC", ".LIB", ".HDL"}:
            if len(tokens) >= 2:
                raw_target = tokens[1].strip("'\"")
                symbols.append(
                    UnifiedSymbol(
                        id=UnifiedSymbol.compute_id(
                            space, file_path, raw_target, SymbolKind.MACRO.value, log_line.start_line
                        ),
                        name=raw_target,
                        kind=SymbolKind.MACRO.value,
                        file_path=file_path,
                        line_number=log_line.start_line,
                        end_line=log_line.end_line,
                        language=LanguageType.SPICE.value,
                        docstring=log_line.docstring,
                        signature=clean,
                        metadata={"space": space, "spaces": [space], "directive": first_tok_upper},
                    )
                )
            return True, current_subckt

        if first_tok_upper == ".GLOBAL":
            for node_name in tokens[1:]:
                symbols.append(
                    UnifiedSymbol(
                        id=UnifiedSymbol.compute_id(
                            space, file_path, node_name, SymbolKind.MACRO.value, log_line.start_line
                        ),
                        name=node_name,
                        kind=SymbolKind.MACRO.value,
                        file_path=file_path,
                        line_number=log_line.start_line,
                        end_line=log_line.end_line,
                        language=LanguageType.SPICE.value,
                        docstring=log_line.docstring,
                        signature=clean,
                        metadata={"space": space, "spaces": [space], "type": "global_node"},
                    )
                )
            return True, current_subckt

        return False, current_subckt

    def _handle_element_instance(
        self,
        first_tok: str,
        first_tok_upper: str,
        log_line: LogicalLine,
        file_path: str,
        space: str,
        current_subckt: Optional[_SubcircuitScope],
        symbols: List[UnifiedSymbol],
    ) -> None:
        prefix_char = first_tok_upper[0] if first_tok_upper else ""
        clean = log_line.clean_text

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
                symbols.append(
                    UnifiedSymbol(
                        id=UnifiedSymbol.compute_id(
                            space, file_path, inst_name, SymbolKind.FUNCTION.value, log_line.start_line
                        ),
                        name=inst_name,
                        kind=SymbolKind.FUNCTION.value,
                        file_path=file_path,
                        line_number=log_line.start_line,
                        end_line=log_line.end_line,
                        language=LanguageType.SPICE.value,
                        docstring=log_line.docstring,
                        signature=clean,
                        metadata={"space": space, "spaces": [space], "type": "subcircuit_instance"},
                    )
                )
            return

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
            elif prefix_char in {"V", "I", "B"}:
                symbols.append(
                    UnifiedSymbol(
                        id=UnifiedSymbol.compute_id(
                            space, file_path, inst_name, SymbolKind.VARIABLE.value, log_line.start_line
                        ),
                        name=inst_name,
                        kind=SymbolKind.VARIABLE.value,
                        file_path=file_path,
                        line_number=log_line.start_line,
                        end_line=log_line.end_line,
                        language=LanguageType.SPICE.value,
                        docstring=log_line.docstring,
                        signature=clean,
                        metadata={"space": space, "spaces": [space], "type": f"element_{prefix_char}"},
                    )
                )

    def _parse_state_machine(
        self,
        logical_lines: List[LogicalLine],
        file_path: str,
        space: str,
        total_lines: int,
    ) -> List[UnifiedSymbol]:
        symbols: List[UnifiedSymbol] = []
        current_subckt: Optional[_SubcircuitScope] = None

        for idx, log_line in enumerate(logical_lines):
            clean = log_line.clean_text
            tokens = _split_tokens(clean)
            if not tokens:
                continue

            first_tok = tokens[0]
            first_tok_upper = first_tok.upper()

            if (
                idx == 0
                and not first_tok.startswith(".")
                and not any(first_tok_upper.startswith(p) for p in self.ELEMENT_PREFIXES)
            ):
                log_debug(f"Skipping probable SPICE title line: '{clean}'")
                continue

            handled, current_subckt = self._handle_dot_directive(
                first_tok_upper, tokens, log_line, file_path, space, current_subckt, symbols
            )
            if handled:
                continue

            self._handle_element_instance(
                first_tok, first_tok_upper, log_line, file_path, space, current_subckt, symbols
            )

        if current_subckt is not None:
            symbols.append(
                self._build_subckt_symbol(
                    current_subckt, file_path, space, total_lines, unclosed=True
                )
            )

        return symbols

    def extract_call_sites(
        self,
        file_path: Union[str, Path],
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        """Extract subcircuit instantiation (`X...`) call sites."""
        if not content or not content.strip():
            return []
        norm_path = str(file_path).replace("\\", "/")
        logical_lines = self._aggregate_logical_lines(content.splitlines())
        target_symbols = (
            symbols if symbols is not None else self.parse(file_path=norm_path, content=content, space=space)
        )
        sites: List[SymbolCallSite] = []
        current_subckt_name = "<netlist>"
        for log_line in logical_lines:
            tokens = _split_tokens(log_line.clean_text)
            if not tokens:
                continue
            first_upper = tokens[0].upper()
            if first_upper in {".SUBCKT", ".MACRO"} and len(tokens) >= 2:
                current_subckt_name = tokens[1]
                continue
            if first_upper in {".ENDS", ".EOM"}:
                current_subckt_name = "<netlist>"
                continue
            if first_upper.startswith("X") and len(tokens) >= 2:
                # Find the last token without '=' as the instantiated subcircuit name
                callee_subckt = ""
                for tok in reversed(tokens[1:]):
                    if "=" not in tok:
                        callee_subckt = tok
                        break
                if callee_subckt:
                    caller_id = ""
                    for s in target_symbols:
                        if s.line_number <= log_line.start_line <= s.end_line and s.kind == SymbolKind.CLASS.value:
                            caller_id = s.id
                            break
                    sites.append(
                        SymbolCallSite(
                            callee_name=callee_subckt,
                            line_number=log_line.start_line,
                            caller_symbol_id=caller_id,
                            caller_member_name=current_subckt_name,
                            context_prefix="",
                            file_path=norm_path,
                            space=space,
                        )
                    )
        return sites

