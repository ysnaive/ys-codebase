"""
knowledge-db 全方位 AST 符號結構化選擇器 (SymbolSelector)
支援類型前綴 (class/struct/fn 等)、階層範疇 (scope.name) 與可調用限定符號 (())
100% 採用純 Python 原生標準庫，零外部依賴
"""

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .schema import SymbolKind, UnifiedSymbol


# 類型前綴至 SymbolKind 集合之正規化映射表
KIND_PREFIX_MAP: Any = MappingProxyType({
    "class": frozenset({SymbolKind.CLASS.value}),
    "cls": frozenset({SymbolKind.CLASS.value}),
    "struct": frozenset({SymbolKind.STRUCT.value}),
    "interface": frozenset({SymbolKind.INTERFACE.value}),
    "iface": frozenset({SymbolKind.INTERFACE.value}),
    "enum": frozenset({SymbolKind.ENUM.value}),
    "fn": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "func": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "def": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "function": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "method": frozenset({SymbolKind.METHOD.value}),
    "meth": frozenset({SymbolKind.METHOD.value}),
    "type": frozenset({SymbolKind.TYPE_ALIAS.value}),
    "typedef": frozenset({SymbolKind.TYPE_ALIAS.value}),
    "const": frozenset({SymbolKind.CONSTANT.value}),
    "constant": frozenset({SymbolKind.CONSTANT.value}),
    "var": frozenset({SymbolKind.VARIABLE.value}),
    "variable": frozenset({SymbolKind.VARIABLE.value}),
    "let": frozenset({SymbolKind.VARIABLE.value}),
    "macro": frozenset({SymbolKind.MACRO.value}),
    "doc": frozenset({
        SymbolKind.DOC_HEADING_1.value,
        SymbolKind.DOC_HEADING_2.value,
        SymbolKind.DOC_HEADING_3.value,
        SymbolKind.DOC_HEADING_4.value,
        SymbolKind.DOC_SECTION.value,
    }),
    "h1": frozenset({SymbolKind.DOC_HEADING_1.value}),
    "h2": frozenset({SymbolKind.DOC_HEADING_2.value}),
    "h3": frozenset({SymbolKind.DOC_HEADING_3.value}),
    "h4": frozenset({SymbolKind.DOC_HEADING_4.value}),
})

CALLABLE_KINDS: Any = frozenset({
    SymbolKind.FUNCTION.value,
    SymbolKind.METHOD.value,
    "function",
    "method",
    "constructor",
})


@dataclass(frozen=True)
class ParsedSelector:
    """結構化符號選擇器容器"""
    raw_query: str
    identifier: str
    scope: Optional[str] = None
    target_kinds: Optional[Set[str]] = None
    is_callable: bool = False

    def matches(self, sym: UnifiedSymbol) -> bool:
        """驗證 UnifiedSymbol 是否符合選擇器條件"""
        sym_kind = sym.kind.value if isinstance(sym.kind, SymbolKind) else str(sym.kind)

        # 1. 類型約束驗證 (Kind Check)
        if self.target_kinds and sym_kind not in self.target_kinds:
            return False

        # 2. 可調用約制驗證 (Callable Check: `()`)
        if self.is_callable and sym_kind not in CALLABLE_KINDS:
            return False

        # 3. 識別符名稱驗證 (Identifier Check)
        ident_lower = self.identifier.lower()
        sym_name_lower = sym.name.lower()
        meta_short = (sym.metadata.get("short_name") or "").lower() if sym.metadata else ""

        # 精準比對短名或全名 (支援 '.' 與 '::' 分隔符及 metadata.short_name)
        name_matched = False
        if sym_name_lower == ident_lower or (meta_short and meta_short == ident_lower):
            name_matched = True
        elif "." in sym.name or "::" in sym.name:
            short_name = re.split(r"[.:]+", sym.name)[-1].lower()
            if short_name == ident_lower:
                name_matched = True

        if not name_matched:
            return False

        # 4. 範疇約束驗證 (Scope Check: `scope.identifier` / `scope::identifier`)
        if self.scope:
            scope_lower = self.scope.lower().replace("::", ".")
            scope_matched = False

            meta_parent = (sym.metadata.get("parent_scope") or "").lower() if sym.metadata else ""
            if meta_parent and (meta_parent == scope_lower or scope_lower.endswith(f".{meta_parent}")):
                scope_matched = True

            # 4.1 比對 sym.name 中的直接前綴 (e.g. sym.name == "Foo.bar" or "Foo::bar", scope == "Foo")
            if not scope_matched and ("." in sym.name or "::" in sym.name):
                sym_parts = re.split(r"[.:]+", sym.name)
                sym_prefix = ".".join(sym_parts[:-1]).lower()
                if sym_prefix == scope_lower or sym_prefix.endswith(f".{scope_lower}"):
                    scope_matched = True

            # 4.2 比對 parent_id (若符號掛於特定類別/父節點之下)
            if not scope_matched and sym.parent_id:
                parent_id_clean = sym.parent_id.lower().replace("\\", "/").split("/")[-1]
                if (
                    parent_id_clean == scope_lower
                    or parent_id_clean.endswith(f":{scope_lower}")
                    or parent_id_clean.endswith(f".{scope_lower}")
                ):
                    scope_matched = True

            # 4.3 比對 sym.fqn 的直接父層節點 (e.g. fqn == "pkg.mod.Foo.bar", scope == "Foo")
            if not scope_matched and sym.fqn:
                fqn_parts = sym.fqn.split(".")
                if len(fqn_parts) >= 2:
                    direct_parent = fqn_parts[-2]
                    # 優先大小寫吻合，或非頂層函式時的不區分大小寫吻合
                    if direct_parent == self.scope:
                        scope_matched = True
                    elif direct_parent.lower() == scope_lower and sym_kind != SymbolKind.FUNCTION.value:
                        scope_matched = True

            if not scope_matched:
                return False

        return True


class SymbolSelector:
    """微型符號選擇器語法解析與比對引擎"""

    # 正則表達式：[<kind_prefix>\s+][<scope>.]<identifier>[()]
    _PATTERN = re.compile(
        r"^(?:(?P<kind>[a-zA-Z0-9_-]+)\s+)?"       # 可選類型前綴 (e.g. 'class ', 'fn ')
        r"(?:(?P<scope>[a-zA-Z0-9_$:./~<>]+)(?:\.|::))?" # 可選範疇 (e.g. 'Foo.', 'Foo::', 'pkg.mod.')
        r"(?P<name>~?[a-zA-Z0-9_$]+)(?:<[^>]*>)?"   # 識別符名稱 (支援 C++ ~dtor 與泛型剝離)
        r"(?P<callable>\([^)]*\))?$",             # 可選調用符號 '()' 或 '(params)'
        re.IGNORECASE,
    )

    @classmethod
    def _fallback_parse(cls, clean_expr: str) -> ParsedSelector:
        is_call = clean_expr.endswith("()")
        base = clean_expr[:-2].strip() if is_call else clean_expr
        base = re.sub(r"<[^>]*>", "", base)
        scope = None
        norm_sep = base.replace("::", ".")
        if "." in norm_sep:
            parts = norm_sep.split(".")
            scope = ".".join(parts[:-1])
            name = parts[-1]
        else:
            name = base
        return ParsedSelector(
            raw_query=clean_expr,
            identifier=name,
            scope=scope,
            target_kinds=None,
            is_callable=is_call,
        )

    @classmethod
    def parse(cls, expr: str) -> ParsedSelector:
        """
        解析選擇器語法表達式為 ParsedSelector
        支援範例：
          - 'a' -> 任何名為 a 的節點
          - 'foo.a' -> 在 foo 範疇內名為 a 的節點
          - 'foo.a()' -> 在 foo 範疇內名為 a 且為可調用之節點
          - 'class Foo' -> 類別節點 Foo
          - 'struct Point.x' -> 在 Point 結構內的 x 成員
          - 'fn run()' -> 函式/方法 run
          - 'const MAX_SIZE' -> 常數 MAX_SIZE
        """
        clean_expr = expr.strip()
        if not clean_expr:
            return ParsedSelector(raw_query="", identifier="")

        m = cls._PATTERN.match(clean_expr)
        if not m:
            return cls._fallback_parse(clean_expr)

        kind_str = m.group("kind")
        scope_str = m.group("scope")
        name_str = m.group("name")
        callable_str = m.group("callable")

        target_kinds: Optional[Set[str]] = None
        if kind_str:
            mapped = KIND_PREFIX_MAP.get(kind_str.lower())
            if mapped is None:
                return cls._fallback_parse(clean_expr)
            target_kinds = set(mapped)

        is_callable = bool(callable_str)
        if target_kinds and target_kinds.issubset(CALLABLE_KINDS):
            is_callable = True

        return ParsedSelector(
            raw_query=clean_expr,
            identifier=name_str,
            scope=scope_str,
            target_kinds=target_kinds,
            is_callable=is_callable,
        )

    @classmethod
    def find_matches(
        cls,
        expr: str,
        symbols_pool: Iterable[UnifiedSymbol],
    ) -> List[UnifiedSymbol]:
        """
        在符號池中查找符合選擇器之符號列表，並按精確度排序
        """
        selector = cls.parse(expr)
        matches: List[Tuple[float, UnifiedSymbol]] = []

        for sym in symbols_pool:
            if selector.matches(sym):
                score = 0.0
                # 精確全名匹配加分
                if sym.name == selector.identifier:
                    score += 10.0
                elif sym.name.lower() == selector.identifier.lower():
                    score += 8.0
                else:
                    score += 5.0

                # 範疇完全吻合加分
                if selector.scope and sym.name.startswith(f"{selector.scope}."):
                    score += 5.0

                matches.append((score, sym))

        matches.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in matches]
