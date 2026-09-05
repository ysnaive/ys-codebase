"""
knowledge-db Tree-sitter 通用語意驅動引擎 (TreeSitterDriver)
基於聲明式 S-Expression (.scm) 查詢檔執行多語言語法樹符號、調用點與 Import 提取。
"""

import importlib
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    import tree_sitter
except ImportError:
    tree_sitter = None

from ..schema import (
    LanguageConfig,
    LanguageType,
    MemberInfo,
    SymbolCallSite,
    SymbolKind,
    UnifiedSymbol,
)
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.treesitter")


def _clean_docstring(raw: str, lang_id: str) -> str:
    """清理多語言 docstring 或註解標記"""
    if not raw:
        return ""
    text = raw.strip()
    # Python triple quotes or single quotes
    if lang_id == "python":
        for q in ('"""', "'''", '"', "'"):
            if text.startswith(q) and text.endswith(q) and len(text) >= 2 * len(q):
                text = text[len(q) : -len(q)].strip()
                break
        return text

    # C / C++ / C# / JS / TS: /// or // or /* */ or XML tags
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        l = line.strip()
        if l.startswith("///"):
            l = l[3:].strip()
        elif l.startswith("//"):
            l = l[2:].strip()
        elif l.startswith("/*"):
            l = l[2:].strip()
        if l.endswith("*/"):
            l = l[:-2].strip()
        if l.startswith("*"):
            l = l[1:].strip()
        # Strip XML tags if present (<summary>, </summary>, etc.)
        l = re.sub(r"<[^>]+>", "", l).strip()
        if l:
            cleaned_lines.append(l)
    return "\n".join(cleaned_lines).strip()


class TreeSitterDriver(BaseParser):
    """
    通用 Tree-sitter 驅動解析器 (一等公民通用引擎)
    接收 LanguageConfig 配置，載入動態 Grammar 與 S-Expression 查詢檔執行符號解析。
    """

    def __init__(self, config: LanguageConfig):
        self.config = config
        self._language: Optional[Any] = None
        self._parser: Optional[Any] = None
        self._query: Optional[Any] = None
        self._init_driver()

    def _init_driver(self) -> None:
        """動態載入 Grammar 與編譯 S-Expression Query"""
        if tree_sitter is None:
            logger.warning("tree_sitter module is not installed; TreeSitterDriver cannot function.")
            return

        if self.config.mode != "tree_sitter":
            return

        # 1. 載入 Language Grammar
        if self.config.grammar:
            try:
                grammar_str = self.config.grammar
                if ":" in grammar_str:
                    mod_name, func_name = grammar_str.split(":", 1)
                else:
                    mod_name = grammar_str
                    func_name = "language"

                mod = importlib.import_module(mod_name)
                if hasattr(mod, func_name):
                    lang_func = getattr(mod, func_name)
                elif hasattr(mod, f"language_{self.config.id}"):
                    lang_func = getattr(mod, f"language_{self.config.id}")
                else:
                    raise AttributeError(f"Module '{mod_name}' has no function '{func_name}'")

                raw_lang = lang_func()
                self._language = tree_sitter.Language(raw_lang)
                self._parser = tree_sitter.Parser(self._language)
            except Exception as e:
                logger.warning(
                    f"TreeSitterDriver: Failed to load grammar '{self.config.grammar}' for '{self.config.id}': {e} (EC-02)"
                )
                self._language = None
                self._parser = None

        # 2. 載入並編譯 Query File
        if self._language and self.config.query_file:
            candidates = [
                Path(self.config.query_file),
                Path(__file__).resolve().parents[2] / self.config.query_file,
                Path(__file__).resolve().parents[1] / self.config.query_file,
                Path(__file__).resolve().parents[2] / "assets" / "queries" / Path(self.config.query_file).name,
            ]
            q_path = None
            for c in candidates:
                if c.exists() and c.is_file():
                    q_path = c
                    break

            if q_path:
                try:
                    with open(q_path, "r", encoding="utf-8") as f:
                        q_str = f.read()
                    self._query = tree_sitter.Query(self._language, q_str)
                except Exception as e:
                    logger.warning(
                        f"TreeSitterDriver: Failed to compile query '{q_path}' for '{self.config.id}': {e} (EC-02)"
                    )
                    self._query = None
            else:
                logger.warning(
                    f"TreeSitterDriver: Query file '{self.config.query_file}' not found for '{self.config.id}' (EC-02)"
                )
                self._query = None

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.config.extensions

    def _extract_preceding_comment(self, node: Any, content_lines: List[str]) -> str:
        """提取節點上方緊鄰之註解行作為 Docstring"""
        try:
            target_node = node
            if target_node.parent and target_node.parent.type in ("export_statement", "decorated_definition"):
                target_node = target_node.parent
            curr = target_node.prev_named_sibling
            comment_lines = []
            while curr and curr.type == "comment":
                comment_lines.insert(0, curr.text.decode("utf-8", errors="replace"))
                curr = curr.prev_named_sibling
            if comment_lines:
                return _clean_docstring("\n".join(comment_lines), self.config.id)
        except Exception:
            pass
        return ""

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []

        lines = content.splitlines()

        # EC-02: 若 parser 或 query 未成功載入，優雅降級
        if self._parser is None or self._query is None:
            if self.config.id == "markdown" and lines:
                return self._fallback_markdown(normalized_path, lines, space)
            return []

        try:
            content_bytes = content.encode("utf-8", errors="replace")
            tree = self._parser.parse(content_bytes)
        except Exception as e:
            logger.warning(f"TreeSitterDriver: parse error on '{normalized_path}': {e} (EC-01)")
            return []

        cursor = tree_sitter.QueryCursor(self._query)
        matches = cursor.matches(tree.root_node)

        raw_items: List[Dict[str, Any]] = []

        # 1. 萃取所有符號定義
        for _, captures in matches:
            # 尋找 definition capture
            def_capture_key = None
            for key in captures:
                if key.startswith("definition."):
                    def_capture_key = key
                    break
            if not def_capture_key:
                continue

            def_kind = def_capture_key.split(".", 1)[1]
            def_nodes = captures[def_capture_key]
            if not def_nodes:
                continue
            def_node = def_nodes[0]

            # 提取名稱
            name = ""
            if "symbol.name" in captures and captures["symbol.name"]:
                name = captures["symbol.name"][0].text.decode("utf-8", errors="replace").strip()
            if not name:
                name = def_node.text.decode("utf-8", errors="replace").splitlines()[0][:60].strip()

            # 提取簽名
            first_line = def_node.text.decode("utf-8", errors="replace").splitlines()[0].strip()
            if first_line.endswith("{") or first_line.endswith(":"):
                first_line = first_line[:-1].strip()

            if self.config.id == "python" and ("def " in first_line or "class " in first_line):
                signature = first_line
            elif "symbol.signature" in captures and captures["symbol.signature"]:
                signature = captures["symbol.signature"][0].text.decode("utf-8", errors="replace").strip()
            else:
                signature = first_line

            # 提取回傳型別
            return_type = ""
            if "symbol.return_type" in captures and captures["symbol.return_type"]:
                return_type = captures["symbol.return_type"][0].text.decode("utf-8", errors="replace").strip()
                if return_type.startswith("->"):
                    return_type = return_type[2:].strip()
                if return_type.startswith(":"):
                    return_type = return_type[1:].strip()

            # 提取 Docstring
            docstring = ""
            if "symbol.docstring" in captures and captures["symbol.docstring"]:
                raw_doc = captures["symbol.docstring"][0].text.decode("utf-8", errors="replace")
                docstring = _clean_docstring(raw_doc, self.config.id)
            if not docstring:
                docstring = self._extract_preceding_comment(def_node, lines)

            start_line = def_node.start_point[0] + 1
            end_line = def_node.end_point[0] + 1
            start_byte = def_node.start_byte
            end_byte = def_node.end_byte

            # 特殊語言處理：Markdown
            if self.config.id == "markdown":
                if def_kind == "heading":
                    # 依 heading 前綴 '#' 計算 level
                    node_text = def_node.text.decode("utf-8", errors="replace").lstrip()
                    level = 1
                    if node_text.startswith("#"):
                        level = len(node_text) - len(node_text.lstrip("#"))
                    kind_map = {
                        1: SymbolKind.DOC_HEADING_1.value,
                        2: SymbolKind.DOC_HEADING_2.value,
                        3: SymbolKind.DOC_HEADING_3.value,
                        4: SymbolKind.DOC_HEADING_4.value,
                    }
                    def_kind = kind_map.get(level, SymbolKind.DOC_HEADING_4.value)
                    signature = f"{'#' * level} {name}"
                elif def_kind == "table":
                    def_kind = SymbolKind.DOC_TABLE.value
                    table_first_line = def_node.text.decode("utf-8", errors="replace").splitlines()[0]
                    name = f"Table: {table_first_line.strip('|').strip()[:50]}"
                    signature = "markdown_table"
                    docstring = def_node.text.decode("utf-8", errors="replace").strip()

            raw_items.append({
                "short_name": name,
                "kind": def_kind,
                "signature": signature,
                "return_type": return_type,
                "docstring": docstring,
                "start_line": start_line,
                "end_line": end_line,
                "start_byte": start_byte,
                "end_byte": end_byte,
                "node": def_node,
            })

        # Markdown 標題段落 docstring 累積處理
        if self.config.id == "markdown" and raw_items:
            # 依行號排序
            raw_items.sort(key=lambda x: x["start_line"])
            for idx, item in enumerate(raw_items):
                if item["kind"].startswith("doc_heading") and not item["docstring"]:
                    s_ln = item["start_line"]
                    e_ln = raw_items[idx + 1]["start_line"] - 1 if idx + 1 < len(raw_items) else len(lines)
                    body_lines = lines[s_ln:e_ln]
                    item["docstring"] = "\n".join(body_lines).strip()
                    item["end_line"] = max(e_ln, s_ln)

        # EC-03: Markdown 若無任何 Heading / Table，降級為 DOC_SECTION
        if self.config.id == "markdown" and not raw_items and lines:
            return self._fallback_markdown(normalized_path, lines, space)

        if not raw_items:
            return []

        # 2. 去重 (同一個節點若重複被 capture)
        seen_keys = set()
        dedup_items = []
        for item in raw_items:
            k = (item["start_byte"], item["end_byte"], item["kind"], item["short_name"])
            if k not in seen_keys:
                seen_keys.add(k)
                dedup_items.append(item)

        # 3. 排序 (start_byte 遞增, end_byte 遞減以確保父節點排在子節點前)
        dedup_items.sort(key=lambda x: (x["start_byte"], -x["end_byte"]))

        # 4. 堆疊演算法構建階層樹狀結構
        scope_sep = "::" if self.config.id in ("cpp", "c") else "."
        stack: List[Dict[str, Any]] = []

        for item in dedup_items:
            while stack and not (
                stack[-1]["start_byte"] <= item["start_byte"] and item["end_byte"] <= stack[-1]["end_byte"]
            ):
                stack.pop()

            if stack:
                parent = stack[-1]
                item["parent_id"] = parent["id"]
                item["scope_path"] = parent["scope_path"] + [parent["short_name"]]
                item["fqn"] = scope_sep.join(item["scope_path"] + [item["short_name"]])
                parent["children_items"].append(item)
                if item["kind"] == "function" and parent["kind"] in ("class", "struct", "interface"):
                    item["kind"] = "method"
            else:
                item["parent_id"] = None
                item["scope_path"] = []
                item["fqn"] = item["short_name"]

            # 計算 SHA1 ID
            item["id"] = UnifiedSymbol.compute_id(
                space=space,
                file_path=normalized_path,
                name=item["fqn"],
                kind=item["kind"],
                line_number=item["start_line"],
            )
            item["children_items"] = []
            stack.append(item)

        # 5. 物化 UnifiedSymbol 與向後相容 members 屬性
        symbols: List[UnifiedSymbol] = []

        for item in dedup_items:
            # field (類別屬性/欄位) 僅保留於類別 members 中，不單獨作為獨立一級 UnifiedSymbol 輸出
            if item["kind"] == "field" and item["parent_id"]:
                continue

            # 建立向後相容之 MemberInfo 清單
            members_list = []
            for child in item["children_items"]:
                vis = "public"
                c_name = child["short_name"]
                if c_name.startswith("__") and not c_name.endswith("__"):
                    vis = "private"
                elif c_name.startswith("_"):
                    vis = "protected"

                members_list.append(
                    MemberInfo(
                        name=child["short_name"],
                        kind=child["kind"],
                        signature=child["signature"],
                        docstring=child["docstring"],
                        visibility=vis,
                        line_number=child["start_line"],
                    )
                )

            search_payload = f"{item['fqn']} {item['short_name']} {item['docstring']} {item['signature']}".strip()

            # 對於巢狀符號 (如方法)，其 name 設定為 fqn 以相容 sym_map[name] 查詢
            sym_name = item["fqn"] if item["parent_id"] else item["short_name"]

            metadata = {
                "short_name": item["short_name"],
                "parent_scope": item["scope_path"][-1] if item["scope_path"] else "",
                "end_line": item["end_line"],
                "scope_path": item["scope_path"],
                "start_byte": item["start_byte"],
                "end_byte": item["end_byte"],
            }

            symbols.append(
                UnifiedSymbol(
                    id=item["id"],
                    name=sym_name,
                    kind=item["kind"],
                    file_path=normalized_path,
                    line_number=item["start_line"],
                    end_line=item["end_line"],
                    language=self.config.id,
                    docstring=item["docstring"],
                    signature=item["signature"],
                    fqn=item["fqn"],
                    scope_path=scope_sep.join(item["scope_path"]),
                    parent_id=item["parent_id"],
                    children=(),
                    parameters=(),
                    return_type=item["return_type"],
                    search_payload=search_payload,
                    members=tuple(members_list),
                    metadata=metadata,
                )
            )

        return symbols

    def _fallback_markdown(self, normalized_path: str, lines: List[str], space: str) -> List[UnifiedSymbol]:
        """Markdown 無 Heading 時安全降級為 DOC_SECTION (EC-03)"""
        non_empty = [l for l in lines if l.strip()]
        sec_name = non_empty[0][:60] if non_empty else os.path.basename(normalized_path)
        doc = "\n".join(lines[:200]).strip()
        total_lines = len(lines)
        sym_id = UnifiedSymbol.compute_id(
            space=space,
            file_path=normalized_path,
            name=sec_name,
            kind=SymbolKind.DOC_SECTION.value,
            line_number=1,
        )
        return [
            UnifiedSymbol(
                id=sym_id,
                name=sec_name,
                kind=SymbolKind.DOC_SECTION.value,
                file_path=normalized_path,
                line_number=1,
                end_line=total_lines,
                language="markdown",
                docstring=doc,
                signature="markdown_section",
                members=(),
                metadata={"fallback": True, "end_line": total_lines},
            )
        ]

    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip() or self._parser is None or self._query is None:
            return []

        call_sites: List[SymbolCallSite] = []

        # Markdown 特殊調用萃取 (包含 [`Name`](link) 與行內 `Name`)
        if self.config.id == "markdown":
            link_re = re.compile(r"\[`?([A-Za-z0-9_$.]+)`?\]\((?:file:///)?([^)#\s]+)(?:#L?(\d+))?\)")
            code_re = re.compile(r"`([A-Za-z0-9_$]+\.[A-Za-z0-9_$]+)(?:\(\))?`")
            current_heading = "<document>"
            heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
            for i, line in enumerate(content.splitlines(), start=1):
                hm = heading_re.match(line.strip())
                if hm:
                    current_heading = hm.group(2).strip()
                    continue
                for m in link_re.finditer(line):
                    sym_str = m.group(1)
                    prefix, callee = (sym_str.rsplit(".", 1)[0], sym_str.rsplit(".", 1)[1]) if "." in sym_str else ("", sym_str)
                    call_sites.append(
                        SymbolCallSite(
                            callee_name=callee,
                            line_number=i,
                            caller_member_name=current_heading,
                            context_prefix=prefix,
                            file_path=normalized_path,
                            space=space,
                        )
                    )
                for m in code_re.finditer(line):
                    sym_str = m.group(1)
                    prefix, callee = sym_str.rsplit(".", 1)
                    call_sites.append(
                        SymbolCallSite(
                            callee_name=callee,
                            line_number=i,
                            caller_member_name=current_heading,
                            context_prefix=prefix,
                            file_path=normalized_path,
                            space=space,
                        )
                    )
            return call_sites

        try:
            content_bytes = content.encode("utf-8", errors="replace")
            tree = self._parser.parse(content_bytes)
        except Exception:
            return []

        cursor = tree_sitter.QueryCursor(self._query)
        matches = cursor.matches(tree.root_node)

        # 萃取 symbols 用於定位調用者
        symbols = self.parse(file_path=file_path, content=content, space=space)

        for _, captures in matches:
            if "call.name" not in captures or not captures["call.name"]:
                continue

            name_node = captures["call.name"][0]
            callee_name = name_node.text.decode("utf-8", errors="replace").strip()
            line_no = name_node.start_point[0] + 1
            call_start_byte = name_node.start_byte

            # 前綴提取
            prefix = ""
            call_node = captures.get("call.site", [name_node])[0]
            call_text = call_node.text.decode("utf-8", errors="replace")
            if "." in call_text:
                parts = call_text.split("(", 1)[0].split(".")
                if len(parts) > 1 and parts[-1].strip() == callee_name:
                    prefix = ".".join(parts[:-1]).strip()
            elif "->" in call_text:
                parts = call_text.split("(", 1)[0].split("->")
                if len(parts) > 1 and parts[-1].strip() == callee_name:
                    prefix = "->".join(parts[:-1]).strip()
            elif "::" in call_text:
                parts = call_text.split("(", 1)[0].split("::")
                if len(parts) > 1 and parts[-1].strip() == callee_name:
                    prefix = "::".join(parts[:-1]).strip()

            if prefix in ("this", "this->", "this."):
                prefix = "self"

            # 定位所屬調用者方法/函式 (最內層優先)
            caller_name = "<module>"
            matching_syms = [s for s in symbols if s.line_number <= line_no <= s.end_line]
            matching_syms.sort(key=lambda s: (s.end_line - s.line_number))
            for sym in matching_syms:
                if sym.kind in ("method", "function"):
                    if sym.metadata.get("parent_scope"):
                        caller_name = f"{sym.metadata['parent_scope']}.{sym.metadata.get('short_name', sym.name)}"
                    else:
                        caller_name = sym.name
                    break
                elif sym.kind in ("class", "struct"):
                    caller_name = sym.name

            call_sites.append(
                SymbolCallSite(
                    callee_name=callee_name,
                    line_number=line_no,
                    caller_member_name=caller_name,
                    context_prefix=prefix,
                    file_path=normalized_path,
                    space=space,
                )
            )

        return call_sites

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        normalized_path = file_path.replace("\\", "/")
        imports: Dict[str, str] = {}
        if not content:
            return {}

        # Markdown 超連結提取
        if self.config.id == "markdown":
            link_re = re.compile(r"\[([^\]]+)\]\(([^)#\s]+)(?:#[^)]*)?\)")
            for match in link_re.finditer(content):
                text = match.group(1).strip()
                target = match.group(2).strip()
                if not target.startswith("http://") and not target.startswith("https://") and not target.startswith("mailto:"):
                    stem = Path(target).stem
                    imports[text] = target
                    imports[stem] = target
                    imports[target] = target
            return imports

        # Python: import x [as y], from x import y [as z]
        if self.config.id == "python":
            import_re = re.compile(r"^\s*import\s+([^\n]+)", re.MULTILINE)
            from_re = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s+([^\n]+)", re.MULTILINE)
            for m in import_re.finditer(content):
                mods = m.group(1).split(",")
                for mod_item in mods:
                    mod_item = mod_item.strip()
                    if " as " in mod_item:
                        orig, alias = mod_item.split(" as ", 1)
                        imports[alias.strip()] = orig.strip()
                    elif mod_item:
                        imports[mod_item] = mod_item
            for m in from_re.finditer(content):
                base_mod = m.group(1).strip()
                targets = m.group(2).split(",")
                for t in targets:
                    t = t.strip()
                    if " as " in t:
                        orig, alias = t.split(" as ", 1)
                        imports[alias.strip()] = f"{base_mod}.{orig.strip()}"
                    elif t:
                        imports[t] = f"{base_mod}.{t}"
            return imports

        # JS / TS: import ... from '...', require('...')
        if self.config.id in ("javascript", "typescript"):
            es_import = re.compile(r"import\s+(?:\{([^}]+)\}|([a-zA-Z0-9_$]+))\s+from\s+['\"]([^'\"]+)['\"]")
            for m in es_import.finditer(content):
                src = m.group(3)
                if m.group(2):
                    imports[m.group(2).strip()] = src
                if m.group(1):
                    for item in m.group(1).split(","):
                        item = item.strip()
                        if " as " in item:
                            orig, alias = item.split(" as ", 1)
                            imports[alias.strip()] = f"{src}.{orig.strip()}"
                        elif item:
                            imports[item] = f"{src}.{item}"
            req_destruct = re.compile(r"(?:const|let|var)\s+\{\s*([^}]+)\s*\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)")
            for m in req_destruct.finditer(content):
                src = m.group(2)
                for item in m.group(1).split(","):
                    item = item.strip()
                    if ":" in item:
                        orig, alias = item.split(":", 1)
                        imports[alias.strip()] = f"{src}.{orig.strip()}"
                    elif item:
                        imports[item] = f"{src}.{item}"
            req_single = re.compile(r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)")
            for m in req_single.finditer(content):
                imports[m.group(1).strip()] = m.group(2).strip()
            return imports

        # C / C++: #include <...>, using namespace X::Y;, using Alias = Target;
        if self.config.id in ("cpp", "c"):
            inc_re = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE)
            for m in inc_re.finditer(content):
                header = m.group(1).strip()
                stem = Path(header).stem
                imports[header] = header
                imports[stem] = header
            using_ns = re.compile(r"^\s*using\s+namespace\s+([a-zA-Z0-9_:]+);", re.MULTILINE)
            for m in using_ns.finditer(content):
                ns = m.group(1).strip()
                last = ns.split("::")[-1]
                imports[last] = ns
            using_alias = re.compile(r"^\s*using\s+([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_:]+);", re.MULTILINE)
            for m in using_alias.finditer(content):
                imports[m.group(1).strip()] = m.group(2).strip()
            return imports

        # C#: using ...; using Alias = Target;
        if self.config.id == "c_sharp":
            using_alias = re.compile(r"^\s*using\s+([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_.]+);", re.MULTILINE)
            for m in using_alias.finditer(content):
                imports[m.group(1).strip()] = m.group(2).strip()
            using_re = re.compile(r"^\s*using\s+(?:static\s+)?([a-zA-Z0-9_.]+);", re.MULTILINE)
            for m in using_re.finditer(content):
                ns = m.group(1).strip()
                if "=" in ns:
                    continue
                last = ns.split(".")[-1]
                imports[last] = ns
                imports[ns] = ns
            return imports

        return imports
